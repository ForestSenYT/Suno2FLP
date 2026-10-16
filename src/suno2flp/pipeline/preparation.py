"""Compose existing deterministic stages into an exclusively new evidence bundle."""

import json
import os
from pathlib import Path

from suno2flp.arrangement import ExplicitInstrumentMapper, FaithfulArrangementEngine
from suno2flp.core.config import load_config
from suno2flp.core.errors import OfflineError
from suno2flp.core.instrument_config import load_instrument_mapping
from suno2flp.core.models import ArrangementOptions, MusicalMetadata
from suno2flp.core.offline_files import capture_input, guarded_path, load_unique_json, verify_inputs
from suno2flp.core.offline_models import FileIdentity, PreparationRun
from suno2flp.importer import LocalAssetImporter, MidiFileImporter
from suno2flp.midi_processor import DeterministicMidiProcessor
from suno2flp.validator.arrangement import audit_arrangement


def _documents(
    project: Path,
    options: ArrangementOptions | None,
    mapping_file: Path | None,
) -> tuple[dict[str, bytes], list[FileIdentity], ArrangementOptions]:
    root = guarded_path(project)
    config_file, _ = capture_input(root / "project.yaml")
    inputs = [config_file]
    config = load_config(config_file.path)
    if config.arrangement_mode != "faithful" or any(
        value != "none" for value in config.integrations.model_dump().values()
    ):
        raise OfflineError(
            "preparation_config_unsupported", "Faithful mode and disabled integrations required"
        )
    effective = ArrangementOptions.model_validate(
        (options or ArrangementOptions(note_view="active")).model_dump()
    )
    if effective.ppq_rounding != "error":
        raise OfflineError(
            "preparation_rounding_forbidden", "Preparation requires exact PPQ conversion"
        )
    for relative in [
        *config.input_directories,
        config.intermediate_directory,
        config.output_directory,
    ]:
        directory = guarded_path(root / relative)
        if not directory.is_dir() or not directory.is_relative_to(root):
            raise OfflineError(
                "preparation_directory_invalid", f"Missing/escaping directory: {directory}"
            )
    if config.template_path is not None:
        template_file, _ = capture_input(root / config.template_path)
        inputs.append(
            template_file
        )  # Identity only: no template parse, edit or backend invocation.
    manifests = []
    original_imports = []
    selected_imports = []
    for directory in config.input_directories:
        manifest = LocalAssetImporter().discover(root / directory)
        manifests.append(manifest.model_dump(mode="json"))
        if any(d.severity == "error" for d in manifest.diagnostics):
            raise OfflineError(
                "preparation_assets_invalid", "Resolve discovery errors before preparation"
            )
        for asset in manifest.assets:
            identity, _ = capture_input(manifest.root / asset.path)
            inputs.append(identity)
            if asset.kind == "midi":
                original = MidiFileImporter().import_file(identity.path)
                if original.source_sha256 != identity.sha256:
                    raise OfflineError("offline_input_changed", "MIDI changed during import")
                original_imports.append(original)
                selected = original
                if (
                    config.midi.remove_duplicates
                    or config.midi.min_duration_ticks
                    or config.midi.quantize
                ):
                    selected = DeterministicMidiProcessor().clean(original, config.midi)
                selected_imports.append(selected)
    if not selected_imports:
        raise OfflineError(
            "preparation_midi_missing", "At least one valid official MIDI is required"
        )
    arrangement = FaithfulArrangementEngine().arrange(
        selected_imports,
        MusicalMetadata(title=config.name),
        options=effective,
    )
    if mapping_file is not None:
        mapping_identity, _ = capture_input(mapping_file)
        inputs.append(mapping_identity)
        arrangement = ExplicitInstrumentMapper().apply(
            arrangement,
            load_instrument_mapping(mapping_identity.path),
        )
    quality = audit_arrangement(arrangement, original_imports)
    if not quality.valid:
        raise OfflineError("preparation_quality_failed", "Current-source arrangement replay failed")
    documents = {
        "assets.json": json.dumps(manifests, ensure_ascii=False, indent=2).encode() + b"\n",
    }
    for index, selected in enumerate(selected_imports):
        documents[f"midi-{index:04d}.json"] = selected.model_dump_json(indent=2).encode() + b"\n"
    documents["arrangement.json"] = arrangement.model_dump_json(indent=2).encode() + b"\n"
    documents["quality.json"] = quality.model_dump_json(indent=2).encode() + b"\n"
    verify_inputs(inputs)
    return documents, inputs, effective


