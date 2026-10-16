# M2 sample-preserving PCM decoding implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Execute inline; use one fresh whole-branch reviewer after implementation.

**Goal:** Advance real audio jobs through independently verified integer PCM WAV decoding, then block at unavailable separation.

**Architecture:** Keep the existing strict WAV preflight unchanged. A standard-library streaming decoder writes a new IEEE float64 WAV with exact binary normalization, and a separate verifier recovers every original integer sample from that output. GUI and CLI use the same durable job service.

**Tech Stack:** Python 3.11+, Pydantic, struct, existing Qt worker/job services; no new dependency or DAW process.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md` and `docs/DELIVERY_ROADMAP.zh-CN.md`.

## Global constraints

- Existing MIDI source events, channels and timing remain unchanged; audio decoding gives no writer or music-quality eligibility.
- Original files and all previous private evidence remain unchanged; new intermediates use exclusive destinations outside backend installations.
- No clicks, keyboard or mouse; only authored offscreen GUI checks.
- Mono/stereo integer PCM WAV, 8–192 kHz, <=600 seconds and <=1 GiB source; preserve rate, channel order, all frames and frame-zero origin.
- MP3, FLAC, RF64, float/extensible source WAV remain explicitly blocked until separate decoder qualification. This slice does not complete M2.
- New runtime/file identities and original container inventory stay in local reports. No private media, binaries or evidence enter Git or build artifacts.
- A source/code/interpreter/output change invalidates decoded evidence; no header-only verification or in-place retries.

## Review focus

1. Unsigned 8-bit and signed 24/32-bit extrema: exact reconstruction, including stereo ordering and late impulses.
2. Forged but consistently rehashed output/report/history: independent sample comparison rejects it.
3. Cancellation or failure after some output: preserve candidates, omit stage completion, resume into a new directory.
4. Existing M1 histories and interrupted stages: retain history, reuse only reverified input/decode, reject later workers.
5. Unsafe/existing destinations and changed runtime/source: refuse before successful completion; never overwrite or infer compatibility.

## Task 1: Real decoder and independent verifier

**Files:** new `core/audio_decode.py`, `importer/pcm_decode.py`, `validator/pcm_decode.py`, `tests/unit/test_pcm_decode.py`.

**Interfaces:** `decode_pcm_wave(source: Path, output_directory: Path, *, should_cancel: Callable[[], bool] | None = None) -> PcmDecodeReport`; `verify_pcm_decode(report_path: Path, *, should_cancel: Callable[[], bool] | None = None) -> PcmDecodeReport`.

- [ ] RED: original tiny WAVs prove all four integer widths, mono/stereo, odd metadata chunks, rational duration and exact inverse normalization; assert runtime/input/output hashes and source immutability.
- [ ] RED: corrupted samples, truncation, forged metadata/runtime, source mutation, duplicate JSON keys, unsafe/existing paths, resource boundaries, cancellation and retry are rejected.
- [ ] GREEN: bounded frame blocks, exclusive/fsynced float64 WAV and JSON, complete source preflight snapshot, code/interpreter identities and fixed no-resampling/frame-zero mapping.
- [ ] GREEN: separately parse the fixed output container and recover/compare source integers; verify current identities before and after complete inspection.
- [ ] Verify targeted tests; record RED/GREEN evidence and scope rulings in a new ignored ledger.

## Task 2: Shared jobs, GUI and installed lifecycle

**Files:** `pipeline/audio_jobs.py`, `cli_audio_jobs.py`, `gui/model.py`, job/GUI tests, `scripts/offline_smoke.py`, `scripts/gui_smoke.py`.

- [ ] RED: real job finishes input and decode then blocks at separation; verify independently, reject forged later workers and decode artifacts, retain interrupted/cancelled history.
- [ ] GREEN: decode into `decode-<event-sequence>` with two exact stage artifacts, never reuse partial output; preserve old M1 snapshots and reverify on resume.
- [ ] GREEN: GUI displays two actual completed stages and an explicit missing-separation explanation; no new desktop actions.
- [ ] Verify installed CLI and offscreen GUI lifecycle; retain original source and all prior outputs.

## Task 3: Evidence, docs and integration

**Files:** new `docs/AUDIO_DECODE.zh-CN.md`; update README, jobs/GUI docs, integration/dependency/risk records and roadmap.

- [ ] Document exact normalization, timing map, runtime/cache invalidation, cancellation, failure preservation and unsupported formats; keep inferred music/host/release gates blocked.
- [ ] Decode and independently verify the real 175-second WAV into a new ignored root; verify preservation manifests and public package inventory.
- [ ] Run full tests, lint, format, types, build and installed smoke; one fresh whole-branch reviewer bound to the full head SHA.
- [ ] Create a new M2 PR, attach it, repair current-head CI, then merge only the exact reviewed head after all eight checks and current-main/public-inventory gates pass.

## Plan review and scope ruling

The approved six-stage design authorizes continuous implementation. This is the first lossless decoding slice, not the whole audio inference milestone. SoundFile/libsndfile is researched only; native codec licensing, pinned wheels, MP3 priming/padding and compressed corruption handling require their own qualification. Implementing them in this PR would couple two independently rejectable deliverables. No additional plan approval is needed under the user's continuous-execution instruction.
