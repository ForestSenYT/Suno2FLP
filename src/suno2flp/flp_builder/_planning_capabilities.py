"""Source-assessed Music2DAW limits; none of these enable execution."""

from fractions import Fraction

from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.models import Arrangement, Diagnostic


def assess_capabilities(
    arrangement: Arrangement, inspection: TemplateInspectionReport, diagnostics: list[Diagnostic]
) -> int | None:
    def error(code: str, message: str) -> None:
        diagnostics.append(Diagnostic(code=code, severity="error", message=message))

    tempo_millibpm = None
    if len(arrangement.tempo_map) != 1:
        error("tempo_map_unsupported", "Pinned backend can set only one constant tempo")
    else:
        tempo = Fraction(60_000_000_000, arrangement.tempo_map[0].microseconds_per_beat)
        if not 0 < tempo <= 999000:
            error(
                "tempo_range_unsupported",
                "Backend tempo range is greater than zero through 999 BPM",
            )
        elif tempo.denominator != 1:
            error(
                "tempo_precision_unsupported",
                "Tempo is not exactly representable at 0.001 BPM; no rounding permitted",
            )
        else:
            tempo_millibpm = tempo.numerator
    if len(arrangement.meter_map) != 1 or any(
        (m.numerator, m.denominator, m.clocks_per_click, m.notated_32nd_notes_per_beat)
        != (4, 4, 24, 8)
        for m in arrangement.meter_map
    ):
        error(
            "meter_unsupported",
            "Only constant MIDI-default 4/4 can enter this preview subset; "
            "backend has no meter setter",
        )
    if inspection.project.fl_studio_version != "25.1.2.4896":
        error(
            "template_version_unsupported",
            "Only FL 25.1.2.4896 has source-assessed layout evidence at this pin",
        )
    if inspection.project.playlist_item_count == 0:
        error(
            "playlist_event_unverified",
            "Summary cannot establish a writable existing playlist event",
        )
    metadata = {
        "track_name",
        "instrument_name",
        "text",
        "copyright",
        "marker",
        "cue_marker",
        "lyrics",
        "end_of_track",
        "set_tempo",
        "time_signature",
        "key_signature",
        "sequence_number",
    }
    for snapshot in arrangement.sources:
        if snapshot.midi.source_sha256 is None:
            error(
                "source_hash_unverified",
                f"Input {snapshot.input_index} has no recorded source hash",
            )
        for diagnostic in snapshot.midi.diagnostics:
            if diagnostic.code in {"unmatched_note_off", "unclosed_note"}:
                copied = diagnostic.model_copy(deep=True)
                copied.code = "source_notes_incomplete"
                copied.severity = "error"
                copied.source_input = snapshot.input_index
                diagnostics.append(copied)
        for position, track in enumerate(snapshot.midi.tracks):
            for event in track.events:
                kind = event.message.get("type")
                if not isinstance(kind, str) or kind not in metadata | {"note_on", "note_off"}:
                    diagnostics.append(
                        Diagnostic(
                            code="source_event_unsupported",
                            severity="error",
                            message=f"Backend cannot translate source event {kind!r}",
                            source_input=snapshot.input_index,
                            track_index=track.index if track.index is not None else position,
                            event_index=event.event_index,
                            path=snapshot.midi.source,
                        )
                    )
    return tempo_millibpm
