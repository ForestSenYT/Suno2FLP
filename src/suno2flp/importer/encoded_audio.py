"""Read-only, bounded complete snapshots for supported compressed-container scanning."""

import hashlib
import stat
import time
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Literal, NoReturn, cast

from suno2flp.core.audio_decode import PCM_PASS_SECONDS, check_decode_request
from suno2flp.core.audio_input import MAX_AUDIO_BYTES, AudioPreflightError
from suno2flp.core.encoded_audio import EncodedAudioInventory, EncodedRegion, FlacStreamInfo
from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import guarded_path, verify_inputs
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime
from suno2flp.importer.flac_frames import scan_flac_frames
from suno2flp.importer.mp3_frames import scan_mp3


def _snapshot(path: Path) -> tuple[FileIdentity, bytes]:
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise OfflineError("offline_input_invalid", "Expected a regular compressed file")
    if before.st_size > MAX_AUDIO_BYTES:
        raise AudioPreflightError("audio_limits_exceeded", "Input exceeds 1 GiB", blocked=True)
    with path.open("rb") as stream:
        raw = stream.read(MAX_AUDIO_BYTES + 1)
    after = path.stat()
    if len(raw) > MAX_AUDIO_BYTES:
        raise AudioPreflightError("audio_limits_exceeded", "Input grew beyond 1 GiB", blocked=True)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(raw) != after.st_size:
        raise OfflineError(
            "offline_input_changed", "Compressed input changed during bounded capture"
        )
    return FileIdentity(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        mtime_ns=after.st_mtime_ns,
    ), raw


def _flac(raw: bytes, source: FileIdentity, check: Callable[[], None]) -> EncodedAudioInventory:
    def invalid(message: str) -> NoReturn:
        raise AudioPreflightError("audio_invalid", message)

    if raw[:4] != b"fLaC":
        invalid("Expected a native FLAC marker")
    offset = 4
    metadata: list[EncodedRegion] = []
    stream = b""
    while True:
        check()
        if len(metadata) >= 1000:
            raise AudioPreflightError(
                "audio_limits_exceeded", "Too many FLAC metadata blocks", blocked=True
            )
        if offset + 4 > len(raw):
            invalid("Truncated complete FLAC metadata header")
        tag = raw[offset]
        kind = tag & 127
        size = int.from_bytes(raw[offset + 1 : offset + 4], "big")
        end = offset + 4 + size
        if kind == 127 or end > len(raw) or (not metadata and kind != 0):
            invalid("Invalid FLAC metadata type/order/extent")
        if kind == 0:
            if stream or size != 34:
                invalid("Expected one first complete 34-byte FLAC stream-info block")
            stream = raw[offset + 4 : end]
        metadata.append(
            EncodedRegion(
                kind=f"flac-{kind}",
                offset=offset,
                size_bytes=end - offset,
                sha256=hashlib.sha256(memoryview(raw)[offset:end]).hexdigest(),
            )
        )
        offset = end
        if tag & 128:
            break
    minimum, maximum = int.from_bytes(stream[:2], "big"), int.from_bytes(stream[2:4], "big")
    if not 16 <= minimum <= maximum <= 65535:
        invalid("Invalid FLAC block size range")
    timing = int.from_bytes(stream[10:18], "big")
    rate, channels, depth, frames = (
        timing >> 44,
        ((timing >> 41) & 7) + 1,
        ((timing >> 36) & 31) + 1,
        timing & ((1 << 36) - 1),
    )
    if channels not in (1, 2) or not 8000 <= rate <= 192000 or frames > rate * 600:
        raise AudioPreflightError(
            "audio_limits_exceeded", "Unsupported FLAC clock/channel/duration", blocked=True
        )
    if depth not in (8, 16, 24) or frames == 0 or stream[18:] == b"\0" * 16:
        raise AudioPreflightError(
            "audio_codec_unavailable",
            "FLAC requires supported depth, known length and MD5",
            blocked=True,
        )
    count, digest = scan_flac_frames(
        raw,
        offset,
        rate=rate,
        channels=channels,
        depth=depth,
        total=frames,
        minimum_block=minimum,
        maximum_block=maximum,
        minimum_bytes=int.from_bytes(stream[4:7], "big"),
        maximum_bytes=int.from_bytes(stream[7:10], "big"),
        check=check,
    )
    return EncodedAudioInventory(
        source=source,
        codec="FLAC",
        sample_rate=rate,
        channels=channels,
        frames=frames,
        frame_count=count,
        data_offset=offset,
        data_end=len(raw),
        frame_headers_sha256=digest,
        metadata=metadata,
        flac=FlacStreamInfo(
            raw_streaminfo_hex=stream.hex(),
            bits_per_sample=cast(Literal[8, 16, 24], depth),
            pcm_md5=stream[18:].hex(),
            min_block_frames=minimum,
            max_block_frames=maximum,
        ),
        duration_microseconds=RationalTime.exact(Fraction(frames * 1_000_000, rate)),
    )


def inspect_encoded_audio(
    source: Path, *, should_cancel: Callable[[], bool] | None = None
) -> EncodedAudioInventory:
    deadline = time.monotonic() + PCM_PASS_SECONDS

    def check() -> None:
        check_decode_request(should_cancel, deadline)

    check()
    path = guarded_path(source)
    if path.suffix.lower() not in (".flac", ".mp3"):
        raise AudioPreflightError(
            "audio_format_unavailable",
            "Only qualified FLAC/MP3 containers are supported",
            blocked=True,
        )
    if path.stat().st_size > MAX_AUDIO_BYTES:
        raise AudioPreflightError("audio_limits_exceeded", "Input exceeds 1 GiB", blocked=True)
    # One bounded immutable snapshot avoids unsafe mutable-file mappings during bit parsing.
    identity, raw = _snapshot(path)
    check()
    result = (
        _flac(raw, identity, check)
        if path.suffix.lower() == ".flac"
        else scan_mp3(raw, identity, check)
    )
    check()
    verify_inputs([identity])
    return result
