"""Explicit estimated ancestry, never original MIDI or original-recording authority."""

from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.transcription import PitchCandidate

PitchedStem = Literal["vocals", "bass", "other"]
PITCHED_STEMS: tuple[PitchedStem, ...] = ("vocals", "bass", "other")


class EstimatedStemSource(Contract):
    profile: Literal["estimated-stem-exact-float-widening-v1"] = (
        "estimated-stem-exact-float-widening-v1"
    )
    stem: PitchedStem
    separation_report: FileIdentity
    separation_replay: FileIdentity
    replay_report: FileIdentity
    original_audio: FileIdentity
    original_decode: FileIdentity
    estimated_audio: FileIdentity
    pcm: FileIdentity
    frames: int = Field(gt=0, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: Literal[2] = 2
    frame_zero_original_frame: Literal[0] = 0
    conversion: Literal["finite-ieee-binary32-to-binary64-exact-no-resampling"] = (
        "finite-ieee-binary32-to-binary64-exact-no-resampling"
    )
    recipe: ScoringRecipe


class StemTranscriptionCandidate(PitchCandidate):
    profile: Literal["estimated-stem-basic-pitch-candidate-v1"] = (
        "estimated-stem-basic-pitch-candidate-v1"
    )
    source: EstimatedStemSource

    @model_validator(mode="after")
    def same_source_clock(self) -> Self:
        if (self.pcm, self.frames, self.sample_rate, self.channels) != (
            self.source.pcm,
            self.source.frames,
            self.source.sample_rate,
            self.source.channels,
        ):
            raise ValueError("Pitch evidence differs from exact estimated source clock")
        return self


class StemTranscriptionEntry(Contract):
    stem: PitchedStem
    transcription: FileIdentity


class StemTranscriptionBatch(Contract):
    profile: Literal["estimated-stem-transcription-batch-v1"] = (
        "estimated-stem-transcription-batch-v1"
    )
    separation_report: FileIdentity
    separation_replay: FileIdentity
    backend_record: FileIdentity
    stems: list[StemTranscriptionEntry] = Field(min_length=1, max_length=3)
    recipe: ScoringRecipe
    drums: Literal["not_transcribed_by_pitched_model"] = "not_transcribed_by_pitched_model"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    ground_truth_metrics: Literal["unavailable"] = "unavailable"
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def canonical_selection(self) -> Self:
        names = [item.stem for item in self.stems]
        if names != [name for name in PITCHED_STEMS if name in names]:
            raise ValueError("Use unique pitched stems in canonical vocals/bass/other order")
        return self


class StemBatchReplay(Contract):
    profile: Literal["estimated-stem-transcription-replay-v1"] = (
        "estimated-stem-transcription-replay-v1"
    )
    original_report: FileIdentity
    replay_report: FileIdentity
    complete_match: Literal[True] = True
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
