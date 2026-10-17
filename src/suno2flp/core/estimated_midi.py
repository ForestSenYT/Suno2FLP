"""Explicit, unqualified audio-inference MIDI projection and timing audit."""

from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import Field

from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.percussion_arrangement import PercussionArrangement
from suno2flp.core.performance import RationalTime
from suno2flp.core.separation import StemName


class SignedTime(Contract):
    numerator: int = Field(strict=True)
    denominator: int = Field(gt=0, strict=True)

    @classmethod
    def exact(cls, value: Fraction) -> "SignedTime":
        return cls(numerator=value.numerator, denominator=value.denominator)


class PreviewBoundary(Contract):
    original_us: RationalTime
    tick: int = Field(ge=0, le=2**31 - 1, strict=True)
    error_us: SignedTime


class PreviewNote(Contract):
    source_kind: Literal["pitched-note", "drum-onset"]
    source_index: int = Field(ge=0, lt=20000, strict=True)
    source_peak_index: int | None = Field(default=None, ge=0, lt=120000, strict=True)
    pitch: int = Field(ge=0, le=127, strict=True)
    velocity: Literal[96] = 96
    start: PreviewBoundary
    end: PreviewBoundary


class PreviewPart(Contract):
    stem: StemName
    channel: int = Field(ge=0, le=15, strict=True)
    notes: list[PreviewNote] = Field(max_length=20000)


class EstimatedMidiScore(Contract):
    profile: Literal["audio-inference-midi-preview-v1"] = "audio-inference-midi-preview-v1"
    authority: Literal["audio-inference"] = "audio-inference"
    status: Literal["unqualified_candidate"] = "unqualified_candidate"
    arrangement: PercussionArrangement
    ppq: Literal[960] = 960
    tempo_us: Literal[500000] = 500000
    clock_basis: Literal["technical-120bpm-not-estimated-musical-tempo"] = (
        "technical-120bpm-not-estimated-musical-tempo"
    )
    rounding: Literal["independent-boundaries-nearest-half-up-v1"] = (
        "independent-boundaries-nearest-half-up-v1"
    )
    drum_key_policy: Literal["explicit-nine-class-preview-keys-v1"] = (
        "explicit-nine-class-preview-keys-v1"
    )
    drum_duration_us: Literal[50000] = 50000
    velocity_policy: Literal["fixed96-not-model-activation-or-dynamics"] = (
        "fixed96-not-model-activation-or-dynamics"
    )
    parts: list[PreviewPart] = Field(min_length=4, max_length=4)
    source_end_us: RationalTime
    end_tick: int = Field(ge=0, le=2**31 - 1, strict=True)
    blockers: list[str]
    model_qualification: Literal["not_assessed"] = "not_assessed"
    ground_truth_metrics: Literal["unavailable"] = "unavailable"
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    human_review: Literal["not_performed"] = "not_performed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False


class EstimatedMidiExport(Contract):
    profile: Literal["estimated-midi-export-v1"] = "estimated-midi-export-v1"
    root: Path
    score: EstimatedMidiScore
    midi: FileIdentity
    recipe: ScoringRecipe
    mido_version: str
