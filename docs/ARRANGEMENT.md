# Faithful arrangements — first Phase 2 slice

`FaithfulArrangementEngine` builds a DAW-independent arrangement from one or more
imported/cleaned `ProcessedMidi` representations. It preserves the selected paired
notes and keeps all source tracks in order, including conductor/empty tracks. All
inputs align at beat zero; no offsets, note rearrangement, channel merging, instrument
inference, re-orchestration or cleanup is applied. “Faithful” describes this structural
policy, not audible reconstruction. Import warnings (including unmatched notes) remain
visible, with all original events retained in source snapshots.

## CLI

```powershell
# Fresh MIDI or previously imported MIDI JSON; default precision and timing rules.
uv run suno2flp arrange song/input/piano.mid song/intermediate/bass.json --output song/intermediate/arrangement.json

# A cleaned result requires explicit selection of its active notes.
uv run suno2flp arrange song/intermediate/cleaned.json --note-view active --target-ppq 960 --output song/intermediate/arrangement.json

# Explicitly choose the second input's tempo/meter maps when sources disagree.
uv run suno2flp arrange piano.mid bass.mid --timing-source 1
```

Inputs are `.mid`/`.midi` files (fresh import) or `.json` serialized `ProcessedMidi`
objects from import/cleanup. Input order defines stable zero-based input indices.
Repeated inputs/names are retained as separate sources/tracks. Arrangement JSON itself
is not a MIDI input. Without `--output`, stdout is JSON; `--title` sets the title.
Output must be a new `.json` file with an existing parent, distinct from inputs;
overwrites are refused. Errors/conflicts fail before creating output. Flags apply
only to this command; project YAML and cleanup options are not applied implicitly.
No source files or existing projects are written, and no MIDI/FLP binary is generated.

## API and note views

```python
from pathlib import Path
from suno2flp.arrangement import FaithfulArrangementEngine
from suno2flp.core.models import ArrangementOptions, MusicalMetadata
from suno2flp.importer import MidiFileImporter

original = MidiFileImporter().import_file(Path("song/input/song.mid"))
arrangement = FaithfulArrangementEngine().arrange(
    [original],
    MusicalMetadata(title="Faithful"),
    "faithful",
    options=ArrangementOptions(target_ppq=960),
)
```

The engine implements the existing `ArrangementEngine` protocol, now extended with
optional keyword `options`. Only `mode="faithful"` is implemented; reinterpretation
fails explicitly. Inputs must have tracks, known original note timing and no error
diagnostics. Warnings are copied into the result with input indices.

`ArrangementOptions.note_view="imported"` is the default. It accepts fresh imports
whose current note timing equals their original timing and rejects cleaned objects
(including recorded no-op cleanup), preventing accidental view changes. Choose
`note_view="active"` to consume each input's current `notes`: fresh imports remain
imported, while cleaned inputs use their cleaned notes. Mixed fresh/cleaned inputs
are supported in that explicit mode, with each actual view recorded separately.
To use originals after cleanup, supply the original import instead of silently undoing
its audit. Missing timing or unrecorded timing edits raise `ArrangementError`.

The API is pure with respect to files: it uses supplied snapshots, does not reopen
source paths and does not independently authenticate externally edited JSON or audits.
Missing source hashes remain null and emit `source_hash_unverified`; no hash or source
evidence is fabricated. Use trusted outputs of the import/cleanup stages.

## PPQ conversion and extent

- Default `target_ppq=None` resolves to the least common multiple of all input PPQs,
  so all integer source times have exact representations. The resolved PPQ is stored
  in `Arrangement.ticks_per_beat`; requested options remain in `build_options`.
- Explicit positive integer `target_ppq` / `--target-ppq` selects another resolution.
  `ppq_rounding="error"` is the default: inexact selected note starts/ends, track ends
  or canonical map changes raise `ArrangementError`.
- `ppq_rounding="nearest"` / `--allow-rounding` explicitly permits nearest-tick
  approximation, with exact half ties toward the later tick and a `ppq_rounded`
  warning for every inexact converted point. All arithmetic uses integers/Fractions;
  no floating-point seconds or tempo-dependent tick scaling is used.
- Start and end are converted independently; duration is `converted_end - converted_start`,
  preserving the endpoint policy rather than rounding durations independently.
  A positive duration that collapses to zero is rejected. Existing zero-length notes
  remain zero-length. No minimum duration is invented.
- Each arranged track starts at zero. `end_tick` is the maximum of converted original
  track end and selected note ends, so a cleaned note beyond the original end is
  retained. Source end ticks and source notes stay untouched in snapshots.

