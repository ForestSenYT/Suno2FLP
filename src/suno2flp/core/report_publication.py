"""Publish a completion name only after serialized bytes and current evidence pass."""

import os
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.offline_files import capture_input, guarded_path, new_report, verify_inputs


def publish_verified_report(
    path: Path, content: str, protected: list[Path], verify: Callable[[], None]
) -> None:
    destination = guarded_path(path)
    if (
        destination.exists()
        or destination.suffix.lower() != ".json"
        or any(destination == guarded_path(source) for source in protected)
    ):
        raise ValueError("Use a new JSON completion path distinct from protected inputs")
    serialized = content.encode("utf-8")
    if len(serialized) > 16 * 1024**2:
        raise ValueError("Complete report exceeds16MiB; no truncation is allowed")
    pending = destination.with_name(f"{destination.stem}.pending.json")
    new_report(pending, content, protected)
    identity, actual = capture_input(pending)
    if actual != serialized:
        raise ValueError("Provisional report changed during serialization")
    verify()
    verify_inputs([identity])
    # Exclusive atomic commit point. Keep both names immutable after success.
    # No rejecting operation follows a successfully published completion marker.
    os.link(guarded_path(pending), guarded_path(destination))
