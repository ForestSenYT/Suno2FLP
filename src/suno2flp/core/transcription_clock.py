"""Fixed model-window addresses expressed in the derived source sample clock.

These anchors describe the adapter's coordinate system, not neural onset accuracy.
All 172 rows per window are retained; ownership excludes redundant context rows.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from suno2flp.core.models import Contract

MODEL_RATE = 22050
WINDOW_SAMPLES: Literal[43844] = 43844
STEP_SAMPLES = 36164
LEFT_PAD = 3840
OUTPUT_ROWS: Literal[172] = 172
MAX_MODEL_FRAMES = MODEL_RATE * 600


def _integer(value: int, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Integer outside the transcription clock budget")


class PredictionWindow(Contract):
    index: int = Field(ge=0, le=366, strict=True)
    virtual_start: int = Field(ge=-LEFT_PAD, strict=True)
    samples: Literal[43844] = WINDOW_SAMPLES
    rows: Literal[172] = OUTPUT_ROWS

    @model_validator(mode="after")
    def coordinate(self) -> Self:
        if self.virtual_start != self.index * STEP_SAMPLES - LEFT_PAD:
            raise ValueError("Window anchor disagrees with its index")
        return self


class PredictionRow(Contract):
    window: int = Field(ge=0, le=366, strict=True)
    row: int = Field(ge=15, le=156, strict=True)
    source_sample: int = Field(ge=0, lt=MAX_MODEL_FRAMES, strict=True)

    @model_validator(mode="after")
    def coordinate(self) -> Self:
        if self.source_sample != self.window * STEP_SAMPLES - LEFT_PAD + self.row * 256:
            raise ValueError("Row anchor disagrees with its raw address")
        return self


def resampled_frame_count(frames: int, sample_rate: int) -> int:
    _integer(sample_rate, 8000, 192000)
    _integer(frames, 1, 600 * sample_rate)
    return (frames * MODEL_RATE + sample_rate - 1) // sample_rate


def plan_prediction_windows(resampled_frames: int) -> list[PredictionWindow]:
    _integer(resampled_frames, 1, MAX_MODEL_FRAMES)
    return [
        PredictionWindow(index=index, virtual_start=start - LEFT_PAD)
        for index, start in enumerate(range(0, resampled_frames + LEFT_PAD, STEP_SAMPLES))
    ]


def owned_prediction_rows(resampled_frames: int) -> list[PredictionRow]:
    return [
        PredictionRow(window=window.index, row=row, source_sample=sample)
        for window in plan_prediction_windows(resampled_frames)
        for row in range(15, 157)
        if 0 <= (sample := window.virtual_start + row * 256) < resampled_frames
    ]
