# Estimated MIDI preview implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce editable, source-bound MIDI candidates from complete pitched/drum producers for the first real-song FLP delivery.

**Architecture:** Reuse the complete percussion input loader and its invocation-owned recheck. A pure projection retains a full estimated arrangement and per-occurrence rational timing audit; a separate serializer/verifier checks the whole SMF before an exclusive completion report. This is an explicit audio-inference preview, never a faithful source-MIDI conversion or FLP eligibility grant.

**Tech Stack:** Existing Python/Pydantic/mido/Typer; no added dependency or model.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md` (approved), editable candidates and preserved inference provenance.

## Global constraints

- Original audio/MIDI/FLP, baselines and old experiments stay immutable; new outputs only.
- No UI input or host launch, no private files uploaded.
- Keep all existing musical/model/FLP restrictions; export does not qualify a model or establish musical tempo.
- No existing MIDI input is accepted by this path; technical-clock rounding applies only to inferred audio coordinates.
- Complete source lists and bend references remain in provenance; no silent omissions.

## Review focus

- Same-pitch nested overlaps must not be silently re-paired by SMF; reject ambiguous derived tracks explicitly.
- A positive source duration collapsing onto one tick fails rather than being extended silently.
- Unsorted/duplicate occurrences and simultaneous off/on retain deterministic identities and order.
- Changed source/native membership, cancelled publication or an altered MIDI never gets a completed report.
- Padding, source trailing silence and synthetic drum duration remain explicit, without clamping the source clock.

## Task 1: Pure projected score and complete SMF round trip

**Files:** Create `core/estimated_midi.py`, `arrangement/midi_preview.py`, `validator/midi_preview.py`; test `tests/unit/test_estimated_midi.py`.

**Interfaces:** `project_estimated_midi(PercussionArrangement) -> EstimatedMidiScore`; `encode_estimated_midi(EstimatedMidiScore) -> bytes`; `verify_estimated_midi(bytes, EstimatedMidiScore) -> None`.

- [ ] Write failing tests for independent rational timing oracles, full order/count, three pitched tracks and all nine drum mappings, tail/rounding, same-pitch overlap refusal and mutations.
- [ ] Observe RED, then implement a fixed 960-PPQ / 500000-us technical clock, half-up rounding and signed rational errors. Fixed velocity96 and 50ms drum triggers are declared rendering policy, not inferred dynamics/offsets. No program, CC or bend is invented; native bends remain referenced and unrendered as an explicit blocker.
- [ ] Encode a named conductor plus four tracks, preserve complete duration and sort note-offs before note-ons at equal ticks. Independently reconstruct all decoded messages with mido and compare the complete expected stream, including tempo/end-of-track.
- [ ] Run targeted tests and static checks.

## Task 2: Current-file export and CLI

**Files:** Create `pipeline/estimated_midi.py`, `cli_estimated_midi.py`; modify `cli.py`; test `tests/unit/test_estimated_midi_files.py` and CLI behavior.

**Interfaces:** `export_estimated_midi(batch_path, drums_path, output, *, beats_path=None, should_cancel=None)` returns the frozen report. Uses `load_percussion_inputs` once plus its complete recheck; no new inference.

- [ ] Add RED tests with original tiny producers for complete export, no native re-execution, existing/overlapping destinations, late input/MIDI changes and cancellation.
- [ ] Publish new `candidate.mid` exclusively, then a bounded source/recipe/audit report only after complete current producer rechecks and independent SMF verification. Freeze serialized inputs and score before publication callbacks.
- [ ] Register `export-estimated-midi` with a clear unqualified-candidate summary. CLI success means candidate export only.
- [ ] Update README, estimated arrangement documentation and delivery roadmap; preserve the full approved product scope.

## Task 3: Verification and real-song use

- [ ] Locked sync; targeted tests; full offline suite; Ruff lint/format; mypy; build and installed CLI smoke.
- [ ] One final exact-head independent review, current-head CI, then PR/merge according to `docs/GITHUB_WORKFLOW.zh-CN.md`.
- [ ] Use a new local real-song lineage bound to the preserved same-hash working copy because the original Downloads WAV disappeared during the previous run. Preserve that failed run and all old records. Do not relabel old receipts or restore/write the original path.
- [ ] Produce the real-song MIDI candidate after current producers validate. FLP generation, host lifecycle, audible routing, quality, GUI and installation remain required subsequent work.
