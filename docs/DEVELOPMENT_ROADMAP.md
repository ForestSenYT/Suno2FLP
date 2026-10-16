# Development roadmap

Latest [control evidence slice](FL26_CONTROL_EVIDENCE.zh-CN.md): selected event-223
integer/REC observations, 14 private background renders, source-replayed scalar error
and route assessment, and synthetic regressions are implemented. Exact FL26 step timing
and instrument/port routing remain blocked; real-song FLP delivery is not complete.

| Phase | Deliverable | Acceptance gate |
| --- | --- | --- |
| 0 — Bootstrap (complete) | Package, contracts, config, CLI, local discovery, tests, CI, evidence | Offline tests and installed CLI pass; integration limits explicit |
| 1 — MIDI importing and cleanup (initial slices implemented) | Track-aware import and opt-in duplicate/short-note filtering and onset quantization | Synthetic multitrack/cleanup fixtures; originals and change history preserved |
| 2 — Arrangement and mapping (faithful/mapping slices implemented) | Faithful arrangements with PPQ/map policy and explicit channel-preserving role hints; reinterpretation remains planned | Note/event/provenance preservation, precision/conflict and mapping fixtures verified |
| 3 — FLP templates (restricted writer implemented; private real input blocked) | Inventories/readiness, explicit-policy native FL26 encoder, independent structural round trip and exclusive Windows output bundles | Eligible real reference/dependencies and independent FL Studio open/readback/listening still required |
| 4 — MCP control (real server discovery audited; host adoption pending) | Pinned protocol discovery and bounded stdio, with actual backend/host work still gated | Actual authorized backend handshake, tool inventory, readback and recoverable mutations |
| 5 — Quality and automation (offline slices implemented) | Current-source replay, reproducible JSON preparation and explicit PCM numerical comparisons | Genuine host render/listening and final musical acceptance remain required |

Implemented Phase 1 slice: `MidiFileImporter` and `import-midi`, including Type 0/1 PPQ
tracks, tempo/meter provenance, source event order, original note ticks and diagnostics.
The next slice adds `DeterministicMidiProcessor` and `clean-midi` for explicitly
selected derived-note cleanup, retaining all source events/timing and before/after
audits. See [MIDI import](MIDI_IMPORT.md) and [cleanup](MIDI_CLEANUP.md).
Type 2/SMPTE, AI inference and MIDI binary export are not implemented.

The first Phase 2 slice implements `FaithfulArrangementEngine` and `arrange`, consuming
imported notes by default or explicitly selected active/cleaned notes. It preserves
full provenance, uses exact common PPQ by default, and rejects unresolved timing maps.
See [arrangement rules](ARRANGEMENT.md).

The next Phase 2 slice adds validated role catalogs, exact input/track/channel rules,
`ExplicitInstrumentMapper`, `map-instruments` and `arrange --instruments`. Mapping records
preserve config provenance; source channels/events stay unchanged, with all plugin
hints explicitly unverified. See [mapping rules](INSTRUMENT_MAPPING.md).

The first Phase 3 slice completed the [read-only compatibility assessment](FLP_BACKEND_ASSESSMENT.md)
and [backend comparison](FLP_BACKEND_ALTERNATIVES.md). Music2DAW commit
`6def9463d6fa8636bbc81010581318a39c47d3c4` is the experimental candidate; source
support is verified, not runtime/template compatibility. No authorized FLP was available
and FL Studio was not discovered in standard locations. Tempo/meter maps, source MIDI
channel semantics and exclusive-output safety need explicit restrictions or adapter work.

The next [Phase 3 slice](TEMPLATE_INSPECTION.md) implements exact-SHA isolated CLI
provisioning, read-only inspection with source/backend hashes, explicit prerequisite
errors and offline/opt-in synthetic tests. Actual local provisioning and synthetic
inspection passed; no existing template or FLP was edited. The earlier assessment's
unexecuted-backend status is historical; real template/DAW compatibility remains open.

The subsequent [binding/planning slice](BUILD_PLANNING.md) implements explicit indexed
source-to-template bindings and dry-run previews with exact PPQ and capability checks.
It preserves full provenance and records blocked cases without enabling execution.
No source channel/role inference, FLP write or plugin loading occurs.

The next [inventory slice](TEMPLATE_INVENTORY.md) adds original read-only note, clip,
automation and crop inventories with raw bytes/float bits and file/event provenance.
Dry-run v2 requires inventory evidence, cross-checks current bytes and backend counts,
and blocks conflicting inherited content, automation, crops and ambiguous encodings.
No writer or implicit content-clearing policy is introduced.

The [FL26 slice](FL26_READ_ONLY.md) reads exact 26.1.7.5654 event-172 and 88-byte
playlist layouts, preserves raw/profiling evidence and flags misleading successful
backend summaries. A private user-created real template is now verified read-only
with unchanged hashes/mtime. Opaque semantics, playback and writer gates remain open.

