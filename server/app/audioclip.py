"""Song clip (media.audioClip, docs/SCHEMA.md): play song [in, out) from project time `offset`.

Non-destructive: the media file is untouched; exports trim + delay it in the ffmpeg filter graph,
and the words job maps song-time results into project time."""
from __future__ import annotations


def clip_of(project) -> dict | None:
    """{in, out, offset} (seconds) or None when the whole song plays from 0."""
    c = getattr(project.media, "audioClip", None)
    if c is None:
        return None
    c = c if isinstance(c, dict) else c.model_dump()
    src = project.media.audio or project.media.video
    dur = float(src.duration) if src and src.duration else float("inf")
    i = max(0.0, float(c.get("in") or 0))
    o = min(dur, float(c.get("out") if c.get("out") is not None else dur))
    if o <= i:
        return None
    return {"in": i, "out": o, "offset": float(c.get("offset") or 0)}


def clip_filters(project) -> list[str]:
    """ffmpeg audio filters that place the clip on the project timeline (prepend to apad etc.)."""
    c = clip_of(project)
    if not c:
        return []
    i, o, off = c["in"], c["out"], c["offset"]
    if off < 0:  # the head plays before 0: cut it
        i, off = i - off, 0.0
    if i >= o:
        return ["volume=0"]
    # Lead-in silence: move the timestamps, then let aresample fill the gap with real samples
    # (adelay only shifts timestamps here, which the AAC/MP4 path drops: the song started early).
    return [f"atrim=start={i:.4f}:end={o:.4f}", f"asetpts=PTS-STARTPTS+{off:.4f}/TB", "aresample=async=1:first_pts=0"]


def song_words_to_project(data: dict, project) -> dict:
    """Word timings from the song file → project time; words outside the clip are dropped."""
    c = clip_of(project)
    if not c:
        return data
    shift = c["offset"] - c["in"]
    words = []
    for w in data.get("words", []):
        s, e = float(w["start"]), float(w["end"])
        if s < c["in"] or s >= c["out"]:
            continue
        words.append({**w, "start": s + shift, "end": min(e, c["out"]) + shift})
    return {**data, "words": words}
