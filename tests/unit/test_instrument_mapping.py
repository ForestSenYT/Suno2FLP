import hashlib
from pathlib import Path

import mido
import pytest
from pydantic import ValidationError

from suno2flp.arrangement import ExplicitInstrumentMapper, FaithfulArrangementEngine
from suno2flp.core.config import MidiPreferences
from suno2flp.core.errors import ConfigurationError, InstrumentMappingError
from suno2flp.core.instrument_config import load_instrument_mapping
from suno2flp.core.models import (
    Arrangement,
    ArrangementOptions,
    InstrumentMappingConfig,
    InstrumentMappingDocument,
    MusicalMetadata,
)
from suno2flp.importer import MidiFileImporter
from suno2flp.midi_processor import DeterministicMidiProcessor


@pytest.fixture
def arrangement(tmp_path: Path):
    source = tmp_path / "source.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks.extend(
        [
            mido.MidiTrack([mido.MetaMessage("track_name", name="Conductor")]),
            mido.MidiTrack(
                [
                    mido.MetaMessage("track_name", name="Same name"),
                    mido.Message("program_change", channel=0, program=5),
                    mido.Message("note_on", channel=0, note=60, time=120),
                    mido.Message("note_on", channel=9, note=36),
                    mido.Message("note_off", channel=0, note=60, time=240),
                    mido.Message("note_off", channel=9, note=36),
                ]
            ),
            mido.MidiTrack(
                [
                    mido.MetaMessage("track_name", name="Same name"),
                    mido.Message("note_on", channel=2, note=48),
                    mido.Message("note_off", channel=2, note=48, time=480),
                ]
            ),
        ]
    )
    midi.save(source)
    imported = MidiFileImporter().import_file(source)
    return FaithfulArrangementEngine().arrange([imported], MusicalMetadata(), "faithful")


def document(mappings=None):
    return InstrumentMappingDocument(
        config=InstrumentMappingConfig.model_validate(
            {
                "roles": {
                    "piano": {"general_midi_program": 1, "plugin_hint": "user piano label"},
                    "drums": {"percussion": True},
                    "bass": {"general_midi_program": 33},
                },
                "mappings": mappings
                if mappings is not None
                else [
                    {
                        "source_input": 0,
                        "source_track_position": 1,
                        "source_channel": 0,
                        "role": "piano",
                    },
                    {
                        "source_input": 0,
                        "source_track_position": 1,
                        "source_channel": 9,
                        "role": "drums",
                    },
                ],
            }
        )
    )


def test_explicit_channel_mapping_preserves_entire_musical_content_and_provenance(arrangement):
    before = arrangement.model_dump_json()
    mapping = document()
    result = ExplicitInstrumentMapper().apply(arrangement, mapping)
    assert arrangement.model_dump_json() == before and arrangement.instrument_mapping is None
    assert [(a.source_channel, a.role) for a in result.tracks[1].instrument_roles] == [
        (0, "piano"),
        (9, "drums"),
    ]
    assignment = result.tracks[1].instrument_roles[0]
    assert assignment.general_midi_program == 1
    assert assignment.plugin_hint == "user piano label" and assignment.plugin_status == "unverified"
    assert result.tracks[1].instrument_roles[1].percussion
    assert result.tracks[2].instrument_roles == []
    assert any(
        d.code == "instrument_role_unmapped" and d.track_index == 2 for d in result.diagnostics
    )
    assert result.sources == arrangement.sources
    assert result.tempo_map == arrangement.tempo_map and result.meter_map == arrangement.meter_map
    assert result.build_options == arrangement.build_options and result.ticks_per_beat == 480
    for original, mapped in zip(arrangement.tracks, result.tracks, strict=True):
        assert mapped.notes == original.notes and mapped.note_origins == original.note_origins
        assert (
            mapped.end_tick == original.end_tick
            and mapped.instrument_hint == original.instrument_hint
        )
    assert [
        (m.rule_index, m.arrangement_track_index, m.source_channel)
        for m in result.instrument_mapping.matches
    ] == [(0, 1, 0), (1, 1, 9)]
    assert result.instrument_mapping.document == mapping
    assert ExplicitInstrumentMapper().apply(arrangement, mapping) == result
    assert ExplicitInstrumentMapper().apply(result, mapping) == result
    assert Arrangement.model_validate_json(result.model_dump_json()) == result
    result.sources[0].midi.tracks[1].events[0].message["name"] = "changed"
    result.instrument_mapping.document.config.roles["piano"].plugin_hint = "changed"
    assert arrangement.model_dump_json() == before
    assert mapping.config.roles["piano"].plugin_hint == "user piano label"
    assert assignment.plugin_hint == "user piano label"


