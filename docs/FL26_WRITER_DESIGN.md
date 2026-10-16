# FL26 writer: restricted output design

This design was produced in the read-only readiness batch. The subsequently authorized
[restricted implementation](FL26_WRITER.md) now supplies explicit-policy encoding,
structural verification and exclusive Windows bundles. General `FLPBuilder` stays a
protocol, defaults stay disabled, and old inspection/assessment/binding statuses never
authorize execution. Host/playback and private-template eligibility remain unresolved.

## Backend decision

Keep Music2DAW `6def9463d6fa8636bbc81010581318a39c47d3c4` unchanged as optional backend
evidence. Its successful FL26 inspection silently returns incomplete data, and its
writer assumes FL25 framing/80-byte playlist records. Sending current local bindings
to that unmodified writer would therefore be unjustified.

Two choices were assessed: a separately pinned upstream fork with demonstrated FL26
support, or a narrow original encoder using our exact profile/byte evidence. The
subsequent authorized batch implements the latter: it avoids modifying the pinned
installation and enforces an explicit changed-byte budget. Independent host checks
remain required. Do not copy
third-party parser/editor source into this package; retain separate license/runtime
evidence for any optional backend used. A complete generic FLP serializer is outside
the initial scope.

## Eligibility before any output

1. Exact declared 26.1.7.5654 version, expected profile and all current input/backend
   hashes verified. Readiness and binding documents must be regenerated and compared
   against current bytes. A saved `matched` assessment is insufficient.
2. A reviewed companion dependency/host manifest identifies actual plugins, versions,
   samples, intended instrument/routing and permitted local use. Opaque state hashes
   establish preservation only. Redistribution is not implied by possession.
3. Only faithful, positive-duration/velocity MIDI notes in a restricted constant-tempo,
   constant-default-4/4 subset. Require exact milli-BPM and exact endpoint/track-end PPQ
   conversion, supported coordinate ranges and complete original provenance. Reject
   unhandled CC/sustain/program/pitch/aftertouch/sysex or effective map changes.
4. Explicit one-to-one source selectors target unique existing Pattern/channel note
   events and playlist lanes; template channels must be demonstrably enabled and of
   the intended supported generator type. No inferred names/roles/GM assignments.
5. Explicit per-target inherited-content policy: retain or replace the named event,
   without implicit merging, deletion or clearing of other channels/Patterns/clips.
   All known automation, crops, groups, mute/loop/routing behavior and arrangements
   must either be preserved with assessed semantics or rejected.
6. A documented byte policy for every field inherited by modified records. Three-byte
   event-172 framing does not establish its semantic meaning. All-zero clip extension
   bytes do not establish that those bytes are safely disposable.

**The present `user-minimal.flp` does not meet these gates.** Stored zero note lengths,
`0x4000` flags/extra attributes and `ffffffff` crop bits are not approved positive
piano-roll-note/uncropped replacement prototypes. Their meaning requires additional
independent host evidence, or a later user-created minimal reference template with
explicitly understood positive notes and crop/attribute settings. This batch does not
create such variants or assume all unknown events can be safely edited.

## Module and data flow

Future modules would consume inward-facing core contracts:

```text
current source snapshots + original template bytes + reviewed policy/host manifest
    -> strict eligibility assessment (reconstruct source, exact binding/timing)
    -> immutable EditIntent with source/target record identities and byte budget
    -> narrow encoder into a new private staging bundle
    -> reparse + target semantic comparison + untouched-payload comparison
    -> exclusive final bundle publication
    -> manual FL Studio open/readback/listen evidence
```

`EditIntent` must be a distinct future versioned contract; do not reinterpret today's
non-executable `DryRunBuildPlan` or `TemplateReadinessReport` as an edit request. Include
template and source hashes, exact profile, full policy/bindings, original event/row
identities, expected target notes/clips, non-target preservation hashes, and sidecar
provenance. Intent creation must fail on any unresolved eligibility gate.

## Encoding and preservation budget

The initial allowed changes, after semantics are assessed, are explicitly selected
note-event payloads, selected playlist-event payloads and a single existing fine-tempo
scalar if the request requires it. No version spoofing, plugin state changes, generator
creation, routing mutation, global reordering or hidden metadata normalization.

