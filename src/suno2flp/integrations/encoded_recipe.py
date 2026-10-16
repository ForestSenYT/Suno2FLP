"""Current recipe identities, exact worker arguments and exclusive attempt diagnostics."""

import json
import os
from pathlib import Path
from typing import Any

from suno2flp.core.encoded_audio import EncodedAudioInventory
from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input, guarded_path
from suno2flp.core.offline_models import FileIdentity


def encoded_adapters() -> list[FileIdentity]:
    package = Path(__file__).resolve().parent.parent
    names = (
        "core/encoded_decode.py",
        "core/encoded_audio.py",
        "core/audio_decode.py",
        "core/offline_files.py",
        "core/performance.py",
        "importer/encoded_audio.py",
        "importer/flac_frames.py",
        "importer/mp3_frames.py",
        "importer/encoded_checksums.py",
        "pipeline/encoded_decode.py",
        "validator/encoded_decode.py",
        "integrations/encoded_recipe.py",
    )
    return [capture_stream_input(package / name) for name in names]


def native_audio_arguments(source: EncodedAudioInventory, pcm: Path) -> list[str]:
    return [
        str(source.source.path),
        str(pcm),
        source.codec,
        str(source.frames),
        str(source.sample_rate),
        str(source.channels),
        str(source.flac.bits_per_sample if source.flac else 0),
        source.flac.pcm_md5 if source.flac else "-",
    ]


def write_encoded_json(
    path: Path, value: dict[str, Any], *, max_bytes: int = 1024**2
) -> FileIdentity:
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    if len(raw) > max_bytes:
        raise OfflineError("audio_limits_exceeded", "Complete audio evidence exceeds report budget")
    target = guarded_path(path)
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return capture_stream_input(target)


def save_encoded_failure(root: Path, error: Exception, phase: str) -> None:
    target = root / "failure.json"
    if not root.is_dir() or target.exists():
        return
    write_encoded_json(
        target,
        {
            "schema_version": 1,
            "profile": "compressed-decode-failure-v1",
            "phase": phase,
            "error_code": error.code if isinstance(error, OfflineError) else "audio_io_failed",
            "error_message": str(error),
            "stdout_hex": getattr(error, "stdout", b"").hex(),
            "stderr_hex": getattr(error, "stderr", b"").hex(),
            "output_capture_truncated": getattr(error, "code", None) == "audio_worker_output_limit",
            "candidate_eligible": False,
        },
        max_bytes=8 * 1024**2,
    )
