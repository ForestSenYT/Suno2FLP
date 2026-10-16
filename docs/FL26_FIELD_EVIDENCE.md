# FL26 note attributes and Pattern crop observations

Independent FL Studio **26.1.7 build 5654**, PPQ **96** GUI experiments narrow two
previously unresolved checks. Ordinary positive Piano roll notes can carry `0x4000`;
the assessed Pattern crop fields can contain signed integer tick endpoints rather
than floating-point beats. This is selected-field evidence, not complete FLP or host
compatibility. It does not make either private reference writer-eligible.

## Controlled local observations

The independently created Empty-template reference uses one default 3x Osc, 120 BPM,
4/4, two one-beat notes at ticks 0/192 and one naturally placed one-bar Pattern clip.
The GUI displays C5/E5; stored pitches are 60/64 and velocities are 100. The saved
baseline was reopened and checked. Song transport and main output meter activity
were observed; the agent did not capture or hear audio. Meter activity is not listening
acceptance. The three differential copies were saved, not claimed to be auditioned.

Each subsequent change was made in FL Studio and saved under a **different new local
filename**, preserving both the baseline and `user-minimal.flp`. Crop experiments
change one edge at a time. The Slide experiment starts from the double-cropped copy
and changes only the first note's Slide switch; its dialog reads `slide to C5`.

| Probe | GUI change | Clip position / length, ticks | Offsets 24 / 28 as signed i32 | Clip flags | Note flags |
| --- | --- | --- | --- | --- | --- |
| Baseline | Positive Piano roll notes; untrimmed Pattern placement | 0 / 384 | -1 / -1 | `0x8040` | `0x4000`, `0x4000` |
| Left crop | Move left edge inward one beat | 96 / 288 | 96 / 384 | `0x0040` | unchanged |
| Both crops | Also move right edge inward one beat | 96 / 192 | 96 / 288 | `0x0040` | unchanged |
| Slide | Enable only first note's Slide | unchanged | unchanged | unchanged | `0x4008`, `0x4000` |

Ordinary copies retain group 0, reserved bytes 13..15 zero, fine-pitch 120, release 64,
pan 64 and trailing bytes `8080`. The observations establish this **combination**, not
independent meanings for every bit or trailing attribute. `0x4000` alone does not prove
an ordinary note or supply a duration for zero-length records in the original project.

The endpoint interpretation follows controlled GUI movement: start stays 96 while end
changes 384 to 288, and `end - start` equals displayed length. No float multiplication,
rounding or normalization is involved. Paired `-1` with `0x8040` identifies the observed
untrimmed form; concrete endpoints and general bit `0x8000`, loop, stretch and automatic
resize behavior remain unproven.

Private records retain paths, source/reference hashes, sizes, mtime, byte-linked raw
records, GUI actions and parent relationships in
`.tools/user-reference-fl26-positive-v1-host-evidence.json` and
`.tools/fl26-host-field-differential-v1.json`. Public tests construct tiny original
records from scalar values, without copying private FLP records or plugin state.
No private FLP, report or fetched/generated backend file is committed.

## Implementation boundary

`core/fl26_fields.py` contains pure observations requiring the exact FL26 read profile.
The note matcher requires positive duration and the **entire** observed attribute
combination. It distinguishes the observed Slide form without enabling Slide writing.
Other flags, groups, reserved/tail bytes and altered combinations remain unresolved.
No mask silently strips bits.

The crop matcher requires an 88-byte **Pattern** record, nonnegative position, positive
length and group 0. It recognizes only paired signed `-1` with flags exactly `0x8040`
(no concrete endpoints), or nonnegative ordered signed endpoints with flags exactly
`0x0040` and a span equal to retained length (explicit template-tick endpoints).
Channel/audio clips, FL25, mixed sentinels, other flags/groups, negative/inconsistent
spans and unknown layouts do not inherit the interpretation. Extensions and remaining
attributes stay opaque.

`assess-template` emits `ordinary_note_attributes_observed`,
`pattern_crop_default_observed` or `pattern_crop_ticks_observed`, linked to original
event/row indices. Other forms retain unresolved findings. Every readiness report
still has `execution_allowed: false`, `writer_status: blocked`, `compatibility: unverified`.

