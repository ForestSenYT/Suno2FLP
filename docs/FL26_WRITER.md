# Restricted native FL26 writer

This batch implements an original **26.1.7.5654** encoder, independent output verifier
and Windows-only exclusive bundle publisher. It is a narrow structural implementation,
not complete FL26 compatibility. The current `templates/user-minimal.flp` remains
ineligible: its unresolved content/dependencies and backend disagreement still block
before encoding/staging. No FLP derived from that private original is generated.

The pinned Music2DAW installation is unchanged and never invoked for writing. Its
incomplete FL26 summary remains evidence, not a source of fabricated local targets.
Old `plan-build` and `assess-template` reports remain non-executable; no flag promotes
them to a build. Defaults still select `flp_backend: none`.

## Explicit commands

Prepare a current-file eligibility report first:

```powershell
uv run suno2flp plan-flp-write arrangement.json --inspection inspection.json --bindings bindings.yaml --policy writer-policy.yaml --backend-dir .tools/music2daw-6def9463d6fa-inspect --output write-plan.json
```

All four documents and the backend are required. A blocked plan is saved for review
and returns 1; a ready plan returns 0. Invalid/stale inputs fail without a report.
Omit `--output` for deterministic JSON stdout. Existing outputs, alternate streams,
non-JSON destinations and backend-directory report paths are refused.

Only an eligible input set can produce a new bundle:

```powershell
uv run suno2flp build-flp arrangement.json --inspection inspection.json --bindings bindings.yaml --policy writer-policy.yaml --backend-dir .tools/music2daw-6def9463d6fa-inspect --output-dir output/song-build-001
```

The destination directory must not exist; its parent must exist. A successful command
creates exactly `project.flp`, `provenance.json` and `verification.json`. It returns a
real `BuildResult` only after structural reparse, input checks and final bundle checks.
Host opening/playback remains explicitly unverified. No command opens FL Studio,
loads plugins, expands sample references or runs upstream `edit`/`export`/`launch`.

## New policy and intent contracts

`Fl26WriterPolicy` / `WriterPolicyDocument` are separate from old read-only plans.
The [draft example](../examples/fl26_writer_policy.yaml) deliberately blocks: it uses
unknown hashes, `reference_kind: unverified`, unverified review fields and no targets.
Current file assessment never invents successful operator/host checks.

The policy pins the original template hash, canonical inventory fingerprint and
canonical binding-config fingerprint, using the existing stable `snapshot_sha256`.
It records a reviewer/reference description, reference kind and dependency/instrument/
local-use review. Each review is `unverified` or `attested`; the former always blocks.
`synthetic_fixture` labels original test inputs; `operator_host_readback` records an
operator's claimed reference evidence. An attestation is retained provenance, not
automatic proof of installation, rights, host behavior or a cryptographic signature.
It cannot override byte, timing, source, backend or ambiguity blockers.

Each target supplies an explicit binding index, prototype note/clip inventory indices,
their raw-record SHA-256 values, a generator declaration event index and exact name.
No prototype or instrument is selected by default. Duplicate prototype indices fail.
Every active binding requires one reviewed target. The only implemented policies are:

- Replace **all** explicitly bound note sets and clips; reject unbound inherited notes
  or clips. No implicit merge, retain, clear or additional Pattern/channel creation.
- Preserve the reviewed prototype's untouched note attributes. Flags/groups and extra
  unassessed note bytes must be zero; positive original note length/ranges are required.
- Preserve every byte of the reviewed 88-byte clip outside position and length,
  including its full eight-byte extension. This does not assign meaning to that tail.
  Nonzero/nonfinite/negative-zero crop bits, clip flags/groups/mute and invalid ranges
  still block, regardless of policy or all-zero extension bytes.

`Fl26WriteIntent` embeds independent copies of arrangement, inspection, bindings,
policy and local binding evidence, canonical fingerprints, precise proposed notes and
an event-edit budget. Status is ready only when every diagnostic gate passes. The
encoder reconstructs a fresh intent from the original bytes and snapshots and requires
exact agreement; editing a saved status, target or preview cannot bypass eligibility.

## Strict eligible subset

| Evidence | Required behavior |
| --- | --- |
| Build/framing | Exact NUL-terminated `26.1.7.5654`, current v2 profile, one FLdt chunk, complete inventory |
| Event set | Explicit writer allowlist only; unknown/routing/arrangement/automation events block |
| Existing structures | One fine-tempo event, one playlist event, unique note events/clip targets and a single playlist encoding base |
| Backend evidence | Retained local/backend comparison must be consistent; partial successful parses remain blocked |
| Template meter | Exactly one each of assessed fields 17/18 with value 4 |
| Generators | Explicit enabled state, channel type 2, reviewed nonempty declaration and matching backend generator/non-sequenced evidence |
| Source music | Faithful reconstruction, complete source hashes and paired notes; constant default 4/4 and one exact integer milli-BPM tempo |
| Timing | Exact starts, ends and track ends at template PPQ; positive durations, signed 32-bit range; no rounding-enabled prior arrangement |
| Performance | Unsupported CC/sustain/program/bend/aftertouch/sysex and other non-allowlisted events block in every retained source track |
| Content/prototypes | Complete explicit one-to-one binding and reviewed exact row hashes; unresolved attributes/crops/ambiguity block |

The writer's event allowlist is intentionally narrower than the reader's passive event
set. Event 172 is retained unchanged with exact three-byte framing; no semantic meaning
or replacement value is invented. Opaque plugin state in assessed passive events is
preserved verbatim, never edited or treated as proof of complete dependency coverage.

