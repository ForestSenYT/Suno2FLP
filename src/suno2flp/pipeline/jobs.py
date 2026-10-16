"""Copy-on-transition job state; no worker launch, filesystem write or publication."""

from pathlib import Path

from suno2flp.core.jobs import (
    CONVERSION_STAGES,
    ConversionJob,
    ConversionStage,
    JobEvent,
    JobStage,
    StopStatus,
    replay_job_events,
)
from suno2flp.core.offline_files import guarded_path, verify_inputs
from suno2flp.core.offline_models import FileIdentity


def _checked(job: ConversionJob) -> ConversionJob:
    return ConversionJob.model_validate(job.model_dump())


def _append(job: ConversionJob, event: JobEvent) -> ConversionJob:
    history = [*job.history, event.model_copy(deep=True)]
    status, stages = replay_job_events(history, job.output_directory, job.source)
    data = job.model_dump()
    data.update(status=status, stages=stages, history=history)
    return ConversionJob.model_validate(data).model_copy(deep=True)


def _verify_evidence(job: ConversionJob) -> None:
    verify_inputs([job.source, *(output for stage in job.stages for output in stage.outputs)])


def new_job(job_id: str, source: FileIdentity, output_directory: Path) -> ConversionJob:
    destination = guarded_path(output_directory)
    if destination.exists() or source.path.is_relative_to(destination):
        raise ValueError("Use a new job output directory distinct from original inputs")
    verify_inputs([source])
    return ConversionJob(
        job_id=job_id,
        source=source.model_copy(deep=True),
        output_directory=destination,
        status="queued",
        stages=[JobStage(stage=stage) for stage in CONVERSION_STAGES],
        history=[JobEvent(sequence=0, kind="created", source=source.model_copy(deep=True))],
    )


def start_stage(job: ConversionJob, stage: ConversionStage) -> ConversionJob:
    current = _checked(job)
    updated = _append(current, JobEvent(sequence=len(current.history), kind="started", stage=stage))
    _verify_evidence(updated)
    return updated


def report_progress(job: ConversionJob, stage: ConversionStage, progress: int) -> ConversionJob:
    current = _checked(job)
    return _append(
        current,
        JobEvent(sequence=len(current.history), kind="progress", stage=stage, progress=progress),
    )


def finish_stage(
    job: ConversionJob, stage: ConversionStage, outputs: list[FileIdentity]
) -> ConversionJob:
    current = _checked(job)
    updated = _append(
        current,
        JobEvent(sequence=len(current.history), kind="finished", stage=stage, outputs=outputs),
    )
    _verify_evidence(updated)
    return updated


def stop_job(job: ConversionJob, status: StopStatus, code: str) -> ConversionJob:
    current = _checked(job)
    active = next((stage for stage in current.stages if stage.status == "running"), None)
    return _append(
        current,
        JobEvent(
            sequence=len(current.history),
            kind="stopped",
            stage=active.stage if active else None,
            stop_status=status,
            code=code,
        ),
    )


def resume_job(job: ConversionJob) -> ConversionJob:
    current = _checked(job)
    stopped = next(
        (stage for stage in current.stages if stage.status in ("blocked", "failed", "cancelled")),
        None,
    )
    updated = _append(
        current,
        JobEvent(
            sequence=len(current.history), kind="resumed", stage=stopped.stage if stopped else None
        ),
    )
    _verify_evidence(updated)
    return updated
