"""Deterministic workspace, MIDI import/cleanup, arrangement and validation commands."""

import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from suno2flp.arrangement import ExplicitInstrumentMapper, FaithfulArrangementEngine
from suno2flp.cli_audio_flp import register_audio_flp
from suno2flp.cli_audio_jobs import register_audio_jobs
from suno2flp.cli_beat_analysis import register_beat_analysis
from suno2flp.cli_drum_scoring import register_drum_scoring
from suno2flp.cli_drum_transcription import register_drum_transcription
from suno2flp.cli_estimated_arrangement import register_estimated_arrangement
from suno2flp.cli_estimated_midi import register_estimated_midi
from suno2flp.cli_note_scoring import register_note_scoring
from suno2flp.cli_percussion_arrangement import register_percussion_arrangement
from suno2flp.cli_separation import register_separation
from suno2flp.cli_stem_transcription import register_stem_transcription
from suno2flp.cli_transcription import register_transcription
from suno2flp.cli_windows_audio import register_windows_audio
from suno2flp.cli_yourmt3 import register_yourmt3
from suno2flp.core.config import MidiPreferences, load_config
from suno2flp.core.doctor import check_environment
from suno2flp.core.errors import (
    ArrangementError,
    MidiProcessingError,
    Suno2FLPError,
    UnsafePathError,
)
from suno2flp.core.instrument_config import load_instrument_mapping
from suno2flp.core.models import Arrangement, ArrangementOptions, MusicalMetadata, ProcessedMidi
from suno2flp.core.offline_files import new_report, verify_inputs
from suno2flp.core.workspace import init_project as create_project
from suno2flp.flp_builder.assessment_files import assess_template_files
from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files
from suno2flp.flp_builder.encoding_assessment import assess_encoding_file, verify_encoding_file
from suno2flp.flp_builder.midi_routing import plan_midi_routing_file, verify_midi_routing_file
from suno2flp.flp_builder.performance import plan_performance_file, verify_performance_file
from suno2flp.flp_builder.planning_files import plan_build_files
from suno2flp.flp_builder.writer_files import build_fl26_files, plan_fl26_files
from suno2flp.importer import LocalAssetImporter, MidiFileImporter
from suno2flp.integrations.fl26_controls import inspect_controls_file
from suno2flp.integrations.music2daw import Music2DawInspector
from suno2flp.integrations.music2daw_provision import provision_music2daw as provision_backend
from suno2flp.midi_processor import DeterministicMidiProcessor
from suno2flp.pipeline.preparation import prepare_project, verify_preparation
from suno2flp.validator import validate_project
from suno2flp.validator.arrangement import verify_arrangement_file
from suno2flp.validator.manual_records import check_manual_records, manual_record_summary
from suno2flp.validator.midi_comparison import compare_midi_events, verify_midi_comparison
from suno2flp.validator.renders import compare_renders

