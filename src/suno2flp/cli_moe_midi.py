"""Explicit inferred MIDI candidate commands; no model installation or FLP execution."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.cli_yourmt3_moe import _fail
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.moe_midi import MoEMidiExport
from suno2flp.pipeline.moe_midi import export_moe_midi, verify_moe_midi_export


def _show(record: MoEMidiExport) -> None:
    typer.echo(
        json.dumps(
            dict(
                root=str(record.root),
                status=record.score.status,
                files=len(record.files),
                notes=sum(len(p.notes) for p in record.score.parts),
                clock_basis=record.score.clock_basis,
                writer_eligibility="blocked",
                execution_allowed=False,
                blockers=record.score.blockers,
            )
        )
    )


def register_moe_midi(app: typer.Typer) -> None:
    @app.command("export-yourmt3-moe-midi")
    def export(report: Path, output: Annotated[Path, typer.Option("--output")]) -> None:
        """Verify current MoE tokens and export separate editable model-program files."""
        try:
            record = export_moe_midi(report, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        _show(record)

    @app.command("verify-yourmt3-moe-midi")
    def verify(report: Path) -> None:
        """Independently recheck the complete bundle; music/host/writer remain blocked."""
        try:
            record = verify_moe_midi_export(report)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        _show(record)
