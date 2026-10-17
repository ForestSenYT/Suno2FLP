# Source-bound drum scoring implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one fresh whole-branch review.

**Goal:** Conditional drum class/onset scoring on verified original audio clocks.
**Architecture:** Small core contracts and linear maximum-cardinality matching; reuse current decoder verification, bounded snapshots and exclusive verified publication. Thin CLI, no model/DAW imports.
**Tech Stack:** Existing Python/Pydantic/Typer, exact fractions, no new dependencies.
**Spec:** ../specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md

## Global constraints

- Original inputs, private artifacts and old candidates remain unchanged; publish new JSON only.
- Fixed exact 50ms inclusive class/onset tolerance, one-to-one matches; no invented drum offsets or GM assignments.
- Preserve annotation order/IDs, source clock and producer evidence. Missing/empty reference has no F1.
- Conditional annotations never authenticate truth, qualify models/jobs or authorize writes.
- Existing arrangement-v1 and host/MIDI/crop blocks remain unchanged. No computer input.

## Review focus

1. Wrong class, boundary fractions and duplicate events cannot produce false matches.
2. Dense clusters must use maximum cardinality, independent of input order.
3. Empty references and false positives must not produce an inflated quality claim.
4. Nested mutation, altered decode/producer/recipe and copied report paths must fail replay.
5. Cancellation, exclusive output and late witness changes must not publish completion.

## Task 1: Exact contracts and matching

Files: core/drum_scoring.py, validator/drum_matching.py, tests/unit/test_drum_scoring.py.
Interfaces: `ScoredDrum(id, label, microseconds)`, `score_drums(candidate, reference, *, should_cancel=None) -> DrumScore`.

- [ ] Write tests first: nine supported IDM labels, exact50ms vs fractional excess, wrong class, maximum matching brute-force oracle, stable ties, complete unmatched lists, missing/empty truth, counts, cancellation and nested mutation.
- [ ] Observe failures, implement fixed per-class chronological earliest-valid matching with owned snapshots; observe green.

## Task 2: Source-bound publication, replay and CLI

Files: validator/drum_scoring.py, pipeline/drum_scoring.py, cli_drum_scoring.py, cli.py, tests/unit/test_drum_scoring_files.py.
Interfaces: `score_drum_files(candidate, reference, output, *, should_cancel=None) -> DrumScoreReport`; `verify_drum_score(path, *, should_cancel=None)`.

- [ ] Write failing file/CLI tests using tiny original PCM, producer and annotations; check current clocks, tampering, duplicate JSON, immutable inputs, late changes, report relocation, exclusive publication and unavailable exit3.
- [ ] Reuse verified_transcription_source, bounded_snapshot, decoder payload witnesses and publish_verified_report; full current replay compares every field and current report location. Add thin commands score-drums/verify-drum-score. Observe green.
- [ ] Document schema/algorithm/limits and synchronize capabilities/roadmap, without claiming model quality or native inference.

## Task 3: Integration

- [ ] Locked sync, full pytest, Ruff check/format, mypy, build and installed CLI smoke; inspect distribution membership.
- [ ] Commit public-only files; fresh independent exact-head review; fix real findings with regressions.
- [ ] PR from latest main, verify every current-head CI and protected-main rules; squash only reviewed head, verify actual merged tree/mainCI. Keep local evidence private.

Status is tracked in the ignored per-plan ledger; checkboxes here describe the validation contract, not a release assertion.
