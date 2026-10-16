"""Standalone isolated native worker. Only stdlib and explicit audited wheels are imported."""

import ctypes.util
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import struct
import sys
import sysconfig
from pathlib import Path
from typing import Any, BinaryIO, NoReturn


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _native(packages: Path) -> tuple[Any, Any, dict[str, Any]]:
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError("Worker requires -I -S -B")
    expected_versions = {(3, 11): "3.11.16", (3, 14): "3.14.7"}
    if (
        expected_versions.get(sys.version_info[:2]) != platform.python_version()
        or sysconfig.get_platform() not in ("win-amd64", "linux-x86_64")
        or sys.platform not in ("win32", "linux")
    ):
        raise ValueError("Worker requires the pinned application Python ABI/version")
    sys.path.insert(0, str(packages))
    np = importlib.import_module("numpy")

    def refuse_system_library(name: str) -> NoReturn:
        raise RuntimeError(f"System library fallback forbidden: {name}")

    ctypes.util.find_library = refuse_system_library
    sf = importlib.import_module("soundfile")
    native = Path(sf._full_path).resolve()
    expected = (
        packages
        / "_soundfile_data"
        / ("libsndfile_x64.dll" if sys.platform == "win32" else "libsndfile_x86_64.so")
    )
    if native != expected:
        raise ValueError("Loaded native library must be the packaged artifact")
    names = ("soundfile", "numpy", "cffi", "pycparser", "typing_extensions")
    versions = {name: importlib.metadata.version(name) for name in names}
    versions.update(soundfile=sf.__version__, numpy=np.__version__)
    probe = {
        "protocol": "soundfile-worker-v1",
        "python_version": platform.python_version(),
        "python_abi": f"cp{sys.version_info.major}{sys.version_info.minor}",
        "platform": "windows-x86_64" if sys.platform == "win32" else "linux-x86_64",
        "versions": versions,
        "libsndfile_version": sf.__libsndfile_version__,
        "native_path": str(native),
        "native_sha256": _digest(native),
        "formats": sorted(sf.available_formats()),
        "isolated": bool(sys.flags.isolated),
        "no_site": bool(sys.flags.no_site),
        "no_bytecode": bool(sys.dont_write_bytecode),
        "system_fallback": "forbidden",
    }
    return sf, np, probe


def _header(frames: int, rate: int, channels: int) -> bytes:
    size = frames * channels * 8
    return struct.pack(
        "<4sI4s4sIHHIIHHH4sII4sI",
        b"RIFF",
        50 + size,
        b"WAVE",
        b"fmt ",
        18,
        3,
        channels,
        rate,
        rate * channels * 8,
        channels * 8,
        64,
        0,
        b"fact",
        4,
        frames,
        b"data",
        size,
    )


def _audio(
    sf: Any, np: Any, probe: dict[str, Any], mode: str, arguments: list[str]
) -> dict[str, Any]:
    if len(arguments) != 8:
        raise ValueError("Expected source, PCM, codec, frame/rate/channel/depth/MD5 parameters")
    source, pcm = Path(arguments[0]), Path(arguments[1])
    codec = arguments[2]
    frames, rate, channels, depth = (int(value) for value in arguments[3:7])
    expected_md5 = arguments[7]
    if (
        codec not in ("FLAC", "MP3")
        or not 1 <= channels <= 2
        or not 8000 <= rate <= 192000
        or not 0 < frames <= rate * 600
    ):
        raise ValueError("Unqualified codec or audio limits")
    if codec == "FLAC" and depth not in (8, 16, 24):
        raise ValueError("Unsupported FLAC integer depth")
    if source.resolve() == pcm.resolve():
        raise ValueError("Source and PCM must differ")
    source_hash = _digest(source)
    sample_hash = hashlib.sha256()
    flac_hash = hashlib.md5()
    count = 0
    output: BinaryIO
    with (
        sf.SoundFile(source, "r") as original,
        pcm.open("xb" if mode == "decode" else "rb") as output,
    ):
        if (original.format, original.samplerate, original.channels, original.frames) != (
            codec,
            rate,
            channels,
            frames,
        ):
            raise ValueError("Native metadata disagrees with complete source inventory")
        header = _header(frames, rate, channels)
        if mode == "decode":
            output.write(header)
        elif output.read(58) != header:
            raise ValueError("PCM header disagrees with exact source clock")
        while True:
            block = original.read(4096, dtype="float64", always_2d=True)
            if not len(block):
                break
            count += len(block)
            if count > frames or not np.isfinite(block).all():
                raise ValueError("Native audio contains extra frames/nonfinite samples")
            data = np.asarray(block, dtype="<f8").tobytes(order="C")
            if mode == "decode":
                output.write(data)
            elif output.read(len(data)) != data:
                raise ValueError("PCM samples disagree with current native source replay")
            sample_hash.update(data)
            if codec == "FLAC":
                scaled = block * (1 << (depth - 1))
                integers = scaled.astype("<i4")
                if not np.array_equal(scaled, integers):
                    raise ValueError("Lossless FLAC samples are not exact source integers")
                packed = integers.reshape(-1).view("u1").reshape(-1, 4)[:, : depth // 8].tobytes()
                flac_hash.update(packed)
        error = sf._snd.sf_error(original._file)
        if error or count != frames:
            raise ValueError("Native read did not cover every expected source frame")
        if mode == "decode":
            output.flush()
            os.fsync(output.fileno())
        elif output.read(1):
            raise ValueError("Unexpected bytes after complete decoded PCM")
    if codec == "FLAC" and flac_hash.hexdigest() != expected_md5:
        raise ValueError("Decoded FLAC PCM MD5 disagrees with original stream info")
    if _digest(source) != source_hash:
        raise ValueError("Source changed during native operation")
    return {
        "protocol": "soundfile-audio-v1",
        "mode": mode,
        "runtime": probe,
        "codec": codec,
        "frames": count,
        "sample_rate": rate,
        "channels": channels,
        "samples_sha256": sample_hash.hexdigest(),
        "source_sha256": source_hash,
        "pcm_sha256": _digest(pcm),
        "flac_pcm_md5": flac_hash.hexdigest() if codec == "FLAC" else None,
        "native_error": 0,
    }


def main(arguments: list[str]) -> int:
    if len(arguments) < 2 or arguments[0] not in ("probe", "decode", "verify"):
        raise ValueError("Only fixed worker modes are accepted")
    mode = arguments[0]
    packages = Path(arguments[1]).resolve()
    sf, np, probe = _native(packages)
    if mode == "probe":
        if len(arguments) != 2:
            raise ValueError("Probe takes no audio arguments")
        result = probe
    else:
        result = _audio(sf, np, probe, mode, arguments[2:])
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
