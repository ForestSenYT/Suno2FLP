"""Synthetic native replies never require a sound device or a DAW."""

import json
import sys
from pathlib import Path

import pytest

from suno2flp.core.codec_backend import CodecProcessError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.integrations import windows_audio as service


def response(tmp_path):
    system = tmp_path / "Windows" / "System32"
    system.mkdir(parents=True)
    libraries = []
    for name in ("kernel32.dll", "ole32.dll", "MMDevApi.dll"):
        path = system / name
        path.write_bytes(b"Original synthetic API library identity: " + name.encode())
        libraries.append(capture_stream_input(path).model_dump(mode="json"))
    return {
        "protocol": "windows-audio-worker-v1",
        "python_version": service.platform.python_version(),
        "python_abi": f"cp{sys.version_info.major}{sys.version_info.minor}",
        "isolated": True,
        "no_site": True,
        "no_bytecode": True,
        "pointer_bits": 64,
        "windows_directory": str(system.parent),
        "libraries": libraries,
        "stream_activation_calls": 0,
        "device_mutation_calls": 0,
        "facts": {
            "protocol": "windows-render-endpoints-v1",
            "started_ns": 1,
            "finished_ns": 2,
            "os_version": "Original synthetic observation",
            "endpoints": [],
            "defaults": [dict(role=i, hresult=0x80070490, device_id=None) for i in range(3)],
        },
    }


def fake_worker(monkeypatch, payload, callback=None):
    calls = []
    monkeypatch.setattr(service, "_supported_platform", lambda: True)

    def run(arguments, **options):
        calls.append((arguments, options))
        if callback is not None:
            callback()
        return json.dumps(payload).encode(), b""

    monkeypatch.setattr(service, "run_bounded_process", run)
    return calls


def test_real_absence_is_successful_discovery_but_never_host_permission(tmp_path, monkeypatch):
    payload = response(tmp_path)
    calls = fake_worker(monkeypatch, payload)
    result = service.inspect_windows_audio(tmp_path / "observation")
    assert result.assessment.status == "output_absent"
    assert result.execution_allowed is False
    assert result.assessment.host_compatibility == "unverified"
    assert (result.root / "inspection.json").exists()
    assert json.loads((result.root / "stdout.bin").read_bytes()) == payload
    assert calls[0][0][0] == str(Path(sys.executable).resolve())
    assert all(flag in calls[0][0] for flag in ("-I", "-S", "-B"))
    assert calls[0][1]["timeout"] == 15


def test_unsupported_platform_does_not_launch_or_create_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_supported_platform", lambda: False)
    monkeypatch.setattr(service, "run_bounded_process", lambda *a, **kw: pytest.fail("launched"))
    with pytest.raises(ValueError, match="Windows"):
        service.inspect_windows_audio(tmp_path / "attempt")
    assert not (tmp_path / "attempt").exists()


@pytest.mark.parametrize(
    "kind",
    ["default_api_error", "duplicate_role", "injected_library", "false_version", "library_changed"],
)
def test_untrusted_native_reply_or_current_library_cannot_promote_absence(
    tmp_path, monkeypatch, kind
):
    payload = response(tmp_path)
    if kind == "default_api_error":
        payload["facts"]["defaults"][0]["hresult"] = 0x80070005
    if kind == "duplicate_role":
        payload["facts"]["defaults"][2]["role"] = 0
    if kind == "injected_library":
        payload["libraries"][0]["path"] = str(tmp_path / "foreign.dll")
    if kind == "false_version":
        payload["python_version"] = "3.11.0"
    if kind == "library_changed":
        Path(payload["libraries"][0]["path"]).write_bytes(b"changed")
    fake_worker(monkeypatch, payload)
    with pytest.raises((ValueError, OSError, service.Suno2FLPError)):
        service.inspect_windows_audio(tmp_path / "attempt")
    assert not (tmp_path / "attempt" / "inspection.json").exists()
    assert (tmp_path / "attempt" / "failure.json").exists()


