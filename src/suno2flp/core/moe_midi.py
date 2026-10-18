"""Inferred model-address MIDI contracts, distinct from source MIDI authority."""

import struct
from fractions import Fraction
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.estimated_midi import PreviewBoundary
from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe, time_fraction
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime
from suno2flp.core.yourmt3 import YourMT3Note
from suno2flp.core.yourmt3_moe import (
    Count,
    YourMT3MoEBackend,
    YourMT3MoECandidate,
    YourMT3MoEProgram,
)


class MoEMidiChannel(Contract):
    channel: int = Field(ge=0, lt=13, strict=True)
    notes: list[YourMT3Note] = Field(max_length=100000)
    decode_errors: dict[str, Count]
    merge_errors: dict[str, Count]


class MoEMidiInputs(Contract):
    producer: FileIdentity
    candidate: YourMT3MoECandidate
    model_channels: list[MoEMidiChannel] = Field(min_length=13, max_length=13)
    program_channels: dict[int, YourMT3MoEProgram] = Field(min_length=99, max_length=99)

    @model_validator(mode="after")
    def addresses(self) -> Self:
        if [c.channel for c in self.model_channels] != list(range(13)):
            raise ValueError("Retain all13 unique model addresses in native order")
        if sum(len(c.notes) for c in self.model_channels) > 20000:
            raise ValueError("Complete MIDI export exceeds20000 notes; no truncation")
        if self.candidate.unresolved_generations:
            raise ValueError("Unfinished generations cannot produce an editable MIDI bundle")
        for channel in self.model_channels:
            for note in channel.notes:
                label = self.program_channels.get(note.program)
                if label is None or label.channel != channel.channel:
                    raise ValueError("Native note is outside its explicit model vocabulary/address")
        return self


class MoEMidiNote(Contract):
    source_index: int = Field(ge=0, lt=20000, strict=True)
    native: YourMT3Note
    onset_bits: str = Field(pattern=r"^[0-9a-f]{16}$")
    offset_bits: str = Field(pattern=r"^[0-9a-f]{16}$")
    start: PreviewBoundary
    end: PreviewBoundary

    @model_validator(mode="after")
    def exact_boundaries(self) -> Self:
        for value, bits, point in (
            (self.native.onset, self.onset_bits, self.start),
            (self.native.offset, self.offset_bits, self.end),
        ):
            exact = Fraction.from_float(value) * 1000000
            error = Fraction(point.tick * 500000, 960) - exact
            rounded = exact * Fraction(960, 500000) + Fraction(1, 2)
            if (
                bits != struct.pack("<d", value).hex()
                or time_fraction(point.original_us) != exact
                or Fraction(point.error_us.numerator, point.error_us.denominator) != error
                or point.tick != rounded.numerator // rounded.denominator
                or abs(error) > Fraction(3125, 12)
            ):
                raise ValueError("Native bits, exact coordinates or half-up boundary audit changed")
        if self.end.tick <= self.start.tick:
            raise ValueError("Positive native duration collapses on the MIDI tick grid")
        return self


class MoEMidiPart(Contract):
    source_channel: int = Field(ge=0, lt=13, strict=True)
    model_program: int = Field(ge=0, le=128, strict=True)
    instrument_group_hint: str
    midi_channel: Literal[0, 9]
    notes: list[MoEMidiNote] = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def routing_and_pairs(self) -> Self:
        if self.midi_channel != (9 if self.model_program == 128 else 0):
            raise ValueError("Each independent file uses melodic0 or drum9")
        indices = [n.source_index for n in self.notes]
        if indices != sorted(set(indices)) or any(
            n.native.program != self.model_program for n in self.notes
        ):
            raise ValueError("Keep unique native occurrence indices and the actual model program")
        ends: dict[int, int] = {}
        for note in sorted(self.notes, key=lambda n: n.start.tick):
            if note.end.tick < ends.get(note.native.pitch, -1):
                raise ValueError("Nested same-key notes cannot retain SMF FIFO occurrence pairing")
            ends[note.native.pitch] = note.end.tick
        return self


class MoEMidiScore(Contract):
    profile: Literal["moe-model-program-midi-v1"] = "moe-model-program-midi-v1"
    authority: Literal["audio-inference"] = "audio-inference"
    status: Literal["unqualified_candidate"] = "unqualified_candidate"
    inputs: MoEMidiInputs
    parts: list[MoEMidiPart] = Field(max_length=99)
    source_end_us: RationalTime
    end_tick: int = Field(ge=0, le=2**31 - 1, strict=True)
    ppq: Literal[960] = 960
    tempo_us: Literal[500000] = 500000
    clock_basis: Literal["technical-audio-seconds-not-musical-tempo"] = (
        "technical-audio-seconds-not-musical-tempo"
    )
    rounding: Literal["independent-boundaries-nearest-half-up-v1"] = (
        "independent-boundaries-nearest-half-up-v1"
    )
    velocity_policy: Literal["fixed96-native-velocity-retained"] = (
        "fixed96-native-velocity-retained"
    )
    routing_policy: Literal["separate-model-program-files-no-gm-program-messages"] = (
        "separate-model-program-files-no-gm-program-messages"
    )
    blockers: list[str]
    model_qualification: Literal["not_assessed"] = "not_assessed"
    ground_truth_metrics: Literal["unavailable"] = "unavailable"
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    human_review: Literal["not_performed"] = "not_performed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False


class MoEMidiFile(Contract):
    source_channel: int = Field(ge=0, lt=13, strict=True)
    model_program: int = Field(ge=0, le=128, strict=True)
    midi: FileIdentity


class MoEMidiExport(Contract):
    profile: Literal["moe-midi-export-v1"] = "moe-midi-export-v1"
    root: Path
    score: MoEMidiScore
    files: list[MoEMidiFile] = Field(max_length=99)
    companion: FileIdentity
    source_backend: YourMT3MoEBackend
    recipe: ScoringRecipe
    mido_version: str
