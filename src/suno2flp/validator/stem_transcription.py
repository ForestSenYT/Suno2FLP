"""Current complete lineage and independent fresh batch replay, without qualification."""

import platform
import sys
from collections.abc import Callable
from pathlib import Path

import pydantic

from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.separation import SeparationCandidate, SeparationReplayReceipt
from suno2flp.core.stem_transcription import (
    EstimatedStemSource,
    StemBatchReplay,
    StemTranscriptionBatch,
    StemTranscriptionCandidate,
)
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.validator.separation import validate_separation_artifacts, verify_separation_witnesses
from suno2flp.validator.stem_audio import verify_stem_wave
from suno2flp.validator.stem_snapshot import StemEvidence, capture_stem_evidence
from suno2flp.validator.transcription import check_cancel, validate_pitch_artifacts


def stem_recipe() -> ScoringRecipe:
    root = Path(__file__).resolve().parent.parent
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[
            capture_stream_input(root / name)
            for name in (
                "core/stem_transcription.py",
                "core/inference_snapshot.py",
                "importer/stem_audio.py",
                "validator/stem_audio.py",
                "validator/stem_transcription.py",
                "validator/stem_snapshot.py",
                "pipeline/stem_transcription.py",
            )
        ],
    )


def read_separation(path: Path) -> tuple[FileIdentity, SeparationCandidate]:
    path = guarded_path(path)
    identity, raw = bounded_snapshot(path, 16 * 1024**2)
    report = SeparationCandidate.model_validate(load_unique_json(raw))
    if (
        path.name != "separation.json"
        or report.native_result.path != path.parent / "native/result.json"
    ):
        raise ValueError("Use a completed separation beside its own native artifacts")
    return identity, report


