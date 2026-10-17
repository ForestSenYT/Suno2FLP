"""Current full numeric lineage once, followed by invocation-owned byte guards."""

from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

from suno2flp.arrangement.midi_preview import project_estimated_midi
from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.estimated_midi import EstimatedMidiExport
from suno2flp.core.offline_files import capture_input, load_unique_json, verify_inputs
from suno2flp.core.offline_models import FileIdentity
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.pipeline.estimated_midi import midi_preview_recipe
from suno2flp.validator.midi_preview import verify_estimated_midi
from suno2flp.validator.percussion_arrangement import (
    Cancel,
    load_percussion_inputs,
    percussion_recipe,
)
from suno2flp.validator.transcription import check_cancel


def load_audio_midi(
    report: Path, should_cancel: Cancel = None
) -> tuple[EstimatedMidiExport, FileIdentity, bytes, list[Path], Callable[[], None]]:
    identity, raw = bounded_snapshot(report, 16 * 1024**2)
    saved = EstimatedMidiExport.model_validate(load_unique_json(raw))
    if (
        identity.path.name != "estimated-midi.json"
        or saved.root != identity.path.parent
        or saved.midi.path != saved.root / "candidate.mid"
        or saved.recipe != midi_preview_recipe()
        or saved.mido_version != version("mido")
    ):
        raise ValueError("Use the current original completed MIDI candidate")
    source = saved.score.arrangement.inputs
    inputs, protected, recheck = load_percussion_inputs(
        source.pitched.batch_report.path,
        source.drums.transcription.path,
        source.pitched.rhythm.report.path if source.pitched.rhythm is not None else None,
        percussion_recipe(),
        should_cancel=should_cancel,
    )
    expected = project_estimated_midi(build_percussion_arrangement(inputs))
    if saved.score != expected:
        raise ValueError("MIDI score differs from complete current producers")
    midi, data = capture_input(saved.midi.path)
    if midi != saved.midi:
        raise ValueError("MIDI identity changed")
    verify_estimated_midi(data, expected)

    def guard() -> None:
        recheck()
        verify_inputs([identity, midi, saved.recipe.python_executable, *saved.recipe.files])
        check_cancel(should_cancel)

    guard()
    return saved, identity, raw, [*protected, saved.root], guard
