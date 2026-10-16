"""Bounded read-only RIFF/PCM preflight, retaining complete original file identity."""

import hashlib
import struct
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO, NoReturn

from suno2flp.core.audio_input import (
    MAX_AUDIO_BYTES,
    MAX_AUDIO_SECONDS,
    AudioPreflightError,
    AudioPreflightReport,
    WaveChunk,
)
from suno2flp.core.offline_files import capture_stream_input, guarded_path, verify_inputs
from suno2flp.core.performance import RationalTime


def _invalid(message: str) -> NoReturn:
    raise AudioPreflightError("audio_invalid", message)


def _read(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        _invalid("Truncated WAVE chunk")
    return data


def inspect_audio(path: Path) -> AudioPreflightReport:
    source_path = guarded_path(path)
    if source_path.stat().st_size > MAX_AUDIO_BYTES:
        raise AudioPreflightError("audio_limits_exceeded", "Input exceeds 1 GiB", blocked=True)
    source = capture_stream_input(source_path)
    if source_path.suffix.lower() != ".wav":
        raise AudioPreflightError(
            "audio_format_unavailable", "Only integer PCM WAVE preflight is available", blocked=True
        )
    chunks: list[WaveChunk] = []
    fmt: bytes | None = None
    data_size: int | None = None
    data_offset = 0
    digest = hashlib.sha256()
    with source_path.open("rb") as stream:
        header = _read(stream, 12)
        if header[:4] in (b"RF64", b"RIFX"):
            raise AudioPreflightError(
                "audio_format_unavailable", "RF64 and big-endian RIFF are unavailable", blocked=True
            )
        if header[:4] != b"RIFF" or header[8:] != b"WAVE":
            _invalid("Expected a RIFF WAVE container")
        if struct.unpack_from("<I", header, 4)[0] + 8 != source.size_bytes:
            _invalid("RIFF length must account for the entire original file")
        while stream.tell() < source.size_bytes:
            if len(chunks) >= 10000:
                raise AudioPreflightError(
                    "audio_limits_exceeded", "Too many RIFF chunks", blocked=True
                )
            offset = stream.tell()
            tag, size = struct.unpack("<4sI", _read(stream, 8))
            end = stream.tell() + size + size % 2
            if end > source.size_bytes:
                _invalid("Chunk payload or padding exceeds the RIFF boundary")
            chunks.append(WaveChunk(id_hex=tag.hex(), offset=offset, data_size=size))
            if tag == b"fmt ":
                if fmt is not None or not 16 <= size <= 65536:
                    _invalid("Expected one bounded WAVE format chunk")
                fmt = _read(stream, size)
            elif tag == b"data":
                if data_size is not None:
                    _invalid("Multiple data chunks are not supported")
                data_size, data_offset = size, stream.tell()
                remaining = size
                while remaining:
                    block = _read(stream, min(remaining, 1024**2))
                    digest.update(block)
                    remaining -= len(block)
            stream.seek(end)
    verify_inputs([source])
    if fmt is None or data_size is None or data_size == 0:
        _invalid("WAVE needs one format chunk and nonempty data")
    tag, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", fmt)
    if tag != 1:
        raise AudioPreflightError(
            "audio_codec_unavailable", "Only integer PCM is qualified for preflight", blocked=True
        )
    if channels not in (1, 2) or not 8000 <= rate <= 192000:
        raise AudioPreflightError(
            "audio_limits_exceeded", "Expected mono/stereo at 8–192 kHz", blocked=True
        )
    if bits not in (8, 16, 24, 32) or align != channels * (bits // 8) or byte_rate != rate * align:
        _invalid("PCM width, block alignment or byte rate is inconsistent")
    if data_size % align:
        _invalid("Partial PCM frames cannot be discarded")
    frames = data_size // align
    if frames > rate * MAX_AUDIO_SECONDS:
        raise AudioPreflightError(
            "audio_limits_exceeded", "Input exceeds ten minutes", blocked=True
        )
    return AudioPreflightReport(
        source=source,
        channels=channels,
        sample_width_bytes=bits // 8,
        sample_rate=rate,
        frames=frames,
        data_offset=data_offset,
        data_bytes=data_size,
        pcm_sha256=digest.hexdigest(),
        chunks=chunks,
        duration_microseconds=RationalTime.exact(Fraction(frames * 1_000_000, rate)),
    )
