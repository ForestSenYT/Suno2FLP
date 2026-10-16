"""Bounded immutable annotation snapshots; no authority inferred from filenames."""

import hashlib
import stat
from pathlib import Path

from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import ANNOTATION_BYTES, AnnotationSnapshot, NoteAnnotation
from suno2flp.core.offline_files import guarded_path, load_unique_json
from suno2flp.core.offline_models import FileIdentity


def bounded_snapshot(path: Path, maximum: int) -> tuple[FileIdentity, bytes]:
    resolved = guarded_path(path)
    before = resolved.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        raise OfflineError("note_score_input_invalid", "Expected a bounded regular evidence file")
    with resolved.open("rb") as stream:
        raw = stream.read(maximum + 1)
    after = resolved.stat()
    if (
        len(raw) > maximum
        or len(raw) != after.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise OfflineError("note_score_input_changed", "Evidence changed during bounded read")
    return FileIdentity(
        path=resolved,
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        mtime_ns=after.st_mtime_ns,
    ), raw


def read_note_annotation(path: Path) -> AnnotationSnapshot:
    identity, raw = bounded_snapshot(path, ANNOTATION_BYTES)
    annotation = NoteAnnotation.model_validate(load_unique_json(raw))
    return AnnotationSnapshot(file=identity, annotation=annotation)
