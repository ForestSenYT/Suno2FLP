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


def test_real_preflight_and_decode_complete_then_block_without_inventing_later_work(tmp_path):
    path = source(tmp_path)
    before = capture_stream_input(path)
    created = api().create_audio_job(path, tmp_path / "new-job", "song-v1")
    assert created.job.status == "queued" and len(created.records) == 1
    result = api().run_audio_job(created.record.path)
    assert result.job.status == "blocked"
    assert result.job.history[-1].code == "worker_unavailable"
    assert result.job.stages[0].status == "succeeded"
    assert result.job.stages[1].status == "succeeded"
    assert len(result.job.stages[1].outputs) == 2
    assert all(stage.status == "queued" for stage in result.job.stages[2:])
    report = json.loads(result.job.stages[0].outputs[0].path.read_bytes())
    assert report["frames"] == 4
    assert report["source"] == before.model_dump(mode="json")
    assert api().verify_audio_job(result.record.path) == result
    assert capture_stream_input(path) == before
    assert not list(result.job.output_directory.rglob("*.flp"))


def test_resume_reuses_only_independently_verified_decode_and_retains_all_outputs(tmp_path):
    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    first = api().run_audio_job(created.record.path)
    assert first.job.stages[1].status == "succeeded"
    outputs = [output for stage in first.job.stages for output in stage.outputs]
    result = api().run_audio_job(first.record.path)
    assert result.job.history[: len(first.job.history)] == first.job.history
    assert [output for stage in result.job.stages for output in stage.outputs] == outputs
    assert len(list(result.job.output_directory.glob("decode-*"))) == 1
    assert result.job.status == "blocked"
    assert api().verify_audio_job(result.record.path) == result


def test_cancel_during_real_decode_retains_partial_and_resumes_to_new_directory(tmp_path):
    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    cancelled = api().run_audio_job(
        created.record.path,
        should_cancel=lambda: bool(list(created.job.output_directory.glob("decode-*/decoded.wav"))),
    )
    assert cancelled.job.status == "cancelled"
    assert cancelled.job.stages[0].status == "succeeded"
    assert cancelled.job.stages[1].status == "cancelled"
    assert cancelled.job.stages[1].outputs == []
    partial = capture_stream_input(next(created.job.output_directory.glob("decode-*/decoded.wav")))
    result = api().run_audio_job(cancelled.record.path)
    assert result.job.stages[1].status == "succeeded"
    assert len(list(result.job.output_directory.glob("decode-*"))) == 2
    assert capture_stream_input(partial.path) == partial
    assert api().verify_audio_job(result.record.path) == result


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
    forged = save_job(start_stage(resumed.job, "separate"), resumed.record.path)
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


def test_cooperative_cancel_before_work_does_not_need_missing_source(tmp_path):
    path = source(tmp_path)
    created = api().create_audio_job(path, tmp_path / "job", "song-v1")
    path.unlink()
    cancelled = api().run_audio_job(created.record.path, should_cancel=lambda: True)
    assert cancelled.job.status == "cancelled"
    assert [event.kind for event in cancelled.job.history] == ["created", "stopped"]
    assert cancelled.job.stages[0].outputs == []


def test_cancel_requested_during_preflight_records_stop_without_completion(tmp_path, monkeypatch):
    from threading import Event

    module = api()
    original = module.inspect_audio
    request = Event()
    path = source(tmp_path)
    before = capture_stream_input(path)
    created = module.create_audio_job(path, tmp_path / "job", "song-v1")

    def inspect_then_cancel(path):
        report = original(path)
        request.set()
        return report

    monkeypatch.setattr(module, "inspect_audio", inspect_then_cancel)
    cancelled = module.run_audio_job(created.record.path, should_cancel=request.is_set)
    assert cancelled.job.status == "cancelled"
    assert cancelled.job.history[-1].code == "user_cancelled"
    assert cancelled.job.stages[0].outputs == []
    assert not list(created.job.output_directory.glob("input-preflight-*.json"))
    assert capture_stream_input(path) == before


def test_valid_structural_decode_events_do_not_attest_a_forged_audio_output(tmp_path):
    from suno2flp.importer.audio import inspect_audio
    from suno2flp.importer.pcm_decode import decode_pcm_wave
    from suno2flp.pipeline.job_store import save_job
    from suno2flp.pipeline.jobs import finish_stage

    path = source(tmp_path)
    stored = api().create_audio_job(path, tmp_path / "job", "song-v1")
    stored = save_job(start_stage(stored.job, "input"), stored.record.path)
    preflight = stored.job.output_directory / "input.json"
    preflight.write_text(inspect_audio(path).model_dump_json(), encoding="utf-8")
    stored = save_job(
        finish_stage(stored.job, "input", [capture_stream_input(preflight)]), stored.record.path
    )
    stored = save_job(start_stage(stored.job, "decode"), stored.record.path)
    root = stored.job.output_directory / "decode-forged"
    decoded = decode_pcm_wave(path, root)
    raw = decoded.pcm.path.read_bytes()
    decoded.pcm.path.write_bytes(raw[:58] + b"\0" * (len(raw) - 58))
    import hashlib

    data = json.loads((root / "decode.json").read_bytes())
    data["pcm"] = capture_stream_input(decoded.pcm.path).model_dump(mode="json")
    data["samples_sha256"] = hashlib.sha256(decoded.pcm.path.read_bytes()[58:]).hexdigest()
    (root / "decode.json").write_text(json.dumps(data), encoding="utf-8")
    stored = save_job(
        finish_stage(
            stored.job,
            "decode",
            [capture_stream_input(decoded.pcm.path), capture_stream_input(root / "decode.json")],
        ),
        stored.record.path,
    )
    with pytest.raises(OfflineError, match="samples differ"):
        api().verify_audio_job(stored.record.path)
    with pytest.raises(OfflineError, match="samples differ"):
        api().run_audio_job(stored.record.path)


@pytest.mark.parametrize("interrupted", [False, True])
def test_old_input_only_history_can_verify_and_advance_without_replacing_old_evidence(
    tmp_path, interrupted
):
    from suno2flp.importer.audio import inspect_audio
    from suno2flp.pipeline.job_store import save_job
    from suno2flp.pipeline.jobs import finish_stage, stop_job

    path = source(tmp_path)
    stored = api().create_audio_job(path, tmp_path / "job", "song-v1")
    stored = save_job(start_stage(stored.job, "input"), stored.record.path)
    preflight = stored.job.output_directory / "input-preflight-00000002.json"
    preflight.write_text(inspect_audio(path).model_dump_json(), encoding="utf-8")
    stored = save_job(
        finish_stage(stored.job, "input", [capture_stream_input(preflight)]), stored.record.path
    )
    if interrupted:
        stored = save_job(start_stage(stored.job, "decode"), stored.record.path)
    else:
        stored = save_job(stop_job(stored.job, "blocked", "worker_unavailable"), stored.record.path)
    before = [capture_stream_input(p.path) for p in stored.records] + [
        capture_stream_input(preflight)
    ]
    assert api().verify_audio_job(stored.record.path) == stored
    result = api().run_audio_job(stored.record.path)
    assert result.job.stages[1].status == "succeeded"
    assert result.job.history[: len(stored.job.history)] == stored.job.history
    assert all(capture_stream_input(p.path) == p for p in before)
    if interrupted:
        assert any(event.code == "interrupted" for event in result.job.history)
