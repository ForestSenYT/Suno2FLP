# M1 Audio Conversion Job Contracts Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. The user approved
> continuous autonomous execution of the full design; one fresh final reviewer checks
> the slice before the SHA-bound CI/merge gate. No per-slice approval is required.

**Goal:** Give the upcoming CLI/GUI one honest, persisted contract for an audio conversion
job: stage progress, evidence-bearing success and explicit failure/cancellation/recovery.

**Architecture:** Add strict job contracts under core, keeping process/UI/runtime adapters
outside core. Every successful stage has immutable input/output identities; final success
requires independently verified publication and the approved quality profile. Pure state
transitions cannot grant host/writer permissions. This first slice is the contract and
transition foundation; no audio-to-FLP command or fabricated running backend is exposed.

**Tech Stack:** Existing Python 3.11+, Pydantic, pytest and current file identities; no new
dependency or model. GUI and models follow in separately reviewed slices.

**Spec:** [Approved delivery design](../specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md)
and [current delivery roadmap](../../DELIVERY_ROADMAP.zh-CN.md).

## Global Constraints

- Audio-only estimates and source-faithful MIDI remain separate authorities.
- Only new files, no private uploads, no desktop input, no new host invocation in this slice.
- Source/template/previous evidence stays immutable; current file identities are verified.
- `succeeded` requires actual evidence and all required stages; enum edits never authorize writes.
- Cancelled/failed/blocked jobs retain their completed stages and history. Resume checks current identities.
- Existing faithful-MIDI and writer schemas/eligibility stay unchanged.

## Review Focus

- Stage reordering, skipped prerequisites or duplicate execution must not turn an incomplete job successful.
- False progress, NaN/infinite values, mutated results and contradictory statuses must fail validation.
- Source files changed between stages or resume must invalidate reuse, including size/mtime/hash changes.
- Cancellation/failure during a stage must preserve prior evidence and cannot publish partial success.
- A policy/quality check is evidence scoped to a job/configuration, not arbitrary trusted booleans.

## Task 1: Job state and stage contracts

**Files:** Create `src/suno2flp/core/jobs.py`; create `tests/unit/test_jobs.py`.

**Interfaces:**
- Consumes: `core.offline_models.FileIdentity` and shared `Contract`.
- Produces: `JobStatus`, `StageStatus`, `ConversionStage`, `JobStage`, `JobEvent`,
  `ConversionJob` with a schema/profile version and complete ordered history.
- Canonical stages: `input`, `decode`, `separate`, `analyze`, `transcribe`, `arrange`,
  `route`, `write`, `host_verify`, `quality`, `publish`.
- Statuses are the approved `queued/running/blocked/failed/cancelled/succeeded`;
  stage pending uses `queued`. No declared stage is silently skipped.

- [ ] Write failing tests for canonical ordering, unique stage names, bounded integer
  progress, empty evidence on success, source identity preservation and illegal terminal states.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/unit/test_jobs.py --basetemp .pytest_cache/m1-jobs-red`;
  expect failure because contracts do not exist.
- [ ] Implement strict contracts, copying evidence and validating cross-field consistency.
- [ ] Run the targeted tests with a new basetemp; every case must pass.

## Task 2: Pure transitions with evidence and recovery boundaries

**Files:** Create `src/suno2flp/pipeline/jobs.py`; extend `tests/unit/test_jobs.py`.

**Interfaces:**
- `new_job(job_id: str, source: FileIdentity, output_directory: Path) -> ConversionJob`
- `start_stage(job: ConversionJob, stage: ConversionStage) -> ConversionJob`
- `report_progress(job: ConversionJob, stage: ConversionStage, progress: int) -> ConversionJob`
- `finish_stage(job: ConversionJob, stage: ConversionStage, outputs: list[FileIdentity]) -> ConversionJob`
- `stop_job(job: ConversionJob, status: Literal['blocked', 'failed', 'cancelled'], code: str) -> ConversionJob`
- `resume_job(job: ConversionJob) -> ConversionJob`: verifies current source and completed
  output identities before returning a queued copy; retains failed-attempt history.
- These functions do not launch workers, create directories or publish files. File persistence,
  adapter execution, actual quality proof and final publication belong to the next slice.
- Final `publish` completion remains blocked by this foundation: a future independent verifier
  must supply a separate proof contract. These helpers cannot set a job to `succeeded`.

- [ ] Add failing behavioral tests for out-of-order starts, monotone progress, unchanged input
  objects, failed/cancelled state preservation, invalid resume after source/output change,
  no stage restart while running, and refusal to complete `publish` or claim final success.
- [ ] Run targeted tests and observe the missing transition implementation failures.
- [ ] Implement minimal pure transitions using deep copies; use current input identity checks
  from `core.offline_files` for resume. Keep transition failures explicit.
- [ ] Run targeted tests, then the complete required suite and installed CLI smoke via CI.

## Task 3: Review and integrate the slice

**Files:** Update `docs/ARCHITECTURE.md`, `docs/DELIVERY_ROADMAP.zh-CN.md` and add a short
`docs/JOBS.zh-CN.md` describing implemented contracts, evidence and next runner boundary.

- [ ] Verify no dependency, CLI or GUI capability is advertised before implementation.
- [ ] Run full pytest, Ruff, formatting, mypy and `git diff --check`; inspect all skips.
- [ ] Commit on a new `codex/m1-job-contracts` branch from merged current main.
- [ ] Obtain one fresh independent review of the complete slice, fix findings and rebind to head.
- [ ] Push, create/attach a small PR; inspect public file inventory and current-head CI.
- [ ] Only after all checks and review pass, merge the exact head under the protected workflow.
- [ ] Next slice: real persisted runner/preflight, then a GUI that consumes these actual states.
