"""Opt-in live read-only OS discovery; absence is not an integration failure."""

import os
import platform
import sys
import sysconfig

import pytest

from suno2flp.integrations.windows_audio import inspect_windows_audio


@pytest.mark.external
def test_actual_windows_core_audio_discovery(tmp_path):
    if os.environ.get("SUNO2FLP_TEST_WINDOWS_AUDIO") != "1":
        pytest.skip("Set SUNO2FLP_TEST_WINDOWS_AUDIO=1 for live read-only device discovery")
    if sys.platform != "win32":
        pytest.skip("Core Audio requires Windows")
    if (
        sysconfig.get_platform() != "win-amd64"
        or platform.python_version() not in ("3.11.16", "3.14.7")
        or platform.python_implementation() != "CPython"
        or sysconfig.get_config_var("Py_GIL_DISABLED")
    ):
        pytest.skip("Use ordinary Windows x64 CPython3.11.16/3.14.7 for this live probe")
    result = inspect_windows_audio(tmp_path / "live-discovery")
    assert len(result.native.facts.defaults) == 3
    assert result.native.stream_activation_calls == 0
    assert result.native.device_mutation_calls == 0
    assert result.host_compatibility == "unverified"
    assert result.execution_allowed is False