Preserve every untouched event's original header and payload bytes, relative order,
and every untouched chunk. Preserve event-172 payloads/framing exactly. For changed
variable events, recompute only their own length prefixes and enclosing FLdt length;
do not demand unchanged offsets after resized payloads. Compare stable event identities
and relative order with an explicit changed-event list instead. Non-target raw hashes
must be identical, including opaque/plugin payloads.

For modified note/clip records, retain only fields whose inheritance policy has been
reviewed. The 88-byte clip record's entire eight-byte extension requires a named
preserve/replace rule backed by reference evidence; never default to truncating to 80
or zero-filling. Keep crop floats as bits until a separately assessed policy exists.
Reject ambiguous repeated events, mixed bases, multiple arrangements and encoded
Pattern overflow. No cloned record receives unreviewed flags/state by accident.

## Exclusive output and failure behavior

Use a caller-selected **new output bundle directory** outside all source/template/
backend trees after resolving identities and link/junction/alternate-stream risks.
The final destination must remain absent until publication; create only a separate
new staging directory initially. The bundle contains the new FLP, provenance sidecar
and verification record, all new files. Reject any pre-existing final destination,
including links/hard-link identity collisions. Never update a destination in place.

Encode and verify in a new private staging directory on the same filesystem. Staged
files are exclusively created; no upstream editor is allowed to choose or overwrite
the original or final path. Publish a verified bundle only with a platform-assessed
no-replace operation; never use overwrite-capable rename as a substitute. Final bundle
publication must not expose a successful FLP without its matching sidecar. On failure,
retain labeled partial staging for diagnosis; remove only artifacts owned by this run
under verified contained paths if cleanup is explicitly implemented. Never recursively
clean a user-supplied source/output parent.

Recheck source/template/backend hashes and source mtime on success and every exception
path. Detect changed snapshots and refuse publication. Record exact output bytes/hash,
source identities, changed event/record locations and preserved payload fingerprints.
Do not report success from process exit 0, output existence or parser EOF alone.

## Reparse and acceptance

First run a strict independent framing/record pass over the output. Expected source
notes, exact starts/durations, channel bindings, clip lanes/bases/lengths and tempo
must match the intent; no extra or missing notes/clips may silently pass. Confirm all
non-target chunks/events/plugin/sample declarations are preserved. Independence means
more than serializing and deserializing through the same unchecked assumptions.
The current pinned backend cannot supply a trusted FL26 output oracle.

Only after structural validation may a separately authorized host step open the new
file in FL Studio 26.1.7 build 5654, confirm no missing/changed instruments/samples,
read back notes/tempo/placement and listen or render for comparison. Record the host
version, output hash and observations. Parser success cannot claim audible fidelity,
source audio reconstruction or complete format support. A `BuildResult` must clearly
separate file creation/structural verification from subsequent host/playback evidence.

## Future test matrix

| Condition | Required result |
| --- | --- |
| Unknown version, changed backend/template or forged evidence | Fail before staging |
| Zero/step-style notes, nonfinite crops, unknown inherited attributes/extensions | Fail until an explicit assessed policy exists |
| Missing/ambiguous targets, inherited unbound content or unsupported source events | Fail without substitution/deletion |
| Inexact PPQ/milli-BPM, range or encoded Pattern overflow | Fail without rounding |
| Large/small replacement payloads, multibyte lengths | Exact framing, timing and untouched payload hashes |
| Existing output, link/junction/hard-link/alternate-stream destination | Refuse; source and existing output unchanged |
| Injected failure during encode, verify, sidecar or publish | No successful bundle; originals unchanged; owned staging diagnosable |
| Reparse sees missing/extra notes/clips or changed plugin payload | Fail publication |
| Same explicit inputs twice in separate new bundles | Same musical/byte semantics and provenance; no random inference |
| Host reports missing plugin/sample or altered timing/playback | Keep compatibility unverified/failed |

The subsequent [writer batch](FL26_WRITER.md) implements the narrow structural workflow
and synthetic/failure-path tests. Positive fixtures remain authored synthetic inputs,
not host-verified reference projects. The private real template still fails preflight;
no later implementation closes its unresolved semantics or replaces host acceptance.
