"""Review reproducers: bounded exact costs and complete request/source evidence."""

import json
from pathlib import Path

import pytest
from test_beat_annotations import annotations as annotations
from test_beat_native import native as native
from test_beat_pipeline import protocol as protocol

from suno2flp.core.beat_scoring import ScoredBeat
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.performance import RationalTime
from suno2flp.pipeline.beat_analysis import analyze_beats
from suno2flp.pipeline.beat_scoring import score_beat_files
from suno2flp.validator.beat_analysis import beat_recipe, verify_beat_analysis
from suno2flp.validator.beat_annotations import beat_scoring_recipe
from suno2flp.validator.beat_scoring import score_beats


def test_oversized_nested_coordinates_are_rejected_before_matching() -> None:
    beat = ScoredBeat(id="a", label="beat", microseconds=RationalTime(numerator=1, denominator=1))
    beat.microseconds.numerator = 1 << 512
    beat.microseconds.denominator = 1 << 512
    with pytest.raises(ValueError, match="integer budget"):
        score_beats([beat], [beat])


def test_empty_prediction_has_undefined_precision_and_zero_recall() -> None:
    ref = ScoredBeat(id="r", label="beat", microseconds=RationalTime(numerator=0, denominator=1))
    score = score_beats([], [ref])
    assert score.precision is None
    assert score.recall.numerator == 0


def test_file_annotations_enforce_the_same_integer_budget(annotations, tmp_path: Path) -> None:
    (candidate, reference), _ = annotations
    raw = json.loads(candidate.read_bytes())
    raw["beats"][0]["microseconds"] = {"numerator": 1 << 512, "denominator": 1 << 512}
    candidate.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="integer budget"):
        score_beat_files(candidate, reference, tmp_path / "refused.json")
    assert not (tmp_path / "refused.json").exists()


def test_analysis_and_score_recipes_bind_shared_behavioral_helpers() -> None:
    for recipe in (beat_recipe(), beat_scoring_recipe()):
        names = {
            i.path.relative_to(Path(__file__).resolve().parents[2] / "src/suno2flp").as_posix()
            for i in recipe.files
        }
        assert {
            "core/note_scoring.py",
            "core/offline_models.py",
            "importer/note_annotations.py",
        } <= names


@pytest.mark.parametrize("field", ["packages", "pins", "pcm", "frames", "sample_rate", "channels"])
def test_coherently_rehashed_foreign_request_cannot_pass(
    protocol, tmp_path: Path, field: str
) -> None:
    _, decode, backend, _ = protocol
    report = analyze_beats(decode, backend, tmp_path / "candidate")
    request = dict(
        packages=str(backend / "packages"),
        pins=str(Path(__file__).resolve().parents[2] / "src/suno2flp/integrations/beat_pins.json"),
        pcm=str(report.pcm.path),
        frames=1025,
        sample_rate=22050,
        channels=1,
    )
    request[field] = (
        True if field == "channels" else (999 if isinstance(request[field], int) else "foreign")
    )
    (report.root / "native/request.json").write_text(json.dumps(request), encoding="utf-8")
    report.native_witnesses = capture_file_tree(report.root / "native")
    path = report.root / "beats.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="request"):
        verify_beat_analysis(path, tmp_path / "replay")
    assert not (tmp_path / "replay/replay.json").exists()
