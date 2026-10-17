"""Exclusive source-bound drum candidates and separate conditional score annotations."""

from pathlib import Path

from suno2flp.core.drum_scoring import DrumAnnotation
from suno2flp.core.drum_transcription import DrumTranscriptionCandidate
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import capture_stream_input, guarded_path
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.beat_backend import Cancel, cancelled
from suno2flp.integrations.drum_backend import call_drum_backend, read_drum_backend
from suno2flp.validator.drum_postprocessing import derive_drum_peaks
from suno2flp.validator.drum_source import DrumSourceEvidence, load_drum_source
from suno2flp.validator.drum_transcription import (
    drum_guard,
    drum_payload_files,
    drum_recipe,
    read_drum_candidate,
    validate_drum_native,
)


def _collect_drums(
    proof: DrumSourceEvidence,
    backend: Path,
    output: Path,
    *,
    should_cancel: Cancel = None,
    protected: list[Path] | None = None,
) -> DrumTranscriptionCandidate:
    cancelled(should_cancel)
    recipe = drum_recipe()
    proof.recheck(recipe, should_cancel=should_cancel)
    source = proof.source()
    model = read_drum_backend(backend, should_cancel=should_cancel)
    backend_record = capture_stream_input(model.root / "backend.json")
    paths = [
        model.root,
        source.separation_report.path.parent,
        source.separation_replay.path.parent,
        *[i.path for i in source.witnesses()],
        *[i.path for i in model.artifacts],
        recipe.python_executable.path,
        *[i.path for i in recipe.files],
        *(protected or []),
    ]
    root = new_model_directory(output, list(dict.fromkeys(paths)))
    attempt = root / "native"
    attempt.mkdir()
    native = call_drum_backend(
        model,
        attempt,
        source.model_pcm,
        source.original.result.model_frames,
        should_cancel=should_cancel,
    )
    peaks, events, rejected = derive_drum_peaks(
        (attempt / "onsets.f32").read_bytes(),
        (attempt / "velocities.f32").read_bytes(),
        source.original.frames,
        source.original.sample_rate,
        should_cancel=should_cancel,
    )
    report = DrumTranscriptionCandidate(
        root=root,
        source=source,
        backend_record=backend_record,
        backend=model,
        model_dependencies=drum_payload_files(model, should_cancel=should_cancel),
        recipe=recipe,
        native=native,
        native_witnesses=capture_file_tree(attempt, should_cancel=should_cancel),
        peaks=peaks,
        events=events,
        rejected_peaks=rejected,
    )
    validate_drum_native(report, should_cancel=should_cancel)
    proof.recheck(drum_recipe(), should_cancel=should_cancel)
    return report


def _publish_drums(
    report: DrumTranscriptionCandidate,
    source: DrumSourceEvidence,
    *,
    should_cancel: Cancel = None,
) -> None:
    guard = drum_guard(report, source, should_cancel=should_cancel)

    def verify() -> None:
        source.recheck(drum_recipe(), should_cancel=should_cancel)
        guard.recheck(should_cancel=should_cancel)
        cancelled(should_cancel)

    publish_verified_report(
        report.root / "drum-transcription.json",
        report.model_dump_json(indent=2),
        [i.path for i in report.witnesses()],
        verify,
    )


def transcribe_drums(
    separation: Path,
    separation_replay: Path,
    backend: Path,
    output: Path,
    *,
    should_cancel: Cancel = None,
) -> DrumTranscriptionCandidate:
    cancelled(should_cancel)
    # Fail native prerequisites before expensive source numeric validation/new output creation.
    read_drum_backend(backend, should_cancel=should_cancel)
    source = load_drum_source(
        separation, separation_replay, drum_recipe(), should_cancel=should_cancel
    )
    report = _collect_drums(source, backend, output, should_cancel=should_cancel)
    _publish_drums(report, source, should_cancel=should_cancel)
    return report


def export_drum_annotation(
    path: Path, output: Path, *, should_cancel: Cancel = None
) -> DrumAnnotation:
    identity, report, source = read_drum_candidate(path, should_cancel=should_cancel)
    original = report.source.original
    destination = guarded_path(output)
    producer_roots = [
        report.root,
        report.backend.root,
        report.source.separation_report.path.parent,
        report.source.separation_replay.path.parent,
        original.backend.root,
        report.source.replay.backend.root,
        original.decode_report.path.parent,
    ]
    producer_roots.extend(
        s.decoder_payload_root
        for s in (original, report.source.replay)
        if s.decoder_payload_root is not None
    )
    if any(destination.is_relative_to(guarded_path(root)) for root in producer_roots):
        raise ValueError("Export drum annotations outside all immutable producer directories")
    annotation = DrumAnnotation(
        role="candidate",
        origin="inferred_candidate",
        method=report.postprocessing_profile + "; geometric centers; musical latency uncalibrated",
        provenance_files=[identity],
        decode_report=original.decode_report,
        source_audio=original.source_audio,
        frames=original.frames,
        sample_rate=original.sample_rate,
        channels=original.channels,
        events=report.events,
    )
    guard = drum_guard(report, source, should_cancel=should_cancel)

    def verify() -> None:
        from suno2flp.core.offline_files import verify_inputs

        verify_inputs([identity])
        source.recheck(drum_recipe(), should_cancel=should_cancel)
        guard.recheck(should_cancel=should_cancel)
        cancelled(should_cancel)

    publish_verified_report(
        output,
        annotation.model_dump_json(indent=2),
        [identity.path, *[i.path for i in report.witnesses()]],
        verify,
    )
    return annotation
