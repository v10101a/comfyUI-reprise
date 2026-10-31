"""Analysis/generation job orchestration. Node ids belong exclusively to workflow sidecars."""
from __future__ import annotations

import json
import math
import shutil
import uuid
from pathlib import Path

from .comfy import runner, read_json_output, generation_runner
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
    ctx.progress(.05, "Extracting speech audio")
    wav = extract_audio_wav(project_path(store, pid, source.path), pdir / "analysis" / f"speech_{ctx.id}.wav")
    audio = stage_to_comfy_input(wav, pid, wav.name)
    result = runner.run("words", {"audio": audio, "lyrics": project.media.lyrics or "", "language": language},
                        pdir / "analysis" / ctx.id, progress=progress(ctx, "Transcribing"))
    data = read_json_output(result.outputs["words_json"])
    words = timeline_words(data, project.duration)
    write_json_atomic(pdir / "analysis" / "words.json", data)
    def update(p):
        current_source = p.media.audio or p.media.video
        if current_source is None or current_source.path != source.path:
            raise ValueError("Source media changed during transcription; run analysis again")
        p.analysis.words = "analysis/words.json"
        p.words = words
    store.update(pid, update)
    ctx.progress(1, f"Transcribed {len(words)} words")
    return {"words": len(words), "path": "analysis/words.json"}


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
    video = stage_to_comfy_input(prepared, pid, prepared.name)
    result = runner.run("matte", {"video": video, "fps": project.fps}, pdir / "analysis" / ctx.id,
                        progress=progress(ctx, "Extracting foreground"))
    frames = result.outputs["fg_png"]
    matte = pdir / "analysis" / f"matte_{ctx.id}"
    matte.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    for i, src in enumerate(frames, 1):
        with Image.open(src) as im:
            # The browser and export must agree with project dimensions, even if a node resized its batch.
            im.convert("RGBA").resize((project.width, project.height)).save(matte / f"fg_{i:05d}.png")
    if not frames:
        raise ValueError("Matte workflow returned no foreground frames")
    tracks = read_json_output(result.outputs["tracks_json"])
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
    ctx.progress(1, f"Foreground ready: {len(frames)} frames")
    return {"frames": len(frames), "matte": f"analysis/{matte.name}/", "tracks": tracks_rel, "occupancy": occ_rel}


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
            current.focus = out.get("focus")
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
