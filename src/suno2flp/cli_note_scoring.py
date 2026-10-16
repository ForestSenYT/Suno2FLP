"""Thin conditional-metric commands; no job qualification or DAW actions."""

from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.note_scoring import NoteScoreReport
from suno2flp.pipeline.note_scoring import score_note_files
from suno2flp.validator.note_scoring import verify_note_score


def _show(report: NoteScoreReport) -> None:
    typer.echo(report.model_dump_json(indent=2))
    if report.result.status != "measured":
        raise typer.Exit(3)


def register_note_scoring(app: typer.Typer) -> None:
    @app.command("score-pitched-notes")
    def score(
        candidate: Path,
        output: Annotated[Path, typer.Option("--output", help="New exclusive JSON report")],
        reference: Annotated[Path | None, typer.Option("--reference")] = None,
    ) -> None:
        """Measure source-bound note annotations; missing truth is explicitly unscored."""
        try:
            report = score_note_files(candidate, reference, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _show(report)

    @app.command("verify-note-score")
    def verify(report: Path) -> None:
        """Recompute current evidence and metrics without rewriting the report."""
        try:
            result = verify_note_score(report)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _show(result)
