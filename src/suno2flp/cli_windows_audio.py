"""Explicit read-only device diagnostic; no host or stream operation."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.errors import Suno2FLPError
from suno2flp.integrations.windows_audio import inspect_windows_audio


def register_windows_audio(app: typer.Typer) -> None:
    @app.command("inspect-windows-audio")
    def inspect(output: Annotated[Path, typer.Option("--output")]) -> None:
        """Inspect output devices into a NEW directory; never start FL Studio."""
        try:
            result = inspect_windows_audio(output)
        except (OSError, ValueError, RecursionError, Suno2FLPError, DecodeCancelled) as error:
            typer.echo(f"Discovery failed: {error}", err=True)
            raise typer.Exit(1) from error
        typer.echo(
            json.dumps(
                {
                    "status": result.assessment.status,
                    "active_outputs": result.assessment.active_count,
                    "default_roles": result.assessment.default_roles,
                    "report": str(result.root / "inspection.json"),
                    "validity": "observed_interval_only",
                    "host_compatibility": result.host_compatibility,
                    "execution_allowed": result.execution_allowed,
                },
                indent=2,
            )
        )
        if result.assessment.status != "output_detected":
            typer.echo(
                "Connect an available audio output; host acceptance remains pending.", err=True
            )
            raise typer.Exit(2)
