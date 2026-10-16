"""Pure deterministic build previews: no filesystem access, subprocess or FLP writes."""

from typing import cast

from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_models import (
    DryRunBuildPlan,
    PlannedBindingPart,
    PlannedNote,
    SourceSelector,
    TemplateBindingDocument,
)
from suno2flp.core.errors import BuildPlanningError
from suno2flp.core.evidence import snapshot_sha256 as snapshot_sha256
from suno2flp.core.models import Arrangement, Diagnostic
from suno2flp.flp_builder._planning_capabilities import assess_capabilities
from suno2flp.flp_builder._planning_provenance import validate_snapshots
from suno2flp.flp_builder._planning_template import assess_template_inventory


class DryRunBuildPlanner:
    def plan(
        self,
        arrangement: Arrangement,
        inspection: TemplateInspectionReport,
        bindings: TemplateBindingDocument,
    ) -> DryRunBuildPlan:
        try:
            arrangement = Arrangement.model_validate(arrangement.model_dump())
            inspection = TemplateInspectionReport.model_validate(inspection.model_dump())
            bindings = TemplateBindingDocument.model_validate(bindings.model_dump())
        except (ValueError, TypeError) as exc:
            raise BuildPlanningError("planning_input_invalid", str(exc)) from exc
        validate_snapshots(arrangement, inspection, bindings)
        diagnostics = [d.model_copy(deep=True) for d in arrangement.diagnostics]
        diagnostics.extend(d.model_copy(deep=True) for d in inspection.diagnostics)
        tempo = assess_capabilities(arrangement, inspection, diagnostics)
        assess_template_inventory(inspection, bindings, diagnostics)
        targets = {cast(int, c["id"]): c for c in inspection.project.channels}
        patterns = {cast(int, p["id"]): p for p in inspection.project.patterns}
        sources: dict[tuple[int, int, int], int] = {}
        for index, track in enumerate(arrangement.tracks):
            assert track.source_input is not None and track.source_track_position is not None
            for channel in sorted({n.channel for n in track.notes}):
                sources[(track.source_input, track.source_track_position, channel)] = index
        used = set()
        parts = []
        for binding_index, binding in enumerate(bindings.config.bindings):
            key = (binding.source_input, binding.source_track_position, binding.source_channel)
            if (
                key not in sources
                or binding.template_channel_id not in targets
                or binding.template_pattern_id not in patterns
            ):
                raise BuildPlanningError(
                    "binding_target_invalid",
                    f"Binding {binding_index} must select an active source channel "
                    "and existing template IDs",
                )
            used.add(key)
            track_index = sources[key]
            track = arrangement.tracks[track_index]
            target_channel = targets[binding.template_channel_id]
            if (
                not isinstance(target_channel.get("generator"), str)
                or type(target_channel.get("isLikelySequenced")) is not bool
            ):
                diagnostics.append(
                    Diagnostic(
                        code="channel_capability_unverified",
                        severity="error",
                        message=f"Binding {binding_index} lacks generator/sequence evidence",
                    )
                )
            elif target_channel["generator"] == "Automation" or target_channel["isLikelySequenced"]:
                diagnostics.append(
                    Diagnostic(
                        code="channel_capability_unsupported",
                        severity="error",
                        message=f"Binding {binding_index} targets automation "
                        "or a sequenced instrument",
                    )
                )
            if patterns[binding.template_pattern_id]["noteCount"] == 0:
                diagnostics.append(
                    Diagnostic(
                        code="pattern_note_event_unverified",
                        severity="error",
                        message=f"Binding {binding_index} has no positive pattern-note count "
                        "to establish an existing note event",
                    )
                )
            part = PlannedBindingPart(
                binding_index=binding_index,
                arrangement_track_index=track_index,
                binding=binding.model_copy(deep=True),
                template_note_indices=[
                    i
                    for i, note in enumerate(inspection.inventory.notes)
                    if note.pattern_id == binding.template_pattern_id
                    and note.channel_id == binding.template_channel_id
                ]
                if inspection.inventory
                else [],
                template_clip_indices=[
                    i
                    for i, clip in enumerate(inspection.inventory.clips)
                    if clip.kind == "pattern"
                    and clip.item_id == binding.template_pattern_id
                    and clip.track == binding.template_playlist_track
                ]
                if inspection.inventory
                else [],
            )

            def convert(tick: int, slot: int = binding_index) -> int:
                value, remainder = divmod(tick * inspection.header.ppq, arrangement.ticks_per_beat)
                if remainder:
                    raise BuildPlanningError(
                        "ppq_inexact",
                        f"Binding {slot}: tick {tick} cannot convert exactly "
                        f"to template PPQ {inspection.header.ppq}",
                    )
                if not 0 <= value <= 2147483647:
                    raise BuildPlanningError(
                        "tick_range_unsupported",
                        f"Binding {slot}: converted tick exceeds backend signed 32-bit coordinates",
                    )
                return value

            try:
                length = convert(track.end_tick)
                notes = []
                for note_index, note in enumerate(track.notes):
                    if note.channel != binding.source_channel:
                        continue
                    if note.duration_ticks <= 0 or not 1 <= note.velocity <= 127:
                        raise BuildPlanningError(
                            "note_range_unsupported",
                            "Backend requires positive note duration and velocity 1..127",
                        )
                    start = convert(note.start_tick)
                    end = convert(note.start_tick + note.duration_ticks)
                    notes.append(
                        PlannedNote(
                            arrangement_note_index=note_index,
                            origin=track.note_origins[note_index].model_copy(deep=True),
                            source_channel=note.channel,
                            pitch=note.pitch,
                            velocity=note.velocity,
                            start_tick=start,
                            duration_ticks=end - start,
                        )
                    )
                    length = max(length, end)
                part.notes, part.clip_length_ticks = notes, length
            except BuildPlanningError as exc:
                diagnostics.append(
                    Diagnostic(
                        code=exc.code,
                        severity="error",
                        message=str(exc),
                        source_input=binding.source_input,
                        track_index=track.source_track,
                        path=track.source,
                    )
                )
            parts.append(part)
        unbound = [
            SourceSelector(source_input=k[0], source_track_position=k[1], source_channel=k[2])
            for k in sources
            if k not in used
        ]
        if unbound or not sources:
            diagnostics.append(
                Diagnostic(
                    code="source_bindings_incomplete",
                    severity="error",
                    message="Every active source channel requires an explicit binding; "
                    "at least one note is required",
                )
            )
        diagnostics.extend(
            Diagnostic(code=code, severity="warning", message=message)
            for code, message in [
                (
                    "writer_disabled",
                    "Dry-run intent only; no executable edit request or FLP output is produced",
                ),
                (
                    "template_structure_unverified",
                    "Inventory covers assessed event families only; opaque plugin/track "
                    "semantics and final event encoding remain unverified",
                ),
                (
                    "template_compatibility_unverified",
                    "Template/plugin rights, availability and FL Studio playback remain unverified",
                ),
                (
                    "source_metadata_sidecar_only",
                    "Original source events and instrument-role hints remain in provenance; "
                    "metadata is not inferred into FL instruments",
                ),
            ]
        )
        return DryRunBuildPlan(
            status="blocked"
            if any(d.severity == "error" for d in diagnostics)
            else "review_required",
            arrangement=arrangement,
            inspection=inspection,
            bindings=bindings,
            arrangement_snapshot_sha256=snapshot_sha256(arrangement),
            inspection_snapshot_sha256=snapshot_sha256(inspection),
            inventory_snapshot_sha256=snapshot_sha256(inspection.inventory)
            if inspection.inventory
            else None,
            target_ppq=inspection.header.ppq,
            tempo_millibpm=tempo,
            parts=parts,
            unbound_sources=unbound,
            diagnostics=diagnostics,
        )
