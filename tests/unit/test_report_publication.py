"""Actual exclusive files and adversarial late callbacks, without native dependencies."""

import importlib
from pathlib import Path

import pytest

from suno2flp.core.errors import Suno2FLPError


def publisher():
    return importlib.import_module("suno2flp.core.report_publication").publish_verified_report


def test_final_name_appears_only_after_verified_serialization(tmp_path: Path):
    target = tmp_path / "report.json"
    pending = tmp_path / "report.pending.json"
    content = '{"message":"中"}\n'

    def verify():
        assert pending.read_text(encoding="utf-8") == content
        assert not target.exists()

    publisher()(target, content, [], verify)
    assert target.read_bytes() == b'{"message":"\xe4\xb8\xad"}\n'
    assert pending.read_bytes() == target.read_bytes()


def test_rejected_verification_preserves_provisional_evidence(tmp_path: Path):
    def verify():
        raise RuntimeError("late witness rejection")

    with pytest.raises(RuntimeError, match="late witness rejection"):
        publisher()(tmp_path / "report.json", "{}", [], verify)
    assert not (tmp_path / "report.json").exists()
    assert (tmp_path / "report.pending.json").read_bytes() == b"{}"


def test_provisional_replacement_cannot_be_published(tmp_path: Path):
    def verify():
        (tmp_path / "report.pending.json").write_bytes(b"different evidence")

    with pytest.raises((ValueError, Suno2FLPError)):
        publisher()(tmp_path / "report.json", "{}", [], verify)
    assert not (tmp_path / "report.json").exists()


def test_competing_final_report_is_never_overwritten(tmp_path: Path):
    def verify():
        (tmp_path / "report.json").write_bytes(b"independent output")

    with pytest.raises(FileExistsError):
        publisher()(tmp_path / "report.json", "{}", [], verify)
    assert (tmp_path / "report.json").read_bytes() == b"independent output"
    assert (tmp_path / "report.pending.json").read_bytes() == b"{}"


@pytest.mark.parametrize("existing", ["report.json", "report.pending.json"])
def test_existing_final_or_provisional_output_is_preserved(tmp_path: Path, existing: str):
    (tmp_path / existing).write_bytes(b"existing record")
    calls = []
    with pytest.raises((OSError, ValueError, Suno2FLPError)):
        publisher()(tmp_path / "report.json", "{}", [], lambda: calls.append("called"))
    assert calls == []
    assert (tmp_path / existing).read_bytes() == b"existing record"


def test_unsupported_publication_has_no_nonexclusive_fallback(tmp_path: Path, monkeypatch):
    def unsupported(*args, **kwargs):
        raise OSError("hard links unavailable")

    monkeypatch.setattr("os.link", unsupported)
    with pytest.raises(OSError, match="hard links unavailable"):
        publisher()(tmp_path / "report.json", "{}", [], lambda: None)
    assert not (tmp_path / "report.json").exists()
    assert (tmp_path / "report.pending.json").read_bytes() == b"{}"


@pytest.mark.parametrize("kind", ["extension", "parent", "protected", "backend"])
def test_unsafe_destination_fails_before_serialization(tmp_path: Path, kind: str):
    target = tmp_path / "report.json"
    protected = []
    if kind == "extension":
        target = tmp_path / "report.txt"
    elif kind == "parent":
        target = tmp_path / "missing/report.json"
    elif kind == "protected":
        protected = [target]
    else:
        (tmp_path / "backend.json").write_bytes(b"backend record")
    with pytest.raises((OSError, ValueError, Suno2FLPError)):
        publisher()(target, "{}", protected, lambda: None)
    assert not (target.parent / f"{target.stem}.pending.json").exists()


def test_oversized_complete_report_is_rejected_without_truncation(tmp_path: Path):
    with pytest.raises(ValueError):
        publisher()(tmp_path / "report.json", " " * (16 * 1024**2 + 1), [], lambda: None)
    assert list(tmp_path.iterdir()) == []
