"""Pure FL26 evidence assessment; unresolved semantics remain explicit writer gates."""

from typing import Literal

from suno2flp.core.assessment_models import (
    CompatibilityFinding,
    TemplateReadinessReport,
    WriterGate,
)
from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_models import TemplateBindingDocument
from suno2flp.core.errors import BuildPlanningError
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.fl26_fields import note_attribute_form, pattern_crop_observation
from suno2flp.core.models import Arrangement
from suno2flp.core.template_profiles import FL26_READ_PROFILE
from suno2flp.flp_builder._planning_provenance import validate_inspection
from suno2flp.flp_builder.assessment_bindings import check_local_bindings
from suno2flp.integrations.template_dependencies import dependency_evidence
from suno2flp.integrations.template_inventory import scan_template_inventory


def assess_template(
    raw: bytes,
    inspection: TemplateInspectionReport,
    arrangement: Arrangement | None = None,
    bindings: TemplateBindingDocument | None = None,
) -> TemplateReadinessReport:
    if (arrangement is None) != (bindings is None):
        raise BuildPlanningError(
            "assessment_inputs_incomplete", "Arrangement and bindings must be supplied together"
        )
    inspection = TemplateInspectionReport.model_validate(inspection.model_dump())
    inventory = inspection.inventory
    if inventory is None or inventory.profile_id != FL26_READ_PROFILE.identifier:
        raise BuildPlanningError(
            "assessment_profile_unsupported", "Refresh exact FL26 26.1.7.5654 inventory first"
        )
    if scan_template_inventory(raw) != inventory:
        raise BuildPlanningError(
            "template_inventory_stale", "Inventory differs from current template bytes"
        )
    validate_inspection(inspection)
    dependencies = dependency_evidence(raw, inventory)
    findings = []

    def finding(
        code: str,
        message: str,
        events: list[int] | None = None,
        notes: list[int] | None = None,
        clips: list[int] | None = None,
    ) -> None:
        findings.append(
            CompatibilityFinding(
                code=code,
                message=message,
                event_indices=events or [],
                note_indices=notes or [],
                clip_indices=clips or [],
            )
        )

    if inspection.backend_summary_status != "consistent":
        finding(
            "backend_summary_inconsistent"
            if inspection.backend_summary_status == "inconsistent"
            else "backend_summary_unchecked",
            "Backend evidence is not a trusted FL26 writer surface",
            sorted(
                {
                    i
                    for mismatch in inspection.backend_summary_mismatches
                    for i in mismatch.event_indices
                }
            ),
        )
    indices = [i for i, n in enumerate(inventory.notes) if n.length_ticks <= 0]
    if indices:
        finding(
            "note_duration_unresolved",
            "Nonpositive stored note lengths are retained; no MIDI duration inferred",
            sorted({inventory.notes[i].event_index for i in indices}),
            notes=indices,
        )
    indices = [
        i
        for i, n in enumerate(inventory.notes)
        if (
            n.flags
            or n.group
            or any(bytes.fromhex(n.raw_hex)[13:16])
            or any(bytes.fromhex(n.raw_hex)[22:24])
        )
        and note_attribute_form(n, inventory.profile_id) != "ordinary"
    ]
    if indices:
        finding(
            "note_attributes_unresolved",
            "Unobserved note attributes or slide forms remain unsupported for replacement",
            sorted({inventory.notes[i].event_index for i in indices}),
            notes=indices,
        )
    indices = [
        i
        for i, n in enumerate(inventory.notes)
        if note_attribute_form(n, inventory.profile_id) == "ordinary"
    ]
    if indices:
        finding(
            "ordinary_note_attributes_observed",
            "Exact positive Piano roll attribute form observed with Slide off: flags 0x4000, "
            "observed fine-pitch/release/pan and tail 8080; preservation only, "
            "not all flag semantics",
            sorted({inventory.notes[i].event_index for i in indices}),
            notes=indices,
        )
    for i, clip in enumerate(inventory.clips):
        observed = pattern_crop_observation(clip, inventory.profile_id)
        if observed is not None:
            finding(
                "pattern_crop_default_observed"
                if observed.form == "default_sentinel"
                else "pattern_crop_ticks_observed",
                "Observed untrimmed Pattern form: paired -1 fields with flags 0x8040; "
                "no concrete endpoints or safe resize behavior inferred"
                if observed.form == "default_sentinel"
                else f"Observed Pattern endpoints {observed.start_ticks}..{observed.end_ticks} "
                "in template ticks with flags 0x40; crop editing remains blocked",
                [clip.event_index],
                clips=[i],
            )
    indices = [
        i
        for i, c in enumerate(inventory.clips)
        if (c.start_offset.value != 0 or c.end_offset.value != 0)
        and pattern_crop_observation(c, inventory.profile_id) is None
    ]
    if indices:
        finding(
            "crop_semantics_unresolved",
            "Crop bytes outside exact observed Pattern forms remain unresolved; "
            "legacy float projections are not assumed to be timing units",
            sorted({inventory.clips[i].event_index for i in indices}),
            clips=indices,
        )
    if inventory.clips:
        finding(
            "clip_extension_unresolved",
            "All eight extension bytes remain opaque, including all-zero values",
            sorted({c.event_index for c in inventory.clips}),
            clips=list(range(len(inventory.clips))),
        )
    events = [e.event_index for e in inventory.events if e.event_id == 172]
    if events:
        finding(
            "event_172_semantics_unresolved",
            "Three-byte framing is assessed; the payload's semantic meaning is not",
            events,
        )
    if inventory.automation:
        finding(
            "automation_semantics_unresolved",
            "Retained automation is not approved for editing or clearing",
            [a.event_index for a in inventory.automation],
        )
    if inventory.coverage != "decoded":
        finding(
            "inventory_coverage_incomplete",
            "Selected-family coverage does not establish complete event semantics",
            sorted({d.event_index for d in inventory.diagnostics if d.event_index is not None}),
        )
    finding(
        "dependencies_unverified",
        "Declarations do not establish plugin versions, resolved samples, "
        "installation, edition or rights",
        [d.event_index for d in dependencies],
    )
    check = None
    if arrangement is not None and bindings is not None:
        check = check_local_bindings(
            Arrangement.model_validate(arrangement.model_dump()),
            inspection,
            TemplateBindingDocument.model_validate(bindings.model_dump()),
        )
    gate_specs: list[tuple[str, Literal["blocked", "unverified"], str]] = [
        (
            "writer_implementation",
            "blocked",
            "This read-only report contains no executable writer policy or edit intent",
        ),
        (
            "backend_fl26_support",
            "blocked",
            "Pinned backend's FL25 writer has not been adapted for FL26",
        ),
        (
            "event_semantics",
            "unverified",
            "All byte evidence and unresolved fields require an explicit preservation policy",
        ),
        (
            "dependencies",
            "unverified",
            "Plugin/sample versions, availability and rights require host/operator evidence",
        ),
        (
            "instrument_intent",
            "unverified",
            "Local binding matches do not verify intended instruments or routing",
        ),
        (
            "inherited_content_policy",
            "unverified",
            "No replacement, clearing, automation or crop policy is approved",
        ),
        (
            "exclusive_output_safety",
            "unverified",
            "This read-only assessment has not staged, published or verified an output",
        ),
        (
            "host_validation",
            "unverified",
            "No copied output has been opened, read back or listened to in FL Studio",
        ),
    ]
    gates = [
        WriterGate(gate=gate, status=status, reason=reason) for gate, status, reason in gate_specs
    ]
    return TemplateReadinessReport(
        inspection=inspection,
        inspection_snapshot_sha256=snapshot_sha256(inspection),
        dependencies=dependencies,
        findings=findings,
        writer_gates=gates,
        binding_check=check,
    )
