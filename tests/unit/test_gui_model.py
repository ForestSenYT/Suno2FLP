"""GUI presentation/actions expose real shared jobs, without importing Qt."""

import json
import wave
from threading import Event

import pytest

from suno2flp.core.errors import OfflineError


def api():
    from suno2flp.gui import model

    return model


def source(tmp_path):
    path = tmp_path / "中文 song.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "none"))
        stream.writeframes(b"\0" * 8)
    return path


def test_actions_and_view_follow_real_state_with_exact_details(tmp_path):
    model = api()
    path = source(tmp_path)
    actions = model.JobActions(tmp_path / "任务")
    assert actions.history() == [] and not actions.root.exists()
    created = actions.create(path)
    view = model.present_job(created)
    assert view.title == "中文 song" and view.status == "待检查"
    assert view.completed == 0 and view.total == 11
    assert view.can_run and view.can_cancel
    assert json.loads(view.diagnostics)["job"]["source"]["path"] == str(path)
    assert created.job.source.sha256 in view.diagnostics
    result = actions.run(created.record.path, Event())
    view = model.present_job(result)
    assert view.status == "已阻断" and view.completed == 1
    assert "尚未接入" in view.explanation and "FLP" in view.explanation
    assert not view.can_cancel and view.can_run
    assert view.stages[0] == ("音频检查", "已完成")
    assert all(status == "待执行" for _, status in view.stages[1:])
    assert actions.verify(result.record.path) == result
    history = model.JobActions(actions.root).history()
    assert len(history) == 1 and history[0].snapshot == result.record.path
    assert history[0].error is None and history[0].title == "中文 song"


def test_history_retains_corrupt_job_as_visible_error(tmp_path):
    actions = api().JobActions(tmp_path / "jobs")
    created = actions.create(source(tmp_path))
    created.record.path.write_bytes(b'{"broken":')
    history = actions.history()
    assert len(history) == 1 and history[0].error
    assert history[0].snapshot is None and history[0].root == created.job.output_directory


def test_current_head_load_and_cancel_do_not_require_source(tmp_path):
    actions = api().JobActions(tmp_path / "jobs")
    path = source(tmp_path)
    created = actions.create(path)
    cancelled = actions.cancel(created.record.path)
    path.unlink()
    loaded = actions.load(created.record.path)
    assert loaded == cancelled
    assert api().present_job(loaded).status == "已取消"
    with pytest.raises(OSError):
        actions.run(cancelled.record.path, Event())


def test_backend_workspace_is_rejected_before_creating_any_directory(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "backend.json").write_text("{}")
    root = backend / "new-jobs"
    with pytest.raises(OfflineError):
        api().JobActions(root).create(source(tmp_path))
    assert not root.exists()


def test_requested_cancel_creates_real_cancelled_state(tmp_path):
    actions = api().JobActions(tmp_path / "jobs")
    created = actions.create(source(tmp_path))
    event = Event()
    event.set()
    cancelled = actions.run(created.record.path, event)
    assert cancelled.job.status == "cancelled"
    assert api().present_job(cancelled).completed == 0


def test_partial_job_directory_is_visible_in_history(tmp_path):
    actions = api().JobActions(tmp_path / "jobs")
    (actions.root / "audio-interrupted").mkdir(parents=True)
    history = actions.history()
    assert len(history) == 1 and history[0].error and history[0].snapshot is None


def test_actions_refuse_snapshot_from_different_workspace(tmp_path):
    first = api().JobActions(tmp_path / "first")
    other = api().JobActions(tmp_path / "other")
    created = first.create(source(tmp_path))
    for action in (other.load, other.verify, other.cancel):
        with pytest.raises(OfflineError, match="当前任务目录"):
            action(created.record.path)
    with pytest.raises(OfflineError, match="当前任务目录"):
        other.run(created.record.path, Event())
