"""Thin CLI entry points over the shared audio job application service."""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.audio_input import AudioPreflightError
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.job_store import StoredJob
from suno2flp.integrations.codec_backend import provision_codec_backend, verify_codec_backend
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
    def run(
        snapshot: Path,
        decoder_directory: Annotated[
            Path | None,
            typer.Option(
                "--decoder-directory", help="Explicit isolated decoder for qualified FLAC/MP3"
            ),
        ] = None,
    ) -> None:
        """Check and verify decoded audio; unavailable later workers block with exit 3."""
        emit(lambda: run_audio_job(snapshot, decoder_directory=decoder_directory), run=True)

    @app.command("verify-audio-job")
    def verify(snapshot: Path) -> None:
        """Check linked history, current files and independent input evidence."""
        emit(lambda: verify_audio_job(snapshot))

    @app.command("cancel-audio-job")
    def cancel(snapshot: Path) -> None:
        """Cancel queued/interrupted work; an already stopped job retains its reason."""
        emit(lambda: cancel_audio_job(snapshot))

    def codec(directory: Path, wheelhouse: Path | None, *, provision: bool) -> None:
        try:
            record = (
                provision_codec_backend(directory, Path(sys.executable), wheelhouse=wheelhouse)
                if provision
                else verify_codec_backend(directory)
            )
        except (Suno2FLPError, OSError, ValueError) as error:
            typer.echo(f"Error: {getattr(error, 'code', 'audio_io_failed')}: {error}", err=True)
            raise typer.Exit(
                3 if isinstance(error, AudioPreflightError) and error.blocked else 1
            ) from error
        typer.echo(record.model_dump_json(indent=2))

    @app.command("provision-audio-decoder")
    def provision_decoder(
        directory: Path,
        wheelhouse: Annotated[
            Path | None,
            typer.Option(
                "--wheelhouse", help="Offline fixed wheels; otherwise download from official PyPI"
            ),
        ] = None,
    ) -> None:
        """Explicitly prepare a new private, pinned decoder; never runs at GUI startup."""
        codec(directory, wheelhouse, provision=True)

    @app.command("verify-audio-decoder")
    def verify_decoder(directory: Path) -> None:
        """Read-only payload validation and real isolated native handshake."""
        codec(directory, None, provision=False)
