"""Installed GUI lifecycle with authored audio and offscreen rendering, no desktop input."""

import argparse
import importlib.metadata
import json
import os
import time
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--require-installed", action="store_true")
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    import suno2flp
    from suno2flp.core.offline_files import capture_stream_input
    from suno2flp.gui.app import configure_font
    from suno2flp.gui.model import JobActions
    from suno2flp.gui.window import WorkbenchWindow

    distribution = importlib.metadata.distribution("suno2flp")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    installed = (
        not direct.get("dir_info", {}).get("editable", False)
        and any(str(item) == "suno2flp/__init__.py" for item in distribution.files or [])
        and Path(distribution.locate_file("suno2flp/__init__.py")).resolve()
        == Path(suno2flp.__file__).resolve()
    )
    if args.require_installed and not installed:
        raise RuntimeError("GUI smoke requires a genuinely installed wheel")
    root = args.workspace.absolute()
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    source = root / "合成 song.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((2, 2, 48000, 0, "NONE", "none"))
        stream.writeframes(b"\0" * 19200)
    original = capture_stream_input(source)
    application = QApplication([])
    font = configure_font()
    metrics = QFontMetrics(application.font())
    if not metrics.inFont("A") or (os.name == "nt" and not metrics.inFont("中")):
        raise RuntimeError("Required system font is unavailable")
    bench = WorkbenchWindow(JobActions(root / "jobs"))

    def finish():
        deadline = time.monotonic() + 20
        while bench.busy and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.002)
        application.processEvents()
        if bench.busy:
            raise RuntimeError("GUI worker timed out")

    def render(name):
        application.processEvents()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not bench.grab().save(buffer, "PNG"):
            raise RuntimeError("Offscreen render failed")
        with (root / name).open("xb") as stream:
            stream.write(bytes(buffer.data()))
        buffer.close()

    bench.source_edit.setText(str(source))
    bench.create_job(source)
    finish()
    if bench.selected is None or bench.selected.job.status != "queued":
        raise RuntimeError("GUI did not create a queued job")
    bench.run_selected()
    finish()
    if bench.selected.job.status != "blocked" or bench.selected.job.stages[0].status != "succeeded":
        raise RuntimeError("GUI did not show real input completion and unavailable workers")
    snapshot = bench.selected.record.path
    bench.verify_selected()
    finish()
    if bench.last_error or "一致" not in bench.notice.text():
        raise RuntimeError("GUI evidence verification failed")
    bench.show()
    render("blocked-normal.png")
    bench.resize(960, 720)
    bench.details_button.setChecked(True)
    render("blocked-minimum.png")
    bench.close()
    bench = WorkbenchWindow(JobActions(root / "jobs"))
    bench.load_snapshot(snapshot)
    finish()
    if bench.selected is None or bench.selected.job.status != "blocked":
        raise RuntimeError("GUI did not restore the real persistent history")
    report = bench.selected.job.stages[0].outputs[0].path
    report.write_bytes(report.read_bytes() + b" ")  # Only this newly generated synthetic report.
    bench.verify_selected()
    finish()
    if not bench.last_error:
        raise RuntimeError("GUI accepted changed evidence")
    bench.create_job(source)
    finish()
    bench.cancel_selected()
    finish()
    if bench.selected.job.status != "cancelled":
        raise RuntimeError("GUI cancellation was not persisted")
    bench.close()
    if capture_stream_input(source) != original or list(root.rglob("*.flp")):
        raise RuntimeError("Source changed or an FLP was created")
    print(
        json.dumps(
            {
                "workflow": "passed",
                "installed_wheel": installed,
                "qt_platform": "offscreen",
                "create_run_block_verify_history_cancel": "passed",
                "evidence_tamper_refused": True,
                "original_unchanged": True,
                "flp_created": False,
                "desktop_input_used": False,
                "host_invoked": False,
                "font": font,
                "chinese_glyph_available": metrics.inFont("中"),
                "release_qualified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
