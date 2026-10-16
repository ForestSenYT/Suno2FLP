# FL26 read-only readiness and dependency evidence

This batch adds `assess-template` for exact **26.1.7.5654**. It completes a reviewable
read-only evidence package, not complete FL26 compatibility. Unknown semantics stay
unknown. This read-only workflow has no encoder, FLP output, backend patch, plugin load
or DAW action. The subsequently authorized [restricted writer](FL26_WRITER.md) uses
separate policy/intent contracts; this report always stays non-executable.
See [byte reader](FL26_READ_ONLY.md) and [writer design](FL26_WRITER_DESIGN.md).

Later [independent host field evidence](FL26_FIELD_EVIDENCE.md) narrows note-attribute
and Pattern-crop findings for exact matching forms. Unknown forms remain unresolved;
this report and its writer gates remain non-executable.

## Usage and result meaning

Start with a current `inspect-template` JSON, then:

```powershell
uv run suno2flp assess-template .tools/user-minimal-fl26-adapted-inspection.json --backend-dir .tools/music2daw-6def9463d6fa-inspect --output .tools/user-minimal-fl26-readiness.json
```

Use a new output path if that report already exists. Omit `--output` for deterministic
JSON on stdout. Assessment itself invokes no process, .NET, Git, network or sample
lookup. It verifies the pinned backend's files and regenerates inventory from the
current original bytes, before and after assessment, including failure paths. Source
hash, size and modification time must stay unchanged. An explicitly missing/broken
backend, changed template, stale inventory or forged comparison fails with no report.
Outputs must be new `.json` files outside the backend, with an existing parent;
existing files, FLP destinations, symlinks and NTFS alternate streams are refused.

Exit **0** means the read-only assessment completed, even when writer gates are blocked.
Exit **1** means invalid input, unmet prerequisites or an integrity/output failure.
Exit **2** means invalid command-line arguments. This differs deliberately from
`plan-build`, whose blocked preview returns 1. Every assessment has
`writer_status: blocked`, `execution_allowed: false`, `compatibility: unverified`.
No output filename, executable backend request or `BuildResult` is emitted.

## Dependency manifest

The outer schema 1 / algorithm `fl26-readiness-v1` embeds the complete original
`inspection`, its canonical snapshot hash, source/backend fingerprints and these
selected event declarations in original order:

| Event ID | Manifest evidence | Interpretation limit |
| --- | --- | --- |
| 192 / 203 | Display text | A label does not establish plugin identity |
| 201 | Generator/plugin declaration text | Blank declarations remain blank; no Sampler substitution |
| 196 | Sample reference text | Literal reference only; placeholders and relative paths stay unresolved |
| 212 | Plugin initialization payload hash/size/location | Opaque; no plugin format/version inference |
| 213 | Plugin state payload hash/size/location | Separate evidence for every event, including repeats |

Text is decoded strictly as UTF-16LE, removing at most one trailing NUL. Empty and
invalid encodings retain exact `raw_text_hex`, hashes and status. State payloads remain
opaque hashes and offsets into the original template, not copied preset internals.
All records link event index, payload offset/size and SHA-256 to retained inventory.
JSON validation rejects missing/modified declaration links or text inconsistent with
its bytes, and recomputes the inspection/arrangement snapshot fingerprints. This is
integrity evidence, not signed authenticity; reassess current files
before using an old report. A manually edited assessment is not a writer input contract.

`channel_context` is a syntactic selection hint only. `owner_verified` is always false.
Pattern/playlist/mixer boundaries clear this hint, including assessed mixer IDs
27/95/98/149/204/225/235/236. A mixer effect does not inherit the last rack-channel
selection through those fields. Neither the backend's
misleading summary nor arbitrary labels establish generator ownership or routing.

Every dependency's version, format and external-file hash remain null; availability
and rights remain `unverified`. No environment expansion, sample path resolution,
disk search, external file access or installation probing is performed. This selected
manifest cannot prove absence of hidden sample/plugin references in opaque state.
Runtime 10.0.12, SDK 10.0.401, DryWetMidi 8.0.3, backend licenses and artifact hashes
remain separate backend evidence inside the inspection. No dependency/pin is changed.

Before a writer, host/operator evidence still needs to record actual plugin versions
and formats, edition/entitlements, resolved sample/preset hashes and intended local
use. Redistribution is a separate question; no dependency is bundled by this batch.

## Local binding checks

Supply both optional inputs together:

```powershell
uv run suno2flp assess-template inspection.json --backend-dir .tools/music2daw-6def9463d6fa-inspect --arrangement arrangement.json --bindings bindings.yaml --output readiness-with-bindings.json
```

Bindings use the existing [strict one-to-one configuration](BUILD_PLANNING.md): exact
template hash/backend pin and zero-based source input/track position/channel and
template channel/Pattern/lane IDs. There are no defaults, role/name matches or inferred
assignments. Duplicate/overlapping rules and modified source reconstruction fail.

Unlike executable-capability planning, this check uses retained local byte evidence
for the exact Pattern/channel note pair and Pattern/playlist lane. It can establish
that a proposed target exists even when the old backend omits all Patterns. The backend
snapshot remains unchanged; local facts are never substituted into it. Missing source,
wrong pair/lane, incomplete source coverage and repeated clips/note events or ambiguous
arrangements produce `binding_check.status: blocked` and diagnostics.
Multiple playlist events are not combined implicitly. Missing source hashes and raw
unmatched/unclosed note diagnostics also block, even if paired notes match local IDs.

