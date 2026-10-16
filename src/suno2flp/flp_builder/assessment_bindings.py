"""Local binding evidence and exact timing previews, independent of backend targets."""

from suno2flp.core.assessment_models import LocalBindingCheck
from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_models import (
    PlannedBindingPart,
    PlannedNote,
    SourceSelector,
    TemplateBindingDocument,
)
from suno2flp.core.errors import BuildPlanningError
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.models import Arrangement, Diagnostic
from suno2flp.flp_builder._planning_provenance import validate_snapshots


def check_local_bindings(
    arrangement: Arrangement,
    inspection: TemplateInspectionReport,
    bindings: TemplateBindingDocument,
) -> LocalBindingCheck:
    validate_snapshots(arrangement, inspection, bindings)
    inventory = inspection.inventory
    assert inventory is not None
    diagnostics = []

    def error(code: str, message: str) -> None:
        diagnostics.append(Diagnostic(code=code, severity="error", message=message))

    for source in arrangement.sources:
        if source.midi.source_sha256 is None:
            error("source_hash_unverified", f"Input {source.input_index} lacks a source byte hash")
        for diagnostic in source.midi.diagnostics:
            if diagnostic.code in {"unclosed_note", "unmatched_note_off"}:
                copied = diagnostic.model_copy(deep=True)
                copied.code, copied.severity = "source_notes_incomplete", "error"
                copied.source_input = source.input_index
                diagnostics.append(copied)

    sources: dict[tuple[int, int, int], int] = {}
    for track_index, track in enumerate(arrangement.tracks):
        assert track.source_input is not None and track.source_track_position is not None
        for channel in sorted({n.channel for n in track.notes}):
            sources[(track.source_input, track.source_track_position, channel)] = track_index
    used = set()
    parts = []
    for index, binding in enumerate(bindings.config.bindings):
        key = (binding.source_input, binding.source_track_position, binding.source_channel)
        if key not in sources:
            error("binding_source_missing", f"Binding {index} selects no active source channel")
            continue
        used.add(key)
        track_index = sources[key]
        track = arrangement.tracks[track_index]
        part = PlannedBindingPart(
            binding_index=index,
            arrangement_track_index=track_index,
            binding=binding,
            template_note_indices=[
                i
                for i, n in enumerate(inventory.notes)
                if (n.pattern_id, n.channel_id)
                == (binding.template_pattern_id, binding.template_channel_id)
            ],
            template_clip_indices=[
                i
                for i, c in enumerate(inventory.clips)
                if c.kind == "pattern"
                and (c.item_id, c.track)
                == (binding.template_pattern_id, binding.template_playlist_track)
            ],
        )
        if not part.template_note_indices or binding.template_channel_id >= inventory.channel_count:
            error(
                "binding_local_note_pair_missing",
                f"Binding {index} lacks the exact local Pattern/channel note pair",
            )
        if not part.template_clip_indices:
            error(
                "binding_local_clip_missing",
                f"Binding {index} lacks the exact local Pattern/playlist lane",
            )
        note_events = [
            e
            for e in inventory.events
            if e.event_id == 224 and e.pattern_id == binding.template_pattern_id
        ]
        if (
            len(part.template_clip_indices) > 1
            or len(note_events) > 1
            or sum(e.event_id == 233 for e in inventory.events) != 1
            or sum(e.event_id == 99 for e in inventory.events) > 1
        ):
            error(
                "binding_local_ambiguous",
                f"Binding {index} has repeated clips/note events or ambiguous arrangements",
            )

        def convert(tick: int, binding_index: int = index) -> int:
            value, remainder = divmod(tick * inventory.ppq, arrangement.ticks_per_beat)
            if remainder:
                raise BuildPlanningError(
                    "ppq_inexact", f"Binding {binding_index}: tick {tick} cannot convert exactly"
                )
            if not 0 <= value <= 2147483647:
                raise BuildPlanningError(
                    "tick_range_unsupported",
                    f"Binding {binding_index}: signed 32-bit tick range exceeded",
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
                        "note_range_unsupported", "Positive duration/velocity required"
                    )
                start, end = (
                    convert(note.start_tick),
                    convert(note.start_tick + note.duration_ticks),
                )
                notes.append(
                    PlannedNote(
                        arrangement_note_index=note_index,
                        origin=track.note_origins[note_index],
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
            error(exc.code, str(exc))
        parts.append(part)
    unbound = [
        SourceSelector(source_input=k[0], source_track_position=k[1], source_channel=k[2])
        for k in sources
        if k not in used
    ]
    if unbound or not sources:
        error("source_bindings_incomplete", "Every active source channel needs an explicit binding")
    return LocalBindingCheck(
        status="blocked" if diagnostics else "matched",
        arrangement=arrangement,
        bindings=bindings,
        arrangement_snapshot_sha256=snapshot_sha256(arrangement),
        parts=parts,
        unbound_sources=unbound,
        diagnostics=diagnostics,
    )
