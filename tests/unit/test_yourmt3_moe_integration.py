"""Offline profile identity, explicit boundaries and failure publication."""

import importlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner


def api(name):
    full = "suno2flp." + name
    assert importlib.util.find_spec(full), "Missing separate MoE integration"
    return importlib.import_module(full)


def test_moe_exact_pins_do_not_relabel_single():
    from suno2flp.integrations import yourmt3_source as source

    assert hasattr(source, "load_yourmt3_moe_pins"), "Missing fixed MoE recipe"
    value = source.load_yourmt3_moe_pins()
    assert len(value.state) == 655 and len(value.wheels) == 59
    assert value.profile != source.load_yourmt3_pins().profile
    assert value.files[-1].size_bytes == 561544628
    assert (
        value.files[-1].sha256 == "ae38e415c79efd5592dcb9b658cdb99ddb11d4c4e1eaa364cab04a052473fc25"
    )
    encoder = value.configuration["model"]["encoder"]["perceiver-tf"]
    assert encoder["rope_partial_pe"] is True
    assert encoder["rotary_partial_pe"] is False
    assert encoder["layer_norm_type"] == "layer_norm"
    assert {role.channel for role in value.program_channels.values()} == set(range(13))
    assert value.generation_policy.retry_max_tokens == 1024


def test_moe_missing_artifacts_and_existing_outputs_never_start(tmp_path):
    backend = api("integrations.yourmt3_moe_backend")
    empty = tmp_path / "artifacts"
    empty.mkdir()
    output = tmp_path / "new"
    with pytest.raises(FileNotFoundError):
        backend.provision_yourmt3_moe_backend(output, empty)
    assert not output.exists()
    output.mkdir()
    with pytest.raises(FileExistsError):
        backend.provision_yourmt3_moe_backend(output, empty)
    assert list(output.iterdir()) == []


def test_moe_pipeline_old_output_and_bad_source_stay_unchanged(tmp_path):
    pipeline = api("pipeline.yourmt3_moe")
    output = tmp_path / "old"
    output.mkdir()
    keep = output / "keep.txt"
    keep.write_bytes(b"immutable")
    with pytest.raises(FileExistsError):
        pipeline.transcribe_yourmt3_moe(tmp_path / "missing", tmp_path / "backend", output, [])
    assert keep.read_bytes() == b"immutable" and list(output.iterdir()) == [keep]
    bad = tmp_path / "bad.json"
    bad.write_bytes(b'{"unsupported":true}')
    with pytest.raises(ValueError):
        pipeline.transcribe_yourmt3_moe(bad, tmp_path / "backend", tmp_path / "new", [])
    assert bad.read_bytes() == b'{"unsupported":true}'
    assert not (tmp_path / "new").exists()


def test_moe_integral_counters_and_exact_rope_override():
    worker = api("integrations.yourmt3_moe_worker")
    assert worker.integer_error_counts({"occurrences": 2.0}) == {"occurrences": 2}
    for value in [0.5, -1, True, "1", float("nan"), float("inf")]:
        with pytest.raises(ValueError):
            worker.integer_error_counts({"occurrences": value})
    audio, model, shared = (
        {"old": 1},
        {"encoder": {"perceiver-tf": {"rotary_partial_pe": False}}},
        {"TOKENIZER": {}},
    )
    actual = worker.moe_configuration(audio, model, shared)
    assert actual[1]["encoder"]["perceiver-tf"]["rope_partial_pe"] is True
    assert actual[1]["encoder"]["perceiver-tf"]["rotary_partial_pe"] is False
    assert "rope_partial_pe" not in model["encoder"]["perceiver-tf"]


def test_moe_worker_isolation_precedes_request_or_model_import(tmp_path):
    worker = Path(__file__).parents[2] / "src/suno2flp/integrations/yourmt3_moe_worker.py"
    assert worker.exists(), "Missing isolated MoE worker"
    result = subprocess.run(
        [sys.executable, str(worker), str(tmp_path / "absent.json")],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0 and b"requires -I -S -B" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_moe_native_failure_retains_complete_diagnostics(tmp_path, monkeypatch):
    backend = api("integrations.yourmt3_moe_backend")
    from suno2flp.core.codec_backend import CodecProcessError
    from suno2flp.core.offline_files import capture_stream_input
    from suno2flp.core.yourmt3_moe import YourMT3MoEBackend

    root = tmp_path / "backend"
    root.mkdir()
    record = YourMT3MoEBackend(
        root=root,
        python=capture_stream_input(Path(sys.executable).resolve(strict=True)),
        runtime=[],
        artifacts=[],
        adapters=[],
        payload={},
    )
    monkeypatch.setattr(backend, "read_yourmt3_moe_backend", lambda root: record)

    def fail(*args, **kwargs):
        raise CodecProcessError(
            "audio_worker_failed", "native failure", b"all partial windows", b"full stderr"
        )

    monkeypatch.setattr(backend, "run_bounded_process", fail)
    attempt = tmp_path / "attempt"
    with pytest.raises(CodecProcessError, match="native failure"):
        backend.call_yourmt3_moe_backend(record, attempt, {"mode": "infer"})
    assert (attempt / "stdout.txt").read_bytes() == b"all partial windows"
    assert (attempt / "stderr.txt").read_bytes() == b"full stderr"
    assert not (attempt / "native.json").exists()


def test_moe_help_is_inert_without_models():
    from suno2flp.cli import app

    for name in ["prepare-yourmt3-moe-backend", "transcribe-yourmt3-moe", "verify-yourmt3-moe"]:
        result = CliRunner().invoke(app, [name, "--help"], color=False)
        assert result.exit_code == 0, result.output
        assert "--help" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)
