"""Auditable experimental peaks retain native bits, rows and padding addresses."""

import math
import struct
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.drum_clock import MAX_ROWS, DrumDomain, drum_model_sample
from suno2flp.core.drum_scoring import MAX_DRUMS, DrumClass
from suno2flp.core.models import Contract

PEAK_PROFILE = "positive-logit-leftmost-local-max3-no-musical-latency-correction-v1"
MAX_PEAKS = MAX_DRUMS + 9 * 13


class DrumPeak(Contract):
    id: str
    label: DrumClass
    row: int = Field(ge=0, lt=MAX_ROWS, strict=True)
    model_sample: int = Field(strict=True)
    domain: DrumDomain
    logit_bits: int = Field(ge=0, le=2**32 - 1, strict=True)
    velocity_bits: int = Field(ge=0, le=2**32 - 1, strict=True)

    @model_validator(mode="after")
    def exact_raw_anchor(self) -> Self:
        logit = struct.unpack("<f", struct.pack("<I", self.logit_bits))[0]
        velocity = struct.unpack("<f", struct.pack("<I", self.velocity_bits))[0]
        if (
            self.id != f"{self.label}.{self.row}"
            or self.model_sample != drum_model_sample(self.row)
            or not math.isfinite(logit)
            or logit <= 0
            or not math.isfinite(velocity)
            or not 0 < velocity <= 2.0
        ):
            raise ValueError(
                "Drum peak must preserve its exact native bits and geometric row anchor"
            )
        return self


class RejectedDrumPeak(Contract):
    peak: DrumPeak
    reason: Literal["before-source-zero", "at-or-after-original-end"]

    @model_validator(mode="after")
    def explicit_padding(self) -> Self:
        expected = {
            "leading_padding": "before-source-zero",
            "tail_padding": "at-or-after-original-end",
        }
        if expected.get(self.peak.domain) != self.reason:
            raise ValueError("Rejected drum peak requires the matching explicit padding reason")
        return self
