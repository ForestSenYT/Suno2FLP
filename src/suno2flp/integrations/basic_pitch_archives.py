"""Bounded regular archive members; no setup, extraction hooks or path interpretation."""

import hashlib
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from suno2flp.core.offline_files import guarded_path


@dataclass(frozen=True)
class ArchiveMember:
    source_name: str
    size_bytes: int
    sha256: str


def _digest(stream: IO[bytes]) -> str:
    digest = hashlib.sha256()
    while block := stream.read(1024**2):
        digest.update(block)
    return digest.hexdigest()


def _name(name: str, *, inert: bool = False) -> str:
    parts = name.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
    }
    if any(
        not part
        or part in (".", "..")
        or part.endswith((".", " "))
        or any(c in part for c in '\\:*?"<>|')
        or part.split(".")[0].upper() in reserved
        for part in parts
    ) or (not inert and name.lower().endswith((".pth", ".pyc"))):
        raise ValueError("Unsafe archive member")
    return name


def archive_members(
    path: Path,
    *,
    source_inventory: list[str] | None = None,
    omitted_members: dict[str, str] | None = None,
    max_expanded: int = 1024**3,
) -> dict[str, ArchiveMember]:
    result: dict[str, ArchiveMember] = {}
    seen: set[str] = set()
    expanded = 0
    omitted = omitted_members or {}
    found_omitted: set[str] = set()

    def add(name: str, size: int, digest: str) -> None:
        nonlocal expanded
        _name(name, inert=name in omitted)
        if name.casefold() in seen:
            raise ValueError("Case-insensitive duplicate archive member")
        expanded += size
        if size > 128 * 1024**2 or expanded > max_expanded or len(seen) >= 20_000:
            raise ValueError("Archive expansion exceeds budget")
        seen.add(name.casefold())
        if name in omitted:
            if not name.lower().endswith((".pth", ".pyc")) or digest != omitted[name]:
                raise ValueError("Pinned omitted member disagrees with the recipe")
            found_omitted.add(name)
            return
        result[name] = ArchiveMember(name, size, digest)

    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.orig_filename != entry.filename:
                    raise ValueError("Normalized archive member is ambiguous")
                _name(entry.filename.rstrip("/"), inert=entry.filename in omitted)
                kind = stat.S_IFMT(entry.external_attr >> 16)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("Linked or special archive member")
                if entry.is_dir():
                    continue
                if entry.file_size > min(max_expanded, 128 * 1024**2):
                    raise ValueError("Archive member exceeds budget")
                with archive.open(entry) as stream:
                    digest = _digest(stream)
                add(entry.filename, entry.file_size, digest)
    else:
        if source_inventory is None:
            raise ValueError("Source archive requires a fixed inventory")
        with tarfile.open(path, "r:gz") as source_archive:
            for tar_entry in source_archive.getmembers():
                _name(tar_entry.name.rstrip("/"))
                if tar_entry.isdir():
                    continue
                if not tar_entry.isfile():
                    raise ValueError("Linked or special archive member")
                if tar_entry.size > min(max_expanded, 128 * 1024**2):
                    raise ValueError("Archive member exceeds budget")
                tar_stream = source_archive.extractfile(tar_entry)
                assert tar_stream is not None
                with tar_stream:
                    digest = _digest(tar_stream)
                add(tar_entry.name, tar_entry.size, digest)
        if set(result) != set(source_inventory):
            raise ValueError("Source archive differs from fixed inventory")
    if found_omitted != set(omitted):
        raise ValueError("Pinned omitted member is missing")
    return result


def install_members(
    path: Path, destination: Path, members: dict[str, ArchiveMember]
) -> dict[str, str]:
    root = guarded_path(destination)
    result: dict[str, str] = {}
    archive = zipfile.ZipFile(path) if path.suffix == ".whl" else tarfile.open(path, "r:gz")
    with archive:
        for name, member in members.items():
            target = guarded_path(root / _name(name))
            if not target.is_relative_to(root):
                raise ValueError("Archive target escapes output")
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = (
                archive.open(member.source_name)
                if isinstance(archive, zipfile.ZipFile)
                else archive.extractfile(member.source_name)
            )
            assert stream is not None
            digest = hashlib.sha256()
            size = 0
            with stream, target.open("xb") as output:
                while block := stream.read(1024**2):
                    size += len(block)
                    if size > member.size_bytes:
                        raise ValueError("Archive member changed during installation")
                    digest.update(block)
                    output.write(block)
            if size != member.size_bytes or digest.hexdigest() != member.sha256:
                raise ValueError("Archive member changed during installation")
            result[name] = member.sha256
    return result
