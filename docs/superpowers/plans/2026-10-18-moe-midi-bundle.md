# MoE model-program MIDI bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export an independently verified current MoE candidate into an editable
per-model-program MIDI bundle, preserving all inferred notes and provenance, without
collapsing programs or granting FLP/music/host qualification.

**Architecture:** Add a separate inferred-source DTO/projection/file workflow. Reuse
current MoE producer validation with a retained current-source recheck; share the
strict note-only SMF framing validator with existing estimated-MIDI verification.
No ML packages or new dependencies enter core. GUI/FLP integration follows separately.

**Tech Stack:** Existing Python/Pydantic/mido/pytest; fixed isolated MoE for opt-in tests.

**Spec:** docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md
and docs/DELIVERY_ROADMAP.zh-CN.md, M2. PR25 merged at6757f22; this slice starts
from that current main on codex/m2-moe-midi-bundle.

## Global Constraints

- Windows11x64 first; existing fixed model/backend identities and source guards remain.
- New outputs only, never modify source audio/MIDI/FLP/baselines/old experiments.
- No UI/keyboard/mouse, private uploads, model downloads, plugins, FLP or host actions.
- Inferred notes remain distinct from official-MIDI facts. All writer/quality gates blocked.
- Source input remains existing MoE qualified integer-WAV producer scope. Current MoE
  verify_pcm_decode rejects encoded-decode receipts; compressed MoE support needs its
  own source-witness slice, not an accidental format claim here.

## Review Focus

1. Program100 is SingingVoice in this model, not proof of GM100 routing.
2. More than15 melodic programs: separate files; never alias channels across instances.
3. Same-key FIFO nesting or collapsed/over-source notes: reject; no trim/shift/drop.
4. Cancellation or producer/backend/decoder/output change: no completion marker.
5. Negativezero/binary64 provenance, empty13addresses, all decoder errors retained.
6. Real MoE has22738 payload members; retained guards explicitly use backend30000/4GiB
   bounds. Generic snapshot default20000 stays unchanged; both per-root budgets frozen,
   full membership/hash checks retained. Payload-only probes never qualify stale backends.

### Task 1: Pure projection, per-program encoding and independent SMF checks

**Files:** new core/moe_midi.py, arrangement/moe_midi.py, validator/smf_notes.py,
validator/moe_midi.py; modify validator/midi_preview.py and pipeline/estimated_midi.py
recipe to retain the factored parser dependency. Original tiny unit fixtures only.

**Interfaces:** core typed inputs snapshot producer FI + YourMT3MoECandidate,13 channel
note/error snapshots and99-entry fixed program vocabulary; typed score/parts/note-source
indices, onset/offset bits, PreviewBoundary audits, output receipts and recipe.
project_moe_midi(inputs)->MoEMidiScore; encode_moe_part(part,end_tick)->bytes;
verify_moe_part(raw,part,end_tick)->None. Pure functions perform no I/O or backend calls.

- [ ] RED: all13addresses/source order; program100 metadata; same sourcechannel multiple
  programs in independent parts; exact binary64 including−0.0; half-tick1/256s rounds8;
  drumchannel9 vs other0; nativevelocity retained, explicit fixed96preview; empty source.
- [ ] RED: note beyond originalsource, nested same-key durations, positive tick collapse,
  wrong program/address/bool or nonfinite data, >20000notes rejected without dropping.
- [ ] Implement: groups sorted(channel,program), source note index order retained;
  technical960PPQ/500000us, independent nearest-half-up, exact rational signed errors
  <=3125/12us. Audio end ceil to technicaltick; notes cannot exceed original duration.
  Parts contain only nonempty groups; source snapshot still preserves all13 addresses.
- [ ] RED then implement: two-trackSMF per part (clock+notes), no program/CC/bend/timesig
  messages, exact technical labels, sourceend EOT; complete framing/VLQ/7bit/meta checks
  and decoded semantic comparison. Tampered program labels/header/EOT/tail fail.
- [ ] Factor old strict parser without changing old5-track verifier behavior; add parser
  to old recipe so legacy artifacts are not silently promoted across code changes.
- [ ] GREEN all new tests plus existing estimated-MIDI/strict raw-SMF tests; commit task.

### Task 2: Retained producer evidence, exclusive file workflow and CLI

**Files:** modify validator/yourmt3_moe.py to expose a verified source receipt while
preserving old public verifier return types/behavior; new pipeline/moe_midi.py and
src/suno2flp/cli_moe_midi.py; register in src/suno2flp/cli.py; unit file-workflow/CLI tests.

**Interfaces:** collect_verified_moe(path)->owned verified producer/native/backend
receipt plus recheck closure, preserving the existing complete token replay;
export_moe_midi(report,output,*,should_cancel=None)->MoEMidiExport;
verify_moe_midi_export(report,*,should_cancel=None)->MoEMidiExport.
Commands export-yourmt3-moe-midi and verify-yourmt3-moe-midi.

- [ ] RED: unsafe/existing output rejected before expensive producer calls; Single,
  fake raw/producer, unresolved generations, wrong sourceclock rejected.
