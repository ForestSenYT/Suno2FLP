"""Lossless bounded source snapshots; malformed envelopes cannot expand unbounded."""

import base64
import hashlib
import zlib

import pytest

from suno2flp.core.drum_snapshot import decode_snapshot, encode_snapshot


def test_snapshot_roundtrip_retains_every_byte_and_reduces_repeated_metadata():
    raw = b'{"source":"unchanged","events":[1,2,3]}\n' * 1000
    wire = encode_snapshot(raw)
    assert decode_snapshot(wire) == raw
    assert len(wire["data"]) < len(raw)
    assert wire["sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "change", ["size", "hash", "encoding", "base64", "truncated", "extra", "bomb", "boolean"]
)
def test_corrupt_or_ambiguous_envelope_rejected(change):
    wire = encode_snapshot(b"original metadata" * 100)
    if change == "size":
        wire["uncompressed_bytes"] += 1
    elif change == "hash":
        wire["sha256"] = "0" * 64
    elif change == "encoding":
        wire["encoding"] = "pickle"
    elif change == "base64":
        wire["data"] = "!invalid!"
    elif change == "truncated":
        wire["data"] = base64.b64encode(zlib.compress(b"x")[:-1]).decode()
    elif change == "extra":
        wire["data"] = base64.b64encode(zlib.compress(b"x") + b"trailing").decode()
    elif change == "boolean":
        wire["uncompressed_bytes"] = True
    else:
        wire["uncompressed_bytes"] = 1
    with pytest.raises(ValueError):
        decode_snapshot(wire)
