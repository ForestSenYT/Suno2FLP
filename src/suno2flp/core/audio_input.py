"""Structural audio evidence; no musical accuracy or decoding attestation."""

from fractions import Fraction
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.errors import OfflineError
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime

MAX_AUDIO_BYTES = 1024**3
MAX_AUDIO_SECONDS = 600


class AudioPreflightError(OfflineError):
    def __init__(self, code: str, message: str, *, blocked: bool = False) -> None:
        super().__init__(code, message)
        self.blocked = blocked


class WaveChunk(Contract):
    id_hex: str = Field(pattern=r"^[0-9a-f]{8}$")
    offset: int = Field(ge=12, strict=True)
    data_size: int = Field(ge=0, strict=True)


class AudioPreflightReport(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["pcm-wave-preflight-v1"] = "pcm-wave-preflight-v1"
    source: FileIdentity
    channels: int = Field(ge=1, le=2, strict=True)
    sample_width_bytes: int = Field(ge=1, le=4, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    frames: int = Field(gt=0, strict=True)
    data_offset: int = Field(ge=20, strict=True)
    data_bytes: int = Field(gt=0, strict=True)
    pcm_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks: list[WaveChunk]
    duration_microseconds: RationalTime
    musical_correctness: Literal["not_assessed"] = "not_assessed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"

    @model_validator(mode="after")
    def consistent_pcm(self) -> Self:
        if self.data_bytes != self.frames * self.channels * self.sample_width_bytes:
            raise ValueError("PCM frames must account for the complete data chunk")
        expected = RationalTime.exact(Fraction(self.frames * 1_000_000, self.sample_rate))
        if (
            self.duration_microseconds != expected
            or self.frames > self.sample_rate * MAX_AUDIO_SECONDS
        ):
            raise ValueError("Duration must preserve exact frame timing within the supported limit")
        if self.data_offset + self.data_bytes > self.source.size_bytes:
            raise ValueError("PCM data exceeds source size")
        return self
