"""Original read-only event-223 observations from controlled FL26 experiments."""

import hashlib
import struct
from pathlib import Path
from typing import Literal

from suno2flp.core.control_evidence import (
    PatternControlInspection,
    PatternControlPayload,
    PatternControlRecord,
)
from suno2flp.core.models import Diagnostic
from suno2flp.core.offline_files import capture_input, verify_inputs
from suno2flp.integrations.template_inventory import _framing


def inspect_controls(raw: bytes) -> PatternControlInspection:
    header, chunks, events = _framing(raw)
    if [payload for eid, _, _, payload in events if eid == 199] != [b"26.1.7.5654\0"]:
        raise ValueError("Control observations require one exact FL26 version event")
    if len(chunks) != 1 or chunks[0].id_hex != b"FLdt".hex():
        raise ValueError("Control observations require one FLdt chunk")
    records = []
    payloads = []
    pattern = None
    diagnostics = [
        Diagnostic(
            code="control_host_timing_unverified",
            severity="error",
            message=(
                "Background probes show step-timing differences; "
                "raw positions are not proof of exact playback"
            ),
        ),
        Diagnostic(
            code="control_midi_routing_unverified",
            severity="error",
            message="Native REC addresses do not establish MIDI CC/program delivery to instruments",
        ),
    ]
    for index, (eid, _, offset, payload) in enumerate(events):
        if eid == 65:
            selected = int.from_bytes(payload, "little")
            pattern = selected - 1 if selected else None
        if eid != 223:
            continue
        complete = len(payload) - len(payload) % 12
        tail = payload[complete:]
        payloads.append(
            PatternControlPayload(
                event_index=index,
                payload_offset=offset,
                raw_hex=payload.hex(),
                tail_hex=tail.hex(),
            )
        )
        if tail:
            diagnostics.append(
                Diagnostic(
                    code="control_record_alignment",
                    severity="error",
                    event_index=index,
                    message=(
                        "Partial 12-byte record retained; "
                        "this payload has no interpreted observations"
                    ),
                )
            )
        for position in range(0, complete, 12):
            record = payload[position : position + 12]
            tick, address, value = struct.unpack("<III", record)
            observation: Literal["tempo_millibpm", "native_channel_zero_volume", "unverified"] = (
                "unverified"
            )
            if not tail and pattern is not None and tick < 2**31 and header.ppq in {96, 960}:
                observed_tempos = {60000, 120000, 240000}
                if header.ppq == 96:
                    observed_tempos.add(120001)
                if address == 0x40000005 and value in observed_tempos:
                    observation = "tempo_millibpm"
                elif address == 0 and value in {0, 12800} and header.ppq == 96:
                    observation = "native_channel_zero_volume"
            records.append(
                PatternControlRecord(
                    event_index=index,
                    record_index=position // 12,
                    file_offset=offset + position,
                    raw_hex=record.hex(),
                    pattern_id=pattern,
                    position_raw=tick,
                    address_raw=address,
                    value_u32=value,
                    value_i32=struct.unpack_from("<i", record, 8)[0],
                    observation=observation,
                )
            )
    return PatternControlInspection(
        template_sha256=hashlib.sha256(raw).hexdigest(),
        ppq=header.ppq,
        events=payloads,
        records=records,
        diagnostics=diagnostics,
    )


def inspect_controls_file(path: Path) -> PatternControlInspection:
    identity, raw = capture_input(path)
    report = inspect_controls(raw)
    report.source_file = identity
    verify_inputs([identity])
    return report
