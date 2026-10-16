"""Durable transitions remain inspectable and cannot overwrite earlier evidence."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.pipeline.jobs import new_job, report_progress, start_stage, stop_job


def api():
    from suno2flp.pipeline import job_store

    return job_store


def seed(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    root = tmp_path / "job"
    job = new_job("song-v1", capture_stream_input(source), root)
    (root / "states").mkdir(parents=True)
    return job


def test_store_reconstructs_each_historical_state_with_hash_links(tmp_path):
    job = seed(tmp_path)
    first = api().save_job(job)
    second = api().save_job(start_stage(job, "input"), first.record.path)
    assert second.record.path.name == "00000001.json"
    assert len(second.records) == 2
    raw = json.loads(second.record.path.read_bytes())
    assert raw["previous"]["sha256"] == first.record.sha256
    assert "history" not in raw and raw["event"]["kind"] == "started"
    assert api().load_job(first.record.path).job == job
    assert api().latest_job(job.output_directory) == second


def test_cancel_can_be_persisted_and_inspected_after_source_disappears(tmp_path):
    job = seed(tmp_path)
    first = api().save_job(job)
    job.source.path.unlink()
    cancelled = api().save_job(stop_job(job, "cancelled", "user_cancelled"), first.record.path)
    assert api().load_job(cancelled.record.path).job.status == "cancelled"
    assert api().latest_job(job.output_directory) == cancelled


def test_start_cannot_persist_if_original_changed(tmp_path):
    job = seed(tmp_path)
    first = api().save_job(job)
    started = start_stage(job, "input")
    job.source.path.write_bytes(b"different")
    with pytest.raises(OfflineError, match="changed"):
        api().save_job(started, first.record.path)
    assert api().latest_job(job.output_directory) == first


def test_stale_writer_and_creation_reuse_never_overwrite(tmp_path):
    job = seed(tmp_path)
    first = api().save_job(job)
    second = api().save_job(start_stage(job, "input"), first.record.path)
    before = second.record.path.read_bytes()
    with pytest.raises((OfflineError, ValueError, OSError)):
        api().save_job(start_stage(job, "input"), first.record.path)
    with pytest.raises((OfflineError, ValueError, OSError)):
        api().save_job(job)
    assert second.record.path.read_bytes() == before


def test_append_cannot_skip_an_event_or_replace_creation_source(tmp_path):
    job = seed(tmp_path)
    first = api().save_job(job)
    skipped = report_progress(start_stage(job, "input"), "input", 20)
    with pytest.raises((OfflineError, ValueError, OSError)):
        api().save_job(skipped, first.record.path)
    replacement = job.model_copy(deep=True)
    other = tmp_path / "other.wav"
    other.write_bytes(b"other")
    identity = capture_stream_input(other)
    replacement = replacement.model_copy(update={"source": identity})
    replacement.history[0].source = identity
    with pytest.raises((OfflineError, ValueError, OSError)):
        api().save_job(start_stage(replacement, "input"), first.record.path)


@pytest.mark.parametrize("corruption", ["partial", "unknown", "missing", "reordered", "foreign"])
def test_corrupt_newest_is_never_ignored(tmp_path, corruption):
    job = seed(tmp_path)
    first = api().save_job(job)
    second = api().save_job(start_stage(job, "input"), first.record.path)
    raw = json.loads(second.record.path.read_bytes())
    if corruption == "partial":
        second.record.path.write_bytes(b'{"schema_version":')
    elif corruption == "unknown":
        raw["pretend_success"] = True
        second.record.path.write_text(json.dumps(raw))
    elif corruption == "missing":
        first.record.path.unlink()
    elif corruption == "reordered":
        raw["event"]["sequence"] = 99
        second.record.path.write_text(json.dumps(raw))
    else:
        raw["previous"]["path"] = str(tmp_path / "outside.json")
        second.record.path.write_text(json.dumps(raw))
    with pytest.raises((OfflineError, ValueError, OSError)):
        api().latest_job(job.output_directory)


def test_changed_ancestor_and_noncanonical_record_are_rejected(tmp_path):
    job = seed(tmp_path)
    first = api().save_job(job)
    second = api().save_job(start_stage(job, "input"), first.record.path)
    first.record.path.write_bytes(first.record.path.read_bytes() + b" ")
    with pytest.raises(Exception, match="changed"):
        api().load_job(second.record.path)
    (job.output_directory / "states" / "other.json").write_bytes(b"{}")
    with pytest.raises((OfflineError, ValueError, OSError)):
        api().latest_job(job.output_directory)


def test_duplicate_json_keys_rejected(tmp_path):
    job = seed(tmp_path)
    first = api().save_job(job)
    raw = first.record.path.read_text()
    first.record.path.write_text(
        raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    )
    with pytest.raises(ValueError, match="Duplicate"):
        api().load_job(first.record.path)


def test_concurrent_appends_publish_one_event_without_overwriting(tmp_path):
    job = seed(tmp_path)
    first = api().save_job(job)
    started = api().save_job(start_stage(job, "input"), first.record.path)
    barrier = Barrier(2)

    def append(progress):
        updated = report_progress(started.job, "input", progress)
        barrier.wait(timeout=5)
        try:
            return api().save_job(updated, started.record.path)
        except (OfflineError, FileExistsError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append, [20, 30]))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    latest = api().latest_job(job.output_directory)
    assert latest == winners[0] and len(latest.records) == 3
    assert latest.job.stages[0].progress in (20, 30)
