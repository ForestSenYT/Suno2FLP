"""One owned fresh separation replay followed by explicit estimated pitched sources."""

from collections.abc import Callable
from functools import partial
from pathlib import Path

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.stem_transcription import (
    PITCHED_STEMS,
    EstimatedStemSource,
    PitchedStem,
    StemTranscriptionBatch,
    StemTranscriptionCandidate,
    StemTranscriptionEntry,
)
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.importer.stem_audio import widen_stem_wave
from suno2flp.integrations.basic_pitch_backend import new_model_directory, read_basic_pitch
from suno2flp.pipeline.transcription import run_pitch_candidate
from suno2flp.validator.separation import verify_separation
from suno2flp.validator.stem_snapshot import capture_stem_evidence
from suno2flp.validator.stem_transcription import (
    read_lineage,
    read_separation,
    read_stem_candidates,
    stem_recipe,
    validate_source,
)
from suno2flp.validator.transcription import (
    check_cancel,
    transcription_recipe,
    validate_pitch_artifacts,
)


def transcribe_stems(
    separation_report: Path,
    backend: Path,
    output: Path,
    *,
    stems: tuple[PitchedStem, ...] = PITCHED_STEMS,
    should_cancel: Callable[[], bool] | None = None,
) -> StemTranscriptionBatch:
    if not stems or tuple(stem for stem in PITCHED_STEMS if stem in stems) != stems:
        raise ValueError(
            "Select unique pitched stems in canonical vocals/bass/other order; drums unsupported"
        )
    check_cancel(should_cancel)
    recipe, pitch_recipe = stem_recipe(), transcription_recipe()
    separation_id, original = read_separation(separation_report)
    backend = read_basic_pitch(backend).root
    protected = [
        original.backend.root,
        separation_id.path.parent,
        original.decode_report.path,
        original.source_audio.path,
        original.pcm.path,
        backend,
        *[i.path for i in recipe.files],
    ]
    root = new_model_directory(output, protected)
    # Always fresh within this invocation. A supplied receipt cannot replace native replay.
    verify_separation(separation_report, root / "separation-replay", should_cancel=should_cancel)
    replay_id = capture_stream_input(root / "separation-replay/separation.json")
    receipt = capture_stream_input(root / "separation-replay/replay.json")
    original, replay = read_lineage(separation_id, receipt, should_cancel=should_cancel)
    entries = []
    candidates = []
    for name in stems:
        check_cancel(should_cancel)
        directory = root / name
        directory.mkdir()
        estimated = next(item.source for item in original.stems if item.stem == name)
        pcm = widen_stem_wave(
            estimated.path,
            directory / "estimated-f64.wav",
            frames=original.frames,
            sample_rate=original.sample_rate,
            channels=2,
            should_cancel=should_cancel,
        )
        source = EstimatedStemSource(
            stem=name,
            separation_report=separation_id,
            separation_replay=receipt,
            replay_report=replay_id,
            original_audio=original.source_audio,
            original_decode=original.decode_report,
            estimated_audio=estimated,
            pcm=pcm,
            frames=original.frames,
            sample_rate=original.sample_rate,
            recipe=recipe,
        )
        validate_source(source, original, replay, should_cancel=should_cancel)
        pitch = run_pitch_candidate(
            pcm,
            source.frames,
            source.sample_rate,
            2,
            backend,
            directory / "pitch",
            protected=protected,
            should_cancel=should_cancel,
        )
        candidate = StemTranscriptionCandidate(**pitch.model_dump(), source=source)
        validate_pitch_artifacts(candidate, should_cancel=should_cancel)
        content = candidate.model_dump_json(indent=2)
        # Numeric relationships were fully established above. Freeze their exact
        # expected bytes, then recheck all current inputs at publication without
        # reconstructing those same waveforms or predictions a second time.
        evidence = capture_stem_evidence(
            original,
            replay,
            [candidate],
            recipe=recipe,
            pitch_recipe=pitch_recipe,
            identities=[separation_id, receipt, replay_id],
            should_cancel=should_cancel,
        )
        manifest = directory / "pitch/transcription.json"
        publish_verified_report(
            manifest,
            content,
            [separation_id.path, receipt.path, estimated.path],
            partial(evidence.recheck, should_cancel=should_cancel),
        )
        identity, serialized = bounded_snapshot(manifest, 16 * 1024**2)
        if serialized != content.encode("utf-8"):
            raise ValueError("Serialized stem prediction differs from its validated snapshot")
        entries.append(StemTranscriptionEntry(stem=name, transcription=identity))
        candidates.append(candidate)
    batch = StemTranscriptionBatch(
        separation_report=separation_id,
        separation_replay=receipt,
        backend_record=capture_stream_input(backend / "backend.json"),
        stems=entries,
        recipe=recipe,
    )
    if read_stem_candidates(batch, root, should_cancel=should_cancel) != candidates:
        raise ValueError("Serialized stem reports differ from the actual validated candidates")
    final_evidence = capture_stem_evidence(
        original,
        replay,
        candidates,
        recipe=recipe,
        pitch_recipe=pitch_recipe,
        identities=[
            separation_id,
            receipt,
            replay_id,
            batch.backend_record,
            *[entry.transcription for entry in entries],
        ],
        should_cancel=should_cancel,
    )
    publish_verified_report(
        root / "stem-transcription.json",
        batch.model_dump_json(indent=2),
        [separation_id.path, receipt.path],
        partial(final_evidence.recheck, should_cancel=should_cancel),
    )
    return batch
