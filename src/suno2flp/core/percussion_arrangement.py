"""Separate estimated composition contracts; producer links are not musical truth."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.drum_clock import MAX_ROWS, drum_domain, drum_output_rows, drum_source_time
from suno2flp.core.drum_peaks import MAX_PEAKS, DrumPeak, RejectedDrumPeak
from suno2flp.core.drum_scoring import MAX_DRUMS, ScoredDrum
from suno2flp.core.estimated_arrangement import (
    EstimatedArrangementInputs,
    EstimatedNotePosition,
    EstimatedReference,
    EstimatedRole,
)
from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe, time_fraction
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime
from suno2flp.core.separation import StemName
from suno2flp.core.separation_clock import model_frame_count


class EstimatedDrumInput(Contract):
    transcription: FileIdentity
    backend_record: FileIdentity
    native_witnesses: list[FileIdentity] = Field(min_length=7, max_length=64)
    source_audio: FileIdentity
    decode_report: FileIdentity
    pcm: FileIdentity
    separation_report: FileIdentity
    separation_replay: FileIdentity
    reference: FileIdentity
    model_pcm: FileIdentity
    frames: int = Field(gt=0, le=115200000, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: int = Field(ge=1, le=2, strict=True)
    model_frames: int = Field(ge=513, le=26460000, strict=True)
    rows: int = Field(ge=16, le=MAX_ROWS, strict=True)
    peaks: list[DrumPeak] = Field(max_length=MAX_PEAKS)
    events: list[ScoredDrum] = Field(max_length=MAX_DRUMS)
    rejected_peaks: list[RejectedDrumPeak] = Field(max_length=117)
    postprocessing_profile: Literal[
        "positive-logit-leftmost-local-max3-no-musical-latency-correction-v1"
    ] = "positive-logit-leftmost-local-max3-no-musical-latency-correction-v1"

    @model_validator(mode="after")
    def complete_peak_mapping(self) -> Self:
        native = self.transcription.path.parent / "native"
        if (
            self.transcription.path.name != "drum-transcription.json"
            or self.frames > 600 * self.sample_rate
            or self.model_frames != model_frame_count(self.frames, self.sample_rate)
            or self.rows != drum_output_rows(self.model_frames)
            or self.model_pcm.size_bytes != self.model_frames * 8
            or any(not i.path.is_relative_to(native) for i in self.native_witnesses)
            or len({i.path for i in self.native_witnesses}) != len(self.native_witnesses)
            or len({p.id for p in self.peaks}) != len(self.peaks)
            or any(
                p.row >= self.rows or p.domain != drum_domain(p.row, self.frames, self.sample_rate)
                for p in self.peaks
            )
        ):
            raise ValueError(
                "Keep complete native drum geometry, identities and exact source domains"
            )
        source = [p for p in self.peaks if p.domain == "source"]
        rejected = [p for p in self.peaks if p.domain != "source"]
        if [(p.id, p.label, drum_source_time(p.row)) for p in source] != [
            (e.id, e.label, time_fraction(e.microseconds)) for e in self.events
        ] or rejected != [r.peak for r in self.rejected_peaks]:
            raise ValueError("Keep every original drum peak, ordered source event and rejection")
        return self


class PercussionArrangementInputs(Contract):
    pitched: EstimatedArrangementInputs
    pitched_separation_replay: FileIdentity
    drums: EstimatedDrumInput

    @model_validator(mode="after")
    def one_original_clock(self) -> Self:
        pitched, drums = self.pitched, self.drums
        references = [s.file for s in pitched.stems if s.stem == "drums"]
        if len(references) != 1 or (
            drums.source_audio,
            drums.decode_report,
            drums.pcm,
            drums.separation_report,
            drums.separation_replay,
            drums.reference,
            drums.frames,
            drums.sample_rate,
            drums.channels,
        ) != (
            pitched.source_audio,
            pitched.decode_report,
            pitched.pcm,
            pitched.separation_report,
            self.pitched_separation_replay,
            references[0],
            pitched.frames,
            pitched.sample_rate,
            pitched.channels,
        ):
            raise ValueError("Pitched and drum producers must share exact source/separation/clock")
        return self


class EstimatedDrumPosition(Contract):
    source_event_index: int = Field(ge=0, lt=MAX_DRUMS, strict=True)
    source_peak_index: int = Field(ge=0, lt=MAX_PEAKS, strict=True)
    source_sample: RationalTime
    microseconds: RationalTime


class PercussionArrangementPart(Contract):
    stem: StemName
    role: EstimatedRole | Literal["classified-percussion-candidate"]
    reference: EstimatedReference
    notes: list[EstimatedNotePosition] = Field(max_length=10000)
    onsets: list[EstimatedDrumPosition] = Field(max_length=MAX_DRUMS)


class PercussionArrangement(Contract):
    profile: Literal["source-clock-estimated-arrangement-v2"] = (
        "source-clock-estimated-arrangement-v2"
    )
    authority: Literal["audio-inference"] = "audio-inference"
    status: Literal["unqualified_candidate"] = "unqualified_candidate"
    clock: Literal["pitch-owned-rows-and-drum-geometric-centers-to-original-samples-v1"] = (
        "pitch-owned-rows-and-drum-geometric-centers-to-original-samples-v1"
    )
    role_basis: Literal["estimated-stem-labels-and-unqualified-drum-classes"] = (
        "estimated-stem-labels-and-unqualified-drum-classes"
    )
    inputs: PercussionArrangementInputs
    root: Path | None = None
    parts: list[PercussionArrangementPart] = Field(min_length=4, max_length=4)
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
    human_review: Literal["not_performed"] = "not_performed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
