# Source-bound beat and downbeat analysis implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task-by-task. No implementer subagents; one fresh strongest-model whole-branch reviewer at the end. Preserve a new private phase ledger.

**Goal:** Obtain actual local neural beat/downbeat candidates and conditional timing scores on the original audio clock, enabling the planned inferred arrangement path.

**Architecture:** An isolated pinned CPU Beat This! runtime consumes independently verified original PCM. Preserve complete derived inputs, all model logits, peak selection/alignment and exact source coordinates; saved candidates require actual fresh native replay. Conditional reference metrics never grant model/job/writer qualification. Existing MIDI, decoder and pitched-stem contracts stay unchanged.

**Tech Stack:** Python3.11+, Pydantic/standard library in core; Windows x64 CPython3.11.16 and pinned CPU PyTorch/Torchaudio2.11.0, Beat This!1.1.0 in a separate private runtime. No heavy dependencies in the application environment.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md` (approved), `docs/DELIVERY_ROADMAP.zh-CN.md`, `docs/NOTE_SCORING.zh-CN.md`.

## Global constraints

- Audio-only positions are inferred; retain original source hash/frame origin/sample rate/channels and every raw prediction. Existing MIDI events remain untouched.
- No desktop input, original/old-experiment mutation, private uploads, plugin loading or FLP/MIDI writes. Exclusive new outputs; cancellation leaves no completion marker.
- Pinned upstream revision `b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c`; final0 weights only after official-source identity/license audit. No default-name/URL checkpoint loading or automatic download fallback.
- CPU8 work threads, peak RAM16GiB reference budget. Record runtime/observed resources; no GPU/release-performance claim. Default tests stay offline without native packages.
- Musical thresholds stay fixed: beat-labelled errors median30ms/P95 80ms; drum class/onset F1 remains a separate unfinished capability. No inferred meter denominator or calibrated confidence claim.
- Every current-head test/review/CI/latest-main/protection/file-list gate precedes exact-head squash. Preserve private failures and complete execution source evidence.

## Review focus

1. A missing/corrupt local model must fail rather than invoke the upstream network fallback or load an arbitrary pickle.
2. Chunk overlap, short tails and 50Hz positions must preserve all logits/padding and exact original time, including noninteger source sample coordinates.
3. Native minimal postprocessing moves downbeat peaks to beats; keep the raw peaks and complete before/after alignment, including ambiguous float ties and absent beats.
4. Silent/anti-phase signals and no-reference/unmatched labels cannot obtain fake rhythm quality or perfect scores.
5. Coherently rehashed artifacts, changed payload membership or cancellation at publication must not pass replay or publish completion.

## Task 1: Audited isolated runtime and real native probe

**Files:** `core/beat_runtime.py`, `integrations/beat_backend.py`, `integrations/beat_worker.py`, `integrations/beat_pins.json`; corresponding offline/opt-in tests; integration/dependency/risk docs.

**Interfaces:** `provision_beat_backend(output: Path, artifacts: Path) -> BeatBackend`; `read_beat_backend(root: Path) -> BeatBackend`; `probe_beat_backend(root: Path, output: Path, *, should_cancel=None) -> BeatProbe`.

- [ ] Audit official source/weights/dependency closure and notices; fix actual artifact hashes, source correspondence and safe checkpoint geometry. Retain all source evidence locally; no vendored backend in Git.
- [ ] RED: missing model/version/runtime/payload, hostile archive paths/collisions, reused/overlapping output and network fallback must fail explicitly. Missing external prerequisites skip only opt-in tests.
- [ ] Implement exclusive preparation using existing safe archive/file tools and separate typed contracts. Native worker requires `-I -S -B`, private imports/caches, fixed CPU and weights-only local checkpoint loading. Use upstream model/frontend/chunk inference/minimal postprocessor; never its file loader/URL resolver.
- [ ] Run tiny original silence/impulse/stereo signals in real native processes. Save complete inputs/logits/postprocessing and exact repeated-output observations. Audit actual imported paths, versions, model state and resource settings; no music qualification.
- [ ] Commit tested runtime boundary and synchronized license/runtime limitations.

## Task 2: Complete source-bound rhythm candidates and fresh replay

**Files:** `core/beat_analysis.py`, `core/beat_clock.py`, `pipeline/beat_analysis.py`, `validator/beat_analysis.py`, `validator/beat_postprocessing.py`; owning tests.

**Interfaces:** `analyze_beats(decode_report: Path, backend: Path, output: Path, *, should_cancel=None) -> BeatCandidate`; `verify_beat_analysis(report: Path, output: Path, *, should_cancel=None) -> BeatCandidate`.

- [ ] RED: nonstandard rates, fractional source anchors, stereo cancellation, complete coverage/tails, invalid/duplicate peaks, no-beat/downbeat-only cases, exact tie behavior and immutable source callbacks. For frame1 at11025Hz, source anchor must be441/2 samples and20000 microseconds. Upstream deduplication averages adjacent peaks: frame1/2 must remain441/4 samples and10000 microseconds, never rounded to an integer frame.
- [ ] Implement explicit estimated-source lineage over current verified decoding. Record source-rate downmix, resampled model input, complete log-mel input and all framewise beat/downbeat logits. Shape/grid/resource checks fail rather than silently truncate.
- [ ] Independently reconstruct fixed minimal peak/dedup/alignment operations from complete raw logits; preserve all raw and aligned positions. Source coordinates use exact frame/50 arithmetic; source-boundary/padding observations remain explicit.
- [ ] RED/GREEN: coherent raw/result/report rehashing, foreign source/recipe/model, payload additions/deletions, late replacement and cancellation. Untrusted saved reports require actual fresh native inference and complete comparison before replay publication; no trusted receipt boolean/cache.
- [ ] Keep raw candidates unqualified, silence/phase limitations explicit, and meter/structure/roles/drum classes unavailable. Run owning tests and preserve source/event invariants; commit.

## Task 3: Conditional beat-label timing metrics, CLI and acceptance

**Files:** `core/beat_scoring.py`, `validator/beat_scoring.py`, source-bound annotation/report wrappers beside existing note scoring, `cli_beat_analysis.py`, thin registration in `cli.py`; tests and `docs/BEAT_ANALYSIS.zh-CN.md`/README/roadmap.

**Interfaces:** `score_beats(candidate: list[ScoredBeat], reference: list[ScoredBeat] | None, *, should_cancel=None) -> BeatScore`; file score/replay operations coordinate existing verified source clocks.

- [ ] RED: labelled one-to-one matching, a greedy counterexample, duplicates, rational boundaries, no-reference versus empty reference, missing/false labels and cancelled/over-budget inputs. Use an independent exhaustive tiny matching oracle.
- [ ] Match exact beat/downbeat labels with a fixed500000-microsecond diagnostic window and deterministic maximum-cardinality/minimum-total-error pairing. Preserve unmatched IDs/coverage. Report exact errors, median and nearest-rank P95; e.g. errors20/100/120ms produce median100/P95 120ms, never hidden by a50ms matching cutoff. Undefined metrics stay `None`, not zero/perfect.
- [ ] Add source-bound annotation provenance and current-file/recipe rechecks using existing patterns. Reference declarations never certify truth; reports retain all unqualified status fields. These beat metrics do not satisfy the separate drum-class gate or final release by themselves.
- [ ] Expose thin analysis/probe/replay/score CLI commands; document source versus inference, explicit supported limits, no fallback, licence evidence and remaining release gates. Update roadmap to reflect PR12 merged and actual new capability only after verification.
- [ ] After source stabilizes and is reviewed, run original tiny native signals and this song in new private outputs, plus full native replay. Retain actual execution source identities and all failures; do not lower thresholds to pass.
- [ ] Run locked full pytest, Ruff/format/mypy, build and genuinely installed CLI; audit public package contents. One fresh whole-branch reviewer bound to complete SHA; fix/rebind current head and all8CI before matching-head squash, then verify actual merged tree/main CI.

## Scope self-review

This slice delivers actual joint beat/downbeat analysis plus conditional timing measurement, rather than substituting an unlabeled onset baseline. Drum timbre classes, meter denominator, structure, calibrated model qualification, shared jobs, inferred arrangement and FLP/host/GUI release remain explicit later tasks in the unchanged product design. No smaller success definition is substituted for that goal.
