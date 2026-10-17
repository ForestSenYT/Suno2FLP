"""Worker startup controls are exercised without importing native packages."""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_native_environment_refuses_ambient_sites_and_disables_plugins(tmp_path, monkeypatch):
    worker = importlib.import_module("suno2flp.integrations.spleeter_worker")
    environment = {
        "TF_USE_MODULAR_FILESYSTEM": "1",
        "TF_PLUGGABLE_DEVICE_LIBRARY_PATH": "untrusted.dll",
        "CUDA_VISIBLE_DEVICES": "0",
        "TF_ENABLE_ONEDNN_OPTS": "1",
    }
    monkeypatch.setattr(worker.os, "environ", environment)
    worker.isolate_environment(tmp_path / "packages", tmp_path)
    assert environment["TF_USE_MODULAR_FILESYSTEM"] == "0"
    assert "TF_PLUGGABLE_DEVICE_LIBRARY_PATH" not in environment
    assert environment["CUDA_VISIBLE_DEVICES"] == "-1"
    assert environment["TF_NUM_INTRAOP_THREADS"] == "8"
    assert environment["TF_NUM_INTEROP_THREADS"] == "1"
    with pytest.raises(ValueError, match="site-packages"):
        worker.isolate_environment(tmp_path / "site-packages/packages", tmp_path)


def test_unknown_worker_operation_fails_without_loading_model_packages(tmp_path):
    worker = importlib.import_module("suno2flp.integrations.spleeter_worker")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"operation": "write-flp", "packages": str(tmp_path)}))
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(Path(worker.__file__)), str(request)],
        capture_output=True,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode != 0 and b"Unsupported" in result.stderr
    assert not (tmp_path / "result.json").exists()
