# M2 isolated Spleeter runtime implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. The full product design and continuous implementation are already approved. Finish with one fresh strongest-model whole-branch review bound to the actual final head.

**Goal:** Explicitly prepare a fixed private Windows CPU separation runtime and prove actual local checkpoint loading, four output shapes, sample origin/length and observed repeated inference. This is the prerequisite slice for source-bound full-song candidates, not model-quality or delivery acceptance.

**Architecture:** Core contracts describe fixed artifacts, current payload and native probe evidence. Integration code installs only inspected regular archive members without setup/build hooks, rechecks all current bytes and invokes one bounded isolated child. The worker constructs the fixed Spleeter graph from pinned Python/configuration, restores a local checkpoint explicitly and never calls ModelProvider, Separator CLI, remote storage, meta-graph import or arbitrary configuration. CLI only coordinates explicit prepare/probe commands. The model is never imported into the application process.

**Tech Stack:** Existing Python/Pydantic/Typer core; trusted application CPython3.11.16 Windows x64; Spleeter2.4.2 source `c8854001ac8acad34a9bc2bd15f28475541828b1`, official v1.4.0 4stems; TensorFlow/Intel2.12.1 CPU, NumPy1.24.3, SciPy1.15.3. Freeze the complete inspected wheel recipe and supplemental official notices after actual dependency audit. No main environment or lockfile additions.

**Spec:** [Approved product design](../specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md), [primary-source runtime audit](../../research/2026-10-16-spleeter-runtime.zh-CN.md).

## Global constraints

- Preserve all original/private assets and old experiments. No desktop input, host execution or private uploads. All native files and every failed/successful attempt remain in new ignored directories; outputs are exclusive.
- Default Spleeter2.4.2 Windows dependency closure fails because its mandatory tensorflow-io-gcs-filesystem0.32.0 has no Windows wheel. This slice explicitly uses a reduced local graph recipe: TensorFlow's metadata closure resolves0.31.0; that plugin is disabled and its native compatibility is not claimed. Pandas1.5.3 and its two dependencies are included because utils.tensor imports it even for inference, yielding50 wheels. Spleeter CLI/FFmpeg/Norbert/MWF/cloud routes are unavailable. Do not call this an unmodified upstream installation or quietly relax package constraints.
- Fixed model archive SHA256 `3adb4a50ad4eb18c7c4d65fcf4cf2367a07d48408a5eb7d03cd20067429dfaa8`,146308147 bytes. Source wheel SHA256 `11b6aad050f89752e3752e08d8f69c69b699929157424e47c00e3e4db21073f9`,48673 bytes. Model members, artifacts, notices and all installed files require exact identities. No inference-time downloads or fallback.
- Use 4stems defaults:44100Hz stereo,L4096,H1024,T512,F1024,mask_extension=zeros,MWFfalse. Preserve raw native outputs. Bins1024..2048 are not recovered by the four stems; report residual explicitly. Never label residual as another separated instrument or pretend sum-to-mixture proves separation accuracy.
- Dedicated archive/payload budgets are justified by actual members, including TensorFlow's665107456-byte native library. Preserve Basic Pitch's existing defaults and gates. Any reusable limit parameter must be explicit and bounded.
- Child uses `-I -S -B`, fixed local graph/checkpoint, GPU disabled, eight CPU intra-op threads and one inter-op thread, bounded timeout and captured logs. CPU execution and repeated bytes must be observed. TF1 Session has no universal determinism guarantee; repeatability is scoped to these attempts, never inferred from a flag.
- Probe original authored nonzero stereo arrays, silence, impulse positions and awkward tails. Verify every output is finite float32 with exact complete dimensions. Retain input/output hashes and numeric residual/alignment evidence. No whole-song, 24-clip, six-song, quality, host, GUI or performance qualification from this probe.
- Canonical job separation remains blocked. No source MIDI changes, delivered stems/MIDI/FLP, writer unblocking or claimed listening acceptance.

## Review focus

1. Metadata closure differences and license notices remain visible; no transitive/native code is silently accepted or imported from global site packages.
2. Archive installation rejects traversal, links, duplicates, ambiguous names and altered members; large-library allowances do not weaken old defaults.
3. Existing/linked/overlapping outputs, changed source/runtime/artifacts/payload/adapters and incomplete native reports fail before success publication.
4. Native proof uses real checkpoint values and nonzero inputs; self-reconstruction/residual conservation alone does not qualify separation or guarantee future repeatability.
5. No package presence/version string is substituted for actual execution; exact source length, low-pass residual and current gates remain explicit.

