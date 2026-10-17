# Source-clock percussion arrangement implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. One fresh exact-head whole-branch review after the cohesive slice; no implementer agents.

**Goal:** Combine the complete pitched batch, optional beats and current drum candidate into a separate, replayable four-part estimated arrangement.

**Architecture:** Keep source-clock-estimated-arrangement-v1 and faithful MIDI untouched. New v2 contracts retain producer identities, complete pitched inputs, all raw-bit drum peaks/events/rejections and exact source-clock positions. Current file readers establish numeric/source authority; a pure builder derives the arrangement. Thin Typer commands exclusively publish and independently reconstruct JSON candidates.

**Tech Stack:** Existing Python/Pydantic/Typer/Fraction and publication/guard primitives; no new dependencies or native execution.

**Spec:** ../specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md

## Global constraints

- Original audio, MIDI, FLP, baselines and old experiments remain immutable. No desktop input, FL Studio invocation, new native inference, MIDI/FLP writing or private uploads.
- Inference remains audio-inference/unqualified_candidate; model_qualification=not_assessed, ground_truth_metrics=unavailable, writer_eligibility=blocked and execution_allowed=false.
- Keep exact original sample/microsecond fractions. No implicit GM, MIDI channel, velocity, note duration, confidence, quantization, tempo/meter/structure or plugin availability.
- Keep every pitched note/bend address and every drum peak/event/padding rejection in source order. JSON16MiB and existing list budgets remain; reject excess, never truncate.
- Different source/decode/separation/replay/clock/reference identities fail explicitly. Do not upgrade v1 reports or old writer plans.
- Work in the existing checkout on fresh codex/m2-percussion-arrangement from main74905aeda893d612946f3231c2192f8ee589137b, preserving identity-bound private evidence. Baseline is actual1725passed/44skips plus8CI and identical squash tree; main's4postmerge checks remain separately pending until observed.

## Review focus

1. Valid but unrelated pitched/drum producers must not be fused by duration or filename alone.
2. Negative/tail drum padding and nonuniform pitched seams must retain their original distinct clocks.
3. Missing/reordered/duplicated peaks or coherently altered derived positions must not pass reconstruction.
4. Changed/added native files, late producer changes, cancellation and overlapping outputs must never publish completion or contaminate producer directories.
5. No labels, activation/head values or JSON success may become GM routing, confidence, musical truth or writer permission.

## Task1: Pure contracts and source-clock fusion

**Files:** core/percussion_arrangement.py, arrangement/percussion.py, tests/unit/test_percussion_arrangement.py.

**Interfaces:** `EstimatedDrumInput` stores transcription/backend/native witness identities, original source/decode/PCM/separation/replay/reference/model PCM identities and clock, complete peaks/events/rejected peaks, current row/model frame counts and fixed peak profile. `PercussionArrangementInputs(pitched:EstimatedArrangementInputs, pitched_separation_replay:FileIdentity, drums:EstimatedDrumInput)`. `build_percussion_arrangement(inputs)->PercussionArrangement` is pure and detaches inputs.

- [x] Write/run RED tests with authored minimal metadata: exact same origin, channels, frames/rate, separation+receipt and drums reference; foreign identities, malformed geometry, missing/reordered/duplicate events and producer mutation are refused.
- [x] Implement new source-clock-estimated-arrangement-v2 with canonical four parts, existing pitched note positions/references and separate onset-only drum positions indexed to complete source events/peaks. Every drum source sample is `(row-6)*256*original_rate/44100`; microseconds use the exact geometric clock. Rejected peaks stay in inputs, outside playable positions.
- [x] Test independent Fraction oracles for 48k fractional positions, pitch seam/final padding, negative/tail drum padding, overlaps, all nine class labels, raw float bits, empty drum estimates and unchanged caller/v1 snapshots.
- [x] Preserve all v1 blockers except its v2-resolved drums-not-transcribed limitation; explicitly retain drum latency/GM routing/quality/playback/host/writer blockers. No fake duration or calibrated velocity.

## Task2: Current producer readers, publication and reconstruction

**Files:** validator/percussion_arrangement.py, pipeline/percussion_arrangement.py, tests/unit/test_percussion_arrangement_files.py.

**Interfaces:** `percussion_recipe()->ScoringRecipe`; `load_percussion_inputs(batch,drums,beats,recipe,should_cancel=...)->(inputs,protected,recheck)`; `compose_percussion_arrangement(batch,drums,output,beats_path=None,should_cancel=None)`; `verify_percussion_arrangement(path,should_cancel=None)`.

- [ ] RED tests establish a complete synthetic pitched batch and drum candidate through current numeric readers (mock only native boundaries), then require exact common original/decode/separation/replay/reference identities.
- [ ] Reuse `load_estimated_inputs` with its own `estimated_recipe()`; retain its recheck. Read the current batch receipt identity, and use `read_drum_candidate` plus its owned source proof and complete native/payload guard. Reference the full immutable drum producer by FileIdentity instead of duplicating its large source snapshots.
- [ ] Freeze detached input/recipe JSON. Publish only new percussion-arrangement.json via pending+exclusive completion; verify a fresh pure reconstruction and current source/recipe/report/native/payload membership immediately before completion. Protect all producer roots before writing anything.
- [ ] Verify from the report's own original directory, current producer files and current recipe; reconstruct every field. Test late mutation/addition, cancellation, wrong root, altered serialized positions/blockers and new output collision without new model/DAW calls.

## Task3: CLI, docs and current-song evidence

**Files:** cli_percussion_arrangement.py, cli.py, tests/unit/test_cli_percussion_arrangement.py, scripts/offline_smoke.py; docs/ESTIMATED_ARRANGEMENT.zh-CN.md, docs/DRUM_SCORING.zh-CN.md, README.md, docs/ARCHITECTURE.md, docs/DELIVERY_ROADMAP.zh-CN.md.

- [ ] RED/GREEN thin Typer commands: `compose-percussion-arrangement BATCH --drums CANDIDATE [--beats REPORT] --output NEW_DIRECTORY`; `verify-percussion-arrangement REPORT`. Summaries expose candidate status, pitched/drum counts, blockers and execution=false. Missing/current-source failures exit nonzero.
- [ ] Document original clocks, full producer references, no invented drum duration/GM/velocity, unsupported playback/quality/jobs/writer/host and unchanged strict MIDI. Correct scorer's historical next-step wording now that the separate inferred-drum producer exists.
- [ ] Use the current real-song pitched batch and PR17's original drum candidate in a new output only; verify current-source reconstruction and protected inputs. Record timings/resource limits honestly; no source edits/rebinding or musical acceptance from this test.

## Task4: Validate and integrate

- [ ] Locked sync; focused meaningful tests and required full pytest/Ruff/format/mypy; build and actual installed CLI smoke for new commands. Preserve explicit external skips.
- [ ] Public-only commit/PR with one fresh exact-head whole-branch review; re-review fixes. Confirm current main, exact files, all8current CI, protection and resolved threads before matching-head squash; no queued unreviewed merge.
- [ ] Verify actual merge/tree and preserve private source identities. Observe actual4mainCI before closing this slice; entire delivery goal remains active and unqualified.

Execution evidence and statuses belong to the ignored per-plan ledger, not speculative checkmarks here.