def read_lineage_snapshots(
    separation: FileIdentity,
    receipt: FileIdentity,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[SeparationCandidate, SeparationCandidate]:
    verify_inputs([separation, receipt])
    identity, raw = bounded_snapshot(receipt.path, 1024**2)
    declared = SeparationReplayReceipt.model_validate(load_unique_json(raw))
    if (
        identity != receipt
        or declared.original_report != separation
        or receipt.path.name != "replay.json"
        or declared.replay_report.path != receipt.path.parent / "separation.json"
    ):
        raise ValueError("Fresh separation receipt must reference its actual own reports")
    original_id, original = read_separation(separation.path)
    replay_id, replay = read_separation(declared.replay_report.path)
    if original_id != separation or replay_id != declared.replay_report:
        raise ValueError("Current complete separation snapshots differ from their receipt")
    # Structural/current metadata only. Numeric authority must come from the
    # caller's full validation or actual owned fresh native invocation.
    check_cancel(should_cancel)
    fields = (
        "decode_report",
        "source_audio",
        "pcm",
        "frames",
        "sample_rate",
        "channels",
        "decode_dependencies",
        "decoder_payload_root",
        "backend",
        "backend_record",
        "model_dependencies",
        "recipe",
        "residual_peak",
        "conservation_error",
    )
    observations = {"elapsed_seconds", "peak_working_set_bytes", "peak_commit_bytes"}

    def signals(report: SeparationCandidate) -> list[tuple[str, int]]:
        return [
            (i.sha256, i.size_bytes)
            for i in [
                report.model_input,
                *[f for p in report.partitions for f in [p.input, *[o.file for o in p.outputs]]],
                *[f for s in report.stems for f in (s.model, s.source, s.tail)],
                report.residual,
            ]
        ]

    if (
        any(getattr(original, f) != getattr(replay, f) for f in fields)
        or original.result.model_dump(exclude=observations)
        != replay.result.model_dump(exclude=observations)
        or signals(original) != signals(replay)
    ):
        raise ValueError("Complete separation replay evidence differs")
    verify_inputs([separation, receipt, replay_id])
    return original, replay


def read_lineage(
    separation: FileIdentity,
    receipt: FileIdentity,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[SeparationCandidate, SeparationCandidate]:
    receipt_id, raw = bounded_snapshot(receipt.path, 1024**2)
    expected = SeparationReplayReceipt.model_validate(load_unique_json(raw))
    if receipt_id != receipt:
        raise ValueError("Separation receipt changed before numeric validation")
    original, replay = read_lineage_snapshots(separation, receipt, should_cancel=should_cancel)
    for report in (original, replay):
        validate_separation_artifacts(report, should_cancel=should_cancel)
    verify_inputs([separation, receipt, expected.replay_report])
    return original, replay


def validate_source(
    source: EstimatedStemSource,
    original: SeparationCandidate,
    replay: SeparationCandidate,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    source = EstimatedStemSource.model_validate(source.model_dump())
    original_id, original_snapshot = read_separation(source.separation_report.path)
    replay_id, replay_snapshot = read_separation(source.replay_report.path)
    if (original_id, original_snapshot, replay_id, replay_snapshot) != (
        source.separation_report,
        original,
        source.replay_report,
        replay,
    ):
        raise ValueError("Estimated source must retain the exact current lineage snapshots")
    estimated = next(item.source for item in original.stems if item.stem == source.stem)
    if (
        source.original_audio,
        source.original_decode,
        source.estimated_audio,
        source.frames,
        source.sample_rate,
        source.channels,
    ) != (
        original.source_audio,
        original.decode_report,
        estimated,
        original.frames,
        original.sample_rate,
        original.output_channels,
    ):
        raise ValueError("Estimated source ancestry differs from the original song/separation")
    if source.recipe != stem_recipe():
        raise ValueError("Current estimated source preparation recipe changed")
    verify_stem_wave(
        estimated,
        source.pcm,
        frames=source.frames,
        sample_rate=source.sample_rate,
        channels=source.channels,
        should_cancel=should_cancel,
    )
    verify_inputs([source.separation_report, source.separation_replay, source.replay_report])
    if source.replay_report.path != source.separation_replay.path.parent / "separation.json":
        raise ValueError("Estimated source replay report has a foreign address")
    if capture_stream_input(source.replay_report.path) != source.replay_report:
        raise ValueError("Estimated source replay identity changed")
    for report in (original, replay):
        verify_separation_witnesses(report, should_cancel=should_cancel)
    check_cancel(should_cancel)


def read_batch(path: Path) -> tuple[FileIdentity, StemTranscriptionBatch]:
    identity, raw = bounded_snapshot(path, 1024**2)
    report = StemTranscriptionBatch.model_validate(load_unique_json(raw))
    if path.name != "stem-transcription.json":
        raise ValueError("Use the canonical completed stem batch report")
    return identity, report


def read_stem_candidates(
    report: StemTranscriptionBatch,
    root: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> list[StemTranscriptionCandidate]:
    report = StemTranscriptionBatch.model_validate(report.model_dump())
    if (
        report.recipe != stem_recipe()
        or report.separation_replay.path != root / "separation-replay/replay.json"
    ):
        raise ValueError("Batch recipe or owned separation replay address differs")
    results = []
    for entry in report.stems:
        expected = root / entry.stem / "pitch/transcription.json"
        identity, raw = bounded_snapshot(entry.transcription.path, 16 * 1024**2)
        candidate = StemTranscriptionCandidate.model_validate(load_unique_json(raw))
        if (
            identity != entry.transcription
            or identity.path != expected
            or candidate.native_result.path != expected.parent / "native/result.json"
            or candidate.pcm.path != root / entry.stem / "estimated-f64.wav"
        ):
            raise ValueError("Stem prediction must retain its own complete native/source artifacts")
        if (
            candidate.source.stem,
            candidate.source.separation_report,
            candidate.source.separation_replay,
            candidate.backend_record,
        ) != (
            entry.stem,
            report.separation_report,
            report.separation_replay,
            report.backend_record,
        ):
            raise ValueError("Stem prediction snapshot differs from batch ancestry")
        results.append(candidate)
    verify_inputs([report.backend_record, *[entry.transcription for entry in report.stems]])
    check_cancel(should_cancel)
    return results


def validate_batch(
    report: StemTranscriptionBatch,
    root: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> list[StemTranscriptionCandidate]:
    results = read_stem_candidates(report, root, should_cancel=should_cancel)
    original, replay = read_lineage(
        report.separation_report, report.separation_replay, should_cancel=should_cancel
    )
    for candidate in results:
        validate_source(candidate.source, original, replay, should_cancel=should_cancel)
        validate_pitch_artifacts(candidate, should_cancel=should_cancel)
    verify_inputs([report.backend_record, *[entry.transcription for entry in report.stems]])
    check_cancel(should_cancel)
    return results


def batch_evidence(
    report: StemTranscriptionBatch,
    candidates: list[StemTranscriptionCandidate],
    *,
    identities: list[FileIdentity],
    should_cancel: Callable[[], bool] | None = None,
) -> StemEvidence:
    """Only after full validation or a trusted live producer returned this exact batch."""
    original, replay = read_lineage_snapshots(
        report.separation_report, report.separation_replay, should_cancel=should_cancel
    )
    return capture_stem_evidence(
        original,
        replay,
        candidates,
        recipe=report.recipe,
        pitch_recipe=candidates[0].recipe,
        identities=[
            report.separation_report,
            report.separation_replay,
            report.backend_record,
            *[entry.transcription for entry in report.stems],
            *identities,
        ],
        should_cancel=should_cancel,
    )


def verify_stem_batch(
    report: Path,
    output: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> StemTranscriptionBatch:
    report, output = guarded_path(report), guarded_path(output)
    identity, original = read_batch(report)
    if (
        output == report.parent
        or output.is_relative_to(report.parent)
        or report.parent.is_relative_to(output)
    ):
        raise ValueError("Use new replay outside the original stem batch")
    before = validate_batch(original, report.parent, should_cancel=should_cancel)
    before_evidence = batch_evidence(
        original, before, identities=[identity], should_cancel=should_cancel
    )
    from suno2flp.pipeline.stem_transcription import transcribe_stems

    current = transcribe_stems(
        original.separation_report.path,
        original.backend_record.path.parent,
        output,
        stems=tuple(entry.stem for entry in original.stems),
        should_cancel=should_cancel,
    )
    current_id, serialized = read_batch(output / "stem-transcription.json")
    if current != serialized:
        raise ValueError("Serialized stem replay differs from actual completed batch")
    # The actual producer just validated every relationship before publication.
    # Re-read its exact serialized snapshots and current bytes without recomputing
    # the same numeric relationships or accepting a standalone saved receipt.
    after = read_stem_candidates(current, output, should_cancel=should_cancel)
    after_evidence = batch_evidence(
        current, after, identities=[current_id], should_cancel=should_cancel
    )
    for a, b in zip(before, after, strict=True):
        fields = (
            "frames",
            "sample_rate",
            "channels",
            "backend_record",
            "backend",
            "model_dependencies",
            "recipe",
            "result",
        )

        def signals(r: StemTranscriptionCandidate) -> list[tuple[str, int]]:
            return [
                (i.sha256, i.size_bytes)
                for i in [r.pcm, r.mono, *[p.file for p in r.predictions], r.bends]
            ]

        if any(getattr(a, name) != getattr(b, name) for name in fields) or signals(a) != signals(b):
            raise ValueError("Fresh complete stem prediction replay disagrees")
    receipt = StemBatchReplay(original_report=identity, replay_report=current_id)

    def verify_current() -> None:
        verify_inputs([identity, current_id])
        before_evidence.recheck(should_cancel=should_cancel)
        after_evidence.recheck(should_cancel=should_cancel)

    publish_verified_report(
        output / "replay.json",
        receipt.model_dump_json(indent=2),
        [identity.path, current_id.path],
        verify_current,
    )
    return original
