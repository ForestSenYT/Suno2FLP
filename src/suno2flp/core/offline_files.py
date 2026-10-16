"""Trusted-local-file snapshots and exclusive report creation; no process launch."""

import hashlib
import json
import stat
from pathlib import Path
from typing import Any

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_models import FileIdentity


def guarded_path(path: Path) -> Path:
    absolute = path.absolute()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    }
    for part in absolute.parts:
        if part == absolute.anchor:
            continue
        if (
            part in {".", ".."}
            or part.endswith((".", " "))
            or any(char in part for char in ':*?"<>|')
            or part.split(".")[0].upper() in reserved
        ):
            raise OfflineError(
                "offline_path_unsafe", "Use unambiguous paths without parent traversal"
            )
    for current in (absolute, *absolute.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise OfflineError("offline_path_unsafe", "Linked/reparse paths are not accepted")
    return absolute.resolve()


def capture_input(path: Path) -> tuple[FileIdentity, bytes]:
    resolved = guarded_path(path)
    before = resolved.stat()
    if not stat.S_ISREG(before.st_mode):
        raise OfflineError("offline_input_invalid", "Expected a regular file")
    raw = resolved.read_bytes()
    after = resolved.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(raw) != after.st_size:
        raise OfflineError("offline_input_changed", f"Input changed while reading: {resolved}")
    return FileIdentity(
        path=resolved,
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        mtime_ns=after.st_mtime_ns,
    ), raw


def verify_inputs(identities: list[FileIdentity]) -> None:
    for expected in identities:
        actual, _ = capture_input(expected.path)
        if actual != expected:
            raise OfflineError("offline_input_changed", f"Input changed: {expected.path}")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_unique_json(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique)


def new_report(path: Path, content: str, protected: list[Path]) -> None:
    destination = guarded_path(path)
    if (
        destination.exists()
        or destination.suffix.lower() != ".json"
        or not destination.parent.is_dir()
        or any(destination == guarded_path(source) for source in protected)
        or any((parent / "backend.json").exists() for parent in destination.parents)
    ):
        raise OfflineError(
            "offline_output_unsafe", "Use a new JSON report distinct from all inputs"
        )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
