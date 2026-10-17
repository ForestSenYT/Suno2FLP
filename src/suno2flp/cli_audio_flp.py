"""Explicit candidate file workflow only; no automatic host invocation."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.pipeline.audio_flp import export_audio_flp, verify_audio_flp_export


def register_audio_flp(app: typer.Typer) -> None:
    @app.command("export-audio-flp")
    def export(
        report: Path,
        base: Annotated[Path, typer.Option("--base", help="Exact observed base component")],
        sampler: Annotated[
            Path, typer.Option("--sampler", help="Exact observed sampler component")
        ],
        output: Annotated[Path, typer.Option("--output", help="New exclusive candidate directory")],
    ) -> None:
        """Build an unqualified inferred-note FLP; requires separately pinned components."""
        try:
            result = export_audio_flp(report, base, sampler, output)
        except (Suno2FLPError, OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        typer.echo(
            json.dumps(
                dict(
                    status=result.status,
                    project=str(result.root / "project.flp"),
                    blockers=result.blockers,
                    host_compatibility="unverified",
                ),
                indent=2,
            )
        )

    @app.command("verify-audio-flp")
    def verify(report: Path) -> None:
        """Rebuild complete current sources and independently check an existing candidate."""
        try:
            result = verify_audio_flp_export(report)
        except (Suno2FLPError, OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        typer.echo(
            json.dumps(
                dict(
                    status=result.status,
                    verification="current-source-rebuilt",
                    host_compatibility="unverified",
                    listening="not_performed",
                )
            )
        )
