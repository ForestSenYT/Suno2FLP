"""Thin CLI entry points over the shared audio job application service."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.job_store import StoredJob
from suno2flp.pipeline.audio_jobs import (
    cancel_audio_job,
    create_audio_job,
    run_audio_job,
    verify_audio_job,
)


def register_audio_jobs(app: typer.Typer) -> None:
    def emit(action: Callable[[], StoredJob], *, run: bool = False) -> None:
        try:
            stored = action()
        except (Suno2FLPError, OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        typer.echo(stored.model_dump_json(indent=2))
        if run:
            if stored.job.status == "blocked":
                raise typer.Exit(3)
            if stored.job.status == "failed":
                raise typer.Exit(1)

    @app.command("create-audio-job")
    def create(
        source: Path,
        output: Annotated[Path, typer.Option("--output", help="New exclusive job directory")],
        job_id: Annotated[str, typer.Option("--job-id", help="Stable lowercase job identifier")],
    ) -> None:
        """Create a queued local job; this does not generate a deliverable."""
        emit(lambda: create_audio_job(source, output, job_id))

    @app.command("run-audio-job")
    def run(snapshot: Path) -> None:
        """Preflight and losslessly decode integer PCM WAV; separation blocks with exit 3."""
        emit(lambda: run_audio_job(snapshot), run=True)

    @app.command("verify-audio-job")
    def verify(snapshot: Path) -> None:
        """Check linked history, current files and independent input evidence."""
        emit(lambda: verify_audio_job(snapshot))

    @app.command("cancel-audio-job")
    def cancel(snapshot: Path) -> None:
        """Cancel queued/interrupted work; an already stopped job retains its reason."""
        emit(lambda: cancel_audio_job(snapshot))
