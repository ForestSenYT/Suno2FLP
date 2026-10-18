"""Strict bounded note-only SMF framing shared by inferred MIDI verifiers."""

import struct

MidiStream = list[tuple[int, dict[str, str | int]]]


def _vlq(raw: bytes, cursor: int, end: int) -> tuple[int, int]:
    value = 0
    for count in range(4):
        if cursor >= end:
            raise ValueError("Truncated MIDI variable-length quantity")
        byte = raw[cursor]
        cursor += 1
        if count == 0 and byte == 0x80:
            raise ValueError("Noncanonical MIDI variable-length quantity")
        value = value * 128 + (byte & 127)
        if byte < 128:
            return value, cursor
    raise ValueError("MIDI variable-length quantity exceeds four bytes")


def _track_bytes(raw: bytes, cursor: int, end: int) -> None:
    running: int | None = None
    while cursor < end:
        _, cursor = _vlq(raw, cursor, end)
        if cursor == end:
            raise ValueError("MIDI delta lacks an event")
        status = raw[cursor]
        if status >= 128:
            cursor += 1
        elif running is not None:
            status = running
        else:
            raise ValueError("MIDI data lacks a channel status")
        if status == 0xFF:
            running = None
            if cursor == end:
                raise ValueError("Truncated MIDI meta type")
            kind = raw[cursor]
            size, cursor = _vlq(raw, cursor + 1, end)
            if cursor + size > end:
                raise ValueError("Truncated MIDI meta payload")
            if kind not in (3, 0x2F, 0x51) or (kind == 0x51 and size != 3):
                raise ValueError("Unexpected MIDI preview metadata or payload size")
            if kind == 0x2F:
                if size != 0 or cursor != end:
                    raise ValueError("MIDI end-of-track must be empty and final")
                return
            cursor += size
        else:
            if status >> 4 not in (8, 9) or cursor + 2 > end:
                raise ValueError("Unexpected or truncated MIDI preview channel event")
            if any(byte >= 128 for byte in raw[cursor : cursor + 2]):
                raise ValueError("MIDI note data must use seven-bit bytes")
            running = status
            cursor += 2
    raise ValueError("MIDI track lacks an explicit end-of-track")


def verify_note_smf(raw: bytes, *, tracks: int) -> None:
    if len(raw) > 8 * 1024**2 or len(raw) < 14:
        raise ValueError("MIDI must retain the complete bounded SMF")
    if raw[:4] != b"MThd" or struct.unpack(">IHHH", raw[4:14]) != (6, 1, tracks, 960):
        raise ValueError("Unexpected MIDI header or technical clock")
    cursor = 14
    for _ in range(tracks):
        if cursor + 8 > len(raw) or raw[cursor : cursor + 4] != b"MTrk":
            raise ValueError("Missing complete MIDI track framing")
        size = int.from_bytes(raw[cursor + 4 : cursor + 8], "big")
        cursor += 8 + size
        if cursor > len(raw):
            raise ValueError("Truncated MIDI track")
        _track_bytes(raw, cursor - size, cursor)
    if cursor != len(raw):
        raise ValueError("Unexpected trailing MIDI bytes")
