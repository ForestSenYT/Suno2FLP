# M2 isolated Basic Pitch inference implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, inline. The approved full design and continuous implementation authorization remain effective. One fresh strongest-model whole-branch review follows implementation.

**Goal:** Run a fixed local CPU transcription model on verified audio and preserve complete raw predictions, original window coordinates and source-bound estimated notes as replayable candidates, without granting music or writer qualification.

**Architecture:** A private, explicitly prepared no-TensorFlow runtime loads the audited Basic Pitch ONNX artifact in a bounded process. Core owns exact window/sample mapping and candidate contracts; integration code owns fixed artifacts/native inference; the pipeline verifies the existing decoded source, publishes exclusively and independently replays current inference. No source MIDI processing or FLP gate changes. Separation and canonical job-stage integration follow once their prerequisites exist.

**Tech Stack:** Existing core Python/Pydantic/Typer; external CPython 3.11.16 Windows x64 CPU profile, Basic Pitch 0.4.0 at `9991303bba609a3b93089d13ec80d1d495083596`, ONNX Runtime 1.23.2. Curated 42-artifact closure from official PyPI, including one pure-source Pretty MIDI archive (no build execution or bundled soundfont use). No core lockfile addition. Execution ruling: the initial41-record metadata closure lacked resampy's undeclared pkg_resources import; actual failed handshake required audited setuptools80.9.0. Its vendored LGPLv3 notices remain retained. A pinned official FlatBuffers notice supplements its wheel.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md`; primary-source audit `docs/research/2026-10-16-audio-model-backends.zh-CN.md`.

## Global constraints

- All author-approved source/template/baseline/old-experiment preservation, no desktop input, no private upload and background-only constraints remain. Use new attempt directories; private packages/weights/real media never enter Git or distributions.
- Fixed weight SHA-256 `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`, 230444 bytes. Fixed official Basic Pitch and ORT wheel hashes come from the audit; every transitive artifact is individually pinned by URL/size/hash before installation.
- Source/model Apache notices and all dependency/native notices remain in the private installation. This is a documented no-TF dependency recipe, not the upstream default Python3.11 installation. Source-only packages are installed from reviewed regular members without executing setup/build scripts; unused soundfonts/sonification are excluded explicitly.
- Only trusted current application CPython 3.11.16 on Windows x64 executes the first native profile. Unsupported hosts fail explicitly; core/default tests and other existing capabilities retain their support. GPU, Linux native inference, alternate models and runtime fallback are not qualified here.
- Explicit local ONNX path and CPU provider; fixed eight intra-op threads, one sequential coordinator. Bounded owned child with captured stdout/stderr, cooperative cancellation, timeout 1800 seconds, no shell/global environment changes. No automatic dataset/model download during inference; no security-sandbox claim.
- Original audio clock and decoded sample proof remain authoritative. Estimated note times remain estimates. Existing MIDI events/channels/timing and all writer gates are unchanged.
- Fixed windows: 22050Hz, 43844 input samples, 7680-sample overlap, 3840-sample virtual left pad, 36164-sample step. Require native outputs `[1,172,88]` note/onset and `[1,172,264]` contour before accepting this profile.
- Keep all raw windows. Own rows15..156 only when their source anchors lie in the resampled source; anchor for window i / output row j is `i*36164 - 3840 + j*256`. Ownership must be unique and strictly increasing, preserve valid tail rows, and never use integer86FPS or the upstream0.0018 heuristic as exact source time. This is an explicit adapter timing profile; neural onset accuracy still requires external reference metrics.
- Preserve raw onset/note/contour arrays and frame-index events/bends. Do not call upstream MIDI export/default120BPM, infer instrument roles, drop overlapping bends, or pretend model amplitudes are calibrated confidence. No delivered MIDI/FLP or automatic quality/job success is claimed by a candidate.
- Input range follows verified decoder limits; numeric array artifacts are fixed little-endian float32 with complete dimensions, finite bounded values, no pickle/object arrays. Limits: 10,000 notes, 512MiB raw prediction data, 16MiB JSON metadata, complete failure on overrun. Resampling/downmix are explicit derived operations with exact source time relation.
- The24-clip/6-song quality and resource/host/GUI/installer requirements remain outstanding and unchanged. No score or published model claim substitutes for them.

## Review focus

1. Long recordings and short/last windows must retain valid tail predictions; inclusive seams cannot duplicate, omit or move source coordinates silently.
2. Curated dependency installation cannot import core/site/system model packages, execute source setup/pickle or accept altered archives/weights/payloads; retain actual notices and source-to-wheel comparison.
3. A changed source/decoder/model/runtime/parameter, extra native payload file, or rehashed forged prediction must fail current replay and publication checks.
4. CPU resource/provider/cancellation claims must come from actual child behavior; a version string or files alone cannot count as native qualification.
5. Every estimate, raw bend and default/unknown property must stay distinguishable from existing source MIDI and certified accuracy; unavailable clock/native/quality evidence cannot unlock writes or canonical stages.

### Task 1: Exact window ownership and contracts

**Files:** Create `core/transcription.py`, `core/transcription_clock.py`; tests `tests/unit/test_transcription_clock.py` and contract tests.

**Interfaces:** `plan_prediction_windows(resampled_frames: int) -> list[PredictionWindow]` records virtual input starts and complete172 rows; `owned_prediction_rows(resampled_frames: int) -> list[PredictionRow]` retains source anchors and raw addresses. Core candidate types retain original decoded/source identities, backend/recipe identities, fixed parameters, raw artifacts, frame-index notes/bends and exact rational inferred microseconds.

