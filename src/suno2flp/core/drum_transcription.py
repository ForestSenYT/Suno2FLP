"""Source-bound inferred drums; all raw inputs/outputs and unearned gates survive."""

from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, JsonValue, field_serializer, field_validator, model_validator

from suno2flp.core.drum_clock import drum_domain, drum_source_time
from suno2flp.core.drum_native import NativeDrumResult
from suno2flp.core.drum_peaks import MAX_PEAKS, DrumPeak, RejectedDrumPeak
from suno2flp.core.drum_runtime import DrumBackend
from suno2flp.core.drum_scoring import MAX_DRUMS, ScoredDrum
from suno2flp.core.drum_snapshot import decode_snapshot, encode_snapshot
from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe, time_fraction
from suno2flp.core.offline_files import load_unique_json
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.separation import SeparationCandidate, SeparationReplayReceipt


class DrumSource(Contract):
    profile: Literal["estimated-drums-model-clock-source-v1"] = (
        "estimated-drums-model-clock-source-v1"
    )
    separation_report: FileIdentity
    separation_replay: FileIdentity
    receipt: SeparationReplayReceipt
    original: SeparationCandidate
    replay: SeparationCandidate
    model_pcm: FileIdentity
    evidence_scope: Literal["current-numerics-and-declared-separation-replay"] = (
        "current-numerics-and-declared-separation-replay"
    )
    fresh_separation_inference_this_invocation: Literal[False] = False

    @field_serializer("original", "replay", when_used="json")
    def snapshot_wire(self, value: SeparationCandidate) -> dict[str, JsonValue]:
        return encode_snapshot(value.model_dump_json().encode("utf-8"))

    @field_validator("original", "replay", mode="before")
    @classmethod
    def snapshot_value(cls, value: Any) -> Any:
        if isinstance(value, dict) and "encoding" in value:
            return load_unique_json(decode_snapshot(value))
        return value

    @model_validator(mode="after")
    def exact_estimated_source(self) -> Self:
        expected = next(s.model for s in self.original.stems if s.stem == "drums")
        if (
            self.receipt.original_report != self.separation_report
            or self.model_pcm != expected
            or self.separation_report.path.name != "separation.json"
            or self.separation_replay.path.name != "replay.json"
            or self.receipt.replay_report.path
            != self.separation_replay.path.parent / "separation.json"
            or self.original.native_result.path
            != self.separation_report.path.parent / "native/result.json"
            or self.replay.native_result.path
            != self.receipt.replay_report.path.parent / "native/result.json"
            or (
                self.original.source_audio,
                self.original.frames,
                self.original.sample_rate,
                self.original.result.model_frames,
            )
            != (
                self.replay.source_audio,
                self.replay.frames,
                self.replay.sample_rate,
                self.replay.result.model_frames,
            )
        ):
            raise ValueError(
                "Drum source must retain the exact current estimated lineage and model clock"
            )
        return self

    def witnesses(self) -> list[FileIdentity]:
        return [
            self.separation_report,
            self.separation_replay,
            self.receipt.replay_report,
            *self.original.witnesses(),
            *self.replay.witnesses(),
        ]


class DrumTranscriptionCandidate(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["source-bound-drum-transcription-v1"] = "source-bound-drum-transcription-v1"
    origin: Literal["inferred_candidate"] = "inferred_candidate"
    root: Path
    source: DrumSource
    backend_record: FileIdentity
    backend: DrumBackend
    model_dependencies: list[FileIdentity]
    recipe: ScoringRecipe
    native: NativeDrumResult
    native_witnesses: list[FileIdentity]
    peaks: list[DrumPeak] = Field(max_length=MAX_PEAKS)
    events: list[ScoredDrum] = Field(max_length=MAX_DRUMS)
    rejected_peaks: list[RejectedDrumPeak] = Field(max_length=117)
    postprocessing_profile: Literal[
        "positive-logit-leftmost-local-max3-no-musical-latency-correction-v1"
    ] = "positive-logit-leftmost-local-max3-no-musical-latency-correction-v1"
    velocity_semantics: Literal["raw-head-values-not-midi-velocity"] = (
        "raw-head-values-not-midi-velocity"
    )
    musical_latency_calibration: Literal["not_performed"] = "not_performed"
    model_qualification: Literal["not_assessed"] = "not_assessed"
    ground_truth_metrics: Literal["unavailable"] = "unavailable"
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    human_review: Literal["not_performed"] = "not_performed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def complete_source_mapping(self) -> Self:
        original = self.source.original
        if (
            not self.root.is_absolute()
            or self.native.model_frames != original.result.model_frames
            or self.native.source_sha256 != self.source.model_pcm.sha256
            or len({p.id for p in self.peaks}) != len(self.peaks)
            or any(
                p.row >= self.native.rows
                or p.domain != drum_domain(p.row, original.frames, original.sample_rate)
                for p in self.peaks
            )
        ):
            raise ValueError("Drum native rows/clock differ from full original-source mapping")
        source_peaks = [p for p in self.peaks if p.domain == "source"]
        rejected = [p for p in self.peaks if p.domain != "source"]
        if [(p.id, p.label, drum_source_time(p.row)) for p in source_peaks] != [
            (e.id, e.label, time_fraction(e.microseconds)) for e in self.events
        ] or rejected != [r.peak for r in self.rejected_peaks]:
            raise ValueError(
                "Every derived drum event/rejected peak must retain its original exact anchor"
            )
        return self

    def witnesses(self) -> list[FileIdentity]:
        return [
            *self.source.witnesses(),
            self.backend_record,
            self.backend.python,
            *self.backend.runtime,
            *self.backend.artifacts,
            *self.backend.adapters,
            *self.model_dependencies,
            self.recipe.python_executable,
            *self.recipe.files,
            *self.native_witnesses,
        ]


class DrumReplayReceipt(Contract):
    profile: Literal["source-drum-fresh-replay-v1"] = "source-drum-fresh-replay-v1"
    original_report: FileIdentity
    replay_report: FileIdentity
    complete_match: Literal[True] = True
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