File preparation reimports every original MIDI and compares the entire snapshot,
replaying recorded deterministic cleanup when present. A forged source snapshot with
a copied hash fails. Imported and active/cleaned views retain original source channels,
events/ticks, options and change history. File hashes/size/mtime are captured for
arrangement, inspection, bindings, policy, original MIDI and template; current backend
artifacts and regenerated template inventory are checked before and after preparation.

## Encoding and independent round trip

The encoder changes only authorized note-event payloads, the existing playlist payload
and fine-tempo scalar. It derives FL channel bytes from explicit destination bindings;
original MIDI channels remain in note origins and the complete sidecar. Note starts
and durations use exact converted endpoints; clips start at zero and retain converted
track ends. Position/length changes leave crop bits, identity/base/lane, flags and all
eight extension bytes untouched.

Unchanged events retain their complete original headers/payloads/order. Changed
variable payloads get canonical length prefixes; only FLdt size is recomputed.
Offsets may change after a resized note payload; verification compares stable event
indices/order and payloads rather than demanding impossible unchanged offsets.

`fl26_verify.py` has an independent strict output framing loop and field/count checks;
it does not call the encoder or inventory scanner to decode the output. It verifies
all intended notes/clips/tempo, prototype attribute bytes, exact untouched event bytes,
clip extension/crop identity and the permitted change budget. Extra/missing notes,
wrong channel/time/pitch/velocity, modified plugin state, truncated framing or malformed
changed-event lengths fail. `Fl26Verification.level` is `structural_round_trip_only`.

## Exclusive new output protection

All build input/output path components are checked for symlinks, junctions/reparse
points, ambiguous trailing components, device names and NTFS alternate streams.
Output must be outside backend, template and original MIDI directories. Existing
destinations are refused, including files/directories or aliases; no user output is
overwritten. The new leaf uses a portable name and existing parent.

After eligibility, write exclusively created files into a new sibling staging
directory. Flush file contents, verify FLP and both sidecars, check directory identity,
recheck all inputs/backend, and only then publish the entire bundle. Publication uses
Windows `os.rename`, whose existing-target refusal is documented by
[Python 3.11](https://docs.python.org/3.11/library/os.html#os.rename).
There is no overwrite-capable `replace`, recursive move or copy fallback. Non-Windows
publication fails before staging; pure preparation/encoding/verification stays portable.

Recheck published bytes, directory identity and all source/backend fingerprints before
returning a result, and recheck originals again on exceptions. Failures retain only
new artifacts for diagnosis, with a path in the error where available; there is no
recursive cleanup. A change/corruption detected after publication returns failure,
even if the newly created bundle remains. Its receipt asserts structural checks only,
not a successful host validation. Never treat file existence as success after an error.

These checks assume a trusted local workspace. They are not an OS sandbox against a
malicious same-user process repeatedly replacing directory ancestors between checks.
No crash-durability, cloud/synchronized filesystem or hostile filesystem guarantee is
claimed. Inputs are never opened for writing; changing external state fails checks.

## Private source and validation boundary

The opt-in actual-template test uses an honestly unreviewed draft and an original
synthetic MIDI negative probe. It requires `SUNO2FLP_FL26_TEMPLATE` and
`SUNO2FLP_MUSIC2DAW_DIR`, verifies the real source and backend, then checks that building
is blocked before output/staging. It does not copy, encode, save or open that FLP.

`user-minimal.flp` still has zero note lengths, `0x4000` note attributes, `ffffffff`
crop bits, opaque families and misleading backend results. None is repaired or
interpreted into an eligible state. A suitable independently evidenced reference,
resolved dependency/instrument intent and actual FL Studio open/readback/listen checks
remain necessary before claiming a usable musical output.

Synthetic positive fixtures demonstrate serialization and structural verification
only. They are authored test byte streams, not licensed host-produced reference projects
or examples of audible FL Studio compatibility. Test/installation receipts and private
negative reports stay ignored under `.tools/`; no private FLP or backend binary is
distributed.

Verification on 2026-10-15: Python 3.11.16 and 3.14.7 each passed **432 tests,
1 skipped** with real external prerequisites enabled. Offline defaults passed
**425 tests, 8 skipped**: seven opt-in external cases and the Windows symbolic-link
privilege case. This batch adds 56 unit cases and one real-template blocking case.
Ruff lint/format and strict mypy (53 source files) passed.

Independent review found prior arrangement rounding could masquerade as exact writer
timing, and an unbound empty note event could pass readiness then fail verification.
Both were reproduced with failing tests and fixed; final full suites include both.
No review finding is deferred. Extra malformed length-prefix and mixed-base/version
checks also have original synthetic regression coverage.

Both package formats built, excluding FLPs, optional binaries and caches. The installed
wheel produced two byte-identical new bundles from explicitly authored synthetic FLP,
inspection and nonexecuting backend-inventory fixtures. These are labeled test stubs,
not successful Music2DAW/host inspections. Genuine pinned-backend inspection of a new
FL26 synthetic input still missed its 88-byte playlist; the mismatch was retained and
not patched or bypassed. The real private-source path uses the genuine installation/
inspection and an unreviewed draft, and remains blocked with no output or staging.

Installed commands verified original source channels 2/9, exact 480-to-96 PPQ, full
source/document hashes, deterministic sidecars, refusal of an existing bundle and
process-free planning/building. Private receipts live in
`.tools/fl26-writer-installed-fixture-smoke/verification.json` and
`.tools/fl26-writer-release-verification.json`. The actual source SHA-256/size/mtime,
all 19 genuine backend artifacts and Python dependency files remain unchanged.
