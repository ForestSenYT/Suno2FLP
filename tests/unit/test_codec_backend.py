"""Offline prerequisite/integrity checks never silently install or load native code."""

import sys
from pathlib import Path

import pytest

from suno2flp.core.errors import OfflineError


def api():
    from suno2flp.integrations import codec_backend

    return codec_backend


def test_profile_pins_every_dependency_and_native_library_for_both_platforms():
    pins = api().load_codec_pins()
    assert pins.python_versions == {"cp311": "3.11.16", "cp314": "3.14.7"}
    assert pins.soundfile_revision == "3162358d0315be769b97f3e4c12545fe18a676bc"
    assert pins.native_revision == "a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87"
    assert set(pins.platforms) == {
        f"{host}-{abi}" for host in ("windows-x86_64", "linux-x86_64") for abi in ("cp311", "cp314")
    }
    for profile in pins.platforms.values():
        assert {wheel.distribution: wheel.version for wheel in profile.wheels} == {
            "soundfile": "0.14.0",
            "numpy": "2.3.5",
            "cffi": "2.0.0",
            "pycparser": "2.23",
            "typing_extensions": "4.16.0",
        }
        assert len({wheel.filename for wheel in profile.wheels}) == 5
        assert all(
            wheel.url.startswith("https://files.pythonhosted.org/packages/")
            for wheel in profile.wheels
        )
        assert all(len(wheel.sha256) == 64 and wheel.size_bytes > 0 for wheel in profile.wheels)
    assert (
        pins.platforms["windows-x86_64-cp311"].native_sha256
        == "22518c16f9d13eda5ae5adf999c4740d7d16cc2d6b178b36dd4ac2f759a38559"
    )
    assert (
        pins.platforms["linux-x86_64-cp314"].native_sha256
        == "c872fb84af2afc0e96b603e0000f0f407af86c49ad1126f2785e5722c7bb27d7"
    )


def test_existing_and_nested_destinations_are_rejected_before_provisioning(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises((OfflineError, OSError)):
        api().provision_codec_backend(existing, Path(sys.executable), wheelhouse=tmp_path)
    assert sentinel.read_text() == "keep" and sorted(p.name for p in existing.iterdir()) == [
        "keep.txt"
    ]
    (existing / "backend.json").write_text("{}")
    with pytest.raises(OfflineError):
        api().provision_codec_backend(existing / "new", Path(sys.executable), wheelhouse=tmp_path)
    assert not (existing / "new").exists()


def test_missing_offline_wheelhouse_never_downloads_or_claims_ready(tmp_path):
    root = tmp_path / "runtime"
    with pytest.raises(OfflineError) as error:
        api().provision_codec_backend(root, Path(sys.executable), wheelhouse=tmp_path / "missing")
    assert error.value.blocked
    assert not (root / "backend.json").exists()


def test_corrupt_offline_wheel_is_not_extracted_or_executed(tmp_path):
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    pins = api().load_codec_pins()
    profile = pins.platforms[f"{api().codec_platform()}-{api().codec_abi()}"]
    for wheel in profile.wheels:
        (wheelhouse / wheel.filename).write_bytes(b"wrong payload")
    root = tmp_path / "runtime"
    with pytest.raises(OfflineError) as error:
        api().provision_codec_backend(root, Path(sys.executable), wheelhouse=wheelhouse)
    assert error.value.code == "audio_wheel_integrity_failed" and error.value.blocked
    assert not (root / "backend.json").exists() and not (root / "packages").exists()


def test_missing_or_wrong_profile_manifest_fails_read_only(tmp_path):
    with pytest.raises(OfflineError) as error:
        api().verify_codec_backend(tmp_path / "missing")
    assert error.value.code == "audio_backend_unavailable" and error.value.blocked
    backend = tmp_path / "invalid"
    backend.mkdir()
    manifest = backend / "backend.json"
    manifest.write_text('{"profile":"some-other-backend"}')
    before = manifest.read_bytes()
    with pytest.raises(OfflineError):
        api().verify_codec_backend(backend)
    assert manifest.read_bytes() == before


def test_backend_preparation_cannot_select_an_executable_from_untrusted_metadata(tmp_path):
    fake = tmp_path / "python.exe"
    fake.write_bytes(b"authored non-executable placeholder")
    root = tmp_path / "runtime"
    with pytest.raises(OfflineError) as error:
        api().provision_codec_backend(root, fake)
    assert error.value.code == "audio_python_unavailable" and error.value.blocked
    assert not root.exists()