### Task 1: Artifact audit and bounded installation contracts

**Files:** `core/separation_runtime.py`, `integrations/spleeter_pins.json`, bounded parameter in `integrations/basic_pitch_archives.py`; unit tests for contracts/archive budgets.

**Produces:** Fixed artifact/notice/model-member contracts, distinct runtime schema, current native probe schema. `archive_members(..., max_member_bytes=...)` preserves128MiB default and permits only explicitly bounded larger members.

- [x] Finish official downloads, inspect actual member sizes/hashes/notices and source correspondence. Record default resolution failure and reduced recipe. Preserve failures.
- [x] RED: oversized/aggregate archives and new schema reject wrong fixed profile, incomplete probe evidence and fake qualification. Implement GREEN with unchanged old archive defaults and meaningful small synthetic budget tests.
- [x] Freeze complete fixed recipe; confirm model members and retain license references. No setup scripts or unreviewed pickle/meta-graph execution.
- [x] Focused tests and commit; ledger exact result (110ce10; archive20/contract3, full1239passed34skipped).

### Task 2: Explicit preparation and current runtime verification

**Files:** `integrations/spleeter_backend.py`, backend unit tests, synthetic fake-package fixtures.

**Produces:** `provision_spleeter(output, artifacts) -> SpleeterBackend`, `read_spleeter(root) -> SpleeterBackend`, `verify_spleeter(root, output, should_cancel=None) -> SpleeterProbe`. Reuse established guarded paths/current file-tree and bounded process boundaries; no model import in core.

- [x] RED: missing or altered artifacts, changed/extra payload, wrong current runtime/adapter, output overlap/existence, malicious archive members and invalid probe provenance. Implement exact immutable recipe validation and exclusive installation.
- [x] Preparation consumes already downloaded files; probe is separate. Keep every native attempt/log and check payload/current dependencies before and after child and report serialization, before exclusive publication. A reproduced result-parse/hash race now uses one captured read and retained failure evidence.
- [x] Focused tests and commit; ledger exact result (23 backend cases, including reproduced parse/identity mutation and five final-publication rejection paths). Review P2 reproduced before correction: reports now remain provisional until validation and exclusive publication; hard-link failure stays explicit.

### Task 3: Real graph handshake and thin CLI

**Files:** `integrations/spleeter_worker.py`, `cli_separation.py`, CLI registration; unit boundary tests and opt-in native integration test; installed smoke.

**Produces:** Only fixed `probe` operation with authored array fixtures and retained raw outputs/report. Unsupported operations/environments fail explicitly.

- [x] RED: wrong output length/nonfinite values, missing stems, changed repeated bytes, invalid loaded modules, malformed startup and native protocol. Timeout/cancellation use the already tested owned-process boundary; actual output dtype is checked by the worker. Native dependencies are opt-in; default tests remain offline.
- [x] Build fixed graph and restore exact checkpoint. First real native test passed with two independent processes, each fixture twice,296 variables and exact impulse positions; retain all evidence. Final-adapter native replay remains a Task4 merge prerequisite. No blanket deterministic or music-quality claim.
- [x] CLI distinguishes prepared, native verified and model unqualified. Installed-wheel smoke checks public commands and explicit prerequisite failures; added CI smoke.
- [x] First actual native integration and focused tests; retain source snapshot and ledger. Final adapter replay is running separately and required before merge.

### Task 4: Documentation, verification and reviewed integration

**Files:** dedicated runtime guide, README, ARCHITECTURE, INTEGRATIONS, DEPENDENCIES, RISK_REGISTER, DELIVERY_ROADMAP; research evidence and this plan.

- [x] Document exact artifacts/licenses/dependency deviation, observed native evidence and outstanding source-bound chunk/resample/residual/quality work; update Basic Pitch as PR9 merged.
- [x] Locked sync, final full1279passed34skipped in155.16s, Ruff295formatted/mypy133, build and genuinely installed CLI smoke passed. Final regression uses ordinary-user permissions for hard-link publication; the restricted sandbox refusal is retained separately. Legacy protected records and55,411previous-phase identities unchanged. Final-adapter native replay and reviewed-head CI remain required before merge.
- [ ] One fresh strongest-model whole-branch review; resolve significant findings and bind any new head. Create/attach new M2 PR, validate current-head eight CI results/latestmain/protection/threads, merge only reviewed head and confirm merge/main CI.
- [ ] Freeze this slice's private evidence; goal remains active. Next short branch implements full source-bound separation candidates and independent replay using this runtime, with source-rate timing and explicit residual.
