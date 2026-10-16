# Architecture

## Current design — foundations, MIDI import/cleanup and faithful arrangements

Official Suno MIDI is the primary musical source; stems provide future references
for timing, instruments, and validation. Deterministic processing is independent
of optional AI inference. Core operations run without a DAW or network connection.

```text
MIDI + WAV -> LocalAssetImporter -> AssetManifest -> LocalQualityValidator
MIDI      -> MidiFileImporter   -> ProcessedMidi (original timing and events)
                                     |
                         DeterministicMidiProcessor (opt-in cleanup)
                                     |
                            FaithfulArrangementEngine
                                     |
                                Arrangement
                                     |
                             future FLPBuilder
                                     |
                             optional DAWController
                                     |
                           future rendered validation
```

## Responsibilities and contracts

| Module | Responsibility | Current implementation |
| --- | --- | --- |
| core | Pydantic contracts, YAML configuration, errors, path guards, doctor | Implemented |
| importer | Discover/match assets; read track-aware MIDI | Local metadata and MidiFileImporter |
| midi_processor | Derive cleaned notes, retain source events/timing and audit | DeterministicMidiProcessor implements MidiProcessor |
| arrangement | Build DAW-independent arrangements and explicit role annotations | FaithfulArrangementEngine and ExplicitInstrumentMapper; reinterpretation remains planned |
| flp_builder | Inspection, planning and guarded template outputs | DryRunBuildPlanner, readiness and explicit restricted native FL26 file workflow; generic FLPBuilder remains a protocol |
| daw_controller | Connect, discover actual MCP capabilities, disconnect | Protocol only |
| validator | Validate metadata and expected track/note event counts | Basic structural checks |
| integrations | Translate backend-specific transport, schemas, paths, units, errors | Explicit pinned Music2DAW provisioning and read-only CLI inspection |
| cli | Compose services and present results/exit codes | Explicit workspace/MIDI/inspection/planning/assessment commands |

`core/models.py` is the shared contract source. Versioned manifests contain an
absolute input root, relative asset paths, metadata, conservative filename matches,
and diagnostics with severity/code/path. Repeated inspection of unchanged input has
stable ordering and no timestamp noise. Manifests currently record sizes, not content
hashes; cache/reuse of assets still needs content hashes. Track-aware MIDI import
separately records a SHA-256 of the source bytes it actually parsed.

`ProcessedMidi` now carries a versioned read-only import result: format, PPQ, source
reference/hash, ordered tracks and decoded events, tempo/meter source locations,
original and current note timing, diagnostics and an optional cleanup record.
An absent cleanup record means import only.
`MidiFileImporter` builds it from a single byte snapshot without writing MIDI.
All musical coordinates are integer
ticks at the representation's explicit PPQ; channels use MIDI's 0–15 convention.
Arrangement conversion uses exact integer/rational arithmetic with explicit precision policy.
`Arrangement` has an explicit mode, musical metadata, tempo/meter maps, notes and
instrument hints. These schemas do not assert processing has occurred.

Track-aware import details, note pairing, timing defaults, conflict policy and
unsupported formats are specified in [MIDI_IMPORT.md](MIDI_IMPORT.md).
`DeterministicMidiProcessor.clean` deep-copies an imported representation before
changing derived notes. All operations default off. `process` implements the existing
Asset/source-root/preferences protocol using a fresh contained import. Cleanup options
are shared Pydantic contracts inherited by YAML `MidiPreferences`. A versioned cleanup
record stores exact options and before/after note snapshots with original indices.
The source event stream remains the authority for originals; downstream arrangement
code must explicitly choose the derived `notes` view. See [MIDI_CLEANUP.md](MIDI_CLEANUP.md)
for ordering, reprocessing and quantization semantics.

`FaithfulArrangementEngine` implements `ArrangementEngine`. It aligns every selected
input at beat zero, keeps tracks separate/in order and retains note pitch/channel/
velocity. `ArrangementOptions` chooses imported/active notes, target PPQ, rounding
and optional timing authority. Default PPQ is the source LCM; precision loss fails
unless explicitly allowed. Tempo/meter functions are compared in rational beats
before conversion, including initial MIDI defaults and the intervals between changes.
Unresolved map conflicts fail. Explicit authority retains ignored evidence and warnings.

`Arrangement.sources` contains independent `ProcessedMidi` snapshots with source hashes,
events, original ticks, selected view and cleanup audits. Tracks identify input index,
source track index/position and source PPQ. `note_origins` maps each arranged note to
the selected source-view note and its input timing. Current note ticks use arrangement
PPQ; original note fields retain source units. Canonical maps identify input/track/event
provenance; synthesized initial defaults are labeled. `build_options` and algorithm
version record reproducibility choices. See [ARRANGEMENT.md](ARRANGEMENT.md).

