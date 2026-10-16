# Explicit instrument-role mapping

This Phase 2 slice adds optional role **annotations** to faithful arrangements.
It does not infer instruments, load plugins/presets, send MIDI, apply program changes,
change channels or contact a DAW. Notes, timing, PPQ, sources, raw events and cleanup
audits remain unchanged. Plugin hints are opaque text with status `unverified`.

## Usage

```powershell
# Map a previously built faithful arrangement to a new JSON file.
uv run suno2flp map-instruments arrangement.json --mapping mapping.yaml --output mapped.json

# Or explicitly request mapping while constructing the arrangement.
uv run suno2flp arrange piano.mid bass.mid --instruments mapping.yaml --output mapped.json
```

The default arranger never applies mapping. `config/instruments.yaml` is an available
catalog whose `mappings: []` makes no assignments. `examples/instrument_mapping.yaml`
demonstrates explicit rules; adapt its indices/channels to your inputs before use.
Without `--output`, stdout contains JSON. Outputs must be new `.json` files with
existing parents; existing files and source replacement are refused. Invalid config,
unmatched/ambiguous/overlapping rules or invalid arrangement provenance fail before
any output is created. Inputs and mapping YAML are read-only.

## YAML schema and numbering

```yaml
schema_version: 1
roles:
  piano:
    general_midi_program: 1
    plugin_hint: User-selected piano preset
  drums:
    percussion: true
mappings:
  - source_input: 0
    source_track_position: 1
    source_channel: 0
    role: piano
  - source_input: 0
    source_track_position: 1
    source_channel: 9
    role: drums
```

Role IDs are exact, case-sensitive nonblank strings without surrounding whitespace.
Roles are user-defined; their names do not trigger special behavior. Role fields:

| Field | Meaning |
| --- | --- |
| `general_midi_program` | Optional **1-based** melodic GM hint, integer 1..128; no program-change event is written |
| `plugin_hint` | Optional nonblank descriptive label, never executed, resolved, installed or loaded |
| `percussion` | Explicit boolean annotation, false by default; never forces a drum channel |

Percussion roles cannot specify a melodic GM program. Preset/kit selection remains
future backend work. Source MIDI program events keep their original zero-based values.
The old unused role field `midi_channel` is rejected; use `percussion: true` for the
drum-role catalog entry, never a destination channel. Availability/status/extra fields
are rejected in role definitions. Role definitions may be unused by rules.

Rule selectors are **zero-based**, nonnegative integers:

- `source_input`: input index recorded by the faithful arranger, not the JSON source filename.
- `source_track_position`: position in that input snapshot's `midi.tracks`, not display name
  or concatenated arrangement-track index. The original track ID is preserved separately.
- `source_channel`: optional integer 0..15. Omit/null to annotate every evidenced source
  channel in that track. This is a selector, never a channel rewrite.
- `role`: exact key in `roles`; unknown roles fail validation.

Channel evidence is the union of active note channels and valid channel fields in the
retained source event stream, including program/control events. Thus a cleaned track
with no remaining notes can still receive an explicit role for its preserved source
channels. A metadata-only track with no evidenced channels cannot be assigned a role.
Channels are never inferred from role names, track names, program numbers or MIDI defaults.

Duplicate exact selectors fail config validation. Rules that expand onto the same
track/channel also fail, even when their role is identical; there is no first/last-wins
precedence. Every rule must resolve exactly one source track and at least one evidenced
channel. Repeated track names and multiple input files remain unambiguous through indices.

Partial mapping is allowed. Other channels have no role annotation and remain unchanged.
When rules are present, `instrument_role_unmapped` warns per track about those channels.
The record lists all unmatched targets. An empty rule list intentionally maps nothing,
records the unmapped targets and does not emit warnings just for selecting a catalog.

## API and provenance

```python
from pathlib import Path
from suno2flp.arrangement import ExplicitInstrumentMapper
from suno2flp.core.instrument_config import load_instrument_mapping

document = load_instrument_mapping(Path("mapping.yaml"))
mapped = ExplicitInstrumentMapper().apply(arrangement, document)
```

`load_instrument_mapping` uses the existing safe YAML parser with duplicate-key rejection,
validates `InstrumentMappingConfig`, and returns an `InstrumentMappingDocument` holding
the config, resolved YAML path and SHA-256 of exactly the bytes parsed. Invalid data,
unknown keys and unreadable files raise `ConfigurationError`.

For programmatic rules, construct `InstrumentMappingDocument(config=...)`. Path/hash may
remain null; none is fabricated. `apply` is pure with respect to files and uses the
provided document/snapshots. It requires faithful mode, source snapshots, consistent
input/track links and note origins whose source channels match the selected source view.
Error-bearing arrangements and unrecorded pre-existing role assignments are rejected.
It validates the structural links used for selection, not the authenticity of externally
edited JSON, MIDI snapshots or cleanup audits.

Each `ArrangementTrack.instrument_roles` entry records source channel, role ID, hints,
percussion flag, matching rule index and `plugin_status="unverified"`. Entries sort by
source channel. The older generic `instrument_hint` field is left untouched; a
multichannel track can now hold different explicit roles without losing that distinction.

`Arrangement.instrument_mapping` stores algorithm version 1, the full independent
document snapshot, rule matches (arrangement-track/channel/rule indices), and unmapped
targets. Matches follow config-rule order then ascending channel; unmapped targets
follow arrangement-track/channel order. Complete source/cleanup/build provenance remains
unchanged. Role changes never imply the suggested plugin exists or that playback changed.

Identical arrangement/document inputs produce identical independent results with no
timestamps or random selection. Reapplying the identical document to its recorded
result returns an independent identical copy. A different document (including changed
origin/hash) requires the original unmapped arrangement; mapping never silently replaces
prior provenance. Source snapshots and channel links are revalidated even for identical
reapplication. This is separate from MIDI cleanup and PPQ/timing-map construction.

## Synthetic verification

Fixtures cover per-channel and track-wide rules, multichannel/percussion tracks,
duplicate track names, multiple input indices, unknown/unmatched/overlapping rules,
strict program/channel bounds, duplicate YAML keys, config hashes, partial/empty maps,
cleaned-empty source-channel evidence, invalid provenance, unchanged notes/events/channels/
timing/source snapshots, copied audits, JSON round trips, deterministic reapplication,
inert plugin labels and both CLI entry points with overwrite protection. All tests run
offline without plugins, FL Studio, MCP, network access or copyrighted media.

Local slice verification on Windows: Python 3.11.16 and 3.14.7 each passed 158 tests
with one existing symbolic-link test skipped because the user lacks OS privileges.
Ruff lint/format checks and strict mypy passed. Both distribution formats built offline;
the installed wheel passed both mapping entry points, source/config hash preservation,
deterministic reapplication, unmatched-rule rejection and output-overwrite protection.
The source archive excludes local environments, tool files and caches. These checks
do not establish plugin availability or FL Studio compatibility.
