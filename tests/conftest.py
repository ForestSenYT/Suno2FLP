import struct
import wave
from pathlib import Path

import pytest


@pytest.fixture
def media(tmp_path: Path) -> Path:
    root = tmp_path / "assets"
    root.mkdir()
    # SMF type 0, one track: note-on, note-off at 480 ticks, end-of-track.
    track = bytes.fromhex("00903c408360803c0000ff2f00")
    (root / "Piano.MID").write_bytes(
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, 480)
        + b"MTrk"
        + struct.pack(">I", len(track))
        + track
    )
    with wave.open(str(root / "piano.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\x00\x00" * 800)
    return root
