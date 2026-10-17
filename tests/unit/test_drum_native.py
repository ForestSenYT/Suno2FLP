"""Inert contracts validate complete rows and native shape declarations."""

import pytest

from suno2flp.core.drum_native import NativeDrumArray


def test_native_array_is_full_little_endian_float32():
    value = NativeDrumArray(shape=[9, 17], size_bytes=9 * 17 * 4, sha256="0" * 64)
    assert value.encoding == "<f4"


@pytest.mark.parametrize("shape,size", [([9, 17], 0), ([0], 0), ([True], 4), ([9, 17, 1], 612)])
def test_invalid_or_truncated_shape_rejected(shape, size):
    with pytest.raises(ValueError):
        NativeDrumArray(shape=shape, size_bytes=size, sha256="0" * 64)
