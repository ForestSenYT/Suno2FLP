"""Thin explicit local rhythm development commands, never delivery promotion."""

import json
from pathlib import Path
from typing import Annotated

import typer

from suno2flp.core.errors import Suno2FLPError
from suno2flp.integrations.beat_backend import provision_beat_backend
from suno2flp.integrations.beat_probe import probe_beat_backend
from suno2flp.pipeline.beat_analysis import analyze_beats
from suno2flp.pipeline.beat_scoring import score_beat_files
from suno2flp.validator.beat_analysis import verify_beat_analysis
from suno2flp.validator.beat_annotations import verify_beat_score


def _fail(error: Exception) -> None:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(1) from error


def _summary(**values: object) -> None:
    typer.echo(
        json.dumps(
            {**values, "model_qualification": "not_assessed", "writer_eligibility": "blocked"},
            indent=2,
        )
    )


def register_beat_analysis(app: typer.Typer) -> None:
    @app.command("prepare-beat-backend")
    def prepare(
        artifacts: Annotated[Path, typer.Option("--artifacts")],
        output: Annotated[Path, typer.Option("--output")],
    ) -> None:
        """Prepare fixed local wheels and final0 weights in a new private directory."""
        try:
            record = provision_beat_backend(output, artifacts)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        _summary(status="prepared_not_probed", backend=str(record.root))

    @app.command("probe-beat-backend")
    def probe(backend: Path, output: Annotated[Path, typer.Option("--output")]) -> None:
        """Run all four original native fixtures twice; no music qualification."""
        try:
            report = probe_beat_backend(backend, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        _summary(status="observed_native_repetition", fixtures=len(report.fixtures))

    @app.command("analyze-beats")
    def analyze(
        decode_report: Path,
        backend: Annotated[Path, typer.Option("--backend")],
        output: Annotated[Path, typer.Option("--output")],
    ) -> None:
        """Keep source-bound inferred beats and complete raw arrays; no MIDI/FLP writes."""
        try:
            report = analyze_beats(decode_report, backend, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        _summary(
            status="unqualified_candidate",
            beats=len(report.beats),
            downbeats=len(report.downbeats),
            signal_observations=report.signal_observations,
        )

    @app.command("verify-beat-analysis")
    def verify(report: Path, output: Annotated[Path, typer.Option("--output")]) -> None:
        """Require new complete native inference in exclusive files."""
        try:
            receipt = verify_beat_analysis(report, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        _summary(status="fresh_native_replay", comparison=receipt.comparison)

    @app.command("score-beats")
    def score(
        candidate: Path,
        output: Annotated[Path, typer.Option("--output")],
        reference: Annotated[Path | None, typer.Option("--reference")] = None,
    ) -> None:
        """Measure declared beat annotations conditionally; absent truth stays unavailable."""
        try:
            report = score_beat_files(candidate, reference, output)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        _summary(
            status=report.result.status,
            matches=len(report.result.matches),
            annotation_truth_verified=False,
        )

    @app.command("verify-beat-score")
    def verify_score(report: Path) -> None:
        """Recompute complete source-bound label metrics from current evidence."""
        try:
            current = verify_beat_score(report)
        except (OSError, ValueError, RecursionError, Suno2FLPError) as error:
            _fail(error)
        _summary(status=current.result.status, annotation_truth_verified=False)
