"""Conversion progress contracts; state snapshots never grant writer permission."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity

JobStatus = Literal["queued", "running", "blocked", "failed", "cancelled", "succeeded"]
StageStatus = JobStatus
ConversionStage = Literal[
    "input",
    "decode",
    "separate",
    "analyze",
    "transcribe",
    "arrange",
    "route",
    "write",
    "host_verify",
    "quality",
    "publish",
]
CONVERSION_STAGES: tuple[ConversionStage, ...] = (
    "input",
    "decode",
    "separate",
    "analyze",
    "transcribe",
    "arrange",
    "route",
    "write",
    "host_verify",
    "quality",
    "publish",
)
StopStatus = Literal["blocked", "failed", "cancelled"]


class JobStage(Contract):
    stage: ConversionStage
    status: StageStatus = "queued"
    progress: int = Field(default=0, ge=0, le=100, strict=True)
    outputs: list[FileIdentity] = Field(default_factory=list)


class JobEvent(Contract):
    sequence: int = Field(ge=0, strict=True)
    kind: Literal["created", "started", "progress", "finished", "stopped", "resumed"]
    stage: ConversionStage | None = None
    progress: int | None = Field(default=None, ge=0, le=99, strict=True)
    outputs: list[FileIdentity] = Field(default_factory=list)
    stop_status: StopStatus | None = None
    code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True)


class ConversionJob(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["audio-job-foundation-v1"] = "audio-job-foundation-v1"
    job_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$", strict=True)
    source: FileIdentity
    output_directory: Path
    status: JobStatus
    stages: list[JobStage]
    history: list[JobEvent]
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def coherent_snapshot(self) -> Self:
        if not self.source.path.is_absolute() or not self.output_directory.is_absolute():
            raise ValueError("Job source and output paths must be absolute")
        initial = [JobStage(stage=stage) for stage in CONVERSION_STAGES]
        if (
            self.status != "queued"
            or self.stages != initial
            or self.history != [JobEvent(sequence=0, kind="created")]
        ):
            raise ValueError("Job snapshot must match its recorded transition history")
        return self