- [x] RED tests for one sample, exact step/seam, multiple windows,175s/600s tail coverage, monotonic unique anchors, negative/out-of-range budgets and snapshots/mutation.
- [x] Implement independent integer/rational source mapping. Last owned anchor must be within256 resampled samples of source end; all rows remain addressable in raw output including non-owned overlap/padding rows.
- [x] Run focused tests and commit. No native packages required.

### Task 2: Explicit private artifact preparation and native handshake

**Files:** Create `integrations/basic_pitch_pins.json`, `basic_pitch_archives.py`, `basic_pitch_backend.py`, `basic_pitch_worker.py`; typed models in core; pure archive/backend tests and opt-in native test.

**Interfaces:** `provision_basic_pitch(output: Path, artifact_directory: Path) -> BasicPitchBackend`; `verify_basic_pitch(root: Path, probe_directory: Path, *, should_cancel=None) -> BasicPitchBackend`. Preparation consumes only the fixed audited artifacts, safe bounded regular members and a trusted current Python; verification checks the complete current payload plus real isolated model loading/inference, not metadata alone.

- [x] Resolve/freeze the42 official artifacts after the recorded missing-import correction, inspect licenses/native notices and compare audited Basic Pitch wheel code/model bytes against the immutable official tree. Record curated omissions; download explicitly into a new private directory with full size/hash checks, not into core or global Python.
- [x] RED tests for hash/size mismatch, linked/traversing/duplicate/oversized archive members, unexpected source members and existing/backend/linked output roots. Implement bounded extraction and full payload inventory, preserving notices. No arbitrary executable/model selector or setup execution.
- [x] RED process/protocol tests for missing runtime, wrong shape/provider/version, extra payload, timeout, cancellation and changed dependencies. Implement fixed `-I -S -B` worker and eight-thread CPU session; capture cache files only in newly owned attempt paths outside immutable payload. Use current trusted Python; do not weaken the existing decoder's runtime policy. Existing actual-child timeout/cancellation tests cover the reused process helper; transcription-specific mutation tests additionally cover both publication boundaries.
- [x] Run actual local handshake against authored arrays, verify repeatability and record real loaded paths/provider/dimensions. Unsupported native environments skip opt-in tests clearly; default CI does not download139MB.

### Task 3: Actual source-bound transcription candidates and replay

**Files:** Create `pipeline/transcription.py`, `validator/transcription.py`, numeric artifact helpers and CLI registration `cli_transcription.py`; tests plus installed-wheel smoke. Extend shared decode-evidence utilities only where there are two concrete consumers; preserve the note scorer's after-publication dependency checks and compatibility surface.

**Interfaces:** `transcribe_audio(decode_report: Path, backend: Path, output: Path, *, should_cancel=None) -> TranscriptionCandidate`; `verify_transcription(report: Path, *, should_cancel=None) -> TranscriptionCandidate`. CLI `transcribe-audio DECODE --backend ROOT --output NEW_DIR` and `verify-transcription REPORT` report candidate-only status, never final quality success. Provision/verify commands are separate explicit preparation operations.

- [x] RED tests bind a real authored PCM decode to typed fake worker outputs: full source/clock/raw address consistency, all bends retained, empty results, excessive/invalid notes, wrong dimensions, rehashed altered predictions, source/runtime/recipe mutation, output exclusivity and cancellation. Keep mocked protocol tests distinct from genuine model evidence.
- [x] Implement explicit mean-to-mono and fixed `scipy.signal.resample_poly` recipe in the worker, retaining the original clock and exact resampled frame count. Feed audited model windows directly; retain complete per-window float32 results before postprocessing. Decode raw frame-index notes using fixed upstream postprocessing with original arrays copied before mutation; own source-anchor timestamps independently. Record parameters, raw row addresses and bend bins. No source MIDI or upstream default MIDI export.
- [x] Parent validates complete numeric artifacts and event/frame mapping without native imports, retains decoder and model dependencies through publication, and verifies current-source inference in a fresh bounded child before reporting a candidate. Read-only replay checks all current dependencies and recomputes full raw data/notes; no boolean/hash-only forgery can qualify a result.
- [x] Run genuine single-note/polyphonic/near-seam/long-tail fixtures and the current175s private song into new directories. Score only authored references with the existing fixed scorer; real-song truth remains unavailable. Compare upstream timing behavior with actual window shapes; only evidence-supported clock handling is accepted. Missing musical calibration keeps writer/quality/job success blocked.

### Task 4: Package, document and integrate the reviewed slice

**Files:** README, dependency/integration/risk/architecture/roadmap documents, `docs/BASIC_PITCH.zh-CN.md`, existing four-name CI workflow and optional installed smoke.

- [x] Document actual supported CPU/native profile, artifacts/source correspondence, license/notices, curated no-TF divergence, source-clock mapping, resource observations and all music/corpus/separation/drum/host/installer limitations.
- [ ] Full default offline suite, Ruff/format/mypy, build, installed CLI/GUI and synthetic protocol smoke. Run opt-in native inference locally; do not upload real input, weights, packages or experiment results. Verify all protected old evidence plus new193-entry note phase checkpoint.
- [ ] One fresh strongest-model whole-branch review bound to full head; reproduce/fix real findings and obtain final-head disposition. Create/attach PR with M2, all eight exact-head CI checks, latest main, expected public inventory, no unresolved threads and protection before exact-head squash merge. Read back actual merge and preserve source identities during equal-tree switch.

## Self-review / sequencing

This advances the real audio path with actual local inference, rather than certifying model quality from a source audit. Spleeter, canonical separation/analyze/transcribe job completion, estimated arrangement/MIDI export, rendering and GUI release still need their own evidence. The first Windows CPU choice and explicit source-window clock profile are engineering choices under the approved design, not new user decisions or relaxed thresholds. If the fixed native shapes/clock evidence fail, preserve candidates and diagnose; do not guess or label a partial tail as complete.