app = typer.Typer(
    help="Inspect Suno assets and prepare safe FL Studio workspaces.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
register_audio_jobs(app)
register_note_scoring(app)
register_drum_scoring(app)
register_drum_transcription(app)
register_percussion_arrangement(app)
register_transcription(app)
register_separation(app)
register_stem_transcription(app)
register_beat_analysis(app)
register_windows_audio(app)
register_estimated_arrangement(app)
register_estimated_midi(app)
register_audio_flp(app)
register_yourmt3(app)


@app.callback()
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def _fail(error: Exception) -> None:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(1)


@app.command()
def doctor() -> None:
    """Report real prerequisite availability; no DAW connection is attempted."""
    for check in check_environment():
        typer.echo(f"{check.component}: {check.status} - {check.detail}")
    if sys.version_info < (3, 11):  # noqa: UP036 - doctor explicitly reports this requirement.
        raise typer.Exit(1)


@app.command("check-host-records")
def check_host_records(
    manifest: Path,
    root: Annotated[
        Path, typer.Option("--root", help="Explicit root for contained evidence files")
    ],
    output: Annotated[Path | None, typer.Option("--output", help="New offline report file")] = None,
    markdown: Annotated[bool, typer.Option("--markdown", help="Render a Markdown summary")] = False,
) -> None:
    """Check local manual records/hashes; no DAW/backend, repairs or writer authorization."""
    try:
        destination = None
        if output is not None:
            destination = output.resolve()
            suffix = ".md" if markdown else ".json"
            if (
                output.exists()
                or output.is_symlink()
                or destination == manifest.resolve()
                or destination.suffix.lower() != suffix
                or not destination.parent.is_dir()
                or any(":" in part for part in output.parts if part != output.anchor)
                or any((parent / "backend.json").is_file() for parent in destination.parents)
            ):
                raise UnsafePathError(
                    "Use a new report with matching format outside backend directories"
                )
        result = check_manual_records(manifest, root)
        if destination is not None and any(
            destination == (root.resolve() / item.expected.path).resolve() for item in result.files
        ):
            raise UnsafePathError("Report destination must be distinct from all input references")
        content = (
            manual_record_summary(result) if markdown else result.model_dump_json(indent=2) + "\n"
        )
        if destination is None:
            typer.echo(content, nl=False)
        else:
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            typer.echo(f"Offline record report: {destination}; host unverified; writer blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)
    if not result.integrity_valid:
        raise typer.Exit(1)


@app.command("verify-arrangement")
def verify_arrangement(
    arrangement: Path,
    output: Annotated[
        Path | None, typer.Option("--output", help="New structural quality JSON")
    ] = None,
) -> None:
    """Replay faithful music from current original MIDI; host/writer remain unverified."""
    try:
        result = verify_arrangement_file(arrangement)
        content = result.model_dump_json(indent=2) + "\n"
        if output is None:
            typer.echo(content, nl=False)
        else:
            new_report(output, content, result.referenced_paths)
            typer.echo(f"Structural quality report: {output}; host unverified; writer blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)
    if not result.valid:
        raise typer.Exit(1)


@app.command("plan-midi-performance")
def plan_midi_performance(
    arrangement: Path,
    output: Annotated[Path, typer.Option("--output", help="New exact event-timing JSON report")],
    target_ppq: Annotated[int | None, typer.Option("--target-ppq", min=1, max=65535)] = None,
) -> None:
    """Compile original events and exact times; FLP encoding remains blocked."""
    try:
        result = plan_performance_file(arrangement, target_ppq=target_ppq)
        content = result.model_dump_json(indent=2) + "\n"
        verify_inputs(result.input_files)
        new_report(output, content, result.referenced_paths)
        verify_inputs(result.input_files)
        typer.echo(f"Performance requirements: {output}; source verified; FLP execution blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("inspect-fl26-controls")
def inspect_fl26_controls(
    template: Path,
    output: Annotated[Path, typer.Option("--output", help="New read-only control evidence JSON")],
) -> None:
    """Inspect selected event-223 fields; no host actions or FLP writing."""
    try:
        result = inspect_controls_file(template)
        assert result.source_file is not None
        content = result.model_dump_json(indent=2) + "\n"
        verify_inputs([result.source_file])
        new_report(output, content, [result.source_file.path])
        verify_inputs([result.source_file])
        typer.echo(f"Control evidence: {output}; timing/routing unverified; FLP execution blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("verify-midi-performance")
def verify_midi_performance(plan_file: Path) -> None:
    """Reconstruct every saved performance requirement; never authorize FLP writes."""
    try:
        verify_performance_file(plan_file)
        typer.echo("Performance replay passed; host unverified; FLP execution blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("assess-midi-encoding")
def assess_midi_encoding(
    performance_file: Path,
    output: Annotated[
        Path, typer.Option("--output", help="New exact precision and routing assessment")
    ],
) -> None:
    """Analyze encoding blockers; hypothetical rounding is never applied to music."""
    try:
        result = assess_encoding_file(performance_file)
        content = result.model_dump_json(indent=2) + "\n"
        verify_inputs(result.input_files)
        new_report(output, content, result.referenced_paths)
        verify_inputs(result.input_files)
        typer.echo(
            f"Encoding assessment: {output}; routing/timing unverified; FLP execution blocked"
        )
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("verify-midi-encoding")
def verify_midi_encoding(assessment_file: Path) -> None:
    """Replay all precision/routing evidence against current original inputs."""
    try:
        verify_encoding_file(assessment_file)
        typer.echo("Encoding assessment replay passed; FLP execution blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("plan-midi-routing")
def plan_midi_routing_command(
    performance_file: Path,
    bindings_file: Path,
    output: Annotated[Path, typer.Option("--output", help="New source-preserving route plan")],
) -> None:
    """Validate explicit destinations; no plugin loading, MIDI dispatch or FLP writing."""
    try:
        result = plan_midi_routing_file(performance_file, bindings_file)
        content = result.model_dump_json(indent=2) + "\n"
        verify_inputs(result.input_files)
        new_report(output, content, result.referenced_paths)
        verify_inputs(result.input_files)
        typer.echo(f"MIDI routing plan: {output}; receiver unverified; FLP execution blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("verify-midi-routing")
def verify_midi_routing_command(report_file: Path) -> None:
    """Replay current sources and bindings; success does not attest delivery."""
    try:
        verify_midi_routing_file(report_file)
        typer.echo("MIDI routing replay passed; receiver unverified; FLP execution blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("compare-midi-events")
def compare_midi_events_command(
    expected: Path,
    candidate: Path,
    output: Annotated[Path, typer.Option("--output", help="New decoded event/clock comparison")],
) -> None:
    """Compare all decoded events and exact clocks; no remapping or host execution."""
    try:
        result = compare_midi_events(expected, candidate)
        content = result.model_dump_json(indent=2) + "\n"
        verify_inputs(result.input_files)
        new_report(output, content, result.referenced_paths)
        verify_inputs(result.input_files)
        status = "equivalent decoded streams" if result.equivalent else "different/unverified"
        typer.echo(f"MIDI comparison: {output}; {status}; receiver unverified; writer blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)
    if not result.equivalent:
        raise typer.Exit(1)


@app.command("verify-midi-comparison")
def verify_midi_comparison_command(report_file: Path) -> None:
    """Recompute saved evidence; successful replay does not mean the files are equivalent."""
    try:
        result = verify_midi_comparison(report_file)
        status = "equivalent" if result.equivalent else "different/unverified"
        typer.echo(f"MIDI comparison replay passed ({status}); receiver unverified; writer blocked")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("prepare-project")
def prepare_project_command(
    project: Path,
    output_directory: Annotated[Path, typer.Option("--output-dir", help="New intermediate bundle")],
    target_ppq: Annotated[int | None, typer.Option("--target-ppq", min=1)] = None,
    timing_source: Annotated[int | None, typer.Option("--timing-source", min=0)] = None,
    instruments: Annotated[Path | None, typer.Option("--instruments")] = None,
) -> None:
    """Prepare deterministic JSON assets/music/quality; no FLP or DAW execution."""
    try:
        run = prepare_project(
            project,
            output_directory,
            options=ArrangementOptions(
                target_ppq=target_ppq,
                timing_source=timing_source,
                note_view="active",
            ),
            mapping_file=instruments,
        )
        typer.echo(
            f"Offline preparation: {run.destination / 'run.json'}; host unverified; writer blocked"
        )
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("verify-preparation")
def verify_preparation_command(run_file: Path) -> None:
    """Reconstruct a saved preparation from current originals; never repair it."""
    try:
        typer.echo(verify_preparation(run_file).model_dump_json(indent=2))
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("compare-renders")
def compare_renders_command(
    reference: Path,
    candidate: Path,
    max_rms_error: Annotated[float | None, typer.Option("--max-rms-error", min=0)] = None,
    output: Annotated[Path | None, typer.Option("--output", help="New PCM comparison JSON")] = None,
) -> None:
    """Measure explicit aligned integer PCM WAVs; no rendering or audible acceptance."""
    try:
        result = compare_renders(reference, candidate, max_rms_error=max_rms_error)
        content = result.model_dump_json(indent=2) + "\n"
        if output is None:
            typer.echo(content, nl=False)
        else:
            new_report(output, content, [reference.absolute(), candidate.absolute()])
            typer.echo(f"PCM measurement report: {output}; audible acceptance unverified")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)
    if not result.valid:
        raise typer.Exit(1)


@app.command("provision-music2daw")
def provision_music2daw(
    backend_directory: Path,
    fl26_read_only: Annotated[
        bool,
        typer.Option("--fl26-read-only", help="New isolated exact-build inspection adaptation"),
    ] = False,
) -> None:
    """Explicitly fetch/build the reviewed CLI pin in a new isolated directory."""
    try:
        result = provision_backend(backend_directory, fl26_read_only=fl26_read_only)
        typer.echo(
            f"Provisioned {result.revision}; record: {backend_directory.resolve() / 'backend.json'}"
        )
    except (Suno2FLPError, OSError, RuntimeError) as exc:
        _fail(exc)


@app.command("inspect-template")
def inspect_template(
    template: Path,
    backend_directory: Annotated[
        Path, typer.Option("--backend-dir", help="Explicit isolated Music2DAW directory")
    ],
    output: Annotated[
        Path | None, typer.Option("--output", help="New inspection JSON report")
    ] = None,
    timeout: Annotated[float, typer.Option("--timeout", min=0.1, max=300)] = 30,
) -> None:
    """Inspect template metadata with before/after hashes; never edit/export/launch FLP."""
    try:
        destination = None
        if output is not None:
            destination = output.resolve()
            if (
                output.exists()
                or output.is_symlink()
                or any(":" in part for part in output.parts if part != output.anchor)
                or destination.suffix.lower() != ".json"
                or destination == template.resolve()
                or destination.is_relative_to(backend_directory.resolve())
                or not destination.parent.is_dir()
            ):
                raise UnsafePathError(
                    "Report must be a new .json outside the backend and distinct from inputs, "
                    "with an existing parent"
                )
        result = Music2DawInspector(backend_directory, timeout=timeout).inspect(template)
        content = result.model_dump_json(indent=2) + "\n"
        if destination is None:
            typer.echo(content, nl=False)
        else:
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            typer.echo(
                f"Inspected {result.template_path}; compatibility unverified; "
                f"backend summary {result.backend_summary_status}; report: {destination}"
            )
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("assess-template")
def assess_template(
    inspection_file: Path,
    backend_directory: Annotated[Path, typer.Option("--backend-dir")],
    arrangement_file: Annotated[Path | None, typer.Option("--arrangement")] = None,
    bindings_file: Annotated[Path | None, typer.Option("--bindings")] = None,
    output: Annotated[
        Path | None, typer.Option("--output", help="New read-only assessment JSON")
    ] = None,
) -> None:
    """Assess FL26 dependencies/local bindings; no process, path expansion or FLP writes."""
    try:
        destination = None
        if output is not None:
            destination = output.resolve()
            if (
                output.exists()
                or output.is_symlink()
                or any(":" in part for part in output.parts if part != output.anchor)
                or destination.suffix.lower() != ".json"
                or destination.is_relative_to(backend_directory.resolve())
                or not destination.parent.is_dir()
            ):
                raise UnsafePathError(
                    "Assessment must be a new .json outside the backend with an existing parent"
                )
        report = assess_template_files(
            inspection_file, backend_directory, arrangement_file, bindings_file
        )
        content = report.model_dump_json(indent=2) + "\n"
        if destination is None:
            typer.echo(content, nl=False)
        else:
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            typer.echo(f"Read-only assessment complete; writer blocked; report: {destination}")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)


@app.command("plan-build")
def plan_build(
    arrangement_file: Path,
    inspection_file: Annotated[
        Path, typer.Option("--inspection", help="Saved read-only template inspection")
    ],
    bindings_file: Annotated[
        Path, typer.Option("--bindings", help="Explicit source-to-template YAML")
    ],
    backend_directory: Annotated[
        Path, typer.Option("--backend-dir", help="Current isolated backend to verify")
    ],
    output: Annotated[Path | None, typer.Option("--output", help="New dry-run JSON plan")] = None,
) -> None:
    """Plan exact bindings/timing without running a backend or writing FLP."""
    try:
        destination = None
        if output is not None:
            destination = output.resolve()
            if (
                output.exists()
                or output.is_symlink()
                or any(":" in part for part in output.parts if part != output.anchor)
                or destination.suffix.lower() != ".json"
                or destination.is_relative_to(backend_directory.resolve())
                or not destination.parent.is_dir()
            ):
                raise UnsafePathError(
                    "Plan must be a new .json outside the backend with an existing parent; "
                    "alternate streams are forbidden"
                )
        plan = plan_build_files(arrangement_file, inspection_file, bindings_file, backend_directory)
        content = plan.model_dump_json(indent=2) + "\n"
        if destination is None:
            typer.echo(content, nl=False)
        else:
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            typer.echo(f"Dry-run {plan.status}; execution disabled; plan: {destination}")
    except (Suno2FLPError, OSError, RuntimeError, ValueError) as exc:
        _fail(exc)
        return
    if plan.status == "blocked":
        raise typer.Exit(1)


@app.command("plan-flp-write")
def plan_flp_write(
    arrangement_file: Path,
    inspection_file: Annotated[Path, typer.Option("--inspection")],
    bindings_file: Annotated[Path, typer.Option("--bindings")],
    policy_file: Annotated[Path, typer.Option("--policy")],
    backend_directory: Annotated[Path, typer.Option("--backend-dir")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Prepare a distinct restricted-writer intent; creates only optional new JSON."""
    try:
        destination = None
        if output is not None:
            destination = output.resolve()
            if (
                output.exists()
                or output.is_symlink()
                or destination.suffix.lower() != ".json"
                or destination.is_relative_to(backend_directory.resolve())
                or not destination.parent.is_dir()
                or any(":" in p for p in output.parts if p != output.anchor)
            ):
                raise UnsafePathError(
                    "Write plan must be a new .json outside backend with an existing parent"
                )
        result = plan_fl26_files(
            arrangement_file, inspection_file, bindings_file, policy_file, backend_directory
        )
        content = result.model_dump_json(indent=2) + "\n"
        if destination is None:
            typer.echo(content, nl=False)
        else:
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            typer.echo(f"Restricted write intent: {result.intent.status}; report: {destination}")
    except (Suno2FLPError, OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        _fail(exc)
        return
    if result.intent.status == "blocked":
        raise typer.Exit(1)


@app.command("build-flp")
def build_flp(
    arrangement_file: Path,
    inspection_file: Annotated[Path, typer.Option("--inspection")],
    bindings_file: Annotated[Path, typer.Option("--bindings")],
    policy_file: Annotated[Path, typer.Option("--policy")],
    backend_directory: Annotated[Path, typer.Option("--backend-dir")],
    output_directory: Annotated[Path, typer.Option("--output-dir")],
) -> None:
    """Build a new restricted FL26 bundle; unresolved evidence blocks before staging."""
    try:
        result = build_fl26_files(
            arrangement_file,
            inspection_file,
            bindings_file,
            policy_file,
            backend_directory,
            output_directory,
        )
        typer.echo(
            f"Created structurally verified {result.output_path}; FL Studio playback unverified"
        )
    except (Suno2FLPError, OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        _fail(exc)


@app.command("verify-flp-bundle")
def verify_flp_bundle(
    bundle_directory: Path,
    backend_directory: Annotated[Path, typer.Option("--backend-dir")],
) -> None:
    """Read-only revalidation of a saved bundle and current originals; host unverified."""
    try:
        proof = verify_fl26_bundle_files(bundle_directory, backend_directory)
        typer.echo(proof.model_dump_json(indent=2) + "\n", nl=False)
    except (Suno2FLPError, OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        _fail(exc)


@app.command("init-project")
def init_project(
    project_name: str,
    directory: Annotated[
        Path, typer.Option("--directory", help="Existing parent directory")
    ] = Path("."),
) -> None:
    """Create a new workspace, refusing an existing destination."""
    try:
        typer.echo(f"Created {create_project(directory, project_name)}")
    except (Suno2FLPError, OSError) as exc:
        _fail(exc)


@app.command()
def inspect(
    input_directory: Path,
    manifest: Annotated[
        Path | None, typer.Option("--manifest", help="New JSON path outside input tree")
    ] = None,
) -> None:
    """Discover MIDI/WAV metadata; print JSON or exclusively create a manifest."""
    try:
        result = LocalAssetImporter().discover(input_directory)
        content = result.model_dump_json(indent=2) + "\n"
        if manifest is None:
            typer.echo(content, nl=False)
        else:
            destination = manifest.resolve()
            if destination.is_relative_to(input_directory.resolve()):
                raise UnsafePathError("Manifest destination must be outside the input tree")
            if destination.suffix.lower() != ".json":
                raise UnsafePathError("Manifest destination must use .json")
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            typer.echo(f"Inspected {len(result.assets)} assets; manifest: {destination}")
        if any(d.severity == "error" for d in result.diagnostics):
            raise typer.Exit(1)
    except (Suno2FLPError, OSError, RuntimeError) as exc:
        _fail(exc)


@app.command()
def import_midi(
    midi_file: Path,
    output: Annotated[
        Path | None, typer.Option("--output", help="New JSON path for track-aware MIDI data")
    ] = None,
) -> None:
    """Read tracks, original ticks, tempo and meter without modifying MIDI."""
    try:
        result = MidiFileImporter().import_file(midi_file)
        content = result.model_dump_json(indent=2) + "\n"
        if output is None:
            typer.echo(content, nl=False)
        else:
            destination = output.resolve()
            if destination.suffix.lower() != ".json":
                raise UnsafePathError("MIDI import destination must use .json")
            if destination == midi_file.resolve():
                raise UnsafePathError("MIDI import destination must differ from source")
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            typer.echo(f"Imported {len(result.tracks)} tracks; JSON: {destination}")
        if any(d.severity == "error" for d in result.diagnostics):
            raise typer.Exit(1)
    except (Suno2FLPError, OSError, RuntimeError) as exc:
        _fail(exc)


@app.command()
def clean_midi(
    midi_file: Path,
    output: Annotated[
        Path | None, typer.Option("--output", help="New JSON path for derived notes and audit")
    ] = None,
    config: Annotated[
        Path | None, typer.Option("--config", help="Project YAML preferences")
    ] = None,
    remove_duplicates: Annotated[
        bool | None, typer.Option("--remove-duplicates/--keep-duplicates")
    ] = None,
    min_duration_ticks: Annotated[
        int | None,
        typer.Option("--min-duration-ticks", min=0, help="0 disables short-note filtering"),
    ] = None,
    quantize_grid_ticks: Annotated[
        int | None,
        typer.Option("--quantize-grid-ticks", min=1, help="Opt-in onset quantization grid"),
    ] = None,
    no_quantize: Annotated[
        bool, typer.Option("--no-quantize", help="Disable configured grid")
    ] = False,
) -> None:
    """Apply explicitly selected note cleanup; retain original events/timing in JSON."""
    try:
        preferences = load_config(config).midi if config is not None else MidiPreferences()
        settings = preferences.model_dump()
        if remove_duplicates is not None:
            settings["remove_duplicates"] = remove_duplicates
        if min_duration_ticks is not None:
            settings["min_duration_ticks"] = min_duration_ticks
        if no_quantize and quantize_grid_ticks is not None:
            raise MidiProcessingError("Choose a quantization grid or --no-quantize, not both")
        if quantize_grid_ticks is not None:
            settings.update(quantize=True, quantize_grid_ticks=quantize_grid_ticks)
        if no_quantize:
            settings.update(quantize=False, quantize_grid_ticks=None)
        preferences = MidiPreferences.model_validate(settings)
        result = DeterministicMidiProcessor().clean(
            MidiFileImporter().import_file(midi_file), preferences
        )
        content = result.model_dump_json(indent=2) + "\n"
        if output is None:
            typer.echo(content, nl=False)
        else:
            destination = output.resolve()
            if destination.suffix.lower() != ".json" or destination == midi_file.resolve():
                raise UnsafePathError(
                    "Cleanup output must be a new .json file distinct from source"
                )
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            changes = len(result.cleanup.changes) if result.cleanup else 0
            typer.echo(
                f"Processed {len(result.tracks)} tracks; {changes} changes; JSON: {destination}"
            )
    except (Suno2FLPError, OSError, RuntimeError, ValidationError) as exc:
        _fail(exc)


@app.command()
def arrange(
    inputs: Annotated[list[Path], typer.Argument(help="MIDI files or imported/cleaned MIDI JSON")],
    output: Annotated[
        Path | None, typer.Option("--output", help="New arrangement JSON path")
    ] = None,
    target_ppq: Annotated[int | None, typer.Option("--target-ppq", min=1)] = None,
    note_view: Annotated[str, typer.Option("--note-view", help="imported or active")] = "imported",
    timing_source: Annotated[
        int | None,
        typer.Option("--timing-source", min=0, help="Explicit zero-based timing authority"),
    ] = None,
    allow_rounding: Annotated[
        bool, typer.Option("--allow-rounding", help="Allow reported nearest-tick PPQ approximation")
    ] = False,
    title: Annotated[str, typer.Option("--title")] = "Untitled",
    instruments: Annotated[
        Path | None, typer.Option("--instruments", help="Explicit instrument-role mapping YAML")
    ] = None,
) -> None:
    """Build a faithful beat-aligned arrangement with source snapshots and explicit timing rules."""
    try:
        options = ArrangementOptions.model_validate(
            {
                "target_ppq": target_ppq,
                "note_view": note_view,
                "timing_source": timing_source,
                "ppq_rounding": "nearest" if allow_rounding else "error",
            }
        )
        sources: list[ProcessedMidi] = []
        for path in inputs:
            if path.suffix.lower() in {".mid", ".midi"}:
                sources.append(MidiFileImporter().import_file(path))
            elif path.suffix.lower() == ".json":
                sources.append(
                    ProcessedMidi.model_validate_json(path.read_text(encoding="utf-8-sig"))
                )
            else:
                raise ArrangementError(f"Expected MIDI or imported/cleaned JSON input: {path}")
        result = FaithfulArrangementEngine().arrange(
            sources, MusicalMetadata(title=title), "faithful", options=options
        )
        if instruments is not None:
            result = ExplicitInstrumentMapper().apply(result, load_instrument_mapping(instruments))
        content = result.model_dump_json(indent=2) + "\n"
        if output is None:
            typer.echo(content, nl=False)
        else:
            destination = output.resolve()
            if destination.suffix.lower() != ".json" or destination in [
                p.resolve() for p in inputs
            ]:
                raise UnsafePathError(
                    "Arrangement output must be a new .json file distinct from inputs"
                )
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            typer.echo(
                f"Arranged {len(result.tracks)} tracks; PPQ {result.ticks_per_beat}: {destination}"
            )
    except (Suno2FLPError, OSError, RuntimeError, ValidationError, UnicodeError) as exc:
        _fail(exc)


@app.command()
def map_instruments(
    arrangement_file: Path,
    mapping: Annotated[Path, typer.Option("--mapping", help="Explicit role mapping YAML")],
    output: Annotated[
        Path | None, typer.Option("--output", help="New mapped arrangement JSON")
    ] = None,
) -> None:
    """Annotate source channels with explicit roles; no plugins or routing are applied."""
    try:
        original = Arrangement.model_validate_json(arrangement_file.read_text(encoding="utf-8-sig"))
        result = ExplicitInstrumentMapper().apply(original, load_instrument_mapping(mapping))
        content = result.model_dump_json(indent=2) + "\n"
        if output is None:
            typer.echo(content, nl=False)
        else:
            destination = output.resolve()
            if destination.suffix.lower() != ".json" or destination in {
                arrangement_file.resolve(),
                mapping.resolve(),
            }:
                raise UnsafePathError("Mapped output must be a new .json file distinct from inputs")
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(content)
            count = len(result.instrument_mapping.matches) if result.instrument_mapping else 0
            typer.echo(f"Assigned roles to {count} source channels; JSON: {destination}")
    except (Suno2FLPError, OSError, RuntimeError, ValidationError, UnicodeError) as exc:
        _fail(exc)


@app.command()
def validate(project_directory: Path) -> None:
    """Validate configuration, required directories, and input asset metadata."""
    report = validate_project(project_directory)
    for diagnostic in report.diagnostics:
        location = f" ({diagnostic.path})" if diagnostic.path else ""
        typer.echo(f"{diagnostic.severity}: {diagnostic.code}{location}: {diagnostic.message}")
    typer.echo("Validation passed" if report.valid else "Validation failed")
    if not report.valid:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
