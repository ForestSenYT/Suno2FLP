"""Original table generation for the published FLAC/LAME checksum polynomials."""


def _table(width: int, reflected: bool) -> tuple[int, ...]:
    entries = []
    for byte in range(256):
        value = byte if reflected else byte << (width - 8)
        for _ in range(8):
            if reflected:
                value = (value >> 1) ^ (0xA001 if value & 1 else 0)
            else:
                polynomial = 7 if width == 8 else 0x8005
                value = ((value << 1) ^ (polynomial if value & (1 << (width - 1)) else 0)) & (
                    (1 << width) - 1
                )
        entries.append(value)
    return tuple(entries)


_CRC8 = _table(8, False)
_CRC16 = _table(16, False)
_LAME_CRC = _table(16, True)


def flac_crc8(raw: bytes) -> int:
    result = 0
    for value in raw:
        result = _CRC8[result ^ value]
    return result


def _crc16_be(raw: bytes, initial: int) -> int:
    result = initial
    for value in raw:
        result = ((result << 8) & 65535) ^ _CRC16[(result >> 8) ^ value]
    return result


def flac_crc16(raw: bytes) -> int:
    return _crc16_be(raw, 0)


def mpeg_crc16(raw: bytes) -> int:
    return _crc16_be(raw, 65535)


def lame_crc16(raw: bytes, initial: int = 0) -> int:
    result = initial
    for value in raw:
        result = (result >> 8) ^ _LAME_CRC[(result ^ value) & 255]
    return result
