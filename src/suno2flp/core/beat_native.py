"""Complete native array observations; declarations alone grant no qualification."""

import math
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.beat_runtime import BeatBackend, BeatExecution, Digest
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity


class NativeBeatArray(Contract):
    shape: list[int] = Field(min_length=1, max_length=2)
    encoding: Literal["<f4", "<f8"]
    size_bytes: int = Field(ge=0, le=512 * 1024**2, strict=True)
    sha256: Digest

    @model_validator(mode="after")
    def complete_shape(self) -> Self:
        if any(type(v) is not int or not 0 <= v <= 115200000 for v in self.shape):
            raise ValueError("Invalid complete native array shape")
        if self.size_bytes != math.prod(self.shape) * (4 if self.encoding == "<f4" else 8):
            raise ValueError("Native bytes disagree with complete array shape")
        return self


class NativeBeatResult(Contract):
    execution: BeatExecution
    frames: int = Field(gt=0, le=115200000, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: Literal[1, 2]
    chunk_starts: list[int] = Field(min_length=1, max_length=22)
    files: dict[str, NativeBeatArray] = Field(min_length=11, max_length=74)
    source_peak: float = Field(ge=0, le=1, allow_inf_nan=False)
    mono_peak: float = Field(ge=0, le=1, allow_inf_nan=False)
    inference_seconds: float = Field(gt=0, allow_inf_nan=False)
    worker_seconds: float = Field(gt=0, allow_inf_nan=False)
    peak_working_set: int = Field(gt=0, le=16 * 1024**3, strict=True)
    peak_commit: int = Field(gt=0, le=16 * 1024**3, strict=True)


class BeatFixtureEvidence(Contract):
    fixture: str
    source: FileIdentity
    attempts: list[Path] = Field(min_length=2, max_length=2)
    results: list[NativeBeatResult] = Field(min_length=2, max_length=2)
    witnesses: list[FileIdentity]
    repeatability: Literal["observed-two-runs"] = "observed-two-runs"


class BeatProbe(Contract):
    profile: Literal["beat-this-local-runtime-evidence-v1"] = "beat-this-local-runtime-evidence-v1"
    backend_record: FileIdentity
    backend: BeatBackend
    fixtures: list[BeatFixtureEvidence] = Field(min_length=4, max_length=4)
    model_qualification: Literal["not_assessed"] = "not_assessed"
    music_quality: Literal["not_assessed"] = "not_assessed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
