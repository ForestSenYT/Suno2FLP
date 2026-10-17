"""Thin editable audio-inference preview command; no host or FLP execution."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.pipeline.estimated_midi import export_estimated_midi, verify_estimated_midi_export


def register_estimated_midi(app: typer.Typer) -> None:
    @app.command("verify-estimated-midi")
    def verify(report: Path) -> None:
        """Reconstruct current inputs and verify a saved unqualified MIDI candidate."""
        try:
            record = verify_estimated_midi_export(report)
        except (Suno2FLPError, OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        typer.echo(
            json.dumps(
                dict(
                    status=record.score.status,
                    verification="current-source-rebuilt",
                    writer_eligibility="blocked",
                    execution_allowed=False,
                )
            )
        )

    @app.command("export-estimated-midi")
    def export(
        batch: Path,
        drums: Annotated[Path, typer.Option("--drums", help="Current complete drum candidate")],
        output: Annotated[Path, typer.Option("--output", help="New exclusive preview directory")],
        beats: Annotated[Path | None, typer.Option("--beats")] = None,
    ) -> None:
        """Export an unqualified editable candidate; no new inference or FLP authorization."""
        try:
            record = export_estimated_midi(batch, drums, output, beats_path=beats)
        except (Suno2FLPError, OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        typer.echo(
            json.dumps(
                dict(
                    status=record.score.status,
                    midi=str(record.midi.path),
                    notes=sum(len(p.notes) for p in record.score.parts),
                    clock_basis=record.score.clock_basis,
                    blockers=record.score.blockers,
                    writer_eligibility="blocked",
                    execution_allowed=False,
                ),
                indent=2,
            )
        )
