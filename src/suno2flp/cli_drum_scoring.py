"""Thin drum annotation scoring commands; never authorize a model or writer."""

from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.drum_scoring import DrumScoreReport
from suno2flp.core.errors import Suno2FLPError
from suno2flp.pipeline.drum_scoring import score_drum_files
from suno2flp.validator.drum_scoring import verify_drum_score


def _show(report: DrumScoreReport) -> None:
    typer.echo(report.model_dump_json(indent=2))
    if report.result.status != "measured":
        raise typer.Exit(3)


def register_drum_scoring(app: typer.Typer) -> None:
    @app.command("score-drums")
    def score(
        candidate: Path,
        output: Annotated[Path, typer.Option("--output", help="New exclusive JSON report")],
        reference: Annotated[Path | None, typer.Option("--reference")] = None,
    ) -> None:
        """Measure conditional drum class/onset F1 on the original audio clock."""
        try:
            report = score_drum_files(candidate, reference, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _show(report)

    @app.command("verify-drum-score")
    def verify(report: Path) -> None:
        """Recompute complete current drum evidence without changing files."""
        try:
            result = verify_drum_score(report)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _show(result)
