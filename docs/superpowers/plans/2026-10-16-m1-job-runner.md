# M1 Persisted Jobs and Real Audio Preflight Implementation Plan

> Execute inline under superpowers:executing-plans and TDD; one fresh final reviewer.
> The user approved continuous autonomous implementation and protected PR merging.

**Goal:** Let the future GUI/CLI create, inspect, run, cancel and recover a real local
audio job with durable event history and actual input validation, without claiming
that unavailable inference or FLP workers have run.

**Spec:** [Approved product design](../specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md).

**Architecture:** An append-only hash-linked event store reconstructs the existing
ConversionJob contract. Real PCM-WAVE preflight verifies chunk bounds, format, frame
alignment, complete data and current source identity. A shared application service
persists every transition and explicitly blocks at the first missing worker. CLI and
the next GUI slice consume the same service. No model/runtime dependency is added.

## Constraints and review focus

- Preserve original source, baseline, previous experiments and evidence. No host/UI calls.
- New job roots and every event/artifact are exclusively created. Interrupted files remain.
- File identities are evidence, not signatures or music-quality/host authorization.
- Creation binds source identity; replacing it cannot reuse old work. Current assets
  are verified on stage boundaries and resume; inspection/cancellation work if source is gone.
- Historical snapshots remain readable; mutation must use the latest valid head, with
  canonical sequence filenames and exclusive creation preventing concurrent overwrite.
- Invalid or interrupted newest records cannot be silently ignored to restart from stale state.
- Cancelled attempts retain history; an interrupted input stage is explicitly failed before retry.
- Validate WAV payload, not just metadata; unsupported codec/format/resource limits are explicit.
- GUI/CLI never see job success while decode/inference/writer/host/quality workers are unavailable.

## Task 1: Actual PCM-WAVE preflight

Files: create `core/audio_input.py`, `importer/audio.py`, `tests/unit/test_audio_input.py`.

Interfaces: `inspect_audio(path: Path) -> AudioPreflightReport` (source identity,
PCM format/frame count/data offsets/hash and rational duration); `AudioPreflightError`
has stable code and blocked/failed classification.

- [x] RED: tiny authored RIFF fixtures test PCM mono/stereo, padding/metadata, integer
  sample widths, truncation, false lengths, partial frames, duplicate/missing chunks,
  unsupported codecs/extensions, zero/overlong content and changed source.
- [x] GREEN: bounded streaming parser. Support ordinary integer PCM WAVE, preserve
  complete source identity; MP3/FLAC/float/RF64 remain explicitly unavailable in this slice.
- [x] Targeted tests and type checks; no transcription or quality assertion.

## Task 2: Durable append-only event store

Files: create `core/job_store.py`, `pipeline/job_store.py`, `tests/unit/test_job_store.py`.

Interfaces: `save_job(job: ConversionJob, previous: Path | None) -> StoredJob`,
`load_job(path: Path) -> StoredJob`, `latest_job(root: Path) -> StoredJob`.

Each canonical `states/00000000.json` contains one JobEvent, immutable job metadata
and the prior record's FileIdentity. Store events once; reconstruct full state on load.
Only creation may start a chain; append extends exactly one event from the current head.

- [x] RED: creation/append/load, original source binding, stale/concurrent publication,
  corrupt/partial/reordered/missing records, unknown keys, foreign paths and changed files.
- [x] GREEN: fsync exclusive writes, canonical contained paths, full linked-chain replay
  and before/after record identity checks. No mutable latest pointer or automatic deletion.
- [x] Inspection loads history without requiring current media; stage-boundary persistence
  checks assets, while cancellation/failure records remain possible if input disappeared.

## Task 3: Shared service and CLI

Files: create `pipeline/audio_jobs.py`, `tests/unit/test_audio_jobs.py`,
`tests/integration/test_audio_jobs_cli.py`; modify `cli.py`, `scripts/offline_smoke.py`,
`tests/integration/test_offline_smoke.py`.

Interfaces: `create_audio_job(source, output_directory, job_id) -> StoredJob`,
`run_audio_job(snapshot) -> StoredJob`, `cancel_audio_job(snapshot) -> StoredJob`,
`verify_audio_job(snapshot) -> StoredJob`.

- [x] RED: create/real preflight/blocked next stage; corrupt input fails; unsupported input
  blocks; source replacement/current evidence tampering refused; cancel after source deletion;
  restart interrupted input with retained history; root reuse and stale writes refused.
- [x] GREEN: exclusive job root, record every transition, exclusively write preflight report,
  reconstruct it independently on verification, keep all later workers blocked.
- [x] CLI: `create-audio-job`, `run-audio-job`, `verify-audio-job`, `cancel-audio-job`;
  creation/verification/cancel exit0, run blocked exit3, failed run exit1; JSON includes snapshot
  path and actual state. Zero on creation never means a deliverable was generated.
- [x] Installed workflow exercises real synthetic lifecycle, negative reuse/tamper and cancellation.

## Task 4: Evidence, docs and integration

- [x] Update jobs, architecture, README and roadmap; document exact initial PCM support.
- [x] Inspect the real song read-only into a fresh local job and verify originals/old probes.
- [x] Run locked sync, full pytest, Ruff/format, mypy, build and installed-wheel lifecycle.
- [ ] Fresh independent whole-branch review; fix significant findings with RED/GREEN.
- [ ] Public-only PR in M1; merge only reviewed exact head after all current CI passes.
- [ ] Keep M1 open: GUI and complete conversion remain unfinished; next slice adds GUI.