def test_track_wide_mapping_expands_channels_without_remapping_them(arrangement):
    result = ExplicitInstrumentMapper().apply(
        arrangement, document([{"source_input": 0, "source_track_position": 1, "role": "bass"}])
    )
    assert [(a.source_channel, a.role) for a in result.tracks[1].instrument_roles] == [
        (0, "bass"),
        (9, "bass"),
    ]
    assert [n.channel for n in result.tracks[1].notes] == [0, 9]
    assert len(result.instrument_mapping.unmapped) == 1


@pytest.mark.parametrize(
    "rules",
    [
        [{"source_input": 1, "source_track_position": 1, "role": "piano"}],
        [{"source_input": 0, "source_track_position": 99, "role": "piano"}],
        [{"source_input": 0, "source_track_position": 0, "role": "piano"}],
        [{"source_input": 0, "source_track_position": 1, "source_channel": 15, "role": "piano"}],
        [
            {"source_input": 0, "source_track_position": 1, "role": "piano"},
            {"source_input": 0, "source_track_position": 1, "source_channel": 0, "role": "drums"},
        ],
    ],
)
def test_unmatched_or_overlapping_rules_fail_without_mutating_input(arrangement, rules):
    before = arrangement.model_dump_json()
    with pytest.raises(InstrumentMappingError):
        ExplicitInstrumentMapper().apply(arrangement, document(rules))
    assert arrangement.model_dump_json() == before


def test_empty_rules_do_not_infer_roles(arrangement):
    result = ExplicitInstrumentMapper().apply(arrangement, document([]))
    assert all(not track.instrument_roles for track in result.tracks)
    assert result.instrument_mapping.matches == []
    assert len(result.instrument_mapping.unmapped) == 3
    assert not any(d.code == "instrument_role_unmapped" for d in result.diagnostics)


def test_recorded_mapping_requires_same_document_or_original_arrangement(arrangement):
    result = ExplicitInstrumentMapper().apply(arrangement, document())
    with pytest.raises(InstrumentMappingError):
        ExplicitInstrumentMapper().apply(result, document([]))
    arrangement.mode = "reinterpretation"
    with pytest.raises(InstrumentMappingError):
        ExplicitInstrumentMapper().apply(arrangement, document())


@pytest.mark.parametrize("broken_provenance", ["missing_sources", "changed_channel"])
def test_identical_mapping_reapplication_still_validates_source_provenance(
    arrangement, broken_provenance
):
    mapping = document()
    mapped = ExplicitInstrumentMapper().apply(arrangement, mapping)
    if broken_provenance == "missing_sources":
        mapped.sources = []
    else:
        mapped.tracks[1].notes[0].channel = 4
    before = mapped.model_dump_json()
    with pytest.raises(InstrumentMappingError):
        ExplicitInstrumentMapper().apply(mapped, mapping)
    assert mapped.model_dump_json() == before


def test_source_channels_of_empty_cleaned_tracks_remain_available(arrangement):
    cleaned = DeterministicMidiProcessor().clean(
        arrangement.sources[0].midi, MidiPreferences(min_duration_ticks=241)
    )
    derived = FaithfulArrangementEngine().arrange(
        [cleaned],
        MusicalMetadata(),
        "faithful",
        options=ArrangementOptions(note_view="active", target_ppq=960),
    )
    before = derived.model_dump_json()
    result = ExplicitInstrumentMapper().apply(derived, document())
    assert [a.source_channel for a in result.tracks[1].instrument_roles] == [0, 9]
    assert result.tracks[1].notes == []
    assert result.sources == derived.sources
    assert result.ticks_per_beat == 960
    assert result.tracks[2].notes == derived.tracks[2].notes
    assert result.tracks[2].note_origins == derived.tracks[2].note_origins
    assert result.tempo_map == derived.tempo_map and result.meter_map == derived.meter_map
    assert len(result.sources[0].midi.cleanup.changes) == 2
    result.sources[0].midi.cleanup.changes.clear()
    assert derived.model_dump_json() == before


def test_missing_ambiguous_or_changed_channel_provenance_is_rejected(arrangement):
    mapper = ExplicitInstrumentMapper()
    bad = arrangement.model_copy(deep=True)
    bad.tracks[1].source_input = None
    with pytest.raises(InstrumentMappingError):
        mapper.apply(bad, document())
    bad = arrangement.model_copy(deep=True)
    bad.tracks[1].notes[0].channel = 4
    with pytest.raises(InstrumentMappingError):
        mapper.apply(bad, document())
    bad = arrangement.model_copy(deep=True)
    bad.tracks.append(bad.tracks[1].model_copy(deep=True))
    with pytest.raises(InstrumentMappingError):
        mapper.apply(bad, document())


