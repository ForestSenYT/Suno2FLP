"""MCP discovery only: lifecycle, paginated tools/list and tool-less peer ping."""

from typing import Literal, Protocol

from pydantic import JsonValue

from suno2flp.core.errors import IntegrationUnavailableError
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.mcp_models import MCP_PROTOCOL_VERSION, McpDiscoveryRecord, McpExchange
from suno2flp.core.models import BackendCapabilities


class McpTransport(Protocol):
    def request(self, method: str, params: dict[str, JsonValue]) -> dict[str, JsonValue]: ...
    def notify(self, method: str, params: dict[str, JsonValue]) -> None: ...
    def close(self) -> None: ...


class DiscoveryController:
    def __init__(
        self,
        transport: McpTransport,
        *,
        evidence_kind: Literal["live_protocol", "synthetic_test"] = "live_protocol",
    ):
        self._transport = transport
        self._kind = evidence_kind
        self._record: McpDiscoveryRecord | None = None
        self._initial: list[McpExchange] = []

    @property
    def record(self) -> McpDiscoveryRecord | None:
        return self._record.model_copy(deep=True) if self._record else None

    def connect(self) -> BackendCapabilities:
        if self._record is not None:
            raise IntegrationUnavailableError("MCP session is already initialized")
        try:
            params: dict[str, JsonValue] = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "suno2flp-discovery", "version": "0.1.0"},
            }
            reply = self._transport.request("initialize", params)
            if reply.get("protocolVersion") != MCP_PROTOCOL_VERSION:
                raise ValueError("Unsupported negotiated MCP version")
            info, capabilities = reply.get("serverInfo"), reply.get("capabilities")
            if (
                not isinstance(info, dict)
                or not isinstance(capabilities, dict)
                or not isinstance(info.get("name"), str)
                or not info["name"]
                or not isinstance(info.get("version"), str)
                or not info["version"]
            ):
                raise ValueError("Missing server identity/capabilities")
            self._transport.notify("notifications/initialized", {})
            self._initial = [
                McpExchange(method="initialize", params=params, result=reply),
                McpExchange(method="notifications/initialized", params={}),
            ]
            self._record = McpDiscoveryRecord(
                evidence_kind=self._kind,
                server_info=info,
                server_capabilities=capabilities,
                tools=[],
                transcript=self._initial,
            )
            return self.capabilities()
        except (ValueError, OSError, RuntimeError, IntegrationUnavailableError) as exc:
            self.disconnect()
            raise IntegrationUnavailableError(f"MCP discovery failed: {exc}") from exc

    def capabilities(self) -> BackendCapabilities:
        if self._record is None:
            raise IntegrationUnavailableError(
                "No initialized MCP session; no cached capability claim"
            )
        try:
            tools: list[dict[str, JsonValue]] = []
            exchanges = list(self._initial)
            names: set[str] = set()
            cursors: set[str] = set()
            cursor = None
            if "tools" in self._record.server_capabilities:
                if not isinstance(self._record.server_capabilities["tools"], dict):
                    raise ValueError("Invalid declared tools capability")
                for _ in range(64):
                    params: dict[str, JsonValue] = {} if cursor is None else {"cursor": cursor}
                    page = self._transport.request("tools/list", params)
                    exchanges.append(McpExchange(method="tools/list", params=params, result=page))
                    definitions = page.get("tools")
                    if not isinstance(definitions, list):
                        raise ValueError("Missing tool inventory")
                    for item in definitions:
                        if not isinstance(item, dict):
                            raise ValueError("Invalid tool definition")
                        name, schema = item.get("name"), item.get("inputSchema")
                        if (
                            not isinstance(name, str)
                            or not name.strip()
                            or name in names
                            or not isinstance(schema, dict)
                            or schema.get("type") != "object"
                        ):
                            raise ValueError(
                                "Missing/duplicate tool name or non-object input schema"
                            )
                        names.add(name)
                        tools.append(item)
                    next_cursor = page.get("nextCursor")
                    if next_cursor is None:
                        break
                    if (
                        not isinstance(next_cursor, str)
                        or not next_cursor
                        or next_cursor in cursors
                    ):
                        raise ValueError("Invalid/repeated pagination cursor")
                    cursors.add(next_cursor)
                    cursor = next_cursor
                else:
                    raise ValueError("Tool inventory exceeds bounded pagination")
            else:
                reply = self._transport.request("ping", {})
                if reply != {}:
                    raise ValueError("Invalid ping response; empty result required")
                exchanges.append(McpExchange(method="ping", params={}, result=reply))
            self._record.tools = tools
            self._record.transcript = exchanges
            return BackendCapabilities(
                backend="mcp-discovery",
                status="available",
                operations=[str(tool["name"]) for tool in tools],
                constraints=[
                    "Protocol inventory only; host unverified",
                    "No tools/call or DAW actions supported",
                    "Tool names, descriptions and annotations are untrusted declarations",
                ],
                evidence=snapshot_sha256(self._record),
            )
        except (ValueError, OSError, RuntimeError, IntegrationUnavailableError) as exc:
            self.disconnect()
            raise IntegrationUnavailableError(f"MCP inventory failed: {exc}") from exc

    def disconnect(self) -> None:
        self._record = None
        self._initial = []
        self._transport.close()
