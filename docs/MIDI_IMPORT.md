# Track-aware MIDI import

Phase 1's first slice imports existing MIDI without cleanup, quantization, tempo
inference, seconds conversion, arrangement generation, or MIDI/FLP writing. It runs
offline with the existing mido dependency. No new runtime dependency is required.

## Usage

```powershell
uv run suno2flp import-midi my-song/input/song.mid
uv run suno2flp import-midi my-song/input/song.mid --output my-song/intermediate/midi.json
```

Without `--output`, stdout contains the JSON result. Output paths must end in `.json`,
have an existing parent directory and differ from the source; existing files are
refused. Errors in result diagnostics return exit code 1 while preserving the partial
representation as JSON. Warnings alone return 0. Unreadable/malformed sources and
unsupported timing raise a typed error; no representation is emitted for those files.
`inspect` and `validate` retain their basic metadata behavior; deep import is explicit.

```python
from pathlib import Path
from suno2flp.importer import MidiFileImporter

midi = MidiFileImporter().import_file(Path("my-song/input/song.mid"))
for track in midi.tracks:
    print(track.index, track.name, track.end_tick, len(track.notes))
for tempo in midi.tempo_map:
    print(tempo.tick, tempo.microseconds_per_beat, tempo.source_track)
```

The result uses the shared `ProcessedMidi` contract. In this stage that name identifies
an imported representation; it does not assert any cleanup or transformation occurred.
The separate [deterministic cleanup processor](MIDI_CLEANUP.md) implements `MidiProcessor`
and adds an optional cleanup record to derived results. Import itself leaves that
record absent and never cleans or quantizes notes.

## Timing and provenance contract

- Supported inputs are SMF Type 0 and Type 1 with positive PPQ. Type 2 independent
  timelines and SMPTE/zero divisions raise `MidiImportError` rather than being coerced
  to a shared beat grid. Type 0 requires exactly one track; files must have tracks.
- The file is read once into a byte snapshot. `source` is its resolved absolute path;
  `source_sha256` fingerprints exactly the bytes parsed. Source bytes are never written.
- Tracks retain source order and zero-based `index`, including conductor/empty tracks.
  The first nonempty track-name message supplies `name`; unnamed tracks use `Track N`
  with human-facing 1-based N. All name messages remain in the event stream.
- Every decoded message is retained as a JSON-compatible `MidiEvent.message`, including
  controllers, program changes, text, sysex, unknown metadata and end-of-track.
  Binary payload tuples become JSON arrays. `event_index`, `delta_ticks`, and absolute
  `tick` retain track-local source ordering/timing. `end_tick` includes trailing silence.
- `start_tick`/`duration_ticks` equal `original_start_tick`/`original_duration_ticks`
  for imported paired notes. Channel numbering stays 0–15. Note-on/off event indices
  point into that track's retained event stream; release velocity remains in the raw
  message. Notes are ordered by onset event, even when releases arrive in another order.
- Tempo and meter maps contain only explicit source events, retaining their ticks,
  source track and source event indices. Maps sort by `(tick, source_track, source_event)`.
  Identical simultaneous events remain present; different simultaneous values warn and
  remain unresolved. Stable ordering is a serialization rule, not a musical preference.
- Missing maps remain empty. Consumers must apply MIDI's default 500000 microseconds
  per beat (120 BPM) and 4/4 before the first explicit change. No default is presented
  as a source event. A later first change does not alter earlier source ticks.
- Meter extraction includes numerator, power-of-two denominator, clocks per click and
  notated 32nd notes per beat. Denominators through the SMF byte exponent's full range
  are representable. No meter changes are inferred from note positions.

This is preservation of decoded musical events/timing, not a byte-identical MIDI export.
Running status and byte encodings are decoded by mido; the original file and hash are
the byte-level authority. There is no MIDI writer or sound-rendering claim.

mido 1.3.3 drops nonzero delta times on unknown metadata. When such events are present,
an isolated SMF framing/timing pass recovers original deltas from the same byte snapshot,
checks track/event counts, and restores the local decoded messages before extraction.
Payload interpretation stays with mido. No global decoder state is patched. Synthetic
byte fixtures verify later notes, maps and track ends retain the correct ticks.

## Note interpretation and diagnostics

Pairing is local to each track and `(channel, pitch)`. A velocity-zero note-on acts as
a release. Overlapping onsets of the same channel/pitch use FIFO pairing with an
ambiguity warning; notes have no voice IDs that could establish the intended pairing.
Zero-length notes are retained. Sustain and other controllers remain as source events;
derived durations describe key-held ticks, not rendered sounding duration. Note releases
in another track are not paired across tracks.

| Code | Severity | Result |
| --- | --- | --- |
| `overlapping_note` | warning | FIFO interpretation; source events retained |
| `unmatched_note_off` | warning | Release retained as raw event; no fabricated note |
| `unclosed_note` | warning | Onset retained as raw event; no invented release/duration |
| `conflicting_tempo` / `conflicting_meter` | warning | Every change retained; no silent conflict resolution |
| `invalid_tempo` / `invalid_meter` | error | Nonpositive tempo/numerator excluded from structured map; raw event retained |

Diagnostics include the resolved source path and zero-based track/event indices.
Malformed SMF parsing and unsupported timing use `MidiImportError`, a `Suno2FLPError`.
As with Phase 0 discovery, import is intended for trusted local exports; parsing has
no resource sandbox or large-file limit. Conflicts, incomplete notes and unverified
instrument identity should be reviewed before any future cleanup or reconstruction.

## Synthetic verification

`tests/unit/test_midi_import.py` covers conductor/empty tracks, format/channel separation,
delta/absolute tick retention, tempo/meter changes and provenance, trailing silence,
velocity-zero releases, overlap/unmatched policies, raw controllers/sysex/unknown meta,
running status, map conflicts/duplicates, malformed files, Type 2/SMPTE rejection,
nonzero unknown-metadata deltas and malformed key-signature error translation,
JSON round trips, repeatability and unchanged source bytes/hash. CLI tests cover JSON
output, exclusive file creation and diagnostic exit codes. Existing Phase 0 tests
continue to run without network, DAW, GPU, model downloads or proprietary plugins.

At import-slice completion on 2026-10-15: full suite **60 passed, 1 skipped** on Python 3.11.16
and 3.14.7. The existing skip is Windows symlink creation permission. Ruff lint/format
and strict mypy checks passed. The source distribution/wheel built, and the installed
CLI imported a synthetic multitrack file with a delayed unknown event, preserved its
source hash/ticks/maps, created JSON, and refused an existing output. No remote CI or
external DAW/integration run is claimed.
