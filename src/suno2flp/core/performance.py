"""Lossless performance requirements, never an executable FLP write intent."""

from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import Field

from suno2flp.core.models import Arrangement, Contract, Diagnostic, TempoEvent
from suno2flp.core.offline_models import FileIdentity


class RationalTime(Contract):
    numerator: int = Field(ge=0, strict=True)
    denominator: int = Field(gt=0, strict=True)

    @classmethod
    def exact(cls, value: Fraction) -> "RationalTime":
        return cls(numerator=value.numerator, denominator=value.denominator)


class PerformancePosition(Contract):
    target_tick: RationalTime
    elapsed_microseconds: RationalTime


class PerformanceEvent(Contract):
    # Original message/delta/tick are in arrangement.sources, not rewritten here.
    source_event_index: int = Field(ge=0)
    position: PerformancePosition


class PerformanceTrack(Contract):
    source_input: int = Field(ge=0)
    source_track_position: int = Field(ge=0)
    source_track_index: int = Field(ge=0)
    events: list[PerformanceEvent]
    end: PerformancePosition


class PerformanceEventAddress(Contract):
    source_input: int = Field(ge=0)
    source_track_position: int = Field(ge=0)
    source_event_index: int = Field(ge=0)
    event_type: str
    source_channel: int | None = Field(default=None, ge=0, le=15)


class PerformanceNote(Contract):
    arrangement_track_position: int = Field(ge=0)
    note_index: int = Field(ge=0)
    start: PerformancePosition
    end: PerformancePosition


class PerformanceTempo(Contract):
    source: TempoEvent
    position: PerformancePosition
    milli_bpm: RationalTime
    exact_milli_bpm: int | None = None


class PerformancePlan(Contract):
    schema_version: Literal[1] = 1
    algorithm_version: Literal[1] = 1
    profile: Literal["fl26-performance-requirements-v1"] = "fl26-performance-requirements-v1"
    status: Literal["analysis_only"] = "analysis_only"
    arrangement_file: FileIdentity
    arrangement_fingerprint: str
    arrangement: Arrangement
    input_files: list[FileIdentity]
    referenced_paths: list[Path]
    target_ppq: int = Field(ge=1, le=65535, strict=True)
    source_verified: Literal[True] = True
    target_grid_exact: bool
    tempo_scalar_exact: bool
    tracks: list[PerformanceTrack]
    notes: list[PerformanceNote]
    tempos: list[PerformanceTempo]
    untranslated_events: list[PerformanceEventAddress]
    event_type_counts: dict[str, int]
    diagnostics: list[Diagnostic]
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
