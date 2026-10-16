"""Current-file restricted writing, guarded staging and verified exclusive bundles."""

import tempfile
from pathlib import Path

import yaml

from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_models import TemplateBindingConfig, TemplateBindingDocument
from suno2flp.core.config import MidiPreferences, UniqueKeyLoader
from suno2flp.core.errors import FlpWriteError, Suno2FLPError
from suno2flp.core.models import Arrangement, BuildResult, Diagnostic
from suno2flp.core.writer_models import (
    Fl26WritePreparation,
    Fl26WriterPolicy,
    WriterBundleProvenance,
    WriterInputFile,
    WriterPolicyDocument,
)
from suno2flp.flp_builder.fl26_codec import encode_fl26
from suno2flp.flp_builder.fl26_verify import verify_fl26_output
from suno2flp.flp_builder.planning_files import _verify_current
from suno2flp.flp_builder.writer_intent import prepare_fl26_write
from suno2flp.flp_builder.writer_io import (
    capture_file,
    guard_output,
    publish_bundle,
    reject_aliases,
    require_windows,
    verify_input_files,
    write_new,
)
from suno2flp.importer import MidiFileImporter
from suno2flp.midi_processor import DeterministicMidiProcessor


def _check_current(
    files: list[WriterInputFile], inspection: TemplateInspectionReport, backend: Path
) -> None:
    verify_input_files(files)
    _verify_current(inspection, backend)


def plan_fl26_files(
    arrangement_file: Path,
    inspection_file: Path,
    bindings_file: Path,
    policy_file: Path,
    backend_directory: Path,
) -> Fl26WritePreparation:
    files = []
    captured = {}
    for kind, path in (
        ("arrangement", arrangement_file),
        ("inspection", inspection_file),
        ("bindings", bindings_file),
        ("policy", policy_file),
    ):
        evidence, raw = capture_file(path.absolute(), kind)
        files.append(evidence)
        captured[kind] = raw
    arrangement = Arrangement.model_validate_json(captured["arrangement"].decode("utf-8-sig"))
    inspection = TemplateInspectionReport.model_validate_json(
        captured["inspection"].decode("utf-8-sig")
    )
    backend_directory = reject_aliases(backend_directory.absolute())
    _verify_current(inspection, backend_directory)
    try:
        evidence, template_raw = capture_file(inspection.template_path, "template")
        files.append(evidence)
        config = TemplateBindingConfig.model_validate(
            yaml.load(captured["bindings"].decode("utf-8-sig"), Loader=UniqueKeyLoader)
        )
        bindings = TemplateBindingDocument(
            config=config, source_path=files[2].path, source_sha256=files[2].sha256
        )
        policy_config = Fl26WriterPolicy.model_validate(
            yaml.load(captured["policy"].decode("utf-8-sig"), Loader=UniqueKeyLoader)
        )
        policy = WriterPolicyDocument(
            config=policy_config, source_path=files[3].path, source_sha256=files[3].sha256
        )
        for source in arrangement.sources:
            evidence, _ = capture_file(source.midi.source, "source_midi")
            files.append(evidence)
            if evidence.sha256 != source.midi.source_sha256:
                raise FlpWriteError(
                    "writer_source_stale", "Source MIDI bytes differ from arrangement provenance"
                )
            imported = MidiFileImporter().import_file(source.midi.source)
            if source.midi.cleanup is not None:
                imported = DeterministicMidiProcessor().clean(
                    imported,
                    MidiPreferences.model_validate(source.midi.cleanup.options.model_dump()),
                )
            if imported != source.midi:
                raise FlpWriteError(
                    "writer_source_snapshot_invalid",
                    "Source snapshot differs from reimport/replayed cleanup",
                )
        intent = prepare_fl26_write(template_raw, arrangement, inspection, bindings, policy)
        return Fl26WritePreparation(intent=intent, input_files=files)
    finally:
        _check_current(files, inspection, backend_directory)


