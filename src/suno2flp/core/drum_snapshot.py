"""Lossless bounded metadata envelopes; hashes/encoding grant no source authority."""

import base64
import binascii
import hashlib
import zlib

from pydantic import JsonValue

MAX_SNAPSHOT_BYTES = 32 * 1024**2


def encode_snapshot(raw: bytes) -> dict[str, JsonValue]:
    if not 0 < len(raw) <= MAX_SNAPSHOT_BYTES:
        raise ValueError("Complete drum source snapshot exceeds its32MiB budget")
    return dict(
        encoding="zlib-base64-json-v1",
        uncompressed_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        data=base64.b64encode(zlib.compress(raw, level=9)).decode("ascii"),
    )


def decode_snapshot(value: object) -> bytes:
    if not isinstance(value, dict) or set(value) != {
        "encoding",
        "uncompressed_bytes",
        "sha256",
        "data",
    }:
        raise ValueError("Drum snapshot needs one exact complete envelope")
    size = value["uncompressed_bytes"]
    data = value["data"]
    if (
        value["encoding"] != "zlib-base64-json-v1"
        or type(size) is not int
        or not 0 < size <= MAX_SNAPSHOT_BYTES
        or not isinstance(data, str)
        or len(data) > MAX_SNAPSHOT_BYTES * 2
        or not isinstance(value["sha256"], str)
    ):
        raise ValueError("Unsupported or over-budget drum snapshot envelope")
    try:
        blob = base64.b64decode(data, validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(blob, size + 1)
    except (ValueError, binascii.Error, zlib.error) as error:
        raise ValueError("Corrupt drum snapshot encoding") from error
    if (
        len(raw) != size
        or not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
        or hashlib.sha256(raw).hexdigest() != value["sha256"]
    ):
        raise ValueError("Complete drum snapshot size/hash/stream differs from envelope")
    return raw
