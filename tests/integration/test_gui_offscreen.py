"""Direct controller calls and offscreen rendering; no mouse/keyboard/UI automation."""

import os
import time
import wave
from threading import Event

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
pytest.importorskip("PySide6", reason="Install the optional gui extra for offscreen GUI tests")
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def application():
    from suno2flp.gui.app import configure_font

    application = QApplication.instance() or QApplication([])
    configure_font()
    return application


def window(tmp_path):
    from suno2flp.gui.model import JobActions
    from suno2flp.gui.window import WorkbenchWindow

    return WorkbenchWindow(JobActions(tmp_path / "jobs"))


def source(tmp_path):
    path = tmp_path / "中文 song.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "none"))
        stream.writeframes(b"\0" * 8)
    return path


def finish(application, workbench):
    deadline = time.monotonic() + 10
    while workbench.busy and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.002)
    application.processEvents()
    assert not workbench.busy, "Worker did not finish within ten seconds"


def test_real_gui_lifecycle_history_and_render(application, tmp_path):
    bench = window(tmp_path)
    assert bench.selected is None and not bench.job_actions.root.exists()
    bench.create_job(source(tmp_path))
    assert bench.busy and not bench.root_edit.isEnabled()
    finish(application, bench)
    assert bench.selected.job.status == "queued"
    bench.run_selected()
    finish(application, bench)
    assert bench.selected.job.status == "blocked"
    assert "尚未接入" in bench.explanation.text()
    assert "1 / 11" in bench.summary.text()
    assert not bench.cancel_button.isEnabled() and bench.run_button.isEnabled()
    bench.verify_selected()
    finish(application, bench)
    assert "一致" in bench.notice.text()
    bench.refresh_history()
    finish(application, bench)
    assert bench.history_list.count() == 1
    bench.resize(1100, 800)
    bench.show()  # Qt offscreen platform only; no desktop window/input.
    application.processEvents()
    assert not bench.grab().isNull()
    snapshot = bench.selected.record.path
    bench.close()
    reopened = window(tmp_path)
    reopened.load_snapshot(snapshot)
    finish(application, reopened)
    assert reopened.selected.job.status == "blocked"
    reopened.close()


def test_preflight_does_not_freeze_gui_and_cancel_waits_for_boundary(
    application, tmp_path, monkeypatch
):
    from suno2flp.pipeline import audio_jobs

    bench = window(tmp_path)
    bench.create_job(source(tmp_path))
    finish(application, bench)
    entered, release = Event(), Event()
    original = audio_jobs.inspect_audio

    def slow_real_inspect(path):
        entered.set()
        assert release.wait(5)
        return original(path)

    monkeypatch.setattr(audio_jobs, "inspect_audio", slow_real_inspect)
    ticks = []
    timer = QTimer()
    timer.setInterval(2)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    try:
        bench.run_selected()
        assert entered.wait(3)
        for _ in range(10):
            application.processEvents()
            time.sleep(0.005)
        assert ticks and bench.busy
        bench.cancel_selected()
        assert bench.busy and "停止" in bench.notice.text()
    finally:
        release.set()
        finish(application, bench)
        timer.stop()
    assert bench.selected.job.status == "cancelled"
    assert bench.selected.job.stages[0].outputs == []
    bench.close()


def test_error_restores_controls_and_explains_problem(application, tmp_path):
    bench = window(tmp_path)
    bench.create_job(tmp_path / "missing.wav")
    finish(application, bench)
    assert bench.selected is None and bench.root_edit.isEnabled()
    assert bench.notice.text() and bench.last_error
    bench.create_job(source(tmp_path))
    finish(application, bench)
    assert bench.selected is not None and not bench.last_error
    bench.close()


def test_create_uses_new_workspace_field_without_losing_operation(application, tmp_path):
    bench = window(tmp_path)
    new_root = tmp_path / "different-jobs"
    bench.root_edit.setText(str(new_root))
    bench.source_edit.setText(str(source(tmp_path)))
    bench._create_from_field()
    finish(application, bench)
    assert bench.selected is not None
    assert bench.selected.job.output_directory.parent == new_root
    bench.close()


def test_invalid_workspace_does_not_fall_back_to_previous_root(application, tmp_path):
    bench = window(tmp_path)
    bench.root_edit.setText(str(tmp_path / "bad.."))
    bench.source_edit.setText(str(source(tmp_path)))
    bench._create_from_field()
    finish(application, bench)
    assert bench.selected is None and not bench.job_actions.root.exists()
    bench.close()