def _bundle_bytes(
    directory: Path,
    original: bytes,
    preparation: Fl26WritePreparation,
    provenance_raw: bytes,
    verification_raw: bytes,
) -> None:
    reject_aliases(directory)
    if {p.name for p in directory.iterdir()} != {
        "project.flp",
        "provenance.json",
        "verification.json",
    }:
        raise FlpWriteError("writer_bundle_invalid", "Bundle file inventory changed")
    for name in ("project.flp", "provenance.json", "verification.json"):
        reject_aliases(directory / name)
    if (directory / "provenance.json").read_bytes() != provenance_raw or (
        directory / "verification.json"
    ).read_bytes() != verification_raw:
        raise FlpWriteError("writer_bundle_invalid", "Sidecar/verification bytes changed")
    proof = verify_fl26_output(
        original, (directory / "project.flp").read_bytes(), preparation.intent
    )
    if proof.model_dump_json(indent=2).encode() + b"\n" != verification_raw:
        raise FlpWriteError("writer_bundle_invalid", "Output verification differs")


def build_fl26_files(
    arrangement_file: Path,
    inspection_file: Path,
    bindings_file: Path,
    policy_file: Path,
    backend_directory: Path,
    output_directory: Path,
) -> BuildResult:
    preparation = plan_fl26_files(
        arrangement_file, inspection_file, bindings_file, policy_file, backend_directory
    )
    intent = preparation.intent
    protected_files = [f.path for f in preparation.input_files]
    protected_trees = [
        backend_directory,
        intent.inspection.template_path.parent,
        *[f.path.parent for f in preparation.input_files if f.kind == "source_midi"],
    ]
    destination = guard_output(output_directory, protected_trees, protected_files)
    if intent.status != "ready":
        raise FlpWriteError(
            "writer_blocked", "; ".join(d.code for d in intent.diagnostics if d.severity == "error")
        )
    require_windows()
    stage = None
    published = False
    try:
        _check_current(preparation.input_files, intent.inspection, backend_directory)
        original = intent.inspection.template_path.read_bytes()
        output = encode_fl26(original, intent)
        proof = verify_fl26_output(original, output, intent)
        provenance = WriterBundleProvenance(
            intent=intent, input_files=preparation.input_files, verification=proof
        )
        provenance_raw = provenance.model_dump_json(indent=2).encode() + b"\n"
        verification_raw = proof.model_dump_json(indent=2).encode() + b"\n"
        stage = Path(tempfile.mkdtemp(prefix=".suno2flp-stage-", dir=destination.parent))
        stage_identity = (stage.stat().st_dev, stage.stat().st_ino)
        write_new(stage / "project.flp", output)
        write_new(stage / "provenance.json", provenance_raw)
        write_new(stage / "verification.json", verification_raw)
        _bundle_bytes(stage, original, preparation, provenance_raw, verification_raw)
        if stage_identity != (stage.stat().st_dev, stage.stat().st_ino):
            raise FlpWriteError("writer_bundle_invalid", "Staging directory identity changed")
        _check_current(preparation.input_files, intent.inspection, backend_directory)
        guard_output(destination, protected_trees, protected_files)
        publish_bundle(stage, destination)
        published = True
        if stage_identity != (destination.stat().st_dev, destination.stat().st_ino):
            raise FlpWriteError("writer_bundle_invalid", "Published directory identity changed")
        _bundle_bytes(destination, original, preparation, provenance_raw, verification_raw)
        _check_current(preparation.input_files, intent.inspection, backend_directory)
        return BuildResult(
            output_path=destination / "project.flp",
            backend="native-fl26-restricted-v1",
            diagnostics=[
                Diagnostic(
                    code="host_compatibility_unverified",
                    severity="warning",
                    message="Structural round trip only; "
                    "no FL Studio open/readback/listen was performed",
                ),
                Diagnostic(
                    code="writer_reference_scope",
                    severity="info",
                    message=f"Reference kind: {intent.reference_kind}; "
                    "operator attestations are not automatic host verification",
                ),
            ],
        )
    except (OSError, RuntimeError, ValueError, Suno2FLPError) as exc:
        retained = destination if published else stage
        raise FlpWriteError("writer_failed", f"{exc}; retained new artifacts: {retained}") from exc
    finally:
        _check_current(preparation.input_files, intent.inspection, backend_directory)
