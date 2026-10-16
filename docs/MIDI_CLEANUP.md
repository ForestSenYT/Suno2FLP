# Opt-in deterministic MIDI cleanup

Phase 1's cleanup slice changes only a derived note view. Defaults change no notes.
Original MIDI bytes, track/event order, event delta/absolute ticks, PPQ, source hash,
tempo/meter maps, track names/end ticks, controllers and metadata remain unchanged.
Every actual change retains a full before/after note snapshot in a versioned audit.
No MIDI file, FLP, audio or AI reconstruction is generated.

## CLI

```powershell
# No-op note view, plus a record showing that all operations were disabled.
uv run suno2flp clean-midi my-song/input/song.mid

# Each operation can be selected independently; this example selects all three.
uv run suno2flp clean-midi my-song/input/song.mid --remove-duplicates --min-duration-ticks 10 --quantize-grid-ticks 120 --output my-song/intermediate/cleaned.json

# Use project MIDI preferences and optionally override them.
uv run suno2flp clean-midi my-song/input/song.mid --config my-song/project.yaml
uv run suno2flp clean-midi my-song/input/song.mid --config my-song/project.yaml --keep-duplicates --min-duration-ticks 0 --no-quantize
```

The positional file is freshly imported. Without `--output`, stdout contains JSON.
Output requires a new `.json` file with an existing parent; overwrites and source
replacement are refused. An explicitly selected YAML config supplies MIDI preferences;
CLI values override it. `--quantize-grid-ticks N` enables quantization. `--no-quantize`
disables a configured grid; passing both flags is an error. `--keep-duplicates` and
`--min-duration-ticks 0` disable those configured operations.

Malformed/unsupported MIDI, invalid configuration/options, error diagnostics from import,
missing original timing, incompatible reprocessing and unsafe output paths fail with
nonzero exit status. Error-bearing imports are refused before any JSON output is created.
Original warnings are retained; warnings alone do not block cleanup. Successful JSON
can have zero notes after an explicitly selected filter; conductor/empty tracks remain.
`inspect`, `validate` and `import-midi` never apply cleanup implicitly.

## YAML and API

All default settings in `config/default.yaml` and `examples/project.yaml` are disabled:

```yaml
midi:
  preserve_timing: true
  remove_duplicates: false
  min_duration_ticks: 0
  quantize: false
  quantize_grid_ticks: null
```

`min_duration_ticks` is a nonnegative integer; zero disables filtering. A positive
integer grid is required when `quantize` is true. With quantization disabled the grid
must be null. Original timing preservation cannot be disabled. The earlier placeholder
`quantize: true` setting now requires an explicit grid rather than assuming a value.
One grid unit is one source PPQ tick; for example, 120 ticks at PPQ 480 is a sixteenth
note. The processor performs no seconds conversion or tempo/meter-based grid inference.

```python
from pathlib import Path
from suno2flp.core.config import MidiPreferences
from suno2flp.importer import MidiFileImporter
from suno2flp.midi_processor import DeterministicMidiProcessor

original = MidiFileImporter().import_file(Path("my-song/input/song.mid"))
preferences = MidiPreferences(
    remove_duplicates=True, min_duration_ticks=10, quantize=True, quantize_grid_ticks=120
)
cleaned = DeterministicMidiProcessor().clean(original, preferences)
for change in cleaned.cleanup.changes:
    print(change.operation, change.track_index, change.note_index, change.before, change.after)
```

`process(asset, source_root, preferences)` implements the existing `MidiProcessor`
protocol: it requires a MIDI asset, resolves its path within the supplied root,
freshly imports the file, and returns the same cleanup representation. Escape paths
are rejected. `clean` accepts a previously imported `ProcessedMidi` and does not reread
or write the file. Both defaults and provided settings are validated by Pydantic.

## Exact operation semantics

Tracks and notes are visited in their imported order. For each track:

1. Scan the original notes in order. Remove a note only if its duration is **strictly
   less than** `min_duration_ticks`; notes equal to the threshold are retained.
