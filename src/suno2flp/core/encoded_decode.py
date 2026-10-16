"""Compressed decode candidates and immutable attempts; stage completion needs replay."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.codec_backend import CodecAudioResult, CodecBackendRecord
from suno2flp.core.encoded_audio import EncodedAudioInventory
from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity


class EncodedDecodeRequest(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["compressed-decode-attempt-v1"] = "compressed-decode-attempt-v1"
    source: FileIdentity
    output_directory: Path
    decoder_directory: Path | None
    app_python: FileIdentity
    python_version: str = Field(min_length=1)
    adapters: list[FileIdentity]
    resampling: Literal["none"] = "none"
    channel_mapping: Literal["source-order"] = "source-order"
    frame_zero_presentation_frame: Literal[0] = 0
    sample_encoding: Literal["ieee-float64-little-endian"] = "ieee-float64-little-endian"


class EncodedDecodeReport(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["qualified-compressed-to-float64-v1"] = "qualified-compressed-to-float64-v1"
    inventory: EncodedAudioInventory
    request: FileIdentity
    backend_manifest: FileIdentity
    backend: CodecBackendRecord
    pcm: FileIdentity
    native: CodecAudioResult
    frame_zero_presentation_frame: Literal[0] = 0
    resampling: Literal["none"] = "none"
    channel_mapping: Literal["source-order"] = "source-order"
    verification_requirement: Literal["current-source-pinned-native-replay"] = (
        "current-source-pinned-native-replay"
    )
    lossless_oracle: Literal["streaminfo-md5", "unavailable-lossy"]
    musical_correctness: Literal["not_assessed"] = "not_assessed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def complete_clock_and_provenance(self) -> Self:
        source, native = self.inventory, self.native
        if (
            native.mode != "decode"
            or native.runtime != self.backend.probe
            or native.codec != source.codec
            or native.source_sha256 != source.source.sha256
            or (native.frames, native.sample_rate, native.channels)
            != (source.frames, source.sample_rate, source.channels)
            or self.pcm.sha256 != native.pcm_sha256
            or self.pcm.size_bytes != 58 + source.frames * source.channels * 8
            or self.backend_manifest.path != self.backend.root / "backend.json"
        ):
            raise ValueError(
                "Candidate must retain the complete current source clock/runtime/output"
            )
        if source.codec == "FLAC":
            if (
                source.flac is None
                or native.flac_pcm_md5 != source.flac.pcm_md5
                or self.lossless_oracle != "streaminfo-md5"
            ):
                raise ValueError("FLAC requires the independent source PCM MD5 oracle")
        elif native.flac_pcm_md5 is not None or self.lossless_oracle != "unavailable-lossy":
            raise ValueError("MP3 must not claim original uncompressed sample equality")
        return self
