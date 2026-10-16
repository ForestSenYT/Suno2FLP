"""Independent faithful arrangement replay from current original MIDI files."""

from pathlib import Path

from suno2flp.arrangement import ExplicitInstrumentMapper, FaithfulArrangementEngine
from suno2flp.core.config import MidiPreferences
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.instrument_config import load_instrument_mapping
from suno2flp.core.models import Arrangement, Diagnostic, ProcessedMidi
from suno2flp.core.offline_files import capture_input, load_unique_json, verify_inputs
from suno2flp.core.offline_models import ArrangementQualityReport
from suno2flp.importer import MidiFileImporter
from suno2flp.midi_processor import DeterministicMidiProcessor


def audit_arrangement(
    arrangement: Arrangement,
    original_imports: list[ProcessedMidi],
) -> ArrangementQualityReport:
    result = ArrangementQualityReport(
        source_count=len(arrangement.sources),
        track_count=len(arrangement.tracks),
        note_count=sum(len(track.notes) for track in arrangement.tracks),
        event_count=sum(
            len(track.events) for source in original_imports for track in source.tracks
        ),
        arrangement_fingerprint=snapshot_sha256(arrangement),
    )

    def error(code: str, message: str) -> None:
        result.diagnostics.append(Diagnostic(code=code, severity="error", message=message))

    if (
        arrangement.mode != "faithful"
        or not arrangement.sources
        or arrangement.build_options is None
        or len(arrangement.sources) != len(original_imports)
    ):
        error(
            "arrangement_provenance_missing", "Faithful sources and explicit build options required"
        )
        return result
    selected = []
    try:
        for index, (source, original) in enumerate(
            zip(arrangement.sources, original_imports, strict=True)
        ):
            current = original
            if source.midi.cleanup is not None:
                current = DeterministicMidiProcessor().clean(
                    original,
                    MidiPreferences.model_validate(source.midi.cleanup.options.model_dump()),
                )
            if source.input_index != index or current != source.midi:
                error(
                    "source_replay_mismatch", f"Source {index} differs from current original replay"
                )
            selected.append(current)
        rebuilt = FaithfulArrangementEngine().arrange(
            selected,
            arrangement.metadata,
            "faithful",
            options=arrangement.build_options,
        )
        if arrangement.instrument_mapping is not None:
            rebuilt = ExplicitInstrumentMapper().apply(
                rebuilt, arrangement.instrument_mapping.document
            )
        result.reference_fingerprint = snapshot_sha256(rebuilt)
        if rebuilt != arrangement:
            error(
                "arrangement_replay_mismatch", "Music, maps, roles or provenance differ from replay"
            )
    except (Suno2FLPError, ValueError) as exc:
        error("arrangement_replay_failed", str(exc))
    result.valid = not result.diagnostics
    return result


def verify_arrangement_file(path: Path) -> ArrangementQualityReport:
    result = ArrangementQualityReport(referenced_paths=[path.absolute()])
    files = []
    references = [path.absolute()]
    try:
        identity, raw = capture_input(path)
        files.append(identity)
        arrangement = Arrangement.model_validate(load_unique_json(raw))
        originals = []
        for source in arrangement.sources:
            references.append(source.midi.source.absolute())
            source_identity, _ = capture_input(source.midi.source)
            files.append(source_identity)
            original = MidiFileImporter().import_file(source.midi.source)
            if original.source_sha256 != source_identity.sha256:
                raise ValueError("Original MIDI changed during reimport")
            originals.append(original)
        if arrangement.instrument_mapping is not None:
            document = arrangement.instrument_mapping.document
            if document.source_path is not None:
                references.append(document.source_path.absolute())
                mapping_identity, _ = capture_input(document.source_path)
                files.append(mapping_identity)
                if load_instrument_mapping(document.source_path) != document:
                    raise ValueError("Current role mapping differs from recorded mapping")
        result = audit_arrangement(arrangement, originals)
    except (OSError, RuntimeError, ValueError, Suno2FLPError) as exc:
        result.valid = False
        result.diagnostics.append(
            Diagnostic(code="arrangement_input_invalid", severity="error", message=str(exc))
        )
    result.input_files = files
    result.referenced_paths = references
    try:
        verify_inputs(files)
    except (OSError, RuntimeError, ValueError, Suno2FLPError) as exc:
        result.valid = False
        result.diagnostics.append(
            Diagnostic(code="arrangement_input_changed", severity="error", message=str(exc))
        )
    return result
