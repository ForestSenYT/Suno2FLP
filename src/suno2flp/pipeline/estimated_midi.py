"""Export complete current inferred producers as a new, unqualified SMF candidate."""

import os
from importlib.metadata import version
from pathlib import Path

import mido

from suno2flp.arrangement.midi_preview import encode_estimated_midi, project_estimated_midi
from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.estimated_midi import EstimatedMidiExport
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_input,
    capture_stream_input,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.percussion_arrangement import PercussionArrangementInputs
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.validator.midi_preview import verify_estimated_midi
from suno2flp.validator.percussion_arrangement import (
    Cancel,
    check_percussion_location,
    load_percussion_inputs,
    percussion_recipe,
)
from suno2flp.validator.transcription import check_cancel


def midi_preview_recipe() -> ScoringRecipe:
    recipe = percussion_recipe()
    package = Path(__file__).resolve().parent.parent
    paths = [
        package / name
        for name in (
            "core/estimated_midi.py",
            "arrangement/midi_preview.py",
            "validator/midi_preview.py",
            "validator/smf_notes.py",
            "pipeline/estimated_midi.py",
        )
    ]
    paths.extend(sorted(Path(mido.__file__).resolve().parent.rglob("*.py")))
    identities = {i.path: i for i in recipe.files}
    for path in paths:
        identity = capture_stream_input(path)
        identities[identity.path] = identity
    recipe.files = [identities[path] for path in sorted(identities)]
    return recipe


def export_estimated_midi(
    batch_path: Path,
    drums_path: Path,
    output: Path,
    *,
    beats_path: Path | None = None,
    should_cancel: Cancel = None,
) -> EstimatedMidiExport:
    check_cancel(should_cancel)
    early_protected = [batch_path.parent, drums_path.parent]
    if beats_path is not None:
        early_protected.append(beats_path.parent)
    destination = check_percussion_location(output, early_protected)
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Use a new directory with an existing parent")
    source_recipe = percussion_recipe()
    frozen_recipe = midi_preview_recipe().model_dump_json()
    inputs, protected, recheck = load_percussion_inputs(
        batch_path, drums_path, beats_path, source_recipe, should_cancel=should_cancel
    )
    frozen_inputs = inputs.model_dump_json()
    score = project_estimated_midi(build_percussion_arrangement(inputs))
    raw = encode_estimated_midi(score)
    verify_estimated_midi(raw, score)
    check_cancel(should_cancel)
    root = new_model_directory(check_percussion_location(output, protected), protected)
    path = root / "candidate.mid"
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    midi = capture_stream_input(path)
    record = EstimatedMidiExport(
        root=root,
        score=score,
        midi=midi,
        recipe=ScoringRecipe.model_validate_json(frozen_recipe),
        mido_version=version("mido"),
    )
    serialized = record.model_dump_json(indent=2)

    def verify() -> None:
        saved = EstimatedMidiExport.model_validate_json(serialized)
        expected = project_estimated_midi(
            build_percussion_arrangement(
                PercussionArrangementInputs.model_validate_json(frozen_inputs)
            )
        )
        if (
            saved.score != expected
            or saved.midi != midi
            or saved.root != root
            or saved.recipe.model_dump_json() != frozen_recipe
            or saved.recipe != midi_preview_recipe()
            or saved.mido_version != version("mido")
        ):
            raise ValueError("Frozen estimated MIDI source, projection or recipe changed")
        recheck()
        actual, current = capture_input(path)
        if actual != midi:
            raise ValueError("Estimated MIDI changed before completion publication")
        verify_estimated_midi(current, saved.score)
        verify_inputs([midi, saved.recipe.python_executable, *saved.recipe.files])
        check_cancel(should_cancel)

    publish_verified_report(root / "estimated-midi.json", serialized, protected, verify)
    return record


def verify_estimated_midi_export(
    report: Path, *, should_cancel: Cancel = None
) -> EstimatedMidiExport:
    """Reconstruct a saved candidate against every current original producer."""
    check_cancel(should_cancel)
    identity, raw = bounded_snapshot(report, 16 * 1024**2)
    saved = EstimatedMidiExport.model_validate(load_unique_json(raw))
    root = identity.path.parent
    if (
        identity.path.name != "estimated-midi.json"
        or saved.root != root
        or saved.midi.path != root / "candidate.mid"
        or saved.recipe != midi_preview_recipe()
        or saved.mido_version != version("mido")
    ):
        raise ValueError("Use the completed estimated MIDI in its current original directory")
    source = saved.score.arrangement.inputs
    inputs, protected, recheck = load_percussion_inputs(
        source.pitched.batch_report.path,
        source.drums.transcription.path,
        source.pitched.rhythm.report.path if source.pitched.rhythm is not None else None,
        percussion_recipe(),
        should_cancel=should_cancel,
    )
    check_percussion_location(root, protected)
    expected = project_estimated_midi(build_percussion_arrangement(inputs))
    if saved.score != expected:
        raise ValueError("Saved MIDI projection differs from complete current producers")
    midi, current = capture_input(saved.midi.path)
    if midi != saved.midi:
        raise ValueError("Saved MIDI identity changed")
    verify_estimated_midi(current, expected)
    recheck()
    verify_inputs([identity, midi, saved.recipe.python_executable, *saved.recipe.files])
    check_cancel(should_cancel)
    return saved
