"""Exclusive publication of measured or explicitly unavailable annotation scores."""

from collections.abc import Callable
from pathlib import Path

from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import REPORT_BYTES, NoteScoreReport
from suno2flp.core.offline_files import new_report
from suno2flp.validator.note_decode_evidence import verify_note_witnesses
from suno2flp.validator.note_scoring import collect_note_score


def score_note_files(
    candidate_path: Path,
    reference_path: Path | None,
    output: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> NoteScoreReport:
    report = collect_note_score(candidate_path, reference_path, should_cancel=should_cancel)
    content = report.model_dump_json(indent=2) + "\n"
    if len(content.encode("utf-8")) > REPORT_BYTES:
        raise OfflineError("note_score_output_limit", "Complete score exceeds report budget")
    if should_cancel and should_cancel():
        raise OfflineError("note_score_cancelled", "Note scoring cancelled before publication")
    verify_note_witnesses(report)
    new_report(output, content, report.protected_paths())
    verify_note_witnesses(report)
    return report
