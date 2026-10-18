"""Independent inferred MoE evidence; no writer or musical qualification."""

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.transcription import ModelArtifactPin
from suno2flp.core.yourmt3 import (
    Digest,
    FrameInterval,
    YourMT3IntervalSummary,
    YourMT3Note,
    YourMT3Tensor,
    YourMT3Window,
    plan_yourmt3_windows,
    validate_yourmt3_intervals,
)

Token = Annotated[int, Field(ge=0, lt=596, strict=True)]
Count = Annotated[int, Field(ge=0, strict=True)]


class YourMT3MoETokens(Contract):
    channel: int = Field(ge=0, lt=13, strict=True)
    tokens: list[Token] = Field(min_length=1, max_length=1024)


class YourMT3MoEWindow(YourMT3Window):
    initial: list[YourMT3MoETokens] = Field(min_length=13, max_length=13)
    retry: list[YourMT3MoETokens] | None = Field(default=None, min_length=13, max_length=13)

    @property
    def selected(self) -> list[YourMT3MoETokens]:
        return self.retry if self.retry is not None else self.initial

    @property
    def unresolved_channels(self) -> list[int]:
        return [stream.channel for stream in self.selected if 1 not in stream.tokens]

    @model_validator(mode="after")
    def generation(self) -> Self:
        for streams, maximum in [(self.initial, 256), (self.retry, 1024)]:
            if streams is None:
                continue
            if [stream.channel for stream in streams] != list(range(13)):
                raise ValueError("Retain all13 unique model channels in source address order")
            lengths = {len(stream.tokens) for stream in streams}
            if len(lengths) != 1 or max(lengths) > maximum:
                raise ValueError("Retain complete equal-width native streams within their bound")
            if any(1 not in stream.tokens for stream in streams) and lengths != {maximum}:
                raise ValueError("A short unfinished stream is incomplete generation evidence")
        needs_retry = any(1 not in stream.tokens for stream in self.initial)
        if needs_retry != (self.retry is not None):
            raise ValueError("Only a capped unfinished initial stream requires one bounded retry")
        if self.retry is not None and any(
            extended.tokens[:256] != original.tokens
            for original, extended in zip(self.initial, self.retry, strict=True)
        ):
            raise ValueError("Every initial token must be an identical retry prefix")
        return self


class YourMT3MoEChannel(Contract):
    channel: int = Field(ge=0, lt=13, strict=True)
    notes: list[YourMT3Note] = Field(max_length=100_000)
    decoded_windows: list[JsonValue] = Field(min_length=1, max_length=293)
    events: list[JsonValue] = Field(min_length=1, max_length=293)
    decode_errors: dict[str, Count]
    merge_errors: dict[str, Count]


class YourMT3MoENative(Contract):
    profile: Literal["yourmt3-moe-raw-adaptive-v1"] = "yourmt3-moe-raw-adaptive-v1"
    windows: list[YourMT3MoEWindow] = Field(min_length=1, max_length=293)
    channels: list[YourMT3MoEChannel] = Field(min_length=13, max_length=13)
    configuration: dict[str, JsonValue]
    versions: dict[str, str]
    seconds: float = Field(gt=0, le=2700, allow_inf_nan=False)
    peak_working_set_bytes: int = Field(gt=0, le=16 * 1024**3, strict=True)
    peak_commit_bytes: int = Field(gt=0, le=16 * 1024**3, strict=True)
    device: Literal["cpu"] = "cpu"
    threads: Literal[8] = 8
    interop_threads: Literal[1] = 1
    precision: Literal["float32"] = "float32"
    deterministic_algorithms: Literal[True] = True
    generation_policy: Literal["eos-256-retry1024-identical-prefix-v1"] = (
        "eos-256-retry1024-identical-prefix-v1"
    )
    musical_correctness: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"

    @model_validator(mode="after")
    def addresses(self) -> Self:
        if [channel.channel for channel in self.channels] != list(range(13)):
            raise ValueError("Keep all13 independently decoded channel records")
        # JSON provenance must remain finite, including opaque pre-merge event fields.
        json.dumps(self.model_dump(), allow_nan=False)
        if sum(len(channel.notes) for channel in self.channels) > 200_000:
            raise ValueError("MoE aggregate notes exceed the explicit raw evidence budget")
        return self


