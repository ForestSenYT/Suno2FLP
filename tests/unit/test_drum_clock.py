"""Exact row anchors derived from selected graph padding, never rounded source ticks."""

from fractions import Fraction

import pytest

from suno2flp.core.drum_clock import (
    drum_domain,
    drum_model_sample,
    drum_output_rows,
    drum_source_time,
)


@pytest.mark.parametrize("frames,rows", [(513, 16), (1024, 17), (1025, 18), (44100, 186)])
def test_full_native_rows_include_centered_fft_and_twelve_extra_rows(frames, rows):
    assert drum_output_rows(frames) == rows


def test_negative_anchors_and_fractional_source_coordinates_never_clamped():
    assert drum_model_sample(0) == -1536
    assert drum_model_sample(5) == -256
    assert drum_model_sample(6) == 0
    assert drum_model_sample(7) == 256
    assert drum_source_time(0) == Fraction(-1536 * 1_000_000, 44100)
    assert drum_source_time(7) == Fraction(256 * 1_000_000, 44100)
    assert drum_source_time(7) * 48000 / 1_000_000 == Fraction(256 * 48000, 44100)


def test_domains_use_exact_original_duration_and_keep_padding_addresses():
    assert drum_domain(0, 1393, 48000) == "leading_padding"
    assert drum_domain(6, 1393, 48000) == "source"
    assert drum_domain(10, 1393, 48000) == "source"
    assert drum_domain(11, 1393, 48000) == "tail_padding"
    assert drum_domain(11, 1394, 48000) == "source"
    # Exact EOF belongs to padding; all rows after EOF remain represented.
    assert drum_domain(10, 1024, 44100) == "tail_padding"
    assert drum_domain(16, 1024, 44100) == "tail_padding"


@pytest.mark.parametrize("frames", [True, 1, 512, 26460001, 1.5])
def test_unsupported_native_lengths_fail_explicitly(frames):
    with pytest.raises(ValueError):
        drum_output_rows(frames)


@pytest.mark.parametrize("row", [True, -1, 103373, 1.5])
def test_invalid_row_addresses_fail(row):
    with pytest.raises(ValueError):
        drum_model_sample(row)


def test_out_of_current_native_output_and_invalid_source_geometry_rejected():
    with pytest.raises(ValueError):
        drum_domain(17, 1024, 44100)
    with pytest.raises(ValueError):
        drum_domain(6, 1000, 1)
    with pytest.raises(ValueError):
        drum_domain(6, True, 44100)
