"""Reconstruct complete current producers; no fresh model or host execution."""

from collections.abc import Callable
from pathlib import Path

from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.inference_snapshot import InferenceSnapshot
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.percussion_arrangement import (
    EstimatedDrumInput,
    PercussionArrangement,
    PercussionArrangementInputs,
)
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.validator.drum_transcription import drum_guard, drum_recipe, read_drum_candidate
from suno2flp.validator.estimated_arrangement import estimated_recipe, load_estimated_inputs
from suno2flp.validator.stem_transcription import read_batch, read_stem_candidates
from suno2flp.validator.transcription import check_cancel

Cancel = Callable[[], bool] | None


def percussion_recipe() -> ScoringRecipe:
    base, drums = estimated_recipe(), drum_recipe()
    files: dict[Path, FileIdentity] = {}
    for identity in [*base.files, *drums.files]:
        if identity.path in files and files[identity.path] != identity:
            raise ValueError("Producer code changed while capturing the percussion recipe")
        files[identity.path] = identity
    root = Path(__file__).resolve().parent.parent
    for name in (
        "core/percussion_arrangement.py",
        "arrangement/percussion.py",
        "validator/percussion_arrangement.py",
        "pipeline/percussion_arrangement.py",
    ):
        identity = capture_stream_input(root / name)
        files[identity.path] = identity
    return ScoringRecipe(
        python_executable=base.python_executable,
        python_version=base.python_version,
        pydantic_version=base.pydantic_version,
        files=[files[path] for path in sorted(files)],
    )


def check_percussion_location(root: Path, protected: list[Path]) -> Path:
    destination = guarded_path(root)
    for source in protected:
        source = guarded_path(source)
        if destination.is_relative_to(source) or source.is_relative_to(destination):
            raise ValueError("Keep the arrangement outside immutable producer/input paths")
    return destination


def load_percussion_inputs(
    batch_path: Path,
    drums_path: Path,
    beats_path: Path | None,
    recipe: ScoringRecipe,
    *,
    should_cancel: Cancel = None,
) -> tuple[PercussionArrangementInputs, list[Path], Callable[[], None]]:
    check_cancel(should_cancel)
    frozen_recipe = recipe.model_dump_json()
    batch_id, batch = read_batch(guarded_path(batch_path))
    pitched, protected, recheck_pitched = load_estimated_inputs(
        batch_id.path, beats_path, estimated_recipe(), should_cancel=should_cancel
    )
    if batch_id != pitched.batch_report or batch.separation_report != pitched.separation_report:
        raise ValueError("Current pitched batch changed during source loading")
    drum_id, record, source = read_drum_candidate(
        guarded_path(drums_path), should_cancel=should_cancel
    )
    frozen_drums = drum_guard(record, source, should_cancel=should_cancel)
    original = record.source.original
    inputs = PercussionArrangementInputs(
        pitched=pitched,
        pitched_separation_replay=batch.separation_replay,
        drums=EstimatedDrumInput(
            transcription=drum_id,
            backend_record=record.backend_record,
            native_witnesses=record.native_witnesses,
            source_audio=original.source_audio,
            decode_report=original.decode_report,
            pcm=original.pcm,
            separation_report=record.source.separation_report,
            separation_replay=record.source.separation_replay,
            reference=next(s.source for s in original.stems if s.stem == "drums"),
            model_pcm=record.source.model_pcm,
            frames=original.frames,
            sample_rate=original.sample_rate,
            channels=original.channels,
            model_frames=record.native.model_frames,
            rows=record.native.rows,
            peaks=record.peaks,
            events=record.events,
            rejected_peaks=record.rejected_peaks,
            postprocessing_profile=record.postprocessing_profile,
        ),
    )
    candidates = read_stem_candidates(batch, batch_id.path.parent, should_cancel=should_cancel)
    native_producers = [
        (parent.native_result.path.parent, parent.witnesses())
        for parent in (original, record.source.replay)
    ] + [(item.native_result.path.parent, item.pitch_witnesses()) for item in candidates]
    frozen_ancestors = InferenceSnapshot.capture(
        [],
        [
            (
                root,
                list(
                    {file.path: file for file in entries if file.path.is_relative_to(root)}.values()
                ),
            )
            for root, entries in native_producers
        ],
        should_cancel=should_cancel,
    )
    protected.extend(
        [
            drum_id.path.parent,
            record.backend.root,
            record.source.separation_report.path.parent,
            record.source.separation_replay.path.parent,
            original.decode_report.path.parent,
            recipe.python_executable.path,
            *[f.path for f in recipe.files],
            *[f.path for f in record.witnesses()],
        ]
    )
    for parent in (original, record.source.replay):
        protected.append(parent.backend.root)
        if parent.decoder_payload_root is not None:
            protected.append(parent.decoder_payload_root)

    def recheck() -> None:
        check_cancel(should_cancel)
        recheck_pitched()
        source.recheck(drum_recipe(), should_cancel=should_cancel)
        frozen_drums.recheck(should_cancel=should_cancel)
        frozen_ancestors.recheck(should_cancel=should_cancel)
        verify_inputs([batch_id, drum_id, recipe.python_executable, *recipe.files])
        if percussion_recipe().model_dump_json() != frozen_recipe:
            raise ValueError("Percussion arrangement execution recipe changed")
        check_cancel(should_cancel)

    return inputs, list(dict.fromkeys(protected)), recheck


def validate_percussion_snapshot(
    record: PercussionArrangement,
    inputs: PercussionArrangementInputs,
    root: Path,
    recipe: ScoringRecipe,
) -> None:
    expected = build_percussion_arrangement(inputs)
    expected.root, expected.recipe = root, recipe
    if record != expected:
        raise ValueError("Percussion arrangement differs from complete current source derivation")


def verify_percussion_arrangement(
    report: Path, *, should_cancel: Cancel = None
) -> PercussionArrangement:
    check_cancel(should_cancel)
    identity, raw = bounded_snapshot(guarded_path(report), 16 * 1024**2)
    saved = PercussionArrangement.model_validate(load_unique_json(raw))
    root = identity.path.parent
    if identity.path.name != "percussion-arrangement.json" or saved.root != root:
        raise ValueError("Use the completed percussion arrangement in its own original directory")
    recipe = percussion_recipe()
    if saved.recipe != recipe:
        raise ValueError("Saved percussion arrangement recipe differs from current execution")
    inputs, protected, recheck = load_percussion_inputs(
        saved.inputs.pitched.batch_report.path,
        saved.inputs.drums.transcription.path,
        saved.inputs.pitched.rhythm.report.path
        if saved.inputs.pitched.rhythm is not None
        else None,
        recipe,
        should_cancel=should_cancel,
    )
    check_percussion_location(root, protected)
    validate_percussion_snapshot(saved, inputs, root, recipe)
    recheck()
    verify_inputs([identity])
    check_cancel(should_cancel)
    return saved
