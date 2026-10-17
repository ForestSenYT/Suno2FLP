"""Current provenance, independent complete signals and fresh native replay."""

import platform
import sys
from collections.abc import Callable
from pathlib import Path

import pydantic

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.inference_snapshot import InferenceSnapshot
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.separation import (
    KerasRuntimeSettings,
    NativeSeparationResult,
    SeparationCandidate,
    SeparationReplayReceipt,
    SeparationRuntimeContext,
)
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.spleeter_backend import read_spleeter, validate_spleeter_execution
from suno2flp.validator.note_decode_evidence import verify_decoder_payload
from suno2flp.validator.separation_signal import validate_separation_signal
from suno2flp.validator.transcription_source import verified_transcription_source


def check_cancel(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise DecodeCancelled()


def separation_payload(
    root: Path, *, should_cancel: Callable[[], bool] | None = None
) -> list[FileIdentity]:
    return capture_file_tree(root / "packages", max_bytes=3 * 1024**3, should_cancel=should_cancel)


def separation_recipe() -> ScoringRecipe:
    root = Path(__file__).resolve().parent.parent
    names = (
        "core/models.py",
        "core/offline_models.py",
        "core/errors.py",
        "core/offline_files.py",
        "core/file_tree.py",
        "core/report_publication.py",
        "core/note_scoring.py",
        "core/separation.py",
        "core/separation_clock.py",
        "core/separation_runtime.py",
        "validator/separation.py",
        "validator/separation_signal.py",
        "pipeline/separation.py",
        "validator/transcription_source.py",
        "validator/note_decode_evidence.py",
        "importer/note_annotations.py",
    )
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[capture_stream_input(root / name) for name in names],
    )


def verify_separation_witnesses(
    report: SeparationCandidate, *, should_cancel: Callable[[], bool] | None = None
) -> None:
    report = SeparationCandidate.model_validate(report.model_dump())
    check_cancel(should_cancel)
    current = separation_payload(report.backend.root, should_cancel=should_cancel)
    if current != sorted(report.model_dependencies, key=lambda i: i.path):
        raise ValueError("Current complete separation model payload changed")
    paths = {identity.path for identity in current}
    if report.runtime_context is not None:
        native = guarded_path(report.native_result.path.parent)
        if read_runtime_context(native) != report.runtime_context:
            raise ValueError("Current runtime configuration differs from candidate snapshot")
        declared = report.native_witnesses()
        InferenceSnapshot.capture([], [(native, declared)], should_cancel=should_cancel)
        paths.update(i.path for i in declared)
    verify_inputs([i for i in report.witnesses() if i.path not in paths])
    verify_decoder_payload(report.decode_dependencies, report.decoder_payload_root)
    check_cancel(should_cancel)


def read_runtime_context(native: Path) -> SeparationRuntimeContext:
    identity, raw = bounded_snapshot(guarded_path(native) / "keras-cache/keras.json", 65536)
    return SeparationRuntimeContext(
        file=identity,
        settings=KerasRuntimeSettings.model_validate(load_unique_json(raw)),
    )


