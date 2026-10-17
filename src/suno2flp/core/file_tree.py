"""Bounded, current regular-file tree identities with directory-change detection.

Walk each guarded directory once instead of resolving every ancestor for every file.
This is integrity checking of trusted local artifacts, not an OS security sandbox.
"""

import hashlib
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.offline_files import guarded_path
from suno2flp.core.offline_models import FileIdentity


def _signature(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _regular(info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Linked/reparse payload entries are not accepted")


def capture_file_tree(
    root: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
    max_files: int = 20_000,
    max_bytes: int = 1024**3,
    timeout: float = 300,
) -> list[FileIdentity]:
    root = guarded_path(root)
    if max_files <= 0 or max_bytes <= 0 or timeout <= 0 or not root.is_dir():
        raise ValueError("Tree budget/root must be valid")
    deadline = time.monotonic() + timeout
    result: list[FileIdentity] = []
    length = 0
    directories: list[tuple[Path, os.stat_result, tuple[str, ...]]] = []

    def check() -> None:
        if should_cancel is not None and should_cancel():
            raise DecodeCancelled()
        if time.monotonic() > deadline:
            raise ValueError("Tree pass exceeded its time budget")

    def visit(directory: Path) -> None:
        nonlocal length
        check()
        directory = guarded_path(directory)
        before = directory.stat(follow_symlinks=False)
        _regular(before)
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda e: e.name)
        directories.append((directory, before, tuple(entry.name for entry in entries)))
        for entry in entries:
            check()
            path = directory / entry.name
            # Windows DirEntry's cached stat may have zero dev/ino; obtain real IDs.
            info = path.stat(follow_symlinks=False)
            _regular(info)
            if stat.S_ISDIR(info.st_mode):
                visit(path)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Payload tree requires regular files")
            length += info.st_size
            if len(result) >= max_files or length > max_bytes:
                raise ValueError("Payload tree exceeds budget")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                if _signature(info) != _signature(opened):
                    raise ValueError("Payload changed before reading")
                while block := stream.read(1024**2):
                    check()
                    digest.update(block)
                after = os.fstat(stream.fileno())
            current = path.stat(follow_symlinks=False)
            _regular(current)
            if _signature(info) != _signature(after) or _signature(info) != _signature(current):
                raise ValueError("Payload changed during reading")
            result.append(
                FileIdentity(
                    path=path,
                    sha256=digest.hexdigest(),
                    size_bytes=info.st_size,
                    mtime_ns=info.st_mtime_ns,
                )
            )

    visit(root)
    for directory, before, names in directories:
        check()
        directory = guarded_path(directory)
        current_names = []
        with os.scandir(directory) as scan:
            for entry in scan:
                check()
                current_names.append(entry.name)
                if len(current_names) > len(names):
                    raise ValueError("Payload directory membership changed during tree capture")
        current = directory.stat(follow_symlinks=False)
        _regular(current)
        if tuple(sorted(current_names)) != names or _signature(before) != _signature(current):
            raise ValueError("Payload directory changed during tree capture")
    if guarded_path(root) != root:
        raise ValueError("Payload root changed during tree capture")
    return sorted(result, key=lambda identity: identity.path)
