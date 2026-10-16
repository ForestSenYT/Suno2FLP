from pathlib import Path

import pytest
from pydantic import ValidationError

from suno2flp.core.config import ProjectConfig, load_config
from suno2flp.core.errors import ConfigurationError, UnsafePathError
from suno2flp.core.models import AssetManifest, MidiNote
from suno2flp.core.workspace import init_project
from suno2flp.importer import LocalAssetImporter
from suno2flp.validator import LocalQualityValidator


def test_discovery_metadata_matching_and_roundtrip(media: Path):
    manifest = LocalAssetImporter().discover(media)
    assert [a.kind for a in manifest.assets] == ["midi", "wav"]
    midi, wav = manifest.assets
    assert midi.midi.tracks == 1
    assert midi.midi.note_events == 2
    assert midi.midi.ticks_per_beat == 480
    assert wav.audio.duration_seconds == pytest.approx(0.1)
    assert len(manifest.matches) == 1
    assert manifest.matches[0].midi_path == midi.path
    assert AssetManifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_malformed_and_unsupported_files_are_diagnostic(media: Path):
    (media / "broken.mid").write_bytes(b"not midi")
    (media / "broken.wav").write_bytes(b"not wave")
    (media / "song.mp3").write_bytes(b"not supported")
    report = LocalQualityValidator().validate_assets(LocalAssetImporter().discover(media))
    assert not report.valid
    assert sum(d.severity == "error" for d in report.diagnostics) == 2
    assert any(d.code == "unsupported_file" for d in report.diagnostics)


def test_ambiguous_stem_names_are_not_guessed(media: Path):
    (media / "nested").mkdir()
    (media / "nested" / "piano.wav").write_bytes((media / "piano.wav").read_bytes())
    manifest = LocalAssetImporter().discover(media)
    assert not manifest.matches
    assert any(d.code == "ambiguous_match" for d in manifest.diagnostics)


def test_initialization_and_config_paths(tmp_path: Path):
    project = init_project(tmp_path, "my-song")
    config = load_config(project / "project.yaml")
    assert config.name == "my-song"
    assert config.input_directories == [Path("input")]
    assert all((project / name).is_dir() for name in ("input", "intermediate", "output"))
    before = (project / "project.yaml").read_bytes()
    with pytest.raises(UnsafePathError):
        init_project(tmp_path, "my-song")
    assert (project / "project.yaml").read_bytes() == before


@pytest.mark.parametrize("name", ["../escape", "a/b", "a\\b", ".", "CON", "bad.", "bad "])
def test_reject_unsafe_workspace_names(tmp_path: Path, name: str):
    with pytest.raises(UnsafePathError):
        init_project(tmp_path, name)


@pytest.mark.parametrize(
    "settings",
    [
        {"non_destructive": False},
        {"input_directories": ["../outside"]},
        {"output_directory": "input"},
        {"output_directory": "input/out"},
        {"output_directory": "output", "intermediate_directory": "output/tmp"},
        {"input_directories": []},
        {"unknown": True},
        {"arrangement_mode": "magic"},
    ],
)
def test_config_rejects_unsafe_or_unknown_settings(settings):
    with pytest.raises(ValidationError):
        ProjectConfig(name="test", **settings)


@pytest.mark.parametrize(
    "text",
    ["[invalid", "null", "[]", "name: test\nname: other", "name: test\nnon_destructive: false"],
)
def test_config_loading_predictable_errors(tmp_path: Path, text: str):
    config = tmp_path / "project.yaml"
    config.write_text(text)
    with pytest.raises(ConfigurationError):
        load_config(config)


def test_invalid_note_ranges():
    with pytest.raises(ValidationError):
        MidiNote(pitch=128, velocity=64, start_tick=0, duration_ticks=480)


def test_discovery_does_not_change_inputs(media: Path):
    before = {p: p.read_bytes() for p in media.iterdir()}
    LocalAssetImporter().discover(media)
    assert before == {p: p.read_bytes() for p in media.iterdir()}
