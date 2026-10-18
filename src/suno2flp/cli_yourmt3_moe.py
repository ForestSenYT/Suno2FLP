"""Explicit opt-in MoE commands; no automatic model install, jobs or FLP writes."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import guarded_path, load_unique_json
from suno2flp.core.yourmt3 import FrameInterval
from suno2flp.integrations.yourmt3_moe_backend import provision_yourmt3_moe_backend
from suno2flp.pipeline.yourmt3_moe import transcribe_yourmt3_moe
from suno2flp.validator.yourmt3_moe import verify_yourmt3_moe


def _fail(error: Exception) -> NoReturn:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(1) from error


def register_yourmt3_moe(app: typer.Typer) -> None:
    @app.command("prepare-yourmt3-moe-backend")
    def prepare(
        artifacts: Annotated[Path, typer.Option("--artifacts")],
        output: Annotated[Path, typer.Option("--output")],
    ) -> None:
        """Prepare fixed local MoE artifacts; native and music acceptance remain separate."""
        try:
            record = provision_yourmt3_moe_backend(output, artifacts)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(f"prepared_not_probed: {record.root}; writer=blocked")

    @app.command("transcribe-yourmt3-moe")
    def transcribe(
        decode: Path,
        backend: Annotated[Path, typer.Option("--backend")],
        intervals: Annotated[Path, typer.Option("--intervals")],
        output: Annotated[Path, typer.Option("--output")],
    ) -> None:
        """Create an unqualified complete13-channel candidate with retained generation traces."""
        try:
            path = guarded_path(intervals)
            if path.stat().st_size > 65536:
                raise ValueError("Interval manifest exceeds budget")
            raw = load_unique_json(path.read_bytes())
            if not isinstance(raw, list):
                raise ValueError("Expected an array of original-frame intervals")
            record = transcribe_yourmt3_moe(
                decode, backend, output, [FrameInterval.model_validate(i) for i in raw]
            )
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(record.model_dump_json(indent=2))

    @app.command("verify-yourmt3-moe")
    def verify(report: Path) -> None:
        """Recheck source/runtime/trace identities and independently decode all13 streams."""
        try:
            record = verify_yourmt3_moe(report)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(f"current_tokens_verified: {record.root}; music=not_assessed; writer=blocked")
