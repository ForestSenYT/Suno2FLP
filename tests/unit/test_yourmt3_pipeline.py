"""Read-only prerequisite failures must preserve old outputs and source files."""

import importlib

import pytest


def api():
    assert importlib.util.find_spec("suno2flp.pipeline.yourmt3"), "Missing source-bound workflow"
    return importlib.import_module("suno2flp.pipeline.yourmt3")


def test_old_output_refusal_precedes_any_missing_source_access(tmp_path):
    output = tmp_path / "old"
    output.mkdir()
    keep = output / "keep.txt"
    keep.write_bytes(b"old immutable experiment")
    with pytest.raises(FileExistsError):
        api().transcribe_yourmt3(
            tmp_path / "missing.json", tmp_path / "missing-backend", output, []
        )
    assert keep.read_bytes() == b"old immutable experiment"
    assert list(output.iterdir()) == [keep]


def test_invalid_decode_never_starts_model_or_creates_candidate(tmp_path):
    decode = tmp_path / "decode.json"
    decode.write_bytes(b'{"unsupported":true}')
    output = tmp_path / "new"
    with pytest.raises(ValueError):
        api().transcribe_yourmt3(decode, tmp_path / "missing-backend", output, [])
    assert decode.read_bytes() == b'{"unsupported":true}'
    assert not output.exists()
