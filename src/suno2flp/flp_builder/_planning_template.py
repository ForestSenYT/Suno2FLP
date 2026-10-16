"""Conservative template-content gates; never clears or changes inherited content."""

from collections import Counter
from fractions import Fraction
from typing import cast

from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_models import TemplateBindingDocument
from suno2flp.core.models import Diagnostic
from suno2flp.core.template_profiles import FL26_READ_PROFILE


def assess_template_inventory(
    inspection: TemplateInspectionReport,
    bindings: TemplateBindingDocument,
    diagnostics: list[Diagnostic],
) -> None:
    def error(code: str, message: str, event_index: int | None = None) -> None:
        diagnostics.append(
            Diagnostic(
                code=code,
                severity="error",
                message=message,
                path=inspection.template_path,
                event_index=event_index,
            )
        )

    inventory = inspection.inventory
    if inventory is None:
        error(
            "template_inventory_missing",
            "Refresh read-only inspection; summary-only evidence cannot pass v2 planning",
        )
        return
    if inventory.profile_id == FL26_READ_PROFILE.identifier:
        error(
            "template_read_only_profile",
            "FL26 profile supports byte reading only; pinned backend writing remains unsupported",
        )
    if inspection.backend_summary_status == "inconsistent":
        error(
            "template_backend_summary_untrusted",
            "Backend summary disagrees with retained local byte evidence",
        )
    diagnostics.extend(item.model_copy(deep=True) for item in inventory.diagnostics)
    if inventory.coverage != "decoded":
        error(
            "template_inventory_incomplete",
            "Unsupported/opaque template structure must be resolved before writer adoption",
        )
    counts = Counter(note.pattern_id for note in inventory.notes)
    declared_patterns = [
        event.pattern_id
        for event in inventory.events
        if event.event_id == 65 and event.pattern_id is not None
    ]
    expected_ids = set(range(max(declared_patterns, default=-1) + 1))
    reported_counts = {
        cast(int, pattern["id"]): cast(int, pattern["noteCount"])
        for pattern in inspection.project.patterns
    }
    if (
        inventory.fl_studio_version != inspection.project.fl_studio_version
        or set(reported_counts) != expected_ids
        or any(counts[pattern] != count for pattern, count in reported_counts.items())
        or len(inventory.clips) != inspection.project.playlist_item_count
    ):
        error(
            "template_inventory_summary_mismatch",
            "Local byte inventory and pinned backend summary disagree",
        )
    note_events = Counter(event.pattern_id for event in inventory.events if event.event_id == 224)
    if any(count > 1 for count in note_events.values()):
        error(
            "template_note_events_ambiguous",
            "Repeated note events could duplicate replacements; no merge/deletion policy exists",
        )
    playlist_events = [event for event in inventory.events if event.event_id == 233]
    if len(playlist_events) != 1:
        error(
            "template_playlist_events_ambiguous",
            "Exactly one assessed playlist event is required; no arrangement selection is inferred",
        )
    if any(event.event_id == 99 for event in inventory.events):
        error(
            "template_arrangements_unsupported",
            "Explicit arrangement delimiters need a backend selection policy",
        )
    fine_tempos = [event for event in inventory.events if event.event_id == 156]
    if len(fine_tempos) != 1:
        error(
            "template_tempo_event_unverified",
            "Exactly one existing fine-tempo event is required by this preview subset",
        )
    tempos = [event for event in inventory.events if event.event_id in {66, 156}]
    if tempos and tempos[-1].event_id != 156:
        error(
            "template_tempo_conflict",
            "A later legacy tempo event could override the backend's fine-tempo edit",
        )
    if tempos:
        last = tempos[-1]
        if last.scalar_hex is not None:
            value = int.from_bytes(bytes.fromhex(last.scalar_hex), "little")
            actual = value if last.event_id == 156 else value * 1000
            if Fraction(str(inspection.project.tempo)) * 1000 != actual:
                error(
                    "template_inventory_summary_mismatch",
                    "Tempo bytes differ from backend summary",
                    last.event_index,
                )
    meter_events = [event for event in inventory.events if event.event_id in {17, 18}]
    if any(event.scalar_hex != "04" for event in meter_events):
        error("template_meter_conflict", "Explicit template meter is outside the source 4/4 subset")
    if {event.event_id for event in meter_events} != {17, 18}:
        diagnostics.append(
            Diagnostic(
                code="template_meter_unverified",
                severity="warning",
                message="Template does not declare both assessed meter fields; "
                "no default is proven",
                path=inspection.template_path,
            )
        )
    if inventory.automation:
        for automation in inventory.automation:
            error(
                "template_automation_unsupported",
                "Template automation is retained but cannot be safely translated or cleared",
                automation.event_index,
            )
    bound_pairs = {
        (rule.template_pattern_id, rule.template_channel_id) for rule in bindings.config.bindings
    }
    enabled = {event.channel_id: event for event in inventory.events if event.event_id == 0}
    for channel_id in {pair[1] for pair in bound_pairs}:
        state = enabled.get(channel_id)
        if state is not None and state.scalar_hex != "01":
            error(
                "template_channel_disabled",
                "Target channel is disabled or has an unverified enabled value",
                state.event_index,
            )
    actual_pairs = {(note.pattern_id, note.channel_id) for note in inventory.notes}
    if bound_pairs - actual_pairs:
        error(
            "template_note_set_missing",
            "Each target needs an existing note record for that exact Pattern/channel pair",
        )
    for note in inventory.notes:
        if (note.pattern_id, note.channel_id) not in bound_pairs:
            error(
                "template_notes_unbound",
                "Inherited notes outside explicit target pairs have no approved content policy",
                note.event_index,
            )
        raw = bytes.fromhex(note.raw_hex)
        if note.flags or note.group or any(raw[13:16]) or any(raw[22:24]):
            error(
                "template_note_attributes_unsupported",
                "Unknown/grouped note attributes could be inherited by a future writer",
                note.event_index,
            )
        if (
            note.position_ticks < 0
            or note.length_ticks <= 0
            or note.pitch > 127
            or not 1 <= note.velocity <= 127
            or note.pan > 127
        ):
            error(
                "template_note_range_unsupported",
                "Template note is outside the conservative backend note range",
                note.event_index,
            )
    bound_lanes = {
        rule.template_pattern_id: rule.template_playlist_track for rule in bindings.config.bindings
    }
    if inventory.clips:
        # The pinned editor uses the first record's base for every replacement.
        base = inventory.clips[0].pattern_base
        if any(clip.pattern_base != base for clip in inventory.clips):
            error(
                "template_pattern_base_ambiguous",
                "Mixed playlist encoding bases need an explicit backend policy",
            )
        for pattern_id in bound_lanes:
            if base + pattern_id + 1 > 65535:
                error(
                    "template_pattern_index_overflow",
                    "Planned Pattern cannot fit the template's encoded 16-bit item index",
                )
    for clip in inventory.clips:
        if clip.kind != "pattern" or bound_lanes.get(clip.item_id) != clip.track:
            error(
                "template_clip_binding_conflict",
                "Inherited channel/unbound/misplaced clip has no approved replacement policy",
                clip.event_index,
            )
        if clip.start_offset.value != 0 or clip.end_offset.value != 0:
            error(
                "template_crop_unsupported",
                "Nonzero/unknown crop bits cannot be cleared by zero-offset backend requests",
                clip.event_index,
            )
        if clip.muted:
            error(
                "template_muted_clip_unsupported",
                "Muted template clips need an explicit content policy",
                clip.event_index,
            )
        if clip.group or clip.flags & ~(0x2000 | 0x40):
            error(
                "template_clip_flags_unsupported",
                "Grouped/unknown clip flags may survive record inheritance",
                clip.event_index,
            )
        if clip.position_ticks < 0 or clip.length_ticks <= 0 or not 0 <= clip.track < 500:
            error(
                "template_clip_range_unsupported",
                "Template clip is outside supported coordinates",
                clip.event_index,
            )
