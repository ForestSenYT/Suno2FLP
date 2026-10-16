# Read-only template inventories and stronger dry-run checks

`inspect-template` now retains a local byte-linked inventory alongside the pinned
Music2DAW summary. The backend, installation and license boundary are unchanged.
There are no new dependencies, writer, encoder, plugin loads or backend operations.
The Python scanner accepts an immutable byte snapshot and has no file/process access.

```powershell
uv run suno2flp inspect-template C:/MyTemplates/original.flp --backend-dir .tools/music2daw-6def9463d6fa-inspect --output inspection-v2.json
uv run suno2flp plan-build arrangement.json --inspection inspection-v2.json --bindings bindings.yaml --backend-dir .tools/music2daw-6def9463d6fa-inspect --output plan-v2.json
```

Use new report paths. Existing output, backend-directory and alternate-stream guards
still apply. Inspection validates framing before any backend process, then calls only
the existing `inspect` command and checks template/backend hashes afterward. The local
inventory and backend summary describe the same byte fingerprint; a successful parse
does not establish FL Studio compatibility.

## Inventory evidence

`TemplateInspectionReport.inventory` has its own schema and reader version. It records
the template SHA-256, byte length, PPQ, channel count and exact declared FL build. Every
chunk has its absolute file offset, ID bytes, payload length and hash. Every event has
an ordered index, absolute event/payload offsets, ID, length, payload hash and current
channel/Pattern/arrangement context. Scalar payloads retain their bytes too.

| Collection | Retained evidence |
| --- | --- |
| `notes` | Exact Pattern/channel pair, position/length in template ticks, pitch, velocity, pan, fine pitch, release, flags/group and full original 24-byte record |
| `clips` | Pattern or channel link, encoded item/base IDs, arrangement context, playlist lane, position/length in template ticks, group, flags/mute, full 80-byte record and both crop floats |
| `automation` | Channel-type indicators, legacy automation, raw 20-byte link records with undecorated parameter/destination values, and 21-byte-header/24-byte-point curve payloads including unknown tails |
| `FloatEvidence` | `f32le`/`f64le`, exact original bit bytes and a finite decoded value; nonfinite values use `value: null` while their bits remain intact |

Note/clip/automation records retain event and record indices plus absolute byte offsets.
Typed fields are checked against raw records, locations and event payload hashes when
loading JSON. Curve points must agree with the retained count/payload and cannot be
dropped or relocated silently. Reports round-trip without rewriting any template data.

Crop floats retain their encoded values; they are never truncated to integer ticks.
Automation retains `encoded_time` rather than claiming an absolute or cumulative
timeline. The pinned Music2DAW parser and alternative PyFLP source interpret those
curve times differently. All automation blocks planning, so no interpretation is used
to infer a safe tempo or translate a performance.

## Assessed layout and coverage

The original reader uses Python integer/struct operations, not imported or copied
upstream parser code. Its exact-build profiles are FL **25.1.2.4896** (80-byte clips)
and **26.1.7.5654** (three-byte event 172, 88-byte clips), retaining 24-byte notes.
See [FL26 support and evidence](FL26_READ_ONLY.md). Known automation event IDs are 21
with channel type 5, 223, 227 and 234. Full automation payloads survive even when a
layout is malformed or legacy semantics remain unknown.

| `coverage` | Meaning |
| --- | --- |
| `decoded` | One assessed FLdt chunk; known selected layouts decoded, with no unsupported framing/layout diagnostics. This describes the profile's fields only, not complete project semantics. |
| `partial` | Bytes are framed, but extra chunks, orphan/misaligned records, opaque events, legacy automation, unsupported links/lanes or nonfinite values need review. Available records and every event hash/location remain. |
| `unsupported` | No unique exact assessed version event; chunk/event evidence remains, but note/clip/automation layouts are not guessed. |

The scanner does not choose a 32/60-byte fallback by divisibility. Event 235 can mean
routing or playlist data in this backend; it stays opaque rather than being guessed
into a playlist. Multiple arrangements are not flattened into an implicit selection.
Unknown plugin states remain hashed opaque payloads even with `decoded` coverage.
Track behavior, plugin-internal automation, sample state and final FL event semantics
remain unverified. An inventory with no known automation is not proof that a project
contains no automation anywhere.

Inventory schema/reader v2 retains exact profile IDs, event headers/framing rules and
the opaque FL26 eight-byte extension. V1 remains readable but current-file checks need
refreshed inventories. Original backend and local selected-family summaries stay
separate, with explicit mismatch evidence. FL26 never enables the FL25 writer profile.

Truncated chunk/event headers, overflowing/unterminated length prefixes, payloads that
escape their chunk and missing FLdt produce `template_inventory_invalid`, with no
inspection output and no backend call. Framed unsupported content produces an explicit
partial inventory if the backend itself can inspect it; backend failures still fail
explicitly. Inputs and backend hashes are never repaired or overwritten.

## Dry-run v2 behavior

New plans use `algorithm_version: 2` and
`capability_profile: music2daw-6def9463-dry-run-v2`. They retain the complete inspection,
including inventory, its normalized snapshot fingerprint and per-part
`template_note_indices` / `template_clip_indices` linking candidates to inventory rows.
Original arrangement notes/events, cleanup/role audits, source MIDI channels, PPQ
conversion rules and all three CLI input-byte fingerprints remain unchanged.

