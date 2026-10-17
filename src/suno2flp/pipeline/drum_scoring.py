"""Exclusive completion publication after current source and recipe checks."""

from pathlib import Path

from suno2flp.core.drum_scoring import DrumScoreReport
from suno2flp.core.offline_files import guarded_path
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.validator.drum_scoring import (
    Cancel,
    check_cancel,
    collect_drum_score,
    verify_drum_witnesses,
)


def score_drum_files(
    candidate_path: Path,
    reference_path: Path | None,
    output: Path,
    *,
    should_cancel: Cancel = None,
) -> DrumScoreReport:
    destination = guarded_path(output)
    if destination.exists():
        raise FileExistsError("Drum score output already exists")
    report = collect_drum_score(
        candidate_path, reference_path, destination, should_cancel=should_cancel
    )

    def verify() -> None:
        check_cancel(should_cancel)
        verify_drum_witnesses(report)

    publish_verified_report(
        destination,
        report.model_dump_json(indent=2) + "\n",
        [p.path for p in report.witnesses()],
        verify,
    )
    return report
