"""Current complete artifacts and fresh native replay, without model qualification."""

import math
import platform
import struct
import sys
from pathlib import Path

import pydantic

from suno2flp.core.drum_native import NativeDrumResult
from suno2flp.core.drum_runtime import DrumBackend
from suno2flp.core.drum_transcription import DrumReplayReceipt, DrumTranscriptionCandidate
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
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.beat_backend import Cancel, cancelled
from suno2flp.integrations.drum_backend import (
    load_drum_pins,
    read_drum_backend,
    verify_drum_request,
)
from suno2flp.integrations.drum_probe import verify_drum_mono
from suno2flp.validator.drum_postprocessing import derive_drum_peaks
from suno2flp.validator.drum_source import DrumSourceEvidence, load_drum_source


def drum_recipe() -> ScoringRecipe:
    root = Path(__file__).resolve().parent.parent
    names = (
        "core/drum_transcription.py",
        "core/drum_peaks.py",
        "core/drum_snapshot.py",
        "core/drum_clock.py",
        "core/drum_native.py",
        "core/drum_runtime.py",
        "core/drum_scoring.py",
        "core/inference_snapshot.py",
        "core/models.py",
        "core/offline_models.py",
        "core/note_scoring.py",
        "core/performance.py",
        "core/offline_files.py",
        "core/report_publication.py",
        "core/separation.py",
        "core/separation_clock.py",
        "importer/note_annotations.py",
        "validator/drum_source.py",
        "validator/drum_postprocessing.py",
        "validator/drum_transcription.py",
        "validator/stem_transcription.py",
        "pipeline/drum_transcription.py",
    )
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[capture_stream_input(root / name) for name in names],
    )


def drum_payload_files(backend: DrumBackend, *, should_cancel: Cancel = None) -> list[FileIdentity]:
    root = guarded_path(backend.root / "packages")
    files = capture_file_tree(root, max_bytes=3 * 1024**3, should_cancel=should_cancel)
    if {i.path.relative_to(root).as_posix(): i.sha256 for i in files} != backend.payload:
        raise ValueError("Complete current drum payload differs from backend")
    return files


def validate_drum_native(
    record: DrumTranscriptionCandidate,
    *,
    should_cancel: Cancel = None,
) -> None:
    cancelled(should_cancel)
    attempt = guarded_path(record.root / "native")
    actual = capture_file_tree(attempt, should_cancel=should_cancel)
    if actual != record.native_witnesses:
        raise ValueError("Complete native drum witness membership/bytes changed")
    identity, raw = bounded_snapshot(attempt / "result.json", 1024**2)
    if (
        NativeDrumResult.model_validate(load_unique_json(raw)) != record.native
        or identity not in actual
    ):
        raise ValueError("Native drum result disagrees with its paired candidate")
    verify_drum_request(
        record.backend, attempt, record.source.model_pcm, record.native.model_frames
    )
    pins = load_drum_pins()
    if record.native.execution.geometry != pins.state or record.native.execution.versions != {
        p.distribution: p.version for p in pins.artifacts
    }:
        raise ValueError("Current drum state/runtime recipe differs from native result")
    modules = record.native.execution.modules
    if set(modules) != {"torch", "torchaudio", "numpy", "einops", "idm"} or any(
        not guarded_path(p).is_relative_to(record.backend.root / "packages")
        for p in modules.values()
    ):
        raise ValueError("Native drum imports escaped fixed isolated payload")
    for name, declared in record.native.files.items():
        current = capture_stream_input(attempt / name)
        if (current.size_bytes, current.sha256) != (declared.size_bytes, declared.sha256):
            raise ValueError("Native drum arrays changed or truncated")
    verify_drum_mono(
        record.source.model_pcm,
        capture_stream_input(attempt / "mono.f32"),
        record.native.model_frames,
    )

    def peak(path: Path) -> float:
        result = 0.0
        with path.open("rb") as stream:
            while block := stream.read(1024**2):
                if len(block) % 4:
                    raise ValueError("Input peak source changed or truncated")
                for (value,) in struct.iter_unpack("<f", block):
                    if not math.isfinite(value):
                        raise ValueError("Nonfinite input peak source")
                    result = max(result, abs(value))
        return result

    if (peak(record.source.model_pcm.path), peak(attempt / "mono.f32")) != (
        record.native.source_peak,
        record.native.mono_peak,
    ):
        raise ValueError("Native drum input peak observations differ from current samples")
    peaks, events, rejected = derive_drum_peaks(
        (attempt / "onsets.f32").read_bytes(),
        (attempt / "velocities.f32").read_bytes(),
        record.source.original.frames,
        record.source.original.sample_rate,
        should_cancel=should_cancel,
    )
    if (peaks, events, rejected) != (record.peaks, record.events, record.rejected_peaks):
        raise ValueError("Complete current drum derivations differ from candidate")
    verify_inputs([*actual, record.source.model_pcm])
    cancelled(should_cancel)


