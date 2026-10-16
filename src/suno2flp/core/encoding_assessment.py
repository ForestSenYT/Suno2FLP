"""Exact analysis of candidate scalar precision and unresolved source routes."""

from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue

from suno2flp.core.models import Contract, Diagnostic
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import PerformanceEventAddress, PerformancePosition, PerformanceTempo


class SignedRatio(Contract):
    numerator: int = Field(strict=True)
    denominator: int = Field(gt=0, strict=True)

    @classmethod
    def exact(cls, value: Fraction) -> "SignedRatio":
        return cls(numerator=value.numerator, denominator=value.denominator)


class TempoPrecision(Contract):
    source: PerformanceTempo
    exact: bool
    hypothetical_nearest_millibpm: int | None
    period_error_microseconds: SignedRatio | None


class UnroutedControl(Contract):
    address: PerformanceEventAddress
    source_tick: int = Field(ge=0)
    delta_ticks: int = Field(ge=0)
    position: PerformancePosition
    message: dict[str, JsonValue]


class SourceRoute(Contract):
    source_input: int = Field(ge=0)
    source_channel: int = Field(ge=0, le=15)
    source_track_positions: list[int]
    channel_event_count: int = Field(ge=0)
    controls: list[UnroutedControl]
    cross_track_same_tick_groups: list[list[PerformanceEventAddress]]
    destination: None = None
    status: Literal["unverified"] = "unverified"


class EncodingAssessment(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["fl26-encoding-assessment-v1"] = "fl26-encoding-assessment-v1"
    performance_file: FileIdentity
    performance_fingerprint: str
    input_files: list[FileIdentity]
    referenced_paths: list[Path]
    tempos: list[TempoPrecision]
    scalar_analysis_min_millibpm: Literal[60000] = 60000
    scalar_analysis_max_millibpm: Literal[240000] = 240000
    hypothetical_end_error_microseconds: SignedRatio | None
    maximum_boundary_error_microseconds: SignedRatio | None
    routes: list[SourceRoute]
    reused_source_channels: list[int]
    nonchannel_events: list[UnroutedControl]
    diagnostics: list[Diagnostic]
    timing_semantics: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