The representation is DAW-independent: the source LCM can exceed MIDI/DAW PPQ limits.
A future backend must validate its own bounds. This slice makes no binary-format
compatibility claim and imposes no speculative DAW limit on arrangement integers.

## Timing-map consensus and explicit authority

The engine compares **effective functions over beats**, before target-PPQ rounding.
It includes MIDI's initial defaults (500000 microseconds/beat and 4/4 with clocks 24,
notated 32nds 8) until the first explicit event. Missing maps therefore declare the
MIDI default function; they do not silently abstain from consensus. Tempo values stay
microseconds per quarter note, and all four meter fields participate in comparison.

Normalization groups same-source events at the same exact beat. Identical duplicates
are harmless; distinct values are unresolved conflicts. Redundant later events with
the same active value are ignored for comparison, so equivalent functions can agree
despite different redundant event layouts. Every original map event remains in its
source snapshot. Different change times or later divergence are conflicts even if no
two explicit events share a tick across inputs. Rounding cannot hide those differences.

By default all input functions must agree. Canonical output maps use input zero's
normalized representation, with explicit initial defaults only where needed. Output
defaults are marked `is_default=true` and have no source event index. Explicit changes
carry `source_input`, `source_track` and `source_event` into their snapshot; their
output ticks use arrangement PPQ.

`timing_source=N` / `--timing-source N` explicitly selects one input's **both** tempo
and meter functions. Divergent maps from other inputs are ignored with
`timing_conflict_overridden` warnings; all evidence remains in snapshots. Internal
conflicts in ignored inputs also warn, while conflicts in the selected input still
fail. Distinct canonical changes collapsing onto one target tick also fail: choose
a higher PPQ instead. Authority does not repair malformed input/error diagnostics.

An override can change how other inputs would play under their own timing maps.
It is an explicit shared beat-grid decision, not automatic time warping or proof of
audible fidelity. No notes are stretched to reconcile differing tempo intentions.

## Provenance and units

`Arrangement.sources` stores input indices, actual imported/cleaned views and independent
full `ProcessedMidi` snapshots, including source path/hash, raw decoded events, original
PPQ/ticks, diagnostics and cleanup before/after records. Large sources produce larger
JSON by design; no source hash alone substitutes for the event evidence.

Every arranged track records `source_input`, `source_track` (original index or position),
`source_track_position` and `source_ticks_per_beat`. `note_origins` is parallel to
`notes`; each origin identifies a note index in that selected snapshot track and its
input start/duration before PPQ conversion. Pitch, velocity, channel and source note
event indices are retained. Current `start_tick`/`duration_ticks` use arrangement PPQ;
`original_start_tick`/`original_duration_ticks` remain in **source PPQ**, including
pre-cleanup timing. These differing units must not be mixed.

`algorithm_version=1` and exact `build_options` record the construction policy.
Identical inputs/order/options produce identical results without timestamps. Metadata,
sources, notes and diagnostics are copied independently of input objects. Generic
`instrument_hint` remains unset by the builder; raw controllers/programs are preserved
but not converted into arrangement automation. The next explicit stage now adds
[per-channel instrument-role annotations](INSTRUMENT_MAPPING.md), also available via
`arrange --instruments mapping.yaml`. Without that flag, arrangement does not map or
infer instruments. Plugin loading and DAW control remain outside this slice.

## Synthetic checks

Fixtures cover same/mixed PPQ, exact LCM and explicit conversion, endpoint rounding and
half ties, positive-duration collapse, zero notes, source extents after cleanup,
view selection, track/note counts, complete provenance, immutable inputs, repeatability,
JSON round trips, default/redundant/later-divergent maps, internal and cross-input
conflicts, explicit authority including later input indices, conversion collisions,
missing provenance, invalid options and CLI file safety. Tests remain offline without
FL Studio, MCP, GPU, proprietary plugins or copyrighted music.

At faithful-slice completion on 2026-10-15: full suite **117 passed, 1 skipped** on Python 3.11.16
and 3.14.7. The skip is the existing Windows symlink-permission test. Ruff lint/format,
strict mypy, source/wheel builds and installed CLI smoke checks passed. Installed checks
covered mixed PPQ, imported/cleaned views, source provenance, conflict rejection and
authority, explicit rounding, exclusive output creation and unchanged source hashes.
Distribution inspection found no bundled environments/downloads/caches. Final read-only
review reported no actionable findings; remote CI and actual DAW operations were not run.
