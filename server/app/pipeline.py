"""Analysis/generation job orchestration. Node ids belong exclusively to workflow sidecars."""
from __future__ import annotations

import json
import math
import os
import shutil
import uuid
from pathlib import Path

from .comfy import runner, read_json_output, generation_runner
from .config import settings
from .jobs import JobContext
from .media import ffmpeg, extract_audio_wav, extract_frame, stage_to_comfy_input, encode_alpha_webm
from .models import GenShot, InworldBody, Word
from .store import ProjectStore, write_json_atomic


def project_path(store: ProjectStore, pid: str, relative: str) -> Path:
    root = store.project_dir(pid).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or Path(relative).is_absolute():
        raise ValueError("Media and analysis paths must remain inside the project")
    return path


def progress(ctx: JobContext, label: str, base: float = .1):
    return lambda status, elapsed: ctx.progress(base, f"{label}: {status} ({elapsed:.0f}s)")


def timeline_words(data: dict, duration: float) -> list[Word]:
    words = []
    for i, item in enumerate(data.get("words", [])):
        start, end = max(0., float(item["start"])), float(item["end"])
        if duration > 0:
            end = min(end, duration)
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            continue
        words.append(Word(id=str(uuid.uuid4()), text=item["text"], start=start, end=end,
                          lineId=str(item.get("lineId", f"l{i // 6}"))))
    words.sort(key=lambda w: w.start)
    return words


def analyze_words(store: ProjectStore, pid: str, language: str, ctx: JobContext):
    project = store.load(pid)
    source = project.media.audio or project.media.video
    if source is None:
        raise ValueError("Upload audio or video before transcribing")
    pdir = store.project_dir(pid)
    lyrics = (project.media.lyrics or "").strip()
    data, engine, note, preview = None, "whisper", "", None
    if lyrics and os.environ.get("TYPESET_WORDS_ALIGNER", "1") != "0":
        # Known lyrics: acoustic forced alignment (TypesetAlignLyrics: HDemucs vocals -> MMS_FA CTC -> onsets).
        try:
            ctx.progress(.05, "Extracting song audio for lyric alignment")
            song = extract_audio_wav(project_path(store, pid, source.path), pdir / "analysis" / f"song_{ctx.id}.wav",
                                     44100, mono=False)
            timing = getattr(project, "timing", None) or {}
            timing = timing if isinstance(timing, dict) else timing.__dict__
            result = runner.run("align", {"audio": stage_to_comfy_input(song, pid, song.name), "lyrics": lyrics,
                                          "vocal_start": float(timing.get("vocalStart") or 0)},
                                pdir / "analysis" / ctx.id / "align", progress=progress(ctx, "Aligning lyrics (vocals + forced alignment)"))
            data = read_json_output(result.outputs["words_json"])
            if result.first("preview"):
                shutil.copy2(result.first("preview"), pdir / "analysis" / "words_align.png")
                preview = "analysis/words_align.png"
            engine = "align"
            note = f"forced alignment via ComfyUI workflow align.api.json (job {result.job_id[:8]})"
        except Exception as exc:  # noqa: BLE001 — fall back to Whisper, and say so
            note = f"lyric alignment failed ({type(exc).__name__}: {str(exc)[:160]}); "
            ctx.progress(.1, f"{note}falling back to Whisper")
    if data is None:
        ctx.progress(.05, "Extracting speech audio")
        wav = extract_audio_wav(project_path(store, pid, source.path), pdir / "analysis" / f"speech_{ctx.id}.wav")
        audio = stage_to_comfy_input(wav, pid, wav.name)
        result = runner.run("words", {"audio": audio, "lyrics": project.media.lyrics or "", "language": language},
                            pdir / "analysis" / ctx.id, progress=progress(ctx, "Transcribing"))
        data = read_json_output(result.outputs["words_json"])
        note += f"Whisper via words.api.json (job {result.job_id[:8]})" + ("; lyric matching is heuristic" if lyrics else "")
    words = timeline_words(data, project.duration)
    write_json_atomic(pdir / "analysis" / "words.json", data)
    def update(p):
        current_source = p.media.audio or p.media.video
        if current_source is None or current_source.path != source.path:
            raise ValueError("Source media changed during transcription; run analysis again")
        p.analysis.words = "analysis/words.json"
        p.words = words
    store.update(pid, update)
    low = sum(1 for w in data.get("words", []) if w.get("lowConfidence"))
    ctx.progress(1, f"{'Aligned' if engine == 'align' else 'Transcribed'} {len(words)} words"
                    + (f" ({low} low-confidence)" if engine == "align" else "") + f" — {note}")
    return {"words": len(words), "path": "analysis/words.json", "engine": engine, "note": note,
            **({"lowConfidence": low} if engine == "align" else {}), **({"preview": preview} if preview else {})}


