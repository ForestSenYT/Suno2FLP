"""The native boundary refuses ordinary Python invocation before any heavy import."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_worker_requires_isolation_before_reading_requests(tmp_path):
    worker = Path(__file__).parents[2] / "src/suno2flp/integrations/yourmt3_worker.py"
    assert worker.exists(), "Missing isolated native boundary"
    result = subprocess.run(
        [sys.executable, str(worker), str(tmp_path / "absent.json")],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert b"requires -I -S -B" in result.stderr
    assert not list(tmp_path.iterdir())


def test_window_journal_retains_short_tail_and_never_overwrites(tmp_path):
    from suno2flp.integrations import yourmt3_worker as worker

    assert hasattr(worker, "write_window_evidence"), "Missing durable window evidence"
    window = dict(index=1, start_frame=32767, valid_frames=1, tokens=[339, 1])
    worker.write_window_evidence(tmp_path, window)
    path = tmp_path / "window-001.json"
    assert json.loads(path.read_bytes()) == window
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        worker.write_window_evidence(tmp_path, window)
    assert path.read_bytes() == before


def test_clean_worker_environment_keeps_compiler_cache_under_attempt(tmp_path, monkeypatch):
    from suno2flp.integrations import yourmt3_worker as worker

    assert hasattr(worker, "configure_environment"), "Missing clean-environment cache contract"
    monkeypatch.setattr(worker.os, "environ", dict(worker.os.environ))
    for name in ("TORCH_HOME", "TORCHINDUCTOR_CACHE_DIR", "TORCHDYNAMO_DISABLE"):
        monkeypatch.delenv(name, raising=False)
    import os

    worker.configure_environment(tmp_path)
    assert Path(os.environ["TORCHINDUCTOR_CACHE_DIR"]).is_relative_to(tmp_path)
    assert os.environ["TORCHDYNAMO_DISABLE"] == "1"


def test_configuration_checks_use_lossless_json_semantics_for_inactive_tuple_geometry():
    from suno2flp.integrations import yourmt3_worker as worker

    assert hasattr(worker, "configurations_match"), "Missing native/JSON configuration contract"
    assert worker.configurations_match(
        {"inactive_geometry": (1, 2), "enabled": False},
        {"enabled": False, "inactive_geometry": [1, 2]},
    )
    assert not worker.configurations_match({"enabled": False}, {"enabled": 0})
    with pytest.raises(ValueError):
        worker.configurations_match({"value": float("nan")}, {"value": 0.0})


def test_native_failure_preserves_complete_diagnostics_and_no_success_name(tmp_path, monkeypatch):
    from suno2flp.core.codec_backend import CodecProcessError
    from suno2flp.core.offline_files import capture_stream_input
    from suno2flp.core.yourmt3 import YourMT3Backend
    from suno2flp.integrations import yourmt3_backend as backend

    root = tmp_path / "backend"
    root.mkdir()
    record = YourMT3Backend(
        root=root,
        python=capture_stream_input(Path(sys.executable)),
        runtime=[],
        artifacts=[],
        adapters=[],
        payload={},
    )
    # Only replace the unavailable native boundary and its already-verified backend.
    monkeypatch.setattr(backend, "read_yourmt3_backend", lambda p: record)

    def fail(*args, **kwargs):
        raise CodecProcessError(
            "audio_worker_failed",
            "original failure",
            b"window0 retained",
            b"complete decoder failure",
        )

    monkeypatch.setattr(backend, "run_bounded_process", fail)
    attempt = tmp_path / "failed-attempt"
    with pytest.raises(CodecProcessError, match="original failure"):
        backend.call_yourmt3_backend(record, attempt, {"mode": "infer"})
    assert (attempt / "stdout.txt").read_bytes() == b"window0 retained"
    assert (attempt / "stderr.txt").read_bytes() == b"complete decoder failure"
    assert not (attempt / "native.json").exists()
    assert not (attempt / "yourmt3.json").exists()
