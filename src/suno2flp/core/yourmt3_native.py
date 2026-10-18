"""Bounded raw tokens, native decoding and measurements; no musical qualification."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue

from suno2flp.core.models import Contract
from suno2flp.core.yourmt3 import YourMT3Note, YourMT3Window, plan_yourmt3_windows


class YourMT3Tokens(YourMT3Window):
    tokens: list[Annotated[int, Field(ge=0, lt=596, strict=True)]] = Field(
        min_length=1, max_length=1024
    )


class YourMT3Native(Contract):
    profile: Literal["yourmt3-single-raw-v1"] = "yourmt3-single-raw-v1"
    windows: list[YourMT3Tokens] = Field(min_length=1, max_length=293)
    notes: list[YourMT3Note] = Field(max_length=100_000)
    decoded_windows: list[JsonValue] = Field(min_length=1, max_length=293)
    events: list[JsonValue] = Field(min_length=1, max_length=293)
    decode_errors: dict[str, Annotated[int, Field(ge=0, strict=True)]]
    merge_errors: dict[str, Annotated[int, Field(ge=0, strict=True)]]
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
    musical_correctness: Literal["not_assessed"] = "not_assessed"


def check_yourmt3_native(record: YourMT3Native, frames: int, sample_rate: int) -> None:
    record = YourMT3Native.model_validate(record.model_dump())
    windows = plan_yourmt3_windows(frames, sample_rate)
    if (
        [YourMT3Window.model_validate(w.model_dump(exclude={"tokens"})) for w in record.windows]
        != (windows)
        or len(record.events) != len(windows)
        or len(record.decoded_windows) != len(windows)
    ):
        raise ValueError("YourMT3 evidence must cover all continuous windows and the complete tail")
    padded_end = len(windows) * 32767 / 16000
    if any(n.onset > padded_end or n.offset > padded_end + 0.01 for n in record.notes):
        raise ValueError("Native notes exceed the complete padded model clock")
