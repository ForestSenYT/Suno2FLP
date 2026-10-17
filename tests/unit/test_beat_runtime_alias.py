"""Resolve the trusted running interpreter; keep asset link guards unchanged."""

import sys
from pathlib import Path

import pytest

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.validator.beat_analysis import beat_recipe
from suno2flp.validator.beat_annotations import beat_scoring_recipe


@pytest.mark.parametrize("recipe", [beat_recipe, beat_scoring_recipe])
def test_interpreter_alias_resolves_without_allowing_linked_assets(
    recipe, tmp_path: Path, monkeypatch
):
    target = tmp_path / "trusted-runtime.bin"
    target.write_bytes(b"original synthetic runtime identity; never executed")
    alias = tmp_path / "python-alias"
    try:
        alias.symlink_to(target)
    except OSError:
        pytest.skip("This user cannot create interpreter-like symbolic links")
    monkeypatch.setattr(sys, "executable", str(alias))
    assert recipe().python_executable == capture_stream_input(target.resolve())
    with pytest.raises(Suno2FLPError, match="Linked/reparse"):
        capture_stream_input(alias)