def test_close_during_work_preserves_cancel_and_defers_close(application, tmp_path, monkeypatch):
    from suno2flp.pipeline import audio_jobs

    bench = window(tmp_path)
    bench.create_job(source(tmp_path))
    finish(application, bench)
    bench.show()
    entered, release = Event(), Event()
    original = audio_jobs.inspect_audio

    def slow_real_inspect(path):
        entered.set()
        assert release.wait(5)
        return original(path)

    monkeypatch.setattr(audio_jobs, "inspect_audio", slow_real_inspect)
    try:
        bench.run_selected()
        assert entered.wait(3)
        assert not bench.close() and bench.busy and bench.isVisible()
        assert not bench.set_workspace(tmp_path / "new-root")
    finally:
        release.set()
        finish(application, bench)
    assert not bench.isVisible() and bench.selected.job.status == "cancelled"


def test_system_fonts_make_offscreen_text_readable(application):
    from PySide6.QtGui import QFontMetrics

    from suno2flp.gui.app import configure_font

    assert configure_font()
    assert QFontMetrics(application.font()).inFont("A")
    if os.name == "nt":
        assert QFontMetrics(application.font()).inFont("中")


def test_corrupt_history_selection_clears_old_action_target(application, tmp_path):
    from suno2flp.gui.model import HistoryEntry

    bench = window(tmp_path)
    bench.create_job(source(tmp_path))
    finish(application, bench)
    bench.selected.record.path.write_bytes(b"{")
    bench.refresh_history()
    finish(application, bench)
    item = bench.history_list.item(0)
    assert isinstance(item.data(256), HistoryEntry)
    bench._history_selected(item)
    assert bench.selected is None and not bench.run_button.isEnabled()
    assert "不可读" in bench.status.text()
    bench.close()


def test_invalid_startup_root_has_explicit_failure(application, tmp_path, capsys):
    from suno2flp.gui.app import main

    assert main(["--jobs-root", str(tmp_path / "bad..")]) == 2
    assert "任务目录" in capsys.readouterr().err


def test_editing_root_then_creating_does_not_start_competing_refresh(application, tmp_path):
    bench = window(tmp_path)
    bench.root_edit.setText(str(tmp_path / "edited-root"))
    bench._apply_root()  # Same controller sequence as focus leaving the root field.
    assert not bench.busy
    bench.source_edit.setText(str(source(tmp_path)))
    bench._create_from_field()
    finish(application, bench)
    assert bench.selected is not None
    assert bench.selected.job.output_directory.parent == tmp_path / "edited-root"
    bench.close()


def test_history_corruption_after_enumeration_cannot_target_previous_job(application, tmp_path):
    bench = window(tmp_path)
    bench.create_job(source(tmp_path))
    finish(application, bench)
    alpha = bench.selected
    beta_source = tmp_path / "Beta.wav"
    beta_source.write_bytes(alpha.job.source.path.read_bytes())
    bench.create_job(beta_source)
    finish(application, bench)
    beta = bench.selected
    beta_item = next(
        bench.history_list.item(index)
        for index in range(bench.history_list.count())
        if bench.history_list.item(index).data(256).snapshot == beta.record.path
    )
    bench.load_snapshot(alpha.record.path)
    finish(application, bench)
    beta.record.path.write_bytes(b"{")
    bench.history_list.setCurrentItem(beta_item)
    bench._history_selected(beta_item)
    finish(application, bench)
    assert bench.selected is None
    assert "Beta" in bench.task_title.text() and "不可读" in bench.status.text()
    assert not bench.run_button.isEnabled() and not bench.cancel_button.isEnabled()
    bench.cancel_selected()
    finish(application, bench)
    assert bench.job_actions.load(alpha.record.path).job.status == "queued"
    bench.close()


def test_manual_workspace_change_disables_previous_task_controls(application, tmp_path):
    bench = window(tmp_path)
    bench.create_job(source(tmp_path))
    finish(application, bench)
    assert bench.cancel_button.isEnabled()
    assert bench.set_workspace(tmp_path / "empty-workspace", refresh=False)
    assert bench.selected is None and not bench.busy
    assert not any(
        button.isEnabled()
        for button in (bench.run_button, bench.verify_button, bench.cancel_button)
    )
    bench.close()
