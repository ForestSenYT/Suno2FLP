"""Explicit local model preparation and candidate-only transcription commands."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.transcription import TranscriptionCandidate
from suno2flp.integrations.basic_pitch_backend import provision_basic_pitch, verify_basic_pitch
from suno2flp.pipeline.transcription import transcribe_audio
from suno2flp.validator.transcription import verify_transcription


def _candidate(report: TranscriptionCandidate) -> None:
    typer.echo(
        json.dumps(
            {
                "status": "unqualified_candidate",
                "origin": report.origin,
                "notes": len(report.result.notes),
                "windows": report.result.windows,
                "resampled_frames": report.result.resampled_frames,
                "ground_truth_metrics": report.ground_truth_metrics,
                "musical_correctness": report.musical_correctness,
                "writer_eligibility": report.writer_eligibility,
                "execution_allowed": False,
            },
            indent=2,
        )
    )


def _fail(error: Exception) -> None:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(1) from error


def register_transcription(app: typer.Typer) -> None:
    @app.command("prepare-basic-pitch")
    def prepare(
        artifacts: Annotated[
            Path, typer.Option("--artifacts", help="Already downloaded fixed official artifacts")
        ],
        output: Annotated[Path, typer.Option("--output", help="New private backend directory")],
    ) -> None:
        """Prepare audited local files explicitly; no download, source build or model inference."""
        try:
            record = provision_basic_pitch(output, artifacts)
        except (OSError, ValueError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(f"prepared_not_probed: {record.root}; model_qualification=not_assessed")

    @app.command("verify-basic-pitch")
    def probe(
        backend: Path,
        output: Annotated[
            Path, typer.Option("--output", help="New native handshake evidence directory")
        ],
    ) -> None:
        """Load the fixed private CPU model and verify actual dimensions and repeatability."""
        try:
            verify_basic_pitch(backend, output)
        except (OSError, ValueError, Suno2FLPError) as error:
            _fail(error)
        typer.echo(
            "native_runtime_verified; model_qualification=not_assessed; writer_eligibility=blocked"
        )

    @app.command("transcribe-audio")
    def transcribe(
        decode_report: Path,
        backend: Annotated[Path, typer.Option("--backend")],
        output: Annotated[Path, typer.Option("--output", help="New candidate directory")],
    ) -> None:
        """Retain complete source-bound raw predictions and estimated notes; no MIDI/FLP writes."""
        try:
            report = transcribe_audio(decode_report, backend, output)
        except (OSError, ValueError, Suno2FLPError) as error:
            _fail(error)
        _candidate(report)

    @app.command("verify-transcription")
    def verify(
        report: Path,
        output: Annotated[
            Path, typer.Option("--output", help="New fresh inference replay directory")
        ],
    ) -> None:
        """Replay complete native inference in new files without modifying the candidate."""
        try:
            result = verify_transcription(report, output)
        except (OSError, ValueError, Suno2FLPError) as error:
            _fail(error)
        _candidate(result)
