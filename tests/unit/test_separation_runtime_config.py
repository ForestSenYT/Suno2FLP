"""Authored metadata/configuration; no native runtime or musical qualification."""

import pytest
from test_separation_contracts import candidate_values, identity

from suno2flp.core.separation import (
    KerasRuntimeSettings,
    SeparationCandidate,
    SeparationRuntimeContext,
)

SETTINGS = dict(
    floatx="float32", epsilon=1e-7, backend="tensorflow", image_data_format="channels_last"
)
V2 = "source-bound-spleeter-four-stem-candidate-v2"


def context(root):
    return SeparationRuntimeContext(
        file=identity(root, "keras-cache/keras.json", 120, "a"),
        settings=KerasRuntimeSettings(**SETTINGS),
    )


def test_legacy_metadata_remains_distinct_from_complete_runtime_context(tmp_path):
    values = candidate_values(tmp_path)
    old = SeparationCandidate(**values)
    assert old.schema_version == 1 and old.runtime_context is None
    current = SeparationCandidate(
        **values, schema_version=2, profile=V2, runtime_context=context(tmp_path)
    )
    assert current.runtime_context.file in current.witnesses()
    assert current.writer_eligibility == "blocked" and not current.execution_allowed


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"profile": V2},
        {"schema_version": 2, "with_context": True},
        {"profile": V2, "with_context": True},
        {"schema_version": 2, "profile": V2},
        {"with_context": True},
        {"schema_version": 2, "profile": V2, "foreign": True},
        {"schema_version": 2, "profile": V2, "oversized": True},
    ],
)
def test_mixed_versions_missing_or_foreign_context_are_rejected(tmp_path, change):
    values = candidate_values(tmp_path)
    update = dict(change)
    foreign, oversized = update.pop("foreign", False), update.pop("oversized", False)
    if update.pop("with_context", False) or foreign or oversized:
        item = context(tmp_path / "foreign" if foreign else tmp_path)
        if oversized:
            item.file.size_bytes = 65537
        update["runtime_context"] = item
    with pytest.raises(ValueError):
        SeparationCandidate(**values, **update)


@pytest.mark.parametrize(
    "field,value",
    [
        ("floatx", "float64"),
        ("epsilon", 1e-6),
        ("epsilon", "1e-7"),
        ("epsilon", True),
        ("epsilon", float("nan")),
        ("backend", "torch"),
        ("image_data_format", "channels_first"),
        ("extra", "unknown"),
    ],
)
def test_unsupported_settings_are_not_defaults(field, value):
    with pytest.raises(ValueError):
        KerasRuntimeSettings(**{**SETTINGS, field: value})


def test_missing_setting_is_rejected():
    with pytest.raises(ValueError):
        KerasRuntimeSettings(**{k: v for k, v in SETTINGS.items() if k != "epsilon"})


def test_separation_recipe_binds_complete_membership_implementation():
    from suno2flp.validator.separation import separation_recipe

    recipe = separation_recipe()
    assert any(i.path.as_posix().endswith("core/inference_snapshot.py") for i in recipe.files)
