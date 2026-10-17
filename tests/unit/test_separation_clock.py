"""Hand-derived source/model and globally anchored STFT boundary cases."""

import importlib

import pytest


def clock():
    return importlib.import_module("suno2flp.core.separation_clock")


@pytest.mark.parametrize(
    "frames,rate,model,returned",
    [
        (1, 192000, 1, 5),
        (8001, 8000, 44106, 8002),
        (16001, 16000, 44103, 16002),
        (22051, 22050, 44102, 22051),
        (44101, 44100, 44101, 44101),
        (48001, 48000, 44101, 48002),
        (96001, 96000, 44101, 96003),
        (192001, 192000, 44101, 192005),
    ],
)
def test_rational_sample_counts_keep_odd_tail(frames, rate, model, returned):
    assert clock().model_frame_count(frames, rate) == model
    assert clock().back_frame_count(model, rate) == returned


@pytest.mark.parametrize(
    "frames,counts,last_start,last_waveform",
    [
        (1, [5], -4096, 8192),
        (1023, [5], -4096, 8192),
        (1024, [5], -4096, 8192),
        (1025, [6], -4096, 9216),
        (4095, [8], -4096, 11264),
        (4096, [8], -4096, 11264),
        (4097, [9], -4096, 12288),
        (520191, [512], -4096, 527360),
        (520192, [512], -4096, 527360),
        (520193, [512, 1], 520192, 4096),
        (1044480, [512, 512], 520192, 527360),
        (1044481, [512, 512, 1], 1044480, 4096),
    ],
)
def test_global_partition_context_and_tail(frames, counts, last_start, last_waveform):
    parts = clock().plan_separation_partitions(frames)
    assert [part.stft_frames for part in parts] == counts
    assert parts[0].virtual_start == -4096
    assert parts[-1].virtual_start == last_start
    assert parts[-1].waveform_frames == last_waveform
    for left, right in zip(parts, parts[1:], strict=False):
        assert left.stft_start + left.stft_frames == right.stft_start
        assert left.virtual_start + left.waveform_frames - right.virtual_start == 3072


@pytest.mark.parametrize("rate", [8000, 22050, 44100, 48000, 96000, 192000])
def test_ten_minutes_covers_complete_last_partition(rate):
    module = clock()
    frames = module.model_frame_count(rate * 600, rate)
    parts = module.plan_separation_partitions(frames)
    assert frames == 26460000
    assert len(parts) == 51
    assert parts[-1].stft_start == 25600
    assert parts[-1].stft_frames == 244
    assert parts[-1].virtual_start == 26210304
    assert parts[-1].waveform_frames == 252928
    assert module.back_frame_count(frames, rate) == rate * 600
    with pytest.raises(ValueError):
        module.model_frame_count(rate * 600 + 1, rate)


@pytest.mark.parametrize(
    "frames,rate",
    [(0, 44100), (-1, 44100), (True, 44100), (1, True), (1.5, 44100), (1, 7999), (1, 192001)],
)
def test_invalid_source_clock_is_not_coerced(frames, rate):
    with pytest.raises(ValueError):
        clock().model_frame_count(frames, rate)


@pytest.mark.parametrize("frames", [0, -1, True, 1.5, 26460001])
def test_invalid_model_clock_is_not_truncated(frames):
    with pytest.raises(ValueError):
        clock().plan_separation_partitions(frames)


def test_partition_cannot_claim_a_different_global_origin():
    module = clock()
    values = dict(
        index=1, stft_start=512, stft_frames=1, virtual_start=520192, waveform_frames=4096
    )
    for field, wrong in (
        ("index", 0),
        ("virtual_start", 0),
        ("stft_start", 0),
        ("waveform_frames", 4097),
        ("stft_frames", True),
    ):
        with pytest.raises(ValueError):
            module.SeparationPartition(**{**values, field: wrong})
