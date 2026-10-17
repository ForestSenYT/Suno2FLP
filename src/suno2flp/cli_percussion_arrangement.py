"""Thin inferred arrangement commands; no model, host or job completion."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.percussion_arrangement import PercussionArrangement
from suno2flp.pipeline.percussion_arrangement import compose_percussion_arrangement
from suno2flp.validator.percussion_arrangement import verify_percussion_arrangement


def _summary(record: PercussionArrangement, verification: str) -> None:
    typer.echo(
        json.dumps(
            dict(
                status=record.status,
                verification=verification,
                notes=sum(len(part.notes) for part in record.parts),
                drum_onsets=sum(len(part.onsets) for part in record.parts),
                rejected_drum_peaks=len(record.inputs.drums.rejected_peaks),
                blockers=record.blockers,
                writer_eligibility=record.writer_eligibility,
                execution_allowed=False,
            ),
            indent=2,
        )
    )


def register_percussion_arrangement(app: typer.Typer) -> None:
    @app.command("compose-percussion-arrangement")
    def compose(
        batch: Path,
        drums: Annotated[Path, typer.Option("--drums", help="Current complete drum candidate")],
        output: Annotated[Path, typer.Option("--output", help="Exclusive new candidate directory")],
        beats: Annotated[
            Path | None, typer.Option("--beats", help="Optional current beats")
        ] = None,
    ) -> None:
        """Combine current pitch/drum estimates in original sample time; no MIDI/FLP."""
        try:
            record = compose_percussion_arrangement(batch, drums, output, beats_path=beats)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _summary(record, "current-artifact-composition")

    @app.command("verify-percussion-arrangement")
    def verify(report: Path) -> None:
        """Reconstruct all current producer relationships; no new native inference."""
        try:
            record = verify_percussion_arrangement(report)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        _summary(record, "current-artifact-reconstruction")
