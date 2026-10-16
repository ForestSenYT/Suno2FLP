"""Exclusive durable event appends with current-head and full-chain verification."""

import os
import re
from pathlib import Path

from suno2flp.core.errors import OfflineError
from suno2flp.core.job_store import JobRecord, StoredJob
from suno2flp.core.jobs import ConversionJob, replay_job_events
from suno2flp.core.offline_files import (
    capture_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity

MAX_RECORDS = 10000


def _invalid(message: str) -> OfflineError:
    return OfflineError("job_store_invalid", message)


def _root(path: Path) -> Path:
    root = guarded_path(path)
    if not root.is_dir() or not guarded_path(root / "states").is_dir():
        raise _invalid("Job root and states directory must already exist")
    if any((parent / "backend.json").exists() for parent in (root, *root.parents)):
        raise _invalid("Jobs must be outside backend installations")
    return root


def load_job(path: Path) -> StoredJob:
    destination = guarded_path(path)
    root = _root(destination.parent.parent)
    if destination.parent != root / "states" or not re.fullmatch(
        r"[0-9]{8}\.json", destination.name
    ):
        raise _invalid("Expected a canonical states/sequence.json record")
    sequence = int(destination.stem)
    if sequence >= MAX_RECORDS:
        raise _invalid("Event limit exceeded")
    records: list[JobRecord] = []
    identities: list[FileIdentity] = []
    expected = None
    for number in range(sequence, -1, -1):
        current = root / "states" / f"{number:08d}.json"
        if current.stat().st_size > 1024**2:
            raise _invalid("Event record exceeds size limit")
        identity, raw = capture_input(current)
        if expected is not None and identity != expected:
            raise OfflineError("offline_input_changed", "Previous job record changed")
        record = JobRecord.model_validate(load_unique_json(raw))
        if record.output_directory != root or record.event.sequence != number:
            raise _invalid("Record location, root and sequence must agree")
        if records and record.job_id != records[0].job_id:
            raise _invalid("Job identity changed inside the chain")
        prior = root / "states" / f"{number - 1:08d}.json"
        if number == 0:
            if record.previous is not None or record.event.kind != "created":
                raise _invalid("Only creation starts a chain")
        elif record.previous is None or record.previous.path != prior:
            raise _invalid("Previous record must be the canonical preceding event")
        expected = record.previous
        records.append(record)
        identities.append(identity)
    events = [record.event for record in reversed(records)]
    source = events[0].source
    if source is None:
        raise _invalid("Creation must retain the original source")
    status, stages = replay_job_events(events, root, source)
    job = ConversionJob(
        job_id=records[0].job_id,
        source=source,
        output_directory=root,
        status=status,
        stages=stages,
        history=events,
    )
    verify_inputs(identities)
    return StoredJob(record=identities[0], records=list(reversed(identities)), job=job)


def latest_job(root: Path) -> StoredJob:
    directory = _root(root) / "states"
    paths = sorted(directory.iterdir())
    if not paths or len(paths) > MAX_RECORDS:
        raise _invalid("Expected a nonempty bounded event chain")
    for number, path in enumerate(paths):
        if path.name != f"{number:08d}.json" or not guarded_path(path).is_file():
            raise _invalid("Incomplete or unexpected state entry; no stale fallback")
    return load_job(paths[-1])


def save_job(job: ConversionJob, previous: Path | None = None) -> StoredJob:
    current = ConversionJob.model_validate(job.model_dump())
    root = _root(current.output_directory)
    sequence = len(current.history) - 1
    if sequence >= MAX_RECORDS:
        raise _invalid("Event limit exceeded")
    prior = None
    if previous is None:
        if sequence != 0 or any((root / "states").iterdir()):
            raise _invalid("Creation requires an empty event directory")
    else:
        prior = latest_job(root)
        if guarded_path(previous) != prior.record.path:
            raise _invalid("Stale snapshot cannot append")
        if (
            len(current.history) != len(prior.job.history) + 1
            or current.history[:-1] != prior.job.history
            or current.source != prior.job.source
            or current.job_id != prior.job.job_id
        ):
            raise _invalid("Append must extend the same job by exactly one event")
    evidence = []
    if current.history[-1].kind in ("created", "started", "finished", "resumed"):
        evidence = [
            current.source,
            *(output for stage in current.stages for output in stage.outputs),
        ]
        verify_inputs(evidence)
    record = JobRecord(
        job_id=current.job_id,
        output_directory=root,
        event=current.history[-1],
        previous=prior.record if prior else None,
    )
    destination = guarded_path(root / "states" / f"{sequence:08d}.json")
    with destination.open("xb") as stream:
        stream.write((record.model_dump_json(indent=2) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    verify_inputs(evidence)
    stored = latest_job(root)
    if stored.job != current:
        raise _invalid("Concurrent event publication; reload the latest state")
    return stored