def check_yourmt3_moe_native(record: YourMT3MoENative, frames: int, sample_rate: int) -> None:
    record = YourMT3MoENative.model_validate(record.model_dump())
    expected = plan_yourmt3_windows(frames, sample_rate)
    actual = [
        YourMT3Window.model_validate(window.model_dump(exclude={"initial", "retry"}))
        for window in record.windows
    ]
    if actual != expected or any(
        len(channel.events) != len(expected) or len(channel.decoded_windows) != len(expected)
        for channel in record.channels
    ):
        raise ValueError("MoE channels must cover the continuous original clock and complete tail")
    padded_end = len(expected) * 32767 / 16000
    if any(
        note.onset > padded_end or note.offset > padded_end + 0.01
        for channel in record.channels
        for note in channel.notes
    ):
        raise ValueError("MoE native notes exceed the complete padded model clock")


class YourMT3MoEFilePin(Contract):
    filename: str
    target: str
    url: str
    size_bytes: int = Field(gt=0, le=1024**3, strict=True)
    sha256: Digest
    license: str


class YourMT3MoEGeneration(Contract):
    initial_max_tokens: Literal[256] = 256
    retry_max_tokens: Literal[1024] = 1024
    max_retries: Literal[1] = 1


class YourMT3MoEProgram(Contract):
    channel: int = Field(ge=0, lt=13, strict=True)
    instrument_group: str
    primary_program: int = Field(ge=0, le=128, strict=True)


class YourMT3MoEPins(Contract):
    profile: Literal["yourmt3-moe-cpu-windows-cp311-v1"]
    python_version: Literal["3.11.16"]
    source_revision: Literal["5e66c1ea173a8186e0d20432b841d3180cc015b5"]
    weights_revision: Literal["e45ebd70398682d54b7bb1901a5216e18f3b1824"]
    wheels: list[ModelArtifactPin] = Field(min_length=59, max_length=59)
    files: list[YourMT3MoEFilePin] = Field(min_length=41, max_length=41)
    state: dict[str, YourMT3Tensor] = Field(min_length=655, max_length=655)
    configuration: dict[str, object]
    unsafe_globals: list[str]
    generation_policy: YourMT3MoEGeneration
    program_channels: dict[int, YourMT3MoEProgram] = Field(min_length=99, max_length=99)


class YourMT3MoEBackend(Contract):
    profile: Literal["yourmt3-moe-cpu-windows-cp311-v1"] = "yourmt3-moe-cpu-windows-cp311-v1"
    root: Path
    python: FileIdentity
    runtime: list[FileIdentity]
    artifacts: list[FileIdentity]
    adapters: list[FileIdentity]
    payload: dict[str, Digest]
    model_qualification: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"


class YourMT3MoECandidate(Contract):
    profile: Literal["yourmt3-moe-unqualified-song-v1"] = "yourmt3-moe-unqualified-song-v1"
    root: Path
    backend: FileIdentity
    decode_report: FileIdentity
    source_audio: FileIdentity
    pcm: FileIdentity
    frames: int = Field(gt=0, strict=True)
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: Literal[1, 2]
    intervals: list[FrameInterval]
    raw: FileIdentity
    request: FileIdentity
    diagnostics: list[FileIdentity] = Field(min_length=2, max_length=2)
    summaries: list[YourMT3IntervalSummary]
    unresolved_generations: list[tuple[int, int]]
    musical_correctness: Literal["not_assessed"] = "not_assessed"
    writer_eligibility: Literal["blocked"] = "blocked"

    @model_validator(mode="after")
    def clock(self) -> Self:
        plan_yourmt3_windows(self.frames, self.sample_rate)
        validate_yourmt3_intervals(self.intervals, self.frames)
        if any(
            not 0 <= window < 293 or not 0 <= channel < 13
            for window, channel in self.unresolved_generations
        ):
            raise ValueError("Invalid addressed incomplete generation")
        return self