MATTE_CHUNK_PIXELS = int(float(os.environ.get("TYPESET_MATTE_CHUNK_PIXELS", "64e6")))


def matte_chunk_frames(width: int, height: int, budget: int = MATTE_CHUNK_PIXELS) -> int:
    """Frames per BiRefNet batch. ComfyUI holds roughly 80-120 bytes per pixel per frame during the matte
    (float32 frames, RGBA output, mask, mask image, list copies before torch.cat), so a pixel budget
    keeps the peak bounded whatever the clip length: 64 MP ≈ 46 frames at 1080×1280, 62 at 1344×768."""
    return max(8, min(240, budget // max(1, width * height)))


def count_frames(video: Path) -> int:
    from .media import ffprobe_frames
    return ffprobe_frames(video)


def split_lossless(video: Path, chunk: int, total: int, out_dir: Path) -> list[Path]:
    """Cut `video` into chunks of `chunk` frames with lossless x264 (qp 0, same yuv420p samples), one
    ffmpeg pass. Decoding a chunk gives exactly the frames the whole file decodes to."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cuts = ",".join(str(k) for k in range(chunk, total, chunk))
    args = ["-i", video, "-an", "-c:v", "libx264", "-qp", "0", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-force_key_frames", f"expr:eq(mod(n,{chunk}),0)", "-f", "segment", "-reset_timestamps", "1"]
    if cuts:
        args += ["-segment_frames", cuts]
    else:
        args += ["-segment_time", "1000000"]
    ffmpeg(args + [out_dir / "chunk_%05d.mp4"], what="ffmpeg(split matte chunks)")
    return sorted(out_dir.glob("chunk_*.mp4"))


def free_comfy_models() -> None:
    """Best effort: ask ComfyUI to unload models and free memory (POST /free)."""
    try:
        import httpx
        httpx.post(f"{runner.comfyui_url}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
    except Exception:  # cleanup must never mask the original error
        pass


def analyze_matte(store: ProjectStore, pid: str, ctx: JobContext):
    project = store.load(pid)
    if project.media.video is None:
        raise ValueError("Upload a video before extracting a foreground")
    pdir = store.project_dir(pid)
    ctx.progress(.03, "Preparing video for foreground extraction")
    prepared = pdir / "analysis" / f"matte_input_{ctx.id}.mp4"
    ffmpeg(["-i", project_path(store, pid, project.media.video.path), "-an", "-vf",
            f"scale={project.width}:{project.height}:force_original_aspect_ratio=decrease,pad={project.width}:{project.height}:(ow-iw)/2:(oh-ih)/2,fps={project.fps}",
            "-t", str(project.duration), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", prepared])
    total = count_frames(prepared)
    per = matte_chunk_frames(project.width, project.height)
    work = pdir / "analysis" / ctx.id
    if total <= per:
        chunks = [prepared]  # short clip: one pass on the prepared file, exactly as before
    else:
        ctx.progress(.05, f"Splitting {total} frames into chunks of {per} (bounded memory)")
        chunks = split_lossless(prepared, per, total, work / "chunks")
    matte = pdir / "analysis" / f"matte_{ctx.id}"
    matte.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    from . import vision
    parts, done = [], 0
    chunked = len(chunks) > 1
    staged_dir = settings.comfy_input_dir / "typeset" / pid / ctx.id
    try:
        for k, chunk in enumerate(chunks):
            last = k == len(chunks) - 1
            label = "Extracting foreground" + (f" (chunk {k + 1}/{len(chunks)}, frames {done + 1}–{min(total, done + per)})" if len(chunks) > 1 else "")
            base = .08 + .72 * done / max(1, total)
            video = stage_to_comfy_input(chunk, pid, ctx.id, chunk.name) if len(chunks) > 1 else stage_to_comfy_input(chunk, pid, chunk.name)
            run_dir = work / f"run_{k:05d}" if len(chunks) > 1 else work
            result = runner.run("matte", {"video": video, "fps": project.fps, "frame_offset": done,
                                          "raw_tracks": len(chunks) > 1, "unload_model": last},
                                run_dir, progress=progress(ctx, label, base))
            frames = result.outputs["fg_png"]
            if not frames:
                raise ValueError(f"Matte workflow returned no foreground frames (chunk {k + 1})")
            for i, src in enumerate(frames, done + 1):
                with Image.open(src) as im:
                    # The browser and export must agree with project dimensions, even if a node resized its batch.
                    im.convert("RGBA").resize((project.width, project.height)).save(matte / f"fg_{i:05d}.png")
            part = read_json_output(result.outputs["tracks_json"])
            fs = [fr["f"] for t in part.get("tracks", []) for fr in t.get("frames", [])]
            if len(chunks) > 1 and done and fs and min(fs) < done:
                raise RuntimeError("ComfyUI's typeset_nodes MaskToTracks ignores frame_offset (old version loaded): "
                                   "restart ComfyUI so chunked matting can merge tracks")
            parts.append(part)
            done += len(frames)
            if len(chunks) > 1:
                shutil.rmtree(run_dir, ignore_errors=True)  # keep disk bounded too: the PNGs live in matte/
                (settings.comfy_input_dir / video).unlink(missing_ok=True)
                chunk.unlink(missing_ok=True)
    except BaseException:
        if chunked:
            free_comfy_models()  # unload_model is only set on the last chunk; don't leave BiRefNet resident
        raise
    finally:
        if chunked:  # temp chunk files, staged ComfyUI inputs and per-chunk run folders, on success or failure
            shutil.rmtree(work / "chunks", ignore_errors=True)
            for d in work.glob("run_*"):
                shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(staged_dir, ignore_errors=True)
    tracks = parts[0] if len(parts) == 1 else vision.merge_track_chunks(parts, project.fps, done)
    tracks_rel = f"analysis/tracks_{ctx.id}.json"
    write_json_atomic(pdir / tracks_rel, tracks)
    ctx.progress(.85, "Encoding transparent foreground preview")
    encode_alpha_webm(matte / "fg_%05d.png", project.fps, matte / "fg.webm")
    ctx.progress(.95, "Computing occupancy grid")
    from .analysis_v2 import write_occupancy
    probe = project.model_copy(update={"analysis": project.analysis.model_copy(update={"matte": f"analysis/{matte.name}/"})})
    occ_rel = write_occupancy(store, probe)
    def update(p):
        if p.media.video is None or p.media.video.path != project.media.video.path:
            raise ValueError("Video changed during foreground extraction; run analysis again")
        p.analysis.matte = f"analysis/{matte.name}/"
        p.analysis.tracks = tracks_rel
        p.analysis.occupancy = occ_rel
    store.update(pid, update)
    ctx.progress(1, f"Foreground ready: {done} frames" + (f" in {len(chunks)} chunks" if len(chunks) > 1 else ""))
    return {"frames": done, "matte": f"analysis/{matte.name}/", "tracks": tracks_rel, "occupancy": occ_rel,
            "chunks": len(chunks), "chunkFrames": per}


def generate_inworld(store: ProjectStore, pid: str, body: InworldBody, ctx: JobContext):
    project = store.load(pid)
    selected = [w for w in project.words if w.id in body.wordIds]
    if not selected:
        raise ValueError("Select at least one existing word")
    if project.media.video is None:
        raise ValueError("Upload a video to generate an in-world shot")
    if body.engine == "remote-minimax":
        return generate_inworld_remote(store, pid, body, selected, ctx)
    video_runner = generation_runner()
    if video_runner.remote:
        ctx.progress(.01, "Checking remote LTX nodes and weights")
        video_runner.preflight("ltx_i2v")
    shot = GenShot(id=str(uuid.uuid4()), wordIds=body.wordIds, start=body.start, end=body.end,
                   prompt=body.prompt, status="running", workflow="text_plate+ltx_i2v")
    store.update(pid, lambda p: p.shots.append(shot))
    pdir = store.project_dir(pid)
    dest = pdir / "gen" / shot.id
    dest.mkdir(parents=True, exist_ok=True)
    try:
        ctx.progress(.03, "Extracting starting frame")
        frame = extract_frame(project_path(store, pid, project.media.video.path), body.start, dest / "frame.png", 512, 320)
        result = runner.run("text_plate", {"frame": stage_to_comfy_input(frame, pid, shot.id, "frame.png"),
                            "text": " ".join(w.text for w in selected), "prompt": body.prompt}, dest / "plate_run",
                            progress=progress(ctx, "Creating lettering plate"))
        plate = result.first("plate")
        if plate is None:
            raise ValueError("Text plate workflow produced no image")
        shutil.copy2(plate, dest / "plate.png")
        # Choose the smallest valid 8k+1 length covering this interval at project fps.
        length = max(9, int(math.ceil(((body.end - body.start) * project.fps - 1) / 8)) * 8 + 1)
        result = video_runner.run("ltx_i2v", {"image": video_runner.stage_image(dest / "plate.png", pid, shot.id, "plate.png"),
                            "prompt": body.prompt, "length": length, "width": 512, "height": 320,
                            "seed": uuid.uuid4().int % (2**32), "fps": project.fps}, dest / "video_run",
                            progress=progress(ctx, "Animating with LTX", .5))
        clip = result.first("video")
        if clip is None:
            raise ValueError("LTX workflow produced no video")
        shutil.copy2(clip, dest / "clip.mp4")
        def finish(p):
            current = next(s for s in p.shots if s.id == shot.id)
            current.status, current.plate, current.video = "done", f"gen/{shot.id}/plate.png", f"gen/{shot.id}/clip.mp4"
            for word in p.words:
                if word.id in body.wordIds:
                    word.placement, word.shotId = "inworld", shot.id
        store.update(pid, finish)
        ctx.progress(1, "In-world shot ready")
        return {"shotId": shot.id, "video": f"gen/{shot.id}/clip.mp4"}
    except Exception:
        def fail(p):
            for s in p.shots:
                if s.id == shot.id:
                    s.status = "failed"
        store.update(pid, fail)
        raise


def generate_inworld_remote(store: ProjectStore, pid: str, body: InworldBody, selected: list[Word], ctx: JobContext):
    """v2 §D: frame → local Qwen/Klein edit → MiniMax H3 i2v on the remote 4090 → attach."""
    from .remote_gen import run_remote_shot
    project = store.load(pid)
    text = (body.text or " ".join(w.text for w in selected)).strip()
    reference = None
    if body.referenceImage:
        reference = project_path(store, pid, body.referenceImage)
        if not reference.is_file():
            raise ValueError(f"Reference image not found in the project: {body.referenceImage}")
    shot = GenShot(id=str(uuid.uuid4()), wordIds=body.wordIds, start=body.start, end=body.end,
                   prompt=body.prompt, status="running", workflow="remote_edit+minimax")
    store.update(pid, lambda p: p.shots.append(shot))
    dest = store.project_dir(pid) / "gen" / shot.id
    try:
        if reference is None and body.referenceTime is not None:
            from .media import extract_frame
            reference = extract_frame(project_path(store, pid, project.media.video.path), body.referenceTime,
                                      dest / "reference.png")
        out = run_remote_shot(video=project_path(store, pid, project.media.video.path), start=body.start, end=body.end,
                              fps=project.fps, width=project.width, height=project.height, text=text,
                              prompt=body.prompt, motion=body.motionPrompt, edit_model=body.editModel,
                              project_id=pid, shot_id=shot.id, dest=dest,
                              report=lambda frac, msg: ctx.progress(frac, msg), long_edge=body.longEdge,
                              reference=reference, guide_first_frame=body.guideFirstFrame)
        def finish(p):
            current = next(s for s in p.shots if s.id == shot.id)
            current.status, current.plate, current.video = "done", f"gen/{shot.id}/plate.png", f"gen/{shot.id}/clip.mp4"
            current.focus = out.get("focus")
            for word in p.words:
                if word.id in body.wordIds:
                    word.placement, word.shotId = "inworld", shot.id
        store.update(pid, finish)
        t = out["timings"]
        ctx.progress(1, f"In-world shot ready ({t.get('edit', 0):.0f}s edit + {t['video']:.0f}s MiniMax)")
        return {"shotId": shot.id, "video": f"gen/{shot.id}/clip.mp4", "plate": f"gen/{shot.id}/plate.png",
                "timings": t, "size": out["size"], "length": out["length"], "focus": out.get("focus")}
    except Exception:
        def fail(p):
            for s in p.shots:
                if s.id == shot.id:
                    s.status = "failed"
        store.update(pid, fail)
        raise
