"""Current numeric producers with synthetic native boundaries; no model/DAW calls."""

import json
import shutil
from types import SimpleNamespace

import pytest
from test_drum_transcription import drum_boundary
from test_stem_transcription import batch as batch
from test_stem_transcription import protocol as protocol
from test_stem_transcription import recipe as recipe

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.pipeline.drum_transcription import transcribe_drums
from suno2flp.pipeline.percussion_arrangement import compose_percussion_arrangement
from suno2flp.pipeline.stem_transcription import transcribe_stems
from suno2flp.validator.percussion_arrangement import verify_percussion_arrangement

pytestmark = pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)


@pytest.fixture
def current_inputs(batch, tmp_path, monkeypatch):
    pitch = transcribe_stems(batch.separation, batch.backend, tmp_path / "batch")
    native = drum_boundary(tmp_path, monkeypatch)
    drum = transcribe_drums(
        batch.separation, pitch.separation_replay.path, native.backend, tmp_path / "drums"
    )
    return SimpleNamespace(
        batch=tmp_path / "batch/stem-transcription.json",
        drums=drum.root / "drum-transcription.json",
        source=batch.source.source,
        pitch_calls=batch.calls,
        drum_calls=native.calls,
    )


def test_complete_source_fusion_reconstruction_and_overlap_guards(current_inputs, tmp_path):
    source = current_inputs
    protected = [capture_stream_input(p) for p in (source.source, source.batch, source.drums)]
    calls = len(source.pitch_calls), len(source.drum_calls)
    output = tmp_path / "arranged"
    result = compose_percussion_arrangement(source.batch, source.drums, output)
    assert result.inputs.pitched_separation_replay == result.inputs.drums.separation_replay
    assert result.inputs.drums.transcription == protected[2]
    assert len(result.parts[1].onsets) == 1 and result.profile.endswith("-v2")
    assert not result.execution_allowed and result.playback == "unavailable"
    report = output / "percussion-arrangement.json"
    assert verify_percussion_arrangement(report) == result
    assert (len(source.pitch_calls), len(source.drum_calls)) == calls == (3, 1)
    assert [capture_stream_input(i.path) for i in protected] == protected
    before = capture_file_tree(source.drums.parent)
    with pytest.raises(ValueError):
        compose_percussion_arrangement(source.batch, source.drums, source.drums.parent / "nested")
    assert capture_file_tree(source.drums.parent) == before
    with pytest.raises(ValueError):
        compose_percussion_arrangement(source.batch, source.drums, output)
    moved = tmp_path / "moved"
    moved.mkdir()
    shutil.copyfile(report, moved / report.name)
    with pytest.raises(ValueError):
        verify_percussion_arrangement(moved / report.name)


@pytest.mark.parametrize("target", ["source-report", "native-member", "recipe", "cancel"])
def test_late_changes_or_cancel_never_publish(current_inputs, tmp_path, monkeypatch, target):
    import suno2flp.pipeline.percussion_arrangement as service
    import suno2flp.validator.percussion_arrangement as validator

    source = current_inputs
    output = tmp_path / "arranged"
    pending = output / "percussion-arrangement.pending.json"
    publish = service.publish_verified_report
    declared_recipe = tmp_path / "declared-recipe.txt"
    if target == "recipe":
        declared_recipe.write_bytes(b"initial declared recipe")
        original_recipe = service.percussion_recipe

        def recipe_with_declared_input():
            result = original_recipe()
            result.files.append(capture_stream_input(declared_recipe))
            return result

        monkeypatch.setattr(service, "percussion_recipe", recipe_with_declared_input)
        monkeypatch.setattr(validator, "percussion_recipe", recipe_with_declared_input)

    def late(path, content, protected, verify):
        def check():
            assert pending.exists()
            if target == "source-report":
                with source.drums.open("ab") as stream:
                    stream.write(b" ")
            elif target == "native-member":
                (source.drums.parent / "native/extra.json").write_text("{}", encoding="utf-8")
            elif target == "recipe":
                declared_recipe.write_bytes(b"changed declared recipe")
            verify()

        return publish(path, content, protected, check)

    monkeypatch.setattr(service, "publish_verified_report", late)
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        compose_percussion_arrangement(
            source.batch,
            source.drums,
            output,
            should_cancel=(pending.exists if target == "cancel" else None),
        )
    assert pending.exists() and not (output / "percussion-arrangement.json").exists()


def test_saved_forged_position_is_refused(current_inputs, tmp_path):
    source = current_inputs
    output = tmp_path / "arranged"
    compose_percussion_arrangement(source.batch, source.drums, output)
    report = output / "percussion-arrangement.json"
    data = json.loads(report.read_bytes())
    data["parts"][1]["onsets"][0]["source_sample"]["numerator"] += 1
    report.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="complete current source derivation"):
        verify_percussion_arrangement(report)
