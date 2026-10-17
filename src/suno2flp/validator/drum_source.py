"""Full current source numeric validation, followed by invocation-local immutable guards."""

from dataclasses import dataclass
from pathlib import Path

from suno2flp.core.drum_transcription import DrumSource
from suno2flp.core.inference_snapshot import InferenceSnapshot
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import capture_stream_input, load_unique_json
from suno2flp.core.separation import SeparationReplayReceipt
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.beat_backend import Cancel, cancelled
from suno2flp.validator.stem_transcription import read_lineage


@dataclass(frozen=True, slots=True)
class DrumSourceEvidence:
    """Internal owned proof; never reconstructed from a saved receipt or caller JSON."""

    source_json: str
    recipe_json: str
    guard: InferenceSnapshot

    def source(self) -> DrumSource:
        return DrumSource.model_validate_json(self.source_json)

    def recheck(self, recipe: ScoringRecipe, *, should_cancel: Cancel = None) -> None:
        cancelled(should_cancel)
        if recipe.model_dump_json() != self.recipe_json:
            raise ValueError("Current drum consumer recipe changed")
        self.guard.recheck(should_cancel=should_cancel)


def load_drum_source(
    separation: Path,
    receipt: Path,
    recipe: ScoringRecipe,
    *,
    should_cancel: Cancel = None,
) -> DrumSourceEvidence:
    cancelled(should_cancel)
    separation_id = capture_stream_input(separation)
    receipt_id, raw = bounded_snapshot(receipt, 1024**2)
    declared = SeparationReplayReceipt.model_validate(load_unique_json(raw))
    # Do not use metadata-only lineage matching or the receipt's boolean as numeric authority.
    original, replay = read_lineage(separation_id, receipt_id, should_cancel=should_cancel)
    source = DrumSource(
        separation_report=separation_id,
        separation_replay=receipt_id,
        receipt=declared,
        original=original,
        replay=replay,
        model_pcm=next(s.model for s in original.stems if s.stem == "drums"),
    )
    files = [*source.witnesses(), recipe.python_executable, *recipe.files]
    payloads = []
    for report in (original, replay):
        payloads.append((report.backend.root / "packages", report.model_dependencies))
        if report.decoder_payload_root is not None:
            root = report.decoder_payload_root
            payloads.append(
                (root, [i for i in report.decode_dependencies if i.path.is_relative_to(root)])
            )
    proof = DrumSourceEvidence(
        source.model_dump_json(),
        recipe.model_dump_json(),
        InferenceSnapshot.capture(files, payloads, should_cancel=should_cancel),
    )
    proof.recheck(recipe, should_cancel=should_cancel)
    return proof