def _destination(project: Path, destination: Path) -> Path:
    root = guarded_path(project)
    config = load_config(root / "project.yaml")
    intermediate = guarded_path(root / config.intermediate_directory)
    target = guarded_path(destination)
    if (
        target == intermediate
        or not target.is_relative_to(intermediate)
        or not target.parent.is_dir()
        or any((parent / "backend.json").exists() for parent in target.parents)
    ):
        raise OfflineError(
            "preparation_output_unsafe", "Use a new directory beneath project intermediate"
        )
    return target


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def prepare_project(
    project: Path,
    destination: Path,
    *,
    options: ArrangementOptions | None = None,
    mapping_file: Path | None = None,
) -> PreparationRun:
    target = _destination(project, destination)
    if target.exists():
        raise OfflineError("preparation_output_exists", "Existing output cannot be reused")
    documents, inputs, effective = _documents(project, options, mapping_file)
    # Recheck destination rules after discovery/config capture and before creating anything.
    if _destination(project, destination) != target:
        raise OfflineError("offline_input_changed", "Output configuration changed")
    verify_inputs(inputs)
    target.mkdir(exist_ok=False)
    artifacts = {}
    for name, raw in documents.items():
        path = target / name
        _write_file(path, raw)
        identity, saved = capture_input(path)
        if saved != raw:
            raise OfflineError(
                "preparation_artifact_changed", "New artifact changed during writing"
            )
        artifacts[name] = identity
    verify_inputs(inputs)
    result = PreparationRun(
        project_root=guarded_path(project),
        destination=target,
        options=effective,
        mapping_file=guarded_path(mapping_file) if mapping_file is not None else None,
        input_files=inputs,
        artifacts=artifacts,
    )
    # Completion marker is last; interrupted/failed directories retain no successful run.json.
    _write_file(target / "run.json", result.model_dump_json(indent=2).encode() + b"\n")
    verify_preparation(target / "run.json")
    return result


def verify_preparation(run_file: Path) -> PreparationRun:
    identity, raw = capture_input(run_file)
    run = PreparationRun.model_validate(load_unique_json(raw))
    directory = guarded_path(run.destination)
    if (
        identity.path != directory / "run.json"
        or _destination(run.project_root, directory) != directory
    ):
        raise OfflineError("preparation_manifest_invalid", "Manifest/destination identity mismatch")
    if {path.name for path in directory.iterdir()} != {*run.artifacts, "run.json"}:
        raise OfflineError("preparation_inventory_changed", "Missing or unlisted output artifacts")
    documents, current_inputs, effective = _documents(
        run.project_root, run.options, run.mapping_file
    )
    if (
        current_inputs != run.input_files
        or effective != run.options
        or set(documents) != set(run.artifacts)
    ):
        raise OfflineError(
            "preparation_inputs_changed", "Current source/configuration/artifact set differs"
        )
    for name, reference in run.artifacts.items():
        if reference.path != directory / name or Path(name).name != name:
            raise OfflineError(
                "preparation_manifest_invalid", "Artifact must be a direct bundle child"
            )
        current, data = capture_input(reference.path)
        if current != reference or data != documents[name]:
            raise OfflineError(
                "preparation_artifact_changed", f"Artifact differs from current replay: {name}"
            )
    verify_inputs([identity, *run.input_files, *run.artifacts.values()])
    return run
