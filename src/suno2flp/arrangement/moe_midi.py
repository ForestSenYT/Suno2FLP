"""Owned, loss-audited projection of inferred native notes into separate SMFs."""

import struct
from fractions import Fraction
from io import BytesIO

import mido

from suno2flp.core.estimated_midi import PreviewBoundary, SignedTime
from suno2flp.core.moe_midi import MoEMidiInputs, MoEMidiNote, MoEMidiPart, MoEMidiScore
from suno2flp.core.performance import RationalTime


def _boundary(value: float) -> PreviewBoundary:
    original = Fraction.from_float(value) * 1000000
    rounded = original * Fraction(960, 500000) + Fraction(1, 2)
    tick = rounded.numerator // rounded.denominator
    return PreviewBoundary(
        original_us=RationalTime.exact(original),
        tick=tick,
        error_us=SignedTime.exact(Fraction(tick * 500000, 960) - original),
    )


def project_moe_midi(inputs: MoEMidiInputs) -> MoEMidiScore:
    source = MoEMidiInputs.model_validate_json(inputs.model_dump_json())
    end_us = Fraction(source.candidate.frames * 1000000, source.candidate.sample_rate)
    end = end_us * Fraction(960, 500000)
    parts = []
    for channel in source.model_channels:
        groups: dict[int, list[MoEMidiNote]] = {}
        for index, note in enumerate(channel.notes):
            if Fraction.from_float(note.offset) * 1000000 > end_us:
                raise ValueError("Native note exceeds original audio; trimming is prohibited")
            groups.setdefault(note.program, []).append(
                MoEMidiNote(
                    source_index=index,
                    native=note.model_copy(deep=True),
                    onset_bits=struct.pack("<d", note.onset).hex(),
                    offset_bits=struct.pack("<d", note.offset).hex(),
                    start=_boundary(note.onset),
                    end=_boundary(note.offset),
                )
            )
        for program, notes in sorted(groups.items()):
            parts.append(
                MoEMidiPart(
                    source_channel=channel.channel,
                    model_program=program,
                    instrument_group_hint=source.program_channels[program].instrument_group,
                    midi_channel=9 if program == 128 else 0,
                    notes=notes,
                )
            )
    return MoEMidiScore(
        inputs=source,
        parts=parts,
        source_end_us=RationalTime.exact(end_us),
        end_tick=-(-end.numerator // end.denominator),
        blockers=[
            "inferred-not-official-midi",
            "model-and-musical-quality-unqualified",
            "technical-clock-not-musical-tempo-or-meter",
            "fixed-velocity-not-native-dynamics",
            "model-labels-not-verified-gm-or-audio-routing",
            "midi-not-host-or-flp-validated",
            "canonical-job-and-writer-blocked",
        ],
    )


def encode_moe_part(part: MoEMidiPart, end_tick: int) -> bytes:
    part = MoEMidiPart.model_validate_json(part.model_dump_json())
    if (
        type(end_tick) is not int
        or not 0 <= end_tick <= 2**31 - 1
        or any(n.end.tick > end_tick for n in part.notes)
    ):
        raise ValueError("Require complete bounded source end, without truncation")
    midi = mido.MidiFile(type=1, ticks_per_beat=960)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage("track_name", name="Unqualified MoE inference - technical clock"),
                mido.MetaMessage("set_tempo", tempo=500000),
                mido.MetaMessage("end_of_track", time=end_tick),
            ]
        )
    )
    label = f"model-channel={part.source_channel:02d};model-program={part.model_program:03d}"
    track = mido.MidiTrack([mido.MetaMessage("track_name", name=label)])
    events = []
    for note in part.notes:
        events.extend(
            [
                (note.start.tick, 1, note.source_index, "note_on", note.native.pitch, 96),
                (note.end.tick, 0, note.source_index, "note_off", note.native.pitch, 0),
            ]
        )
    tick = 0
    for position, _, _, kind, pitch, velocity in sorted(events):
        track.append(
            mido.Message(
                kind, note=pitch, velocity=velocity, channel=part.midi_channel, time=position - tick
            )
        )
        tick = position
    track.append(mido.MetaMessage("end_of_track", time=end_tick - tick))
    midi.tracks.append(track)
    stream = BytesIO()
    midi.save(file=stream)
    return stream.getvalue()
