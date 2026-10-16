"""Explicit MIDI destination declarations; no receiver or writer authorization."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from suno2flp.core.encoding_assessment import EncodingAssessment, SourceRoute
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity


class MidiRouteBinding(Contract):
    source_input: int = Field(ge=0, strict=True)
    source_channel: int = Field(ge=0, le=15, strict=True)
    destination_port: int = Field(ge=0, le=255, strict=True)
    destination_channel: int = Field(ge=0, le=15, strict=True)
    receiver_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$", strict=True)


class MidiRoutingConfig(Contract):
    schema_version: Literal[1] = 1
    bindings: list[MidiRouteBinding]


class PlannedMidiRoute(Contract):
    binding: MidiRouteBinding
    source: SourceRoute
    receiver_delivery: Literal["unverified"] = "unverified"


class MidiRoutingPlan(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["explicit-midi-routing-v1"] = "explicit-midi-routing-v1"
    bindings_file: FileIdentity
    config: MidiRoutingConfig
    assessment: EncodingAssessment
    routes: list[PlannedMidiRoute]
    input_files: list[FileIdentity]
    referenced_paths: list[Path]
    coverage_complete: Literal[True] = True
    receiver_delivery: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
