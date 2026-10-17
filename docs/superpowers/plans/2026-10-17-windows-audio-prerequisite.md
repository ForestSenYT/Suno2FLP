# Windows audio discovery for the blocked FL26 host lifecycle

> **For agentic workers:** Use superpowers:executing-plans inline with TDD; one fresh whole-branch review after implementation. No implementer agents or repeated unchanged tests.

**Goal:** Expose a genuine, bounded, read-only Windows output-device prerequisite check so the current FL Studio ASIO investigation can identify a missing environment prerequisite before more host launches.

**Architecture:** Core validates complete endpoint/default-role observations. An isolated standard-library worker calls only Core Audio discovery APIs; the adapter records current interpreter/worker/native-library identities and exclusively publishes point-in-time evidence. A thin CLI reports absence distinctly from discovery failure. Neither endpoint discovery nor historical receipts authorize FLP writing or claim host compatibility.

**Tech stack:** Existing Python/Pydantic; Windows x64 application CPython3.11.16/3.14.7; operating-system Core Audio/COM APIs. No new package, driver, downloaded runtime, UI automation or device configuration.

**Spec:** Approved `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md`, M3 of `docs/DELIVERY_ROADMAP.zh-CN.md`, `docs/GITHUB_WORKFLOW.zh-CN.md`. This is a prerequisite/diagnostic component of M3, not its completion.

## Constraints and evidence

- Preserve original media/FLPs/baselines/old experiments; new exclusive files only. No click, keyboard, mouse, audio stream activation, notification subscription, registry/device changes, private upload or FLP encoding.
- Two new60s background cases (MIDI Out/LSD and independent3xOsc) leave invalid80-byte WAVs; a separately owned10s thread snapshot is intentionally terminated, not a successful render. Current Core Audio reports16registered/0active output devices and E_NOTFOUND for all three roles. Missing devices are a demonstrated environmental gap; causality awaits the same baseline after a real device becomes available.
- Native diagnostics remain local, including limited dump/module/stack observations. Raw stack image words are not unwound call stacks or proof of a driver defect. WCT returned only one blocked thread in its synthetic mutex observation, so it does not establish a complete wait chain.
- Observation availability, native API discovery, host lifecycle, routing and musical/release acceptance stay separate. Existing writer/timing/crop/control gates remain unchanged.

## Review focus

1. An API error or malformed/partial snapshot must never become an empty-device success.
2. Defaults must identify active enumerated devices; transient/inconsistent snapshots fail explicitly.
3. Cached point-in-time evidence cannot establish current hardware availability or grant execution.
4. Worker/source/interpreter/library changes, cancellation, existing output and linked paths cannot publish a successful report.
5. Unsupported platforms fail before launching a worker; default tests need no audio device/DAW.

## Task 1: Typed facts and diagnostic assessment

**Files:** `core/windows_audio.py`, `tests/unit/test_windows_audio.py`.
**Interfaces:** `WindowsAudioFacts`, `assess_windows_audio(facts) -> WindowsAudioAssessment`.

- [x] RED: absent output/default, valid output, duplicate IDs/roles, unsupported states/HRESULTs, false defaults and mutated snapshots.
- [x] Preserve complete device IDs/states and all three default-role HRESULTs; retain exact observed interval. Distinguish output_absent/default_absent/output_detected; all remain host-unverified with execution disabled.
- [x] GREEN owning tests; no GUI/host code or fallback.15 tests plus owning Ruff/format/mypy pass; full branch validation follows Task3.

## Task 2: Genuine isolated read-only Windows discovery

**Files:** `integrations/windows_audio_worker.py`, `integrations/windows_audio.py`, owning adapter tests and separately marked opt-in integration test.
**Interface:** `inspect_windows_audio(output: Path, *, should_cancel=None) -> WindowsAudioInspection`.

- [x] RED: non-Windows, isolation/version mismatch, native API failure, malformed output, interpreter/source changes, cancellation and exclusive publication.
- [x] Worker requires -I/-S/-B; only EnumAudioEndpoints/GetDefaultAudioEndpoint/GetId/GetState and COM lifetime APIs. Explicit checked HRESULTs, complete bounded membership, released interfaces/allocated strings and CoUninitialize only for its own initialization.
- [x] Use the existing bounded process runner. Retain actual complete stdout/stderr, recipe and loaded OS-library hashes; reject inconsistent snapshots. Current absence is a valid discovery result, not a launch permission. Save the complete request before launching; failures retain it without a completed result.
- [ ] Actually execute current-source discovery on this machine in new private output. Do not start FL Studio while the needed output is absent; pending user connection is an external prerequisite, not approval inferred from elapsed time.

## Task 3: CLI, documentation and integration gate

**Files:** thin `cli_windows_audio.py` registration, `docs/HOST_READINESS.zh-CN.md`, README/roadmap/integration/dependency/risk documentation, CLI tests.

- [x] RED/GREEN thin command with explicit absent-output versus API-error messages. No fake compatibility/quality status or shared-job success.
- [x] Cite official Microsoft API/state documentation and current pinned FL26 scope. Explain point-in-time validity, physical output prerequisite, unconfirmed causality and untouched old gates. No proprietary logs, registry IDs, dump bytes, projects or backends in Git/packages.
- [ ] After changes stabilize: locked full tests/static checks/build/actual installed CLI, one exact-head independent review, current8CI/latest-main/protection/files/discussions, matching-head squash and actual merged-tree/mainCI verification. No redundant whole-suite/native reruns for unchanged source.

## Native continuation after hardware change

Only after a fresh API observation confirms an available output: use a new byte-identical native reference copy with the same host/arguments; require normal exit, independent whole-WAV validation and complete PCM comparison. Repeatability and separate MIDI Out/LSD evidence follow only if justified. A success narrows this environment failure and never clears untested precise-tempo, routing, crop, resave/reopen or final listening gates.
