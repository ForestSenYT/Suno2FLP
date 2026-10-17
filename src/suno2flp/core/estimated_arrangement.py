"""Estimated audio-clock composition, separate from faithful MIDI contracts."""

from pathlib import Path
from typing import Literal

from pydantic import Field, StrictInt

from suno2flp.core.beat_clock import BeatAnchor
from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime
from suno2flp.core.separation import StemFile, StemName
from suno2flp.core.stem_transcription import PitchedStem
from suno2flp.core.transcription import InferredFrameNote

EstimatedRole = Literal["vocal-pitch-proxy", "percussion-reference", "bass", "mixed-pitched"]


class EstimatedPitchInput(Contract):
    stem: PitchedStem
    transcription: FileIdentity
    source_audio: FileIdentity
    decode_report: FileIdentity
    estimated_audio: FileIdentity
    frames: int = Field(gt=0, le=115200000, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    notes: list[InferredFrameNote] = Field(max_length=10000)
    bends: FileIdentity


class EstimatedRhythmInput(Contract):
    report: FileIdentity
    source_audio: FileIdentity
    decode_report: FileIdentity
    pcm: FileIdentity
    frames: int = Field(gt=0, le=115200000, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: int = Field(ge=1, le=2, strict=True)
    beats: list[BeatAnchor] = Field(max_length=60000)
    raw_downbeats: list[BeatAnchor] = Field(max_length=60000)
    downbeat_to_beat: list[StrictInt | None] = Field(max_length=60000)
    downbeats: list[BeatAnchor] = Field(max_length=60000)
    signal_observations: list[
        Literal["source-silent", "downmix-cancellation", "no-beat-predictions"]
    ] = Field(max_length=3)


class EstimatedArrangementInputs(Contract):
    source_audio: FileIdentity
    decode_report: FileIdentity
    pcm: FileIdentity
    frames: int = Field(gt=0, le=115200000, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: int = Field(ge=1, le=2, strict=True)
    batch_report: FileIdentity
    separation_report: FileIdentity
    stems: list[StemFile] = Field(min_length=4, max_length=4)
    residual: FileIdentity
    pitches: list[EstimatedPitchInput] = Field(min_length=3, max_length=3)
    rhythm: EstimatedRhythmInput | None = None


class EstimatedBoundary(Contract):
    row_boundary: int = Field(ge=0, le=52000, strict=True)
    resampled_sample: int = Field(ge=0, le=13230000, strict=True)
    source_sample: RationalTime
    microseconds: RationalTime
    domain: Literal["source", "padding"]


class EstimatedNotePosition(Contract):
    source_note_index: int = Field(ge=0, lt=10000, strict=True)
    start: EstimatedBoundary
    end: EstimatedBoundary


class EstimatedReference(Contract):
    file: FileIdentity
    encoding: Literal["stereo-float32-wave", "stereo-little-endian-float64-raw"] = (
        "stereo-float32-wave"
    )
    channels: Literal[2] = 2
    start_sample: Literal[0] = 0
    end_sample: RationalTime
    muted: Literal[True] = True


class EstimatedPart(Contract):
    stem: StemName
    role: EstimatedRole
    reference: EstimatedReference
    notes: list[EstimatedNotePosition] = Field(max_length=10000)


class EstimatedArrangement(Contract):
    profile: Literal["source-clock-estimated-arrangement-v1"] = (
        "source-clock-estimated-arrangement-v1"
    )
    authority: Literal["audio-inference"] = "audio-inference"
    clock: Literal["owned-model-row-boundaries-to-exact-audio-samples-v1"] = (
        "owned-model-row-boundaries-to-exact-audio-samples-v1"
    )
    role_basis: Literal["estimated-separation-stem-labels"] = "estimated-separation-stem-labels"
    inputs: EstimatedArrangementInputs
    root: Path | None = None
    parts: list[EstimatedPart] = Field(min_length=4, max_length=4)
    residual: EstimatedReference
    recipe: ScoringRecipe | None = None
    blockers: list[str]
    tempo: Literal["unavailable"] = "unavailable"
    meter: Literal["unavailable"] = "unavailable"
    structure: Literal["unavailable"] = "unavailable"
    playback: Literal["unavailable"] = "unavailable"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    ground_truth_metrics: Literal["unavailable"] = "unavailable"
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
