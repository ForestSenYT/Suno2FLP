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


def replay_job_events(
    history: list[JobEvent], output_directory: Path
) -> tuple[JobStatus, list[JobStage]]:
    """Reconstruct structural progress only; never attest a worker or authorize writes."""
    if not history or history[0] != JobEvent(sequence=0, kind="created"):
        raise ValueError("Job history must begin with creation")
    status: JobStatus = "queued"
    stages = [JobStage(stage=stage) for stage in CONVERSION_STAGES]
    seen_outputs: set[str] = set()
    for sequence, event in enumerate(history[1:], 1):
        if event.sequence != sequence:
            raise ValueError("Job history sequence is not contiguous")
        active = next((stage for stage in stages if stage.status == "running"), None)
        pending = next((stage for stage in stages if stage.status != "succeeded"), None)
        if event.kind == "started":
            if status != "queued" or pending is None or pending.stage != event.stage:
                raise ValueError("Only the next queued stage may start")
            if event != JobEvent(sequence=sequence, kind="started", stage=event.stage):
                raise ValueError("Unexpected start payload")
            pending.status = "running"
            status = "running"
        elif event.kind == "progress":
            if (
                status != "running"
                or active is None
                or event.stage != active.stage
                or event.progress is None
                or event.progress < active.progress
            ):
                raise ValueError("Progress must increase on the active stage")
            if event != JobEvent(
                sequence=sequence, kind="progress", stage=event.stage, progress=event.progress
            ):
                raise ValueError("Unexpected progress payload")
            active.progress = event.progress
        elif event.kind == "finished":
            if status != "running" or active is None or event.stage != active.stage:
                raise ValueError("Only the active stage may finish")
            if event.stage == "publish":
                raise ValueError(
                    "Final publication requires independent proof; foundation cannot finish"
                )
            if not event.outputs or event != JobEvent(
                sequence=sequence, kind="finished", stage=event.stage, outputs=event.outputs
            ):
                raise ValueError("Stage completion needs output evidence and no other payload")
            for output in event.outputs:
                key = str(output.path).casefold()
                if (
                    not output.path.is_absolute()
                    or output.path == output_directory
                    or not output.path.is_relative_to(output_directory)
                    or key in seen_outputs
                ):
                    raise ValueError("Stage outputs must be unique files inside the job output")
                seen_outputs.add(key)
            active.status = "succeeded"
            active.progress = 100
            active.outputs = [output.model_copy(deep=True) for output in event.outputs]
            status = "queued"
        elif event.kind == "stopped":
            if (
                status not in ("queued", "running")
                or event.stop_status is None
                or event.code is None
                or event.stage != (active.stage if active else None)
            ):
                raise ValueError("Only an active or queued job may stop with a reason")
            if event != JobEvent(
                sequence=sequence,
                kind="stopped",
                stage=event.stage,
                stop_status=event.stop_status,
                code=event.code,
            ):
                raise ValueError("Unexpected stop payload")
            if active:
                active.status = event.stop_status
            status = event.stop_status
        elif event.kind == "resumed":
            if status not in ("blocked", "failed", "cancelled"):
                raise ValueError("Resume requires a stopped job")
            stopped = next(
                (stage for stage in stages if stage.status in ("blocked", "failed", "cancelled")),
                None,
            )
            if event.stage != (stopped.stage if stopped else None) or event != JobEvent(
                sequence=sequence, kind="resumed", stage=event.stage
            ):
                raise ValueError("Unexpected resume payload")
            if stopped:
                stopped.status = "queued"
                stopped.progress = 0
            status = "queued"
        else:
            raise ValueError("Creation is allowed only at the start of history")
    return status, stages


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
        if self.source.path.is_relative_to(self.output_directory):
            raise ValueError("Job output must be distinct from the original input tree")
        expected_status, expected_stages = replay_job_events(self.history, self.output_directory)
        if self.status != expected_status or self.stages != expected_stages:
            raise ValueError("Job snapshot must match its recorded transition history")
        return self
