"""Complete encoder observations; native declarations alone never qualify music."""

import math
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.drum_clock import drum_output_rows
from suno2flp.core.drum_runtime import Digest, DrumBackend, DrumTensor
from suno2flp.core.drum_scoring import DRUM_CLASSES, DrumClass
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity


class NativeDrumArray(Contract):
    shape: list[Annotated[int, Field(strict=True)]] = Field(min_length=1, max_length=2)
    encoding: Literal["<f4"] = "<f4"
    size_bytes: int = Field(ge=0, le=256 * 1024**2, strict=True)
    sha256: Digest

    @model_validator(mode="after")
    def complete_geometry(self) -> Self:
        if any(type(v) is not int or not 1 <= v <= 26460000 for v in self.shape):
            raise ValueError("Invalid complete drum array shape")
        if self.size_bytes != math.prod(self.shape) * 4:
            raise ValueError("Drum array bytes disagree with full float32 shape")
        return self


class DrumExecution(Contract):
    profile: Literal["idm-encoder-only-fixed-cpu-v1"] = "idm-encoder-only-fixed-cpu-v1"
    intra_op_threads: Literal[8]
    inter_op_threads: Literal[1]
    deterministic_algorithms: Literal[True]
    mkldnn: Literal[False]
    cuda: None
    matmul_precision: Literal["highest"]
    checkpoint_sha256: Literal["5856a9bee7c6d503842795756d238dc8470f6f3e010e9e4f33ede0362850cb4c"]
    geometry: dict[str, DrumTensor] = Field(min_length=330, max_length=330)
    versions: dict[str, str]
    modules: dict[str, Path]
    time_convolutions: list[list[int]]


class NativeDrumResult(Contract):
    profile: Literal["complete-idm-encoder-output-v1"] = "complete-idm-encoder-output-v1"
    execution: DrumExecution
    model_frames: int = Field(ge=513, le=26460000, strict=True)
    sample_rate: Literal[44100] = 44100
    channels: Literal[2] = 2
    rows: int = Field(ge=16, le=103373, strict=True)
    classes: list[DrumClass]
    source_sha256: Digest
    files: dict[str, NativeDrumArray]
    source_peak: float = Field(ge=0, allow_inf_nan=False)
    mono_peak: float = Field(ge=0, allow_inf_nan=False)
    inference_seconds: float = Field(gt=0, allow_inf_nan=False)
    worker_seconds: float = Field(gt=0, allow_inf_nan=False)
    peak_working_set: int = Field(gt=0, le=16 * 1024**3, strict=True)
    peak_commit: int = Field(gt=0, le=16 * 1024**3, strict=True)

    @model_validator(mode="after")
    def full_native_geometry(self) -> Self:
        expected = {
            "mono.f32": [self.model_frames],
            "onsets.f32": [9, self.rows],
            "velocities.f32": [9, self.rows],
        }
        if (
            self.rows != drum_output_rows(self.model_frames)
            or self.classes != list(DRUM_CLASSES)
            or {name: value.shape for name, value in self.files.items()} != expected
            or self.execution.time_convolutions != [[7, 3, 1, 1], *[[3, 3, 1, 1]] * 3]
        ):
            raise ValueError("Complete drum row/class/array/convolution geometry changed")
        return self


DrumFixtureName = Literal["signed-pair-1025", "stereo-tone-tail-44117"]


class DrumFixtureEvidence(Contract):
    fixture: DrumFixtureName
    source: FileIdentity
    model_frames: int = Field(ge=513, le=26460000, strict=True)
    attempts: list[Path] = Field(min_length=2, max_length=2)
    results: list[NativeDrumResult] = Field(min_length=2, max_length=2)
    witnesses: list[FileIdentity]
    repeatability: Literal["observed-two-runs"] = "observed-two-runs"


class DrumProbe(Contract):
    profile: Literal["selected-drum-encoder-runtime-evidence-v1"] = (
        "selected-drum-encoder-runtime-evidence-v1"
    )
    root: Path
    backend_record: FileIdentity
    backend: DrumBackend
    fixtures: list[DrumFixtureEvidence] = Field(min_length=2, max_length=2)
    model_qualification: Literal["not_assessed"] = "not_assessed"
    musical_quality: Literal["not_assessed"] = "not_assessed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