def drum_guard(
    record: DrumTranscriptionCandidate,
    source: DrumSourceEvidence,
    *,
    should_cancel: Cancel = None,
) -> InferenceSnapshot:
    if source.source() != record.source or record.recipe != drum_recipe():
        raise ValueError("Drum source/recipe differs from invocation's numeric proof")
    if record.model_dependencies != drum_payload_files(record.backend, should_cancel=should_cancel):
        raise ValueError(
            "Drum candidate must retain the complete current model dependency identities"
        )
    return InferenceSnapshot.capture(
        record.witnesses(),
        [(record.backend.root / "packages", record.model_dependencies)],
        should_cancel=should_cancel,
    )


def read_drum_candidate(
    path: Path,
    *,
    should_cancel: Cancel = None,
) -> tuple[FileIdentity, DrumTranscriptionCandidate, DrumSourceEvidence]:
    cancelled(should_cancel)
    identity, raw = bounded_snapshot(path, 16 * 1024**2)
    report = DrumTranscriptionCandidate.model_validate(load_unique_json(raw))
    if identity.path != report.root / "drum-transcription.json":
        raise ValueError("Use the completed drum candidate in its own original directory")
    recipe = drum_recipe()
    if recipe != report.recipe:
        raise ValueError("Current drum consumer recipe changed")
    current = read_drum_backend(report.backend.root, should_cancel=should_cancel)
    if report.backend != current or report.backend_record != capture_stream_input(
        current.root / "backend.json"
    ):
        raise ValueError("Current drum backend differs from candidate")
    source = load_drum_source(
        report.source.separation_report.path,
        report.source.separation_replay.path,
        recipe,
        should_cancel=should_cancel,
    )
    if source.source() != report.source:
        raise ValueError("Complete current estimated drum source differs from candidate")
    validate_drum_native(report, should_cancel=should_cancel)
    proof = drum_guard(report, source, should_cancel=should_cancel)
    source.recheck(drum_recipe(), should_cancel=should_cancel)
    proof.recheck(should_cancel=should_cancel)
    verify_inputs([identity])
    return identity, report, source


def verify_drum_transcription(
    path: Path,
    output: Path,
    *,
    should_cancel: Cancel = None,
) -> DrumReplayReceipt:
    from suno2flp.pipeline.drum_transcription import _collect_drums, _publish_drums

    identity, original, source = read_drum_candidate(path, should_cancel=should_cancel)
    frozen = drum_guard(original, source, should_cancel=should_cancel)
    replay = _collect_drums(
        source,
        original.backend.root,
        output,
        should_cancel=should_cancel,
        protected=[original.root],
    )
    if (
        replay.source != original.source
        or replay.backend != original.backend
        or replay.recipe != original.recipe
        or replay.native.files != original.native.files
        or replay.native.source_sha256 != original.native.source_sha256
        or (replay.native.source_peak, replay.native.mono_peak)
        != (original.native.source_peak, original.native.mono_peak)
        or replay.native.execution != original.native.execution
        or (replay.peaks, replay.events, replay.rejected_peaks)
        != (original.peaks, original.events, original.rejected_peaks)
    ):
        raise ValueError("Complete fresh native drum replay differs from saved candidate")
    frozen.recheck(should_cancel=should_cancel)
    verify_inputs([identity])
    _publish_drums(replay, source, should_cancel=should_cancel)
    replay_id = capture_stream_input(replay.root / "drum-transcription.json")
    receipt = DrumReplayReceipt(original_report=identity, replay_report=replay_id)

    def verify() -> None:
        source.recheck(drum_recipe(), should_cancel=should_cancel)
        frozen.recheck(should_cancel=should_cancel)
        verify_inputs([identity, replay_id])
        cancelled(should_cancel)

    publish_verified_report(
        replay.root / "replay.json",
        receipt.model_dump_json(indent=2),
        [original.root, identity.path],
        verify,
    )
    return receipt
