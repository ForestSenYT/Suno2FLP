"""Candidate-only audio inference export; never grants legacy writer eligibility."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity

DRUM_PREVIEW_KEYS = (49, 51, 42, 46, 36, 38, 43, 48, 47)
PITCH_CHANNELS = {"vocals": 0, "bass": 1, "other": 2}


class AudioPreviewNote(Contract):
    source_part: int = Field(ge=0, lt=4, strict=True)
    source_occurrence: int = Field(ge=0, lt=20000, strict=True)
    stem: Literal["vocals", "drums", "bass", "other"]
    source_pitch: int = Field(ge=0, le=127, strict=True)
    channel: int = Field(ge=0, lt=12, strict=True)
    pitch: int = Field(ge=0, le=127, strict=True)
    velocity: Literal[96] = 96
    start_tick: int = Field(ge=0, le=2**31 - 1, strict=True)
    end_tick: int = Field(gt=0, le=2**31 - 1, strict=True)

    @model_validator(mode="after")
    def route(self) -> "AudioPreviewNote":
        if self.stem == "drums":
            if self.source_pitch not in DRUM_PREVIEW_KEYS:
                raise ValueError("Unsupported drum preview key")
            expected = 3 + DRUM_PREVIEW_KEYS.index(self.source_pitch)
            pitch = 60
        else:
            expected, pitch = PITCH_CHANNELS[self.stem], self.source_pitch
        if self.channel != expected or self.pitch != pitch or self.end_tick <= self.start_tick:
            raise ValueError("Preserve the explicit source route and positive projected duration")
        return self


class AudioPreviewPlan(Contract):
    profile: Literal["fl26-audio-candidate-v1"] = "fl26-audio-candidate-v1"
    status: Literal["unqualified_candidate"] = "unqualified_candidate"
    source_score_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    notes: list[AudioPreviewNote] = Field(max_length=80000)
    end_tick: int = Field(gt=3840, le=2**31 - 1, strict=True)
    ppq: Literal[960] = 960
    tempo_us: Literal[500000] = 500000
    channel_gain: Literal[1280] = 1280
    legacy_writer_eligibility: Literal["blocked"] = "blocked"
    musical_quality: Literal["not_assessed"] = "not_assessed"

    @model_validator(mode="after")
    def extent(self) -> "AudioPreviewPlan":
        occurrences = [(n.source_part, n.source_occurrence) for n in self.notes]
        if len(set(occurrences)) != len(occurrences) or any(
            n.end_tick > self.end_tick - 3840 for n in self.notes
        ):
            raise ValueError("Retain unique occurrences and explicit non-cut tail padding")
        return self


class AudioFlpExport(Contract):
    profile: Literal["audio-flp-export-v1"] = "audio-flp-export-v1"
    root: Path
    source_report: FileIdentity
    source_midi: FileIdentity
    components: list[FileIdentity] = Field(min_length=2, max_length=2)
    plan: AudioPreviewPlan
    files: list[FileIdentity]
    recipe: ScoringRecipe
    status: Literal["unqualified_candidate"] = "unqualified_candidate"
    host_compatibility: Literal["unverified"] = "unverified"
    listening: Literal["not_performed"] = "not_performed"
    reference_stems_in_playlist: Literal[False] = False
    legacy_writer_eligibility: Literal["blocked"] = "blocked"
    blockers: list[str]
