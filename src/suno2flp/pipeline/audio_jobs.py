"""Shared verified audio decoding and durable jobs; later workers stay blocked."""

import os
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.audio_input import MAX_AUDIO_BYTES, AudioPreflightError, AudioPreflightReport
from suno2flp.core.encoded_audio import EncodedAudioInventory
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
from suno2flp.importer.encoded_audio import inspect_encoded_audio
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.integrations.encoded_recipe import save_encoded_failure
from suno2flp.pipeline.encoded_decode import decode_encoded_audio
from suno2flp.pipeline.job_store import latest_job, load_job, save_job
from suno2flp.pipeline.jobs import finish_stage, new_job, resume_job, start_stage, stop_job
from suno2flp.validator.encoded_decode import verify_encoded_decode
from suno2flp.validator.pcm_decode import verify_pcm_decode


def _compressed(source: Path) -> bool:
    return source.suffix.lower() in (".flac", ".mp3")


def _inspect(
    source: Path, should_cancel: Callable[[], bool] | None = None
) -> AudioPreflightReport | EncodedAudioInventory:
    return (
        inspect_encoded_audio(source, should_cancel=should_cancel)
        if _compressed(source)
        else inspect_audio(source)
    )


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


def _verify_supported(stored: StoredJob, should_cancel: Callable[[], bool] | None = None) -> None:
    job = stored.job
    if any(stage.status != "queued" for stage in job.stages[2:]):
        raise OfflineError(
            "job_worker_unqualified", "This runner only qualifies the input and decode stages"
        )
    if any(event.stage not in (None, "input", "decode") for event in job.history):
        raise OfflineError("job_worker_unqualified", "Later worker activity has not been qualified")
    verify_inputs([job.source, *(output for stage in job.stages for output in stage.outputs)])
    stage = job.stages[0]
    if stage.status == "succeeded":
        if len(stage.outputs) != 1 or stage.outputs[0].size_bytes > 1024**2:
            raise OfflineError(
                "job_input_evidence_invalid", "Expected one bounded preflight report"
            )
        _, raw = capture_input(stage.outputs[0].path)
        report = (
            EncodedAudioInventory if _compressed(job.source.path) else AudioPreflightReport
        ).model_validate(load_unique_json(raw))
        if report.source != job.source or report != _inspect(job.source.path, should_cancel):
            raise OfflineError("job_input_evidence_invalid", "Report disagrees with current audio")
        verify_inputs([stage.outputs[0]])
        decoded = job.stages[1]
        if decoded.status == "succeeded":
            if isinstance(report, EncodedAudioInventory):
                if len(decoded.outputs) != 3:
                    raise OfflineError(
                        "job_decode_evidence_invalid", "Expected PCM, report and attempt"
                    )
                encoded = verify_encoded_decode(
                    decoded.outputs[1].path, should_cancel=should_cancel
                )
                valid = (
                    encoded.inventory == report
                    and encoded.pcm == decoded.outputs[0]
                    and encoded.request == decoded.outputs[2]
                )
            else:
                if len(decoded.outputs) != 2:
                    raise OfflineError(
                        "job_decode_evidence_invalid", "Expected PCM and decode report"
                    )
                evidence = verify_pcm_decode(decoded.outputs[1].path, should_cancel=should_cancel)
                valid = evidence.preflight == report and evidence.pcm == decoded.outputs[0]
            if not valid:
                raise OfflineError(
                    "job_decode_evidence_invalid",
                    "Decoded evidence disagrees with job inputs/outputs",
                )
            verify_inputs(decoded.outputs)


def verify_audio_job(snapshot: Path) -> StoredJob:
    stored = load_job(snapshot)
    _verify_supported(stored)
    verify_inputs(stored.records)
    return stored


