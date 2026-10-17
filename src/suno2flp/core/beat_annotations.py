"""Declared source-bound rhythm labels, not proof of truth or model inference."""

from fractions import Fraction
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.beat_scoring import MAX_BEATS, BeatScore, ScoredBeat
from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe, time_fraction
from suno2flp.core.offline_models import FileIdentity


class BeatAnnotation(Contract):
    profile: Literal["source-bound-beat-annotation-v1"] = "source-bound-beat-annotation-v1"
    role: Literal["candidate", "reference"]
    origin: Literal["inferred_candidate", "declared_reference", "synthetic_fixture"]
    method: str = Field(min_length=1, max_length=1024)
    provenance_files: list[FileIdentity] = Field(min_length=1, max_length=32)
    decode_report: FileIdentity
    source_audio: FileIdentity
    frames: int = Field(gt=0, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: Literal[1, 2]
    beats: list[ScoredBeat] = Field(max_length=MAX_BEATS)

    @model_validator(mode="after")
    def exact_source_domain(self) -> Self:
        if (self.role, self.origin) in {
            ("reference", "inferred_candidate"),
            ("candidate", "declared_reference"),
        }:
            raise ValueError("Beat annotation role and origin disagree")
        if self.frames > self.sample_rate * 600:
            raise ValueError("Beat annotation exceeds the ten-minute source clock")
        if len({b.id for b in self.beats}) != len(self.beats):
            raise ValueError("Beat annotation IDs must be unique")
        end = Fraction(self.frames * 1000000, self.sample_rate)
        for beat in self.beats:
            position = time_fraction(beat.microseconds)
            limit = end if self.role == "reference" else end + 20000
            if position > limit or beat.domain != ("source" if position < end else "padding"):
                raise ValueError("Beat position/domain disagrees with the exact source clock")
        paths = [i.path for i in self.provenance_files]
        if len(set(paths)) != len(paths) or any(not p.is_absolute() for p in paths):
            raise ValueError("Beat provenance needs unique absolute identities")
        return self


class BeatAnnotationSnapshot(Contract):
    file: FileIdentity
    annotation: BeatAnnotation


class BeatScoreReport(Contract):
    profile: Literal["source-bound-conditional-beat-score-v1"] = (
        "source-bound-conditional-beat-score-v1"
    )
    candidate: BeatAnnotationSnapshot
    reference: BeatAnnotationSnapshot | None
    source_audio: FileIdentity
    pcm: FileIdentity
    decode_dependencies: list[FileIdentity]
    decoder_payload_root: Path | None
    recipe: ScoringRecipe
    result: BeatScore
    annotation_truth_verified: Literal[False] = False
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    human_review: Literal["not_performed"] = "not_performed"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"
