"""Independent numeric, provenance and fresh native replay of inferred candidates."""

import math
import platform
import struct
import sys
from collections.abc import Callable
from pathlib import Path

import pydantic

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.transcription import TranscriptionCandidate
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.basic_pitch_backend import read_basic_pitch, validate_basic_pitch_probe
from suno2flp.validator.note_decode_evidence import verify_decoder_payload


def transcription_recipe() -> ScoringRecipe:
    root = Path(__file__).resolve().parent.parent
    names = (
        "core/models.py",
        "core/offline_models.py",
        "core/performance.py",
        "core/offline_files.py",
        "core/report_publication.py",
        "core/errors.py",
        "core/file_tree.py",
        "core/note_scoring.py",
        "core/transcription.py",
        "core/transcription_clock.py",
        "validator/transcription.py",
        "validator/transcription_source.py",
        "validator/note_decode_evidence.py",
        "importer/note_annotations.py",
        "pipeline/transcription.py",
    )
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[capture_stream_input(root / name) for name in names],
    )


def check_cancel(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise DecodeCancelled()


def verify_transcription_witnesses(
    report: TranscriptionCandidate, *, should_cancel: Callable[[], bool] | None = None
) -> None:
    current = capture_file_tree(report.backend.root / "packages", should_cancel=should_cancel)
    if current != sorted(report.model_dependencies, key=lambda identity: identity.path):
        raise ValueError("Complete current model payload identities changed")
    model_paths = {identity.path for identity in current}
    verify_inputs([identity for identity in report.witnesses() if identity.path not in model_paths])
    verify_decoder_payload(report.decode_dependencies, report.decoder_payload_root)


def validate_transcription_artifacts(
    report: TranscriptionCandidate, *, should_cancel: Callable[[], bool] | None = None
) -> None:
    report = TranscriptionCandidate.model_validate(report.model_dump())
    validate_basic_pitch_probe(report.result.probe, report.backend.root)
    check_cancel(should_cancel)
    verify_transcription_witnesses(report, should_cancel=should_cancel)
    if report.recipe != transcription_recipe() or report.backend != read_basic_pitch(
        report.backend.root
    ):
        raise ValueError("Current transcription recipe/backend changed")
    payload = guarded_path(report.backend.root / "packages")
    expected = {payload / name for name in report.backend.payload}
    if {i.path for i in report.model_dependencies} != expected or len(
        report.model_dependencies
    ) != len(expected):
        raise ValueError("Model provenance does not cover complete payload membership")
    native = guarded_path(report.native_result.path.parent)
    names = {
        "mono.f32": report.mono,
        "bends.i8": report.bends,
        "result.json": report.native_result,
        "request.json": report.native_request,
        "stdout.bin": report.stdout,
        "stderr.bin": report.stderr,
    }
    names.update({f"{artifact.kind}.f32": artifact.file for artifact in report.predictions})
    if any(identity.path != native / name for name, identity in names.items()):
        raise ValueError("Candidate artifacts disagree with their native attempt addresses")
    _, raw = bounded_snapshot(report.native_result.path, 16 * 1024**2)
    from suno2flp.core.transcription import NativeTranscriptionResult

    if NativeTranscriptionResult.model_validate(load_unique_json(raw)) != report.result:
        raise ValueError("Native result differs from candidate snapshot")
    _, raw = bounded_snapshot(report.native_request.path, 1024**2)
    if load_unique_json(raw) != {
        "operation": "transcribe",
        "packages": str(report.backend.root / "packages"),
        "pcm": str(report.pcm.path),
        "frames": report.frames,
        "sample_rate": report.sample_rate,
        "channels": report.channels,
    }:
        raise ValueError("Native request disagrees with verified source clock")
    for identity in [report.mono, *[p.file for p in report.predictions]]:
        with identity.path.open("rb") as stream:
            while block := stream.read(1024**2):
                check_cancel(should_cancel)
                values = [value[0] for value in struct.iter_unpack("<f", block)]
                if any(not math.isfinite(value) for value in values):
                    raise ValueError("Numeric transcription artifacts must be finite")
                if identity != report.mono and any(not 0 <= value <= 1 for value in values):
                    raise ValueError("Raw model activations must remain in [0,1]")
    with report.bends.path.open("rb") as stream:
        while block := stream.read(1024**2):
            check_cancel(should_cancel)
            if any(not -25 <= value[0] <= 25 for value in struct.iter_unpack("<b", block)):
                raise ValueError("Bend artifact contains invalid third-semitone bins")
    verify_transcription_witnesses(report, should_cancel=should_cancel)


def verify_transcription(
    report_path: Path,
    replay_directory: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> TranscriptionCandidate:
    report_path = guarded_path(report_path)
    replay = guarded_path(replay_directory)
    original_root = report_path.parent
    if report_path.name != "transcription.json" or (
        replay == original_root
        or replay.is_relative_to(original_root)
        or original_root.is_relative_to(replay)
    ):
        raise ValueError(
            "Use a completed transcription report and replay outside its original root"
        )
    identity, raw = bounded_snapshot(report_path, 16 * 1024**2)
    report = TranscriptionCandidate.model_validate(load_unique_json(raw))
    if report.native_result.path != original_root / "native/result.json":
        raise ValueError("Completion report must remain with its own native artifacts")
    validate_transcription_artifacts(report, should_cancel=should_cancel)
    from suno2flp.pipeline.transcription import transcribe_audio

    current = transcribe_audio(
        report.decode_report.path,
        report.backend.root,
        replay_directory,
        should_cancel=should_cancel,
    )
    fields = (
        "decode_report",
        "source_audio",
        "pcm",
        "frames",
        "sample_rate",
        "channels",
        "decode_dependencies",
        "decoder_payload_root",
        "backend_record",
        "backend",
        "model_dependencies",
        "recipe",
        "result",
    )

    def artifacts(r: TranscriptionCandidate) -> list[tuple[str, int]]:
        return [
            (i.sha256, i.size_bytes) for i in [r.mono, *[p.file for p in r.predictions], r.bends]
        ]

    if any(getattr(report, name) != getattr(current, name) for name in fields) or artifacts(
        report
    ) != artifacts(current):
        raise ValueError("Fresh native replay disagrees with complete candidate predictions/notes")
    verify_inputs([identity])
    verify_transcription_witnesses(report, should_cancel=should_cancel)
    return report
