"""Inert, unqualified YourMT3+ observations in the original audio clock."""

from fractions import Fraction
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.transcription import ModelArtifactPin

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MODEL_RATE = 16_000
WINDOW_FRAMES = 32_767


class FrameInterval(Contract):
    start_frame: int = Field(ge=0, strict=True)
    end_frame: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def positive(self) -> Self:
        if self.start_frame >= self.end_frame:
            raise ValueError("Interval end must follow start")
        return self


class YourMT3Window(Contract):
    index: int = Field(ge=0, le=292, strict=True)
    start_frame: int = Field(ge=0, strict=True)
    valid_frames: int = Field(gt=0, le=WINDOW_FRAMES, strict=True)

    @property
    def padding_frames(self) -> int:
        return WINDOW_FRAMES - self.valid_frames

    @model_validator(mode="after")
    def continuous(self) -> Self:
        if self.start_frame != self.index * WINDOW_FRAMES:
            raise ValueError("Window origin must follow the continuous model clock")
        return self


def plan_yourmt3_windows(frames: int, sample_rate: int) -> list[YourMT3Window]:
    if (
        type(frames) is not int
        or type(sample_rate) is not int
        or not 8000 <= sample_rate <= 192000
        or not 0 < frames <= sample_rate * 600
    ):
        raise ValueError("Expected an integer original audio clock of at most600 seconds")
    count = (frames * MODEL_RATE + sample_rate - 1) // sample_rate
    return [
        YourMT3Window(index=i, start_frame=start, valid_frames=min(WINDOW_FRAMES, count - start))
        for i, start in enumerate(range(0, count, WINDOW_FRAMES))
    ]


def validate_yourmt3_intervals(intervals: list[FrameInterval], frames: int) -> None:
    previous = 0
    if not 1 <= len(intervals) <= 40:
        raise ValueError("Expected1–40 explicit observation intervals")
    for item in intervals:
        interval = FrameInterval.model_validate(item.model_dump())
        if interval.start_frame < previous or interval.end_frame > frames:
            raise ValueError("Observation intervals must be ordered, disjoint and within source")
        previous = interval.end_frame


class YourMT3Note(Contract):
    is_drum: bool = Field(strict=True)
    program: int = Field(ge=0, le=129, strict=True)
    pitch: int = Field(ge=0, le=127, strict=True)
    onset: float = Field(ge=0, le=604, allow_inf_nan=False, strict=True)
    offset: float = Field(gt=0, le=604, allow_inf_nan=False, strict=True)
    velocity: int = Field(ge=0, le=127, strict=True)

    @model_validator(mode="after")
    def duration(self) -> Self:
        if self.offset <= self.onset or self.is_drum != (self.program == 128):
            raise ValueError("Invalid native note duration or drum label")
        return self


class YourMT3IntervalSummary(Contract):
    interval: FrameInterval
    onsets: int = Field(ge=0, strict=True)
    overlapping_notes: int = Field(ge=0, strict=True)
    programs: dict[int, int]
    pitches: dict[int, int]
    ground_truth_metrics: Literal["reference_unavailable"] = "reference_unavailable"
    musical_correctness: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"


def summarize_yourmt3(
    notes: list[YourMT3Note], intervals: list[FrameInterval], sample_rate: int
) -> list[YourMT3IntervalSummary]:
    result = []
    for interval in intervals:
        start = Fraction(interval.start_frame, sample_rate)
        end = Fraction(interval.end_frame, sample_rate)
        overlap = [n for n in notes if Fraction(n.onset) < end and Fraction(n.offset) > start]
        programs: dict[int, int] = {}
        pitches: dict[int, int] = {}
        for note in overlap:
            programs[note.program] = programs.get(note.program, 0) + 1
            pitches[note.pitch] = pitches.get(note.pitch, 0) + 1
        result.append(
            YourMT3IntervalSummary(
                interval=interval,
                onsets=sum(start <= Fraction(n.onset) < end for n in overlap),
                overlapping_notes=len(overlap),
                programs=programs,
                pitches=pitches,
            )
        )
    return result


class YourMT3FilePin(Contract):
    filename: str
    target: str
    url: str
    size_bytes: int = Field(gt=0, le=512 * 1024**2, strict=True)
    sha256: Digest
    license: str


class YourMT3Tensor(Contract):
    shape: list[Annotated[int, Field(ge=0, strict=True)]]
    dtype: Literal["torch.float32", "torch.int64"]


class YourMT3Pins(Contract):
    profile: Literal["yourmt3-single-cpu-windows-cp311-v1"]
    python_version: Literal["3.11.16"]
    source_revision: Literal["5e66c1ea173a8186e0d20432b841d3180cc015b5"]
    weights_revision: Literal["e45ebd70398682d54b7bb1901a5216e18f3b1824"]
    wheels: list[ModelArtifactPin] = Field(min_length=59, max_length=59)
    files: list[YourMT3FilePin]
    state: dict[str, YourMT3Tensor] = Field(min_length=386, max_length=386)
    configuration: dict[str, object]
    unsafe_globals: list[str]


class YourMT3Backend(Contract):
    profile: Literal["yourmt3-single-cpu-windows-cp311-v1"] = "yourmt3-single-cpu-windows-cp311-v1"
    root: Path
    python: FileIdentity
    runtime: list[FileIdentity]
    artifacts: list[FileIdentity]
    adapters: list[FileIdentity]
    payload: dict[str, Digest]
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"


class YourMT3Candidate(Contract):
    profile: Literal["yourmt3-unqualified-continuous-song-v1"] = (
        "yourmt3-unqualified-continuous-song-v1"
    )
    root: Path
    backend: FileIdentity
    decode_report: FileIdentity
    source_audio: FileIdentity
    pcm: FileIdentity
    frames: int = Field(gt=0, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: Literal[1, 2]
    intervals: list[FrameInterval]
    raw: FileIdentity
    request: FileIdentity
    diagnostics: list[FileIdentity] = Field(min_length=2, max_length=2)
    summaries: list[YourMT3IntervalSummary]
    musical_correctness: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"

    @model_validator(mode="after")
    def clock(self) -> Self:
        plan_yourmt3_windows(self.frames, self.sample_rate)
        validate_yourmt3_intervals(self.intervals, self.frames)
        return self
