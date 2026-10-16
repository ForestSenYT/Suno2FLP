import copy

import pytest

from suno2flp.core.errors import IntegrationUnavailableError


class FixtureTransport:
    """Original in-memory protocol peer; never a real FL Studio connection."""

    def __init__(self):
        self.version = "2025-06-18"
        self.tools = [
            {"name": "fixture_inspect", "inputSchema": {"type": "object"}},
            {
                "name": "fixture_launch",
                "inputSchema": {"type": "object"},
                "annotations": {"readOnlyHint": False},
            },
        ]
        self.closed = False
        self.initialized = False
        self.tool_executed = False
        self.pages = None
        self.index = 0

    def request(self, method, params):
        if method == "initialize":
            return {
                "protocolVersion": self.version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "authored-fixture", "version": "1"},
            }
        if method == "tools/call":
            self.tool_executed = True
            pytest.fail("Discovery invoked a tool")
        assert method == "tools/list" and self.initialized
        if self.pages is not None:
            page = copy.deepcopy(self.pages[min(self.index, len(self.pages) - 1)])
            self.index += 1
            return page
        return {"tools": copy.deepcopy(self.tools)}

    def notify(self, method, params):
        assert method == "notifications/initialized"
        self.initialized = True

    def close(self):
        self.closed = True


def controller(peer):
    from suno2flp.daw_controller.discovery import DiscoveryController

    return DiscoveryController(peer, evidence_kind="synthetic_test")


def test_real_negotiation_flow_preserves_metadata_without_tool_execution():
    peer = FixtureTransport()
    client = controller(peer)
    caps = client.connect()
    assert caps.status == "available" and caps.operations == ["fixture_inspect", "fixture_launch"]
    assert "host unverified" in " ".join(caps.constraints)
    record = client.record
    assert record.evidence_kind == "synthetic_test" and record.host_compatibility == "unverified"
    assert not record.execution_allowed and record.tools[1]["annotations"]["readOnlyHint"] is False
    assert [item.method for item in record.transcript] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
    assert not peer.tool_executed
    client.disconnect()
    assert peer.closed
    with pytest.raises(IntegrationUnavailableError):
        client.capabilities()


def test_capabilities_refresh_inventory_instead_of_reusing_stale_names():
    peer = FixtureTransport()
    client = controller(peer)
    client.connect()
    peer.tools = [{"name": "changed", "inputSchema": {"type": "object"}}]
    assert client.capabilities().operations == ["changed"]
    assert client.record.tools == peer.tools
    assert not peer.tool_executed


def test_paginated_inventory_is_complete():
    peer = FixtureTransport()
    peer.pages = [{"tools": [peer.tools[0]], "nextCursor": "page-2"}, {"tools": [peer.tools[1]]}]
    client = controller(peer)
    assert client.connect().operations == ["fixture_inspect", "fixture_launch"]
    assert len(client.record.tools) == 2


@pytest.mark.parametrize(
    "kind", ["version", "duplicate", "cursor", "schema", "missing_tools", "missing_name"]
)
def test_unverified_or_incomplete_discovery_fails_closed(kind):
    peer = FixtureTransport()
    if kind == "version":
        peer.version = "unsupported"
    elif kind == "duplicate":
        peer.tools.append(copy.deepcopy(peer.tools[0]))
    elif kind == "cursor":
        peer.pages = [{"tools": [], "nextCursor": "same"}]
    elif kind == "schema":
        peer.tools[0]["inputSchema"] = {"type": "string"}
    elif kind == "missing_tools":
        peer.pages = [{}]
    else:
        del peer.tools[0]["name"]
    client = controller(peer)
    with pytest.raises(IntegrationUnavailableError):
        client.connect()
    assert peer.closed and client.record is None and not peer.tool_executed
    with pytest.raises(IntegrationUnavailableError):
        client.capabilities()


def test_disconnect_is_idempotent_and_connect_cannot_reinitialize_a_live_session():
    peer = FixtureTransport()
    client = controller(peer)
    with pytest.raises(IntegrationUnavailableError):
        client.capabilities()
    client.connect()
    with pytest.raises(IntegrationUnavailableError):
        client.connect()
    client.disconnect()
    client.disconnect()
    assert peer.closed


def test_refresh_failure_invalidates_previous_success():
    peer = FixtureTransport()
    client = controller(peer)
    client.connect()
    peer.tools[0]["name"] = ""
    with pytest.raises(IntegrationUnavailableError):
        client.capabilities()
    assert client.record is None and peer.closed


class NoToolsTransport(FixtureTransport):
    def __init__(self):
        super().__init__()
        self.alive = True
        self.ping_result = {}
        self.requests = []

    def request(self, method, params):
        self.requests.append(method)
        if not self.alive:
            raise IntegrationUnavailableError("Synthetic peer disconnected")
        if method == "ping":
            assert self.initialized and params == {}
            return self.ping_result
        assert method == "initialize"
        result = super().request(method, params)
        result["capabilities"] = {}
        return result


def test_no_tools_capability_does_not_fabricate_tool_inventory():
    peer = NoToolsTransport()
    client = controller(peer)
    assert client.connect().operations == []
    assert client.record.tools == [] and not client.record.execution_allowed
    assert [item.method for item in client.record.transcript] == [
        "initialize",
        "notifications/initialized",
        "ping",
    ]
    assert client.capabilities().operations == []
    assert peer.requests == ["initialize", "ping", "ping"]


@pytest.mark.parametrize("failure", ["disconnected", "malformed_ping"])
def test_no_tools_refresh_invalidates_disconnected_or_invalid_peer(failure):
    peer = NoToolsTransport()
    client = controller(peer)
    client.connect()
    if failure == "disconnected":
        peer.alive = False
    else:
        peer.ping_result = {"unexpected": True}
    with pytest.raises(IntegrationUnavailableError):
        client.capabilities()
    assert client.record is None and peer.closed
    with pytest.raises(IntegrationUnavailableError):
        client.capabilities()


def test_returned_record_cannot_mutate_the_connection_evidence():
    client = controller(FixtureTransport())
    client.connect()
    record = client.record
    record.tools.clear()
    assert len(client.record.tools) == 2
