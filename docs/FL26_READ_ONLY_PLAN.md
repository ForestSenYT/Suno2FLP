# FL Studio 26.1.7.5654 read-only adaptation plan

User-authorized scope: exact-build read-only adaptation, original synthetic tests,
documentation and validation against the private local `templates/user-minimal.flp`.
Never modify the source, create an FLP output, patch the pinned backend, load plugins
or enable build execution. Python dependencies and backend pin remain unchanged.

Design: select a fixed profile from a structurally read version event, before any
version-dependent event is consumed. Only exact 26.1.7.5654 uses three payload bytes
for event 172 and 88-byte event-233 playlist records. The existing FL25 profile keeps
four bytes and 80-byte records. No substring sniffing, width guessing, fallback by
divisibility or support claim for other FL26 builds. Missing/ambiguous version evidence
must not select the override. Preserve event header bytes, rule/profile identifiers,
offsets, hashes, full records, crop float bits and opaque extension bytes.

The unmodified pinned backend may return a misleading successful summary for FL26.
Retain that summary as backend evidence, separately expose a local summary of selected
inventoried event families and explicitly compare them. Inconsistent summaries remain
untrusted; no source is silently substituted. Unknown fields/step-note durations/crop
sentinels stay uninterpreted. Existing FL25 writer capability gates remain in place:
FL26 is readable evidence only and every plan stays non-executable.

- [x] Add failing synthetic cases for exact profile selection, event 172 widths,
  truncated/malformed/late/conflicting version events and 80/88-byte isolation.
- [x] Add profile metadata and variable-stride byte-linked inventory contracts;
  preserve unknown 8-byte extensions, floating bits and round-trip integrity.
- [x] Update original reader framing and record decoding, without an encoder.
- [x] Add failing inspection comparison cases, then retain local/backend summaries
  independently with explicit mismatch status, original backend metadata and hashes.
- [x] Keep FL26 dry runs blocked; validate file-wrapper regeneration and CLI guards.
- [x] Run synthetic suites on Python 3.11/3.14, lint/format/mypy, isolated package
  smoke and independent read-only review. Fix real findings with RED/GREEN tests.
- [x] Read the user's actual source only, verify full hash/mtime and backend hashes
  before/after, and save new private JSON reports. Do not distribute the FLP.
- [x] Update usage, inventory schema/migration, architecture, roadmap and risks;
  distinguish field decoding from host/plugin/playback or writer compatibility.

Review focus: false-positive backend success; a one-byte event-172 interpretation can
also finish framing while fabricating events; layouts divisible by both 80 and 88;
nonfinite crop sentinel bits; lost/moved record extensions or provenance after JSON load.

No commits, pushes or backend installations are part of this slice.
