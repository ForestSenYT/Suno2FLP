"""Conditional annotation metrics; declarations never certify musical truth."""

from fractions import Fraction
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.performance import RationalTime

MAX_NOTES = 10_000
MAX_EDGES = 200_000
MATCH_SECONDS = 300
ANNOTATION_BYTES = 4 * 1024**2
REPORT_BYTES = 16 * 1024**2


def time_fraction(value: RationalTime) -> Fraction:
    return Fraction(value.numerator, value.denominator)


class ScoredNote(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,96}$")
    pitch: int = Field(ge=0, le=127, strict=True)
    onset_microseconds: RationalTime
    offset_microseconds: RationalTime

    @field_validator("onset_microseconds", "offset_microseconds")
    @classmethod
    def bounded_time(cls, value: RationalTime) -> RationalTime:
        if value.numerator.bit_length() > 128 or value.denominator.bit_length() > 64:
            raise ValueError("Time rational exceeds the fixed integer budget")
        return value

    @model_validator(mode="after")
    def positive_duration(self) -> Self:
        if time_fraction(self.offset_microseconds) <= time_fraction(self.onset_microseconds):
            raise ValueError("Note offset must follow onset")
        return self


class ExactRatio(Contract):
    numerator: int = Field(ge=0, strict=True)
    denominator: int = Field(gt=0, strict=True)

    @classmethod
    def exact(cls, value: Fraction) -> "ExactRatio":
        return cls(numerator=value.numerator, denominator=value.denominator)

    @model_validator(mode="after")
    def canonical(self) -> Self:
        value = Fraction(self.numerator, self.denominator)
        if value > 1 or (value.numerator, value.denominator) != (self.numerator, self.denominator):
            raise ValueError("Expected a reduced ratio in [0,1]")
        return self


class NoteMatch(Contract):
    reference_id: str
    candidate_id: str
    onset_error_microseconds: RationalTime
    offset_error_microseconds: RationalTime


class NoteScore(Contract):
    profile: Literal["pitched-note-exact-maximum-matching-v1"] = (
        "pitched-note-exact-maximum-matching-v1"
    )
    status: Literal["measured", "reference_unavailable", "no_reference_notes"]
    candidate_count: int = Field(ge=0, le=MAX_NOTES, strict=True)
    reference_count: int | None = Field(default=None, ge=0, le=MAX_NOTES, strict=True)
    true_positives: int = Field(ge=0, le=MAX_NOTES, strict=True)
    precision: ExactRatio | None = None
    recall: ExactRatio | None = None
    f1: ExactRatio | None = None
    matches: list[NoteMatch]
    unmatched_reference_ids: list[str]
    unmatched_candidate_ids: list[str]

    @model_validator(mode="after")
    def consistent_counts(self) -> Self:
        refs = [pair.reference_id for pair in self.matches] + self.unmatched_reference_ids
        candidates = [pair.candidate_id for pair in self.matches] + self.unmatched_candidate_ids
        if (
            len(self.matches) != self.true_positives
            or len(refs) != (self.reference_count or 0)
            or len(candidates) != self.candidate_count
            or len(set(refs)) != len(refs)
            or len(set(candidates)) != len(candidates)
        ):
            raise ValueError("Matches must have unique IDs and complete counts")
        measured = self.status == "measured"
        if measured != bool(self.reference_count) or (self.status == "reference_unavailable") != (
            self.reference_count is None
        ):
            raise ValueError("Reference availability disagrees with score status")
        if measured:
            count = self.reference_count or 1
            expected = (
                Fraction(self.true_positives, self.candidate_count or 1),
                Fraction(self.true_positives, count),
                Fraction(2 * self.true_positives, count + self.candidate_count),
            )
            if (self.precision, self.recall, self.f1) != tuple(map(ExactRatio.exact, expected)):
                raise ValueError("Metrics disagree with exact match counts")
        elif any(value is not None for value in (self.precision, self.recall, self.f1)):
            raise ValueError("Unavailable reference cannot have metrics")
        return self