def validate_separation_artifacts(
    report: SeparationCandidate, *, should_cancel: Callable[[], bool] | None = None
) -> None:
    report = SeparationCandidate.model_validate(report.model_dump())
    verify_separation_witnesses(report, should_cancel=should_cancel)
    if report.recipe != separation_recipe() or report.backend != read_spleeter(report.backend.root):
        raise ValueError("Current separation recipe/backend differs from candidate")
    validate_spleeter_execution(report.result.execution, report.backend)
    expected = {
        report.backend.root / "packages" / name: digest
        for name, digest in report.backend.payload.items()
    }
    if (
        len(report.model_dependencies) != len(expected)
        or {i.path: i.sha256 for i in report.model_dependencies} != expected
    ):
        raise ValueError("Separation provenance must cover every fixed payload entry")
    source = verified_transcription_source(report.decode_report.path, should_cancel=should_cancel)
    if (
        report.decode_report,
        report.source_audio,
        report.pcm,
        report.frames,
        report.sample_rate,
        report.channels,
        report.decode_dependencies,
        report.decoder_payload_root,
    ) != (
        source.decode_report,
        source.source,
        source.pcm,
        source.frames,
        source.sample_rate,
        source.channels,
        source.dependencies,
        source.decoder_payload_root,
    ):
        raise ValueError(
            "Separation source/decode snapshot differs from independently verified source"
        )
    native = guarded_path(report.native_result.path.parent)
    names = {
        "result.json": report.native_result,
        "request.json": report.native_request,
        "stdout.bin": report.stdout,
        "stderr.bin": report.stderr,
        "model-input.f32": report.model_input,
    }
    if report.residual.path != native.parent / "unassigned-residual.f64":
        raise ValueError("Residual must remain beside its own native attempt")
    for stem in report.stems:
        names.update(
            {
                f"model.{stem.stem}.f32": stem.model,
                f"{stem.stem}.wav": stem.source,
                f"{stem.stem}.tail.f32": stem.tail,
            }
        )
    for part in report.partitions:
        prefix = f"parts/{part.partition.index:04d}"
        names[f"{prefix}.input.f32"] = part.input
        names.update({f"{prefix}.{o.stem}.f32": o.file for o in part.outputs})
    if any(i.path != native / name for name, i in names.items()):
        raise ValueError("Separation artifacts disagree with native attempt addresses")
    identity, raw = bounded_snapshot(report.native_result.path, 2 * 1024**2)
    if (
        identity != report.native_result
        or NativeSeparationResult.model_validate(load_unique_json(raw)) != report.result
    ):
        raise ValueError("Native separation result differs from paired candidate snapshot")
    identity, raw = bounded_snapshot(report.native_request.path, 1024**2)
    if identity != report.native_request or load_unique_json(raw) != dict(
        operation="separate",
        packages=str(report.backend.root / "packages"),
        pcm=str(report.pcm.path),
        frames=report.frames,
        sample_rate=report.sample_rate,
        channels=report.channels,
    ):
        raise ValueError("Native separation request differs from source clock")
    validate_separation_signal(report, should_cancel=should_cancel)
    verify_separation_witnesses(report, should_cancel=should_cancel)


def separation_replay_data(report: SeparationCandidate) -> list[tuple[str, int]]:
    files = [
        report.model_input,
        *[i for p in report.partitions for i in [p.input, *[o.file for o in p.outputs]]],
        *[i for s in report.stems for i in (s.model, s.source, s.tail)],
        report.residual,
        *([report.runtime_context.file] if report.runtime_context is not None else []),
    ]
    return [(i.sha256, i.size_bytes) for i in files]


def verify_separation(
    report_path: Path, replay_directory: Path, *, should_cancel: Callable[[], bool] | None = None
) -> SeparationCandidate:
    report_path, replay = guarded_path(report_path), guarded_path(replay_directory)
    root = report_path.parent
    if (
        report_path.name != "separation.json"
        or replay == root
        or replay.is_relative_to(root)
        or root.is_relative_to(replay)
    ):
        raise ValueError(
            "Use a completed separation report and new replay outside the original root"
        )
    original_identity, raw = bounded_snapshot(report_path, 16 * 1024**2)
    report = SeparationCandidate.model_validate(load_unique_json(raw))
    if report.native_result.path != root / "native/result.json":
        raise ValueError("Completion report must remain with its own native artifacts")
    if report.schema_version != 2:
        raise ValueError("Legacy separation metadata needs new v2 generation; no context backfill")
    validate_separation_artifacts(report, should_cancel=should_cancel)
    from suno2flp.pipeline.separation import separate_audio

    current = separate_audio(
        report.decode_report.path, report.backend.root, replay, should_cancel=should_cancel
    )
    replay_identity, raw = bounded_snapshot(replay / "separation.json", 16 * 1024**2)
    if SeparationCandidate.model_validate(load_unique_json(raw)) != current:
        raise ValueError("Serialized replay report differs from the verified candidate")
    fields = (
        "schema_version",
        "profile",
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
        "residual_peak",
        "conservation_error",
    )
    observations = {"elapsed_seconds", "peak_working_set_bytes", "peak_commit_bytes"}
    if (
        any(getattr(report, f) != getattr(current, f) for f in fields)
        or report.result.model_dump(exclude=observations)
        != current.result.model_dump(exclude=observations)
        or separation_replay_data(report) != separation_replay_data(current)
    ):
        raise ValueError("Fresh separation replay disagrees with complete candidate evidence")
    receipt = SeparationReplayReceipt(
        original_report=original_identity, replay_report=replay_identity
    )

    def verify_current() -> None:
        verify_inputs([original_identity, replay_identity])
        verify_separation_witnesses(report, should_cancel=should_cancel)
        verify_separation_witnesses(current, should_cancel=should_cancel)
        if report.recipe != separation_recipe():
            raise ValueError("Separation recipe changed before replay publication")
        check_cancel(should_cancel)

    publish_verified_report(
        replay / "replay.json",
        receipt.model_dump_json(indent=2),
        [original_identity.path, replay_identity.path],
        verify_current,
    )
    return report
