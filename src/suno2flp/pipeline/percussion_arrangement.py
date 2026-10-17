"""Exclusively publish source-bound percussion arrangements; no MIDI/FLP writes."""

from pathlib import Path

from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.percussion_arrangement import (
    PercussionArrangement,
    PercussionArrangementInputs,
)
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.validator.percussion_arrangement import (
    Cancel,
    check_percussion_location,
    load_percussion_inputs,
    percussion_recipe,
    validate_percussion_snapshot,
)
from suno2flp.validator.transcription import check_cancel


def compose_percussion_arrangement(
    batch_path: Path,
    drums_path: Path,
    output: Path,
    *,
    beats_path: Path | None = None,
    should_cancel: Cancel = None,
) -> PercussionArrangement:
    check_cancel(should_cancel)
    recipe = percussion_recipe()
    frozen_recipe = recipe.model_dump_json()
    inputs, protected, recheck = load_percussion_inputs(
        batch_path, drums_path, beats_path, recipe, should_cancel=should_cancel
    )
    frozen_inputs = inputs.model_dump_json()
    root = new_model_directory(check_percussion_location(output, protected), protected)
    record = build_percussion_arrangement(inputs)
    record.root, record.recipe = root, ScoringRecipe.model_validate_json(frozen_recipe)
    serialized = record.model_dump_json(indent=2)

    def verify() -> None:
        validate_percussion_snapshot(
            PercussionArrangement.model_validate_json(serialized),
            PercussionArrangementInputs.model_validate_json(frozen_inputs),
            root,
            ScoringRecipe.model_validate_json(frozen_recipe),
        )
        recheck()
        check_cancel(should_cancel)

    publish_verified_report(root / "percussion-arrangement.json", serialized, protected, verify)
    return record
