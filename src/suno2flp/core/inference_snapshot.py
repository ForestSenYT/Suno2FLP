"""Invocation-local immutable file guards, without numeric or inference authority.

Callers establish complete numeric relationships first. Later rechecks prove those
exact bytes remain current, including complete model payload membership. This is
not a serialized receipt, cross-invocation cache or model qualification.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import guarded_path, verify_inputs
from suno2flp.core.offline_models import FileIdentity

FileStamp = tuple[Path, str, int, int]


def _stamp(identity: FileIdentity) -> FileStamp:
    return identity.path, identity.sha256, identity.size_bytes, identity.mtime_ns


def _identity(stamp: FileStamp) -> FileIdentity:
    return FileIdentity(path=stamp[0], sha256=stamp[1], size_bytes=stamp[2], mtime_ns=stamp[3])


def _cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise DecodeCancelled()


@dataclass(frozen=True, slots=True)
class InferenceSnapshot:
    _files: tuple[FileStamp, ...]
    _payloads: tuple[tuple[Path, tuple[FileStamp, ...]], ...]

    @classmethod
    def capture(
        cls,
        files: list[FileIdentity],
        payloads: list[tuple[Path, list[FileIdentity]]],
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> "InferenceSnapshot":
        _cancel(should_cancel)
        unique: dict[Path, FileStamp] = {}
        roots: dict[Path, tuple[FileStamp, ...]] = {}
        for root, entries in payloads:
            root = guarded_path(root)
            expected = tuple(sorted((_stamp(i) for i in entries), key=lambda item: item[0]))
            if any(not item[0].is_relative_to(root) for item in expected):
                raise ValueError("Payload declarations must remain inside their own root")
            if root in roots and roots[root] != expected:
                raise ValueError("Conflicting complete payload declarations")
            roots[root] = expected
        for stamp in [*map(_stamp, files), *[i for entries in roots.values() for i in entries]]:
            if stamp[0] in unique and unique[stamp[0]] != stamp:
                raise ValueError("Conflicting expected file identities")
            unique[stamp[0]] = stamp
        result = cls(tuple(unique.values()), tuple(roots.items()))
        result.recheck(should_cancel=should_cancel)
        return result

    def recheck(self, *, should_cancel: Callable[[], bool] | None = None) -> None:
        _cancel(should_cancel)
        payload_paths: set[Path] = set()
        for root, expected in self._payloads:
            current = capture_file_tree(root, max_bytes=3 * 1024**3, should_cancel=should_cancel)
            if tuple(_stamp(i) for i in current) != expected:
                raise ValueError("Current complete inference payload changed")
            payload_paths.update(i.path for i in current)
        verify_inputs([_identity(stamp) for stamp in self._files if stamp[0] not in payload_paths])
        _cancel(should_cancel)
