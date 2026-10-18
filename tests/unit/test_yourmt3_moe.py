"""Original small generation traces: all channels, clocks and source prefixes."""

import importlib
import importlib.util
from copy import deepcopy

import pytest
from pydantic import ValidationError


def core():
    name = "suno2flp.core.yourmt3_moe"
    assert importlib.util.find_spec(name) is not None, "Missing independent MoE profile"
    return importlib.import_module(name)


def streams(length=2):
    return [dict(channel=c, tokens=[339, 1] + [0] * (length - 2)) for c in range(13)]


def window(index=0, valid=32767):
    return dict(index=index, start_frame=index * 32767, valid_frames=valid, initial=streams())


def capped_window(retry_length=257, finished=True):
    value = window()
    value["initial"] = streams(256)
    value["initial"][0]["tokens"] = [339] + [44] * 255
    value["retry"] = deepcopy(value["initial"])
    for channel in value["retry"]:
        channel["tokens"] += [0] * (retry_length - 256)
    if finished:
        value["retry"][0]["tokens"][-1] = 1
    return value


def native():
    return dict(
        windows=[window(), window(1, 1)],
        channels=[
            dict(
                channel=c,
                notes=[],
                decoded_windows=[[[], [], [], 0.0], [[], [], [], 32767 / 16000]],
                events=[[], []],
                decode_errors={},
                merge_errors={},
            )
            for c in range(13)
        ],
        configuration={},
        versions={},
        seconds=1.0,
        peak_working_set_bytes=1000,
        peak_commit_bytes=2000,
    )


def test_moe_retry_preserves_every_initial_token_and_channel():
    module = core()
    data = capped_window()
    saved = deepcopy(data)
    result = module.YourMT3MoEWindow.model_validate(data)
    assert result.selected[0].tokens[-1] == 1
    assert result.selected[0].tokens[:256] == saved["initial"][0]["tokens"]
    assert result.unresolved_channels == []
    assert data == saved
    assert result.model_dump()["initial"] == saved["initial"]


@pytest.mark.parametrize("field", ["initial", "retry"])
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered"])
def test_moe_requires_all_thirteen_addressed_streams(field, mutation):
    module = core()
    data = capped_window()
    if mutation == "missing":
        data[field].pop()
    elif mutation == "duplicate":
        data[field][1] = deepcopy(data[field][0])
    else:
        data[field][1], data[field][2] = data[field][2], data[field][1]
    with pytest.raises(ValidationError):
        module.YourMT3MoEWindow.model_validate(data)


def test_moe_rejects_changed_prefix_and_unnecessary_or_missing_retry():
    module = core()
    altered = capped_window()
    altered["retry"][0]["tokens"][3] += 1
    missing = capped_window()
    missing.pop("retry")
    unnecessary = window()
    unnecessary["retry"] = streams()
    short = window()
    short["initial"][0]["tokens"] = [339, 44]
    for data in [altered, missing, unnecessary, short]:
        with pytest.raises(ValidationError):
            module.YourMT3MoEWindow.model_validate(data)


def test_moe_retains_bounded_unfinished_stream_without_claiming_success():
    module = core()
    result = module.YourMT3MoEWindow.model_validate(capped_window(1024, finished=False))
    assert result.unresolved_channels == [0]
    with pytest.raises(ValidationError):
        module.YourMT3MoEWindow.model_validate(capped_window(1023, finished=False))
    with pytest.raises(ValidationError):
        module.YourMT3MoEWindow.model_validate(capped_window(1025))


def test_moe_native_covers_full_original_clock_and_one_frame_tail():
    module = core()
    value = module.YourMT3MoENative.model_validate(native())
    module.check_yourmt3_moe_native(value, 98304, 48000)
    assert value.writer_eligibility == "blocked"
    value.windows[-1].valid_frames = 2
    with pytest.raises(ValueError, match="clock|tail|continuous"):
        module.check_yourmt3_moe_native(value, 98304, 48000)


def test_moe_native_rejects_missing_channel_records_and_nonfinite_evidence():
    module = core()
    missing = native()
    missing["channels"].pop()
    nonfinite = native()
    nonfinite["channels"][0]["events"][0] = [float("nan")]
    promoted = {**native(), "writer_eligibility": "allowed"}
    for data in [missing, nonfinite, promoted]:
        with pytest.raises(ValidationError):
            module.YourMT3MoENative.model_validate(data)


def test_moe_pin_does_not_expand_the_single_checkpoint_boundary():
    module = core()
    from suno2flp.core.yourmt3 import YourMT3FilePin

    data = dict(
        filename="last.ckpt",
        target="models/last.ckpt",
        url="https://example.test",
        size_bytes=561544628,
        sha256="a" * 64,
        license="Apache-2.0",
    )
    assert module.YourMT3MoEFilePin.model_validate(data).size_bytes == 561544628
    with pytest.raises(ValidationError):
        YourMT3FilePin.model_validate(data)
