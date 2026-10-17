"""Pure discovery coordination and isolation gates, no platform calls."""

import pytest

from suno2flp.integrations import windows_audio_worker as worker
from suno2flp.integrations.windows_audio_worker import collect_observation, require_runtime


class ObservedAPI:
    def __init__(self):
        self.calls = []

    def endpoints(self):
        self.calls.append("endpoints")
        return [dict(id="disconnected", state=8)]

    def default(self, role):
        self.calls.append(role)
        return dict(role=role, hresult=0x80070490, device_id=None)


def test_all_three_roles_preserved_and_absence_not_dropped():
    api = ObservedAPI()
    facts = collect_observation(api)
    assert api.calls == ["endpoints", 0, 1, 2]
    assert facts["endpoints"] == [dict(id="disconnected", state=8)]
    assert len(facts["defaults"]) == 3
    assert facts["finished_ns"] >= facts["started_ns"]


def test_api_failure_does_not_return_an_empty_snapshot():
    class Failing(ObservedAPI):
        def endpoints(self):
            raise OSError("Core Audio unavailable")

    with pytest.raises(OSError, match="Core Audio unavailable"):
        collect_observation(Failing())


def test_nonisolated_import_cannot_execute_native_discovery():
    with pytest.raises(ValueError, match="-I -S -B"):
        require_runtime()


def test_native_interfaces_refuse_non_windows_before_any_platform_call(monkeypatch):
    monkeypatch.setattr(worker.sys, "platform", "linux")

    def refuse_native(*args, **kwargs):
        pytest.fail("Native loader reached on an unsupported platform")

    monkeypatch.setattr(worker.ctypes, "WinDLL", refuse_native, raising=False)
    with pytest.raises(ValueError, match="Windows"):
        worker._NativeAudio()
    with pytest.raises(ValueError, match="Windows"):
        worker._method(None, 2)


def test_native_lifetime_closes_on_discovery_error_without_any_real_api(monkeypatch):
    closed = []

    class SyntheticLifetime:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(worker, "_NativeAudio", SyntheticLifetime)
    with pytest.raises(OSError):
        with worker._native():
            raise OSError("synthetic discovery failure")
    assert closed == [True]
