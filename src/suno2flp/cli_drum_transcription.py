"""Thin explicit drum runtime/candidate commands; never complete a conversion job."""

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.integrations.drum_backend import provision_drum_backend
from suno2flp.integrations.drum_probe import probe_drum_backend
from suno2flp.pipeline.drum_transcription import export_drum_annotation, transcribe_drums
from suno2flp.validator.drum_transcription import verify_drum_transcription


def _fail(error: Exception) -> NoReturn:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(1) from error


def register_drum_transcription(app: typer.Typer) -> None:
    @app.command("prepare-drum-backend")
    def prepare(
        artifacts: Annotated[
            Path, typer.Option("--artifacts", help="Already downloaded fixed local artifacts")
        ],
        output: Annotated[
            Path, typer.Option("--output", help="New exclusive private backend directory")
        ],
    ) -> None:
        """Prepare fixed local files without downloads, source setup or model execution."""
        try:
            record = provision_drum_backend(output, artifacts)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(f"prepared_not_probed: {record.root}; model_qualification=not_assessed")

    @app.command("verify-drum-backend")
    def probe(backend: Path, output: Annotated[Path, typer.Option("--output")]) -> None:
        """Run actual original signal probes and complete native repeats in new files."""
        try:
            report = probe_drum_backend(backend, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(
            f"native_runtime_verified: {report.root}; "
            "model_qualification=not_assessed; writer=blocked"
        )

    @app.command("transcribe-drums")
    def transcribe(
        separation: Path,
        separation_replay: Annotated[Path, typer.Option("--separation-replay")],
        backend: Annotated[Path, typer.Option("--backend")],
        output: Annotated[
            Path, typer.Option("--output", help="New exclusive source-bound candidate directory")
        ],
    ) -> None:
        """Retain complete estimated-drum raw outputs and original-clock peak/rejection audit."""
        try:
            record = transcribe_drums(separation, separation_replay, backend, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(
            json.dumps(
                dict(
                    status="unqualified_candidate",
                    root=str(record.root),
                    events=len(record.events),
                    rejected_padding=len(record.rejected_peaks),
                    ground_truth_metrics=record.ground_truth_metrics,
                    writer_eligibility=record.writer_eligibility,
                    execution_allowed=record.execution_allowed,
                )
            )
        )

    @app.command("verify-drum-transcription")
    def replay(report: Path, output: Annotated[Path, typer.Option("--output")]) -> None:
        """Independently run complete current drum inference in a new replay directory."""
        try:
            receipt = verify_drum_transcription(report, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(receipt.model_dump_json(indent=2))

    @app.command("export-drum-annotation")
    def export(report: Path, output: Annotated[Path, typer.Option("--output")]) -> None:
        """Export a separate current inferred candidate annotation for conditional scoring."""
        try:
            annotation = export_drum_annotation(report, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(
            f"inferred_candidate_annotation: {output}; events={len(annotation.events)}; "
            "truth=unverified"
        )
