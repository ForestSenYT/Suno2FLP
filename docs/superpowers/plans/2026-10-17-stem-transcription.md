# Source-bound stem transcription implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan inline, task-by-task. Keep TDD evidence and rulings in the new private phase ledger.

**Goal:** Transcribe explicitly estimated pitched stems on the original song clock, with fresh separation replay and complete independently verifiable ancestry.

**Architecture:** Preserve original decoder and MIDI semantics. A separately typed derived source uses exact float32-to-float64 widening, with independently checked complete samples and thin references to complete current separation reports. A batch owns one fresh separation replay; shared pitch inference mechanics may be factored without granting the derived source original-recording authority. Full native predictions remain separate bounded reports.

**Tech Stack:** Python 3.11+, Pydantic, standard-library waveform checks; existing isolated pinned Spleeter and Basic Pitch runtimes. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md` (approved); `docs/BASIC_PITCH.zh-CN.md`, `docs/SEPARATION.zh-CN.md`.

## Global constraints

- Audio-only inferred candidates remain distinct from source-faithful MIDI and independently decoded original recordings.
- Preserve every sample/frame/channel, signed zero, original source clock, raw windows, bends and complete current provenance. Do not normalize, clip, shift or cast through integers.
- Vocals, bass and other are estimated pitched mixtures; drums require a different supported analysis. No fabricated melodic drum notes.
- All musical/model/job/writer/host qualification stays blocked; confidence is not calibrated.
- No desktop input, changes to original media or frozen phases, private uploads, model downloads or backend redistribution. New exclusive outputs only.
- Use short `codex/*` branch from current main; exact-head independent review, complete current CI and latest-main/protection/file-list gates before squash merge.
- Default tests offline, original tiny synthetic fixtures; mock only native process boundaries. Native experiments remain opt-in.

## Review focus

1. Coherent rehashed separation or prediction forgery must require actual fresh native replay, not trust a receipt boolean.
2. Large full-song reports must remain bounded and complete, with no repeated inventory explosion or truncation.
3. Nonstandard rates, signed zero, stereo asymmetry and tails must preserve original coordinates and every finite value.
4. Cancellation or source/report/payload replacement at publication must leave no completion marker.
5. Foreign/provisional reports and overlapping destinations must not obtain valid lineage or mutate prior artifacts.

## File boundaries

- `core/stem_transcription.py`: explicit derived-source, candidate and thin batch/replay contracts.
- `importer/stem_audio.py`: exclusive finite float32-to-float64 preparation; no inference or original decoder claims.
- `validator/stem_audio.py`: independently derived IEEE bit widening and strict complete waveform verification.
- `validator/stem_transcription.py`: complete current ancestry/report/member checks and batch replay.
- `pipeline/stem_transcription.py`: owns fresh separation replay, preparation, native prediction and completion publication.
- Existing transcription core/pipeline/validator: smallest typed shared inference seam only if required; keep original v1 semantics intact.
- `cli_stem_transcription.py`: thin development commands; docs and tests beside their owning features.

### Task 1: Exact derived waveform bridge

**Interfaces:** `widen_stem_wave(source: Path, output: Path, *, frames: int, sample_rate: int, channels: int, should_cancel=None) -> FileIdentity`; `verify_stem_wave(source: FileIdentity, pcm: FileIdentity, *, frames: int, sample_rate: int, channels: int, should_cancel=None) -> None`.

- [ ] Write behavioral tests for signed zero/subnormals/extrema, mono/stereo/odd rates, malformed headers, nonfinite samples, truncated/extra data, invalid geometry, alias/overlap, cancellation and changed input.
- [ ] Observe meaningful RED failures, then implement streaming standard-library producer and independent integer IEEE-bit oracle. Use strict canonical 58-byte float WAV layouts, original N/Fs/C and bounded passes.
- [ ] Run owning tests and existing decoder/signal regressions; commit and ledger exact results.

### Task 2: Typed estimated lineage and complete batch inference

**Interfaces:** `transcribe_stems(separation_report: Path, backend: Path, output: Path, *, stems=("vocals", "bass", "other"), should_cancel=None) -> StemTranscriptionBatch`; `verify_stem_batch(report: Path, output: Path, *, should_cancel=None) -> StemTranscriptionBatch`.

- [ ] Write RED tests using real separation/decode contracts and only synthetic native process boundaries. Cover complete ancestry, exact clock, unsupported drums, reordered/duplicate/missing selection, full source/backend/recipe/payload mutation, all Review Focus cases and final serialization replacement.
- [ ] Implement explicit derived contracts and smallest shared pitch seam. Own a new fresh separation replay once per batch; independently validate current complete referenced snapshots before consumption and publication. Canonical report addresses and exclusive roots required.
- [ ] Save complete raw predictions/notes/bends for each stem. Thin batch references must re-read complete own reports; no trusted mutable cache or copied original-decoder report.
- [ ] Fresh full batch replay reruns separation and every selected pitch prediction and compares complete semantics/artifact hashes. Receipt paths/resource observations may differ but remain individually current and bounded.
- [ ] Run all owning and original transcription/separation regressions, commit and ledger.

### Task 3: CLI, documentation and actual full-song evidence

- [ ] Write RED thin CLI and opt-in prerequisite tests; expose only unqualified candidates/replay, never automatic job/writer success.
- [ ] Document source vs estimate authority, clocks, failure/exclusivity policies, commands and limitations. Update roadmap around actual implementation status.
- [ ] After source stabilizes and is committed, use new isolated backend/evidence directories and readonly prior song/separation. Save complete execution source identities; run real pitched inference and fresh full replay. Preserve failures and actual outputs; do not lower budgets or musical gates to pass.
- [ ] Run `uv sync --locked`, full pytest, Ruff check/format, mypy, build and genuinely noneditable CLI smoke; audit public package contents. Record native limits/skips honestly.
- [ ] One fresh strongest-model whole-branch review bound to full SHA, resolve substantive findings with RED/GREEN, rebind changed head per repository policy. Publish public files only; all eight current-head CI checks and merge gates precede exact-head squash. Verify merged tree/main CI; freeze phase and proceed to next independent work.
