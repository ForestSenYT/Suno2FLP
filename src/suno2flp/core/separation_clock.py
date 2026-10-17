"""Integer source clocks and the fixed model's global STFT partition addresses."""

from typing import Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract

MODEL_RATE = 44100
FRAME_LENGTH = 4096
FRAME_STEP = 1024
PARTITION_ROWS = 512
MAX_MODEL_FRAMES = MODEL_RATE * 600


def _integer(value: int, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Integer outside the fixed separation clock budget")


def model_frame_count(frames: int, sample_rate: int) -> int:
    _integer(sample_rate, 8000, 192000)
    _integer(frames, 1, sample_rate * 600)
    return (frames * MODEL_RATE + sample_rate - 1) // sample_rate


def back_frame_count(model_frames: int, sample_rate: int) -> int:
    _integer(sample_rate, 8000, 192000)
    _integer(model_frames, 1, MAX_MODEL_FRAMES)
    return (model_frames * sample_rate + MODEL_RATE - 1) // MODEL_RATE


class SeparationPartition(Contract):
    index: int = Field(ge=0, le=50, strict=True)
    stft_start: int = Field(ge=0, le=25600, strict=True)
    stft_frames: int = Field(gt=0, le=512, strict=True)
    virtual_start: int = Field(ge=-4096, strict=True)
    waveform_frames: int = Field(ge=4096, le=527360, strict=True)

    @model_validator(mode="after")
    def global_coordinates(self) -> Self:
        if (
            self.stft_start != self.index * PARTITION_ROWS
            or self.virtual_start != self.stft_start * FRAME_STEP - FRAME_LENGTH
            or self.waveform_frames != (self.stft_frames - 1) * FRAME_STEP + FRAME_LENGTH
        ):
            raise ValueError("Partition geometry disagrees with the fixed global STFT clock")
        return self


def plan_separation_partitions(model_frames: int) -> list[SeparationPartition]:
    _integer(model_frames, 1, MAX_MODEL_FRAMES)
    rows = (model_frames + FRAME_LENGTH + FRAME_STEP - 1) // FRAME_STEP
    result = []
    for index, start in enumerate(range(0, rows, PARTITION_ROWS)):
        count = min(PARTITION_ROWS, rows - start)
        result.append(
            SeparationPartition(
                index=index,
                stft_start=start,
                stft_frames=count,
                virtual_start=start * FRAME_STEP - FRAME_LENGTH,
                waveform_frames=(count - 1) * FRAME_STEP + FRAME_LENGTH,
            )
        )
    return result
