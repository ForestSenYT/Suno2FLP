"""Explicit unqualified YourMT3+ development commands; no FLP writing or downloads."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import guarded_path, load_unique_json
from suno2flp.core.yourmt3 import FrameInterval
from suno2flp.integrations.yourmt3_backend import provision_yourmt3_backend
from suno2flp.pipeline.yourmt3 import transcribe_yourmt3
from suno2flp.validator.yourmt3 import verify_yourmt3


def _fail(error: Exception) -> NoReturn:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(1) from error


def register_yourmt3(app: typer.Typer) -> None:
    @app.command("prepare-yourmt3-backend")
    def prepare(
        artifacts: Annotated[Path, typer.Option("--artifacts")],
        output: Annotated[Path, typer.Option("--output")],
    ) -> None:
        """Prepare already downloaded fixed local artifacts in a new private directory."""
        try:
            record = provision_yourmt3_backend(output, artifacts)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(f"prepared_not_probed: {record.root}; writer=blocked")

    @app.command("transcribe-yourmt3")
    def transcribe(
        decode: Path,
        backend: Annotated[Path, typer.Option("--backend")],
        intervals: Annotated[
            Path, typer.Option("--intervals", help="JSON array of original-frame intervals")
        ],
        output: Annotated[Path, typer.Option("--output")],
    ) -> None:
        """Transcribe continuous audio and observe intervals without cropping the model input."""
        try:
            path = guarded_path(intervals)
            if path.stat().st_size > 65536:
                raise ValueError("Interval manifest exceeds budget")
            raw = load_unique_json(path.read_bytes())
            if not isinstance(raw, list):
                raise ValueError("Expected an array of explicit source-frame intervals")
            record = transcribe_yourmt3(
                decode, backend, output, [FrameInterval.model_validate(i) for i in raw]
            )
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(record.model_dump_json(indent=2))

    @app.command("verify-yourmt3")
    def verify(report: Path) -> None:
        """Recheck current files and replay all tokens into a new retained sibling directory."""
        try:
            record = verify_yourmt3(report)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(f"current_tokens_verified: {record.root}; music=not_assessed; writer=blocked")
