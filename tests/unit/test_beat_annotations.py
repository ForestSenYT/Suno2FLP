"""Source-bound conditional scores use real decoding and original tiny labels."""

from pathlib import Path

import pytest
from test_beat_native import native as native
from test_beat_pipeline import protocol as protocol

from suno2flp.core.beat_annotations import BeatAnnotation
from suno2flp.core.beat_scoring import ScoredBeat
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.performance import RationalTime
from suno2flp.pipeline.beat_scoring import score_beat_files
from suno2flp.validator.beat_annotations import verify_beat_score


@pytest.fixture
def annotations(protocol, tmp_path):
    source, decode, _, _ = protocol
    producer = tmp_path / "original-labels.txt"
    producer.write_bytes(b"tiny synthetic labels, not musical ground truth")
    paths = []
    for role, origin, onset in (
        ("candidate", "synthetic_fixture", 20000),
        ("reference", "synthetic_fixture", 40000),
    ):
        annotation = BeatAnnotation(
            role=role,
            origin=origin,
            method="original synthetic labels",
            provenance_files=[capture_stream_input(producer)],
            decode_report=capture_stream_input(decode),
            source_audio=capture_stream_input(source),
            frames=1025,
            sample_rate=22050,
            channels=1,
            beats=[
                ScoredBeat(
                    id=role, label="beat", microseconds=RationalTime(numerator=onset, denominator=1)
                )
            ],
        )
        path = tmp_path / f"{role}.json"
        path.write_text(annotation.model_dump_json(), encoding="utf-8")
        paths.append(path)
    return paths, producer


def test_score_replays_from_current_original_source(annotations, tmp_path: Path) -> None:
    (candidate, reference), _ = annotations
    path = tmp_path / "score.json"
    report = score_beat_files(candidate, reference, path)
    assert report.result.median_error_microseconds.numerator == 20000
    assert report.annotation_truth_verified is False
    assert verify_beat_score(path) == report


def test_missing_truth_remains_explicitly_unscored(annotations, tmp_path: Path) -> None:
    (candidate, _), _ = annotations
    report = score_beat_files(candidate, None, tmp_path / "no-reference.json")
    assert report.result.status == "reference_unavailable"
    assert report.result.recall is None


def test_changed_producer_and_forged_score_fail(annotations, tmp_path: Path) -> None:
    (candidate, reference), producer = annotations
    path = tmp_path / "score.json"
    report = score_beat_files(candidate, reference, path)
    report.result.median_error_microseconds.numerator = 0
    path.write_text(report.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_beat_score(path)
    producer.write_bytes(b"changed original evidence")
    with pytest.raises((ValueError, Suno2FLPError)):
        score_beat_files(candidate, reference, tmp_path / "refused.json")
    assert not (tmp_path / "refused.json").exists()
