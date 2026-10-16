# Explicit MIDI routing evidence implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline and one fresh final review.

**Goal:** Preserve source events and coordinates while making every input/channel destination explicit and testing FL26 tempo/program hypotheses without UI input.

**Architecture:** Add a read-only routing plan over the independently replayed encoding assessment. A strict JSON binding document names receiver, port and unchanged MIDI channel for every source group. Coverage, aliases and receiver/port collisions fail before publication; full control occurrences and source identities survive. No writer gate changes or vendor state in public code.

**Tech stack:** Existing Python/Pydantic/Fraction/pytest; pinned local FL26 background CLI for private experiments only.

**Spec:** User continuation request and [performance preservation contract](../../NONINTERACTIVE_PERFORMANCE.zh-CN.md).

## Constraints and review focus

- Only new experiment files; hash and preserve old inputs, baselines, probes and filled records.
- No clicks, keyboard/mouse input, settings edits, private uploads, source tick shifts or tempo rounding.
- Duplicate programs and terminal controls remain separate, including same-channel cross-track occurrences.
- Destination declarations prove no receiver delivery; tempo, template and listening gates remain blocked.
- Reject missing/extra/duplicate selectors, destination collisions and hidden channel remapping.
- Saved reports must recompute current configuration and all current sources, not trust edited flags.

## Tasks

- [x] Background evidence: test selected plugin parameters with MIDI and audio controls; compare factory tempo-clip structure against fixed two-note reference without changing note positions. Retain unsuccessful hypotheses and qualify scope.
- [x] RED/GREEN: `core/midi_routing.py`, `flp_builder/midi_routing.py`, `tests/unit/test_midi_routing.py`. Implement `plan_midi_routing_file(performance_file, bindings_file)` and `verify_midi_routing_file(path)` with complete coverage, preserved messages/timing and before/after identities. Add CLI commands and installed workflow checks.
- [x] Bind all 63 real-source groups in a new private report, verify replay and source preservation. Do not generate the song while any required evidence remains missing.
- [x] Update architecture, roadmap and Chinese evidence documentation; run full checks/build/install and one fresh review. Public-only publication and exact-head CI are tracked by PR #1's commit and check results.
- [ ] Real-song FLP generation, host render and delivery acceptance: blocked pending exact tempo, receiver delivery, stable host lifecycle and pre-existing template/listening evidence.

## Decisions

- Continue the existing PR branch and existing runtime. User authorization covers new isolated background probes; there is no permission gap.
- Official tempo fine tuning is documented in 0.001 BPM units. This does not prove that every possible automation path shares that limit; alternate paths need direct evidence.
- A selected MIDI Out plugin parameter changed both exported program messages and audio. Other parameter/state hypotheses remain hypotheses until the relevant observations support them.

## Verification and review ledger

- RED observed for missing routing implementation and installed-smoke replay result; GREEN
  followed implementation. New synthetic routing cases: 22. Full suite: 845 passed,
  19 explicitly skipped. Ruff, formatting, mypy, build and installed-wheel lifecycle passed.
- Real report independently replayed: 63 source groups, 66 program changes and 66 CC7
  occurrences, with receiver delivery unverified and execution blocked.
- Host audit: 93 new copies, 83 launches, 80 completed, 3 timeouts. Route batch:
  57 completed, 1 failed, 5 unexecuted; one fresh-copy retry and a known-positive
  baseline also timed out. No later launches. No claims about all 63 receiving correctly.
- Completed route exports contain 120/120 matching control occurrences when channel is
  ignored and 16/120 when it is included. Export overlap cannot acknowledge delivery.
- All 568 protected files and 8 runtime identities stayed unchanged. Package inventories
  exclude private assets and backend files. No UI input was used.
- One fresh independent review found no critical, important or minor code findings and
  approved this read-only increment. Reviewer independently replayed the real routing
  report; the parent performed the full suite, build, installed smoke and evidence audit.
- Reviewer-declined host/audio claims remain limitations: selected PCM observations do
  not establish every program, arbitrary scheduling boundary or channel isolation;
  exact tempo and existing manual crop/flag/reopen/listening evidence remain unverified.
  CI and publication status must be checked against the actual PR head, not inferred
  from the review or a previous commit.
