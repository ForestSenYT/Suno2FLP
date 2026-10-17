"""Independent probe readback catches lost samples, false repeats and moved impulses."""

import hashlib
import importlib
import struct

import pytest

from suno2flp.core.separation_runtime import PROBE_FRAMES, STEMS, SeparationFixtureResult


def _outputs(module, root, fixture):
    source = module.fixture_bytes(fixture)
    (root / f"{fixture}.input.f32").write_bytes(source)
    values = [v[0] for v in struct.iter_unpack("<f", source)]
    hashes = {}
    for index, name in enumerate(STEMS):
        raw = b"".join(struct.pack("<f", v * (index + 1) / 10) for v in values)
        for run in (1, 2):
            (root / f"{fixture}.{name}.{run}.f32").write_bytes(raw)
        hashes[name] = [hashlib.sha256(raw).hexdigest()] * 2
    return SeparationFixtureResult(fixture=fixture, frames=PROBE_FRAMES[fixture], hashes=hashes)


def test_probe_fixtures_retain_boundary_impulses_and_separate_channels():
    module = importlib.import_module("suno2flp.core.separation_probe")
    raw = module.fixture_bytes("impulses")
    pairs = list(struct.iter_unpack("<ff", raw))
    assert len(pairs) == 12347
    assert [(i, p) for i, p in enumerate(pairs) if p != (0.0, 0.0)] == [
        (0, (0.5, 0.0)),
        (6000, (0.25, 0.0)),
        (12346, (0.0, 0.75)),
    ]
    assert module.fixture_bytes("silence") == bytes(1025 * 8)


@pytest.mark.parametrize("fixture", ["silence", "impulses", "stereo-pattern"])
def test_readback_retains_raw_outputs_and_explicit_residual(tmp_path, fixture):
    module = importlib.import_module("suno2flp.core.separation_probe")
    result = _outputs(module, tmp_path, fixture)
    evidence = module.check_fixture(tmp_path, result)
    assert evidence.residual.size_bytes == PROBE_FRAMES[fixture] * 2 * 8
    assert evidence.conservation_error <= 1e-12
    if fixture == "impulses":
        assert evidence.impulse_peak_frames == [0, 6000, 12346]
    with pytest.raises(FileExistsError):
        module.check_fixture(tmp_path, result)


@pytest.mark.parametrize("mutation", ["tail", "nan", "repeat", "shift", "source", "all-zero"])
def test_rehashed_false_native_outputs_are_rejected(tmp_path, mutation):
    module = importlib.import_module("suno2flp.core.separation_probe")
    result = _outputs(module, tmp_path, "impulses")
    for name in STEMS:
        for run in (1, 2):
            path = tmp_path / f"impulses.{name}.{run}.f32"
            raw = path.read_bytes()
            if mutation == "tail":
                raw = raw[:-8]
            elif mutation == "nan":
                raw = struct.pack("<f", float("nan")) + raw[4:]
            elif mutation == "repeat" and run == 2:
                raw = struct.pack("<f", 0.125) + raw[4:]
            elif mutation == "shift":
                raw = bytes(16) + raw[:-16]
            elif mutation == "all-zero":
                raw = bytes(len(raw))
            path.write_bytes(raw)
            # A forged report can rehash both runs; independent readback must still fail.
            if run == 1:
                result.hashes[name] = [hashlib.sha256(raw).hexdigest()] * 2
    if mutation == "source":
        (tmp_path / "impulses.input.f32").write_bytes(bytes(12347 * 8))
    with pytest.raises(ValueError):
        module.check_fixture(tmp_path, result)