`ExplicitInstrumentMapper` is a separate metadata-only stage, invoked explicitly or
through `arrange --instruments`. It resolves input/track-position/channel selectors
against source snapshots, validates channel provenance, rejects ambiguous/overlapping
rules and deep-copies the arrangement. Per-channel `instrument_roles` store role IDs,
GM/plugin/percussion hints and unverified plugin status. `InstrumentMappingRecord`
retains the complete config document, byte hash/path when loaded, rule matches and
unmapped targets. Source notes, channels, raw programs/events, timing and provenance
remain unchanged. YAML loading uses the existing safe duplicate-key-rejecting loader.
There is no instrument inference, plugin loading or channel routing. See
[INSTRUMENT_MAPPING.md](INSTRUMENT_MAPPING.md).

`BackendCapabilities` distinguishes available, unavailable and unverified, with
operations, constraints and evidence. `BuildResult` is reserved for a backend that
actually created and verified a file; no implementation currently produces it.
`ValidationReport.valid` derives from error diagnostics, avoiding inconsistent status.

Phase 3's [read-only assessment](FLP_BACKEND_ASSESSMENT.md) recommends a pinned,
separately provisioned Music2DAW CLI candidate. The subsequent
[inspection slice](TEMPLATE_INSPECTION.md) implements explicit provisioning and the
read-only `TemplateInspector`, with synthetic real-backend execution. A user-created
FL26 template now has read-only byte evidence; MCP/FL Studio playback remain unverified.
Its single-tempo/template edit surface cannot consume our
full timing maps or source-channel semantics directly. A future adapter must explicitly
bind source identities to existing FL structures, enforce exact template-PPQ conversion
and exclusive output safety, and preserve the complete provenance sidecar. Unsupported
maps/events must be rejected. Current configuration remains `flp_backend: none`.

`core/backend_models.py` owns versioned provisioning/header/inspection evidence.
`integrations/music2daw_provision.py` builds only the exact reviewed CLI in a new
private directory, with SDK/package locks and file hashes; Python never imports the
GPL backend. `integrations/music2daw.py` validates the record/artifacts and header,
calls only `dotnet <dll> inspect <template>`, validates the typed summary and checks
template/backend hashes after success or process failure. The report always marks
compatibility unverified. Domain failures carry stable codes; no `BuildResult` is
produced. These hashes do not authenticate an externally edited installation record.

`core/build_models.py` defines hash-pinned, one-to-one source/template bindings and
`DryRunBuildPlan`; `core/build_config.py` loads safe YAML with exact-byte provenance.
`DryRunBuildPlanner` is pure: reconstruct faithful music/role provenance from snapshots,
resolve exact active-channel targets, assess the pinned subset and convert endpoints
to template PPQ with no rounding. Parts retain source channel/origin and independent
full snapshots. Capability violations block; all plans remain non-executable and
compatibility-unverified because inventories cannot prove all final event semantics,
plugin rights or playback.
`planning_files.plan_build_files` verifies current backend/template hashes before/after
the pure plan, regenerates inventories and records input-file byte hashes; CLI writes only new JSON.
See [build planning](BUILD_PLANNING.md). No backend edit request or BuildResult exists.

`core/template_inventory.py` owns byte-linked records, encoded float evidence and
JSON consistency checks. `integrations/template_inventory.py` is an original pure
reader of known event/record layouts, not a writer or imported backend parser.
Inspection scans its initial byte snapshot before launching the pinned inspector.
`flp_builder/_planning_template.py` checks inventory/summary agreement, inherited
content, repeated events, known automation, crop/mute/attribute risks and encoded ID
limits. V2 plans retain the complete inventory, fingerprint and target-row indices.
Unsupported layouts remain partial/unsupported; see [inventory limits](TEMPLATE_INVENTORY.md).

`core/template_profiles.py` defines exact read-only FL25/FL26 widths and strides.
Inventory v2 stores selected profiles and raw event headers/rules; 88-byte clips keep
opaque extensions. `core/template_summary.py` derives selected-family local facts and
compares the original backend result without replacing it. Inspection retains both;
planning validates the comparison and always blocks FL26 writer use. See
[FL26 scope and actual input evidence](FL26_READ_ONLY.md).

`core/assessment_models.py` owns permanently non-executable readiness contracts.
`integrations/template_dependencies.py` reads selected declaration text/state evidence
without resolving external paths. `flp_builder/assessment.py` combines current byte
evidence with unresolved semantic/writer gates; `assessment_bindings.py` checks local
targets and exact source coordinates independently of backend omissions, retaining
full snapshots. `assessment_files.py` rechecks template hash/mtime and backend artifacts
on success/failure without a process. CLI `assess-template` creates only new JSON.
See [readiness](FL26_READINESS.md) and the documentation-only
[writer architecture](FL26_WRITER_DESIGN.md). Existing build eligibility is unchanged.

