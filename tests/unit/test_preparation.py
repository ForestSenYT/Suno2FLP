import hashlib
import json
import wave

import pytest
import yaml
from offline_fixtures import write_midi
from typer.testing import CliRunner

from suno2flp.cli import app
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.models import ArrangementOptions
from suno2flp.core.workspace import init_project


@pytest.fixture
def project(tmp_path):
    root = init_project(tmp_path, "synthetic")
    write_midi(root / "input/song.mid")
    return root


def prepare(root, destination, **kwargs):
    from suno2flp.pipeline.preparation import prepare_project

    return prepare_project(root, destination, **kwargs)


def verify(path):
    from suno2flp.pipeline.preparation import verify_preparation

    return verify_preparation(path)


def test_end_to_end_preparation_and_current_source_verification(project, monkeypatch):
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in project.rglob("*") if p.is_file()}
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: pytest.fail("external process"))
    output = project / "intermediate/first"
    result = prepare(project, output)
    assert result.status == "offline_ready" and result.writer_eligibility == "blocked"
    assert result.host_compatibility == "unverified" and not result.execution_allowed
    assert {p.name for p in output.iterdir()} == {
        "assets.json",
        "midi-0000.json",
        "arrangement.json",
        "quality.json",
        "run.json",
    }
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == identity for p, identity in before.items())
    saved = verify(output / "run.json")
    assert saved == result
    arrangement = json.loads((output / "arrangement.json").read_text(encoding="utf-8"))
    assert arrangement["tracks"][1]["notes"][0]["start_tick"] == 120
    assert (
        arrangement["sources"][0]["midi"]["source_sha256"]
        == hashlib.sha256((project / "input/song.mid").read_bytes()).hexdigest()
    )
    second = project / "intermediate/second"
    prepare(project, second)
    for name in ("assets.json", "midi-0000.json", "arrangement.json", "quality.json"):
        assert (output / name).read_bytes() == (second / name).read_bytes()


