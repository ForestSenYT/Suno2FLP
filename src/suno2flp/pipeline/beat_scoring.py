"""Exclusive source-bound conditional metric publication; no quality promotion."""

from pathlib import Path

from suno2flp.core.beat_annotations import BeatScoreReport
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.beat_backend import Cancel
from suno2flp.validator.beat_annotations import (
    collect_beat_score,
    score_witnesses,
    verify_score_witnesses,
)


def score_beat_files(
    candidate: Path, reference: Path | None, output: Path, *, should_cancel: Cancel = None
) -> BeatScoreReport:
    report = collect_beat_score(candidate, reference, should_cancel=should_cancel)
    publish_verified_report(
        output,
        report.model_dump_json(indent=2),
        [i.path for i in score_witnesses(report)],
        lambda: verify_score_witnesses(report, should_cancel=should_cancel),
    )
    return report
