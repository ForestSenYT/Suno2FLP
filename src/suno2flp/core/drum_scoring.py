"""Conditional class/onset declarations, separate from MIDI and musical truth."""

from fractions import Fraction
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ExactRatio, ScoringRecipe, time_fraction
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime

DrumClass = Literal["CY_CR", "CY_RD", "HH_CHH", "HH_OHH", "KD", "SD", "TT_HFT", "TT_HMT", "TT_LMT"]
DRUM_CLASSES: tuple[DrumClass, ...] = (
    "CY_CR",
    "CY_RD",
    "HH_CHH",
    "HH_OHH",
    "KD",
    "SD",
    "TT_HFT",
    "TT_HMT",
    "TT_LMT",
)
MAX_DRUMS = 20_000
ONSET_TOLERANCE_US = 50_000


class ScoredDrum(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,96}$")
    label: DrumClass
    microseconds: RationalTime

    @field_validator("microseconds")
    @classmethod
    def bounded_time(cls, value: RationalTime) -> RationalTime:
        if value.numerator.bit_length() > 128 or value.denominator.bit_length() > 64:
            raise ValueError("Drum time rational exceeds the fixed integer budget")
        if time_fraction(value) >= 600_000_000:
            raise ValueError("Drum onset exceeds the ten-minute source profile")
        return value


class DrumMatch(Contract):
    candidate_id: str
    reference_id: str
    label: DrumClass
    error_microseconds: RationalTime


class DrumScore(Contract):
    profile: Literal["drum-class-onset-max-cardinality-50ms-v1"] = (
        "drum-class-onset-max-cardinality-50ms-v1"
    )
    status: Literal["measured", "reference_unavailable", "no_reference_events"]
    candidate_count: int = Field(ge=0, le=MAX_DRUMS, strict=True)
    reference_count: int | None = Field(default=None, ge=0, le=MAX_DRUMS, strict=True)
    true_positives: int = Field(ge=0, le=MAX_DRUMS, strict=True)
    matches: list[DrumMatch]
    unmatched_candidate_ids: list[str]
    unmatched_reference_ids: list[str]
    precision: ExactRatio | None = None
    recall: ExactRatio | None = None
    f1: ExactRatio | None = None
    annotation_truth_verified: Literal[False] = False
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def complete_metrics(self) -> Self:
        cs = [p.candidate_id for p in self.matches] + self.unmatched_candidate_ids
        rs = [p.reference_id for p in self.matches] + self.unmatched_reference_ids
        if (
            len(self.matches) != self.true_positives
            or len(cs) != self.candidate_count
            or len(rs) != (self.reference_count or 0)
            or len(set(cs)) != len(cs)
            or len(set(rs)) != len(rs)
            or any(time_fraction(p.error_microseconds) > ONSET_TOLERANCE_US for p in self.matches)
        ):
            raise ValueError("Drum matches require complete unique IDs and in-window errors")
        if (self.status == "reference_unavailable") != (self.reference_count is None) or (
            self.status == "measured"
        ) != bool(self.reference_count):
            raise ValueError("Drum reference availability disagrees with status")
        expected: tuple[ExactRatio | None, ...] = (None, None, None)
        if self.status == "measured":
            count = self.true_positives
            expected = tuple(
                map(
                    ExactRatio.exact,
                    (
                        Fraction(count, self.candidate_count or 1),
                        Fraction(count, self.reference_count or 1),
                        Fraction(2 * count, self.candidate_count + (self.reference_count or 1)),
                    ),
                )
            )
        if (self.precision, self.recall, self.f1) != expected:
            raise ValueError("Drum metrics disagree with complete counts")
        return self


class DrumAnnotation(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["source-clock-drum-annotation-v1"] = "source-clock-drum-annotation-v1"
    role: Literal["candidate", "reference"]
    origin: Literal["inferred_candidate", "declared_reference", "synthetic_fixture"]
    method: str = Field(min_length=1, max_length=1024)
    provenance_files: list[FileIdentity] = Field(min_length=1, max_length=32)
    decode_report: FileIdentity
    source_audio: FileIdentity
    frames: int = Field(gt=0, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: int = Field(ge=1, le=2, strict=True)
    events: list[ScoredDrum] = Field(max_length=MAX_DRUMS)

    @model_validator(mode="after")
    def source_bounds(self) -> Self:
        if (self.role, self.origin) in {
            ("candidate", "declared_reference"),
            ("reference", "inferred_candidate"),
        }:
            raise ValueError("Drum role and origin disagree")
        if self.frames > self.sample_rate * 600:
            raise ValueError("Drum annotation exceeds the ten-minute profile")
        if len({e.id for e in self.events}) != len(self.events):
            raise ValueError("Drum event IDs must be unique")
        end = Fraction(self.frames * 1_000_000, self.sample_rate)
        if any(time_fraction(e.microseconds) >= end for e in self.events):
            raise ValueError("Drum onset must be inside the source clock, excluding EOF/padding")
        paths = [p.path for p in self.provenance_files]
        if len(set(paths)) != len(paths) or any(not p.is_absolute() for p in paths):
            raise ValueError("Producer provenance requires unique absolute paths")
        return self


class DrumAnnotationSnapshot(Contract):
    file: FileIdentity
    annotation: DrumAnnotation


class DrumScoreReport(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["source-bound-drum-score-v1"] = "source-bound-drum-score-v1"
    report_path: Path
    candidate: DrumAnnotationSnapshot
    reference: DrumAnnotationSnapshot | None
    pcm: FileIdentity
    decode_dependencies: list[FileIdentity]
    decoder_payload_root: Path | None
    recipe: ScoringRecipe
    result: DrumScore
    annotation_truth_verified: Literal[False] = False
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    human_review: Literal["not_performed"] = "not_performed"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False

    def witnesses(self) -> list[FileIdentity]:
        result = [
            self.pcm,
            self.recipe.python_executable,
            *self.recipe.files,
            *self.decode_dependencies,
        ]
        for snapshot in (self.candidate, self.reference):
            if snapshot is not None:
                a = snapshot.annotation
                result.extend([snapshot.file, a.decode_report, a.source_audio, *a.provenance_files])
        return result
