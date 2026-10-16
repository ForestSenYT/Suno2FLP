"""Complete supported encoded-container evidence, separate from native sample decoding."""

from fractions import Fraction
from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime


class EncodedRegion(Contract):
    kind: str = Field(min_length=1)
    offset: int = Field(ge=0, strict=True)
    size_bytes: int = Field(gt=0, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FlacStreamInfo(Contract):
    raw_streaminfo_hex: str = Field(pattern=r"^[0-9a-f]{68}$")
    bits_per_sample: Literal[8, 16, 24]
    pcm_md5: str = Field(pattern=r"^[0-9a-f]{32}$")
    min_block_frames: int = Field(ge=16, le=65535, strict=True)
    max_block_frames: int = Field(ge=16, le=65535, strict=True)


class Mp3GaplessInfo(Contract):
    reservoir_validation: Literal["layer-iii-audio-main-data-extents-v1"] = (
        "layer-iii-audio-main-data-extents-v1"
    )
    side_info_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_tag_hex: str = Field(pattern=r"^(?:[0-9a-f]{2})+$")
    tag_offset: int = Field(ge=0, strict=True)
    encoder_hex: str = Field(pattern=r"^[0-9a-f]{18}$")
    encoder_delay: int = Field(ge=0, le=3000, strict=True)
    encoder_padding: int = Field(ge=0, le=3000, strict=True)
    audio_frames: int = Field(gt=0, strict=True)
    samples_per_frame: Literal[576, 1152]
    encoded_bytes: int = Field(gt=0, strict=True)
    music_crc16: int = Field(ge=0, le=65535, strict=True)
    tag_crc16: int = Field(ge=0, le=65535, strict=True)


class EncodedAudioInventory(Contract):
    schema_version: Literal[1] = 1
    profile: Literal["flac-mpeg-container-v1"] = "flac-mpeg-container-v1"
    source: FileIdentity
    codec: Literal["FLAC", "MP3"]
    sample_rate: int = Field(ge=8000, le=192000, strict=True)
    channels: int = Field(ge=1, le=2, strict=True)
    frames: int = Field(gt=0, strict=True)
    frame_count: int = Field(gt=0, le=1_000_000, strict=True)
    data_offset: int = Field(ge=0, strict=True)
    data_end: int = Field(gt=0, strict=True)
    frame_headers_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: list[EncodedRegion]
    flac: FlacStreamInfo | None = None
    mp3: Mp3GaplessInfo | None = None
    duration_microseconds: RationalTime
    decode_status: Literal["not_performed"] = "not_performed"
    musical_correctness: Literal["not_assessed"] = "not_assessed"
    host_compatibility: Literal["unverified"] = "unverified"
    writer_eligibility: Literal["blocked"] = "blocked"

    @model_validator(mode="after")
    def exact_supported_clock(self) -> Self:
        if not self.data_offset < self.data_end <= self.source.size_bytes:
            raise ValueError("Encoded audio extent must be inside the original input")
        if self.frames > self.sample_rate * 600 or self.duration_microseconds != RationalTime.exact(
            Fraction(self.frames * 1_000_000, self.sample_rate)
        ):
            raise ValueError("Presentation clock must be exact and within ten minutes")
        if any(
            region.offset + region.size_bytes > self.source.size_bytes for region in self.metadata
        ):
            raise ValueError("Metadata region exceeds original source")
        if self.codec == "FLAC":
            if self.flac is None or self.mp3 is not None or self.flac.pcm_md5 == "0" * 32:
                raise ValueError("FLAC requires complete stream info and a known PCM MD5")
        else:
            if self.mp3 is None or self.flac is not None:
                raise ValueError("MP3 requires qualified gapless metadata")
            tag = self.mp3
            if (
                self.frame_count != tag.audio_frames + 1
                or self.frames
                != tag.audio_frames * tag.samples_per_frame
                - tag.encoder_delay
                - tag.encoder_padding
                or tag.encoded_bytes != self.data_end - self.data_offset
            ):
                raise ValueError("MP3 presentation clock must account for every coded frame")
        return self
