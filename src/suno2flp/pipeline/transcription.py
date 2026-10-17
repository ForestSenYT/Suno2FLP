"""Exclusive candidate publication from current independently decoded source audio."""

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import (
    capture_stream_input,
    load_unique_json,
    new_report,
)
from suno2flp.core.transcription import (
    NativeTranscriptionResult,
    RawPredictionArtifact,
    TranscriptionCandidate,
)
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.basic_pitch_backend import (
    call_basic_pitch,
    new_model_directory,
    read_basic_pitch,
)
from suno2flp.validator.transcription import (
    check_cancel,
    transcription_recipe,
    validate_transcription_artifacts,
    verify_transcription_witnesses,
)
from suno2flp.validator.transcription_source import verified_transcription_source


def transcribe_audio(
    decode_report: Path,
    backend: Path,
    output: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> TranscriptionCandidate:
    check_cancel(should_cancel)
    source = verified_transcription_source(decode_report, should_cancel=should_cancel)
    model = read_basic_pitch(backend)
    backend_record = capture_stream_input(model.root / "backend.json")
    recipe = transcription_recipe()
    dependencies = capture_file_tree(model.root / "packages", should_cancel=should_cancel)
    root = new_model_directory(
        output,
        [
            model.root,
            *[i.path for i in source.dependencies],
            source.pcm.path,
            *[i.path for i in model.artifacts],
            *[i.path for i in recipe.files],
        ],
    )
    attempt = root / "native"
    attempt.mkdir()
    call_basic_pitch(
        model,
        attempt,
        {
            "operation": "transcribe",
            "pcm": str(source.pcm.path),
            "frames": source.frames,
            "sample_rate": source.sample_rate,
            "channels": source.channels,
        },
        should_cancel=should_cancel,
    )
    _, raw = bounded_snapshot(attempt / "result.json", 16 * 1024**2)
    result = NativeTranscriptionResult.model_validate(load_unique_json(raw))
    kinds: tuple[Literal["note", "onset", "contour"], ...] = ("note", "onset", "contour")
    report = TranscriptionCandidate(
        decode_report=source.decode_report,
        source_audio=source.source,
        pcm=source.pcm,
        frames=source.frames,
        sample_rate=source.sample_rate,
        channels=source.channels,
        decode_dependencies=source.dependencies,
        decoder_payload_root=source.decoder_payload_root,
        backend_record=backend_record,
        backend=model,
        model_dependencies=dependencies,
        recipe=recipe,
        result=result,
        mono=capture_stream_input(attempt / "mono.f32"),
        predictions=[
            RawPredictionArtifact(
                kind=name,
                windows=result.windows,
                file=capture_stream_input(attempt / f"{name}.f32"),
            )
            for name in kinds
        ],
        bends=capture_stream_input(attempt / "bends.i8"),
        native_result=capture_stream_input(attempt / "result.json"),
        native_request=capture_stream_input(attempt / "request.json"),
        stdout=capture_stream_input(attempt / "stdout.bin"),
        stderr=capture_stream_input(attempt / "stderr.bin"),
    )
    validate_transcription_artifacts(report, should_cancel=should_cancel)
    content = report.model_dump_json(indent=2)
    if len(content.encode("utf-8")) > 16 * 1024**2:
        raise ValueError("Complete candidate exceeds the metadata budget; no truncation allowed")
    check_cancel(should_cancel)
    verify_transcription_witnesses(report, should_cancel=should_cancel)
    # The entire exclusive root was checked against all source/recipe/model roots
    # before creation; no need to resolve 7816 payload ancestors again here.
    new_report(
        root / "transcription.json",
        content,
        [source.decode_report.path, source.source.path, source.pcm.path, backend_record.path],
    )
    validate_transcription_artifacts(report, should_cancel=should_cancel)
    return report
