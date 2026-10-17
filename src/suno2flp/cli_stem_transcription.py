"""Thin development commands for explicitly estimated pitched sources."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.stem_transcription import StemTranscriptionBatch
from suno2flp.pipeline.stem_transcription import transcribe_stems
from suno2flp.validator.stem_transcription import verify_stem_batch


def _summary(report: StemTranscriptionBatch) -> None:
    typer.echo(
        json.dumps(
            {
                "status": "unqualified_candidate",
                "stems": [entry.stem for entry in report.stems],
                "drums": report.drums,
                "ground_truth_metrics": report.ground_truth_metrics,
                "writer_eligibility": report.writer_eligibility,
                "execution_allowed": False,
            },
            indent=2,
        )
    )


def register_stem_transcription(app: typer.Typer) -> None:
    @app.command("transcribe-stems")
    def transcribe(
        separation: Path,
        backend: Annotated[Path, typer.Option("--backend")],
        output: Annotated[Path, typer.Option("--output", help="Exclusive new batch directory")],
    ) -> None:
        """Freshly replay separation, then estimate vocals/bass/other; no MIDI/FLP writes."""
        try:
            report = transcribe_stems(separation, backend, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _summary(report)

    @app.command("verify-stem-transcription")
    def verify(
        report: Path,
        output: Annotated[
            Path, typer.Option("--output", help="New complete native replay directory")
        ],
    ) -> None:
        """Repeat separation and every pitched estimate in new files; no quality qualification."""
        try:
            result = verify_stem_batch(report, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _summary(result)
