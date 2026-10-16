"""Exclusive file primitives and Windows-only no-replace bundle publication."""

import hashlib
import os
import re
import stat
from pathlib import Path

from suno2flp.core.errors import FlpWriteError
from suno2flp.core.writer_models import WriterInputFile


def reject_aliases(path: Path) -> Path:
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise FlpWriteError("writer_path_unsafe", "Use absolute paths without parent traversal")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    for part in path.parts:
        if part == path.anchor:
            continue
        if ":" in part or part.endswith((".", " ")) or part.split(".")[0].upper() in reserved:
            raise FlpWriteError(
                "writer_path_unsafe",
                "Device names, alternate streams and ambiguous path components are forbidden",
            )
    for item in [path, *path.parents]:
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise FlpWriteError(
                "writer_path_unsafe", "Links/junctions/reparse path components are forbidden"
            )
    return path.resolve()


def capture_file(path: Path, kind: str) -> tuple[WriterInputFile, bytes]:
    resolved = reject_aliases(path)
    before = resolved.stat()
    if not stat.S_ISREG(before.st_mode):
        raise FlpWriteError("writer_input_invalid", "Expected a regular source file")
    raw = resolved.read_bytes()
    after = resolved.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise FlpWriteError("writer_input_changed", f"Input changed while reading: {resolved}")
    return WriterInputFile.model_validate(
        {
            "kind": kind,
            "path": resolved,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "mtime_ns": after.st_mtime_ns,
        }
    ), raw


def verify_input_files(files: list[WriterInputFile]) -> None:
    for previous in files:
        current, _ = capture_file(previous.path, previous.kind)
        if current != previous:
            raise FlpWriteError("writer_input_changed", f"Input changed: {previous.path}")


def guard_output(
    destination: Path, protected_trees: list[Path], protected_files: list[Path]
) -> Path:
    destination = reject_aliases(destination.absolute())
    if (
        destination.exists()
        or not destination.parent.is_dir()
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", destination.name)
        or destination.suffix.lower() in {".flp", ".mid", ".midi", ".json", ".yaml"}
    ):
        raise FlpWriteError(
            "writer_output_unsafe",
            "Output must be a new bundle directory with a portable name and existing parent",
        )
    for tree in protected_trees:
        if destination.is_relative_to(tree.resolve()):
            raise FlpWriteError(
                "writer_output_unsafe", "Output must be outside source/template/backend trees"
            )
    for source in protected_files:
        if source.resolve().is_relative_to(destination):
            raise FlpWriteError("writer_output_unsafe", "Output cannot contain an input")
    return destination


def require_windows() -> None:
    if os.name != "nt":
        raise FlpWriteError(
            "writer_publish_unavailable",
            "No-replace directory publication is supported only on Windows",
        )


def write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def publish_bundle(stage: Path, destination: Path) -> None:
    require_windows()
    # Windows os.rename always refuses an existing destination; never use replace/move.
    os.rename(stage, destination)
