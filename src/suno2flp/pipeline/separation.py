"""Exclusive source-bound separation candidates; no musical qualification or DAW action."""

import math
import struct
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.separation import (
    SeparationCandidate,
    SeparationPartArtifact,
    SeparationStemArtifact,
    StemFile,
    StemName,
)
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.spleeter_backend import call_spleeter_separation, read_spleeter
from suno2flp.validator.separation import (
    check_cancel,
    read_runtime_context,
    separation_payload,
    separation_recipe,
    validate_separation_artifacts,
    verify_separation_witnesses,
)
from suno2flp.validator.transcription_source import verified_transcription_source

STEMS: tuple[StemName, ...] = ("vocals", "drums", "bass", "other")


def _residual(
    pcm: Path,
    stems: list[SeparationStemArtifact],
    output: Path,
    frames: int,
    channels: int,
    should_cancel: Callable[[], bool] | None,
) -> tuple[float, float]:
    peak = error = 0.0
    with ExitStack() as stack:
        source = stack.enter_context(pcm.open("rb"))
        source.seek(58)
        streams = [stack.enter_context(stem.source.path.open("rb")) for stem in stems]
        for stream in streams:
            stream.seek(58)
        target = stack.enter_context(output.open("xb"))
        for start in range(0, frames, 4096):
            check_cancel(should_cancel)
            count = min(4096, frames - start)
            original = list(struct.iter_unpack("<d", source.read(count * channels * 8)))
            parts = [list(struct.iter_unpack("<f", s.read(count * 8))) for s in streams]
            if len(original) != count * channels or any(len(p) != count * 2 for p in parts):
                raise ValueError("Complete source-grid samples are required for the residual")
            block = bytearray()
            for index in range(count * 2):
                value = original[index // 2 if channels == 1 else index][0]
                estimates = [part[index][0] for part in parts]
                if not all(math.isfinite(v) for v in [value, *estimates]):
                    raise ValueError("Residual inputs must be finite")
                residual = value - math.fsum(estimates)
                peak = max(peak, abs(residual))
                error = max(error, abs(math.fsum([*estimates, residual]) - value))
                block.extend(struct.pack("<d", residual))
            target.write(block)
    return peak, error


def separate_audio(
    decode_report: Path,
    backend: Path,
    output: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> SeparationCandidate:
    check_cancel(should_cancel)
    source = verified_transcription_source(decode_report, should_cancel=should_cancel)
    model = read_spleeter(backend)
    backend_record = capture_stream_input(model.root / "backend.json")
    recipe = separation_recipe()
    dependencies = separation_payload(model.root, should_cancel=should_cancel)
    root = new_model_directory(
        output,
        [
            model.root,
            source.source.path,
            source.pcm.path,
            *[i.path for i in source.dependencies],
            *[i.path for i in model.artifacts],
            *[i.path for i in recipe.files],
        ],
    )
    native = root / "native"
    native.mkdir()
    native_result, result = call_spleeter_separation(
        model,
        native,
        dict(
            operation="separate",
            pcm=str(source.pcm.path),
            frames=source.frames,
            sample_rate=source.sample_rate,
            channels=source.channels,
        ),
        should_cancel=should_cancel,
    )
    runtime_context = read_runtime_context(native)
    partitions = [
        SeparationPartArtifact(
            partition=part.partition,
            input=capture_stream_input(native / f"parts/{part.partition.index:04d}.input.f32"),
            outputs=[
                StemFile(
                    stem=stem,
                    file=capture_stream_input(
                        native / f"parts/{part.partition.index:04d}.{stem}.f32"
                    ),
                )
                for stem in STEMS
            ],
        )
        for part in result.partitions
    ]
    stems = [
        SeparationStemArtifact(
            stem=stem,
            model=capture_stream_input(native / f"model.{stem}.f32"),
            source=capture_stream_input(native / f"{stem}.wav"),
            tail=capture_stream_input(native / f"{stem}.tail.f32"),
        )
        for stem in STEMS
    ]
    residual = root / "unassigned-residual.f64"
    peak, error = _residual(
        source.pcm.path, stems, residual, source.frames, source.channels, should_cancel
    )
    report = SeparationCandidate(
        schema_version=2,
        profile="source-bound-spleeter-four-stem-candidate-v2",
        runtime_context=runtime_context,
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
        model_input=capture_stream_input(native / "model-input.f32"),
        partitions=partitions,
        stems=stems,
        residual=capture_stream_input(residual),
        residual_peak=peak,
        conservation_error=error,
        native_result=native_result,
        native_request=capture_stream_input(native / "request.json"),
        stdout=capture_stream_input(native / "stdout.bin"),
        stderr=capture_stream_input(native / "stderr.bin"),
    )
    validate_separation_artifacts(report, should_cancel=should_cancel)
    content = report.model_dump_json(indent=2)

    def verify_current() -> None:
        # Numeric checks ran against these exact witnesses. Recheck all bytes and
        # membership after serialization; do not repeat the expensive DSP walk.
        snapshot = SeparationCandidate.model_validate_json(content)
        verify_separation_witnesses(snapshot, should_cancel=should_cancel)
        if snapshot.recipe != separation_recipe():
            raise ValueError("Separation recipe changed before publication")
        check_cancel(should_cancel)

    publish_verified_report(
        root / "separation.json",
        content,
        [source.decode_report.path, source.source.path, source.pcm.path, backend_record.path],
        verify_current,
    )
    return report
