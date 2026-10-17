"""Source-clock beat annotations and conditional diagnostic metrics."""

from fractions import Fraction
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ExactRatio, time_fraction
from suno2flp.core.performance import RationalTime

MAX_BEATS = 12000
MAX_MATCH_CELLS = 4_000_000
MATCH_WINDOW_US = 500000


class ScoredBeat(Contract):
    id: str = Field(min_length=1, max_length=128)
    label: Literal["beat", "downbeat"]
    microseconds: RationalTime
    domain: Literal["source", "padding"] = "source"

    @field_validator("microseconds")
    @classmethod
    def bounded_time(cls, value: RationalTime) -> RationalTime:
        if value.numerator.bit_length() > 128 or value.denominator.bit_length() > 64:
            raise ValueError("Time rational exceeds the fixed integer budget")
        return value


class BeatMatch(Contract):
    candidate_id: str
    reference_id: str
    label: Literal["beat", "downbeat"]
    error_microseconds: RationalTime


class BeatScore(Contract):
    profile: Literal["labelled-beat-max-count-min-error-500ms-v1"] = (
        "labelled-beat-max-count-min-error-500ms-v1"
    )
    status: Literal["measured", "reference_unavailable", "no_reference_beats"]
    candidate_count: int = Field(ge=0, le=MAX_BEATS, strict=True)
    reference_count: int | None = Field(default=None, ge=0, le=MAX_BEATS, strict=True)
    matches: list[BeatMatch]
    unmatched_candidate_ids: list[str]
    unmatched_reference_ids: list[str]
    precision: ExactRatio | None = None
    recall: ExactRatio | None = None
    median_error_microseconds: RationalTime | None = None
    p95_error_microseconds: RationalTime | None = None
    musical_correctness: Literal["not_proven"] = "not_proven"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"

    @model_validator(mode="after")
    def complete_counts(self) -> Self:
        candidates = [p.candidate_id for p in self.matches] + self.unmatched_candidate_ids
        refs = [p.reference_id for p in self.matches] + self.unmatched_reference_ids
        if (
            len(candidates) != self.candidate_count
            or len(refs) != (self.reference_count or 0)
            or len(set(candidates)) != len(candidates)
            or len(set(refs)) != len(refs)
        ):
            raise ValueError("Beat matches need unique IDs and complete unmatched counts")
        if (self.status == "reference_unavailable") != (self.reference_count is None):
            raise ValueError("Beat reference availability changed")
        if (self.status == "measured") != bool(self.reference_count):
            raise ValueError("Measured beat score requires nonempty truth")
        count = len(self.matches)
        errors = sorted(time_fraction(p.error_microseconds) for p in self.matches)
        if any(e > MATCH_WINDOW_US for e in errors):
            raise ValueError("Beat match is outside the fixed diagnostic window")
        expected_ratios: tuple[ExactRatio | None, ExactRatio | None]
        if self.status == "measured":
            expected_ratios = (
                ExactRatio.exact(Fraction(count, self.candidate_count))
                if self.candidate_count
                else None,
                ExactRatio.exact(Fraction(count, self.reference_count or 1)),
            )
        else:
            expected_ratios = (None, None)
        if (self.precision, self.recall) != expected_ratios:
            raise ValueError("Beat coverage disagrees with complete match counts")
        median = (
            RationalTime.exact((errors[(count - 1) // 2] + errors[count // 2]) / 2)
            if count
            else None
        )
        p95 = RationalTime.exact(errors[(95 * count + 99) // 100 - 1]) if count else None
        if (self.median_error_microseconds, self.p95_error_microseconds) != (median, p95):
            raise ValueError("Beat error summaries disagree with every exact matched error")
        return self
