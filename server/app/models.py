"""Pydantic models mirroring docs/SCHEMA.md §1 (Project) and §4 (Job).

JSON keys are camelCase exactly as in SCHEMA.md; attribute names match the keys.
Every model allows extra fields so the web app can round-trip data we do not know about.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Base(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, allow_inf_nan=False)


# ---- §1 Project ----------------------------------------------------------------

class MediaRef(Base):
    path: str
    duration: float
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    hasAudio: Optional[bool] = None


class TextStyle(Base):
    fontFamily: str = "Inter"
    fontWeight: int = 700
    fontSize: float = 0.08
    fill: str = "#ffffff"
    stroke: Optional[str] = None
    strokeWidth: Optional[float] = None
    letterSpacing: Optional[float] = None
    align: Literal["left", "center", "right"] = "center"


Placement = Literal["overlay", "behind", "anchor", "inworld", "surface"]
Preset = Literal["pop", "karaoke", "typewriter", "hud", "none"]


class Position(Base):
    x: float
    y: float


class Anchor(Base):
    trackId: str
    dx: float = 0.0
    dy: float = 0.0


class Word(Base):
    id: str
    text: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    lineId: str
    placement: Placement = "overlay"
    preset: Preset = "pop"
    position: Optional[Position] = None
    anchor: Optional[Anchor] = None
    style: Optional[dict[str, Any]] = None  # Partial<TextStyle>
    shotId: Optional[str] = None

    @model_validator(mode="after")
    def time_range(self):
        if self.end <= self.start:
            raise ValueError("Word end must be greater than start")
        return self


ShotStatus = Literal["pending", "running", "done", "failed"]
ShotWorkflow = Literal["text_plate+ltx_i2v", "ltx_morph", "remote_edit+minimax"]


class GenShot(Base):
    id: str
    wordIds: list[str] = Field(default_factory=list)
    start: float
    end: float
    prompt: str = ""
    plate: Optional[str] = None
    video: Optional[str] = None
    status: ShotStatus = "pending"
    workflow: ShotWorkflow = "text_plate+ltx_i2v"
    # Source-normalized [x0, y0, x1, y1] of the generated word in this shot; reframe keeps it in the crop.
    focus: Optional[tuple[float, float, float, float]] = None


class Media(Base):
    video: Optional[MediaRef] = None
    audio: Optional[MediaRef] = None
    lyrics: Optional[str] = None


class Analysis(Base):
    words: Optional[str] = None
    matte: Optional[str] = None
    tracks: Optional[str] = None
    depth: Optional[str] = None
    occupancy: Optional[str] = None      # v2 §B: "analysis/occupancy.json"
    beats: Optional[str] = None          # "analysis/beats.json" (TypesetBeatGrid)
    flow: Optional[str] = None           # "analysis/flow.json" (TypesetFlowField): motion field for the type
    voice: Optional[str] = None          # "analysis/voice.json" (TypesetVoiceField): loudness/pitch per frame


SurfaceStatus = Literal["drawn", "tracking", "tracked", "failed"]


class Surface(Base):
    """v2 §A: a quad drawn on a plane in the footage (normalized corners TL, TR, BR, BL at keyFrame)."""
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    label: Optional[str] = None
    keyFrame: int = Field(default=0, ge=0)
    corners: list[tuple[float, float]] = Field(min_length=4, max_length=4)
    track: Optional[str] = None
    status: Optional[SurfaceStatus] = None


Aspect = Literal["16:9", "9:16", "1:1", "4:5"]


class FrameSource(Base):
    projectId: str


class Frame(Base):
    """v2 §C: reframed project — crop path is source-normalized per frame."""
    aspect: Aspect
    source: Optional[FrameSource] = None
    crop: Optional[str] = None


class Project(Base):
    version: Literal[1] = 1
    id: str
    name: str
    fps: float = Field(default=24, ge=1, le=120)
    width: int = Field(default=1920, ge=2, le=4096, multiple_of=2)
    height: int = Field(default=1080, ge=2, le=4096, multiple_of=2)
    duration: float = Field(default=0.0, ge=0)
    media: Media = Field(default_factory=Media)
    analysis: Analysis = Field(default_factory=Analysis)
    style: TextStyle = Field(default_factory=TextStyle)
    words: list[Word] = Field(default_factory=list)
    shots: list[GenShot] = Field(default_factory=list)
    surfaces: Optional[list[Surface]] = None
    frame: Optional[Frame] = None


# ---- §4 Job ----------------------------------------------------------------------

JobKind = Literal["words", "matte", "inworld", "export", "surface", "reframe", "occupancy", "beats", "flow", "voice"]
JobStatus = Literal["queued", "running", "done", "failed"]


class Job(Base):
    id: str
    kind: JobKind
    status: JobStatus = "queued"
    progress: Optional[float] = None
    message: Optional[str] = None
    result: Optional[Any] = None
    projectId: str
    # Not in SCHEMA (harmless extras): timestamps for the UI's job list.
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


# ---- request bodies (§4) --------------------------------------------------------------

class CreateProjectBody(Base):
    name: str = Field(default="Untitled", max_length=200)


class AnalyzeWordsBody(Base):
    language: Optional[str] = None


class AnalyzeMatteBody(Base):
    pass


class InworldBody(Base):
    wordIds: list[str] = Field(default_factory=list)
    prompt: str = ""
    start: float
    end: float
    engine: Literal["local-ltx", "remote-minimax"] = "local-ltx"
    editModel: Literal["qwen", "klein", "none"] = "qwen"
    text: Optional[str] = None           # word(s) to write; default = selected words joined
    motionPrompt: Optional[str] = None   # remote-minimax: camera/subject motion for the i2v prompt
    # remote-minimax only. Generation size: long edge in px (default TYPESET_MINIMAX_LONG_EDGE = 736);
    # 1344 gives 1344×768 for 16:9, the size of the hero shots. The local edit stays ≤ 1024.
    longEdge: Optional[int] = Field(default=None, ge=256, le=1344)
    # Identity reference (MiniMaxH3ReferenceToVideo): a project-relative image path, or a time in the
    # project video to take the reference frame from. The prompt calls it <Picture 1>.
    referenceImage: Optional[str] = None
    referenceTime: Optional[float] = Field(default=None, ge=0)
    # With a reference: also anchor the (edited) first frame at frame 0 (continuity with the footage).
    # False = pure reference-to-video, like the hero's same-face plates.
    guideFirstFrame: bool = True


FocusMode = Literal["auto", "pan"]


class ReframeFocus(Base):
    """A region the reframe crop must contain from `start` to `end` (seconds), e.g. a generated word.
    auto: follow the subject but keep the box in frame; zoom out (letterboxed) if the box is bigger than
    the crop. pan: keep the full-height crop and scan across the box."""
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    box: tuple[float, float, float, float]
    mode: FocusMode = "auto"
    label: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def valid(self):
        if self.end <= self.start:
            raise ValueError("focus end must be greater than start")
        x0, y0, x1, y1 = self.box
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("focus box must be [x0, y0, x1, y1] inside [0, 1] with x0 < x1, y0 < y1")
        return self


class ReframeBody(Base):
    aspect: Aspect
    name: Optional[str] = Field(default=None, max_length=200)
    # Explicit focus ranges; generated shots with a `focus` box are added automatically.
    focus: list[ReframeFocus] = Field(default_factory=list)


class TrackSurfaceBody(Base):
    pass


ExportLayer = Literal["text", "composite"]
ExportFormat = Literal["mp4", "mov", "webm"]


class ExportBody(Base):
    layer: ExportLayer = "text"
    formats: list[ExportFormat] = Field(default_factory=lambda: ["mp4", "mov", "webm"])
    # Frames the studio rendered itself (browser capture, no Playwright): a session from POST .../export/frames.
    frames: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{12}$")
