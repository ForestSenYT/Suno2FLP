"""Optional GUI launcher; help and prerequisite errors do not initialize a window."""

import argparse
import os
import sys
from pathlib import Path

from suno2flp.core.errors import OfflineError


def configure_font() -> str:
    """Use installed system fonts; Windows' offscreen plugin has no font discovery."""
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    if os.name == "nt" and not QFontDatabase.families():
        directory = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in ("msyh.ttc", "segoeui.ttf"):
            path = directory / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
    families = QFontDatabase.families()
    chosen = next(
        (
            name
            for name in (
                "Microsoft YaHei UI",
                "Noto Sans CJK SC",
                "WenQuanYi Zen Hei",
                "PingFang SC",
                "DejaVu Sans",
            )
            if name in families
        ),
        families[0] if families else "",
    )
    if chosen:
        QApplication.setFont(QFont(chosen, 10))
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Suno2FLP 本地音频工作台（研发预览）")
    parser.add_argument("--jobs-root", type=Path, default=Path.cwd() / "workspaces/audio-jobs")
    args = parser.parse_args(argv)
    try:
        from PySide6.QtCore import qVersion
        from PySide6.QtWidgets import QApplication
    except (ImportError, OSError) as error:
        print(
            "GUI 依赖不可用。请使用 uv sync --locked --extra gui；"
            f"已安装包使用 suno2flp[gui]。\n{error}",
            file=sys.stderr,
        )
        return 2
    if qVersion() != "6.12.0":
        print("GUI 需要固定的 Qt 6.12.0；请同步 gui 依赖。", file=sys.stderr)
        return 2
    from suno2flp.gui.model import JobActions
    from suno2flp.gui.window import WorkbenchWindow

    try:
        actions = JobActions(args.jobs_root)
    except (OfflineError, OSError, ValueError) as error:
        print(f"任务目录不可用：{error}", file=sys.stderr)
        return 2
    application = QApplication([sys.argv[0]])
    configure_font()
    window = WorkbenchWindow(actions)
    window.show()
    window.refresh_history()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
