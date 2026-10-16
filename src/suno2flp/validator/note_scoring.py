"""Fresh source/decode verification and complete conditional metric replay."""

import platform
import sys
from collections.abc import Callable
from pathlib import Path

import pydantic

from suno2flp.core.audio_input import AudioPreflightReport
from suno2flp.core.encoded_audio import EncodedAudioInventory
from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import REPORT_BYTES, NoteScoreReport, ScoringRecipe
from suno2flp.core.offline_files import capture_stream_input, load_unique_json, verify_inputs
from suno2flp.importer.note_annotations import bounded_snapshot, read_note_annotation
from suno2flp.validator.encoded_decode import verify_encoded_decode
from suno2flp.validator.note_decode_evidence import decode_dependencies, verify_note_witnesses
from suno2flp.validator.note_matching import score_notes
from suno2flp.validator.pcm_decode import verify_pcm_decode


def scoring_recipe() -> ScoringRecipe:
    root = Path(__file__).resolve().parent.parent
    names = (
        "core/note_scoring.py",
        "core/models.py",
        "core/offline_models.py",
        "core/performance.py",
        "core/offline_files.py",
        "core/errors.py",
        "importer/note_annotations.py",
        "validator/note_matching.py",
        "validator/note_decode_evidence.py",
        "validator/note_scoring.py",
        "pipeline/note_scoring.py",
    )
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[capture_stream_input(root / name) for name in names],
    )


def collect_note_score(
    candidate_path: Path,
    reference_path: Path | None,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> NoteScoreReport:
    def check() -> None:
        if should_cancel and should_cancel():
            raise OfflineError("note_score_cancelled", "Note scoring cancelled")

    check()
    recipe = scoring_recipe()
    candidate = read_note_annotation(candidate_path)
    reference = read_note_annotation(reference_path) if reference_path is not None else None
    annotation = candidate.annotation
    if annotation.role != "candidate" or (reference and reference.annotation.role != "reference"):
        raise OfflineError("note_score_role_invalid", "Use explicit candidate/reference roles")
    decode_identity, raw = bounded_snapshot(annotation.decode_report.path, 1024**2)
    if decode_identity != annotation.decode_report:
        raise OfflineError("note_score_decode_changed", "Decode report identity changed")
    declared = load_unique_json(raw)
    profile = declared.get("profile") if isinstance(declared, dict) else None
    source: AudioPreflightReport | EncodedAudioInventory
    if profile == "integer-pcm-to-float64-wave-v1":
        pcm_report = verify_pcm_decode(annotation.decode_report.path, should_cancel=should_cancel)
        source = pcm_report.preflight
        pcm = pcm_report.pcm
        dependencies, payload_root = decode_dependencies(pcm_report)
    elif profile == "qualified-compressed-to-float64-v1":
        compressed = verify_encoded_decode(
            annotation.decode_report.path, should_cancel=should_cancel
        )
        source = compressed.inventory
        pcm = compressed.pcm
        dependencies, payload_root = decode_dependencies(compressed)
    else:
        raise OfflineError("note_score_decode_invalid", "Unsupported independent decode evidence")
    for snapshot in (candidate, reference):
        if snapshot is None:
            continue
        current = snapshot.annotation
        if (
            current.decode_report != decode_identity
            or current.source_audio != source.source
            or (current.frames, current.channels, current.sample_rate)
            != (source.frames, source.channels, source.sample_rate)
        ):
            raise OfflineError(
                "note_score_clock_invalid", "Annotation disagrees with verified clock/source"
            )
        for witness in current.provenance_files:
            check()
            actual, _ = bounded_snapshot(witness.path, REPORT_BYTES)
            if actual != witness:
                raise OfflineError("note_score_provenance_changed", "Producer provenance changed")
    result = score_notes(
        annotation.notes,
        reference.annotation.notes if reference else None,
        should_cancel=should_cancel,
    )
    report = NoteScoreReport(
        candidate=candidate,
        reference=reference,
        pcm=pcm,
        recipe=recipe,
        result=result,
        decode_dependencies=dependencies,
        decoder_payload_root=payload_root,
    )
    check()
    verify_note_witnesses(report)
    if recipe != scoring_recipe():
        raise OfflineError("note_score_recipe_changed", "Scoring runtime/recipe changed")
    return report


def verify_note_score(
    report_path: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> NoteScoreReport:
    identity, raw = bounded_snapshot(report_path, REPORT_BYTES)
    report = NoteScoreReport.model_validate(load_unique_json(raw))
    current = collect_note_score(
        report.candidate.file.path,
        report.reference.file.path if report.reference else None,
        should_cancel=should_cancel,
    )
    if current != report:
        raise OfflineError(
            "note_score_replay_mismatch", "Complete current score disagrees with report"
        )
    verify_inputs([identity])
    verify_note_witnesses(current)
    return report
