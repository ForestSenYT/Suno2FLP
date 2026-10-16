"""Shared jobs run real preflight and stop honestly at unavailable workers."""

import json
import wave

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.pipeline.jobs import start_stage


def api():
    from suno2flp.pipeline import audio_jobs

    return audio_jobs


def source(tmp_path):
    path = tmp_path / "真实 song.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\1" * 8)
    return path


def test_real_preflight_completes_input_then_blocks_without_inventing_later_work(tmp_path):
    path = source(tmp_path)
    before = capture_stream_input(path)
    created = api().create_audio_job(path, tmp_path / "new-job", "song-v1")
    assert created.job.status == "queued" and len(created.records) == 1
    result = api().run_audio_job(created.record.path)
    assert result.job.status == "blocked"
    assert result.job.history[-1].code == "worker_unavailable"
    assert result.job.stages[0].status == "succeeded"
    assert all(stage.status == "queued" for stage in result.job.stages[1:])
    report = json.loads(result.job.stages[0].outputs[0].path.read_bytes())
    assert report["frames"] == 4
    assert report["source"] == before.model_dump(mode="json")
    assert api().verify_audio_job(result.record.path) == result
    assert capture_stream_input(path) == before
    assert not list(result.job.output_directory.rglob("*.flp"))


@pytest.mark.parametrize(
    "name,data,status,code",
    [
        ("bad.wav", b"bad", "failed", "audio_invalid"),
        ("unknown.mp3", b"unknown", "blocked", "audio_format_unavailable"),
    ],
)
def test_failures_and_unsupported_inputs_are_durable(tmp_path, name, data, status, code):
    path = tmp_path / name
    path.write_bytes(data)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    result = api().run_audio_job(created.record.path)
    assert result.job.status == status and result.job.history[-1].code == code
    assert result.job.stages[0].outputs == []


def test_cancel_queued_job_after_source_is_gone_retains_history(tmp_path):
    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    path.unlink()
    cancelled = api().cancel_audio_job(created.record.path)
    assert cancelled.job.status == "cancelled" and len(cancelled.records) == 2
    assert cancelled.job.history[0] == created.job.history[0]


def test_changed_source_stale_snapshot_and_root_reuse_refuse_work(tmp_path):
    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    with pytest.raises((OfflineError, ValueError, OSError)):
        api().create_audio_job(path, tmp_path / "job", "song-v2")
    result = api().run_audio_job(created.record.path)
    with pytest.raises(OfflineError, match="Stale"):
        api().run_audio_job(created.record.path)
    path.write_bytes(b"replacement")
    with pytest.raises(OfflineError, match="changed"):
        api().run_audio_job(result.record.path)


def test_restart_of_interrupted_input_records_failure_and_retry(tmp_path):
    from suno2flp.pipeline.job_store import save_job

    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    interrupted = save_job(start_stage(created.job, "input"), created.record.path)
    result = api().run_audio_job(interrupted.record.path)
    assert result.job.status == "blocked"
    assert [event.kind for event in result.job.history] == [
        "created",
        "started",
        "stopped",
        "resumed",
        "started",
        "finished",
        "stopped",
    ]
    assert result.job.history[2].code == "interrupted"


def test_tampered_report_cannot_verify_or_resume(tmp_path):
    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    result = api().run_audio_job(created.record.path)
    report = result.job.stages[0].outputs[0].path
    report.write_bytes(report.read_bytes() + b" ")
    with pytest.raises(OfflineError, match="changed"):
        api().verify_audio_job(result.record.path)
    with pytest.raises(OfflineError, match="changed"):
        api().run_audio_job(result.record.path)


def test_completed_input_must_equal_independent_preflight_not_only_match_file_hash(tmp_path):
    from suno2flp.pipeline.job_store import save_job
    from suno2flp.pipeline.jobs import finish_stage

    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    started = save_job(start_stage(created.job, "input"), created.record.path)
    report = created.job.output_directory / "fake.json"
    report.write_text("{}")
    forged = save_job(
        finish_stage(started.job, "input", [capture_stream_input(report)]), started.record.path
    )
    with pytest.raises((OfflineError, ValueError)):
        api().verify_audio_job(forged.record.path)


def test_source_change_during_preflight_does_not_finish_input(tmp_path, monkeypatch):
    module = api()
    original = module.inspect_audio
    path = source(tmp_path)
    created = module.create_audio_job(path, tmp_path / "job", "song-v1")

    def inspect_then_change(path):
        result = original(path)
        path.write_bytes(b"changed")
        return result

    monkeypatch.setattr(module, "inspect_audio", inspect_then_change)
    result = module.run_audio_job(created.record.path)
    assert result.job.status == "failed"
    assert result.job.stages[0].outputs == []
    assert result.job.history[-1].code == "offline_input_changed"


def test_structural_later_stage_completion_does_not_qualify_a_worker(tmp_path):
    from suno2flp.pipeline.job_store import save_job
    from suno2flp.pipeline.jobs import resume_job

    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    blocked = api().run_audio_job(created.record.path)
    resumed = save_job(resume_job(blocked.job), blocked.record.path)
    forged = save_job(start_stage(resumed.job, "decode"), resumed.record.path)
    with pytest.raises(OfflineError, match="only qualifies"):
        api().run_audio_job(forged.record.path)
    with pytest.raises(OfflineError, match="only qualifies"):
        api().verify_audio_job(forged.record.path)


def test_cancel_of_stopped_job_preserves_reason_even_without_source(tmp_path):
    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    blocked = api().run_audio_job(created.record.path)
    path.unlink()
    assert api().cancel_audio_job(blocked.record.path) == blocked
