"""Project inferred coordinates only; existing MIDI never enters this path."""

from collections import defaultdict
from fractions import Fraction
from io import BytesIO

import mido

from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.estimated_arrangement import EstimatedPitchInput
from suno2flp.core.estimated_midi import (
    EstimatedMidiScore,
    PreviewBoundary,
    PreviewNote,
    PreviewPart,
    SignedTime,
)
from suno2flp.core.note_scoring import time_fraction
from suno2flp.core.percussion_arrangement import PercussionArrangement
from suno2flp.core.performance import RationalTime

# Deliberate preview choices, not a qualified receiver or instrument discovery.
DRUM_KEYS = dict(
    CY_CR=49, CY_RD=51, HH_CHH=42, HH_OHH=46, KD=36, SD=38, TT_HFT=43, TT_HMT=48, TT_LMT=47
)


def _boundary(value: Fraction) -> PreviewBoundary:
    ticks = value * Fraction(960, 500000)
    rounded = ticks + Fraction(1, 2)
    tick = rounded.numerator // rounded.denominator
    return PreviewBoundary(
        original_us=RationalTime.exact(value),
        tick=tick,
        error_us=SignedTime.exact(Fraction(tick * 500000, 960) - value),
    )


def _check_pairs(part: PreviewPart) -> None:
    by_key: dict[int, list[PreviewNote]] = defaultdict(list)
    for note in part.notes:
        if note.end.tick <= note.start.tick:
            raise ValueError("Inferred duration would collapse on the preview tick grid")
        by_key[note.pitch].append(note)
    for notes in by_key.values():
        previous_end = -1
        for note in sorted(notes, key=lambda n: n.start.tick):
            if note.end.tick < previous_end:
                raise ValueError("Nested same-key notes cannot retain occurrence pairing in SMF")
            previous_end = note.end.tick


def project_estimated_midi(arrangement: PercussionArrangement) -> EstimatedMidiScore:
    source = PercussionArrangement.model_validate(arrangement.model_dump())
    expected = build_percussion_arrangement(source.inputs)
    expected.root, expected.recipe = source.root, source.recipe
    if source != expected:
        raise ValueError("Use the complete independently reconstructed estimated arrangement")
    pitches: dict[str, EstimatedPitchInput] = {p.stem: p for p in source.inputs.pitched.pitches}
    channels = dict(vocals=0, drums=9, bass=1, other=2)
    parts = []
    for part in source.parts:
        notes = []
        for pos in part.notes:
            note = pitches[part.stem].notes[pos.source_note_index]
            notes.append(
                PreviewNote(
                    source_kind="pitched-note",
                    source_index=pos.source_note_index,
                    pitch=note.pitch,
                    start=_boundary(time_fraction(pos.start.microseconds)),
                    end=_boundary(time_fraction(pos.end.microseconds)),
                )
            )
        for onset in part.onsets:
            event = source.inputs.drums.events[onset.source_event_index]
            start = time_fraction(onset.microseconds)
            notes.append(
                PreviewNote(
                    source_kind="drum-onset",
                    source_index=onset.source_event_index,
                    source_peak_index=onset.source_peak_index,
                    pitch=DRUM_KEYS[event.label],
                    start=_boundary(start),
                    end=_boundary(start + 50000),
                )
            )
        target = PreviewPart(stem=part.stem, channel=channels[part.stem], notes=notes)
        _check_pairs(target)
        parts.append(target)
    audio = source.inputs.pitched
    end_us = Fraction(audio.frames * 1000000, audio.sample_rate)
    exact_end = end_us * Fraction(960, 500000)
    end_tick = -(-exact_end.numerator // exact_end.denominator)
    end_tick = max([end_tick, *[n.end.tick for p in parts for n in p.notes]])
    return EstimatedMidiScore(
        arrangement=source,
        parts=parts,
        source_end_us=RationalTime.exact(end_us),
        end_tick=end_tick,
        blockers=[
            *source.blockers,
            "technical-clock-not-musical-tempo",
            "fixed-velocity-preview-policy",
            "synthetic-drum-note-offs",
            "pitch-bends-not-rendered",
            "midi-instrument-routing-unverified",
            "midi-preview-not-host-validated",
        ],
    )


def encode_estimated_midi(score: EstimatedMidiScore) -> bytes:
    if score != project_estimated_midi(score.arrangement):
        raise ValueError("Score differs from the complete source projection")
    midi = mido.MidiFile(type=1, ticks_per_beat=score.ppq)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage(
                    "track_name", name="Unqualified audio inference - technical clock"
                ),
                mido.MetaMessage("set_tempo", tempo=score.tempo_us),
                mido.MetaMessage("end_of_track", time=score.end_tick),
            ]
        )
    )
    for part in score.parts:
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=part.stem)])
        events = []
        for index, note in enumerate(part.notes):
            events.extend(
                [
                    (note.start.tick, 1, index, "note_on", note.pitch, note.velocity),
                    (note.end.tick, 0, index, "note_off", note.pitch, 0),
                ]
            )
        tick = 0
        for position, _, _, kind, pitch, velocity in sorted(events):
            track.append(
                mido.Message(
                    kind, note=pitch, velocity=velocity, channel=part.channel, time=position - tick
                )
            )
            tick = position
        track.append(mido.MetaMessage("end_of_track", time=score.end_tick - tick))
        midi.tracks.append(track)
    stream = BytesIO()
    midi.save(file=stream)
    return stream.getvalue()
