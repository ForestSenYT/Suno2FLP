"""Explicit prerequisites and exclusive output protection require no model libraries."""

import importlib

import pytest


def api():
    assert importlib.util.find_spec("suno2flp.integrations.yourmt3_backend"), (
        "Missing fixed backend"
    )
    return importlib.import_module("suno2flp.integrations.yourmt3_backend")


def test_missing_fixed_artifacts_fail_without_creating_output(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    output = tmp_path / "new"
    with pytest.raises(FileNotFoundError):
        api().provision_yourmt3_backend(output, source)
    assert not output.exists()


def test_existing_output_is_never_reused_even_if_empty(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        api().provision_yourmt3_backend(output, tmp_path / "absent")
    assert not list(output.iterdir())
