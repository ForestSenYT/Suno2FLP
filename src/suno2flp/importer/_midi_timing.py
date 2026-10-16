"""Source delta verification for mido's unknown-metadata timing compatibility gap.

This reads SMF framing/timing only; mido still decodes and validates message payloads.
No third-party parser state is patched and no source bytes are modified.
"""

import io
import struct


def _read(stream: io.BytesIO, count: int) -> bytes:
    data = stream.read(count)
    if len(data) != count:
        raise ValueError("Truncated MIDI timing data")
    return data


def _variable_int(stream: io.BytesIO) -> int:
    value = 0
    for _ in range(4):
        byte = _read(stream, 1)[0]
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value
    raise ValueError("SMF variable-length integer exceeds four bytes")


def _track_deltas(data: bytes) -> list[int]:
    stream = io.BytesIO(data)
    deltas: list[int] = []
    running_status: int | None = None
    system_lengths = {
        0xF1: 1,
        0xF2: 2,
        0xF3: 1,
        0xF6: 0,
        0xF8: 0,
        0xFA: 0,
        0xFB: 0,
        0xFC: 0,
        0xFE: 0,
    }
    while stream.tell() < len(data):
        deltas.append(_variable_int(stream))
        first = _read(stream, 1)[0]
        consumed = 0
        if first < 0x80:
            if running_status is None:
                raise ValueError("MIDI running status has no preceding status")
            status = running_status
            consumed = 1
        else:
            status = first
            if 0x80 <= status <= 0xEF:
                running_status = status
            elif status in {0xF0, 0xF7}:
                running_status = None
        if status == 0xFF:
            _read(stream, 1)  # Meta type; payload interpretation belongs to mido.
            _read(stream, _variable_int(stream))
        elif status in {0xF0, 0xF7}:
            _read(stream, _variable_int(stream))
        elif 0x80 <= status <= 0xEF:
            size = 1 if status >> 4 in {0xC, 0xD} else 2
            _read(stream, size - consumed)
        elif status in system_lengths:
            _read(stream, system_lengths[status] - consumed)
        else:
            raise ValueError(f"Unsupported MIDI status byte: {status:#x}")
    return deltas


def source_deltas(raw: bytes) -> list[list[int]]:
    """Read deltas directly from MTrk chunks without interpreting musical messages."""
    stream = io.BytesIO(raw)
    if _read(stream, 4) != b"MThd":
        raise ValueError("Missing MIDI header")
    header_size = struct.unpack(">I", _read(stream, 4))[0]
    header = _read(stream, header_size)
    if header_size < 6:
        raise ValueError("Truncated MIDI header")
    _, tracks, _ = struct.unpack(">HHH", header[:6])
    result = []
    for _ in range(tracks):
        if _read(stream, 4) != b"MTrk":
            raise ValueError("Missing MIDI track chunk")
        size = struct.unpack(">I", _read(stream, 4))[0]
        result.append(_track_deltas(_read(stream, size)))
    return result
