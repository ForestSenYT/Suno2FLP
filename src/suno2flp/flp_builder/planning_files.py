"""Explicit file orchestration for dry-run planning; never invokes the backend."""

import hashlib
from pathlib import Path

from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_config import load_template_bindings
from suno2flp.core.build_models import DryRunBuildPlan, PlanInputFile
from suno2flp.core.errors import BuildPlanningError
from suno2flp.core.models import Arrangement
from suno2flp.flp_builder.planning import DryRunBuildPlanner
from suno2flp.integrations.music2daw_provision import verify_backend
from suno2flp.integrations.template_inventory import scan_template_inventory


def _verify_current(inspection: TemplateInspectionReport, backend_directory: Path) -> None:
    record, fingerprint = verify_backend(backend_directory)
    if fingerprint != inspection.backend_manifest_sha256 or record != inspection.backend:
        raise BuildPlanningError(
            "backend_snapshot_mismatch", "Current backend differs from inspection record"
        )
    try:
        path = inspection.template_path
        raw = path.read_bytes()
        if (
            hashlib.sha256(raw).hexdigest() != inspection.template_sha256_after
            or len(raw) != inspection.size_bytes
        ):
            raise BuildPlanningError(
                "template_snapshot_stale", "Current template differs from inspection snapshot"
            )
        if (
            inspection.inventory is not None
            and scan_template_inventory(raw) != inspection.inventory
        ):
            raise BuildPlanningError(
                "template_inventory_stale",
                "Saved inventory differs from a fresh scan of current template bytes",
            )
    except OSError as exc:
        raise BuildPlanningError("template_snapshot_stale", str(exc)) from exc


def plan_build_files(
    arrangement_file: Path, inspection_file: Path, bindings_file: Path, backend_directory: Path
) -> DryRunBuildPlan:
    arrangement_raw = arrangement_file.read_bytes()
    inspection_raw = inspection_file.read_bytes()
    arrangement = Arrangement.model_validate_json(arrangement_raw.decode("utf-8-sig"))
    inspection = TemplateInspectionReport.model_validate_json(inspection_raw.decode("utf-8-sig"))
    bindings = load_template_bindings(bindings_file)
    _verify_current(inspection, backend_directory)
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert bindings.source_sha256 is not None and bindings.source_path is not None
    plan.input_files = [
        PlanInputFile(
            kind="arrangement",
            path=arrangement_file.resolve(),
            sha256=hashlib.sha256(arrangement_raw).hexdigest(),
        ),
        PlanInputFile(
            kind="inspection",
            path=inspection_file.resolve(),
            sha256=hashlib.sha256(inspection_raw).hexdigest(),
        ),
        PlanInputFile(kind="bindings", path=bindings.source_path, sha256=bindings.source_sha256),
    ]
    _verify_current(inspection, backend_directory)
    return plan
