# Noninteractive performance preservation implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Advance the authorized noninteractive MIDI-to-FLP path without silently changing tempo, controls or timing, and identify remaining writer blockers from reproducible evidence.

**Architecture:** Add a source-verified performance compilation step before any FLP encoding. Retain the complete arrangement/source event snapshots and address every event in original track order; compute target positions and elapsed times as exact rational numbers. Assess the existing FL26 scalar representation separately from unknown automation/routing semantics. Reconstruct saved reports from current inputs; neither this report nor its successful verification authorizes FLP writing.

**Tech Stack:** Existing Python/Pydantic/Mido, standard-library Fraction/bisect; no new runtime dependencies.

**Spec:** User's 2026-10-16 request; existing MIDI_IMPORT.md, ARRANGEMENT.md, FL26_WRITER.md and TEMPLATE_INVENTORY.md. Background host runs permitted; no click, keyboard or mouse automation. Unknown compatibility must remain blocked.

## Global constraints

- Preserve all source events, delta/absolute ticks, source-channel identity and provenance.
- No tempo rounding, event omission, PPQ rounding, inferred CC-to-plugin mapping or conversion of program changes to annotations presented as playback preservation.
- Source files, references, six experiment candidates and historical receipts remain unchanged; all runtime evidence stays under ignored `.tools`.
- Existing writer gates remain; a successful background render is not evidence of MIDI import/save, automation semantics or audible acceptance.
- Continue the clean existing PR branch in this checkout, where private baseline paths are already established; no branch reset or private file publication.

## Evidence and decisions

The official toolbar documentation describes fine tempo in 1/1000 BPM. The pinned writer uses that integer scalar. The actual source's effective 374 tempo values are all inexact in that representation; this does not prove all possible FL automation representations are impossible. Pinned PyFLP controller records retain unknown fields and acknowledge uncertain position semantics. They do not establish exact FL26 parameter addressing or interpolation. The prior bounded MIDI CLI experiment produced no output; its root cause remains undetermined.

Consequently no FLP encoder can be honestly enabled by this batch without additional evidence. Implement the lossless compilation boundary and explicit quantified blockers now; retain the goal of an eventual playable FLP. This is a necessary partial deliverable, not a completed song delivery.

## Review focus

- Same-tick controller order and source channel reuse across files must never be merged.
- Equivalent maps at different PPQs, default tempo, changes between note endpoints and conductor/control-only tracks must have exact elapsed time.
- A tempo override or prior cleanup/rounding must not masquerade as preserved source performance.
- Forged reports, changed originals, duplicate JSON keys and missing input paths must fail replay, without allowing an output to occupy an input path.
- Rational target times or zero-duration notes must not become rounded ticks or invented positive durations.

### Task 1: Exact event-level performance compilation and replay

**Files:** new `core/performance.py`, `flp_builder/performance.py`, `tests/unit/test_performance_plan.py`; extend `cli.py` and installed-wheel smoke checks.

**Interfaces:** `plan_performance_file(arrangement_file: Path, *, target_ppq: int | None = None) -> PerformancePlan`; `verify_performance_file(path: Path) -> PerformancePlan`.

- [x] Write synthetic real-SMF tests for two tempos, cross-boundary notes, PPQ conversion, same-tick controls, control-only tracks, reused channels, defaults and integer-milli-BPM exactness.
- [x] Observe tests fail; implement typed rational positions, original-event addresses, track ends, selected notes, tempo representation diagnostics and full input snapshots.
- [x] Reject replay-invalid, overridden, cleaned/rounded performance inputs; do not pretend source preservation if musical edits have been selected.
- [x] Add saved-report mutation/current-input tests and exclusive CLI output tests; verify by rebuilding the complete plan.
- [x] Run focused and full synthetic suites, lint, formatting and strict types.

### Task 2: Real source assessment, documentation and PR

**Files:** new `docs/NONINTERACTIVE_PERFORMANCE.zh-CN.md`; update README, architecture, roadmap, integration/risk notes.

- [x] Run the new planner at source PPQ and 960 against the private prepared song; replay both reports, verify protected hashes and record precise counts. Do not generate a blocked FLP.
- [x] Document validated CLI rendering separately from unverified MIDI-to-FLP/save/automation, and document source tempo precision and control routing requirements.
- [ ] Obtain one fresh review, fix important findings with regressions, run required checks, inspect public file inventory, commit/push PR #1 and verify CI for the exact new SHA.

## Local verification checkpoint

32 original unit cases, expanded installed-wheel smoke, full suite 774 passed / 19 explicit skips; Ruff/format and strict mypy 71 modules passed. One important review finding (source changes during report publication) was reproduced RED then fixed GREEN. Both private 480/960 PPQ plans replay from current sources, with all prior protected identities unchanged. Archive inventories exclude private media/backend/cache files. Remaining publication/CI status is recorded on PR #1; real-song FLP generation remains blocked, not completed.
