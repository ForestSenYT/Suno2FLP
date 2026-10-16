# Offline Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Steps use checkbox syntax.

**Goal:** Complete the deterministic, usable offline path and honest acceptance evidence without controlling FL Studio or widening writer gates.

**Architecture:** Reuse track-aware import, optional cleanup and faithful arrangement services. Add independent current-source quality replay, an exclusively new preparation bundle and verifier, transport-only MCP discovery, and explicit PCM render comparison. Existing writer/planning eligibility remains separate.

**Tech Stack:** Python 3.11/3.14, Pydantic, Typer, stdlib streaming/JSON/subprocess, existing locked dependencies.

**Spec:** User's approved overnight prompt; `docs/DEVELOPMENT_ROADMAP.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/ARRANGEMENT.md`, `docs/FL26_WRITER.md`, `docs/FL26_RECORD_CHECKS.zh-CN.md`.

## Global Constraints

- No computer/UI control, actual FL Studio launch, plugin loading or DAW tool calls.
- Original/baseline/GUI references, six probes, original manual records and both backend installations stay unchanged; all private records/binaries stay ignored.
- Ordinary code/tests/docs and empty examples only may be pushed to PR #1; never merge or release.
- Preserve source event order, timing, channels, exact PPQ and full provenance; unknown semantics and host claims remain blocked/unverified.
- Default integrations stay disabled; no large models, vendor source copying or additional dependency is necessary.
- Existing clean `codex/fl26-restricted-writer` task branch is reused for the requested existing PR; no concurrent user edits were present at start.

## Review Focus

1. A forged arrangement/source snapshot or stale original must never pass a current-source replay.
2. Preparation/report output must not overwrite or occupy any input, including missing inputs and linked paths.
3. A partially written preparation directory must never look like a completed run; verifier must distrust edited manifests/statuses.
4. MCP discovery must never issue `tools/call`, accept incomplete pagination or elevate server metadata into host/write authorization.
5. PCM comparisons must retain sample rate/channel/unit meaning, detect truncation and distinguish numerical measurements from audible equivalence.

## Task 1: Current-source arrangement quality

**Files:** new `core/offline_models.py`, `core/offline_files.py`, `validator/arrangement.py`; modify CLI; new unit/integration tests.

**Interfaces:** `audit_arrangement(arrangement, original_imports) -> ArrangementQualityReport`; `verify_arrangement_file(path) -> ArrangementQualityReport`; `capture_input(path) -> (FileIdentity, bytes)` and `verify_inputs(identities)`.

- [x] Write failing tests for original/hash/event/note/map/role changes, cleanup replay, missing source, exact PPQ, file identity and no process/write side effects.
- [x] Implement source reimport, optional cleanup replay and faithful reconstruction, with separate diagnostics and permanently unverified host/write status.
- [x] Expose `verify-arrangement INPUT [--output NEW.json]`, test CLI/no-overwrite and run whole suite/lint/typing.
- [x] Document semantics and commit this independently usable feature.

## Task 2: Reproducible offline preparation

**Files:** new `pipeline/__init__.py`, `pipeline/preparation.py`; extend offline contracts/files; modify CLI; unit/integration tests and guide.

**Interfaces:** `prepare_project(project, destination, *, options=None, mapping_file=None) -> PreparationRun`; `verify_preparation(run_file) -> PreparationRun`.

- [x] Failing tests: MIDI/WAV discovery, optional configured cleanup/roles, multiple PPQ/maps, original preservation, existing/linked/overlapping destination, malformed source/config and changed inputs.
- [x] Generate assets, selected MIDI JSON, arrangement and quality artifacts; create completion manifest last in a new intermediate directory only.
- [x] Reconstruct saved bundles from current originals/config/options; reject tampered artifacts/manifests, incomplete run, stale originals and extra/unlisted artifacts.
- [x] Expose `prepare-project` and `verify-preparation`; installed-CLI synthetic end-to-end verification and commit.

## Task 3: MCP discovery boundary

**Files:** new `core/mcp_models.py`, `daw_controller/discovery.py`, `integrations/mcp_stdio.py`; tests and integration/usage documentation.

**Interfaces:** synchronous request/notify/close transport; `DiscoveryController.connect/capabilities/disconnect` implements the existing protocol; opt-in stdio transport.

- [x] Pin supported protocol `2025-06-18` using official lifecycle/tools/stdio specifications. No tool names or readOnly hints confer execution permission.
- [x] Failing tests: initialization order/version/capabilities, paginated tools, duplicate names/cursors, stale/disconnected state, malformed replies, RPC errors, timeout/EOF and close behavior.
- [x] Implement bounded stdio JSON-RPC with no shell/visible console and discovery-only method allowlist; synthetic original test server only. No actual DAW/backend server is started in this task.
- [x] Document that protocol availability is not a live FL Studio handshake, and actual host/MCP adoption stays pending; commit.

## Task 4: Offline rendered PCM measurements

**Files:** new `core/audio_quality.py`, `validator/renders.py`; CLI, original PCM synthetic tests and docs.

- [x] Failing tests for identical/different PCM, explicit threshold, mismatched sample rate/channels, supported integer widths, empty/truncated WAV, clipping and preserved file hashes.
- [x] Stream aligned uncompressed integer PCM comparison with explicit units; no resampling, alignment inference, perceptual similarity or synthesized audio.
- [x] Expose `compare-renders REFERENCE CANDIDATE [--max-rms-error ...] [--output NEW.json]`; no threshold implies measurements only, not acceptance.
- [x] Verify no source edits/processes and commit. Actual FL Studio rendering/listening remains unavailable.

## Task 5: Final acceptance and distribution evidence

- [x] Publish a phase-by-phase acceptance matrix and Chinese quickstart distinguishing implemented offline features, host-blocked gates and optional future AI/reinterpretation work.
- [x] Fresh 3.11/3.14 tests, Ruff, format, mypy, source/wheel builds, archive privacy audit and installed CLI end-to-end checks including negative cases.
- [x] Recheck original/reference/probe/manual/backend identities using the existing private manifest; write only new local receipts.
- [ ] One independent read-only review, repair important findings with failing-first tests; update PR #1 and fix latest-commit CI until all eight jobs pass.
- [x] Final checkpoint records exact implementation/host boundaries; no whole-project-ready claim without genuine host acceptance.
