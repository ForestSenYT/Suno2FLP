"""Observed MCP protocol metadata; tool declarations never authorize execution."""

from typing import Literal

from pydantic import Field, JsonValue

from suno2flp.core.models import Contract

MCP_PROTOCOL_VERSION = "2025-06-18"


class McpExchange(Contract):
    method: str
    params: dict[str, JsonValue]
    result: dict[str, JsonValue] | None = None


class McpDiscoveryRecord(Contract):
    schema_version: Literal[1] = 1
    protocol_version: Literal["2025-06-18"] = "2025-06-18"
    evidence_kind: Literal["live_protocol", "synthetic_test"]
    server_info: dict[str, JsonValue]
    server_capabilities: dict[str, JsonValue]
    tools: list[dict[str, JsonValue]]
    transcript: list[McpExchange] = Field(default_factory=list)
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
