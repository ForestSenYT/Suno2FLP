"""Current-file readiness orchestration; reads only and never launches a process."""

import hashlib
from pathlib import Path

from suno2flp.core.assessment_models import TemplateReadinessReport
from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_config import load_template_bindings
from suno2flp.core.build_models import PlanInputFile
from suno2flp.core.errors import BuildPlanningError
from suno2flp.core.models import Arrangement
from suno2flp.flp_builder.assessment import assess_template
from suno2flp.flp_builder.planning_files import _verify_current


def assess_template_files(
    inspection_file: Path,
    backend_directory: Path,
    arrangement_file: Path | None = None,
    bindings_file: Path | None = None,
) -> TemplateReadinessReport:
    if (arrangement_file is None) != (bindings_file is None):
        raise BuildPlanningError(
            "assessment_inputs_incomplete", "Arrangement and bindings must be supplied together"
        )
    inspection_raw = inspection_file.read_bytes()
    inspection = TemplateInspectionReport.model_validate_json(inspection_raw.decode("utf-8-sig"))
    _verify_current(inspection, backend_directory)
    path = inspection.template_path
    before = path.stat().st_mtime_ns
    inputs = [
        PlanInputFile(
            kind="inspection",
            path=inspection_file.resolve(),
            sha256=hashlib.sha256(inspection_raw).hexdigest(),
        )
    ]
    try:
        arrangement = bindings = None
        if arrangement_file is not None and bindings_file is not None:
            raw = arrangement_file.read_bytes()
            arrangement = Arrangement.model_validate_json(raw.decode("utf-8-sig"))
            bindings = load_template_bindings(bindings_file)
            assert bindings.source_path is not None and bindings.source_sha256 is not None
            inputs.extend(
                [
                    PlanInputFile(
                        kind="arrangement",
                        path=arrangement_file.resolve(),
                        sha256=hashlib.sha256(raw).hexdigest(),
                    ),
                    PlanInputFile(
                        kind="bindings", path=bindings.source_path, sha256=bindings.source_sha256
                    ),
                ]
            )
        result = assess_template(path.read_bytes(), inspection, arrangement, bindings)
    finally:
        _verify_current(inspection, backend_directory)
        if path.stat().st_mtime_ns != before:
            raise BuildPlanningError(
                "template_timestamp_changed", "Template modification time changed during assessment"
            )
    result.input_files = inputs
    result.template_mtime_ns_before = before
    result.template_mtime_ns_after = path.stat().st_mtime_ns
    return result
