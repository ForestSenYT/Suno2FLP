"""Source-bound inferred rhythm candidates; no MIDI or FLP writing."""

from pathlib import Path

from suno2flp.core.beat_analysis import BeatCandidate
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.beat_backend import (
    Cancel,
    call_beat_backend,
    cancelled,
    read_beat_backend,
)
from suno2flp.validator.beat_analysis import beat_derivations, beat_recipe, verify_beat_witnesses
from suno2flp.validator.beat_native import validate_native_beats
from suno2flp.validator.transcription_source import verified_transcription_source


def collect_beats(
    decode_report: Path,
    backend: Path,
    output: Path,
    *,
    should_cancel: Cancel = None,
    protected: list[Path] | None = None,
) -> BeatCandidate:
    cancelled(should_cancel)
    source = verified_transcription_source(decode_report, should_cancel=should_cancel)
    model = read_beat_backend(backend, should_cancel=should_cancel)
    backend_record = capture_stream_input(model.root / "backend.json")
    recipe = beat_recipe()
    root = new_model_directory(
        output,
        [
            model.root,
            *[f.path for f in source.dependencies],
            source.source.path,
            source.pcm.path,
            *[f.path for f in model.artifacts],
            *[f.path for f in recipe.files],
            *(protected or []),
        ],
    )
    attempt = root / "native"
    attempt.mkdir()
    result = call_beat_backend(
        model,
        attempt,
        source.pcm,
        source.frames,
        source.sample_rate,
        source.channels,
        should_cancel=should_cancel,
    )
    _, witnesses = validate_native_beats(
        attempt, result, source.pcm.path, should_cancel=should_cancel
    )
    record = BeatCandidate(
        root=root,
        decode_report=source.decode_report,
        source_audio=source.source,
        pcm=source.pcm,
        decode_dependencies=source.dependencies,
        decoder_payload_root=source.decoder_payload_root,
        backend_record=backend_record,
        backend=model,
        recipe=recipe,
        native=result,
        native_witnesses=witnesses,
        beat_peaks=[],
        downbeat_peaks=[],
        beats=[],
        raw_downbeats=[],
        downbeat_to_beat=[],
        downbeats=[],
        signal_observations=[],
    )
    return BeatCandidate.model_validate(
        {**record.model_dump(), **beat_derivations(record, should_cancel=should_cancel)}
    )


def analyze_beats(
    decode_report: Path,
    backend: Path,
    output: Path,
    *,
    should_cancel: Cancel = None,
) -> BeatCandidate:
    record = collect_beats(decode_report, backend, output, should_cancel=should_cancel)
    publish_verified_report(
        record.root / "beats.json",
        record.model_dump_json(indent=2),
        [
            record.decode_report.path,
            record.source_audio.path,
            record.pcm.path,
            record.backend_record.path,
        ],
        lambda: verify_beat_witnesses(record, should_cancel=should_cancel),
    )
    return record
