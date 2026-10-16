"""Separate selected-field observations; no change to historical inventories."""

from typing import Literal

from pydantic import Field

from suno2flp.core.models import Contract, Diagnostic
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.template_inventory import Digest, HexBytes, Index, RecordEvidence


class PatternControlRecord(RecordEvidence):
    pattern_id: Index | None
    position_raw: int = Field(ge=0, le=0xFFFFFFFF)
    address_raw: int = Field(ge=0, le=0xFFFFFFFF)
    value_u32: int = Field(ge=0, le=0xFFFFFFFF)
    value_i32: int = Field(ge=-(2**31), lt=2**31)
    observation: Literal["tempo_millibpm", "native_channel_zero_volume", "unverified"]


class PatternControlPayload(Contract):
    event_index: Index
    payload_offset: Index
    raw_hex: HexBytes
    tail_hex: HexBytes


class PatternControlInspection(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["fl26-pattern-control-observations-v1"] = (
        "fl26-pattern-control-observations-v1"
    )
    template_sha256: Digest
    source_file: FileIdentity | None = None
    ppq: int
    events: list[PatternControlPayload]
    records: list[PatternControlRecord]
    diagnostics: list[Diagnostic]
    timing_semantics: Literal["unverified"] = "unverified"
    midi_routing: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
