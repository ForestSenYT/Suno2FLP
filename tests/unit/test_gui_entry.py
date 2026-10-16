"""The optional GUI entry is lazy; CLI/help work without a Qt install."""

import builtins
import sys


def test_gui_help_does_not_import_qt(capsys):
    import pytest

    from suno2flp.gui.app import main

    before = set(sys.modules)
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    assert "--jobs-root" in capsys.readouterr().out
    assert not any(name.startswith("PySide6") for name in set(sys.modules) - before)


def test_missing_gui_runtime_has_explicit_install_message(monkeypatch, capsys):
    from suno2flp.gui.app import main

    original = builtins.__import__

    def without_qt(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ModuleNotFoundError("No module named PySide6", name="PySide6")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_qt)
    assert main([]) == 2
    message = capsys.readouterr().err
    assert "gui" in message and "uv sync" in message