Each part retains template row indices and converts source note starts, ends and track
ends exactly with `tick * template_ppq / arrangement_ppq`. Inexact/range-invalid notes
produce null notes/clip length, not a partial or rounded preview. Source channels,
original timing, input PPQ, raw events, cleanup/role audits, full arrangement and exact
binding document remain in independent snapshots. File assessments additionally retain
byte hashes/resolved paths for all three input documents.

`matched` means local target presence and exact coordinate preview only. It does not
verify tempo/control writing, audible instrument intent, generator availability,
enabled/muted/routed playback or inherited-content replacement. Those remain explicit
writer gates. Without supplied arrangement/bindings, `binding_check` is null; source
intent is not fabricated. Existing `plan-build` restrictions are unchanged.

## Actual private input

Read-only assessment of `templates/user-minimal.flp` retains the original 53,397 bytes,
SHA-256 `d45f79750d44bfe3eb37fed22f8779ef8e8464a230b3b47d00c9967dbb2997ca`,
1,618 events, 4 raw note records and one 88-byte clip. PPQ remains 96, and locally
observed tempo remains 130 BPM; the original backend's 140 BPM/empty Patterns/clips
remains explicitly inconsistent.

Declarations include four literal `%FLStudioFactoryData%` sample references for Basic
808 Kick, Clap, HiHat and Snare; nonempty plugin declarations include FLEX and
Emphasizer. Emphasizer follows mixer-slot events and receives no rack-channel hint.
These are observations, not verified installed versions, resolved files or availability.
The template contains five rack channels, including inherited content/dependencies
outside the played Pattern. Nothing is deleted as apparently unused.

Unresolved evidence includes all four zero stored note lengths, flags `0x4000` and
raw trailing attributes; crop `ffffffff` float bits; the all-zero eight-byte clip
extension; event-172 meaning and opaque event families. No MIDI duration, sentinel
meaning, harmless-reserved-byte status or plugin assignment is invented.

The primary private report is `.tools/user-minimal-fl26-readiness.json`.
An independently authored synthetic MIDI binding probe uses source channel 2,
480 PPQ and start/duration 120/240 ticks, explicitly targeting local channel 0,
Pattern 0, lane 0; its preview is 24/48 ticks at 96 PPQ. Its full inputs/report live in
`.tools/fl26-readiness-probe/`. This demonstrates target/coordinate validation only;
it is not a user song or a confirmed production instrument assignment.

## Verification

Synthetic tests cover exact-build selection, byte-linked declarations, invalid/empty
text, repeated states, mixer context, raw zero lengths/crops/extensions, false backend
success, complete source snapshots, local target mismatches/ambiguity, exact/inexact
PPQ, stale evidence and JSON/output guards. Failure-path tests simulate concurrent
changes only on original synthetic fixtures, never the user's template.

The private integration test is opt-in:

```powershell
$env:SUNO2FLP_MUSIC2DAW_DIR = (Resolve-Path .tools/music2daw-6def9463d6fa-inspect).Path
$env:SUNO2FLP_FL26_TEMPLATE = (Resolve-Path templates/user-minimal.flp).Path
uv run pytest tests/integration/test_readiness_external.py
```

Without both variables it skips. Explicit invalid prerequisites fail. Full-suite,
installed-package and private-source verification were executed on 2026-10-15:

- Python 3.11.16 and 3.14.7 each passed **375 tests, 1 skipped**, with both private
  input/backend variables enabled. The skip is Windows symbolic-link privilege.
- Offline defaults passed **369 tests, 7 skipped**: six opt-in external checks and
  that privilege case. This batch adds 45 synthetic unit cases and one private-input
  integration case. Ruff lint/format and strict mypy (47 source files) passed.
- Independent manual/synthetic review found four P2 boundary issues: missing source
  hash/pairing checks, additional known mixer boundaries, multiple playlist events
  and unchecked snapshot hashes. Eight regression cases failed first and passed after
  one fix pass; the final full suites include those fixes. CodeRabbit was unavailable;
  no external review service, install or network request was used.
- Both package formats built and exclude private FLPs, backend binaries, environments
  and caches. Installed-wheel commands ran with an empty executable PATH and verified
  deterministic reports, complete snapshots/hashes, exact original source-channel/
  PPQ previews, blocked wrong bindings, paired arguments, output guards and refusal
  of a forged comparison. Neither local matches nor exit 0 enabled execution.
- Original source SHA-256/mtime and every pinned backend artifact match baseline;
  Python dependency files are unchanged. No FLP output was created. Private evidence
  is retained in `.tools/fl26-readiness-probe/verification.json` and the final archive/
  source receipt `.tools/fl26-readiness-release-verification.json`.

The preceding [FL26 reader verification](FL26_READ_ONLY.md) remains historical evidence
for that slice. This batch finishes the evidence/reporting work; dependency availability,
unknown field semantics, production instrument/content intent and host playback gates
are explicitly unresolved rather than reported as passed.