def test_explicit_configured_cleanup_and_ppq_conversion(project):
    config = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8"))
    config["midi"]["min_duration_ticks"] = 300
    (project / "project.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    output = project / "intermediate/cleaned"
    prepare(project, output, options=ArrangementOptions(target_ppq=960, note_view="active"))
    arrangement = json.loads((output / "arrangement.json").read_text(encoding="utf-8"))
    assert arrangement["ticks_per_beat"] == 960 and arrangement["tracks"][1]["notes"] == []
    assert (
        arrangement["sources"][0]["midi"]["cleanup"]["changes"][0]["operation"]
        == "remove_short_note"
    )
    assert verify(output / "run.json").status == "offline_ready"


@pytest.mark.parametrize(
    "kind", ["artifact", "rehashed_artifact", "original", "config", "extra", "missing", "manifest"]
)
def test_saved_preparation_detects_stale_and_forged_inputs_or_outputs(project, kind):
    output = project / "intermediate/first"
    prepare(project, output)
    run = output / "run.json"
    if kind in {"artifact", "rehashed_artifact"}:
        target = output / "arrangement.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        data["tracks"][1]["notes"][0]["pitch"] = 61
        target.write_text(json.dumps(data), encoding="utf-8")
        if kind == "rehashed_artifact":
            recorded = json.loads(run.read_text(encoding="utf-8"))
            ref = recorded["artifacts"]["arrangement.json"]
            ref.update(
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                size_bytes=target.stat().st_size,
                mtime_ns=target.stat().st_mtime_ns,
            )
            run.write_text(json.dumps(recorded), encoding="utf-8")
    elif kind == "original":
        write_midi(project / "input/song.mid", start=121)
    elif kind == "config":
        with (project / "project.yaml").open("a", encoding="utf-8") as stream:
            stream.write("\n# changed\n")
    elif kind == "extra":
        (output / "unknown.json").write_text("{}", encoding="utf-8")
    elif kind == "missing":
        (output / "quality.json").unlink()
    else:
        data = json.loads(run.read_text(encoding="utf-8"))
        data["execution_allowed"] = True
        run.write_text(json.dumps(data), encoding="utf-8")
    before = {p: p.read_bytes() for p in output.iterdir()}
    with pytest.raises((Suno2FLPError, OSError, ValueError)):
        verify(run)
    assert before == {p: p.read_bytes() for p in output.iterdir()}


@pytest.mark.parametrize("destination", ["input/new", "output/new", "intermediate", "../outside"])
def test_destination_cannot_overlap_inputs_or_escape_intermediate(project, destination):
    target = project / destination
    with pytest.raises((Suno2FLPError, OSError, ValueError)):
        prepare(project, target)
    assert not (project / "input/new").exists()


def test_existing_output_is_never_reused(project):
    target = project / "intermediate/new"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises((Suno2FLPError, OSError, ValueError)):
        prepare(project, target)
    assert marker.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize(
    "setting,value",
    [("integrations", {"daw_backend": "rosasynthesiz"}), ("arrangement_mode", "reinterpretation")],
)
def test_unsupported_configuration_does_not_silently_fall_back(project, setting, value):
    config = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8"))
    config[setting] = value
    (project / "project.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    target = project / "intermediate/blocked"
    with pytest.raises((Suno2FLPError, OSError, ValueError)):
        prepare(project, target)
    assert not target.exists()


def test_conflicting_midi_maps_fail_before_output_creation(project):
    write_midi(project / "input/other.mid", tempo=600000)
    target = project / "intermediate/conflict"
    with pytest.raises((Suno2FLPError, OSError, ValueError)):
        prepare(project, target)
    assert not target.exists()


def test_preparation_cli_is_a_real_saved_workflow(project):
    runner = CliRunner()
    target = project / "intermediate/cli"
    result = runner.invoke(app, ["prepare-project", str(project), "--output-dir", str(target)])
    assert result.exit_code == 0, result.output
    checked = runner.invoke(app, ["verify-preparation", str(target / "run.json")])
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["status"] == "offline_ready"
    again = runner.invoke(app, ["prepare-project", str(project), "--output-dir", str(target)])
    assert again.exit_code == 1


def test_mixed_ppq_wav_reference_and_explicit_role_mapping(project):
    write_midi(project / "input/other.mid", ppq=720, start=180, duration=360)
    with wave.open(str(project / "input/song.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\x00\x00" * 8)
    mapping = project / "roles.yaml"
    mapping.write_text(
        yaml.safe_dump(
            {
                "roles": {"lead": {"general_midi_program": 81}},
                "mappings": [
                    {
                        "source_input": 0,
                        "source_track_position": 1,
                        "source_channel": 2,
                        "role": "lead",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output = project / "intermediate/mixed"
    run = prepare(project, output, mapping_file=mapping)
    data = json.loads((output / "arrangement.json").read_text(encoding="utf-8"))
    assert data["ticks_per_beat"] == 1440
    assert data["tracks"][1]["notes"][0]["start_tick"] == 360
    assert data["tracks"][3]["notes"][0]["start_tick"] == 360
    assert data["tracks"][1]["instrument_roles"][0]["role"] == "lead"
    assert any(item.path.suffix == ".wav" for item in run.input_files)
    assert verify(output / "run.json") == run


def test_failed_write_has_no_completion_marker_and_preserves_inputs(project, monkeypatch):
    from suno2flp.pipeline import preparation

    original_write = preparation._write_file
    before = (project / "input/song.mid").read_bytes()

    def fail_arrangement(path, raw):
        if path.name == "arrangement.json":
            raise OSError("Synthetic disk failure")
        return original_write(path, raw)

    monkeypatch.setattr(preparation, "_write_file", fail_arrangement)
    output = project / "intermediate/partial"
    with pytest.raises(OSError):
        prepare(project, output)
    assert output.is_dir() and not (output / "run.json").exists()
    assert (project / "input/song.mid").read_bytes() == before


@pytest.mark.parametrize("kind", ["empty", "bad_midi", "missing_mapping", "rounding"])
def test_no_successful_bundle_for_incomplete_inputs(project, kind):
    options = {}
    if kind == "empty":
        (project / "input/song.mid").unlink()
    elif kind == "bad_midi":
        (project / "input/song.mid").write_bytes(b"invalid MIDI")
    elif kind == "missing_mapping":
        options["mapping_file"] = project / "missing.yaml"
    else:
        options["options"] = ArrangementOptions(ppq_rounding="nearest")
    output = project / "intermediate/invalid"
    with pytest.raises((Suno2FLPError, OSError, ValueError)):
        prepare(project, output, **options)
    assert not output.exists()
