"""Read-only current-input reconstruction and independent saved-bundle verification."""

import os
import stat
from pathlib import Path

from suno2flp.core.errors import FlpWriteError
from suno2flp.core.writer_models import Fl26Verification, WriterBundleProvenance
from suno2flp.flp_builder.fl26_verify import verify_fl26_output
from suno2flp.flp_builder.writer_files import _check_current, plan_fl26_files
from suno2flp.flp_builder.writer_io import reject_aliases

BUNDLE_NAMES = {"project.flp", "provenance.json", "verification.json"}
FileIdentity = tuple[int, int, int, int]
BundleSnapshot = tuple[FileIdentity, dict[str, tuple[FileIdentity, bytes]]]


def _identity(info: os.stat_result) -> FileIdentity:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _bundle_snapshot(directory: Path) -> BundleSnapshot:
    reject_aliases(directory)
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode) or {p.name for p in directory.iterdir()} != BUNDLE_NAMES:
        raise FlpWriteError("writer_bundle_invalid", "Expected exactly three bundle files")
    files = {}
    for name in sorted(BUNDLE_NAMES):
        path = reject_aliases(directory / name)
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise FlpWriteError("writer_bundle_invalid", "Bundle members must be regular files")
        raw = path.read_bytes()
        if _identity(before) != _identity(path.stat()):
            raise FlpWriteError("writer_bundle_changed", "Bundle member changed while reading")
        files[name] = (_identity(before), raw)
    if _identity(info) != _identity(directory.stat()):
        raise FlpWriteError("writer_bundle_changed", "Bundle directory changed while reading")
    return _identity(info), files


def verify_fl26_bundle_files(bundle_directory: Path, backend_directory: Path) -> Fl26Verification:
    """Rebuild intent from current originals, then verify bytes without writing/launching."""
    directory = reject_aliases(bundle_directory.absolute())
    backend = reject_aliases(backend_directory.absolute())
    snapshot = _bundle_snapshot(directory)
    members = snapshot[1]
    provenance = WriterBundleProvenance.model_validate_json(members["provenance.json"][1])
    recorded = Fl26Verification.model_validate_json(members["verification.json"][1])
    for name, model in (("provenance.json", provenance), ("verification.json", recorded)):
        if model.model_dump_json(indent=2).encode() + b"\n" != members[name][1]:
            raise FlpWriteError(
                "writer_bundle_invalid", "Bundle JSON must retain its canonical writer bytes"
            )
    if recorded != provenance.verification:
        raise FlpWriteError("writer_bundle_invalid", "Bundle verification sidecars disagree")
    try:
        _check_current(provenance.input_files, provenance.intent.inspection, backend)
        inputs = {}
        for kind in ("arrangement", "inspection", "bindings", "policy", "template"):
            matches = [f.path for f in provenance.input_files if f.kind == kind]
            if len(matches) != 1:
                raise FlpWriteError("writer_bundle_invalid", "Bundle input roles must be unique")
            inputs[kind] = matches[0]
        preparation = plan_fl26_files(
            inputs["arrangement"],
            inputs["inspection"],
            inputs["bindings"],
            inputs["policy"],
            backend,
        )
        if (
            preparation.intent != provenance.intent
            or preparation.input_files != provenance.input_files
        ):
            raise FlpWriteError(
                "writer_bundle_invalid", "Bundle provenance differs from current reconstruction"
            )
        proof = verify_fl26_output(
            inputs["template"].read_bytes(), members["project.flp"][1], preparation.intent
        )
        if proof != recorded:
            raise FlpWriteError("writer_bundle_invalid", "Independent bundle proof differs")
        return proof
    finally:
        _check_current(provenance.input_files, provenance.intent.inspection, backend)
        if snapshot != _bundle_snapshot(directory):
            raise FlpWriteError("writer_bundle_changed", "Bundle changed during verification")