def _save_stop(stored: StoredJob, error: AudioPreflightError | OfflineError | OSError) -> StoredJob:
    if isinstance(error, DecodeCancelled):
        return save_job(stop_job(stored.job, "cancelled", error.code), stored.record.path)
    blocked = isinstance(error, AudioPreflightError) and error.blocked
    code = error.code if isinstance(error, OfflineError) else "audio_io_failed"
    job = stop_job(stored.job, "blocked" if blocked else "failed", code)
    return save_job(job, stored.record.path)


def run_audio_job(
    snapshot: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
    decoder_directory: Path | None = None,
) -> StoredJob:
    stored = _current(snapshot)
    if should_cancel is not None and should_cancel():
        return cancel_audio_job(stored.record.path)
    try:
        _verify_supported(stored, should_cancel)
    except DecodeCancelled:
        return cancel_audio_job(stored.record.path)
    if (
        _compressed(stored.job.source.path)
        and stored.job.stages[1].status == "succeeded"
        and decoder_directory is not None
    ):
        _, raw = capture_input(stored.job.stages[1].outputs[1].path)
        if Path(load_unique_json(raw)["backend"]["root"]) != guarded_path(decoder_directory):
            raise OfflineError(
                "audio_runtime_changed", "Completed decode uses another runtime; create a new job"
            )
    if should_cancel is not None and should_cancel():
        return cancel_audio_job(stored.record.path)
    if stored.job.status == "running":
        stored = save_job(stop_job(stored.job, "failed", "interrupted"), stored.record.path)
    if stored.job.status in ("blocked", "failed", "cancelled"):
        stored = save_job(resume_job(stored.job), stored.record.path)
    if stored.job.stages[0].status != "succeeded":
        stored = save_job(start_stage(stored.job, "input"), stored.record.path)
        try:
            report = _inspect(stored.job.source.path, should_cancel)
            if should_cancel is not None and should_cancel():
                return cancel_audio_job(stored.record.path)
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
    if should_cancel is not None and should_cancel():
        return cancel_audio_job(stored.record.path)
    if stored.job.stages[1].status != "succeeded":
        stored = save_job(start_stage(stored.job, "decode"), stored.record.path)
        root = stored.job.output_directory / f"decode-{len(stored.job.history) - 1:08d}"
        encoded_candidate = False
        try:
            root = guarded_path(root)
            report_path = root / "decode.json"
            if _compressed(stored.job.source.path):
                encoded = decode_encoded_audio(
                    stored.job.source.path, root, decoder_directory, should_cancel=should_cancel
                )
                encoded_candidate = True
                if encoded != verify_encoded_decode(report_path, should_cancel=should_cancel):
                    raise OfflineError(
                        "job_decode_evidence_invalid", "Decode verification disagrees"
                    )
                outputs = [encoded.pcm, capture_stream_input(report_path), encoded.request]
            else:
                evidence = decode_pcm_wave(
                    stored.job.source.path, root, should_cancel=should_cancel
                )
                if evidence != verify_pcm_decode(report_path, should_cancel=should_cancel):
                    raise OfflineError(
                        "job_decode_evidence_invalid", "Decode verification disagrees"
                    )
                outputs = [evidence.pcm, capture_stream_input(report_path)]
            if should_cancel is not None and should_cancel():
                return cancel_audio_job(stored.record.path)
            job = finish_stage(stored.job, "decode", outputs)
        except (OfflineError, OSError, ValueError) as error:
            failure = (
                OfflineError("audio_decode_evidence_invalid", str(error))
                if isinstance(error, ValueError)
                else error
            )
            if encoded_candidate:
                save_encoded_failure(root, failure, "verify")
            return _save_stop(stored, failure)
        stored = save_job(job, stored.record.path)
    return save_job(stop_job(stored.job, "blocked", "worker_unavailable"), stored.record.path)


def cancel_audio_job(snapshot: Path) -> StoredJob:
    stored = _current(snapshot)
    # Already stopped jobs have no active worker to cancel; preserve their existing reason.
    if stored.job.status in ("blocked", "failed", "cancelled"):
        return stored
    return save_job(stop_job(stored.job, "cancelled", "user_cancelled"), stored.record.path)
