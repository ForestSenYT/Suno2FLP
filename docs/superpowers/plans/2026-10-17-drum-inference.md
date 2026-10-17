# Encoder-only drum inference implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; one fresh exact-head whole-branch review after implementation.

**Goal:** Run the fixed IDM encoder in isolation, retain all nine-class raw outputs and original source timing, publish current-source replayable drum candidates and conditional annotations.
**Architecture:** Pin selected upstream source/checkpoint/notices and existing audited CPU wheels in a new runtime. A bounded worker uses explicit constructors and restricted strict state loading. Core clocks/postprocessing remain deterministic and distinct from faithful MIDI; pipeline/validator own source ancestry, raw numeric replay and exclusive files.
**Tech Stack:** Existing core Python/Pydantic, isolated CPython3.11.16 Windows x64; Torch/Torchaudio2.11.0+cpu, NumPy1.26.4, einops0.8.0 and audited transitive wheels only.
**Spec:** ../specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md

## Global constraints

- Fixed upstream456656868538205ef756912c7cf5b0fd936de8af; checkpoint SHA5856a9bee7c6d503842795756d238dc8470f6f3e010e9e4f33ede0362850cb4c. No convenience loader, Hydra, decoder, unsafe pickle, network fallback or native core imports.
- Complete194encoder tensors strict-load;136other tensors retained as unused metadata. Preserve Apache2.0 and supplementary Meta MIT notice, source/patch correspondence and dependency notices.
- Source is current numerically validated separation's complete drums.model stereo float32 at44100Hz. Downmix float64 mean thenfloat32; retain exact original-clock relation and full raw arrays, including leading/trailing padding.
- No source event movement, implicit GM/velocity/confidence claims, source/old artifact edits, GUI input, private uploads or unearned model/job/writer/host/release qualification.
- Keep old arrangement-v1 and strict MIDI/crop/host blocks unchanged. Every completion name exclusive; cancellation/failure leaves no completion marker.

## Review focus

1. Wrong source/weights/dependency membership, even rehashed, must fail current replay.
2. Encoder's extra time padding must not silently shift detections; derive geometry from code and actual probes, not frame_count/frame_rate guesses.
3. Full-length/tail/negative raw positions must remain represented; unsupported resource limits fail explicitly, never truncate.
4. Probes and real repeat outputs must come from actual selected graph, without claiming musical accuracy or faithful MIDI authority.
5. Forged receipts, moved paths, nested mutation, late file changes and cancellation must not promote completion.

## Task1: Graph and timing evidence

Files: core/drum_clock.py, tests/unit/test_drum_clock.py; local-only graph/probe attempts in new ignored directory.
Interfaces: `drum_output_rows(model_frames:int)->int`, `drum_model_sample(row:int)->int`, `drum_source_time(row:int)->Fraction` (signed exact microseconds).

- [ ] Write failing source-clock tests for513/1024/1025/44100 frames, inclusive source bounds, fractional source tail and unchanged negative/padding coordinates.
- [ ] Execute actual strict complete encoder probes on tiny authored silence/impulses/tones and exact repeats, retaining full raw outputs/source/weights/runtime/source-patch hashes. Explicitly resolve discrepancies before product timing implementation.
- [ ] Implement only evidence-supported clock rules and observe green.

## Task2: Pinned isolated backend and full raw execution

Files: core/drum_runtime.py, integrations/drum_pins.json, integrations/drum_backend.py, integrations/drum_worker.py; focused runtime/execution tests plus opt-in external test.
Interfaces: provision/read/call fixed drum backend; request complete raw stereo float32 and bounded geometry, return full class-major onset/velocity arrays and execution witnesses.

- [ ] Tests first for fixed pin/license/source patch recipes, collision/path/missing/corrupt artifacts, safe loader/strict keys/shapes, request immutability, complete output geometry/finite values, local caches/network denial, wrong native result and cancellation.
- [ ] Reuse audited bounded archive/process/path/metrics primitives without weakening their old callers. New isolation only; no global pip/model downloads. Record actual runtime deviations from upstream and all unused checkpoint state.
- [ ] Actual new-runtime handshake/probes, current payload checks before/after, CPU8threads/inter1/deterministic/mkldnnFalse; no FAKE success based on a manifest.

## Task3: Source-bound candidate, annotation and replay

Files: core/drum_transcription.py, validator/drum_transcription.py, pipeline/drum_transcription.py, cli_drum_transcription.py, cli.py; synthetic contract/pipeline/CLI tests.
Interfaces: `transcribe_drums(separation,backend,output,...)`, `verify_drum_transcription(candidate,new_replay,...)` and export a separate original-clock candidate annotation for existing score-drums.

- [ ] Tests first: verified source separation ancestry, exact downmix oracle, every raw row/label/order, declared experimental peak profile, explicit out-of-source rejection audit, no invented MIDI velocity/confidence, absent truth unavailable, source/model/recipe mutation and fresh complete native replay detect rehash-only forgeries.
- [ ] Retain all original-clock provenance and fresh invocation-local guards; reuse current complete separation proof within one trusted call, never serialized metadata as authority. Exclusive attempts/reports and full streams/partial failures retained.
- [ ] Real local song candidate and independent fresh complete replay in new files; protect originals/baselines/old experiments. No FL/GUI calls or playable-project claims.

## Task4: Validation and integration

- [ ] Synchronize INTEGRATIONS/DEPENDENCIES/RISK_REGISTER, README/architecture/roadmap and new drum inference guide with actual behavior/limitations.
- [ ] Locked sync; focused and full offline suite; Ruff/format/mypy; build, safe distribution membership and genuine installed CLI smoke. External tests opt-in and clearly skip missing prerequisites.
- [ ] Commit public-only source/tests/docs; one independent whole-branch exact-head review, actual current-head CI/protection/main/files/threads gates; squash reviewed head only; verify identical tree and real merge/mainCI. No private payloads or model/backend files uploaded.

Execution state belongs to the ignored per-plan ledger. This plan and its checkboxes do not grant model quality or delivery acceptance.
