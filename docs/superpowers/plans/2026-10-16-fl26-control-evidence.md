# FL26 control evidence implementation plan

> **For agentic workers:** Use superpowers:executing-plans; implement inline with a final fresh review.

**Goal:** Narrow tempo/control unknowns with independent background probes and original read-only code, without claiming an exact song writer.

**Architecture:** Keep the existing writer and inventory schemas unchanged. Add a separate event-223 observation report and a source-replayed MIDI encoding assessment. Backend/host runs remain private experiments; product commands never launch processes.

**Tech stack:** Existing Python 3.11+, Pydantic, Fraction, pytest, Windows FL26 CLI for authorized private probes.

**Spec:** User request plus [noninteractive preservation contract](../../NONINTERACTIVE_PERFORMANCE.zh-CN.md).

## Constraints and review focus

- Exact build 26.1.7.5654; original source, baselines and previous experimental files remain unchanged.
- No UI input, settings edits, private uploads, new dependencies or guessed write eligibility.
- Preserve every event and source identity; simulated nearest tempo is analysis only, never an encoding policy.
- Unknown/partial records, cross-track order, duplicate events, same channel in different files, stale or forged reports must remain distinguishable.
- Background render success cannot prove exact automation timing or MIDI routing. Keep all existing writer gates.

## Tasks

1. Private probes (new files only): pin executable/source, compare scalar and event tempo, stepped tempo, 96/960 PPQ, repeatability and native channel volume. Hash inputs before/after. Record observed differences without compensating source ticks.
2. TDD read-only `inspect-fl26-controls`: `core/control_evidence.py` contracts and `integrations/fl26_controls.py` scanner; original synthetic bytes test integer values, offsets, ordering, malformed tails, unknown IDs, profile gates and exclusive CLI output. Old inventory stays unchanged.
3. TDD `assess-midi-encoding`: `flp_builder/encoding_assessment.py` replays a current performance plan; report rational scalar errors and hypothetical accumulated error, source/channel control-event requirements with original addresses/messages, and unconditional write/routing/timing blockers. Test cross-file channel separation, duplicates, control-only tracks, inexact/range edges and tampered inputs. Add saved-assessment replay and installed CLI smoke coverage.
4. Document actual private observations and limits; run required full checks, build and installed-wheel smoke; fresh review and fixes; inspect public file list, commit, push, update PR #1 and check CI.

## Decisions / execution evidence

- Continue the existing PR branch and isolated ignored evidence directory; no second checkout or new backend required.
- Evidence so far: 14 background CLI renders succeeded. Constant 60, 120 and 120.001 BPM event/scalar pairs were PCM-identical. Repeated stepped render was identical, but measured step timing differs from the ideal source clock at both tested PPQs. Therefore no writer gate is relaxed.
- Native channel volume response establishes only a native REC control, not MIDI CC7/program delivery to an instrument. Product inspection labels it accordingly.
- Retain all private evidence for provenance; do not delete the experiment workspace.
- Validation checkpoint: 30 new synthetic unit cases; full suite 804 passed / 19 explicit skips;
  Ruff and formatting (170 files), strict mypy (75 modules), source/wheel build and installed-wheel
  lifecycle passed. Ordinary build dependency resolution hit restricted DNS; cached offline build passed.
- One fresh read-only review found no Critical/Important/Minor issues. Reviewer checked public code
  and private combined-render metadata, not host scheduling, private source hashes or actual song
  delivery. Parent independently rehashed 61 source/baseline/probe identities, verified all 73 manual
  record references and all 14 new probe/render identities; host compatibility and song delivery remain
  unverified. No claim is made that these unresolved behaviors were approved by the review.
- Public distributions contain no private assets or runtime caches. PR #1 carries final commit/CI status.