The [readiness batch](FL26_READINESS.md) adds a hash-linked selected-declaration manifest,
explicit unresolved-note/crop/extension evidence, process-free current-file checks and
local source-to-template binding/PPQ previews. It retains full inspection/source
snapshots without repairing the backend summary. The [writer design](FL26_WRITER_DESIGN.md)
defines eligibility, immutable edit intent, byte preservation, exclusive staging and
independent reparse/host acceptance. That first batch introduced no encoder or copied FLP.

The next [writer batch](FL26_WRITER.md) implements that restricted native encoding/
verification surface and guarded new bundle publication, with separate explicit policy
and edit-intent contracts. Old read-only reports cannot authorize execution. Authored
synthetic fixtures exercise positive writes; the original private template is verified
as blocked without output. No upstream backend is modified or called for writing.

Remaining before a usable real output: obtain independent host evidence for unknown
note/crop/extension semantics or a later suitable original reference; confirm dependency
versions/availability and production instrument/content intent, resolve backend and
inventory disagreements, then meet the new strict policy gates. Real FL Studio open/
readback/listen acceptance remains required. Unsupported cases fail explicitly.
Reinterpretation and automatic instrument selection remain future work. AI transcription remains
an opt-in fallback for absent/unreliable MIDI and must record uncertainty/provenance.
No audio reconstruction, instrument loading or DAW control is implemented.

The next [saved-bundle verification slice](FL26_BUNDLE_VERIFICATION.md) provides a
read-only `verify-flp-bundle` command, reconstructing all current originals and checking
the output independently after publication. It rejects stale/forged evidence without
writing, launching a process or changing host compatibility. The same document records
the separate real-reference and manual host observations still needed before Phase 3
can be accepted. Phase 4 now has the separate offline discovery boundary described below;
real backend/host adoption remains pending.

The [noninteractive performance preparation](NONINTERACTIVE_PERFORMANCE.zh-CN.md)
compiles/replays all source events and exact elapsed times before encoding, exposing
PPQ loss, scalar tempo precision and untranslated control/routing requirements.
This is an implemented prerequisite, not completion of variable-tempo FLP generation.
A separate local background-render experiment succeeded on existing reference copies;
noninteractive MIDI import/save, full automation semantics and real-song acceptance
remain unresolved. No writer gate is relaxed by a successful requirements report.

The [MIDI round-trip evidence slice](MIDI_EVENT_COMPARISON.zh-CN.md) adds offline exact
event/clock comparison and saved-report replay. Private background tests narrow selected
MIDI Out/LSD port and volume behavior, but a one-tick timing compensation changes host
MIDI event positions and cannot preserve the source. Complete exact-tempo/control song
delivery remains blocked; program routing, old template gates and audible acceptance
are still required.

The [isolated FL26 backend adaptation](FL26_BACKEND_ADAPTATION.md) adds an explicit
inspection-only build from the same upstream pin, with source/recipe/artifact hashes.
It fixes demonstrated exact-build event-172 and event-233 stride parsing in a separate
private installation, preserving the old result and writer restrictions. The actual
adapted process agrees on the private input's selected summary facts; unknown field/
host semantics remain open. Follow the [Chinese reference guide](FL26_REFERENCE.zh-CN.md)
to create the next independent host observation input.

The [independent field-evidence slice](FL26_FIELD_EVIDENCE.md) uses a new GUI-created
positive reference and separately saved one-change crop/Slide probes. It distinguishes
the whole observed ordinary positive-note attributes and assessed Pattern integer crop
endpoints. Native writing may preserve reviewed ordinary attributes; Slide, crop
replacement/resizing, unknown events, incomplete inventory and host/listening acceptance
stay blocked. No private template/reference or backend is distributed.

The [offline crop/flag regression slice](FL26_CLIP_OFFLINE.md) adds authored synthetic
boundary tests and a private change-budget audit while host control is paused. Six
experimental candidate files have no host-open/resave/reopen results; these stages
remain pending. Runtime eligibility, crop writes and nonzero clip flags are unchanged.

The [manual host-validation preparation](FL26_MANUAL_VALIDATION.zh-CN.md) supplies a
six-candidate checklist and blank result form, separating view zoom from a fixed-left
right-edge length experiment and requiring new A/B saves plus fresh-session reopens.
Local prepared forms contain provenance/planned values only. No host actions or FLP
writes occur in this documentation slice; all pending results and writer gates remain.

The [offline manual-record checker](FL26_RECORD_CHECKS.zh-CN.md) adds versioned JSON
companions, pinned file/evidence checks and JSON/Markdown summaries for all six probes.
Intact pending records differ from invalid claims; reported completion never verifies
the host or authorizes writes. No backend/DAW invocation or FLP mutation is introduced.

The [offline readiness batch](OFFLINE_ACCEPTANCE.zh-CN.md) adds independent current-source
arrangement replay, new JSON preparation bundles and full saved-run reconstruction,
discovery-only MCP lifecycle/stdio with original synthetic peers, and aligned integer
PCM measurements with explicit numerical thresholds. CI also checks the installed
wheel lifecycle against locked runtime dependencies. This completes these offline
components, not real-template compatibility or whole-project host acceptance.
