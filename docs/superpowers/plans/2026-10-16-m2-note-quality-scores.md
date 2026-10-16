# M2 pitched-note scoring implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The user has authorized continuous inline implementation and gated merges.

**Goal:** Produce replayable, source-bound, exact-time pitched-note scores against explicitly declared reference annotations, without claiming model or song qualification.

**Architecture:** Core contracts describe annotations and conditional metrics. A pure maximum-cardinality matcher uses exact rational microseconds; file services independently verify the existing decoded-audio evidence and replay scores. Thin CLI commands publish new reports only. Existing job stages, MIDI handling and writer gates do not change.

**Tech Stack:** Python 3.11+, existing Pydantic/Typer, standard library; no new dependency, native runtime, model or UI action.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md`, quality and data-authority sections.

## Global constraints

- Onset tolerance 50ms; offset tolerance max(50ms, reference duration ×20%); exact MIDI pitch equality, fixed matching version.
- Preserve original annotation order, note IDs, duplicate notes and rational source coordinates. No rounding, shifting, quantization or greedy many-to-one matching.
- Release F1 macro ≥0.80 and each clip ≥0.70 remain requirements, not current achievements. This slice cannot establish the 24-clip corpus or model qualification.
- No truth means unavailable metrics; empty reference is a distinct unscored case. Declared reference provenance is not certified truth. Confidence is not accuracy.
- Source audio, decoded PCM, annotation, producer provenance and current scoring recipe identities must agree and remain current. Decode evidence is independently checked, including native replay for compressed input.
- No input overwrite, FLP writes, model download, host interaction, private upload or job success promotion.
- Fixed limits: 10,000 notes per annotation, 200,000 eligible edges, 4MiB annotation JSON, 16MiB report/provenance file, 300-second cooperative matching budget. Exceeding limits fails completely.

## Review focus

1. Ambiguous overlapping equal-pitch notes require augmenting paths and deterministic duplicate-aware matching, including a chain longer than Python's recursion limit.
2. Rational values just beyond inclusive tolerance boundaries must fail without rounding; offset tolerance depends on reference duration.
3. Fabricated clocks, altered PCM, changed annotation/provenance/recipe or a rehashed fabricated result must be rejected by fresh replay.
4. Missing and empty references cannot become perfect scores or promote jobs to success.
5. Dense adversarial input, cancellation, linked paths and existing outputs must fail without partial metrics or input changes.

### Task 1: Exact conditional metrics

**Files:** Create `core/note_scoring.py`, `validator/note_matching.py`, `tests/unit/test_note_matching.py`.

**Interfaces:** `ScoredNote(id, pitch, onset_microseconds, offset_microseconds)`; `score_notes(candidate: list[ScoredNote], reference: list[ScoredNote] | None, *, should_cancel: Callable[[], bool] | None = None) -> NoteScore`. Exact ratios and matched/unmatched IDs are explicit. Scoring returns measured/reference_unavailable/no_reference_notes; it never grants qualification.

- [ ] Write tests for 50ms inclusive onset, exact fractional overrun, reference-relative offsets, duplicates, wrong pitch, empty/missing references, greedy counterexample and iteration beyond recursion limits.
- [ ] Observe RED, then implement exact fractions and deterministic iterative augmenting paths over sorted-ID views. Use per-pitch onset buckets/bisect, bounded edges, cooperative cancellation/deadline.
- [ ] Compare maximum cardinality against an independent exhaustive small-graph oracle; verify input order unchanged. Run focused tests and commit this task.

### Task 2: Source-bound file reports and replay

**Files:** Extend core contracts; create `importer/note_annotations.py`, `validator/note_scoring.py`, `pipeline/note_scoring.py`, `tests/unit/test_note_scoring_files.py`.

**Interfaces:** `NoteAnnotation` contains role/origin, method, producer provenance FileIdentities, decode-report/source identities, rate/channels/frames and original notes. `collect_note_score(candidate_path, reference_path, *, should_cancel=None) -> NoteScoreReport` verifies all current inputs and existing decode proof. `score_note_files(candidate_path, reference_path, output, *, should_cancel=None) -> NoteScoreReport` exclusively publishes. `verify_note_score(report_path, *, should_cancel=None) -> NoteScoreReport` recomputes and compares, without writes.

- [ ] Write failing tests using new authored PCM and independently verified decode: valid report/replay, unknown truth, clock/role/source mismatches, altered producer files, fabricated result, current recipe changes, oversized/duplicate JSON, cancellation and exclusive output protection.
- [ ] Observe RED; implement bounded regular-file reads with before/after identity, without modifying existing decode modules or their bound helpers. Verify PCM/compressed decode using existing independent validators, then compare annotations to actual clock/source/report identity. Freeze scorer code identities and current Python executable/version in reports.
- [ ] Recheck all witnesses before and after matching/publication. Publish only to a new JSON file outside inputs/backend trees; retain failed outputs as evidence if a late check fails, never claim success. Replay uses current inputs and recipe, not report assertions.
- [ ] Run focused tests, full suite, lint/types; commit task.

### Task 3: CLI, installed behavior and documentation

**Files:** Create `cli_note_scoring.py`, `scripts/note_score_smoke.py`, `docs/NOTE_SCORING.zh-CN.md`, CLI tests; modify CLI registration, README, architecture, delivery roadmap and existing four-name CI workflow.

**Interfaces:** `score-pitched-notes CANDIDATE --reference REF --output NEW.json`; optional reference produces unavailable status. `verify-note-score REPORT`. Exit 0 means valid measured report, exit 3 means unscored, exit 1 means error. Below-target measurements remain measurements, not software release acceptance.

- [ ] Add failing CLI status/report tests; implement thin commands. Explain exact-time units, schema, fixed algorithm, resource limits, conditional reference provenance and explicit outstanding drum/beat/separation/corpus/host gates.
- [ ] Add installed-wheel synthetic smoke: actual new PCM decode, known duplicate-aware F1, replay, unknown truth and tamper refusal. Add it to all four existing CI matrices without renaming checks.
- [ ] Run full offline tests, Ruff, mypy, offline build, installed CLI/GUI and scoring smoke. No redundant native codec rerun unless relevant implementation changes.
- [ ] Inspect public inventory/distributions; request one fresh strongest-model whole-branch review bound to full head. Fix real findings with RED→GREEN and bind final disposition to final head. Commit, push PR, attach and assign M2.
- [ ] Merge only after exact-head independent approval, all eight CI checks, latest main, expected public files, resolved threads and branch protection. Verify merged tree/main CI and preserve private evidence. Keep overall goal active.

## Self-review and remaining scope

This is the first scoring slice, not all M2. Drum/category matching, beat metrics, separation SI-SDR, corpus licensing/splits, model audit/inference/calibration and actual song/host/listening/installer qualification remain independent work. The evaluator measures annotations conditional on their declaration; it does not certify annotation correctness or mislabel source MIDI as human audio truth. No policy threshold is changed.
