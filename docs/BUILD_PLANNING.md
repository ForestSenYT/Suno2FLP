# Explicit template bindings and dry-run build planning

This Phase 3 slice generates deterministic, non-executable JSON previews from a
faithful arrangement, saved template inspection and explicit binding YAML. It performs
no FLP writes, backend invocation, export, launch, plugin loading or MCP actions.
`FLPBuilder.build` remains unimplemented and project defaults stay disabled.

## CLI

```powershell
uv run suno2flp plan-build arrangement.json --inspection inspection.json --bindings bindings.yaml --backend-dir .tools/music2daw-6def9463d6fa-inspect --output plan.json
```

Create the arrangement and inspection through the existing commands first. Planning
needs their JSON, binding YAML, original template bytes and complete provisioned backend
inventory. It verifies current template size/hash and backend record/artifacts against
inspection both before and after planning. No .NET/Git executable, network access or
running DAW is required for this step, and no implicit inspection/provisioning occurs.
Stale/missing/modified evidence fails before a plan output is created.

Without `--output`, stdout is JSON. Report destinations must be new `.json` files with
existing parents, outside the backend directory. Existing files, symlinks and NTFS
alternate streams are refused. Invalid configuration, selectors or provenance fail
with exit 1 and no output. A valid-input **blocked** plan is deliberately written for
review and returns 1; `review_required` returns 0. Neither status permits execution.
Invalid CLI arguments return 2.

## Binding YAML and identity

```yaml
schema_version: 1
backend_revision: 6def9463d6fa8636bbc81010581318a39c47d3c4
# Use inspection.template_sha256_after, not a filename or role-catalog hash.
template_sha256: "0000000000000000000000000000000000000000000000000000000000000000"
bindings:
  - source_input: 0
    source_track_position: 1
    source_channel: 2
    template_channel_id: 0
    template_pattern_id: 0
    template_playlist_track: 4
```

Replace the illustrative all-zero hash with the exact inspected template SHA-256.
All selectors/IDs are strict zero-based integers; booleans, names, roles, wildcard
selectors, coercion and unknown keys are rejected. The backend revision and template
hash are mandatory; they cannot be inferred. YAML uses the duplicate-key-rejecting safe
loader. `TemplateBindingDocument` retains resolved YAML path, hash of the exact bytes
parsed and a complete independent config snapshot. Programmatic documents can omit
path/hash; no file identity is fabricated.

| Field | Meaning / bounds |
| --- | --- |
| `source_input` | Recorded arrangement input index, >=0 |
| `source_track_position` | Position in that input's selected-view `midi.tracks`, >=0; not track display name or flattened arrangement index |
| `source_channel` | Explicit original MIDI channel 0..15 with at least one active selected-view note |
| `template_channel_id` | Existing inspected FL rack channel ID, 0..255 (note-record byte limit); not a MIDI channel or GM program |
| `template_pattern_id` | Existing inspected zero-based Pattern ID, 0..65534; not raw FLP's one-based delimiter |
| `template_playlist_track` | Explicit destination lane 0..499 under the assessed FL25 layout; no instrument inference |

The first slice is strictly one-to-one: duplicate source tuples, reused template rack
channels, Patterns or playlist lanes fail. Intentional merging/layering and sharing a
Pattern across bindings require future policies; this prevents accidental duplicated
playback and provenance collapse. Repeated names and multiple source inputs do not
change indexed selection. The source channel remains in every planned note and the
unchanged arrangement; the destination is separately recorded, never substituted into
source MIDI. Instrument-role/GM/plugin hints remain unverified annotations.

Every active source channel must be bound. Missing bindings produce a blocked plan
with `unbound_sources`; supplied rules selecting missing/inactive sources or nonexistent
template channel/Pattern IDs are invalid inputs. Empty/conductor tracks and channels
whose notes were all explicitly cleaned away require no binding; their raw events and
cleanup history remain in the full source snapshots.

## Exact timing and capability subset

`DryRunBuildPlanner` reconstructs the arrangement from its recorded source snapshots,
selected note views and build options, then checks tracks, notes/origins, tempo/meter
maps, PPQ, source links and role-mapping audit against that reconstruction. Missing
provenance, unrecorded edits/assignments, error-bearing inputs, inconsistent inspection
path/header/hash or a different binding template hash fail. Generic `instrument_hint`
metadata may remain unchanged without affecting musical reconstruction. This checks
internal consistency, not authenticity of externally edited JSON or cleanup audits.

For each binding, previews place one clip at beat zero. Notes keep their arrangement
positions and durations. Convert each start, end and retained track end exactly using
`tick * template_ppq / arrangement_ppq`; calculate duration from converted endpoints.
Clip length retains the converted track end or later note endpoint. No offset, trim,
loop, merge, quantization or rounding is introduced. Even an inexact original trailing
track tick blocks conversion after cleanup. Positive notes cannot collapse; converted
coordinates/lengths must fit signed 32-bit integers. A failed part has `notes: null`
and `clip_length_ticks: null`, never a partial or approximated preview.

The current profile `music2daw-6def9463-dry-run-v2` is **source-assessed**, pinned to the
same backend revision as inspection. It is not negotiated writer availability.
The [backend assessment](FLP_BACKEND_ASSESSMENT.md) records the pinned upstream
request, editor and parser sources behind these conservative checks.
The [FL26 reader](FL26_READ_ONLY.md) does not widen this writer capability subset.
Its inventories always block with `template_read_only_profile`; inconsistent backend
summaries add `template_backend_summary_untrusted`. Stored local/comparison evidence
must agree with the inventory or provenance validation fails.
The separate [readiness assessment](FL26_READINESS.md) can check proposed local IDs
despite these backend omissions. It reports only target/coordinate evidence; it does
not promote local targets into the backend summary or bypass any planning/writer gate.

