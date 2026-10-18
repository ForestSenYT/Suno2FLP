"""Opt-in inspection of actual built archives before publication."""

import os
import tarfile
import zipfile
from pathlib import Path

import pytest


@pytest.mark.external
def test_built_archives_exclude_private_workspaces_assets_and_model_payloads():
    value = os.environ.get("SUNO2FLP_PACKAGE_ARTIFACTS")
    if not value:
        pytest.skip("Set SUNO2FLP_PACKAGE_ARTIFACTS to new local wheel/sdist outputs")
    root = Path(value)
    wheels = list(root.glob("*.whl"))
    sources = list(root.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "Both new distribution archives are required"
    with zipfile.ZipFile(wheels[0]) as archive:
        members = archive.namelist()
    with tarfile.open(sources[0]) as archive:
        members += archive.getnames()
    for name in members:
        assert not {
            ".tools",
            ".superpowers",
            ".venv",
            ".uv-cache",
            "workspaces",
            "intermediate",
            "output",
        } & set(name.split("/")), name
        assert not name.lower().endswith(
            (".flp", ".wav", ".mid", ".midi", ".ckpt", ".onnx", ".dll", ".pyd")
        ), name
