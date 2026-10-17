# M2 Source-bound Separation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. The complete product design and continuous implementation are already approved. Finish with one fresh strongest-model whole-branch review bound to the actual head; preserve all private evidence.

**Goal:** Produce complete, source-clock-bound four-stem WAV candidates from verified local audio, with bounded global-STFT inference, retained intermediate evidence and independent fresh replay. Repair the existing transcription publication boundary before reusing that pattern.

**Architecture:** Core owns exact clocks, contracts and exclusive verified report publication. The pinned private Spleeter child processes one global 512-frame STFT partition at a time, preserving the original partition grid and overlap-add. Pipeline services bind current decoder/model/source identities; independent validators check complete numeric evidence and reexecute the fixed model in a new directory. CLI coordinates these services. Candidates remain unqualified for music quality, jobs and FLP writing.

**Tech Stack:** Existing typed Python/Pydantic/Typer and standard-library validators; isolated fixed Spleeter2.4.2/TensorFlow2.12.1/NumPy1.24.3/SciPy1.15.3 Windows CPU recipe from PR10. No new dependency, model download, DAW or desktop interaction.

**Spec:** [Approved delivery design](../specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md), [runtime source analysis](../../research/2026-10-16-spleeter-runtime.zh-CN.md), [runtime prerequisites](../../SPLEETER_RUNTIME.zh-CN.md).

## Global Constraints

- Preserve original audio/MIDI, baselines and all earlier experiments. New exclusive directories only; no desktop clicks, keys or mouse. Private audio, models, vendor packages and experiments stay ignored and local.
- WAV/MP3/FLAC use the existing independently verified decoder evidence. Source rate8000..192000, channels1/2, duration at most600seconds; unsupported or incomplete data fails without truncation.
- Source origin remains frame0. Model rate44100, L4096/H1024/T512/F1024; mono is duplicated explicitly. Model frames `ceil(N*44100/Fs)`, source coordinate of model sample j is `j*Fs/44100`. No accumulated floating time or moved source events.
- Fixed SciPy polyphase conversion uses reduced integer factors, Kaiser beta5, constant-zero boundaries and explicit float32 model input. Back-conversion retains exactly N source frames; retain any returned tail separately. Never call resampling lossless.
- Global STFT frame k begins at source-model coordinate `k*1024-4096`; Q=`ceil((Nm+4096)/1024)`. Each partition owns up to512 consecutive global STFT frames. Windowed analysis and synthesis retain global origin and3072-sample inter-partition overlap; no independent waveform reset/crossfade.
- Retain padded partition inputs and four native partial outputs, assembled model-rate outputs, source-rate float32 stereo WAVs, resampling tails, float64 unassigned residual and all native logs/requests/results. Residual is not a fifth separated instrument and cannot improve the model's quality score.
- Native whole-vs-partition reference comparison is fixed before execution: maximum absolute error <=1e-5*max(1,input absolute peak). This is a float32 engineering tolerance, not musical qualification. Fresh replay of the same bounded recipe compares complete bytes.
- CPU8 intra-op/1 inter-op, GPU/TFIO/ambient plugins disabled, bounded owned process1800seconds. Record observed peak process memory and refuse candidate publication if above16GiB; this is not whole-application performance qualification.
- All final reports are staged, checked with current witnesses and exclusively atomically published as the last operation. No fallback on unsupported hard links. Rejected attempts retain diagnostics and provisional reports only; replay cannot write inside the original candidate.
- Full24-clip/6-song quality, calibrated thresholds,10-run stability, warm3-minute<=30-minute budget, host lifecycle/FLP gates and final GUI/installer acceptance remain required by the product design. This slice cannot mark them passed.

## Review Focus

1. Concurrent replacement after serialization, late cancellation and competing publication must never leave a completion marker or overwrite a file.
2. Odd source/model lengths, mono, all supported rates and partition boundaries must retain every source frame exactly once without silently discarding resampler tails.
3. Global-STFT synthesis must include cross-partition overlap and the exact upstream padding/cropping; missing/reordered/duplicated chunks cannot pass validation.
4. Rehashed forged outputs, changed decoder/runtime/model/recipe and provisional/foreign manifests must fail independent current-source replay.
5. Default CI must stay offline and model-free; genuine native checks must execute the checkpoint and distinguish alignment/repeatability from musical accuracy.

### Task1: Verified publication and transcription boundary correction

**Files:** new `core/report_publication.py`; modify `pipeline/transcription.py`, `validator/transcription.py`; tests `test_report_publication.py`, `test_transcription_pipeline.py`.

**Interfaces:** `publish_verified_report(path:Path, content:str, protected:list[Path], verify:Callable[[],None])->None`. It writes a `.pending.json` sibling, captures exactly those bytes, calls the final verifier, rechecks the provisional identity and exclusively links the final path. No potentially rejecting work follows publication.

- [x] RED: a final source/payload/artifact/provisional mutation, cancellation, existing final/pending file or unsupported publication leaves no new completion marker and preserves diagnostics; successful publication matches exact serialized bytes.
- [x] RED: transcription's parsed native result identity comes from the same bounded read; late validation failures retain `transcription.pending.json`, and pending/nested/foreign replay paths are rejected.
- [x] GREEN: use the primitive, keep all source snapshots and include the helper in the transcription recipe. Do not weaken independent numeric checks or mutate old candidates.
- [x] Focused38 passed; full1296 passed34 skipped; Ruff298 formatted/mypy134 passed. Commit and ledger record the completed boundary correction.

### Task2: Exact separation clock and evidence contracts

**Files:** new `core/separation_clock.py`, `core/separation.py`; factor shared `SpleeterExecution` fields in `core/separation_runtime.py`; tests for clock/contracts.

