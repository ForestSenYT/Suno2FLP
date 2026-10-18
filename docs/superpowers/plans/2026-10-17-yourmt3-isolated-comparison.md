# YourMT3+ isolated comparison implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate a pinned local YourMT3+ candidate and compare fixed original-clock song excerpts against the rejected baseline before authorizing any new FLP experiment.

**Architecture:** Keep the core free of model libraries. Provision a separate fixed CPU payload from audited wheels, pinned author source and checkpoint; a bounded worker returns complete tokens, decoding diagnostics and explicitly inferred notes. An independent file reader verifies source/runtime/output identities and time derivations. Musical acceptance, existing source-MIDI restrictions and FLP eligibility remain separate.

**Tech Stack:** Existing Python3.11.16/Pydantic contracts and exclusive publication helpers; isolated cached torch/torchaudio2.11.0+cpu, numpy1.26.4, author transformers4.45.1. Additional inference dependencies must be resolved, audited and pinned before execution.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md`; explicit user request2026-10-17 for isolated YourMT3+ and song excerpt comparison.

## Global constraints

- No keyboard/mouse/clicks or UI automation. Only bounded owned background processes.
- Only new private outputs; original assets, references, rejected candidates and old experiments remain unchanged. Never upload private files or backend/model payloads.
- Author Space revision `5e66c1ea173a8186e0d20432b841d3180cc015b5`; weights revision `e45ebd70398682d54b7bb1901a5216e18f3b1824`. Start with YPTF+Single(noPS),361050039B,SHA256 `507ff129bf68f65b3b3439368706fc413523fc729d994e4da2c3f50860b05dde`.
- CPU8threads, job RAM<=16GiB; GPU support is not inferred from CPU evidence. No automatic runtime/precision/model fallback.
- Freeze six15-second observation intervals before inference:0–15,30–45,60–75,90–105,120–135,160–175seconds. Preserve source-frame origins and any model context separately. These real-song excerpts are not the24-piece calibration/holdout corpus and have no claimed ground-truth accuracy.
- Current baseline's human music acceptance failed for wrong notes, rhythm and missing sections. More notes, activity or audible output alone cannot qualify an improvement. No new FLP before positive comparison evidence; unsupported routing/fields continue blocking writes.

## Review focus

1. Unlocked demo dependencies, web/YouTube helpers and implicit downloads must never become the local worker entry point.
2. A valid checkpoint filename must not hide missing/unexpected tensor keys, unsafe loading or a different model/configuration.
3. Fragment offsets, short tails, tied notes and chunk boundaries must retain original-clock provenance; clipped inference context must not masquerade as missing music.
4. Program/drum/vocal labels are model estimates; retain raw labels/errors and never silently coerce them into existing four-stem or GM routing contracts.
5. Failed or stale model/results, changed files and user-rejected music must not become a successful job, qualified model or writer permission.

## Task1: establish the fixed runtime and native contract

**Files:** new ignored `.tools/yourmt3-adoption-v1/`; public findings `docs/YOURMT3.zh-CN.md`, `docs/INTEGRATIONS.md`, `docs/DEPENDENCIES.md`, `docs/RISK_REGISTER.md`.

**Consumes:** existing fixed author text audit, `ModelArtifactPin`, `archive_members`, audited drum wheel archives (read-only).
**Produces:** exact wheel/source/notice/checkpoint inventories, complete tensor key/shape/dtype expectations, an observed short native inference contract and explicit deviations from the author demo.

- [ ] Resolve the minimal real inference import closure; audit author Apache statements and third-party notices separately from the GPL GitHub landing repository. Fix every artifact URL/size/hash and license before installing; no upstream setup scripts or package source builds.
- [ ] Download only the pinned checkpoint into a new path, verify actual bytes/hash, and inspect its container/load requirements. Use audited safe tensor loading; no arbitrary user checkpoints or silent unsafe fallback.
- [ ] Reuse cached fixed wheels through new payload extraction; add fixed binary wheels only. Record all omissions/source patches. Do not modify any existing runtime.
- [ ] Execute one bounded real handshake and original short inference; capture actual versions/device/threads/config/state, complete tokens/errors/times and peak memory. Missing prerequisites fail explicitly. If unsupported, retain failure and stop that hypothesis.

## Task2: implement the evidenced typed development workflow

**Files:** `core/yourmt3.py`; focused `integrations/yourmt3_{backend,source,worker}.py` and fixed pins; `pipeline/yourmt3.py`; `validator/yourmt3.py`; thin `cli.py`/commands module; original unit/opt-in integration tests.

**Produces:** `load_yourmt3_pins() -> YourMT3Pins`; `provision_yourmt3_backend(output: Path, artifacts: Path) -> YourMT3Backend`; `transcribe_yourmt3(decode_report: Path, backend_root: Path, output: Path, intervals: list[FrameInterval]) -> YourMT3Candidate`; `verify_yourmt3(candidate_path: Path) -> YourMT3Candidate`. Exact native field values and payload inventory come from Task1, never guessed by Task2.

- [ ] Write original tests RED for incomplete/changed artifacts, unsafe membership/collisions, exact source intervals, complete tail/context, malformed tokens/state, source/program provenance, changed files and old-output refusal.
- [ ] Implement inert contracts and separate bounded worker/source provisioning. Retain all raw native evidence and decoder errors; keep core dependent only on core. Do not call the author demo or expose arbitrary module/checkpoint entry points.
- [ ] Independently verify current complete payload/result/source identities and every time mapping; reject contradictory/missing results. Publish exclusively only after final rechecks; retain failed attempts without completion names.
- [ ] Observe GREEN for the focused original tests and explicit external missing-prerequisite skips. Add synthetic note/onset matching fixtures where truth exists; do not invent real-song F1.

## Task3: compare the song and condition subsequent FLP work

- [ ] Save the fixed interval manifest and baseline source identities before native song inference; compare the same intervals, preserving model context and whole-song offsets separately.
- [ ] Record per-interval note/program/onset distributions, coverage and decoding/boundary errors; obtain audio/listening or genuine reference evidence for wrong notes/rhythm/missing sections. Report inconclusive comparisons honestly. A larger event count is insufficient.
- [ ] If comparison evidence supports a new candidate, first specify and test exact source reconstruction/program routing into an independently qualified FLP profile. Otherwise retain the music/writer blockers and do not generate or render another weak candidate. Background rendering, if eligible, uses a new bundle and bounded owned host only.
- [ ] Update capability/roadmap and integration documentation. Run locked sync, full pytest, Ruff/format and mypy; packaging changes also require build and installed CLI smoke.
- [ ] Freeze exact head; one fresh-context whole-branch review, public-file whitelist and all current CI. Merge only the reviewed matched head; read back actual merge/tree and preserve private inputs/old outputs. Complete product/GUI/corpus/release acceptance remains separate.
