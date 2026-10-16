"""Read-only container checks and complete current native replay; no candidate rewrites."""

import hashlib
import platform
import struct
import sys
import time
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.audio_decode import PCM_PASS_SECONDS, check_decode_request
from suno2flp.core.encoded_decode import EncodedDecodeReport, EncodedDecodeRequest
from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import (
    capture_input,
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.importer.encoded_audio import inspect_encoded_audio
from suno2flp.integrations.codec_backend import run_codec_worker, verify_codec_backend
from suno2flp.integrations.encoded_recipe import encoded_adapters, native_audio_arguments


def verify_encoded_decode(
    report_path: Path, *, should_cancel: Callable[[], bool] | None = None
) -> EncodedDecodeReport:
    deadline = time.monotonic() + PCM_PASS_SECONDS
    check_decode_request(should_cancel, deadline)
    path = guarded_path(report_path)
    if path.stat().st_size > 1024**2:
        raise OfflineError("audio_decode_evidence_invalid", "Expected a bounded complete report")
    identity, raw = capture_input(path)
    report = EncodedDecodeReport.model_validate(load_unique_json(raw))
    root = path.parent
    if (
        path.name != "decode.json"
        or report.pcm.path != root / "decoded.wav"
        or report.request.path != root / "attempt.json"
        or report.inventory.source.path.is_relative_to(root)
        or any((p / "backend.json").exists() for p in (root, *root.parents))
    ):
        raise OfflineError(
            "audio_decode_evidence_invalid", "Inconsistent candidate/report locations"
        )
    verify_inputs([report.pcm, report.request, report.inventory.source, report.backend_manifest])
    if report.request.size_bytes > 1024**2:
        raise OfflineError("audio_decode_evidence_invalid", "Attempt request exceeds profile")
    _, request_raw = capture_input(report.request.path)
    request = EncodedDecodeRequest.model_validate(load_unique_json(request_raw))
    if (
        request.source != report.inventory.source
        or request.output_directory != root
        or request.decoder_directory != report.backend.root
        or request.adapters != encoded_adapters()
        or request.app_python != capture_stream_input(Path(sys.executable).resolve())
        or request.python_version != platform.python_version()
    ):
        raise OfflineError(
            "audio_decode_evidence_invalid", "Attempt recipe/source/application runtime changed"
        )
    if report.inventory != inspect_encoded_audio(
        report.inventory.source.path, should_cancel=should_cancel
    ) or report.backend != verify_codec_backend(report.backend.root):
        raise OfflineError(
            "audio_decode_evidence_invalid", "Current source/runtime disagrees with candidate"
        )
    source = report.inventory
    with report.pcm.path.open("rb") as stream:
        header = stream.read(58)
        if (
            len(header) != 58
            or header[:4] != b"RIFF"
            or header[8:16] != b"WAVEfmt "
            or struct.unpack_from("<I", header, 4)[0] != report.pcm.size_bytes - 8
            or struct.unpack_from("<IHHIIHHH", header, 16)
            != (
                18,
                3,
                source.channels,
                source.sample_rate,
                source.sample_rate * source.channels * 8,
                source.channels * 8,
                64,
                0,
            )
            or header[38:42] != b"fact"
            or struct.unpack_from("<II", header, 42) != (4, source.frames)
            or header[50:54] != b"data"
            or struct.unpack_from("<I", header, 54)[0] != source.frames * source.channels * 8
        ):
            raise OfflineError(
                "audio_decode_evidence_invalid", "Invalid complete float64 PCM header"
            )
        digest = hashlib.sha256()
        while block := stream.read(1024**2):
            check_decode_request(should_cancel, deadline)
            digest.update(block)
        if digest.hexdigest() != report.native.samples_sha256:
            raise OfflineError(
                "audio_decode_evidence_invalid", "PCM samples hash disagrees with candidate"
            )
    replay = run_codec_worker(
        report.backend.root,
        "verify",
        native_audio_arguments(source, report.pcm.path),
        should_cancel=should_cancel,
    )
    if report.native.model_dump(exclude={"mode"}) != replay.model_dump(exclude={"mode"}):
        raise OfflineError(
            "audio_decode_evidence_invalid", "Current codec replay disagrees with source candidate"
        )
    verify_inputs(
        [
            identity,
            report.pcm,
            report.request,
            source.source,
            report.backend_manifest,
            *request.adapters,
        ]
    )
    check_decode_request(should_cancel, deadline)
    return report
