import json
import sys
from pathlib import Path

import pytest

from suno2flp.core.errors import IntegrationUnavailableError


def transport(tmp_path, mode="normal", timeout=5):
    from suno2flp.integrations.mcp_stdio import StdioMcpTransport

    peer = Path(__file__).resolve().parents[1] / "fixtures/mcp_peer.py"
    return StdioMcpTransport(
        [sys.executable, "-u", str(peer), mode, str(tmp_path / "wire.jsonl")],
        timeout=timeout,
        cwd=tmp_path,
    )


def test_stdio_peer_negotiates_without_any_daw_or_tool_calls(tmp_path):
    from suno2flp.daw_controller.discovery import DiscoveryController

    wire = transport(tmp_path)
    client = DiscoveryController(wire, evidence_kind="synthetic_test")
    assert client.connect().operations == ["fixture_only"]
    assert client.capabilities().operations == ["fixture_only"]
    client.disconnect()
    assert wire.closed
    messages = [
        json.loads(line)
        for line in (tmp_path / "wire.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["method"] for item in messages] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/list",
    ]


def test_toolless_stdio_peer_exit_invalidates_discovery(tmp_path):
    from suno2flp.daw_controller.discovery import DiscoveryController

    wire = transport(tmp_path, "no-tools-exit")
    client = DiscoveryController(wire, evidence_kind="synthetic_test")
    try:
        assert client.connect().operations == []
        assert client.record.transcript[-1].method == "ping"
        with pytest.raises(IntegrationUnavailableError):
            client.capabilities()
        assert client.record is None and wire.closed
    finally:
        client.disconnect()


@pytest.mark.parametrize("mode", ["malformed", "wrong-id", "error", "eof", "hang"])
def test_stdio_failures_close_owned_process_and_never_report_connection(tmp_path, mode):
    from suno2flp.daw_controller.discovery import DiscoveryController

    wire = transport(tmp_path, mode, timeout=0.5 if mode == "hang" else 5)
    client = DiscoveryController(wire, evidence_kind="synthetic_test")
    with pytest.raises(IntegrationUnavailableError):
        client.connect()
    assert wire.closed and client.record is None


def test_transport_does_not_offer_tool_execution_even_if_called_directly(tmp_path):
    wire = transport(tmp_path)
    with pytest.raises(IntegrationUnavailableError):
        wire.request("tools/call", {"name": "launch_fl_studio_project", "arguments": {}})
    wire.close()
    assert wire.closed
    if (tmp_path / "wire.jsonl").exists():
        assert "tools/call" not in (tmp_path / "wire.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("method", ["resources/read", "sampling/createMessage", "prompts/get"])
def test_other_protocol_surfaces_are_not_implicitly_enabled(tmp_path, method):
    wire = transport(tmp_path)
    try:
        with pytest.raises(IntegrationUnavailableError):
            wire.request(method, {})
    finally:
        wire.close()
