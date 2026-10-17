"""Reconstruction rejects individual coherent metadata edits without expensive I/O."""

import pytest
from test_percussion_arrangement import inputs

from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.validator.percussion_arrangement import (
    percussion_recipe,
    validate_percussion_snapshot,
)


@pytest.mark.parametrize("changed", ["blockers", "root", "recipe", "role", "model-pcm"])
def test_complete_snapshot_comparison_rejects_each_changed_field(tmp_path, changed):
    source = inputs()
    recipe = percussion_recipe()
    root = tmp_path / "new"
    record = build_percussion_arrangement(source)
    record.root = root
    record.recipe = ScoringRecipe.model_validate_json(recipe.model_dump_json())
    validate_percussion_snapshot(record, source, root, recipe)
    if changed == "blockers":
        record.blockers.clear()
    elif changed == "root":
        record.root = tmp_path / "other"
    elif changed == "recipe":
        record.recipe.files.pop()
    elif changed == "role":
        record.parts[1].role = "bass"
    else:
        record.inputs.drums.model_pcm.sha256 = "0" * 64
    with pytest.raises(ValueError, match="complete current source derivation"):
        validate_percussion_snapshot(record, source, root, recipe)
