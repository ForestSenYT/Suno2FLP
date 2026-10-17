"""Exclusively publish a source-bound estimated composition, never MIDI or FLP."""

from pathlib import Path

from suno2flp.arrangement.inferred import build_estimated_arrangement
from suno2flp.core.estimated_arrangement import EstimatedArrangement, EstimatedArrangementInputs
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.validator.estimated_arrangement import (
    Cancel,
    estimated_recipe,
    load_estimated_inputs,
    validate_estimated_snapshot,
)
from suno2flp.validator.transcription import check_cancel


def compose_estimated_arrangement(
    batch_path: Path,
    output: Path,
    *,
    beats_path: Path | None = None,
    should_cancel: Cancel = None,
) -> EstimatedArrangement:
    check_cancel(should_cancel)
    recipe = estimated_recipe()
    frozen_recipe = recipe.model_dump_json()
    inputs, protected, recheck = load_estimated_inputs(
        batch_path,
        beats_path,
        recipe,
        should_cancel=should_cancel,
    )
    frozen_inputs = inputs.model_dump_json()
    record = build_estimated_arrangement(inputs)
    root = new_model_directory(output, protected)
    record.root, record.recipe = root, ScoringRecipe.model_validate_json(frozen_recipe)
    serialized = record.model_dump_json(indent=2)

    def verify() -> None:
        validate_estimated_snapshot(
            EstimatedArrangement.model_validate_json(serialized),
            EstimatedArrangementInputs.model_validate_json(frozen_inputs),
            root,
            ScoringRecipe.model_validate_json(frozen_recipe),
        )
        recheck()
        check_cancel(should_cancel)

    publish_verified_report(root / "estimated-arrangement.json", serialized, protected, verify)
    return record
