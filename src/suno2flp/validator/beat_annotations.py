"""Conditional declared-label scores with fresh decode and current provenance."""

import platform
import sys
from pathlib import Path

import pydantic

from suno2flp.core.beat_annotations import BeatAnnotation, BeatAnnotationSnapshot, BeatScoreReport
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import capture_stream_input, load_unique_json, verify_inputs
from suno2flp.core.offline_models import FileIdentity
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.beat_backend import Cancel, cancelled
from suno2flp.validator.beat_scoring import score_beats
from suno2flp.validator.note_decode_evidence import verify_decoder_payload
from suno2flp.validator.transcription_source import verified_transcription_source


def beat_scoring_recipe() -> ScoringRecipe:
    root = Path(__file__).parent.parent
    names = (
        "core/beat_annotations.py",
        "core/beat_scoring.py",
        "core/models.py",
        "core/offline_models.py",
        "core/note_scoring.py",
        "importer/note_annotations.py",
        "core/performance.py",
        "core/offline_files.py",
        "core/report_publication.py",
        "validator/beat_annotations.py",
        "validator/beat_scoring.py",
        "validator/transcription_source.py",
        "validator/note_decode_evidence.py",
        "pipeline/beat_scoring.py",
    )
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[capture_stream_input(root / name) for name in names],
    )


def read_beat_annotation(path: Path) -> BeatAnnotationSnapshot:
    identity, raw = bounded_snapshot(path, 16 * 1024**2)
    return BeatAnnotationSnapshot(
        file=identity, annotation=BeatAnnotation.model_validate(load_unique_json(raw))
    )


def score_witnesses(report: BeatScoreReport) -> list[FileIdentity]:
    result = [
        report.source_audio,
        report.pcm,
        *report.decode_dependencies,
        report.recipe.python_executable,
        *report.recipe.files,
    ]
    for snapshot in (report.candidate, report.reference):
        if snapshot is not None:
            result.extend(
                [
                    snapshot.file,
                    snapshot.annotation.decode_report,
                    snapshot.annotation.source_audio,
                    *snapshot.annotation.provenance_files,
                ]
            )
    return result


def verify_score_witnesses(report: BeatScoreReport, *, should_cancel: Cancel = None) -> None:
    cancelled(should_cancel)
    verify_inputs(score_witnesses(report))
    verify_decoder_payload(report.decode_dependencies, report.decoder_payload_root)
    if report.recipe != beat_scoring_recipe():
        raise ValueError("Current beat scoring recipe changed")
    cancelled(should_cancel)


def collect_beat_score(
    candidate_path: Path, reference_path: Path | None, *, should_cancel: Cancel = None
) -> BeatScoreReport:
    cancelled(should_cancel)
    recipe = beat_scoring_recipe()
    candidate = read_beat_annotation(candidate_path)
    reference = read_beat_annotation(reference_path) if reference_path is not None else None
    if candidate.annotation.role != "candidate" or (
        reference is not None and reference.annotation.role != "reference"
    ):
        raise ValueError("Beat score requires explicit candidate/reference roles")
    source = verified_transcription_source(
        candidate.annotation.decode_report.path, should_cancel=should_cancel
    )
    for snapshot in (candidate, reference):
        if snapshot is None:
            continue
        a = snapshot.annotation
        if (a.decode_report, a.source_audio, a.frames, a.sample_rate, a.channels) != (
            source.decode_report,
            source.source,
            source.frames,
            source.sample_rate,
            source.channels,
        ):
            raise ValueError("Beat labels disagree with current original source/decode clock")
        verify_inputs([snapshot.file, *a.provenance_files])
    result = score_beats(
        candidate.annotation.beats,
        reference.annotation.beats if reference is not None else None,
        should_cancel=should_cancel,
    )
    report = BeatScoreReport(
        candidate=candidate,
        reference=reference,
        source_audio=source.source,
        pcm=source.pcm,
        decode_dependencies=source.dependencies,
        decoder_payload_root=source.decoder_payload_root,
        recipe=recipe,
        result=result,
    )
    verify_score_witnesses(report, should_cancel=should_cancel)
    return report


def verify_beat_score(path: Path, *, should_cancel: Cancel = None) -> BeatScoreReport:
    identity, raw = bounded_snapshot(path, 16 * 1024**2)
    saved = BeatScoreReport.model_validate(load_unique_json(raw))
    current = collect_beat_score(
        saved.candidate.file.path,
        saved.reference.file.path if saved.reference else None,
        should_cancel=should_cancel,
    )
    if saved != current:
        raise ValueError("Saved beat score differs from current complete source-bound metrics")
    verify_inputs([identity])
    verify_score_witnesses(current, should_cancel=should_cancel)
    return current
