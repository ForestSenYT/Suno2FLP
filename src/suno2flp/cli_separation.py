"""Explicit preparation and native probe commands; no full-song or writer route."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.integrations.spleeter_backend import provision_spleeter, verify_spleeter


def _fail(error: Exception) -> None:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(1) from error


def register_separation(app: typer.Typer) -> None:
    @app.command("prepare-spleeter")
    def prepare(
        artifacts: Annotated[
            Path, typer.Option("--artifacts", help="Fixed local official artifacts")
        ],
        output: Annotated[Path, typer.Option("--output", help="New private backend directory")],
    ) -> None:
        """Prepare the audited local graph recipe without downloading or running a model."""
        try:
            record = provision_spleeter(output, artifacts)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(f"prepared_not_probed: {record.root}; model_qualification=not_assessed")

    @app.command("verify-spleeter")
    def probe(
        backend: Path,
        output: Annotated[
            Path, typer.Option("--output", help="New native probe evidence directory")
        ],
    ) -> None:
        """Actually restore the fixed CPU model and verify original signal probes in new files."""
        try:
            report = verify_spleeter(backend, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(
            json.dumps(
                {
                    "status": "native_runtime_verified",
                    "fixtures": len(report.evidence),
                    "repeatability": report.native.repeatability_scope,
                    "model_qualification": report.model_qualification,
                    "whole_song_support": report.whole_song_support,
                    "writer_eligibility": report.writer_eligibility,
                    "execution_allowed": False,
                },
                indent=2,
            )
        )
