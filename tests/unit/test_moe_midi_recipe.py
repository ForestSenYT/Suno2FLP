"""Fingerprint the actual interpreter target; input/output link guards stay strict."""

from pathlib import Path

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.pipeline import moe_midi


def _recipe_for_alias(monkeypatch, alias: Path, target: Path) -> None:
    monkeypatch.setattr(moe_midi.sys, "executable", str(alias))
    assert moe_midi.moe_midi_recipe().python_executable == capture_stream_input(target)
    # Canonicalizing the running interpreter does not permit linked/traversing assets.
    with pytest.raises(OfflineError, match="offline_path_unsafe"):
        capture_stream_input(alias)


def test_recipe_records_canonical_interpreter_target(tmp_path, monkeypatch):
    target = tmp_path / "fixture-python.exe"
    target.write_bytes(b"Original identity fixture; never executed")
    parent = tmp_path / "existing-parent"
    parent.mkdir()
    _recipe_for_alias(monkeypatch, parent / ".." / target.name, target)


def test_recipe_accepts_symlinked_venv_interpreter(tmp_path, monkeypatch):
    target = tmp_path / "fixture-python.exe"
    target.write_bytes(b"Original identity fixture; never executed")
    alias = tmp_path / "venv-python"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Creating an interpreter symlink requires OS privileges")
    _recipe_for_alias(monkeypatch, alias, target)