Inventory v1/v2 JSON and canonical snapshots stay unchanged for backward compatibility:
`start_offset`/`end_offset` retain **legacy float projections** and original bits. For
these Pattern forms that projection is not a timing unit. `ffffffff` still has
`value: null` and its conservative nonfinite-projection diagnostic; explicit ticks can
project to tiny finite floats. Separate observations neither rewrite historical fields
nor silently promote inventory coverage.

The adapted Music2DAW process is unchanged. Selected tempo/count agreement does not
check individual crop conversion or establish MIDI-export/editor correctness. The
old backend retains its parsing differences. Neither backend is invoked for native
writing or given fabricated local values.

## Narrow writer change and remaining blockers

The separate writer permits **preserving** the complete observed ordinary positive-note
attributes from a reviewed, hash-pinned prototype, alongside its existing synthetic
zeroed form. It changes only authorized coordinates/channel/pitch/velocity. Independent
verification checks all preserved attributes, including `0x4000` and `8080`; changed
bits fail. Full template/inventory/binding/prototype hashes and dependency/instrument/use
reviews stay mandatory. Saved blocked intents cannot be promoted by changing status.

Slide (`0x4008`), zero durations and nearby unobserved combinations still block. Crop
writing retains its previous exact positive-zero bit requirement: **neither paired
`ffffffff` nor explicit cropped endpoints gain write eligibility**. Replacing notes or
resizing clips with those forms needs separate output/host evidence. Clip flags,
opaque families/extensions, partial inventory, dependencies, routing, instrument intent
and listening acceptance retain independent gates. Both private original and positive
reference remain blocked before encoding/staging. No private-source native output is
created by this slice.

## Verification

Offline cases cover ordinary preservation, exact PPQ, independent byte verification,
Slide/zero-length rejection, prototype hashes, integer crop units, sentinel pairs,
profile/type isolation, invalid spans/flags/groups and continued crop-write refusal.
Existing inventory and saved-bundle regressions remain applicable.

Four opt-in read-only cases use genuine adapted inspection of the local GUI references.
Missing configuration skips explicitly; a configured missing file fails. They check
source bytes/mtime and backend fingerprints before/after, and never encode.

```powershell
$env:SUNO2FLP_FL26_REFERENCE_DIR = (Resolve-Path templates).Path
$env:SUNO2FLP_FL26_ADAPTED_BACKEND = (Resolve-Path .tools/music2daw-6def9463d6fa-fl26-inspect-v1).Path
uv run pytest tests/integration/test_fl26_field_reference.py
```

Local filenames are `user-reference-fl26-positive-v1.flp`,
`user-reference-fl26-left-crop-v1.flp`, `user-reference-fl26-both-crop-v1.flp` and
`user-reference-fl26-slide-v1.flp`. They stay ignored; CI needs no private files or DAW.
See the [Chinese guide](FL26_REFERENCE.zh-CN.md) and [writer limits](FL26_WRITER.md).

Local verification on 2026-10-15: Python 3.11 and 3.14 each passed **537 tests,
1 skipped** with original/adapted backends and all four GUI references enabled.
Offline defaults passed **521 tests, 17 skipped** (16 external cases and the Windows
symbolic-link privilege case). This slice adds 46 synthetic unit cases and four opt-in
reference cases. Ruff lint/format and strict mypy (57 source modules) passed. Independent
code review found no actionable issue. Both package formats built offline and their
contents exclude private media, caches and backend sources/binaries; the installed
wheel inspected/assessed the actual positive reference while retaining blocked status.

Current-file reports for all four probes and the unchanged original, plus separate
blocked native preflights for positive/original inputs, remain private under
`.tools/fl26-field-validation-v1/`. They confirm that the positive reference no longer
has `writer_note_attributes`, while `writer_crop`, incomplete inventory, clip attributes
and other independent blockers remain. The original still has nonpositive note ranges.
Original and baseline SHA/size/mtime and both backend fingerprints remain unchanged;
no private input was encoded or staged.

## Subsequent offline regression slice

[Offline crop/flag coverage](FL26_CLIP_OFFLINE.md) adds regression tests and a private
byte-budget/provenance audit of six separately created experimental candidates. Host
control was interrupted before candidate results existed and is now paused at the
user's request. Candidate opening/save/reopen/resize behavior remains pending; the
earlier GUI observations are not promoted into acceptance of these byte-written files.
Runtime code and all unverified crop/clip write gates remain unchanged.
