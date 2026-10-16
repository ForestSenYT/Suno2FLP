"""Shared synchronous application service for real preflight and durable job state."""

import os
from pathlib import Path

from suno2flp.core.audio_input import MAX_AUDIO_BYTES, AudioPreflightError, AudioPreflightReport
from suno2flp.core.errors import OfflineError
from suno2flp.core.job_store import StoredJob
from suno2flp.core.offline_files import (
    capture_input,
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.importer.audio import inspect_audio
from suno2flp.pipeline.job_store import latest_job, load_job, save_job
from suno2flp.pipeline.jobs import finish_stage, new_job, resume_job, start_stage, stop_job


def create_audio_job(source: Path, output_directory: Path, job_id: str) -> StoredJob:
    path = guarded_path(source)
    if path.stat().st_size > MAX_AUDIO_BYTES:
        raise AudioPreflightError("audio_limits_exceeded", "Input exceeds 1 GiB", blocked=True)
    job = new_job(job_id, capture_stream_input(path), output_directory)
    root = job.output_directory
    if not root.parent.is_dir() or any(
        (parent / "backend.json").exists() for parent in (root, *root.parents)
    ):
        raise OfflineError("job_output_unsafe", "Use a new job root outside backend installations")
    root.mkdir()
    (root / "states").mkdir()
    return save_job(job)


def _current(snapshot: Path) -> StoredJob:
    stored = load_job(snapshot)
    latest = latest_job(stored.job.output_directory)
    if stored.record != latest.record:
        raise OfflineError("job_store_stale", "Stale snapshot; use the latest event record")
    return stored


def _verify_supported(stored: StoredJob) -> None:
    job = stored.job
    if any(stage.status != "queued" for stage in job.stages[1:]):
        raise OfflineError("job_worker_unqualified", "This runner only qualifies the input stage")
    if any(event.stage not in (None, "input") for event in job.history):
        raise OfflineError("job_worker_unqualified", "Later worker activity has not been qualified")
    verify_inputs([job.source, *(output for stage in job.stages for output in stage.outputs)])
    stage = job.stages[0]
    if stage.status == "succeeded":
        if len(stage.outputs) != 1 or stage.outputs[0].size_bytes > 1024**2:
            raise OfflineError(
                "job_input_evidence_invalid", "Expected one bounded preflight report"
            )
        _, raw = capture_input(stage.outputs[0].path)
        report = AudioPreflightReport.model_validate(load_unique_json(raw))
        if report.source != job.source or report != inspect_audio(job.source.path):
            raise OfflineError("job_input_evidence_invalid", "Report disagrees with current audio")
        verify_inputs([stage.outputs[0]])


def verify_audio_job(snapshot: Path) -> StoredJob:
    stored = load_job(snapshot)
    _verify_supported(stored)
    verify_inputs(stored.records)
    return stored


def _save_stop(stored: StoredJob, error: AudioPreflightError | OfflineError | OSError) -> StoredJob:
    blocked = isinstance(error, AudioPreflightError) and error.blocked
    code = error.code if isinstance(error, OfflineError) else "audio_io_failed"
    job = stop_job(stored.job, "blocked" if blocked else "failed", code)
    return save_job(job, stored.record.path)


def run_audio_job(snapshot: Path) -> StoredJob:
    stored = _current(snapshot)
    _verify_supported(stored)
    if stored.job.status == "running":
        stored = save_job(stop_job(stored.job, "failed", "interrupted"), stored.record.path)
    if stored.job.status in ("blocked", "failed", "cancelled"):
        stored = save_job(resume_job(stored.job), stored.record.path)
    if stored.job.stages[0].status != "succeeded":
        stored = save_job(start_stage(stored.job, "input"), stored.record.path)
        try:
            report = inspect_audio(stored.job.source.path)
            destination = guarded_path(
                stored.job.output_directory / f"input-preflight-{len(stored.job.history):08d}.json"
            )
            with destination.open("xb") as stream:
                stream.write((report.model_dump_json(indent=2) + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            job = finish_stage(stored.job, "input", [capture_stream_input(destination)])
        except (OfflineError, OSError) as error:
            return _save_stop(stored, error)
        stored = save_job(job, stored.record.path)
    return save_job(stop_job(stored.job, "blocked", "worker_unavailable"), stored.record.path)


def cancel_audio_job(snapshot: Path) -> StoredJob:
    stored = _current(snapshot)
    # Already stopped jobs have no active worker to cancel; preserve their existing reason.
    if stored.job.status in ("blocked", "failed", "cancelled"):
        return stored
    return save_job(stop_job(stored.job, "cancelled", "user_cancelled"), stored.record.path)
