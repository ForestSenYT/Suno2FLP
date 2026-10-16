"""Apply/verify an original recipe only inside a newly provisioned external checkout."""

import hashlib
from pathlib import Path

from suno2flp.core import backend_adaptation as recipe
from suno2flp.core.backend_models import BackendProvisionRecord, BackendReadAdaptation

ADAPTATION_FILES = {recipe.PARSER_PATH, recipe.BASELINE_PATH, recipe.NOTICE_PATH}


def apply_read_adaptation(root: Path) -> BackendReadAdaptation:
    source = root / recipe.PARSER_PATH
    original = source.read_bytes()
    adapted = recipe.adapt_parser_bytes(original)
    for name, raw in ((recipe.BASELINE_PATH, original), (recipe.NOTICE_PATH, recipe.NOTICE)):
        with (root / name).open("xb") as stream:
            stream.write(raw)
    source.write_bytes(adapted)
    return BackendReadAdaptation(
        profile=recipe.PROFILE,
        upstream_source_sha256=hashlib.sha256(original).hexdigest(),
        adapted_source_sha256=hashlib.sha256(adapted).hexdigest(),
        recipe_sha256=recipe.RECIPE_SHA256,
    )


def verify_read_adaptation(root: Path, record: BackendProvisionRecord) -> None:
    adaptation = record.adaptation
    if adaptation is None:
        if any((root / name).exists() for name in (recipe.BASELINE_PATH, recipe.NOTICE_PATH)):
            raise ValueError("Adapted installation is missing its adaptation declaration")
        return
    if not ADAPTATION_FILES.issubset(record.files):
        raise ValueError("Adapted source, original baseline and modification notice are required")
    original = (root / recipe.BASELINE_PATH).read_bytes()
    adapted = recipe.adapt_parser_bytes(original)
    if (
        adaptation.upstream_source_sha256 != recipe.UPSTREAM_PARSER_SHA256
        or adaptation.recipe_sha256 != recipe.RECIPE_SHA256
        or adaptation.adapted_source_sha256 != hashlib.sha256(adapted).hexdigest()
        or (root / recipe.PARSER_PATH).read_bytes() != adapted
        or (root / recipe.NOTICE_PATH).read_bytes() != recipe.NOTICE
    ):
        raise ValueError("Adaptation differs from the exact assessed source/recipe")
