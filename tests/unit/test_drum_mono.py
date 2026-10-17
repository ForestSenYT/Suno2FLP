"""Independent oracle reads serialized stereo values and preserves signed zero."""

import struct

import pytest

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.integrations.drum_probe import verify_drum_mono


def test_complete_pairwise_mean_oracle(tmp_path):
    pairs = [(-0.0, -0.0), (1.0, -0.5), (0.3, 0.2), (-1.0, 1.0)]
    source = tmp_path / "source.f32"
    mono = tmp_path / "mono.f32"
    source.write_bytes(b"".join(struct.pack("<ff", *p) for p in pairs))
    rounded = list(struct.iter_unpack("<ff", source.read_bytes()))
    mono.write_bytes(b"".join(struct.pack("<f", (a + b) * 0.5) for a, b in rounded))
    before = [capture_stream_input(p) for p in (source, mono)]
    verify_drum_mono(*before, len(pairs))
    assert mono.read_bytes()[:4] == struct.pack("<f", -0.0)
    assert before == [capture_stream_input(p) for p in (source, mono)]
    mono.write_bytes(struct.pack("<f", 0.0) + mono.read_bytes()[4:])
    with pytest.raises(ValueError, match="oracle"):
        verify_drum_mono(capture_stream_input(source), capture_stream_input(mono), len(pairs))


@pytest.mark.parametrize("change", ["truncated", "nonfinite", "changed"])
def test_invalid_mono_source_or_witness_rejected(tmp_path, change):
    source = tmp_path / "source.f32"
    mono = tmp_path / "mono.f32"
    source.write_bytes(struct.pack("<ff", 0.25, 0.5))
    mono.write_bytes(struct.pack("<f", 0.375))
    first, second = capture_stream_input(source), capture_stream_input(mono)
    if change == "truncated":
        mono.write_bytes(b"\0")
        second = capture_stream_input(mono)
    elif change == "nonfinite":
        source.write_bytes(struct.pack("<ff", float("nan"), 0.0))
        first = capture_stream_input(source)
    else:
        mono.write_bytes(struct.pack("<f", 0.5))
    with pytest.raises(ValueError):
        verify_drum_mono(first, second, 1)