`core/writer_models.py` adds policy, explicit intent, source-file evidence and structural
verification/bundle contracts. `writer_intent.py` reconstructs current music/evidence
and enforces a strict original writer allowlist. `fl26_codec.py` only replaces explicit
note/playlist/fine-tempo payloads; `fl26_verify.py` independently frames output and
checks expected fields/counts plus exact untouched bytes. `writer_io.py` owns new-file,
path and Windows no-replace primitives; `writer_files.py` reimports source MIDI/replays
cleanup, checks all inputs/backend and verifies staged/final bundles. New CLI commands
are `plan-flp-write` and `build-flp`; old preview eligibility is never widened. See
[restricted writer](FL26_WRITER.md). No host compatibility is asserted.

`bundle_verification.py` adds a read-only saved-bundle entry point. It checks canonical
sidecars, reconstructs complete current-file intent/provenance, independently reparses
the output, then rechecks originals/backend and bundle identities/bytes. It never
encodes, publishes, repairs or launches a process. `verify-flp-bundle` returns only
structural verification; [host acceptance](FL26_BUNDLE_VERIFICATION.md) remains external.

`core/backend_adaptation.py` owns an original source-hash-guarded two-edit recipe.
`integrations/music2daw_adaptation.py` applies it only in a new external checkout and
verifies original/adapted source, recipe and notice fingerprints. The optional backend
manifest adaptation declaration preserves legacy serialization when absent. Explicit
`--fl26-read-only` provisioning changes only that checkout's parser; inspection restricts
inputs to the exact assessed build and aligned event-233 records. Actual process output
is still compared independently with local inventory; no summary substitution occurs.
See [scope and remaining semantics](FL26_BACKEND_ADAPTATION.md).

`core/fl26_fields.py` adds exact-profile pure observations from independent host
references. Readiness findings distinguish the whole ordinary/Slide note form and
Pattern integer crop endpoints without changing legacy inventory JSON/float projections.
The restricted writer permits preserving only complete ordinary positive-note attributes,
with existing prototype hashes and independent byte checks; crop-write, Slide and unknown
field gates remain. See [field evidence](FL26_FIELD_EVIDENCE.md).

## Safety and error handling

Workspace names are portable simple names; Windows device names are rejected.
`init-project` exclusively creates a new root and never reuses an existing directory.
If creation fails halfway, partial files remain for inspection; no recursive cleanup
is attempted. Config paths are relative, contained, and mutually non-overlapping.
Validation resolves links and rejects escaping or overlapping resolved paths.
Configured templates are read-only references, outside generated directories.

Discovery opens media read-only. Linked files/directories are skipped, including
Windows junctions. Unique case-insensitive filename stems can match MIDI files to
WAVs; duplicate candidates produce warnings rather than guesses. This is file-level
matching, not semantic matching of tracks inside multitrack MIDI.
Explicit `import-midi` accepts a user-selected readable file path and resolves it;
it does not perform directory discovery. JSON outputs use exclusive creation.

WAV metadata uses standard-library `wave`: PCM formats supported by the runtime,
not every WAV codec. Headers alone cannot establish integrity of all sample data.
MIDI uses mido; SMPTE timing is rejected by the positive PPQ metadata contract.
No waveform decoding, tempo inference, transcription or MIDI binary writing is performed.
Very large/untrusted files are not resource-isolated; use trusted local exports.

Domain failures inherit `Suno2FLPError`. Discovery reports per-file errors and continues.
Track-aware MIDI parsing failures/unsupported timing raise `MidiImportError`; recoverable
note/map issues appear in its result diagnostics with track/event indices.
`MidiProcessingError` rejects error-bearing imports, missing/modified original timing,
or attempts to change an already recorded cleanup pipeline without reimporting source.
`ArrangementError` rejects unsupported modes, missing provenance or unrepresentable
PPQ conversion; `TimingConflictError` handles disagreeing maps and conversion collisions.
`InstrumentMappingError` rejects invalid source links, unmatched/overlapping rules,
unsupported modes and attempts to overwrite existing mapping provenance.
CLI failures return nonzero status. Optional missing tools
do not make `doctor` fail. Package logging uses standard Python logging; configuration
selects the project logger level, and command results remain separate from logs.

## Extension boundary

Adapters depend inward on core contracts. Core never imports an upstream DAW/AI
runtime. Prefer a separately provisioned process and versioned JSON/files for heavy
or incompatible dependencies. MCP adapters must handshake and list actual tools;
tool names are backend-specific. Future mutations require snapshots, exclusive output,
source/template hash checks, parse/readback, then FL Studio listening verification.
No complete MIDI-to-FLP backend has been established.
