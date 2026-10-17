"""Current original-source binding and independent fresh native rhythm replay."""

import platform
import sys
from fractions import Fraction
from pathlib import Path

import pydantic

from suno2flp.core.beat_analysis import BeatCandidate, BeatReplay
from suno2flp.core.beat_clock import BeatAnchor, beat_anchor
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import capture_stream_input, load_unique_json, verify_inputs
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.beat_backend import (
    Cancel,
    cancelled,
    read_beat_backend,
    verify_beat_request,
)
from suno2flp.validator.beat_native import validate_native_beats
from suno2flp.validator.note_decode_evidence import verify_decoder_payload
from suno2flp.validator.transcription_source import verified_transcription_source


def beat_recipe() -> ScoringRecipe:
    root = Path(__file__).parent.parent
    names = (
        "core/beat_analysis.py",
        "core/beat_clock.py",
        "core/beat_native.py",
        "core/beat_runtime.py",
        "core/models.py",
        "core/offline_models.py",
        "core/note_scoring.py",
        "importer/note_annotations.py",
        "core/performance.py",
        "core/offline_files.py",
        "core/report_publication.py",
        "core/file_tree.py",
        "validator/beat_analysis.py",
        "validator/beat_native.py",
        "validator/beat_postprocessing.py",
        "validator/transcription_source.py",
        "validator/note_decode_evidence.py",
        "pipeline/beat_analysis.py",
    )
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[capture_stream_input(root / name) for name in names],
    )


def beat_derivations(record: BeatCandidate, *, should_cancel: Cancel = None) -> dict[str, object]:
    peaks, identities = validate_native_beats(
        record.root / "native", record.native, record.pcm.path, should_cancel=should_cancel
    )
    if identities != record.native_witnesses:
        raise ValueError("Complete native beat witnesses changed")

    def anchors(positions: list[Fraction]) -> list[BeatAnchor]:
        return [
            beat_anchor(
                p, sample_rate=record.native.sample_rate, source_frames=record.native.frames
            )
            for p in positions
        ]

    observations = []
    if record.native.source_peak == 0:
        observations.append("source-silent")
    elif record.native.mono_peak == 0:
        observations.append("downmix-cancellation")
    if not peaks.beat_frames:
        observations.append("no-beat-predictions")
    return dict(
        beat_peaks=peaks.beat_peaks,
        downbeat_peaks=peaks.downbeat_peaks,
        beats=anchors(peaks.beat_frames),
        raw_downbeats=anchors(peaks.downbeat_frames),
        downbeat_to_beat=peaks.downbeat_to_beat,
        downbeats=anchors(peaks.aligned_downbeat_frames),
        signal_observations=observations,
    )


def verify_beat_witnesses(record: BeatCandidate, *, should_cancel: Cancel = None) -> None:
    record = BeatCandidate.model_validate(record.model_dump())
    cancelled(should_cancel)
    verify_inputs(
        [
            record.decode_report,
            record.source_audio,
            record.pcm,
            record.backend_record,
            *record.decode_dependencies,
            *record.native_witnesses,
            *record.recipe.files,
            record.recipe.python_executable,
        ]
    )
    verify_decoder_payload(record.decode_dependencies, record.decoder_payload_root)
    if record.recipe != beat_recipe() or record.backend != read_beat_backend(
        record.backend.root, should_cancel=should_cancel
    ):
        raise ValueError("Beat analysis source recipe or backend changed")
    source = verified_transcription_source(record.decode_report.path, should_cancel=should_cancel)
    if (
        record.source_audio,
        record.pcm,
        record.decode_dependencies,
        record.decoder_payload_root,
        record.native.frames,
        record.native.sample_rate,
        record.native.channels,
    ) != (
        source.source,
        source.pcm,
        source.dependencies,
        source.decoder_payload_root,
        source.frames,
        source.sample_rate,
        source.channels,
    ):
        raise ValueError("Beat analysis no longer matches original source/decode geometry")
    result_path = record.root / "native/result.json"
    verify_beat_request(
        record.backend,
        record.root / "native",
        record.pcm,
        record.native.frames,
        record.native.sample_rate,
        record.native.channels,
    )
    _, raw = bounded_snapshot(result_path, 1024**2)
    if record.native.model_dump(mode="json") != load_unique_json(raw):
        raise ValueError("Beat native result snapshot changed")
    for key, expected in beat_derivations(record, should_cancel=should_cancel).items():
        if getattr(record, key) != expected:
            raise ValueError(f"Saved inferred beat derivation changed: {key}")
    cancelled(should_cancel)


def verify_beat_analysis(report: Path, output: Path, *, should_cancel: Cancel = None) -> BeatReplay:
    from suno2flp.pipeline.beat_analysis import collect_beats

    original, raw = bounded_snapshot(report, 16 * 1024**2)
    saved = BeatCandidate.model_validate(load_unique_json(raw))
    if original.path != saved.root / "beats.json":
        raise ValueError("Saved beat report must be bound to its original directory")
    verify_beat_witnesses(saved, should_cancel=should_cancel)
    fresh = collect_beats(
        saved.decode_report.path,
        saved.backend.root,
        output,
        should_cancel=should_cancel,
        protected=[original.path, saved.root],
    )
    if saved.native.files != fresh.native.files or saved.native.execution != fresh.native.execution:
        raise ValueError("Fresh native rhythm replay differs from the saved complete inference")
    receipt = BeatReplay(original=original, saved=saved, fresh=fresh)

    def verify() -> None:
        verify_inputs([original])
        verify_beat_witnesses(saved, should_cancel=should_cancel)
        verify_beat_witnesses(fresh, should_cancel=should_cancel)

    publish_verified_report(
        fresh.root / "replay.json", receipt.model_dump_json(indent=2), [original.path], verify
    )
    return receipt
