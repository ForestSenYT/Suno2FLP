"""No archive extraction APIs, source builds, links or ambiguous Windows members."""

import hashlib
import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from suno2flp.integrations.basic_pitch_archives import archive_members, install_members


def wheel(path: Path, entries: list[tuple[str, bytes, int]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data, mode in entries:
            entry = zipfile.ZipInfo(name)
            entry.external_attr = mode << 16
            archive.writestr(entry, data)


@pytest.mark.parametrize(
    "name", ["../evil.py", "/evil.py", "a\\b.py", "a/../b", "a:b", "a./b", "CON/x", "a//b", "a.pth"]
)
def test_ambiguous_or_automatic_import_members_fail(tmp_path: Path, name: str) -> None:
    path = tmp_path / "fake.whl"
    wheel(path, [(name, b"data", stat.S_IFREG)])
    # ZipInfo normalizes Windows separators when authoring; emulate untrusted bytes.
    if "\\" in name:
        path.write_bytes(path.read_bytes().replace(name.replace("\\", "/").encode(), name.encode()))
    with pytest.raises(ValueError):
        archive_members(path)


def test_links_case_duplicates_and_expansion_fail(tmp_path: Path) -> None:
    path = tmp_path / "link.whl"
    wheel(path, [("linked", b"target", stat.S_IFLNK)])
    with pytest.raises(ValueError, match="member"):
        archive_members(path)
    path = tmp_path / "duplicate.whl"
    wheel(path, [("A.py", b"1", stat.S_IFREG), ("a.py", b"2", stat.S_IFREG)])
    with pytest.raises(ValueError, match="duplicate"):
        archive_members(path)
    path = tmp_path / "large.whl"
    wheel(path, [("a.py", b"12345", stat.S_IFREG)])
    with pytest.raises(ValueError, match="budget"):
        archive_members(path, max_expanded=4)


def test_installation_is_exclusive_and_retains_notices(tmp_path: Path) -> None:
    path = tmp_path / "fake.whl"
    wheel(
        path,
        [
            ("pkg/__init__.py", b"ok", stat.S_IFREG),
            ("pkg.dist-info/LICENSE", b"notice", stat.S_IFREG),
        ],
    )
    destination = tmp_path / "packages"
    destination.mkdir()
    members = archive_members(path)
    installed = install_members(path, destination, members)
    assert set(installed) == {"pkg/__init__.py", "pkg.dist-info/LICENSE"}
    assert (destination / "pkg.dist-info/LICENSE").read_bytes() == b"notice"
    with pytest.raises(FileExistsError):
        install_members(path, destination, members)


def test_only_exact_pinned_inert_members_can_be_omitted(tmp_path: Path) -> None:
    path = tmp_path / "curated.whl"
    wheel(path, [("pkg.py", b"ok", stat.S_IFREG), ("hook.pth", b"import evil", stat.S_IFREG)])
    digest = hashlib.sha256(b"import evil").hexdigest()
    assert set(archive_members(path, omitted_members={"hook.pth": digest})) == {"pkg.py"}
    with pytest.raises(ValueError, match="omitted"):
        archive_members(path, omitted_members={"hook.pth": "0" * 64})


def test_source_archive_requires_exact_inventory_and_regular_files(tmp_path: Path) -> None:
    path = tmp_path / "source.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in ("pkg/setup.py", "pkg/pkg/__init__.py", "pkg/LICENSE"):
            entry = tarfile.TarInfo(name)
            entry.size = 4
            archive.addfile(entry, io.BytesIO(b"data"))
    with pytest.raises(ValueError, match="inventory"):
        archive_members(path, source_inventory=["pkg/pkg/__init__.py", "pkg/LICENSE"])
    members = archive_members(
        path, source_inventory=["pkg/setup.py", "pkg/pkg/__init__.py", "pkg/LICENSE"]
    )
    target = tmp_path / "packages"
    target.mkdir()
    install_members(
        path,
        target,
        {
            "pkg/__init__.py": members["pkg/pkg/__init__.py"],
            "notices/LICENSE": members["pkg/LICENSE"],
        },
    )
    assert not (target / "setup.py").exists()