2. For each surviving note, optional duplicate removal keeps the first matching
   `(channel, pitch, velocity, start_tick, duration_ticks, release_velocity)` in that
   track. Track/channel/velocity/duration differences are preserved. Release velocity
   is read from the retained source release event after checking its index, release
   semantics, channel/pitch, tick and velocity range. Absent/unverified release metadata
   causes that note's duplicate check to be skipped with a warning.
3. Quantize the surviving starts to the nearest multiple of the explicit tick grid,
   using integer arithmetic. Exact half-grid ties round toward the later tick.
   Durations, velocities, source note-event indices and original timing fields stay
   unchanged. A grid-aligned note produces no change record. Quantization-created
   collisions are retained; they do not trigger a second implicit deduplication pass.

Removal audit entries follow the input note order; onset changes follow the surviving
note order. No pitch correction, duration quantization, overlap repair, channel merging,
silent-track removal, sustain extension or transcription is performed. Zero-duration
notes survive unless the selected duration threshold removes them.

Cleanup inherits the importer's track-local FIFO interpretation of overlapping notes.
That ambiguity warning stays present because the source event stream is unchanged;
duplicate removal is an explicit note-view choice, not proof of intended voice identity.
Short notes may be valid ornamentation, and quantization may change feel. The processor
does not infer musical intent or assert perceptual improvement.

## Preservation, audit and repeatability

`ProcessedMidi.cleanup` is null on import and contains `MidiCleanupRecord` after cleanup.
The record includes algorithm version 1, exact options and ordered `MidiCleanupChange`
entries. Each entry has operation, source track index (or track position when absent),
original imported-note index, complete `before`, and `after` (null for removals).
Removed notes remain reconstructible from the audit and original source events.
Each real change adds an informational `midi_cleanup_applied` diagnostic at its source
track/onset event. Missing release metadata uses `midi_cleanup_unverified_release`.

Input objects, options, source events and audit snapshots do not share mutable objects
with the returned view. `original_start_tick` and `original_duration_ticks` remain the
imported values on every retained/removed note, including when `start_tick` changes.
Fresh cleanup requires unmodified current timing equal to known original timing;
missing or already edited timing is rejected rather than relabeled as original.

Identical original input/settings produce identical results with no timestamps or
random choices. Applying the same preferences to an already recorded result returns
an independent identical copy without adding audit entries. Different preferences on
that result raise `MidiProcessingError`; reimport the source to start a new pipeline.
This avoids hidden stacking of lossy edits. Source imports with error diagnostics
also raise `MidiProcessingError`. Normal import/path errors retain their typed errors.

`track.events` and `track.end_tick` always describe the **source**, while `track.notes`
is the active derived view. Quantization can move a note beyond the source end tick;
it does not truncate the note or rewrite original metadata. Future arrangement/export
code must deliberately consume `notes`, compute its required extent, and handle source
controllers separately. Replaying `events` reproduces original timing, not cleanup.
There is no cleaned MIDI binary writer in this slice.

The [faithful arrangement engine](ARRANGEMENT.md) consumes this selected view with
`note_view="active"` / `arrange --note-view active`, retains cleanup/source snapshots,
and computes converted track extents. Controller-event playback/export is still deferred.

## Synthetic verification

Tests cover default no-op behavior, independent options, combined ordering, threshold
equality, duplicate identity/release velocities, missing release metadata, zero-length
notes, exact tie rounding, large integer ticks, collisions introduced by quantization,
unchanged source events/maps/end ticks/hash, immutable inputs and audit snapshots,
JSON round trips, repeatability, reprocessing rules, invalid options and source-root
containment. CLI fixtures verify YAML overrides, output refusal and original-file safety.
All tests remain offline and use synthetic MIDI without DAW/GPU/AI prerequisites.

Verified locally on 2026-10-15: **89 passed, 1 skipped** on both Python 3.11.16 and
3.14.7. The skip is the existing Windows symlink-permission test. Ruff formatting/lint,
strict mypy checks, source/wheel builds and installed CLI smoke checks passed. The
installed command verified default no-op, all selected operations, before/after audit,
original ticks/events/maps/hash and refusal to overwrite outputs/source. Distribution
inspection found no bundled environments, downloads or caches. Remote CI and actual
DAW/backend interaction were not run.
