# M2 isolated compressed decoding implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Execute inline with one fresh whole-branch review at the end.

**Goal:** Accept qualified FLAC/MP3 files through the shared real job service, producing a new verified PCM intermediate with exact presentation timing and explicit failures.

**Architecture:** A read-only source scanner proves complete container/frame coverage before native decoding. Fixed official wheels live in a new private package tree; the application's trusted CPython3.11.16 or3.14.7 launches a standalone worker with `-I -S -B`, controlled import paths and forbidden system-library fallback. A record cannot select another executable. A separate verifier checks the output container/current identities and replays the pinned codec; FLAC additionally has independent decoded-PCM MD5 verification. Existing PCM jobs retain their stronger original-sample proof.

**Tech Stack:** Existing Python/Pydantic core; isolated SoundFile 0.14.0, libsndfile 1.2.2, NumPy 2.3.5, CFFI 2.0.0, pycparser 2.23, typing_extensions 4.16.0. No core dependency/lock change.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md`; incremental acceptance in `docs/DELIVERY_ROADMAP.zh-CN.md`.

## Global constraints

- Preserve all originals, old artifacts and protected checkpoints; exclusive new outputs, never FLP/host/UI actions or private uploads.
- Source <=1 GiB, mono/stereo, 8–192 kHz and <=600 seconds; never truncate/resample, swap channels or move the source/presentation clock.
- FLAC: native container, supported 8/16/24-bit PCM, known nonzero total frames and MD5; complete frame structure, CRCs and sample count. Unsupported features block explicitly.
- MP3: MPEG Layer III with a qualified complete Xing/Info and LAME gapless extension. Validate every frame boundary, declared stream bytes/frame count, delay/padding and tag integrity; metadata-free/unknown timing stays blocked. Lossy decoded samples are decoder-qualified, never represented as original uncompressed truth.
- Windows/Linux x86_64 only, exact application CPython3.11.16/cp311 or3.14.7/cp314. The isolated process reuses that trusted interpreter and its verified matching wheel ABI, never an executable chosen by task metadata.
- Pin URLs/hashes for both platforms before provisioning. Retain all upstream wheel notices locally; do not redistribute binaries. Installer licensing/source/replaceability acceptance remains M5 work.
- Complete decode success requires independent current-source/output verification. Later separation/inference/FLP/host/music/release remain blocked.
- Preserve failures, bounded process lifetime/output, cooperative cancellation; never kill unrelated processes or reuse partial candidates.

## Review focus

1. Native success hides truncated MP3 or FLAC trailing/concatenated audio: structural scanner must cover every encoded byte and frame.
2. MP3 encoder delay/padding moves the musical origin: exact supported tag/stream checks and authored impulse/lag evidence; refuse unknown policies.
3. Native dependency injection/system fallback: verify pinned archive/payload inventory before execution, disable site/Python-path imports and fallback; recheck actual loaded library/version.
4. Forged report/history with rehashed PCM: recompute source inventory, qualified runtime and full native replay; no cached success from JSON booleans.
5. Cancellation, timeout, changed files/runtime, old M1/PCM histories and missing prerequisites: durable honest stops, new attempt directories, explicit cache invalidation and backwards verification.

## Task 1: Encoded input contracts and complete scanners

**Files:** new `core/encoded_audio.py`, `importer/encoded_audio.py`, `importer/flac_frames.py`, `importer/mp3_frames.py`; new `tests/unit/test_encoded_audio.py`.

**Interface:** `inspect_encoded_audio(source: Path, *, should_cancel: Callable[[], bool] | None = None) -> EncodedAudioInventory` containing original FileIdentity, source codec, exact rate/channels/presentation frames/rational duration, metadata regions, raw timing headers and complete ordered-frame coverage digest.

- [ ] RED: authored metadata and FLAC constant/verbatim/fixed/LPC/Rice frame fixtures prove valid frame boundaries, CRC8/CRC16, numbering/sample totals and full EOF coverage; reject truncation, appended garbage, concatenation, invalid residuals and resource limits.
- [ ] RED: authored MPEG frames plus independently specified Xing/LAME fields prove CBR/VBR, mono/stereo, supported MPEG rates and exact delay/padding arithmetic; reject partial/extra frames, changing rate/channel layout, malformed tags, missing gapless evidence and unknown timing.
- [ ] GREEN: capture/hash one immutable source snapshot bounded to1GiB, preserve metadata offsets/raw stream info, parse complete supported structures without decoding music or guessing resynchronization. This trades up to1GiB source-buffer RAM for stable bit-level random access within the16GiB product budget; full native samples are verified later.
- [ ] Record observed RED/GREEN and parser budgets in a new ignored ledger.

## Task 2: Fixed isolated runtime and bounded worker

**Files:** new `core/codec_backend.py`, `integrations/codec_wheels.json`, `integrations/codec_backend.py`, `integrations/codec_process.py`, `integrations/codec_worker.py`; new backend/process unit and opt-in integration tests.

**Interfaces:** `provision_codec_backend(directory: Path, python: Path, *, wheelhouse: Path | None = None) -> CodecBackendRecord`; `verify_codec_backend(directory: Path) -> CodecBackendRecord`; `run_codec_worker(backend: Path, mode: Literal["decode", "verify"], arguments: list[str], *, should_cancel: Callable[[], bool] | None = None) -> CodecAudioResult`. Probe is a separate fixed handshake.

- [ ] RED: missing/wrong Python/platform, existing/linked/nested backend, bad pin/hash/path/archive, extra/changed payload, missing native library and forbidden system fallback fail explicitly before usable readiness.
- [ ] GREEN: download official fixed wheels or consume an explicit offline wheelhouse, verify before exclusive extraction, retain notices/archives and full package inventory, then perform real handshake and compare actual native path/version/capabilities. Backend marker remains `backend.json` so existing output guards also protect this integration.
- [ ] RED/GREEN: owned child timeout, cancellation, nonzero exit, invalid/duplicate/oversized JSON, stderr/stdout limits and missing outputs; bounded readers, always reap the owned process, no shell or UI calls.
- [ ] Actual worker decode preserves rate/channels/frames, emits finite little-endian float64 without clipping/resampling, proves FLAC decoded MD5, compares all samples in verify mode and never rewrites an existing output. Worker imports only stdlib and the explicit audited package tree.

## Task 3: Decode evidence and application integration

**Files:** new `core/encoded_decode.py`, `pipeline/encoded_decode.py`, `validator/encoded_decode.py`; modify `pipeline/audio_jobs.py`, `cli_audio_jobs.py`, GUI model/app; new/expanded service, CLI and offscreen tests.

**Interfaces:** `decode_encoded_audio(source: Path, output_directory: Path, backend: Path | None, *, should_cancel: Callable[[], bool] | None = None) -> EncodedDecodeReport`; `verify_encoded_decode(report_path: Path, *, should_cancel: Callable[[], bool] | None = None) -> EncodedDecodeReport`. Shared `run_audio_job(..., decoder_directory: Path | None = None)`; GUI `JobActions(..., decoder_directory: Path | None = None)` and optional advanced app flag share that service.

- [ ] RED: input+decode finish for qualified FLAC/MP3 then separation blocks; missing runtime records an explicit prerequisite block. Rehashed output, backend/source/clock changes, mismatched artifacts and unqualified later workers refuse reuse.
- [ ] GREEN: report embeds complete source inventory, runtime record/current identities, exact presentation map, sample/output hashes, observed native counts and verification kind; musical/host/writer eligibility remains unverified/blocked.
- [ ] Preserve old PCM report semantics and legacy input-only histories; cancellation/interruption retain attempts and resume into new directories. Installed GUI/CLI use identical stages/reasons.
- [ ] Real codec integration generates original short WAV→FLAC/MP3 fixtures locally, independently checks frame-zero/lag/count and lossless sample identity, and tests observed native false-positive damage cases.

## Task 4: Qualification, docs and PR

**Files:** new `docs/COMPRESSED_AUDIO.zh-CN.md`; update README, jobs/GUI/dependency/integration/risk/roadmap docs; new `scripts/codec_smoke.py`; add actual isolated codec smoke to existing four CI matrix names.

- [ ] Record fixed upstream/source/binary mapping, actual notices/licensing limits, exact supported formats/timing, native replay limits, output/cancellation protection and no completed music/FLP claim.
- [ ] Build and run installed CLI/GUI/core codec smoke; default offline tests require no native package, opt-in integration declares prerequisites, CI separately exercises the real downloaded fixed backend.
- [ ] Use a new synthetic/local real-song derived copy to verify FLAC frame/sample preservation without modifying the original WAV; protect all previous manifests/checkpoints. Real compressed source is not assumed to exist.
- [ ] Full tests/lint/format/types/build/package inventory; one fresh whole-branch review bound to actual head; create/attach a new M2 PR and repair CI. Merge only the exact reviewed current head after all eight checks, current main, expected public inventory and resolved threads pass. Preserve all private evidence; keep goal and M2 open.

## Evidence-driven rulings

Exploratory probes established isolated imports and byte-identical FLAC reconstruction; authored MP3 had unchanged 44,100-frame length and best correlation lag zero. The same runtime accepted truncated MP3 and FLAC trailing garbage/concatenation, so native success cannot qualify complete input. This plan therefore includes full structural scanners before adding worker success. MP3 amplitude equality to original PCM is not a valid lossy-codec gate. The already approved continuous implementation instruction supersedes a repeated approval handoff.
