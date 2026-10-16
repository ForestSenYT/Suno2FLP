# Isolated FL Studio MCP Adoption Audit Plan

> **For agentic workers:** Use superpowers:executing-plans inline for this operational audit. Steps use checkboxes.

**Goal:** Audit fixed MCP backends and obtain genuine initialization/tool-inventory evidence without touching FL Studio or any protected project.

**Architecture:** Reuse the existing discovery-only controller/stdio transport. Provision unmodified pinned upstream servers in a new ignored audit directory; keep source/runtime/dependency identities and raw protocol records local. Separate server protocol availability from host acceptance.

**Tech Stack:** Existing Python 3.11 discovery client; isolated .NET 10 Music2DAW MCP and, only if startup is host-inert, an isolated Python live-bridge candidate.

**Spec:** User authorization on 2026-10-16; `AGENTS.md`, `docs/MCP_DISCOVERY.md`, `docs/INTEGRATIONS.md`, `docs/FL26_RECORD_CHECKS.zh-CN.md`.

## Global Constraints

- No FL Studio launch, UI control, MIDI/bridge calls, playback, project opening/saving or FLP writes.
- No `tools/call`, resource reads, prompts or subscriptions. Only initialize, initialized notification, tools/list and protocol ping.
- Original FLPs, references, six probes, old forms/manifests and existing backend installations remain unchanged.
- All upstream sources, binaries, packages, raw discovery data and private receipts stay ignored/local; public documentation contains generic facts only.
- Preserve protocol `2025-06-18`; unsupported negotiation is an explicit blocker, not an inferred success.
- No optional audio/ML stack, virtual MIDI driver/controller installation, global integration configuration or automatic activation.

## Review Focus

1. Import/static initialization/registration must not contact or mutate the host before discovery.
2. Tool descriptions/annotations are untrusted declarations; discovery must never invoke them.
3. Genuine server inventory must be distinguished from synthetic tests and actual host/bridge readiness.
4. Exact source revisions, dependency locks, licenses, runtime and process lifecycle must remain reproducible.
5. Private data and protected-input identities must remain unchanged through setup, discovery and teardown.

## Task 1: Audit and isolate sources

- [x] Recheck the 73 protected references; capture only new receipts in `.tools/flstudio-mcp-audit-v1`.
- [x] Audit Music2DAW `6def9463d6fa8636bbc81010581318a39c47d3c4` and live candidate `e6eff37e45a076098ed81ee4e50fb7bf08aef11a`: notices, metadata, startup/import/registration and side effects.
- [x] Materialize exact sources in new private directories; verify source-tree/file identities. Reject unsafe automatic host activity.

## Task 2: Provision and discover

- [x] Build only Music2DAW MCP under isolated CLI-home/NuGet/cache/output directories, recording SDK/runtime and resolved dependency locks/licenses.
- [x] For the live candidate, install only ordinary required dependencies into a new locked Python environment if startup audit permits. No bridge/controller/driver setup or host ping.
- [x] Run existing synthetic MCP lifecycle/negative tests. Expected: all pass, no external backend or host dependency.
- [x] Start each approved actual server with audited argv, perform real initialization and complete tool listing/refresh, then disconnect. Preserve raw records, hashes, exit/lifecycle evidence; tools/call count must be zero.

## Task 3: Evidence and scope

- [x] Classify actual advertised tools against every manual acceptance stage; missing/mutating/host-dependent operations remain blocked.
- [x] Update public integration/dependency/risk/scope documentation without private payloads or runtime activation.
- [x] Run required repository checks and packaging privacy verification as appropriate; final read-only review and protected-reference recheck.
- [x] Report exact connected scope, runtime/license/pins, genuine versus pending evidence and remaining host/manual blockers in Chinese.

## Completion evidence

Two actual servers negotiated2025-06-18, returned5/67 tools with identical refreshed
inventories, passed protocol ping and exited0; tools/call and resource reads stayed0.
All73 protected refs remain valid and54 host stages pending. Existing26 MCP contract
tests plus full742 passed/19 skipped, Ruff/format/mypy69, package privacy and installed
wheel smoke passed. One independent read-only review reported no findings. Actual
host/bridge readiness, native-FFI containment, legal redistribution compliance and
process guarantees beyond recorded owned lifecycles remain unverified.
