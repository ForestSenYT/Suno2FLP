"""Integer source coordinates, independently of upstream's heuristic time conversion."""

import pytest
from pydantic import ValidationError

from suno2flp.core.transcription_clock import (
    PredictionRow,
    owned_prediction_rows,
    plan_prediction_windows,
    resampled_frame_count,
)


@pytest.mark.parametrize("frames", [1, 256, 36164, 36165, 39999, 22050 * 175, 22050 * 600])
def test_all_source_anchors_are_unique_ordered_and_reach_the_tail(frames: int) -> None:
    windows = plan_prediction_windows(frames)
    rows = owned_prediction_rows(frames)
    anchors = [row.source_sample for row in rows]
    assert anchors[0] == 0
    assert anchors == sorted(set(anchors))
    assert 0 < frames - anchors[-1] <= 256
    assert all(0 < b - a <= 256 for a, b in zip(anchors, anchors[1:], strict=False))
    assert len(windows) == (frames + 3840 + 36163) // 36164
    for row in rows:
        assert 15 <= row.row <= 156
        assert row.source_sample == row.window * 36164 - 3840 + row.row * 256
        assert row.source_sample < frames
    assert windows[0].virtual_start == -3840
    assert windows[-1].index == len(windows) - 1
    assert all(window.rows == 172 and window.samples == 43844 for window in windows)


def test_seam_has_a_short_real_gap_and_keeps_raw_addresses() -> None:
    rows = owned_prediction_rows(36165)
    assert [(r.window, r.row, r.source_sample) for r in rows[-2:]] == [
        (0, 156, 36096),
        (1, 15, 36164),
    ]
    assert len(plan_prediction_windows(36164)) == 2
    assert owned_prediction_rows(1) == [PredictionRow(window=0, row=15, source_sample=0)]


@pytest.mark.parametrize("frames, count, last", [(44100, 173, 43844), (44101, 174, 44100)])
def test_exact_two_second_endpoint_is_excluded_until_it_contains_a_sample(
    frames: int, count: int, last: int
) -> None:
    # First window contributes 142 rows. Second starts at sample36164; its
    # row46 anchor is44100, exactly outside the two-second half-open source.
    rows = owned_prediction_rows(frames)
    assert len(rows) == count
    assert sum(row.window == 0 for row in rows) == 142
    assert sum(row.window == 1 for row in rows) == count - 142
    assert rows[-1].source_sample == last
    assert rows[-1].row == (45 if frames == 44100 else 46)
    assert len(plan_prediction_windows(frames)) == 2


@pytest.mark.parametrize("frames", [0, -1, True, 1.5, 22050 * 600 + 1, 10**100])
def test_window_budget_rejects_invalid_input(frames: int) -> None:
    with pytest.raises(ValueError):
        plan_prediction_windows(frames)
    with pytest.raises(ValueError):
        owned_prediction_rows(frames)


def test_resampling_count_is_ceiling_with_a_fixed_origin() -> None:
    assert resampled_frame_count(1, 48000) == 1
    assert resampled_frame_count(8400000, 48000) == 3858750
    assert resampled_frame_count(192000 * 600, 192000) == 22050 * 600
    for frames, rate in [(0, 48000), (1, 7999), (4800001, 8000), (1, True)]:
        with pytest.raises(ValueError):
            resampled_frame_count(frames, rate)


def test_row_contract_rejects_an_invented_coordinate() -> None:
    with pytest.raises(ValidationError, match="anchor"):
        PredictionRow(window=1, row=15, source_sample=36163)
    with pytest.raises(ValidationError):
        PredictionRow(window=0, row=14, source_sample=0)
