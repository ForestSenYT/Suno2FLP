"""Complete tiny lineage; only the existing native inference boundary is simulated."""

import json
import shutil

import pytest
import test_beat_pipeline
from test_beat_native import native as native
from test_stem_transcription import batch as batch
from test_stem_transcription import protocol as protocol
from test_stem_transcription import recipe as recipe

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.pipeline.estimated_arrangement import compose_estimated_arrangement
from suno2flp.pipeline.stem_transcription import transcribe_stems
from suno2flp.validator.estimated_arrangement import verify_estimated_arrangement


@pytest.fixture
def current_batch(batch, tmp_path):
    transcribe_stems(batch.separation, batch.backend, tmp_path / "batch")
    return batch, tmp_path / "batch/stem-transcription.json"


@pytest.fixture
def beat_protocol(native, tmp_path, monkeypatch):
    root = tmp_path / "different-song"
    root.mkdir()
    return test_beat_pipeline.protocol.__wrapped__(native, root, monkeypatch)


def test_complete_current_composition_and_saved_reconstruction_need_no_new_native_run(
    current_batch, tmp_path
):
    source, report = current_batch
    before = capture_stream_input(source.source.source)
    calls = len(source.calls)
    result = compose_estimated_arrangement(report, tmp_path / "arranged")
    assert result.inputs.source_audio == before
    assert len(result.parts) == 4 and len(result.inputs.pitches) == 3
    assert result.inputs.residual.path.name == "unassigned-residual.f64"
    assert result.residual.encoding == "stereo-little-endian-float64-raw"
    assert result.recipe is not None
    assert verify_estimated_arrangement(tmp_path / "arranged/estimated-arrangement.json") == result
    assert len(source.calls) == calls and capture_stream_input(source.source.source) == before
    assert result.execution_allowed is False and result.playback == "unavailable"


@pytest.mark.parametrize("target", ["source", "stem", "bend", "batch"])
def test_current_dependency_tamper_refuses_saved_arrangement(current_batch, tmp_path, target):
    source, report = current_batch
    result = compose_estimated_arrangement(report, tmp_path / "arranged")
    paths = dict(
        source=source.source.source,
        stem=result.inputs.stems[0].file.path,
        bend=result.inputs.pitches[0].bends.path,
        batch=report,
    )
    with paths[target].open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        verify_estimated_arrangement(tmp_path / "arranged/estimated-arrangement.json")


def test_forged_derived_role_and_copied_completion_are_refused(current_batch, tmp_path):
    _, report = current_batch
    compose_estimated_arrangement(report, tmp_path / "arranged")
    completed = tmp_path / "arranged/estimated-arrangement.json"
    other = tmp_path / "copied"
    other.mkdir()
    shutil.copyfile(completed, other / completed.name)
    with pytest.raises(ValueError):
        verify_estimated_arrangement(other / completed.name)
    raw = json.loads(completed.read_bytes())
    raw["parts"][0]["role"] = "bass"
    completed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_estimated_arrangement(completed)


def test_cancel_existing_output_and_partial_batch_cannot_publish(current_batch, tmp_path):
    source, report = current_batch
    with pytest.raises(Suno2FLPError):
        compose_estimated_arrangement(report, tmp_path / "cancelled", should_cancel=lambda: True)
    assert not (tmp_path / "cancelled/estimated-arrangement.json").exists()
    out = tmp_path / "existing"
    out.mkdir()
    with pytest.raises(ValueError):
        compose_estimated_arrangement(report, out)
    assert list(out.iterdir()) == []
    with pytest.raises(ValueError):
        compose_estimated_arrangement(report, report.parent / "overlap")
    assert not (report.parent / "overlap").exists()
    transcribe_stems(source.separation, source.backend, tmp_path / "partial", stems=("vocals",))
    with pytest.raises(ValueError):
        compose_estimated_arrangement(
            tmp_path / "partial/stem-transcription.json", tmp_path / "refused"
        )
    assert not (tmp_path / "refused/estimated-arrangement.json").exists()


def test_late_source_mutation_never_publishes_completion(current_batch, tmp_path, monkeypatch):
    from suno2flp.pipeline import estimated_arrangement as service

    source, report = current_batch
    publish = service.publish_verified_report

    def changed(path, content, protected, verify):
        def guard():
            with source.source.source.open("ab") as stream:
                stream.write(b"late")
            verify()

        publish(path, content, protected, guard)

    monkeypatch.setattr(service, "publish_verified_report", changed)
    with pytest.raises((ValueError, Suno2FLPError)):
        compose_estimated_arrangement(report, tmp_path / "arranged")
    assert not (tmp_path / "arranged/estimated-arrangement.json").exists()


def test_different_fully_validated_beat_source_is_refused(current_batch, beat_protocol, tmp_path):
    from suno2flp.pipeline.beat_analysis import analyze_beats

    _, report = current_batch
    _, decode, backend, _ = beat_protocol
    analyze_beats(decode, backend, tmp_path / "beats")
    with pytest.raises(ValueError, match="same source clock"):
        compose_estimated_arrangement(
            report, tmp_path / "arranged", beats_path=tmp_path / "beats/beats.json"
        )
    assert not (tmp_path / "arranged").exists()


def test_incorrect_producer_snapshot_is_refused_before_completion(
    current_batch, tmp_path, monkeypatch
):
    from suno2flp.pipeline import estimated_arrangement as service

    _, report = current_batch
    build = service.build_estimated_arrangement

    def forged(inputs):
        result = build(inputs)
        result.parts[0].role = "bass"
        return result

    monkeypatch.setattr(service, "build_estimated_arrangement", forged)
    with pytest.raises(ValueError, match="complete current source derivation"):
        compose_estimated_arrangement(report, tmp_path / "arranged")
    assert not (tmp_path / "arranged/estimated-arrangement.json").exists()
