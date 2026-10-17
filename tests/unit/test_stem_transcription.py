"""Real source/lineage checks; native boundaries are explicitly synthetic."""

import importlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_separation_pipeline import protocol as protocol
from test_separation_pipeline import recipe as recipe
from typer.testing import CliRunner

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.transcription import BasicPitchBackend
from suno2flp.pipeline.separation import separate_audio


def services():
    return (
        importlib.import_module("suno2flp.pipeline.stem_transcription"),
        importlib.import_module("suno2flp.validator.stem_transcription"),
    )


@pytest.fixture
def batch(protocol, tmp_path, monkeypatch):
    source = protocol
    separate_audio(source.decode, source.backend, tmp_path / "separation")
    backend = tmp_path / "pitch-backend"
    (backend / "packages/pkg").mkdir(parents=True)
    module = backend / "packages/pkg/__init__.py"
    module.write_bytes(b"# synthetic pitch process boundary only")
    module_id = capture_stream_input(module)
    (backend / "backend.json").write_text("{}", encoding="utf-8")
    record = BasicPitchBackend(
        root=backend,
        python=module_id,
        runtime=[],
        artifacts=[],
        adapters=[],
        payload={"pkg/__init__.py": module_id.sha256},
    )
    calls = []

    def read(root):
        if root != backend:
            raise ValueError("Missing synthetic backend")
        return record.model_copy(deep=True)

    def call(record, attempt, request, **kwargs):
        calls.append(attempt)
        assert request["frames"] == 37 and request["sample_rate"] == 44100
        assert request["channels"] == 2
        (attempt / "request.json").write_text(
            json.dumps({**request, "packages": str(backend / "packages")}), encoding="utf-8"
        )
        (attempt / "mono.f32").write_bytes(b"\0" * 19 * 4)
        for name, width in (("note", 88), ("onset", 88), ("contour", 264)):
            (attempt / f"{name}.f32").write_bytes(b"\0" * 172 * width * 4)
        for name in ("bends.i8", "stdout.bin", "stderr.bin"):
            (attempt / name).write_bytes(b"")
        probe = dict(
            profile="basic-pitch-native-probe-v1",
            provider="CPUExecutionProvider",
            intra_op_threads=8,
            inter_op_threads=1,
            sequential=True,
            repeatable=True,
            shapes={"note": [1, 172, 88], "onset": [1, 172, 88], "contour": [1, 172, 264]},
            versions={
                "onnxruntime": "1.23.2",
                "numpy": "2.3.5",
                "scipy": "1.16.3",
                "basic-pitch": "0.4.0",
            },
            modules={
                name: str(module)
                for name in (
                    "numpy",
                    "onnxruntime",
                    "scipy",
                    "basic_pitch",
                    "librosa",
                    "pretty_midi",
                    "mir_eval",
                    "resampy",
                )
            },
        )
        (attempt / "result.json").write_text(
            json.dumps(
                dict(
                    probe=probe,
                    resampled_frames=19,
                    windows=1,
                    owned_rows=1,
                    notes=[],
                    bend_bytes=0,
                )
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr("suno2flp.pipeline.transcription.read_basic_pitch", read)
    monkeypatch.setattr("suno2flp.pipeline.stem_transcription.read_basic_pitch", read)
    monkeypatch.setattr("suno2flp.pipeline.transcription.call_basic_pitch", call)
    monkeypatch.setattr("suno2flp.validator.transcription.read_basic_pitch", read)
    return SimpleNamespace(
        source=source,
        separation=tmp_path / "separation/separation.json",
        backend=backend,
        calls=calls,
    )


def test_batch_uses_one_fresh_separation_and_preserves_explicit_estimated_lineage(batch, tmp_path):
    pipeline, validator = services()
    before = capture_stream_input(batch.source.source)
    original = batch.separation.read_bytes()
    result = pipeline.transcribe_stems(batch.separation, batch.backend, tmp_path / "batch")
    assert [item.stem for item in result.stems] == ["vocals", "bass", "other"]
    assert len(batch.calls) == 3
    assert result.drums == "not_transcribed_by_pitched_model"
    assert not result.execution_allowed and result.writer_eligibility == "blocked"
    for item in result.stems:
        report = json.loads(item.transcription.path.read_bytes())
        assert report["profile"] == "estimated-stem-basic-pitch-candidate-v1"
        assert "decode_report" not in report  # inferred source must never impersonate a decoder
        assert report["source"]["original_audio"] == before.model_dump(mode="json")
        assert report["source"]["stem"] == item.stem
        assert report["frames"] == 37 and report["sample_rate"] == 44100 and report["channels"] == 2
    assert (tmp_path / "batch/separation-replay/replay.json").exists()
    assert (
        validator.verify_stem_batch(tmp_path / "batch/stem-transcription.json", tmp_path / "replay")
        == result
    )
    assert len(batch.calls) == 6
    assert capture_stream_input(batch.source.source) == before
    assert batch.separation.read_bytes() == original


@pytest.mark.parametrize(
    "stems", [("drums",), (), ("bass", "bass"), ("other", "bass"), ("unknown",)]
)
def test_invalid_or_noncanonical_selection_cannot_run_or_create_output(batch, tmp_path, stems):
    pipeline, _ = services()
    with pytest.raises(ValueError):
        pipeline.transcribe_stems(
            batch.separation, batch.backend, tmp_path / "invalid", stems=stems
        )
    assert not (tmp_path / "invalid").exists() and not batch.calls


@pytest.mark.parametrize(
    "changed",
    [
        "original",
        "stem",
        "separation",
        "model",
        "extra",
        "receipt",
        "pending",
        "cancel",
        "metadata",
        "recipe",
    ],
)
def test_late_mutation_does_not_publish_batch(batch, tmp_path, monkeypatch, changed):
    pipeline, validator = services()
    publication = importlib.import_module("suno2flp.core.report_publication")
    original = publication.new_report
    pending = tmp_path / "batch/stem-transcription.pending.json"
    recipe_file = tmp_path / "declared-recipe.py"
    if changed == "recipe":
        recipe_file.write_bytes(b"original declared recipe")
        current_recipe = pipeline.stem_recipe

        def declared_recipe():
            result = current_recipe()
            result.files.append(capture_stream_input(recipe_file))
            return result

        monkeypatch.setattr(pipeline, "stem_recipe", declared_recipe)
        monkeypatch.setattr(validator, "stem_recipe", declared_recipe)

    def mutate(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path == pending and changed != "cancel":
            if changed == "metadata":
                import pydantic

                monkeypatch.setattr(pydantic, "__version__", "changed after serialization")
                return
            targets = dict(
                original=batch.source.source,
                stem=tmp_path / "separation/native/bass.wav",
                separation=batch.separation,
                model=batch.backend / "packages/pkg/__init__.py",
                extra=batch.backend / "packages/extra.pth",
                receipt=tmp_path / "batch/separation-replay/replay.json",
                pending=pending,
                recipe=recipe_file,
            )
            with targets[changed].open("ab") as stream:
                stream.write(b"changed after serialization")

    monkeypatch.setattr(publication, "new_report", mutate)
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        pipeline.transcribe_stems(
            batch.separation,
            batch.backend,
            tmp_path / "batch",
            should_cancel=(pending.exists if changed == "cancel" else None),
        )
    assert pending.exists() and not (tmp_path / "batch/stem-transcription.json").exists()


def test_rehashed_prediction_forgery_still_requires_actual_fresh_inference(batch, tmp_path):
    pipeline, validator = services()
    result = pipeline.transcribe_stems(
        batch.separation, batch.backend, tmp_path / "batch", stems=("bass",)
    )
    manifest = result.stems[0].transcription.path
    candidate = json.loads(manifest.read_bytes())
    prediction = tmp_path / "batch/bass/pitch/native/note.f32"
    raw = prediction.read_bytes()
    prediction.write_bytes(struct.pack("<f", 0.5) + raw[4:])
    candidate["predictions"][0]["file"] = capture_stream_input(prediction).model_dump(mode="json")
    manifest.write_text(json.dumps(candidate), encoding="utf-8")
    result.stems[0].transcription = capture_stream_input(manifest)
    completed = tmp_path / "batch/stem-transcription.json"
    completed.write_text(result.model_dump_json(), encoding="utf-8")
    validator.validate_batch(result, completed.parent)
    with pytest.raises(ValueError, match="prediction replay"):
        validator.verify_stem_batch(completed, tmp_path / "replay")
    assert not (tmp_path / "replay/replay.json").exists()


@pytest.mark.parametrize("kind", ["pending", "foreign", "overlap"])
def test_provisional_foreign_and_overlapping_separation_are_not_consumed(batch, tmp_path, kind):
    pipeline, _ = services()
    source, output = batch.separation, tmp_path / "attempt"
    if kind == "pending":
        source = source.with_name("separation.pending.json")
    elif kind == "foreign":
        copied = tmp_path / "copied"
        copied.mkdir()
        foreign = copied / "separation.json"
        foreign.write_bytes(source.read_bytes())
        source = foreign
    else:
        output = source.parent / "overlapping"
    with pytest.raises((ValueError, Suno2FLPError)):
        pipeline.transcribe_stems(source, batch.backend, output)
    assert not output.exists() and not batch.calls


def test_missing_pitch_prerequisite_fails_before_separation_replay_or_new_outputs(batch, tmp_path):
    pipeline, _ = services()
    with pytest.raises(ValueError, match="backend"):
        pipeline.transcribe_stems(batch.separation, tmp_path / "missing", tmp_path / "attempt")
    assert not (tmp_path / "attempt").exists() and not batch.calls


def test_valid_relative_separation_is_accepted_by_api_and_cli(batch, tmp_path, monkeypatch):
    _, validator = services()
    monkeypatch.chdir(tmp_path)
    relative = Path("separation/separation.json")
    identity, _ = validator.read_separation(relative)
    assert identity == capture_stream_input(batch.separation)
    from suno2flp.cli import app

    completed = CliRunner().invoke(
        app,
        [
            "transcribe-stems",
            str(relative),
            "--backend",
            str(batch.backend),
            "--output",
            str(tmp_path / "relative-batch"),
        ],
    )
    assert completed.exit_code == 0, completed.output
    assert "unqualified_candidate" in completed.output
    assert (tmp_path / "relative-batch/stem-transcription.json").exists()


def test_lineage_replay_report_cannot_change_after_its_numeric_validation(
    batch, tmp_path, monkeypatch
):
    _, validator = services()
    from suno2flp.validator.separation import verify_separation

    verify_separation(batch.separation, tmp_path / "separation-replay")
    replay = tmp_path / "separation-replay/separation.json"
    receipt = capture_stream_input(tmp_path / "separation-replay/replay.json")
    original = validator.validate_separation_artifacts

    def change_after_validation(report, **kwargs):
        original(report, **kwargs)
        if report.native_result.path == replay.parent / "native/result.json":
            replay.write_bytes(replay.read_bytes() + b"\n")

    monkeypatch.setattr(validator, "validate_separation_artifacts", change_after_validation)
    with pytest.raises((ValueError, Suno2FLPError)):
        validator.read_lineage(capture_stream_input(batch.separation), receipt)