- [ ] RED: source/raw/backend runtime/payload membership, code/mido, output bytes,
  manifest paths or occurrence-index changes; cancellation before/during publication;
  unsupported old profile refused. No completion JSON after failure; old outputs stay.
- [ ] Implement bounded owned snapshot and independent producer/token verification
  once, not neural inference. Retain backend/runtime/artifact/adapter and source
  identities through a frozen recheck closure; do not weaken any old source guard.
- [ ] Snapshot native notes + fixed vocabulary into core inputs; preserve raw producer
  and all native generation/error evidence by identity. Freeze input/recipe JSON before
  callbacks. Compare rebuilt canonical snapshots/explicit bits, not float equality alone.
- [ ] Exclusive notes/modelch-XX-program-YYY.mid files; verify every file, exact folder
  inventory, source occurrence mapping, complete projection and current source witnesses.
  Write companion explanation BEFORE atomic completion; retain pending record and publish
  completion last. No rejecting operation after marker; test companion-write failure.
- [ ] Verifier rebuilds from current producer, checks complete part inventory and all
  files/receipts/code identities, retaining recheck through publication/replay.
- [ ] Status always unqualified_candidate; technical clock, fixedvelocity, inferred
  roles, music/routing/host/FLP/job blockers explicit. No existing writer invoked.
- [ ] GREEN offline contract/CLI tests, then commit task.

### Task 3: Current-source native evidence, package, docs and exact-head PR

**Files:** docs/MOE_MIDI.zh-CN.md, ARCHITECTURE, README, roadmap and integration limits;
original synthetic installed smoke/opt-in tests as appropriate. No private assets.
Actual runtime evidence also requires additive per-root file budgets in
src/suno2flp/core/inference_snapshot.py and tests/unit/test_inference_snapshot.py,
with explicit30000 only in MoE's retained source collector; generic defaults unchanged.

- [ ] Freeze final appsource before native qualification. New backend in isolation using
  existing fixed100 local artifacts; no downloads. Old backend/results stay untouched.
- [ ] Re-run full original175s MoE on current source; compare all semantic tokens,
  notes/events/errors to frozen old producer, keeping new runtime stats separate.
  Export via normal new API, independently import and compare all23files/7670notes,
  exact timing audits and protected input identities; replay through actual installed CLI.
- [ ] Retain program100/model-label warning, no GMprogram messages, positive/negative
  error audits and sourceaudio origin. Do not route inferred files through faithful-MIDI
  writer automatically or claim music/host/GUI acceptance from MIDI success.
- [ ] uv sync --locked; pytest/Ruff/format/mypy; build and installed CLI/help/privacy
  smoke. Default suite offline; native test explicit opt-in with missing prerequisites skip.
- [ ] Fresh whole-head independent review, four current CI matrix names/all8runs green,
  currentmain/protection/discussion/whitelist checks then matched-head squash auto-merge.
  Read actual merge SHA/tree and preserve private experiment/source identities.

Self-review: this is one M2 editable-preview slice, not full delivery. Main unresolved
requirements (music/corpus, role audio routing, FLP, tempo/structure, GUI, install/host)
remain in the product roadmap; no goal completion or narrower release definition.

## Exact file and type map

All core/arrangement/validator/pipeline paths above are under src/suno2flp/.
New tests: tests/unit/test_moe_midi.py, tests/unit/test_moe_midi_files.py,
tests/unit/test_cli_moe_midi.py; existing parser regressions stay in their current files.
Core contracts: MoEMidiChannel(channel,notes,decode_errors,merge_errors); MoEMidiInputs
(producer:FileIdentity,candidate:YourMT3MoECandidate,model_channels:13channels,
program_channels:dict[int,YourMT3MoEProgram] with99entries); MoEMidiNote(source_index,
native:YourMT3Note,onset_bits,offset_bits,start:PreviewBoundary,end:PreviewBoundary);
MoEMidiPart(source_channel,model_program,instrument_group_hint,midi_channel,notes);
MoEMidiScore(inputs,parts,source_end_us,end_tick,all explicit fixed policies/blockers);
MoEMidiFile(source_channel,model_program,midi:FileIdentity); MoEMidiExport(root,score,
files,source_backend:YourMT3MoEBackend,recipe:ScoringRecipe,mido_version).
Source snapshots are owned copies; explicit nativebits and canonical snapshot comparisons
preserve negativezero, not float equality alone. Synthetic fixtures use current static
model vocabulary, no weights/backend/real songs.

Task1 test command: uv run pytest tests/unit/test_moe_midi.py -q
plus the existing estimated-MIDI/raw-SMF tests identified by source search. Expected: allpass.
Task2 command: uv run pytest tests/unit/test_moe_midi.py tests/unit/test_moe_midi_files.py
tests/unit/test_cli_moe_midi.py -q . Expected: allpass.
Task3 commands are the repository locked/full/build checks above; Expected: zero exit,
explicit conditional integration skips, no private archive members; final reviewedhead
all8CI completedSUCCESS.
