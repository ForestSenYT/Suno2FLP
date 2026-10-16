"""Pinned isolated audio runtime and bounded child protocol contracts."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.audio_input import AudioPreflightError
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity


class CodecProcessError(AudioPreflightError):
    def __init__(self, code: str, message: str, stdout: bytes = b"", stderr: bytes = b"") -> None:
        super().__init__(code, message)
        self.stdout, self.stderr = stdout, stderr


class CodecCancelled(DecodeCancelled):
    def __init__(self, stdout: bytes, stderr: bytes) -> None:
        super().__init__()
        self.stdout, self.stderr = stdout, stderr


class CodecWheelPin(Contract):
    distribution: str = Field(pattern=r"^[a-z_]+$")
    version: str = Field(pattern=r"^[0-9.]+$")
    filename: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.whl$")
    url: str = Field(pattern=r"^https://files\.pythonhosted\.org/packages/[A-Za-z0-9/_.-]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0, le=64 * 1024**2, strict=True)


class CodecPlatformPin(Contract):
    native_filename: str = Field(pattern=r"^libsndfile_[A-Za-z0-9_]+\.(?:dll|so)$")
    native_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    wheels: list[CodecWheelPin]


class CodecPins(Contract):
    schema_version: Literal[1] = 1
    python_versions: dict[str, str]
    soundfile_revision: Literal["3162358d0315be769b97f3e4c12545fe18a676bc"]
    native_revision: Literal["a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87"]
    platforms: dict[str, CodecPlatformPin]

    @model_validator(mode="after")
    def complete_platforms(self) -> Self:
        if self.python_versions != {"cp311": "3.11.16", "cp314": "3.14.7"} or set(
            self.platforms
        ) != {
            f"{host}-{abi}"
            for host in ("windows-x86_64", "linux-x86_64")
            for abi in self.python_versions
        }:
            raise ValueError("Expected exact qualified platform pins")
        expected = {
            "soundfile": "0.14.0",
            "numpy": "2.3.5",
            "cffi": "2.0.0",
            "pycparser": "2.23",
            "typing_extensions": "4.16.0",
        }
        for profile in self.platforms.values():
            if (
                len(profile.wheels) != 5
                or {w.distribution: w.version for w in profile.wheels} != expected
            ):
                raise ValueError("Every native runtime dependency must be exactly pinned")
            if len({w.filename.casefold() for w in profile.wheels}) != 5:
                raise ValueError("Wheel names must be unique")
        return self


class CodecProbe(Contract):
    protocol: Literal["soundfile-worker-v1"] = "soundfile-worker-v1"
    python_version: Literal["3.11.16", "3.14.7"]
    python_abi: Literal["cp311", "cp314"]
    platform: Literal["windows-x86_64", "linux-x86_64"]
    versions: dict[str, str]
    libsndfile_version: Literal["1.2.2"]
    native_path: Path
    native_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    formats: list[str]
    isolated: Literal[True]
    no_site: Literal[True]
    no_bytecode: Literal[True]
    system_fallback: Literal["forbidden"]


class CodecBackendRecord(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["isolated-soundfile-runtime-v1"] = "isolated-soundfile-runtime-v1"
    root: Path
    platform: Literal["windows-x86_64", "linux-x86_64"]
    python: FileIdentity
    python_abi: Literal["cp311", "cp314"]
    python_runtime: list[FileIdentity]
    wheels: list[FileIdentity]
    adapter_files: list[FileIdentity]
    payload: dict[str, str]
    probe: CodecProbe
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"


class CodecAudioResult(Contract):
    protocol: Literal["soundfile-audio-v1"] = "soundfile-audio-v1"
    mode: Literal["decode", "verify"]
    runtime: CodecProbe
    codec: Literal["FLAC", "MP3"]
    frames: int = Field(gt=0, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: int = Field(ge=1, le=2, strict=True)
    samples_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pcm_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    flac_pcm_md5: str | None
    native_error: Literal[0]
