"""Inferred audio candidates and a fixed private native model recipe, never source MIDI."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.transcription_clock import (
    MODEL_RATE,
    owned_prediction_rows,
    plan_prediction_windows,
    resampled_frame_count,
)


class ModelArtifactPin(Contract):
    distribution: str
    version: str
    filename: str
    url: str
    size_bytes: int = Field(gt=0, le=256 * 1024**2, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str
    notices: dict[str, str]
    source_inventory: list[str] | None = None
    selected_members: dict[str, str] | None = None
    omitted_members: dict[str, str] = Field(default_factory=dict)


class SupplementalNotice(Contract):
    filename: str
    url: str
    size_bytes: int = Field(gt=0, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target: str


class BasicPitchPins(Contract):
    profile: Literal["basic-pitch-onnx-cpu-windows-cp311-v1"]
    python_version: Literal["3.11.16"]
    basic_pitch_commit: Literal["9991303bba609a3b93089d13ec80d1d495083596"]
    model_path: Literal["basic_pitch/saved_models/icassp_2022/nmp.onnx"]
    model_sha256: str
    source_correspondence: dict[str, str]
    artifacts: list[ModelArtifactPin] = Field(min_length=42, max_length=42)
    supplemental_notice: SupplementalNotice


class BasicPitchBackend(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["basic-pitch-onnx-cpu-windows-cp311-v1"] = (
        "basic-pitch-onnx-cpu-windows-cp311-v1"
    )
    root: Path
    python: FileIdentity
    runtime: list[FileIdentity]
    artifacts: list[FileIdentity]
    adapters: list[FileIdentity]
    payload: dict[str, str]
    curated_install: Literal["no-tensorflow-no-build-no-soundfont"] = (
        "no-tensorflow-no-build-no-soundfont"
    )
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"


class BasicPitchProbe(Contract):
    profile: Literal["basic-pitch-native-probe-v1"]
    provider: Literal["CPUExecutionProvider"]
    intra_op_threads: Literal[8]
    inter_op_threads: Literal[1]
    sequential: Literal[True]
    repeatable: Literal[True]
    shapes: dict[str, list[int]]
    versions: dict[str, str]
    modules: dict[str, Path]


class RawPredictionArtifact(Contract):
    kind: Literal["note", "onset", "contour"]
    windows: int = Field(ge=1, le=366, strict=True)
    file: FileIdentity
    encoding: Literal["little-endian-float32-window-row-bin"] = (
        "little-endian-float32-window-row-bin"
    )

    @property
    def width(self) -> int:
        return 264 if self.kind == "contour" else 88

    @model_validator(mode="after")
    def complete_size(self) -> Self:
        if self.file.size_bytes != self.windows * 172 * self.width * 4:
            raise ValueError("Raw artifact size disagrees with full window dimensions")
        return self


class InferredFrameNote(Contract):
    start_frame: int = Field(ge=0, le=52000, strict=True)
    end_frame: int = Field(gt=0, le=52000, strict=True)
    pitch: int = Field(ge=21, le=108, strict=True)
    activation: float = Field(ge=0, le=1, allow_inf_nan=False, strict=True)
    bend_offset: int = Field(ge=0, le=64 * 1024**2, strict=True)
    model_activation_is_confidence: Literal[False] = False

    @property
    def bend_count(self) -> int:
        return self.end_frame - self.start_frame

    @model_validator(mode="after")
    def positive_duration(self) -> Self:
        if self.end_frame <= self.start_frame:
            raise ValueError("Estimated note must have positive frame duration")
        return self


class NativeTranscriptionResult(Contract):
    profile: Literal["basic-pitch-frame-estimates-v1"] = "basic-pitch-frame-estimates-v1"
    probe: BasicPitchProbe
    resampled_frames: int = Field(gt=0, le=MODEL_RATE * 600, strict=True)
    windows: int = Field(gt=0, le=366, strict=True)
    owned_rows: int = Field(gt=0, le=52000, strict=True)
    notes: list[InferredFrameNote] = Field(max_length=10000)
    bend_bytes: int = Field(ge=0, le=64 * 1024**2, strict=True)

    @model_validator(mode="after")
    def complete_geometry(self) -> Self:
        rows = owned_prediction_rows(self.resampled_frames)
        if self.windows != len(
            plan_prediction_windows(self.resampled_frames)
        ) or self.owned_rows != len(rows):
            raise ValueError("Native geometry disagrees with complete source window ownership")
        bend_offset = 0
        for note in self.notes:
            if note.end_frame > len(rows) or note.bend_offset != bend_offset:
                raise ValueError("Native note/bend address is outside complete frame evidence")
            bend_offset += note.bend_count
        if bend_offset != self.bend_bytes:
            raise ValueError("Bend artifact must retain every per-note frame, including overlaps")
        return self


class PitchCandidate(Contract):
    """Source-neutral complete pitch inference evidence; never qualification."""

    schema_version: Literal[1] = 1
    origin: Literal["inferred_candidate"] = "inferred_candidate"
    pcm: FileIdentity
    frames: int = Field(gt=0, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: int = Field(ge=1, le=2, strict=True)
    backend_record: FileIdentity
    backend: BasicPitchBackend
    model_dependencies: list[FileIdentity]
    recipe: ScoringRecipe
    result: NativeTranscriptionResult
    mono: FileIdentity
    predictions: list[RawPredictionArtifact] = Field(min_length=3, max_length=3)
    bends: FileIdentity
    native_result: FileIdentity
    native_request: FileIdentity
    stdout: FileIdentity
    stderr: FileIdentity
    clock_profile: Literal["owned-window-source-anchors-v1"] = "owned-window-source-anchors-v1"
    downmix: Literal["float64-channel-mean-then-float32"] = "float64-channel-mean-then-float32"
    resampling: Literal["scipy-resample-poly-kaiser5-constant-zero-v1"] = (
        "scipy-resample-poly-kaiser5-constant-zero-v1"
    )
    postprocessing: Literal["bp0.4-onset0.5-frame0.3-min11-energy11-infer-melodia-bends25"] = (
        "bp0.4-onset0.5-frame0.3-min11-energy11-infer-melodia-bends25"
    )
    tempo: Literal["not_estimated"] = "not_estimated"
    instrument_roles: Literal["not_estimated"] = "not_estimated"
    ground_truth_metrics: Literal["unavailable"] = "unavailable"
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    human_review: Literal["not_performed"] = "not_performed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def source_geometry(self) -> Self:
        if self.result.resampled_frames != resampled_frame_count(self.frames, self.sample_rate):
            raise ValueError("Native resampling disagrees with original source clock")
        if self.mono.size_bytes != self.result.resampled_frames * 4:
            raise ValueError("Mono waveform does not cover the complete derived source")
        if (
            {p.kind for p in self.predictions} != {"note", "onset", "contour"}
            or any(p.windows != self.result.windows for p in self.predictions)
            or self.bends.size_bytes != self.result.bend_bytes
        ):
            raise ValueError("Prediction/bend evidence does not cover native output")
        return self

    def pitch_witnesses(self) -> list[FileIdentity]:
        return [
            self.pcm,
            self.backend_record,
            self.backend.python,
            *self.backend.runtime,
            *self.backend.artifacts,
            *self.backend.adapters,
            *self.model_dependencies,
            self.recipe.python_executable,
            *self.recipe.files,
            self.mono,
            *[p.file for p in self.predictions],
            self.bends,
            self.native_result,
            self.native_request,
            self.stdout,
            self.stderr,
        ]


class TranscriptionCandidate(PitchCandidate):
    """Original-audio v1 semantics remain distinct from estimated stem sources."""

    profile: Literal["source-bound-basic-pitch-candidate-v1"] = (
        "source-bound-basic-pitch-candidate-v1"
    )
    decode_report: FileIdentity
    source_audio: FileIdentity
    decode_dependencies: list[FileIdentity]
    decoder_payload_root: Path | None

    def witnesses(self) -> list[FileIdentity]:
        return [
            self.decode_report,
            self.source_audio,
            *self.decode_dependencies,
            *self.pitch_witnesses(),
        ]
