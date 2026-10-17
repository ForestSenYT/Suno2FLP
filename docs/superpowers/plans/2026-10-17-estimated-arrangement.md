# Source-bound estimated arrangement implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; one fresh exact-head whole-branch review at completion. Preserve the already approved autonomous implementation method.

**Goal:** Compose current separated audio, pitched stem candidates and optional rhythm into one explicitly estimated, source-clock arrangement without losing notes, bends, reference stems or provenance.
**Architecture:** Pure typed assembly stays separate from file validation/publication. Reuse complete existing source/native-artifact validators; no model/DAW invocation, dependency change or qualification shortcut.
**Tech Stack:** Existing Python/Pydantic/Fraction and exclusive report publisher.
**Spec:** docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md (approved).

## Global constraints

- Existing MIDI authority, precise timing/control/crop/writer/host gates stay unchanged. Estimated arrangements use a separate profile and never manufacture source MIDI.
- No GUI input, old artifact edits or private uploads. Preserve exact original audio clock and all candidate note order, activation and bend addresses.
- Reference vocals/drums/bass/other plus unassigned residual remain explicit; reference playback intent is muted, with no claim that a playable reconstruction exists.
- Roles mean source stem labels: vocal pitch proxy, bass, percussion reference and mixed pitched. No independent instrument/monophony, GM program, plugin availability or confidence inference.
- Drums stay untranscribed; meter/structure/calibration/model/music/host/writer/shared-job qualification remain unavailable or blocked. No tempo or meter fabricated from beat count.

## Review focus

1. Different input songs or clocks must fail, even with equal durations or recomputed JSON hashes.
2. Window boundary gaps, final exclusive note end, fractional source samples and padding must retain exact rational coordinates; no quantization/clamping.
3. Every note, overlapping bend stream and full reference including residual must remain addressed; empty notes are explicit, not success.
4. Changed source/runtime/batch/beat/serialized report or caller-mutated models must fail before completion publication.
5. Cancellation, existing/overlapping/linked output and unsupported/partial stem selection must retain diagnostics and never overwrite/publish completion.

## Task 1: Exact pure composition

**Files:** core/estimated_arrangement.py, arrangement/inferred.py, tests/unit/test_estimated_arrangement.py.
**Interface:** build_estimated_arrangement(batch identity/snapshot, complete pitched candidates, separation snapshot, optional beat identity/snapshot) -> EstimatedArrangement.

- [x] RED: missing assembler before implementation; behavioral source/clock/seam/end/overlap/bend/reference/role/mutated/partial checks, then explicit boolean-address rejection RED.
- [x] Implement separate audio-inference contracts. Map each start/end model-row boundary to exact source samples and microseconds using existing owned row addresses; end==owned_rows uses full resampled extent and labels any padding explicitly. Retain original native note and bend identity/address, never synthesize velocity/program/channel.
- [x] GREEN owning tests; explicit unqualified/blocked outcome and missing-capability reasons.

## Task 2: Current file workflow and reconstruction verification

**Files:** pipeline/estimated_arrangement.py, validator/estimated_arrangement.py, tests/unit/test_estimated_arrangement_pipeline.py.
**Interfaces:** compose_estimated_arrangement(batch_path, output, *, beats_path=None, should_cancel=None); verify_estimated_arrangement(report_path, *, should_cancel=None).

- [x] RED: missing workflow before implementation; actual tiny source/decode/separation/batch fixture with simulated native boundary only; changed source/bend/report, beat mismatch, existing/overlapping output, cancellation and late mutation fail without completion.
- [x] Fully validate current batch/separation and optional beat artifacts, capture immutable evidence, assemble detached values, exclusively publish estimated-arrangement.json with final source/serialized reconstruction checks. Verification repeats current artifact derivation; it does not claim fresh native replay or musical truth.
- [x] GREEN owning offline checks, including independently valid foreign-song beats and forged producer output. No actual model download/run or host launch.

## Task 3: Thin commands, public documentation and gates

**Files:** cli_estimated_arrangement.py, cli.py, tests/unit/test_cli_estimated_arrangement.py; docs/ESTIMATED_ARRANGEMENT.zh-CN.md, README, ARCHITECTURE and DELIVERY_ROADMAP.

- [x] RED/GREEN compose-estimated-arrangement and verify-estimated-arrangement; report candidate status and persistent blockers, never conversion/job success.
- [x] Document exact coordinates, role authority, references/residual, missing drums/meter/structure, no MIDI/FLP/preview yet; record prior discovery evidence while leaving whole M3/host pending.
- [ ] Locked full tests/static checks/build and genuinely installed CLI smoke; one fresh full-branch exact-head review, all current CI/main/protection/files/threads, match-head squash, actual merged tree/mainCI. Reuse unchanged validation; no private artifacts in package/Git.

Scope omits drum estimator, quality corpus/calibration, target-tick/MIDI serialization, playable synth routing and GUI integration. These remain explicit next delivery work, not completed by this plan.
