"""Current-artifact reconstruction; no native replay or musical qualification."""

import platform
import sys
from collections.abc import Callable
from pathlib import Path

import pydantic

from suno2flp.arrangement.inferred import build_estimated_arrangement
from suno2flp.core.beat_analysis import BeatCandidate
from suno2flp.core.estimated_arrangement import (
    EstimatedArrangement,
    EstimatedArrangementInputs,
    EstimatedPitchInput,
    EstimatedRhythmInput,
)
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.separation import StemFile
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.validator.beat_analysis import verify_beat_witnesses
from suno2flp.validator.stem_transcription import (
    batch_evidence,
    read_batch,
    read_separation,
    validate_batch,
)
from suno2flp.validator.transcription import check_cancel

Cancel = Callable[[], bool] | None


def estimated_recipe() -> ScoringRecipe:
    root = Path(__file__).resolve().parent.parent
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[
            capture_stream_input(root / name)
            for name in (
                "core/estimated_arrangement.py",
                "arrangement/inferred.py",
                "pipeline/estimated_arrangement.py",
                "validator/estimated_arrangement.py",
                "core/models.py",
                "core/offline_models.py",
                "core/performance.py",
                "core/offline_files.py",
                "core/report_publication.py",
                "core/errors.py",
                "core/note_scoring.py",
                "core/transcription_clock.py",
                "core/beat_clock.py",
                "importer/note_annotations.py",
            )
        ],
    )


def load_estimated_inputs(
    batch_path: Path,
    beats_path: Path | None,
    recipe: ScoringRecipe,
    *,
    should_cancel: Cancel = None,
) -> tuple[EstimatedArrangementInputs, list[Path], Callable[[], None]]:
    check_cancel(should_cancel)
    frozen_recipe = recipe.model_dump_json()
    batch_id, batch = read_batch(guarded_path(batch_path))
    candidates = validate_batch(batch, batch_id.path.parent, should_cancel=should_cancel)
    evidence = batch_evidence(batch, candidates, identities=[batch_id], should_cancel=should_cancel)
    separation_id, separation = read_separation(batch.separation_report.path)
    if separation_id != batch.separation_report:
        raise ValueError("Current separation differs from batch provenance")
    protected = [batch_id.path.parent, separation.backend.root]
    protected.extend(f.path for f in separation.witnesses())
    protected.extend([recipe.python_executable.path, *[f.path for f in recipe.files]])
    pitches = []
    for entry, candidate in zip(batch.stems, candidates, strict=True):
        pitches.append(
            EstimatedPitchInput(
                stem=entry.stem,
                transcription=entry.transcription,
                source_audio=candidate.source.original_audio,
                decode_report=candidate.source.original_decode,
                estimated_audio=candidate.source.estimated_audio,
                frames=candidate.frames,
                sample_rate=candidate.sample_rate,
                notes=candidate.result.notes,
                bends=candidate.bends,
            )
        )
        protected.extend(f.path for f in candidate.pitch_witnesses())
        protected.append(candidate.backend.root)
    rhythm = None
    beat = None
    beat_id = None
    if beats_path is not None:
        beat_id, raw = bounded_snapshot(guarded_path(beats_path), 16 * 1024**2)
        beat = BeatCandidate.model_validate(load_unique_json(raw))
        if beat_id.path != beat.root / "beats.json":
            raise ValueError("Use the completed beat report in its own original directory")
        verify_beat_witnesses(beat, should_cancel=should_cancel)
        rhythm = EstimatedRhythmInput(
            report=beat_id,
            source_audio=beat.source_audio,
            decode_report=beat.decode_report,
            pcm=beat.pcm,
            frames=beat.native.frames,
            sample_rate=beat.native.sample_rate,
            channels=beat.native.channels,
            beats=beat.beats,
            raw_downbeats=beat.raw_downbeats,
            downbeat_to_beat=beat.downbeat_to_beat,
            downbeats=beat.downbeats,
            signal_observations=beat.signal_observations,
        )
        protected.extend([beat.root, beat.backend.root, beat_id.path])
    inputs = EstimatedArrangementInputs(
        source_audio=separation.source_audio,
        decode_report=separation.decode_report,
        pcm=separation.pcm,
        frames=separation.frames,
        sample_rate=separation.sample_rate,
        channels=separation.channels,
        batch_report=batch_id,
        separation_report=separation_id,
        stems=[StemFile(stem=s.stem, file=s.source) for s in separation.stems],
        residual=separation.residual,
        pitches=pitches,
        rhythm=rhythm,
    )

    def recheck() -> None:
        check_cancel(should_cancel)
        evidence.recheck(should_cancel=should_cancel)
        if beat_id is not None and beat is not None:
            verify_inputs([beat_id])
            verify_beat_witnesses(beat, should_cancel=should_cancel)
        if estimated_recipe().model_dump_json() != frozen_recipe:
            raise ValueError("Estimated arrangement execution recipe changed")
        check_cancel(should_cancel)

    return inputs, protected, recheck


def validate_estimated_snapshot(
    record: EstimatedArrangement,
    inputs: EstimatedArrangementInputs,
    root: Path,
    recipe: ScoringRecipe,
) -> None:
    expected = build_estimated_arrangement(inputs)
    expected.root, expected.recipe = root, recipe
    if record != expected:
        raise ValueError("Estimated arrangement differs from complete current source derivation")


def verify_estimated_arrangement(
    report: Path,
    *,
    should_cancel: Cancel = None,
) -> EstimatedArrangement:
    identity, raw = bounded_snapshot(guarded_path(report), 16 * 1024**2)
    saved = EstimatedArrangement.model_validate(load_unique_json(raw))
    if identity.path.name != "estimated-arrangement.json" or saved.root != identity.path.parent:
        raise ValueError("Use the completed arrangement in its own original directory")
    recipe = estimated_recipe()
    if saved.recipe != recipe:
        raise ValueError("Saved estimated arrangement recipe differs from current execution")
    inputs, _, recheck = load_estimated_inputs(
        saved.inputs.batch_report.path,
        saved.inputs.rhythm.report.path if saved.inputs.rhythm is not None else None,
        recipe,
        should_cancel=should_cancel,
    )
    validate_estimated_snapshot(saved, inputs, identity.path.parent, recipe)
    recheck()
    verify_inputs([identity])
    check_cancel(should_cancel)
    return saved