The pure planner checks internal snapshot consistency without I/O. File-based planning
also verifies current template/backend bytes and regenerates the local inventory both
before and after planning. A saved inventory differing from the current byte scan fails
with `template_inventory_stale`, even when the template's declared hash is unchanged.
This adds no .NET, Git, network or DAW prerequisite to planning.

| Condition | Blocking diagnostic / policy |
| --- | --- |
| Old summary-only inspection | `template_inventory_missing`; rerun read-only inspection |
| Partial/unsupported coverage | `template_inventory_incomplete`; no assumption of empty/safe content |
| Local inventory differs from backend version, Pattern IDs/counts, clip count or tempo bytes | `template_inventory_summary_mismatch`; neither source silently wins |
| Bound Pattern/channel pair lacks an original note record | `template_note_set_missing`; aggregate Pattern count is insufficient |
| Any template note outside the exact bound pairs, even in an unplayed Pattern | `template_notes_unbound`; no deletion or carry-over policy inferred |
| Repeated Pattern-note or playlist events / explicit arrangements | `template_note_events_ambiguous`, `template_playlist_events_ambiguous`, `template_arrangements_unsupported`; prevent repeated replacements or flattened arrangements |
| Mixed playlist bases or base + target Pattern + 1 exceeding 65535 | `template_pattern_base_ambiguous` / `template_pattern_index_overflow`; check the actual encoding inherited from the first record, not just logical IDs |
| Any retained automation | `template_automation_unsupported`; no clearing or translation |
| Channel clip, unbound Pattern clip or clip in a different lane | `template_clip_binding_conflict`; no implicit replacement/merge policy |
| Nonzero or unknown/nonfinite start/end crop | `template_crop_unsupported`; a zero request does not clear inherited backend crop bytes |
| Muted/grouped/unknown clip flags, unknown note attributes, disabled target channel or out-of-range records | Explicit content diagnostics; no silent inheritance |
| Missing/repeated fine-tempo event or later legacy tempo | `template_tempo_event_unverified` / `template_tempo_conflict`; the editor only changes its first fine-tempo event |
| Explicit template meter outside default 4/4 | `template_meter_conflict`; absent meter fields remain a warning, not a proven default |

Candidate converted notes may remain visible in a blocked plan; they are not a partial
build. A valid blocked plan is emitted with exit 1; `review_required` returns 0. Every
plan keeps `execution_allowed: false`, compatibility unverified and the writer-disabled
and template-semantics warnings. No content is actually cleared, replaced or written.

The inspection outer schema remains 1 with optional `inventory` for reading older
reports. New inspection always supplies inventory. Saved v1 plans remain readable
but are not upgraded into v2 eligibility; replan from a fresh inspection. All hashes
are integrity evidence, not signed authenticity or protection against a hostile process.

## Sources and remaining gates

Field layouts and conservative hazards were checked against the exact pinned
[Music2DAW parser](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Monad.FLParser/ProjectParser.cs),
[event IDs](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Monad.FLParser/Enums.cs)
and [editor](https://github.com/jihadkhawaja/flstudio-mcp/blob/6def9463d6fa8636bbc81010581318a39c47d3c4/src/Music2Daw.Core/FlpProjectEditor.cs).
Alternative observations are in pinned
[PyFLP automation](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/channel.py)
and [playlist](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/arrangement.py)
sources. Those implementations remain separately licensed; no third-party parser or
backend binary enters the Python distribution.

Synthetic tests create original temporary inputs only and cover exact records,
multibyte lengths, invalid framing, unknown layouts, float bits, automation integrity,
inventory/summary disagreements, current-byte verification and content blockers.
Opt-in real backend tests include a one-note/clip case and a two-channel case with
automation links/points plus a fractional crop. Only read-only inspect is invoked;
planning is checked with process calls disabled.

Inventory-slice verification on 2026-10-15: Python 3.11.16 and 3.14.7 each passed
**299 tests, 1 skipped** with the real backend explicitly enabled. Offline execution
passed **295 tests, 5 skipped**: four opt-in real checks and the Windows symbolic-link
privilege case. This slice adds 47 unit cases and one real automation/crop case.
Ruff lint/format and strict mypy (39 source files) passed. Independent manual review
identified one missing encoded Pattern overflow check; it was reproduced with a failing
test and fixed, together with a mixed-base case, before final full-suite verification.

Both package formats built and excluded optional backend binaries, FLP fixtures,
environments and caches. Installed-wheel checks exercised real original synthetic
inspection, inventory hashes/row links, exact source-channel/PPQ provenance, deterministic
stdout, blocked automation/crop reports, old-report refresh and refusal of modified
saved inventory. Planning worked with an empty executable PATH. Existing-output,
input, backend-directory, alternate-stream and stale-template guards passed. Original
MIDI/template/config/backend fingerprints and Python dependency files stayed unchanged.

The subsequent [FL26 slice](FL26_READ_ONLY.md) verifies a user-created real template
read-only. Complete host/plugin/sample/rights evidence, reviewed
content policy, safe exclusive-output staging and independent FL Studio open/listen
validation are still required before a separately authorized writer slice. This work
does not establish complete format coverage or audible compatibility.
