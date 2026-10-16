"""Explicit role annotations for provenanced channels; no inference, routing or plugins."""

from suno2flp.core.errors import InstrumentMappingError
from suno2flp.core.models import (
    Arrangement,
    Diagnostic,
    InstrumentAssignment,
    InstrumentMappingDocument,
    InstrumentMappingMatch,
    InstrumentMappingRecord,
    InstrumentMappingTarget,
)


class ExplicitInstrumentMapper:
    def apply(self, arrangement: Arrangement, mapping: InstrumentMappingDocument) -> Arrangement:
        """Return an independent arrangement with explicit metadata-only assignments."""
        if arrangement.mode != "faithful":
            raise InstrumentMappingError("Instrument mapping currently requires faithful mode")
        if any(d.severity == "error" for d in arrangement.diagnostics):
            raise InstrumentMappingError("Resolve arrangement errors before instrument mapping")
        mapping = InstrumentMappingDocument.model_validate(mapping.model_dump())
        selectors, available = _source_channels(arrangement)
        if arrangement.instrument_mapping is not None:
            if arrangement.instrument_mapping.document == mapping:
                return arrangement.model_copy(deep=True)
            raise InstrumentMappingError(
                "Changed mapping requires the original unmapped arrangement"
            )
        if any(track.instrument_roles for track in arrangement.tracks):
            raise InstrumentMappingError("Unrecorded instrument assignments cannot be overwritten")
        result = arrangement.model_copy(deep=True)
        record = InstrumentMappingRecord(document=mapping.model_copy(deep=True))
        used: set[tuple[int, int]] = set()
        for rule_index, rule in enumerate(mapping.config.mappings):
            tracks = selectors.get((rule.source_input, rule.source_track_position), [])
            if len(tracks) != 1:
                raise InstrumentMappingError(
                    f"Rule {rule_index} must select exactly one source track"
                )
            track_index = tracks[0]
            channels = (
                sorted(available[track_index])
                if rule.source_channel is None
                else [rule.source_channel]
            )
            if not channels or not set(channels).issubset(available[track_index]):
                raise InstrumentMappingError(
                    f"Rule {rule_index} selects no verified source channels"
                )
            role = mapping.config.roles[rule.role]
            for channel in channels:
                target = (track_index, channel)
                if target in used:
                    raise InstrumentMappingError(
                        f"Overlapping rules: track {track_index}, channel {channel}"
                    )
                used.add(target)
                result.tracks[track_index].instrument_roles.append(
                    InstrumentAssignment(
                        source_channel=channel,
                        role=rule.role,
                        rule_index=rule_index,
                        general_midi_program=role.general_midi_program,
                        plugin_hint=role.plugin_hint,
                        percussion=role.percussion,
                    )
                )
                record.matches.append(
                    InstrumentMappingMatch(
                        rule_index=rule_index,
                        arrangement_track_index=track_index,
                        source_channel=channel,
                    )
                )
        for track_index, source_channels in enumerate(available):
            track = result.tracks[track_index]
            track.instrument_roles.sort(key=lambda assignment: assignment.source_channel)
            missing = sorted(
                channel for channel in source_channels if (track_index, channel) not in used
            )
            record.unmapped.extend(
                InstrumentMappingTarget(arrangement_track_index=track_index, source_channel=channel)
                for channel in missing
            )
            if missing and mapping.config.mappings:
                result.diagnostics.append(
                    Diagnostic(
                        code="instrument_role_unmapped",
                        severity="warning",
                        path=track.source,
                        source_input=track.source_input,
                        track_index=track.source_track,
                        message=f"No explicit role for source channels {missing}; left unchanged",
                    )
                )
        result.instrument_mapping = record
        return result


def _source_channels(
    arrangement: Arrangement,
) -> tuple[dict[tuple[int, int], list[int]], list[set[int]]]:
    if not arrangement.sources:
        raise InstrumentMappingError("Instrument mapping requires arrangement source snapshots")
    for source_slot, snapshot in enumerate(arrangement.sources):
        if snapshot.input_index != source_slot:
            raise InstrumentMappingError("Source snapshot indices are inconsistent")
    selectors: dict[tuple[int, int], list[int]] = {}
    available: list[set[int]] = []
    for track_index, track in enumerate(arrangement.tracks):
        source_index, position = track.source_input, track.source_track_position
        if (
            source_index is None
            or position is None
            or source_index < 0
            or position < 0
            or source_index >= len(arrangement.sources)
        ):
            raise InstrumentMappingError("Track has missing or invalid source provenance")
        source_midi = arrangement.sources[source_index].midi
        if position >= len(source_midi.tracks):
            raise InstrumentMappingError("Track refers to a missing source track")
        original = source_midi.tracks[position]
        expected_index = original.index if original.index is not None else position
        if (
            track.source != source_midi.source
            or track.source_ticks_per_beat != source_midi.ticks_per_beat
            or track.source_track != expected_index
        ):
            raise InstrumentMappingError("Track and source snapshot provenance disagree")
        if len(track.notes) != len(track.note_origins):
            raise InstrumentMappingError("Track note provenance is incomplete")
        channels: set[int] = set()
        for note, origin in zip(track.notes, track.note_origins, strict=True):
            if origin.note_index >= len(original.notes):
                raise InstrumentMappingError("Source note index is invalid")
            if note.channel != original.notes[origin.note_index].channel:
                raise InstrumentMappingError("Source MIDI channels must be preserved")
            channels.add(note.channel)
        for event in original.events:
            channel = event.message.get("channel")
            if type(channel) is int and 0 <= channel <= 15:
                channels.add(channel)
        selectors.setdefault((source_index, position), []).append(track_index)
        available.append(channels)
    return selectors, available
