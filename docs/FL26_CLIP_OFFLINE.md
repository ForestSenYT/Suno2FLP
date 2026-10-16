# FL26 offline crop and playlist-flag regression evidence

This slice adds **tests and documentation only**. Runtime code, writer policy,
inventory schemas and backend installations are unchanged. FL Studio control is
paused at the user's request. Host opening, resaving, reopening, resize behavior and
listening acceptance for the six experimental candidates remain **pending**.

## Evidence states

The [earlier field observations](FL26_FIELD_EVIDENCE.md) came from a GUI-created
positive reference and separately saved GUI crop/Slide copies. Those observations
establish selected original field forms, not the behavior of native-written outputs.

A separate, interrupted host-validation batch produced six privately stored
byte-patched copies of the positive reference. This was a laboratory experiment,
not a successful restricted-writer build. All original/reference files were retained.
This offline slice reads those existing candidates and creates new JSON/text receipts;
it does not rewrite them, create further private FLPs, run the backend or control a DAW.

| Existing candidate | Proposed length, ticks | Raw clip flags | Signed crop fields | Extra proposed edit | Host result |
| --- | --- | --- | --- | --- | --- |
| Default grow | 768 | `0x8040` | -1 / -1 | none | Pending |
| Fixed sentinel grow | 768 | `0x0040` | -1 / -1 | none | Pending |
| Explicit grow | 768 | `0x0040` | 0 / 768 | none | Pending |
| Explicit short | 192 | `0x0040` | 0 / 192 | none | Pending |
| Explicit odd length | 250 | `0x0040` | 0 / 250 | none | Pending |
| Explicit grow with notes | 768 | `0x0040` | 0 / 768 | second note starts at 576 | Pending |

All retain PPQ 96 and clip position zero. These are **proposed byte values**, not
observed FL Studio geometry. The matrix does not establish the independent meaning
of `0x8000` or prove that any candidate opens, plays, scales or survives a host save.
It also does not establish an arbitrary time-stretch or crop-write feature.

## Private provenance audit

The original experiment is under `.tools/fl26-clip-write-validation-v1/` with
`baseline.json`, `probe-provenance.json`, six `probes/*.flp` and an empty `host/`.
The new `offline-review-v1/provenance-audit.json` records:

- exact source/candidate SHA-256, size and modification time, plus the existing manifests' hashes;
- original inventory event/row indices, absolute offsets, complete raw clip records,
  signed crop fields and proposed flags/lengths;
- actual changed-byte offsets compared with an independently reconstructed budget:
  clip length bytes 8..11, flags 18..19 and crops 24..31, plus second-note start bytes
  only in the explicitly declared note-movement candidate;
- identical bytes outside that budget, matching event order and record evidence;
- unchanged fingerprints for all five original/reference FLPs and all 19 original /
  22 adapted backend artifacts;
- explicit `pending_not_performed` host-open/save/reopen states and unverified audio.

The audit does not fabricate candidate backend inspection JSON or a ready write intent.
Byte agreement proves provenance and bounded changes, not host acceptance. Paths, raw
project records, candidates, backend manifests and audit receipts stay local and ignored.
Public tests author independent records from scalar values, without copying private
project records or plugin state. Missing future host results stay missing.

## Offline synthetic coverage

`tests/unit/test_fl26_clip_offline.py` covers the following real boundaries:

- All six candidate shapes retain byte-linked inventory/prototype snapshots and are
  refused before encoding, including forms recognized by the read-only matcher.
- Exact 480-to-96 PPQ conversion is checked at small, ordinary, doubled and non-bar
  spans. Even a matching zero-start/full-span crop does not authorize writing.
- Negative zero, paired/mixed sentinels, infinities, a distinct NaN and a subnormal
  preserve their exact bits through JSON and cannot be normalized into permission.
- Each individual bit of the 16-bit clip-flags field remains blocked independently
  of the crop gate, even with exact positive-zero crops and a claimed host reference.
- Independent structural verification rejects mutation of either flag byte or any
  of the eight crop bytes in an authored synthetic output. Structural success retains
  `compatibility: unverified`; no actual host inference is made.
- File-based builds with unverified crop/flag evidence fail before encoder, process,
  staging or publication, leaving sources unchanged and no output directory contents.

These are regression tests for existing restrictions; no new runtime allowance is
introduced. In isolated ignored copies, deliberately removing the crop gate causes
10 new cases to fail; removing the nonzero-flag gate causes 15 to fail; removing the
verifier's preserved clip-suffix check causes 10 to fail. The artificial failures
demonstrate regression sensitivity and are not failures of the tracked runtime.
Mutation logs/receipt stay in `offline-review-v1/`; tracked runtime sources are unchanged.

Run without any DAW or external backend:

```powershell
uv run pytest tests/unit/test_fl26_clip_offline.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Remaining writer boundary

`writer_crop` still rejects every crop pair except exact positive-zero bits, including
paired `ffffffff` and explicit integer endpoints. `writer_clip_attributes` still rejects
nonzero flags/groups/mute and invalid geometry. Read-only pattern observations and
operator attestations cannot override either gate. Unknown events, partial inventory,
dependency/instrument intent and source/PPQ integrity retain their independent checks.
Old read-only plans remain permanently non-executable.

Future host evidence would need the exact candidate hash, actual displayed geometry,
errors/warnings, a separately named new host save, reopened readback and field comparison.
Any such work stays deferred while computer control is paused. No reopening, resizing,
normalization or audible-compatibility claim is added by this offline slice.

## Verified results for this offline slice

The new file adds **49 synthetic cases**. Local Python 3.11 and 3.14 each passed
**570 tests, 17 skipped** with external prerequisites disabled: 16 opt-in external
cases and the Windows symbolic-link privilege case. Ruff lint/format and strict mypy
(57 runtime modules) passed. No runtime source file was changed. Both package formats
built offline; archive contents are checked separately for private media, backend
sources/binaries and caches before publication of code changes.

The private `offline-review-v1/` receipts retain the six-candidate provenance audit,
three deliberate-defect checks, package audit and test summary. A pass in any of those
receipts is explicitly offline evidence; host opening/resaving/reopening and audio
remain pending/unverified and cannot authorize crop or flag writes.
