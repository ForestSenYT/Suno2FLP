# Discovery-only MCP boundary

This implements the existing `DAWController` connection/capability/disconnect shape,
not live FL Studio control. Nothing starts on import, project initialization or
preparation. Default integrations remain `none`; no real MCP server, FL Studio or
plugin was launched to validate this slice. Original synthetic peers are explicitly
labeled `evidence_kind: synthetic_test`, never real-host evidence.

## Protocol scope and primary sources

The supported profile is pinned to **2025-06-18**. Initialization negotiates this
exact version, records server information/capabilities and sends the initialized
notification before listing tools. Other negotiated versions fail closed. Sources:
[official lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle),
[tool inventory/pagination](https://modelcontextprotocol.io/specification/2025-06-18/server/tools),
[stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports).

The original implementation adds no SDK dependency and incorporates no upstream
parser/server source. Tool names, schemas, descriptions, annotations and initialization
instructions are recorded as untrusted data. They are never executed or treated as
permissions, even if `readOnlyHint` is true. This supported profile is not a claim that
any separately installed backend negotiates it; that actual adoption remains pending.

## Explicit Python API

`DiscoveryController(transport, evidence_kind="live_protocol")` consumes a synchronous
`McpTransport` with `request(method, params)`, `notify(method, params)` and `close()`.
`connect()` negotiates and discovers; `capabilities()` refreshes the current complete
tool list rather than reusing cached names; `disconnect()` clears evidence and closes.
Use a new controller/transport for a new process session. `record` returns a deep copy.
Only successful protocol interaction produces `BackendCapabilities.status=available`.
That means protocol availability, **not** a connected/compatible FL Studio host.

Every record retains raw initialization and paginated tool results, server identity,
full tool definitions and a canonical metadata fingerprint. It always reports host
unverified, writer blocked and execution false. Duplicate names, malformed definitions,
repeated cursors and more than 64 pages fail rather than publish a partial inventory.
Failures invalidate the previous record; disconnected sessions have no cached claims.

`StdioMcpTransport(argv, timeout=10, cwd=None)` is explicitly opt-in and starts the
caller-selected local child process. **Use only a startup command whose behavior has
already been audited and authorized.** This is not an operating-system sandbox and
cannot make arbitrary server startup safe. No such real command is configured or run
in this slice; under the user's computer-control pause, only authored test peers run.
No CLI command launches a real MCP backend.

The transport uses argv without a shell, hides the Windows child console, separates
stderr from UTF-8 newline JSON-RPC stdout, checks request IDs/errors/duplicate keys,
and bounds frames, queues, intervening messages and request/write waits. Peer ping is
answered; unsupported server requests fail. Client requests are limited to initialize,
tools/list and ping, plus lifecycle/cancellation notifications. `tools/call`, resource,
prompt, sampling and elicitation operations are not exposed. The API is synchronous;
serialize access and do not share one transport between concurrent callers.

Closing first signals EOF where possible, then terminates/kills only the owned child
after bounded waits. Descendant processes are not managed. Reader/writer threads are
daemonized; streams still owned by a blocked reader/writer are not synchronously closed
in a way that could deadlock teardown. The scope is trusted local, audited servers,
not hostile process-tree isolation or production-wide resource containment.

## Validation and remaining host work

Tests cover version/state/initialization, pagination, stale/invalidated inventories,
metadata preservation, EOF, RPC error, malformed JSON, mismatched ID, timeout and close.
A separately launched **original test peer** exercises actual stdio framing and logs
that only lifecycle/discovery messages were received; it provides no FL Studio tools.
This is transport evidence, not a genuine installed-backend or DAW handshake.

Real backend adoption still requires an explicitly authorized startup command,
version/runtime/license identity, genuine negotiated inventory and independently
verified host behavior. DAW mutation, playback, rendering, recoverable edits and audible
acceptance remain separate future/host gates. This component cannot authorize them or
change the restricted native writer's policy.
