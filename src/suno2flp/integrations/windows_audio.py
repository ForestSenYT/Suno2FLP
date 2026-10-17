"""Bounded read-only Windows discovery, with exclusive point-in-time evidence."""

import json
import platform
import sys
import sysconfig
from collections.abc import Callable
from pathlib import Path

import pydantic

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.codec_backend import CodecCancelled, CodecProcessError
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    load_unique_json,
    new_report,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.windows_audio import (
    WindowsAudioInspection,
    WindowsAudioNative,
    WindowsAudioRequest,
    assess_windows_audio,
)
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.codec_process import run_bounded_process


def _supported_platform() -> bool:
    return sys.platform == "win32" and sysconfig.get_platform() == "win-amd64"


def audio_recipe() -> ScoringRecipe:
    package = Path(__file__).parent.parent
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[
            capture_stream_input(package / name)
            for name in (
                "core/windows_audio.py",
                "core/models.py",
                "core/note_scoring.py",
                "core/offline_models.py",
                "core/offline_files.py",
                "core/report_publication.py",
                "core/audio_decode.py",
                "core/audio_input.py",
                "core/codec_backend.py",
                "integrations/windows_audio.py",
                "integrations/windows_audio_worker.py",
                "integrations/codec_process.py",
                "integrations/basic_pitch_backend.py",
            )
        ],
    )


def inspect_windows_audio(
    output: Path, *, should_cancel: Callable[[], bool] | None = None
) -> WindowsAudioInspection:
    def cancelled() -> None:
        if should_cancel is not None and should_cancel():
            raise DecodeCancelled()

    cancelled()
    if not _supported_platform():
        raise ValueError("Windows x64 Core Audio discovery is unavailable on this platform")
    if platform.python_version() not in ("3.11.16", "3.14.7"):
        raise ValueError("Use the inspected application Python3.11.16 or3.14.7")
    recipe = audio_recipe()
    inputs = [recipe.python_executable, *recipe.files]
    target = new_model_directory(output, [item.path for item in inputs])
    stdout = stderr = b""
    streams_written = False
    worker = next(item.path for item in recipe.files if item.path.name == "windows_audio_worker.py")
    request = WindowsAudioRequest(
        recipe=recipe,
        arguments=[str(recipe.python_executable.path), "-I", "-S", "-B", "-X", "utf8", str(worker)],
        timeout_seconds=15,
        max_bytes=4 * 1024**2,
    )
    request_identity: FileIdentity | None = None

    def save_streams() -> None:
        nonlocal streams_written
        for name, raw in (("stdout.bin", stdout), ("stderr.bin", stderr)):
            with (target / name).open("xb") as stream:
                stream.write(raw)
        streams_written = True

    try:
        new_report(
            target / "request.json",
            request.model_dump_json(indent=2),
            [item.path for item in inputs],
        )
        request_identity = capture_stream_input(target / "request.json")
        stdout, stderr = run_bounded_process(
            list(request.arguments),
            should_cancel=should_cancel,
            timeout=request.timeout_seconds,
            max_bytes=request.max_bytes,
        )
        save_streams()
        native = WindowsAudioNative.model_validate(load_unique_json(stdout))
        result = WindowsAudioInspection(
            root=target,
            native=native,
            request=request_identity,
            request_snapshot=request,
            stdout=capture_stream_input(target / "stdout.bin"),
            stderr=capture_stream_input(target / "stderr.bin"),
            assessment=assess_windows_audio(native.facts),
        )

        def verify() -> None:
            cancelled()
            verify_inputs(
                [*inputs, *native.libraries, result.request, result.stdout, result.stderr]
            )
            if (
                WindowsAudioRequest.model_validate(
                    load_unique_json((target / "request.json").read_bytes())
                )
                != request
            ):
                raise ValueError("Native request snapshot changed")
            raw = (target / "stdout.bin").read_bytes()
            if WindowsAudioNative.model_validate(load_unique_json(raw)) != native:
                raise ValueError("Native observation bytes changed")
            if WindowsAudioInspection.model_validate(result.model_dump(mode="json")) != result:
                raise ValueError("Inspection changed before publication")
            cancelled()

        publish_verified_report(
            target / "inspection.json",
            result.model_dump_json(indent=2),
            [item.path for item in inputs],
            verify,
        )
        return result
    except (OSError, ValueError, Suno2FLPError, DecodeCancelled) as error:
        if isinstance(error, (CodecProcessError, CodecCancelled)):
            stdout, stderr = error.stdout, error.stderr
        if not streams_written:
            save_streams()
        new_report(
            target / "failure.json",
            json.dumps(
                {
                    "status": "cancelled" if isinstance(error, DecodeCancelled) else "failed",
                    "error": str(error),
                    "host_compatibility": "unverified",
                    "request_snapshot": request.model_dump(mode="json"),
                    "request_identity": request_identity.model_dump(mode="json")
                    if request_identity
                    else None,
                    "stdout": capture_stream_input(target / "stdout.bin").model_dump(mode="json"),
                    "stderr": capture_stream_input(target / "stderr.bin").model_dump(mode="json"),
                },
                indent=2,
            ),
            [item.path for item in inputs],
        )
        raise
