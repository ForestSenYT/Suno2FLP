"""Original side-info fixtures prove exact audio payload extents before native decoding."""

import pytest

from suno2flp.core.errors import OfflineError


def side_info(samples, channels, pointer, lengths):
    mpeg1 = samples == 1152
    bits = f"{pointer:0{9 if mpeg1 else 8}b}"
    bits += "0" * ((5 if channels == 1 else 3) if mpeg1 else channels)
    bits += "0" * (4 * channels if mpeg1 else 0)
    for length in lengths:
        bits += f"{length:012b}" + "0" * ((59 if mpeg1 else 63) - 12)
    assert len(bits) in (72, 136, 256) and len(bits) % 8 == 0
    return int(bits, 2).to_bytes(len(bits) // 8, "big")


def state():
    from suno2flp.importer.mpeg_side_info import MpegMainDataExtent

    return MpegMainDataExtent()


@pytest.mark.parametrize("samples", [576, 1152])
@pytest.mark.parametrize("channels", [1, 2])
def test_no_xing_header_crc_or_id3_bytes_can_supply_first_audio_reservoir(samples, channels):
    with pytest.raises(OfflineError, match="reservoir"):
        state().consume(
            side_info(samples, channels, 1, [0] * ((2 if samples == 1152 else 1) * channels)),
            samples=samples,
            channels=channels,
            payload_bytes=100,
        )


@pytest.mark.parametrize("samples", [576, 1152])
@pytest.mark.parametrize("channels", [1, 2])
def test_valid_nonzero_backpointer_and_unused_ancillary_bits_are_preserved(samples, channels):
    count = (2 if samples == 1152 else 1) * channels
    tracker = state()
    tracker.consume(
        side_info(samples, channels, 0, [75] + [0] * (count - 1)),
        samples=samples,
        channels=channels,
        payload_bytes=100,
    )
    # Current payload starts at byte100; begin at byte10, after the previous 75bits.
    tracker.consume(
        side_info(samples, channels, 90, [40] + [0] * (count - 1)),
        samples=samples,
        channels=channels,
        payload_bytes=100,
    )
    assert tracker.payload_bytes == 200 and tracker.previous_end_bits == 120


@pytest.mark.parametrize("samples", [576, 1152])
@pytest.mark.parametrize("channels", [1, 2])
def test_main_data_cannot_reuse_consumed_bits_or_extend_into_future_frames(samples, channels):
    count = (2 if samples == 1152 else 1) * channels
    tracker = state()
    tracker.consume(
        side_info(samples, channels, 0, [800] + [0] * (count - 1)),
        samples=samples,
        channels=channels,
        payload_bytes=100,
    )
    with pytest.raises(OfflineError, match="overlap"):
        tracker.consume(
            side_info(samples, channels, 1, [1] + [0] * (count - 1)),
            samples=samples,
            channels=channels,
            payload_bytes=100,
        )
    with pytest.raises(OfflineError, match="available"):
        state().consume(
            side_info(samples, channels, 0, [801] + [0] * (count - 1)),
            samples=samples,
            channels=channels,
            payload_bytes=100,
        )


def test_every_granule_and_channel_length_contributes_to_bounds():
    with pytest.raises(OfflineError, match="available"):
        state().consume(
            side_info(1152, 2, 0, [200, 200, 200, 201]), samples=1152, channels=2, payload_bytes=100
        )
