"""Current-byte guards after full numeric validation within the owning invocation.

These guards neither establish numeric relationships nor accept serialized trust.
They preserve already checked relationships by checking every exact input byte and
complete current payload membership again at consumption/publication boundaries.
"""

import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pydantic

from suno2flp.core.inference_snapshot import InferenceSnapshot
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.separation import SeparationCandidate
from suno2flp.core.stem_transcription import StemTranscriptionCandidate


@dataclass(frozen=True, slots=True)
class StemEvidence:
    _files: InferenceSnapshot
    _runtime: tuple[Path, str, str]

    def _check_recipes(self) -> None:
        # Recipe files are already among the exact immutable file witnesses.
        # Recheck runtime metadata here without hashing those same files twice.
        if self._runtime != (
            Path(sys.executable).resolve(),
            platform.python_version(),
            pydantic.__version__,
        ):
            raise ValueError("Current inference runtime changed after numeric validation")

    def recheck(self, *, should_cancel: Callable[[], bool] | None = None) -> None:
        self._check_recipes()
        self._files.recheck(should_cancel=should_cancel)


def capture_stem_evidence(
    original: SeparationCandidate,
    replay: SeparationCandidate,
    candidates: list[StemTranscriptionCandidate],
    *,
    recipe: ScoringRecipe,
    pitch_recipe: ScoringRecipe,
    identities: list[FileIdentity],
    should_cancel: Callable[[], bool] | None = None,
) -> StemEvidence:
    """Caller must already own full validated reports, never just a receipt boolean."""
    files = list(identities)
    payloads = []
    byte_limits: dict[Path, int] = {}
    if original.recipe != replay.recipe:
        raise ValueError("Separation numeric proof recipes differ")
    for report in (original, replay):
        files.extend(report.witnesses())
        payloads.append((report.backend.root / "packages", report.model_dependencies))
        if report.runtime_context is not None:
            native, members = report.native_result.path.parent, report.native_witnesses()
            payloads.append((native, members))
            byte_limits[native] = max(1, sum(i.size_bytes for i in members))
        if report.decoder_payload_root is not None:
            root = report.decoder_payload_root
            payloads.append(
                (root, [i for i in report.decode_dependencies if i.path.is_relative_to(root)])
            )
    for candidate in candidates:
        if candidate.recipe != pitch_recipe or candidate.source.recipe != recipe:
            raise ValueError("Candidate proof differs from the invocation's initial recipes")
        files.extend(candidate.pitch_witnesses())
        files.extend(
            [
                candidate.source.separation_report,
                candidate.source.separation_replay,
                candidate.source.replay_report,
                candidate.source.estimated_audio,
                candidate.source.original_audio,
                candidate.source.original_decode,
            ]
        )
        payloads.append((candidate.backend.root / "packages", candidate.model_dependencies))
    for declaration in (recipe, pitch_recipe):
        files.extend([declaration.python_executable, *declaration.files])
    runtimes = {
        (r.python_executable.path, r.python_version, r.pydantic_version)
        for r in (recipe, pitch_recipe, original.recipe)
    }
    if len(runtimes) != 1:
        raise ValueError("Numeric proof runtime declarations differ")
    guard = StemEvidence(
        InferenceSnapshot.capture(
            files, payloads, payload_byte_limits=byte_limits, should_cancel=should_cancel
        ),
        next(iter(runtimes)),
    )
    guard._check_recipes()
    return guard