def test_worker_failure_keeps_complete_streams_without_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_supported_platform", lambda: True)

    def fail(*args, **kwargs):
        request = json.loads((tmp_path / "attempt" / "request.json").read_bytes())
        assert request["arguments"][0] == str(Path(sys.executable).resolve())
        assert request["timeout_seconds"] == 15
        assert request["max_bytes"] == 4 * 1024**2
        assert request["recipe"]["files"]
        raise CodecProcessError(
            "audio_worker_failed", "API unavailable", b"partial stdout", b"full diagnostic"
        )

    monkeypatch.setattr(service, "run_bounded_process", fail)
    with pytest.raises(CodecProcessError):
        service.inspect_windows_audio(tmp_path / "attempt")
    assert (tmp_path / "attempt" / "stdout.bin").read_bytes() == b"partial stdout"
    assert (tmp_path / "attempt" / "stderr.bin").read_bytes() == b"full diagnostic"
    assert not (tmp_path / "attempt" / "inspection.json").exists()
    failure = json.loads((tmp_path / "attempt" / "failure.json").read_bytes())
    assert failure["request_snapshot"] == json.loads(
        (tmp_path / "attempt" / "request.json").read_bytes()
    )
    assert (
        failure["stdout"]["sha256"]
        == capture_stream_input(tmp_path / "attempt" / "stdout.bin").sha256
    )


def test_existing_output_is_rejected_before_worker(tmp_path, monkeypatch):
    payload = response(tmp_path)
    calls = fake_worker(monkeypatch, payload)
    target = tmp_path / "attempt"
    target.mkdir()
    with pytest.raises(ValueError):
        service.inspect_windows_audio(target)
    assert not calls


def test_cancellation_before_or_after_native_discovery_never_publishes(tmp_path, monkeypatch):
    payload = response(tmp_path)
    calls = fake_worker(monkeypatch, payload)
    with pytest.raises(service.DecodeCancelled):
        service.inspect_windows_audio(tmp_path / "before", should_cancel=lambda: True)
    assert not calls and not (tmp_path / "before").exists()
    cancelled = False

    def cancel():
        nonlocal cancelled
        cancelled = True

    fake_worker(monkeypatch, payload, cancel)
    with pytest.raises(service.DecodeCancelled):
        service.inspect_windows_audio(tmp_path / "after", should_cancel=lambda: cancelled)
    assert not (tmp_path / "after" / "inspection.json").exists()


def test_changed_recipe_during_worker_fails_before_publication(tmp_path, monkeypatch):
    payload = response(tmp_path)
    marker = tmp_path / "synthetic-recipe.py"
    marker.write_bytes(b"original recipe")
    recipe = service.audio_recipe()
    recipe.files.append(capture_stream_input(marker))
    monkeypatch.setattr(service, "audio_recipe", lambda: recipe)
    fake_worker(monkeypatch, payload, lambda: marker.write_bytes(b"changed recipe"))
    with pytest.raises(service.Suno2FLPError):
        service.inspect_windows_audio(tmp_path / "attempt")
    assert not (tmp_path / "attempt" / "inspection.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("isolated", 1),
        ("no_site", 1),
        ("no_bytecode", 1),
        ("pointer_bits", 64.0),
    ],
)
def test_worker_flags_have_exact_types(tmp_path, monkeypatch, field, value):
    payload = response(tmp_path)
    payload[field] = value
    fake_worker(monkeypatch, payload)
    with pytest.raises(ValueError):
        service.inspect_windows_audio(tmp_path / "attempt")


def test_changed_request_cannot_publish_and_original_intent_is_retained(tmp_path, monkeypatch):
    payload = response(tmp_path)
    target = tmp_path / "attempt"

    def change_request():
        request = json.loads((target / "request.json").read_bytes())
        request["timeout_seconds"] = 999
        (target / "request.json").write_text(json.dumps(request), encoding="utf-8")

    fake_worker(monkeypatch, payload, change_request)
    with pytest.raises(service.Suno2FLPError):
        service.inspect_windows_audio(target)
    assert not (target / "inspection.json").exists()
    assert (
        json.loads((target / "failure.json").read_bytes())["request_snapshot"]["timeout_seconds"]
        == 15
    )
