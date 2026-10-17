"""Thin source-clock candidate commands; never complete a conversion job."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.estimated_arrangement import EstimatedArrangement
from suno2flp.pipeline.estimated_arrangement import compose_estimated_arrangement
from suno2flp.validator.estimated_arrangement import verify_estimated_arrangement


def _summary(record: EstimatedArrangement, verification: str) -> None:
    typer.echo(
        json.dumps(
            {
                "status": "unqualified_candidate",
                "verification": verification,
                "parts": [part.stem for part in record.parts],
                "notes": sum(len(part.notes) for part in record.parts),
                "blockers": record.blockers,
                "writer_eligibility": record.writer_eligibility,
                "execution_allowed": False,
            },
            indent=2,
        )
    )


def register_estimated_arrangement(app: typer.Typer) -> None:
    @app.command("compose-estimated-arrangement")
    def compose(
        batch: Path,
        output: Annotated[Path, typer.Option("--output", help="Exclusive new candidate directory")],
        beats: Annotated[
            Path | None, typer.Option("--beats", help="Optional current beat report")
        ] = None,
    ) -> None:
        """Compose complete stem estimates in the exact audio clock; no MIDI/FLP/preview."""
        try:
            result = compose_estimated_arrangement(batch, output, beats_path=beats)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _summary(result, "current-artifact-composition")

    @app.command("verify-estimated-arrangement")
    def verify(report: Path) -> None:
        """Reconstruct from all current artifacts; no fresh model or host execution."""
        try:
            result = verify_estimated_arrangement(report)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _summary(result, "current-artifact-reconstruction")
