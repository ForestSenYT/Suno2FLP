"""Opt-in inspection of actual built archives before publication."""

import json
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
        pin_name = "suno2flp/integrations/yourmt3_moe_pins.json"
        assert pin_name in members, "Installed MoE profile metadata is missing"
        pins = json.loads(archive.read(pin_name))
        assert len(pins["state"]) == 655
        assert pins["generation_policy"]["retry_max_tokens"] == 1024
    with tarfile.open(sources[0]) as archive:
        members += archive.getnames()
        matching = [m for m in archive.getmembers() if m.name.endswith("/src/" + pin_name)]
        assert len(matching) == 1 and matching[0].size < 1024**2
        stream = archive.extractfile(matching[0])
        assert stream is not None
        assert json.loads(stream.read()) == pins
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
