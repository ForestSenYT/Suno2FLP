# MIDI round-trip evidence implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one fresh final review.

**Goal:** Detect changed event streams and exact clocks in independently exported MIDI, while narrowing FL26 timing/routing unknowns through new private background probes.

**Architecture:** Add a process-free validator and core evidence models. Compare complete decoded events with rational beat positions; separately check ordered tracks and piecewise exact tempo clocks. Preserve both imports and current-file identities. No existing writer or eligibility rule changes.

**Tech stack:** Existing Python, Pydantic, mido, Fraction, pytest; fixed local FL26 CLI only for authorized private experiments.

**Spec:** User request and [preservation contract](../../NONINTERACTIVE_PERFORMANCE.zh-CN.md).

## Constraints / review focus

- Only new experiment/output files; all originals, baselines and previous copies immutable.
- No UI input, global settings changes, private uploads or new dependencies.
- Source ticks are never compensated. Candidate field changes are private hypotheses, not writer recipes.
- Duplicate controls, same-tick order, cross-track relocation and unknown meta/SysEx must remain visible.
- Same notes do not imply the same clock; tempo conflicts make clock comparison unverified.
- A successful process exit or equal decoded MIDI cannot attest a receiver, audio timing or host compatibility.
- Current-source/report tampering and publication races must fail; reports cannot authorize execution.

## Tasks

- [x] New private probes: qualify the render environment, test +/- one-tick control boundaries at 96/960 PPQ, obtain host MIDI exports, and test an isolated factory receiver candidate. Pin inputs, executable and outputs; keep all unsuccessful attempts.
- [x] TDD `compare-midi-events`: create `core/midi_comparison.py` and `validator/midi_comparison.py`. Match identical beat/message occurrences without collapsing duplicates; report missing/extra addresses, ordered track equality, exact clock differences and all input snapshots. Add `verify-midi-comparison` current-file replay. CLI comparisons return nonzero when different, but still publish new evidence.
- [x] Test explicit PPQ equivalence, one-tick tempo shifts, extra startup/tail controls, program/channel changes, same-tick order, unknown meta deltas, SysEx, map conflicts, defaults, no-output files, stale/tampered reports and exclusive publication.
- [x] Run the validator on private host exports and document only established observations. Run full tests, lint/format/types, installed CLI smoke and distribution privacy checks. Complete one fresh final review. Record publication and exact-head CI results in PR #1 after pushing public changes.

## Rulings / ledger

- Continue the existing dedicated PR branch; no new checkout or backend installation is needed.
- User explicitly authorized this continuation and background runs; no redundant plan approval is required. Evidence directory is retained for provenance.
- Sandboxed processes exited zero without artifacts, including the known WAV baseline. Fresh unsandboxed background baseline produced a valid WAV. These no-output runs are environmental failures, not proof that MIDI export is unsupported.
- Joined single-file `/M"path.flp"` produced MIDI. Spaced `/M "path.flp"` and tested directory forms did not. Require actual output checks.
- Minus-one-tick probes aligned selected audio onsets, but exported MIDI retained the shifted tick. This falsifies treating the shift as a lossless representation change.
- Initial factory receiver candidates rendered silent WAVs; silence alone did not establish port/state meanings. Later matched-port controls (1→1 and 2→2) produced identical non-silent PCM, while 1→2 was entirely silent. Selected native volume changes suppressed the second note. This establishes only the tested one-sender/one-receiver paths and selected values, not full source/program/control routing. No gates are relaxed.
- The comparator has 19 synthetic cases, including invalid tempos and capture/import identity races. The full local suite passed 823 tests with 19 explicit skips. Fresh independent review found no critical or important implementation issue; its two minor documentation clarifications were incorporated. Lint, format, strict types, source/wheel builds and the installed-wheel offline workflow passed. Distribution inventories excluded private projects, media, plugins and backend files. Exact-head CI is recorded in PR #1 after publication.