def test_mapping_loader_records_exact_yaml_snapshot_and_hash(tmp_path):
    path = tmp_path / "mapping.yaml"
    raw = (
        b"schema_version: 1\nroles:\n  piano:\n    general_midi_program: 1\n"
        b"mappings:\n  - source_input: 0\n    source_track_position: 1\n    role: piano\n"
    )
    path.write_bytes(raw)
    loaded = load_instrument_mapping(path)
    assert loaded.source_path == path.resolve()
    assert loaded.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert loaded.config.roles["piano"].general_midi_program == 1
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "text",
    [
        "null",
        "[invalid",
        "roles: {}\nroles: {}",
        "roles: {}\nmappings: []\nunknown: true",
        "roles:\n  piano:\n    general_midi_program: 0\nmappings: []",
        "roles:\n  piano: {}\nmappings:\n  - source_input: 0\n"
        "    source_track_position: 1\n    role: typo",
    ],
)
def test_bad_mapping_yaml_has_predictable_error(tmp_path, text):
    path = tmp_path / "bad.yaml"
    path.write_text(text)
    with pytest.raises(ConfigurationError):
        load_instrument_mapping(path)


@pytest.mark.parametrize(
    "role",
    [
        {"general_midi_program": 0},
        {"general_midi_program": 129},
        {"general_midi_program": True},
        {"general_midi_program": 1.5},
        {"plugin_hint": "  "},
        {"plugin_status": "available"},
        {"percussion": True, "general_midi_program": 1},
        {"midi_channel": 10},
    ],
)
def test_invalid_role_hints_or_channel_rewrite_fields_are_rejected(role):
    with pytest.raises(ValidationError):
        InstrumentMappingConfig(roles={"piano": role})


@pytest.mark.parametrize(
    "selector",
    [
        {"source_input": -1},
        {"source_input": True},
        {"source_track_position": 1.5},
        {"source_channel": 16},
        {"source_channel": True},
        {"track_name": "Piano"},
    ],
)
def test_invalid_or_ambiguous_selectors_are_rejected(selector):
    rule = {"source_input": 0, "source_track_position": 1, "role": "piano", **selector}
    with pytest.raises(ValidationError):
        InstrumentMappingConfig(roles={"piano": {}}, mappings=[rule])


def test_multiple_inputs_use_source_identity_not_names_or_arrangement_positions(arrangement):
    source = arrangement.sources[0].midi
    combined = FaithfulArrangementEngine().arrange([source, source], MusicalMetadata(), "faithful")
    result = ExplicitInstrumentMapper().apply(
        combined,
        document(
            [{"source_input": 1, "source_track_position": 1, "source_channel": 9, "role": "drums"}]
        ),
    )
    assert result.tracks[1].instrument_roles == []
    assert result.tracks[4].instrument_roles[0].role == "drums"
    assert result.instrument_mapping.matches[0].arrangement_track_index == 4
    assert result.sources == combined.sources


def test_repo_catalog_example_and_gm_boundaries_are_valid(arrangement):
    catalog = load_instrument_mapping(Path("config/instruments.yaml"))
    assert catalog.config.mappings == []
    assert catalog.config.roles["drums"].percussion
    example = load_instrument_mapping(Path("examples/instrument_mapping.yaml"))
    result = ExplicitInstrumentMapper().apply(arrangement, example)
    assert len(result.instrument_mapping.matches) == 3
    assert result.instrument_mapping.unmapped == []
    assert not any(d.code == "instrument_role_unmapped" for d in result.diagnostics)
    config = InstrumentMappingConfig(
        roles={"first": {"general_midi_program": 1}, "last": {"general_midi_program": 128}}
    )
    assert config.roles["first"].general_midi_program == 1
    assert config.roles["last"].general_midi_program == 128


def test_duplicate_selector_and_blank_role_ids_are_rejected():
    rule = {"source_input": 0, "source_track_position": 1, "role": "piano"}
    with pytest.raises(ValidationError):
        InstrumentMappingConfig(roles={"piano": {}}, mappings=[rule, rule])
    with pytest.raises(ValidationError):
        InstrumentMappingConfig(roles={" ": {}})


def test_plugin_hint_is_opaque_unverified_text_and_does_not_run_programs(arrangement, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Role mapping attempted to run an external process")

    monkeypatch.setattr("subprocess.run", unexpected)
    mapping = document()
    mapping.config.roles["piano"].plugin_hint = "$(not-a-command); opaque preset label"
    result = ExplicitInstrumentMapper().apply(arrangement, mapping)
    assignment = result.tracks[1].instrument_roles[0]
    assert assignment.plugin_hint == "$(not-a-command); opaque preset label"
    assert assignment.plugin_status == "unverified"


def test_percussion_role_does_not_force_a_standard_drum_channel(arrangement):
    result = ExplicitInstrumentMapper().apply(
        arrangement,
        document(
            [{"source_input": 0, "source_track_position": 2, "source_channel": 2, "role": "drums"}]
        ),
    )
    assert result.tracks[2].instrument_roles[0].percussion
    assert result.tracks[2].instrument_roles[0].source_channel == 2
    assert result.tracks[2].notes[0].channel == 2
    assert result.sources == arrangement.sources
