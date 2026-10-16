"""Exclusive compressed decode candidate creation; callers must independently replay it."""

import platform
import sys
import time
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.audio_decode import PCM_PASS_SECONDS, check_decode_request
from suno2flp.core.audio_input import AudioPreflightError
from suno2flp.core.encoded_decode import EncodedDecodeReport, EncodedDecodeRequest
from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input, guarded_path, verify_inputs
from suno2flp.importer.encoded_audio import inspect_encoded_audio
from suno2flp.integrations.codec_backend import run_codec_worker, verify_codec_backend
from suno2flp.integrations.encoded_recipe import (
    encoded_adapters,
    native_audio_arguments,
    save_encoded_failure,
    write_encoded_json,
)


def decode_encoded_audio(
    source: Path,
    output_directory: Path,
    backend: Path | None,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> EncodedDecodeReport:
    deadline = time.monotonic() + PCM_PASS_SECONDS
    check_decode_request(should_cancel, deadline)
    inventory = inspect_encoded_audio(source, should_cancel=should_cancel)
    root = guarded_path(output_directory)
    if (
        root.exists()
        or not root.parent.is_dir()
        or inventory.source.path.is_relative_to(root)
        or any((p / "backend.json").exists() for p in (root, *root.parents))
    ):
        raise OfflineError(
            "audio_decode_output_unsafe", "Use a new directory outside all inputs/backends"
        )
    requested = guarded_path(backend) if backend is not None else None
    adapters = encoded_adapters()
    request = EncodedDecodeRequest(
        source=inventory.source,
        output_directory=root,
        decoder_directory=requested,
        app_python=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        adapters=adapters,
    )
    check_decode_request(should_cancel, deadline)
    root.mkdir()
    request_identity = write_encoded_json(root / "attempt.json", request.model_dump(mode="json"))
    try:
        if requested is None:
            raise AudioPreflightError(
                "audio_backend_unavailable",
                "Prepare the isolated audio decoder before decoding compressed files",
                blocked=True,
            )
        record = verify_codec_backend(requested)
        backend_identity = capture_stream_input(record.root / "backend.json")
        check_decode_request(should_cancel, deadline)
        pcm = root / "decoded.wav"
        native = run_codec_worker(
            record.root,
            "decode",
            native_audio_arguments(inventory, pcm),
            should_cancel=should_cancel,
        )
        verify_inputs([inventory.source, request_identity, backend_identity, *adapters])
        report = EncodedDecodeReport(
            inventory=inventory,
            request=request_identity,
            backend_manifest=backend_identity,
            backend=record,
            pcm=capture_stream_input(pcm),
            native=native,
            lossless_oracle="streaminfo-md5" if inventory.codec == "FLAC" else "unavailable-lossy",
        )
        write_encoded_json(root / "decode.json", report.model_dump(mode="json"))
        check_decode_request(should_cancel, deadline)
        return report
    except (OfflineError, OSError, ValueError) as error:
        save_encoded_failure(root, error, "decode")
        raise
