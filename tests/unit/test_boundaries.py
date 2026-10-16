import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from suno2flp.core.doctor import _probe
from suno2flp.core.models import (
    Arrangement,
    ArrangementTrack,
    MidiNote,
    ProcessedMidi,
    TempoEvent,
)
from suno2flp.core.workspace import init_project
from suno2flp.importer import LocalAssetImporter
from suno2flp.validator import LocalQualityValidator, validate_project


def test_preserve_timing_roundtrip_and_expected_counts():
    note = MidiNote(
        pitch=60,
        velocity=80,
        start_tick=120,
        duration_ticks=480,
        original_start_tick=119,
        original_duration_ticks=481,
    )
    midi = ProcessedMidi(
        source=Path("original.mid"),
        ticks_per_beat=480,
        tempo_map=[TempoEvent(tick=0, microseconds_per_beat=500000)],
    )
    assert ProcessedMidi.model_validate_json(midi.model_dump_json()) == midi
    arrangement = Arrangement(
        ticks_per_beat=480,
        tracks=[ArrangementTrack(name="Piano", source=midi.source, notes=[note])],
    )
    validator = LocalQualityValidator()
    assert validator.validate_arrangement(arrangement, 1, 2).valid
    report = validator.validate_arrangement(arrangement, 2, 4)
    assert {d.code for d in report.diagnostics} == {"track_count", "note_event_count"}
    assert not report.valid
    assert note.original_start_tick == 119


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"MThd",
        b"MThd" + struct.pack(">IHHH", 6, 1, 1, 480),
        b"MThd" + struct.pack(">IHHH", 6, 1, 0, 0xE728),
    ],
)
def test_malformed_and_smpte_midi_report_errors(tmp_path: Path, data: bytes):
    (tmp_path / "bad.mid").write_bytes(data)
    manifest = LocalAssetImporter().discover(tmp_path)
    assert not manifest.assets
    assert any(d.code == "invalid_asset" for d in manifest.diagnostics)


def test_missing_template_and_folder_are_errors(tmp_path: Path):
    project = init_project(tmp_path, "song")
    config = project / "project.yaml"
    config.write_text(
        config.read_text().replace("template_path: null", "template_path: missing.flp")
    )
    (project / "output").rmdir()
    report = validate_project(project)
    assert not report.valid
    assert {"missing_template", "missing_directory"} <= {d.code for d in report.diagnostics}


def test_links_are_skipped_and_workspace_escape_rejected(tmp_path: Path, media: Path):
    linked = media / "linked"
    try:
        linked.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not permit symbolic-link creation for this user")
    manifest = LocalAssetImporter().discover(media)
    assert len(manifest.assets) == 2
    assert any(d.code == "linked_path" for d in manifest.diagnostics)
    project = init_project(tmp_path, "song")
    (project / "output").rmdir()
    (project / "output").symlink_to(media, target_is_directory=True)
    assert not validate_project(project).valid


def test_doctor_missing_and_timeout_are_not_success(monkeypatch):
    monkeypatch.setattr("suno2flp.core.doctor.shutil.which", lambda _: None)
    assert _probe("Git", "git").status == "unavailable"
    monkeypatch.setattr("suno2flp.core.doctor.shutil.which", lambda _: "fake")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("fake", 5)

    monkeypatch.setattr("suno2flp.core.doctor.subprocess.run", timeout)
    assert _probe("Git", "git").status == "unverified"


def test_doctor_dotnet_without_sdk_is_unavailable(monkeypatch):
    monkeypatch.setattr("suno2flp.core.doctor.shutil.which", lambda _: "dotnet")
    monkeypatch.setattr(
        "suno2flp.core.doctor.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    assert _probe(".NET SDK", "dotnet", "--list-sdks").status == "unavailable"