**Interfaces:** `model_frame_count(frames:int,sample_rate:int)->int`, `plan_separation_partitions(model_frames:int)->list[SeparationPartition]`. Partition fields: index, global STFT start/count, virtual waveform start/count. `NativeSeparationResult` covers execution proof, complete canonical partitions, source geometry and observed native resource use. `SeparationCandidate` binds decoder, full model, current recipe and every intermediate/output identity; `SeparationReplayReceipt` records a complete fresh match and stays unqualified.

- [ ] RED: N=1,1023/1024/1025,4095/4096/4097,512-hop partition boundaries on both sides; rates8000/22050/44100/48000/96000/192000, odd lengths and600-second endpoints; reject bools, missing/reordered/duplicate partitions and wrong sizes.
- [ ] GREEN: integer-only clocks, complete artifact geometry and permanently unqualified quality/writer fields. Preserve old probe JSON shape.
- [ ] Focused checks, record results and commit.

### Task3: Bounded native source processing

**Files:** `integrations/spleeter_worker.py`, new `integrations/spleeter_separation_worker.py`; `integrations/spleeter_backend.py`; worker boundary tests.

**Interfaces:** `native(..., partitioned:bool=False)` keeps the original full-waveform probe and adds fixed partition analysis/synthesis. `call_spleeter_separation(record:SpleeterBackend,attempt:Path,request:dict[str,object],should_cancel:Callable[[],bool]|None=None)->None` invokes only the fixed child with exact source metadata and retains logs. The child emits the canonical raw files and bounded result JSON; it imports no application Pydantic/native packages into the parent.

- [ ] RED: malformed operation/source geometry, invalid float samples, incomplete outputs, reordered input partitions and wrong native proof fail explicitly. Validate request type and owned-process timeout/cancellation behavior.
- [ ] GREEN: map verified float64 WAV at offset58; explicit mono duplication and fixed rational resampling; one globally anchored STFT partition per model call; preserve partial inputs/outputs and overlap-add onto model-grid files; resample each stem to source-grid WAV with separately retained tail. Never normalize or clip.
- [ ] Bind the new worker/helper/contracts in current adapter hashes. Factor shared native proof validation; old probes keep their existing meaning.
- [ ] Focused offline checks and commit. Run real probes only after attested source bytes stop changing; use new private backend/attempts.

### Task4: Source-bound pipeline, independent checks and replay

**Files:** new `pipeline/separation.py`, `validator/separation.py`, `validator/separation_signal.py`; source/pipeline/validator tests and original synthetic native protocol helpers.

**Interfaces:** `separate_audio(decode_report:Path,backend:Path,output:Path,*,should_cancel:Callable[[],bool]|None=None)->SeparationCandidate`; `validate_separation_artifacts(report:SeparationCandidate,...)->None`; `verify_separation(report_path:Path,replay_directory:Path,...)->SeparationCandidate`.

- [ ] RED: source/decode/model/recipe changes, malformed WAV/length/nonfinite data, missing/reordered chunks, forged rehashed assembly/residual and invalid final marker fail. Cancellation and late validation never publish a candidate. Replay output overlapping any original candidate root fails before creating files.
- [ ] GREEN: reuse independently verified decoded-source evidence; capture native result identity and bytes once. Independently reconstruct global overlap-add with standard-library float32 operations, verify every partial input against model PCM, source-grid geometry, resampling tail and residual conservation. Verify all current dependencies at publication.
- [ ] Fresh replay compares the full canonical result, all partial/intermediate/WAV bytes and residual, then publishes a separate replay receipt only on complete match. Preserve original and failed replay attempts.
- [ ] Focused tests and commit.

### Task5: Thin CLI and genuine engineering evidence

**Files:** `cli_separation.py`, `scripts/separation_smoke.py`, CLI/smoke tests; opt-in `tests/integration/test_separation_external.py`, native reference test helper.

**Interfaces:** `separate-audio <decode-report> <backend> --output <new-directory>` and `verify-separation <candidate> --replay-output <new-directory>`.

- [ ] RED/GREEN: CLI reports current prerequisite failures and unqualified candidate status, installed smoke sees commands without importing native dependencies.
- [ ] Compare bounded native output to a separate full-graph process on an original nonzero stereo fixture crossing two partition boundaries with awkward tail and impulses; fixed tolerance above, complete dimensions and peak positions checked.
- [ ] Independently test the declared polyphase alignment/filter recipe on original small signals and multiple rates; no hidden fallback or rate reinterpretation.
- [ ] In a new ignored delivery directory, decode the existing real song read-only, generate complete source-bound stems and fresh replay; retain all raw evidence and source identities. Record native CPU/memory/timing, not music acceptance. Any unsupported evidence remains blocked.

### Task6: Documentation and reviewed integration

**Files:** new `docs/SEPARATION.zh-CN.md`; README, ARCHITECTURE, DELIVERY_ROADMAP, BASIC_PITCH/SPLEETER_RUNTIME and risks/integration docs as affected.

- [ ] Document exact sample/partition/resampling/overlap/residual rules, completion marker semantics, genuine results and remaining quality/job/host/GUI gates. Mark PR10 merged without rewriting the approved design.
- [ ] Locked sync, full tests, Ruff check/format, mypy; build and genuine installed CLI smoke, public package inventory only. Native and private assets stay excluded.
- [ ] One fresh strongest-model full-branch review bound to actual head; fix significant findings, rebind changed head per repository rule. New M2 PR with public-only file inventory; eight current checks/latest main/protection/threads before exact-head squash merge. Confirm actual merge, identical tree and main CI.
- [ ] Freeze this slice's new private evidence and protect earlier checkpoints unchanged. Keep the overall goal active until all product requirements pass.
