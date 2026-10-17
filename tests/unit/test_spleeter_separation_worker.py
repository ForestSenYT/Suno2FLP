"""Native worker startup and exact PCM headers are tested without loading a model."""

import importlib
import json
import struct
import subprocess
import sys

import pytest


def worker():
    return importlib.import_module("suno2flp.integrations.spleeter_separation_worker")


def source_wave(path, frames=3, rate=48000, channels=1):
    size = frames * channels * 8
    header = struct.pack(
        "<4sI4s4sIHHIIHHH4sII4sI",
        b"RIFF",
        50 + size,
        b"WAVE",
        b"fmt ",
        18,
        3,
        channels,
        rate,
        rate * channels * 8,
        channels * 8,
        64,
        0,
        b"fact",
        4,
        frames,
        b"data",
        size,
    )
    path.write_bytes(header + b"\0" * size)


@pytest.mark.parametrize(
    "mutation",
    [None, "operation", "extra", "frames", "rate", "channels", "header", "truncated", "bool"],
)
def test_worker_request_preserves_the_declared_complete_pcm(tmp_path, mutation):
    module = worker()
    pcm = tmp_path / "decoded.wav"
    source_wave(pcm)
    request = dict(
        operation="separate",
        packages=str(tmp_path / "packages"),
        pcm=str(pcm),
        frames=3,
        sample_rate=48000,
        channels=1,
    )
    if mutation == "operation":
        request["operation"] = "write-flp"
    elif mutation == "extra":
        request["download_model"] = True
    elif mutation in ("frames", "rate", "channels"):
        field = "sample_rate" if mutation == "rate" else mutation
        request[field] = {"frames": 4, "rate": 44100, "channels": 2}[mutation]
    elif mutation == "header":
        pcm.write_bytes(b"RIFX" + pcm.read_bytes()[4:])
    elif mutation == "truncated":
        pcm.write_bytes(pcm.read_bytes()[:-8])
    elif mutation == "bool":
        request["channels"] = True
    if mutation:
        with pytest.raises((ValueError, OSError)):
            module.validate_request(request)
    else:
        packages, source, frames, rate, channels = module.validate_request(request)
        assert str(packages) == request["packages"] and source == pcm
        assert (frames, rate, channels) == (3, 48000, 1)
    assert "tensorflow" not in sys.modules


def test_unknown_operation_refuses_before_loading_native_packages(tmp_path):
    module = worker()
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"operation": "write-flp"}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", module.__file__, str(request)],
        capture_output=True,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode != 0 and b"Unsupported" in result.stderr
    assert not (tmp_path / "result.json").exists()


def test_partitioned_graph_preserves_isolated_startup_requirement(tmp_path):
    module = importlib.import_module("suno2flp.integrations.spleeter_worker")
    with pytest.raises(ValueError, match="-I -S -B"):
        module.native(tmp_path / "packages", tmp_path, partitioned=True)


def test_native_process_memory_is_observed_or_explicitly_unsupported():
    module = importlib.import_module("suno2flp.integrations.process_metrics")
    if sys.platform == "win32":
        working_set, commit = module.peak_process_memory()
        assert working_set > 0 and commit > 0
    else:
        with pytest.raises(ValueError, match="Windows"):
            module.peak_process_memory()
