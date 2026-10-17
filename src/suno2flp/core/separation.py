"""Complete source-bound separation candidates, without musical qualification."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.separation_clock import (
    SeparationPartition,
    back_frame_count,
    model_frame_count,
    plan_separation_partitions,
)
from suno2flp.core.separation_runtime import STEMS, Digest, SpleeterBackend, SpleeterExecution

StemName = Literal["vocals", "drums", "bass", "other"]


class SeparationPartResult(Contract):
    partition: SeparationPartition
    input_sha256: Digest
    output_sha256: dict[str, Digest]

    @model_validator(mode="after")
    def complete_stems(self) -> Self:
        if set(self.output_sha256) != set(STEMS):
            raise ValueError("A native partition must retain all four complete outputs")
        return self


class NativeSeparationResult(Contract):
    profile: Literal["global-stft-four-stem-result-v1"] = "global-stft-four-stem-result-v1"
    execution: SpleeterExecution
    source_frames: int = Field(gt=0, le=115200000, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    source_channels: int = Field(ge=1, le=2, strict=True)
    model_frames: int = Field(gt=0, le=26460000, strict=True)
    returned_source_frames: int = Field(gt=0, le=115200000, strict=True)
    partitions: list[SeparationPartResult] = Field(min_length=1, max_length=51)
    model_input_sha256: Digest
    model_output_sha256: dict[str, Digest]
    source_output_sha256: dict[str, Digest]
    resampling_tail_sha256: dict[str, Digest]
    peak_working_set_bytes: int = Field(gt=0, le=16 * 1024**3, strict=True)
    peak_commit_bytes: int = Field(gt=0, le=2**64 - 1, strict=True)
    elapsed_seconds: float = Field(gt=0, le=1800, allow_inf_nan=False)

    @model_validator(mode="after")
    def exact_geometry(self) -> Self:
        if self.model_frames != model_frame_count(self.source_frames, self.sample_rate):
            raise ValueError("Native model length differs from the source's exact rational clock")
        if self.returned_source_frames != back_frame_count(self.model_frames, self.sample_rate):
            raise ValueError("Native back-resampling length or tail is incomplete")
        if [part.partition for part in self.partitions] != plan_separation_partitions(
            self.model_frames
        ):
            raise ValueError("Native partitions must cover the complete global STFT in order")
        for hashes in (
            self.model_output_sha256,
            self.source_output_sha256,
            self.resampling_tail_sha256,
        ):
            if set(hashes) != set(STEMS):
                raise ValueError("Native output inventory must contain exactly the four stems")
        return self


class StemFile(Contract):
    stem: StemName
    file: FileIdentity


class SeparationPartArtifact(Contract):
    partition: SeparationPartition
    input: FileIdentity
    outputs: list[StemFile] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def complete_size(self) -> Self:
        if tuple(item.stem for item in self.outputs) != STEMS or any(
            file.size_bytes != self.partition.waveform_frames * 8
            for file in [self.input, *[item.file for item in self.outputs]]
        ):
            raise ValueError("Partition evidence must retain every stereo float32 sample")
        return self


class SeparationStemArtifact(Contract):
    stem: StemName
    model: FileIdentity
    source: FileIdentity
    tail: FileIdentity


class SeparationCandidate(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["source-bound-spleeter-four-stem-candidate-v1"] = (
        "source-bound-spleeter-four-stem-candidate-v1"
    )
    origin: Literal["inferred_candidate"] = "inferred_candidate"
    decode_report: FileIdentity
    source_audio: FileIdentity
    pcm: FileIdentity
    frames: int = Field(gt=0, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: int = Field(ge=1, le=2, strict=True)
    decode_dependencies: list[FileIdentity]
    decoder_payload_root: Path | None
    backend_record: FileIdentity
    backend: SpleeterBackend
    model_dependencies: list[FileIdentity]
    recipe: ScoringRecipe
    result: NativeSeparationResult
    model_input: FileIdentity
    partitions: list[SeparationPartArtifact] = Field(min_length=1, max_length=51)
    stems: list[SeparationStemArtifact] = Field(min_length=4, max_length=4)
    residual: FileIdentity
    residual_peak: float = Field(ge=0, allow_inf_nan=False)
    conservation_error: float = Field(ge=0, le=1e-12, allow_inf_nan=False)
    native_result: FileIdentity
    native_request: FileIdentity
    stdout: FileIdentity
    stderr: FileIdentity
    output_channels: Literal[2] = 2
    clock_profile: Literal["rational-44100-source-origin-zero-v1"] = (
        "rational-44100-source-origin-zero-v1"
    )
    channel_mapping: Literal["mono-duplicate-or-stereo-source-order"] = (
        "mono-duplicate-or-stereo-source-order"
    )
    resampling: Literal["scipy-polyphase-kaiser5-zero-f64-input-f32-stems-v1"] = (
        "scipy-polyphase-kaiser5-zero-f64-input-f32-stems-v1"
    )
    synthesis: Literal["global-stft-partition-overlap-add-float32-v1"] = (
        "global-stft-partition-overlap-add-float32-v1"
    )
    residual_semantics: Literal["unassigned-source-minus-four-estimates"] = (
        "unassigned-source-minus-four-estimates"
    )
    model_qualification: Literal["not_assessed"] = "not_assessed"
    ground_truth_metrics: Literal["unavailable"] = "unavailable"
    musical_correctness: Literal["not_proven_per_song"] = "not_proven_per_song"
    human_review: Literal["not_performed"] = "not_performed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def complete_evidence(self) -> Self:
        result = self.result
        if (self.frames, self.sample_rate, self.channels) != (
            result.source_frames,
            result.sample_rate,
            result.source_channels,
        ) or self.pcm.size_bytes != 58 + self.frames * self.channels * 8:
            raise ValueError("Candidate source clock or complete decoded PCM differs")
        if (self.model_input.size_bytes, self.model_input.sha256) != (
            result.model_frames * 8,
            result.model_input_sha256,
        ):
            raise ValueError("Model input evidence is incomplete")
        if len(self.partitions) != len(result.partitions):
            raise ValueError("Candidate partition evidence is incomplete")
        for artifact, native in zip(self.partitions, result.partitions, strict=True):
            if (
                artifact.partition != native.partition
                or artifact.input.sha256 != native.input_sha256
            ):
                raise ValueError("Candidate partition input differs from its native evidence")
            if {
                output.stem: output.file.sha256 for output in artifact.outputs
            } != native.output_sha256:
                raise ValueError("Candidate partition outputs differ from native evidence")
        if tuple(stem.stem for stem in self.stems) != STEMS:
            raise ValueError("Candidate must retain exactly the four canonical stems in order")
        tail_frames = result.returned_source_frames - self.frames
        for stem in self.stems:
            for identity, size, digest in (
                (stem.model, result.model_frames * 8, result.model_output_sha256[stem.stem]),
                (stem.source, 58 + self.frames * 8, result.source_output_sha256[stem.stem]),
                (stem.tail, tail_frames * 8, result.resampling_tail_sha256[stem.stem]),
            ):
                if (identity.size_bytes, identity.sha256) != (size, digest):
                    raise ValueError(
                        "Complete model/source/tail artifact disagrees with native output"
                    )
        if self.residual.size_bytes != self.frames * 16:
            raise ValueError("Unassigned residual must retain the complete stereo source grid")
        return self

    def witnesses(self) -> list[FileIdentity]:
        return [
            self.decode_report,
            self.source_audio,
            self.pcm,
            *self.decode_dependencies,
            self.backend_record,
            self.backend.python,
            *self.backend.runtime,
            *self.backend.artifacts,
            *self.backend.adapters,
            *self.model_dependencies,
            self.recipe.python_executable,
            *self.recipe.files,
            self.model_input,
            *[
                file
                for part in self.partitions
                for file in [part.input, *[o.file for o in part.outputs]]
            ],
            *[file for stem in self.stems for file in (stem.model, stem.source, stem.tail)],
            self.residual,
            self.native_result,
            self.native_request,
            self.stdout,
            self.stderr,
        ]


class SeparationReplayReceipt(Contract):
    profile: Literal["source-separation-fresh-replay-v1"] = "source-separation-fresh-replay-v1"
    original_report: FileIdentity
    replay_report: FileIdentity
    complete_match: Literal[True] = True
    evidence_scope: Literal["complete-current-source-native-artifacts"] = (
        "complete-current-source-native-artifacts"
    )
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False
