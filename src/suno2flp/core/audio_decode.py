"""Exact, lossless PCM decoding contracts; no musical or host qualification."""

import time
from collections.abc import Callable
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.audio_input import AudioPreflightReport
from suno2flp.core.errors import OfflineError
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime

PCM_BLOCK_FRAMES = 4096
PCM_PASS_SECONDS = 300
MAX_PCM_REPORT_BYTES = 1024**2


class DecodeCancelled(OfflineError):
    def __init__(self) -> None:
        super().__init__("user_cancelled", "Audio decoding/verification was cancelled")


def check_decode_request(should_cancel: Callable[[], bool] | None, deadline: float) -> None:
    if should_cancel is not None and should_cancel():
        raise DecodeCancelled()
    if time.monotonic() > deadline:
        raise OfflineError("audio_decode_timeout", "PCM pass exceeded its 300-second budget")


class PcmDecodeRuntime(Contract):
    implementation: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    executable: FileIdentity
    decoder: FileIdentity
    verifier: FileIdentity
    preflight: FileIdentity
    contract: FileIdentity


class PcmDecodeReport(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["integer-pcm-to-float64-wave-v1"] = "integer-pcm-to-float64-wave-v1"
    preflight: AudioPreflightReport
    runtime: PcmDecodeRuntime
    pcm: FileIdentity
    sample_encoding: Literal["ieee-float64-little-endian"] = "ieee-float64-little-endian"
    data_offset: Literal[58] = 58
    samples_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frame_zero_source_frame: Literal[0] = 0
    resampling: Literal["none"] = "none"
    channel_mapping: Literal["source-order"] = "source-order"
    normalization: Literal["signed-integer-divided-by-2-to-bits-minus-1"] = (
        "signed-integer-divided-by-2-to-bits-minus-1"
    )
    duration_microseconds: RationalTime
    musical_correctness: Literal["not_assessed"] = "not_assessed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"

    @model_validator(mode="after")
    def exact_clock_and_size(self) -> Self:
        expected = self.data_offset + self.preflight.frames * self.preflight.channels * 8
        if self.pcm.size_bytes != expected:
            raise ValueError("Decoded PCM must contain every original frame exactly once")
        if self.duration_microseconds != self.preflight.duration_microseconds:
            raise ValueError("Decoded duration must retain the exact original sample clock")
        return self
