"""Current decoder/producer evidence and full replay of conditional drum scores."""

import platform
import sys
from collections.abc import Callable
from pathlib import Path

import pydantic

from suno2flp.core.drum_scoring import DrumAnnotation, DrumAnnotationSnapshot, DrumScoreReport
from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import ANNOTATION_BYTES, REPORT_BYTES, ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.validator.drum_matching import score_drums
from suno2flp.validator.note_decode_evidence import verify_decoder_payload
from suno2flp.validator.transcription_source import verified_transcription_source

Cancel = Callable[[], bool] | None


def check_cancel(callback: Cancel) -> None:
    if callback is not None and callback():
        raise OfflineError("drum_score_cancelled", "Drum scoring cancelled")


def drum_scoring_recipe() -> ScoringRecipe:
    root = Path(__file__).resolve().parent.parent
    names = (
        "core/drum_scoring.py",
        "core/note_scoring.py",
        "core/performance.py",
        "core/models.py",
        "core/offline_models.py",
        "core/errors.py",
        "core/offline_files.py",
        "core/report_publication.py",
        "importer/note_annotations.py",
        "validator/transcription_source.py",
        "validator/note_decode_evidence.py",
        "validator/drum_matching.py",
        "validator/drum_scoring.py",
        "pipeline/drum_scoring.py",
    )
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[capture_stream_input(root / name) for name in names],
    )


def read_drum_annotation(path: Path) -> DrumAnnotationSnapshot:
    file, raw = bounded_snapshot(path, ANNOTATION_BYTES)
    return DrumAnnotationSnapshot(
        file=file, annotation=DrumAnnotation.model_validate(load_unique_json(raw))
    )


def verify_drum_witnesses(report: DrumScoreReport) -> None:
    verify_inputs(report.witnesses())
    verify_decoder_payload(report.decode_dependencies, report.decoder_payload_root)
    if report.recipe != drum_scoring_recipe():
        raise ValueError("Drum scoring runtime or recipe changed")


def collect_drum_score(
    candidate_path: Path,
    reference_path: Path | None,
    report_path: Path,
    *,
    should_cancel: Cancel = None,
) -> DrumScoreReport:
    check_cancel(should_cancel)
    recipe = drum_scoring_recipe()
    candidate = read_drum_annotation(candidate_path)
    reference = read_drum_annotation(reference_path) if reference_path is not None else None
    a = candidate.annotation
    if a.role != "candidate" or (reference and reference.annotation.role != "reference"):
        raise ValueError("Use explicit drum candidate/reference roles")
    source = verified_transcription_source(a.decode_report.path, should_cancel=should_cancel)
    for snapshot in (candidate, reference):
        if snapshot is None:
            continue
        check_cancel(should_cancel)
        current = snapshot.annotation
        if (
            current.decode_report != source.decode_report
            or current.source_audio != source.source
            or (current.frames, current.sample_rate, current.channels)
            != (source.frames, source.sample_rate, source.channels)
        ):
            raise ValueError("Drum annotation disagrees with current source/decoder clock")
        for witness in current.provenance_files:
            actual, _ = bounded_snapshot(witness.path, REPORT_BYTES)
            if actual != witness:
                raise ValueError("Drum producer provenance changed")
    result = score_drums(
        a.events, reference.annotation.events if reference else None, should_cancel=should_cancel
    )
    report = DrumScoreReport(
        report_path=guarded_path(report_path),
        candidate=candidate,
        reference=reference,
        pcm=source.pcm,
        decode_dependencies=source.dependencies,
        decoder_payload_root=source.decoder_payload_root,
        recipe=recipe,
        result=result,
    )
    check_cancel(should_cancel)
    verify_drum_witnesses(report)
    return report


def verify_drum_score(report_path: Path, *, should_cancel: Cancel = None) -> DrumScoreReport:
    check_cancel(should_cancel)
    identity, raw = bounded_snapshot(report_path, REPORT_BYTES)
    report = DrumScoreReport.model_validate(load_unique_json(raw))
    if report.report_path != identity.path:
        raise ValueError("Drum score was relocated from its declared completion path")
    current = collect_drum_score(
        report.candidate.file.path,
        report.reference.file.path if report.reference else None,
        identity.path,
        should_cancel=should_cancel,
    )
    if current != report:
        raise ValueError("Complete current drum score disagrees with saved report")
    verify_inputs([identity])
    verify_drum_witnesses(current)
    return report
