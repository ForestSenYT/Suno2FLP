"""Validate the existing faithful reconstruction contract without accessing files."""

from suno2flp.arrangement import ExplicitInstrumentMapper, FaithfulArrangementEngine
from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_models import TemplateBindingDocument
from suno2flp.core.errors import BuildPlanningError, Suno2FLPError
from suno2flp.core.models import Arrangement
from suno2flp.core.template_summary import compare_backend_summary


def validate_snapshots(
    arrangement: Arrangement,
    inspection: TemplateInspectionReport,
    bindings: TemplateBindingDocument,
) -> None:
    if (
        arrangement.mode != "faithful"
        or not arrangement.sources
        or arrangement.build_options is None
    ):
        raise BuildPlanningError(
            "arrangement_provenance_invalid",
            "Recorded faithful source views and build options are required",
        )
    if any(d.severity == "error" for d in [*arrangement.diagnostics, *inspection.diagnostics]):
        raise BuildPlanningError("input_errors", "Resolve input errors before planning")
    try:
        reconstructed = FaithfulArrangementEngine().arrange(
            [s.midi for s in arrangement.sources],
            arrangement.metadata,
            "faithful",
            options=arrangement.build_options,
        )
        if arrangement.instrument_mapping is not None:
            reconstructed = ExplicitInstrumentMapper().apply(
                reconstructed, arrangement.instrument_mapping.document
            )
    except Suno2FLPError as exc:
        raise BuildPlanningError("arrangement_provenance_invalid", str(exc)) from exc
    expected_tracks = [t.model_dump(exclude={"instrument_hint"}) for t in reconstructed.tracks]
    actual_tracks = [t.model_dump(exclude={"instrument_hint"}) for t in arrangement.tracks]
    if (
        reconstructed.sources != arrangement.sources
        or expected_tracks != actual_tracks
        or reconstructed.tempo_map != arrangement.tempo_map
        or reconstructed.meter_map != arrangement.meter_map
        or reconstructed.ticks_per_beat != arrangement.ticks_per_beat
        or reconstructed.instrument_mapping != arrangement.instrument_mapping
    ):
        raise BuildPlanningError(
            "arrangement_provenance_invalid",
            "Arrangement differs from recorded source views/options/role mapping",
        )
    validate_inspection(inspection)
    if (
        bindings.config.template_sha256 != inspection.template_sha256_after
        or bindings.config.backend_revision != inspection.backend.revision
    ):
        raise BuildPlanningError(
            "binding_identity_mismatch",
            "Bindings must identify this exact template hash and backend pin",
        )


def validate_inspection(inspection: TemplateInspectionReport) -> None:
    """Validate internal inspection provenance independently of optional music inputs."""
    if (
        inspection.template_sha256_before != inspection.template_sha256_after
        or inspection.header.ppq != inspection.project.ppq
        or inspection.header.channel_count != len(inspection.project.channels)
        or inspection.template_path != inspection.project.source_path
    ):
        raise BuildPlanningError(
            "inspection_inconsistent", "Inspection hash, path or header evidence disagrees"
        )
    inventory = inspection.inventory
    if inventory is not None and (
        inventory.template_sha256 != inspection.template_sha256_after
        or inventory.size_bytes != inspection.size_bytes
        or inventory.ppq != inspection.header.ppq
        or inventory.channel_count != inspection.header.channel_count
    ):
        raise BuildPlanningError(
            "inspection_inconsistent",
            "Inventory and inspection identify different bytes or timing units",
        )
    if inspection.local_summary is not None:
        if inventory is None:
            raise BuildPlanningError(
                "inspection_inconsistent", "Local summary requires byte inventory"
            )
        local, status, mismatches = compare_backend_summary(inventory, inspection.project)
        if (
            local != inspection.local_summary
            or status != inspection.backend_summary_status
            or mismatches != inspection.backend_summary_mismatches
        ):
            raise BuildPlanningError(
                "inspection_inconsistent",
                "Recorded local/backend comparison differs from inventory evidence",
            )
    elif inspection.backend_summary_status != "unchecked" or inspection.backend_summary_mismatches:
        raise BuildPlanningError(
            "inspection_inconsistent", "Summary comparison requires retained local evidence"
        )
