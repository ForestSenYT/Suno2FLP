# FL Studio 26.1.7.5654: exact-build read-only support

This original Python profile reads exact build **26.1.7.5654**, alongside 25.1.2.4896.
This read profile contains no encoder, backend patch, plugin load or new dependency,
and grants no implicit support for other FL26 builds. A separate later
[restricted writer](FL26_WRITER.md) requires new explicit eligibility; this profile
and old previews never enable execution by themselves. Defaults stay disabled.

```powershell
uv run suno2flp inspect-template templates/user-minimal.flp --backend-dir .tools/music2daw-6def9463d6fa-inspect --output .tools/user-minimal-fl26-adapted-inspection.json
```

Choose a new output path if it exists. Inspection checks input/backend hashes and
creates JSON exclusively; the pinned backend remains unchanged at
`6def9463d6fa8636bbc81010581318a39c47d3c4`.

## Version-specific framing and provenance

| Exact declared build | Profile | Event 172 payload | Event-233 clip stride |
| --- | --- | --- | --- |
| 25.1.2.4896 | `fl25-25.1.2.4896-read-v1` | 4 bytes | 80 bytes |
| 26.1.7.5654 | `fl26-26.1.7.5654-read-v1` | 3 bytes | 88 bytes |

Only a structurally read version event selects a profile. Version must precede
dependent records and event 172; repeated/conflicting versions fail. A missing or
unknown version cannot enable the override. There is no substring sniffing, retry
with alternative widths or stride choice by divisibility. Tests use payload lengths
divisible by both 80 and 88 to check isolation.

The actual FL26 file contains 172 values `010100` and `000100`. A one-byte reading
can also reach EOF while fabricating events, so EOF alone proves nothing. Tests
assert exact following event order and metadata boundaries. Unknown three-byte
values remain raw evidence with an unassessed-value warning.

Inventory schema/reader **v2** adds `profile_id`, event `header_hex` and `framing_rule`.
FL26 event 172 uses `fl26-event-172-3bytes`; other events use `classic`. JSON loading
checks headers, widths, rules, offsets, scalar bytes and payload hashes. Notes retain
their complete 24-byte records; clips retain all 88 bytes, the common decoded prefix
and uninterpreted eight-byte `extension_hex`. Positions/lengths stay in template ticks;
crop floats retain their exact bits. Unknown extensions, sentinel values, zero note
durations and flags receive no invented meaning.

Real v1 inventories remain readable with their original required `record_size: 80`.
Missing provenance is not fabricated. File planning regenerates v2 inventories, so
older reports must be refreshed rather than silently passing current-byte equality.
The outer inspection schema stays 1; migration grants no writer capability.

## Local and backend evidence remain separate

The old backend can exit successfully while silently omitting FL26 content. Reports
therefore retain:

- `project`: the unchanged typed backend result and its original metadata/hashes.
- `inventory` and `local_summary`: byte evidence and a summary scoped to selected
  event families, with tempo/Pattern/playlist event indices. Tempo stays in integer
  milli-BPM; omitted defaults are not invented. Incomplete note/clip records produce
  unknown (`null`) summary counts, not false empty collections.
- `backend_summary_status` (`unchecked`, `consistent`, `inconsistent`) and
  `backend_summary_mismatches`: both observations with source event indices.

`consistent` means selected-field agreement only; `unchecked` means comparison is
incomplete. Neither proves format/playback compatibility. An inconsistent result is
a useful read-only JSON report with a warning; backend values are never substituted.

Planning recomputes recorded comparison evidence. Every produced FL26 plan receives
`template_read_only_profile`, even with an apparently consistent synthetic backend
result. Mismatches add `template_backend_summary_untrusted`. Invalid target bindings
still fail explicitly without a plan; local inventory never fabricates missing backend
Pattern targets. An empty binding set can produce a diagnostic-only blocked plan with
unbound sources and complete input snapshots. The pinned backend's
FL25 writer limits have not been extended to 88-byte clips. Every plan remains
non-executable and compatibility unverified.

## Actual private-template evidence

The user-created `templates/user-minimal.flp` was read locally; its binary and plugin
data are not distributed.

| Property | Observation |
| --- | --- |
| Source bytes | 53,397 |
| SHA-256 | `d45f79750d44bfe3eb37fed22f8779ef8e8464a230b3b47d00c9967dbb2997ca` |
| Version / PPQ / header channels | 26.1.7.5654 / 96 / 5 |
| Framed events | 1,618 |
| Note records | 4 in zero-based Pattern 0, channel 0; starts 0/96/192/288 ticks; stored lengths remain 0 |
| Playlist | 1 original 88-byte record |
| Local fine tempo | 130,000 milli-BPM (130 BPM), event index 8 / ID 156 |
| Old backend | 140 BPM, no Patterns/clips; explicitly inconsistent |
| Coverage | Partial: opaque semantics and nonfinite crop bits remain unverified |

The new private report `.tools/user-minimal-fl26-adapted-inspection.json` contains
full inventory/offsets/raw records/float bits and original backend evidence. Source
SHA-256 and modification time match the baseline; backend fingerprints stay unchanged.
No source/version string/backend binary or manifest was patched. Zero note lengths
are observations, not reconstructed MIDI durations. Crop `ffffffff` values retain
their bits and null finite values; their sentinel semantics remain unknown.

## Verification and remaining scope

Default synthetic tests cover exact/unknown/late/conflicting versions, 172 widths and
truncation, 80/88 isolation, extensions/crop bits, false backend success, incomplete
records and provenance tampering. Explicit private-input validation never writes it:

```powershell
$env:SUNO2FLP_MUSIC2DAW_DIR = (Resolve-Path .tools/music2daw-6def9463d6fa-inspect).Path
$env:SUNO2FLP_FL26_TEMPLATE = (Resolve-Path templates/user-minimal.flp).Path
uv run pytest tests/integration/test_fl26_external.py
```

Without both variables this test skips. An explicitly configured wrong/missing input
or broken backend fails.

Verification on 2026-10-15: Python 3.11.16 and 3.14.7 each passed **329 tests,
1 skipped** with both private-input/backend variables enabled. Offline defaults passed
**324 tests, 6 skipped**: five opt-in external cases and the Windows symbolic-link
privilege case. This slice adds 29 synthetic unit cases and one opt-in private-input
case. Ruff lint/format and strict mypy (41 source files) passed. Independent review
found a version-order issue; synthetic late-note/playlist cases failed before the fix
and passed afterward.

Both package formats exclude private FLPs, backend binaries and environments/caches.
The installed wheel verified this original input, deterministic JSON, full inventory
round-trip, explicit backend mismatches, old v1 loading, existing-output/source/backend
directory/alternate-stream guards and stale-inventory refusal. PATH-free planning
rejected invalid backend targets, then retained the complete original MIDI channel,
timing and input PPQ in a diagnostic-only blocked plan with explicit empty bindings.
No target or converted-note preview was fabricated. Private installed-package evidence
is in `.tools/fl26-wheel-check-final/verification.json`; input SHA-256/mtime and all
pinned backend fingerprints remained unchanged. Python dependency files are unchanged.

Complete plugin/sample/track and automation semantics,
independent host readback/listening and all writer prerequisites remain open.