| Check | Current behavior |
| --- | --- |
| Tempo | One effective constant value; exact integer milli-BPM `60000000000 / microseconds_per_beat`, >0 through 999000; no rounding to 0.001 BPM |
| Meter | Only one constant MIDI-default 4/4 tuple (4,4,24,8); no meter-writing API |
| Source events | Note events plus an explicit metadata allowlist; CC/sustain, pitch bend, program changes, aftertouch, sysex and other unsupported types block with input/track/event provenance |
| Notes/provenance | Positive duration/velocity 1..127; source hashes required; unclosed/unmatched source notes block rather than silently disappearing |
| Template version | Only upstream-assessed FL `25.1.2.4896` enters this preview subset; a successful parse of another build is insufficient |
| Targets | Existing IDs and exact Pattern/channel note records, enabled/non-sequenced generator evidence, one assessed playlist, representable encoded Pattern IDs and no conflicting inherited content; see inventory rules |

Allowed metadata types are track/instrument names, text, copyright, marker, cue marker,
lyrics, end-of-track, set-tempo, time-signature, key-signature and sequence-number.
These raw events remain in the sidecar; the preview does not imply their translation
to native FL events. Unsupported events are checked in all retained source tracks,
including cleaned inputs. Explicit arrangement timing-authority/rounding choices remain
recorded; this stage adds no new override or approximation.

The [inventory slice](TEMPLATE_INVENTORY.md) now retains byte-linked notes, clips,
automation and crop bits and checks them against the backend summary. It blocks
unsupported/unknown evidence, unbound content, automation, crops, muted clips and
ambiguous event/Pattern encodings. Exact final event, plugin and track semantics are
still unverified. Every plan therefore retains `template_structure_unverified`,
`template_compatibility_unverified` and `writer_disabled` warnings. Rights, samples,
plugins, source-to-instrument sound fidelity and real FL Studio playback remain open.

## Plan evidence and API

```python
from suno2flp.core.build_config import load_template_bindings
from suno2flp.flp_builder.planning import DryRunBuildPlanner

document = load_template_bindings(bindings_path)
plan = DryRunBuildPlanner().plan(arrangement, inspection, document)
```

The pure planner accesses no files or processes. It validates snapshots, not current
installation/template files; use the CLI or `planning_files.plan_build_files` for the
current-file checks. Results are independent copies with stable binding/source order,
no timestamps or random selection. JSON plans round-trip through `DryRunBuildPlan`.

Each plan embeds the complete arrangement (raw events, hashes, cleanup, timing choices,
role mapping), inspection (backend record/plugin hashes and unverified warnings) and
binding document. Each note links its arrangement index and copied source-view origin.
V2 also records the inventory snapshot hash and per-part template note/clip row indices.
Snapshot fingerprints hash normalized UTF-8 JSON with sorted keys and compact separators;
they are explicitly different from source-file hashes. The CLI additionally records
exact byte hashes/resolved paths of the arrangement JSON, inspection JSON and binding
YAML in `input_files`. File hashes detect changes; none is a signed authenticity claim.

`status` is `blocked` when any diagnostic is an error, otherwise `review_required`.
`execution_allowed` is always false and `compatibility` always `unverified`. There is
no FLP output path, `BuildResult`, backend edit request, new generator or plugin-state
copy. Preview notes remain visible when other capability checks block the whole plan;
no partial execution is implied. Invalid provenance/selector/configuration raises a
typed `BuildPlanningError` or `ConfigurationError`; capability limitations are reviewable
blocking diagnostics, including `ppq_inexact`, `tick_range_unsupported`,
`tempo_map_unsupported`, `tempo_precision_unsupported`, `meter_unsupported`,
`source_event_unsupported`, `source_bindings_incomplete` and template capability codes.

## Synthetic verification and remaining work

Offline fixtures cover exact conversions, trailing ticks, large tick bounds, zero
duration, source controls/programs, variable tempo/meter, strict selectors, collisions,
multiple inputs, multichannel tracks, repeated names, altered provenance, copied cleanup
and role audits, JSON stability, hashes and safe report/error behavior. The opt-in real
backend test inspects an original synthetic one-channel/Pattern/playlist template, then
disables process calls during planning and verifies original source channel 2 maps
explicitly to FL channel 0 with exact 480-to-96 conversion. Tests create original
temporary inputs only; there are no backend FLP writes or existing project edits.

Binding-slice verification on 2026-10-15: Python 3.11.16 and 3.14.7 each passed **251 tests,
1 skipped** with the existing real backend explicitly enabled. Default offline tests
passed **248 tests, 4 skipped** (three opt-in backend checks and the Windows symlink
privilege case). This slice adds 51 unit cases and one real inspection-to-plan case.
Ruff lint/format and strict mypy (36 source files) passed; an independent manual review
found no actionable issues. Python dependencies and the backend record stayed unchanged.

Wheel and source archives built successfully and excluded environments, caches, FLP
fixtures and backend binaries. The installed wheel exercised arrangement, real synthetic
inspection and planning. Planning succeeded with an empty executable PATH, retained all
three raw input fingerprints, produced identical JSON on stdout, rejected existing/input/
backend/alternate-stream destinations and stale evidence, and retained blocked plans with
exit 1. Source MIDI, template, binding YAML and backend-record hashes stayed unchanged.

For current verification and schema migration, see [template inventory](TEMPLATE_INVENTORY.md).
Before a writer: inspect an authorized real template, resolve the remaining opaque
event semantics, inherited content and template/plugin rights, verify destination
instrument intent, define safe exclusive-output staging and independently reparse and
open/listen to any future copied output. This slice does not close those gates.
