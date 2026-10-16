"""Decoded MIDI evidence, not a host/receiver attestation or writer permission."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from suno2flp.core.encoding_assessment import SignedRatio
from suno2flp.core.models import Contract, Diagnostic, ProcessedMidi
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime


class MidiEventAddress(Contract):
    track_position: int = Field(ge=0, strict=True)
    event_index: int = Field(ge=0, strict=True)


class MidiEventMatch(Contract):
    expected: MidiEventAddress
    candidate: MidiEventAddress


class MidiClockDifference(Contract):
    beat: RationalTime
    expected_microseconds: RationalTime
    candidate_microseconds: RationalTime
    candidate_minus_expected_microseconds: SignedRatio


class MidiEventComparison(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["decoded-midi-comparison-v1"] = "decoded-midi-comparison-v1"
    input_files: list[FileIdentity]
    referenced_paths: list[Path]
    expected: ProcessedMidi
    candidate: ProcessedMidi
    matches: list[MidiEventMatch]
    missing: list[MidiEventAddress]
    extra: list[MidiEventAddress]
    events_equal: bool
    ordered_tracks_equal: bool
    compared_through_beat: RationalTime
    clock_differences: list[MidiClockDifference]
    maximum_clock_error_microseconds: RationalTime | None
    clock_equal: bool | None
    equivalent: bool
    diagnostics: list[Diagnostic]
    host_compatibility: Literal["unverified"] = "unverified"
    receiver_delivery: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
