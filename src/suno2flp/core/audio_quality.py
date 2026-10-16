"""Numerical PCM measurements, explicitly separate from audible acceptance."""

from typing import Literal

from pydantic import Field

from suno2flp.core.models import Contract, Diagnostic
from suno2flp.core.offline_models import FileIdentity


class RenderComparisonReport(Contract):
    schema_version: Literal[1] = 1
    valid: bool = False
    input_files: list[FileIdentity] = Field(default_factory=list)
    sample_rate: int | None = None
    channels: int | None = None
    sample_width_bytes: int | None = None
    frames_reference: int | None = None
    frames_candidate: int | None = None
    compared_samples: int = 0
    reference_rms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    candidate_rms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    rms_difference: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_abs_difference: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    reference_full_scale_samples: int = 0
    candidate_full_scale_samples: int = 0
    samples_identical: bool | None = None
    max_rms_error: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    within_tolerance: bool | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    host_compatibility: Literal["unverified"] = "unverified"
    audible_acceptance: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
