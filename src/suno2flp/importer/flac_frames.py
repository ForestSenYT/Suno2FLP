"""Complete FLAC structure/CRC walk; does not reconstruct sample predictions."""

import hashlib
import struct
from collections.abc import Callable
from typing import NoReturn

from suno2flp.core.audio_input import AudioPreflightError
from suno2flp.importer.encoded_checksums import flac_crc8, flac_crc16


def _invalid(message: str) -> NoReturn:
    raise AudioPreflightError("audio_invalid", message)


class _Bits:
    def __init__(self, raw: bytes, offset: int, limit: int) -> None:
        self.raw, self.position, self.limit = raw, offset * 8, min(limit, len(raw)) * 8
        self.budget_limited = limit < len(raw)

    def skip(self, count: int) -> None:
        if count < 0 or self.position + count > self.limit:
            if count >= 0 and self.budget_limited:
                raise AudioPreflightError(
                    "audio_limits_exceeded", "FLAC frame exceeds 4 MiB parsing budget", blocked=True
                )
            _invalid("FLAC bitstream exceeds its complete frame/input boundary")
        self.position += count

    def read(self, count: int) -> int:
        start = self.position
        self.skip(count)
        if count == 0:
            return 0
        value = int.from_bytes(self.raw[start // 8 : (self.position + 7) // 8], "big")
        return (value >> (-self.position % 8)) & ((1 << count) - 1)

    def unary(self) -> int:
        total = 0
        while self.position < self.limit:
            available = 8 - self.position % 8
            value = self.raw[self.position // 8] & ((1 << available) - 1)
            zeros = available - value.bit_length()
            self.skip(zeros)
            total += zeros
            if value:
                self.skip(1)
                return total
        if self.budget_limited:
            raise AudioPreflightError(
                "audio_limits_exceeded", "FLAC unary parsing exceeds frame budget", blocked=True
            )
        _invalid("Unterminated FLAC unary value")
        return 0


def _number(bits: _Bits, variable: bool) -> int:
    first = bits.read(8)
    if first < 128:
        return first
    leading = 8 - (first ^ 255).bit_length()
    if not 2 <= leading <= (7 if variable else 6):
        _invalid("Invalid FLAC coded frame/sample number")
    value = first & ((1 << (7 - leading)) - 1)
    for _ in range(leading - 1):
        byte = bits.read(8)
        if byte & 192 != 128:
            _invalid("Invalid FLAC number continuation")
        value = value * 64 + (byte & 63)
    if value < (1 << (7 if leading == 2 else 5 * leading - 4)):
        _invalid("Overlong FLAC number")
    if value >= 1 << (36 if variable else 31):
        _invalid("FLAC frame/sample number overflows its field")
    return value


def _residual(bits: _Bits, block: int, order: int, check: Callable[[], None]) -> None:
    method = bits.read(2)
    if method > 1:
        _invalid("Reserved FLAC residual coding method")
    partitions = 1 << bits.read(4)
    if block % partitions or block // partitions < order:
        _invalid("FLAC residual partition does not account for warmup samples")
    width = 4 + method
    for partition in range(partitions):
        check()
        count = block // partitions - (order if partition == 0 else 0)
        parameter = bits.read(width)
        if parameter == (1 << width) - 1:
            bits.skip(count * bits.read(5))
        else:
            for sample in range(count):
                if sample % 4096 == 0:
                    check()
                quotient = bits.unary()
                if quotient > 0xFFFFFFFF >> parameter:
                    _invalid("FLAC residual exceeds the supported 32-bit coding range")
                bits.skip(parameter)


def _subframe(bits: _Bits, depth: int, block: int, check: Callable[[], None]) -> None:
    if bits.read(1):
        _invalid("FLAC subframe reserved bit must be zero")
    kind = bits.read(6)
    if bits.read(1):
        depth -= bits.unary() + 1
    if depth <= 0:
        _invalid("FLAC wasted bits consume the complete sample depth")
    if kind == 0:
        bits.skip(depth)
    elif kind == 1:
        bits.skip(depth * block)
    elif 8 <= kind <= 12 or kind >= 32:
        order = kind - 8 if kind < 32 else kind - 31
        if order > block:
            _invalid("FLAC predictor order exceeds available samples")
        bits.skip(depth * order)
        if kind >= 32:
            precision = bits.read(4) + 1
            if precision == 16 or bits.read(5) & 16:
                _invalid("Invalid FLAC LPC coefficient precision/negative shift")
            bits.skip(order * precision)
        _residual(bits, block, order, check)
    else:
        _invalid("Reserved FLAC subframe type")


def scan_flac_frames(
    raw: bytes,
    offset: int,
    *,
    rate: int,
    channels: int,
    depth: int,
    total: int,
    minimum_block: int,
    maximum_block: int,
    minimum_bytes: int,
    maximum_bytes: int,
    check: Callable[[], None],
) -> tuple[int, str]:
    count = 0
    decoded = 0
    digest = hashlib.sha256()
    previous_block = 0
    fixed_block: int | None = None
    strategy: bool | None = None
    while offset < len(raw):
        check()
        if count >= 1_000_000:
            raise AudioPreflightError("audio_limits_exceeded", "Too many FLAC frames", blocked=True)
        start = offset
        bits = _Bits(raw, start, start + 4 * 1024**2)
        if bits.read(15) != 0x7FFC:
            _invalid("Invalid FLAC frame sync, trailing bytes or concatenated stream")
        variable = bool(bits.read(1))
        if strategy is not None and strategy != variable:
            _invalid("Changing FLAC blocking strategy")
        strategy = variable
        block_code, rate_code = bits.read(4), bits.read(4)
        assignment, depth_code = bits.read(4), bits.read(3)
        if bits.read(1) or block_code == 0 or rate_code == 15 or assignment > 10 or depth_code == 3:
            _invalid("Reserved FLAC frame header fields")
        number = _number(bits, variable)
        if number != (decoded if variable else count):
            _invalid("FLAC frame/sample numbering is not contiguous from zero")
        if block_code == 1:
            block = 192
        elif block_code in (6, 7):
            block = bits.read(8 if block_code == 6 else 16) + 1
        elif block_code < 6:
            block = 576 << (block_code - 2)
        else:
            block = 256 << (block_code - 8)
        declared_rate = (
            (rate, 88200, 176400, 192000, 8000, 16000, 22050, 24000, 32000, 44100, 48000, 96000)[
                rate_code
            ]
            if rate_code < 12
            else bits.read(8 if rate_code == 12 else 16)
            * (1000 if rate_code == 12 else 10 if rate_code == 14 else 1)
        )
        declared_depth = (depth, 8, 12, 0, 16, 20, 24, 32)[depth_code]
        if (
            declared_rate != rate
            or declared_depth != depth
            or (assignment + 1 if assignment < 8 else 2) != channels
        ):
            _invalid("Changing FLAC sample rate/depth/channel configuration")
        header_end = bits.position // 8
        if bits.read(8) != flac_crc8(raw[start:header_end]):
            _invalid("FLAC frame header CRC mismatch")
        header_end += 1
        if block > maximum_block or decoded + block > total:
            _invalid("FLAC frame block exceeds declared frame total/block maximum")
        if count and previous_block < minimum_block:
            _invalid("Only the last FLAC block may be shorter than the minimum")
        if not variable:
            if fixed_block is None:
                fixed_block = block
            elif block > fixed_block or (previous_block != fixed_block and count > 1):
                _invalid("FLAC fixed blocks changed before the final frame")
        for channel in range(channels):
            side = (
                (assignment == 8 and channel == 1)
                or (assignment == 9 and channel == 0)
                or (assignment == 10 and channel == 1)
            )
            _subframe(bits, depth + int(side), block, check)
        padding = -bits.position % 8
        if bits.read(padding):
            _invalid("Nonzero FLAC frame alignment padding")
        footer = bits.position // 8
        expected_crc = bits.read(16)
        if flac_crc16(raw[start:footer]) != expected_crc:
            _invalid("FLAC complete frame CRC mismatch")
        offset = bits.position // 8
        size = offset - start
        if (minimum_bytes and size < minimum_bytes) or (maximum_bytes and size > maximum_bytes):
            _invalid("FLAC frame bytes disagree with stream-info bounds")
        digest.update(struct.pack("<QQ", start, size) + raw[start:header_end])
        count += 1
        decoded += block
        previous_block = block
    if not count or decoded != total:
        _invalid("Complete FLAC frames disagree with declared sample total")
    return count, digest.hexdigest()
