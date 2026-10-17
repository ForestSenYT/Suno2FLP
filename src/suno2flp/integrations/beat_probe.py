"""Actual bounded repeated private inference and independent complete readback."""

from pathlib import Path

from suno2flp.core.beat_native import BeatFixtureEvidence, NativeBeatResult
from suno2flp.core.beat_probe import BEAT_FIXTURES, BeatRuntimeProbe, beat_fixture_wave
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import capture_stream_input, verify_inputs
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.beat_backend import (
    Cancel,
    call_beat_backend,
    cancelled,
    read_beat_backend,
    verify_beat_request,
)
from suno2flp.validator.beat_native import validate_native_beats


def probe_beat_backend(
    root: Path, output: Path, *, should_cancel: Cancel = None
) -> BeatRuntimeProbe:
    import platform
    import sys

    import pydantic

    package = Path(__file__).parent.parent
    recipe = ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable).resolve()),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[
            capture_stream_input(package / n)
            for n in (
                "core/beat_probe.py",
                "core/note_scoring.py",
                "core/models.py",
                "core/offline_models.py",
                "integrations/beat_probe.py",
                "validator/beat_native.py",
                "validator/beat_postprocessing.py",
                "core/report_publication.py",
            )
        ],
    )
    backend = read_beat_backend(root, should_cancel=should_cancel)
    record = capture_stream_input(backend.root / "backend.json")
    target = new_model_directory(output, [backend.root, *[p.path for p in backend.artifacts]])
    fixtures = []
    for name, (frames, rate, channels) in BEAT_FIXTURES.items():
        cancelled(should_cancel)
        path = target / f"{name}.wav"
        with path.open("xb") as stream:
            stream.write(beat_fixture_wave(name))
        source = capture_stream_input(path)
        results: list[NativeBeatResult] = []
        attempts = []
        witnesses = [source]
        for index in range(2):
            attempt = target / f"{name}-{index}"
            attempt.mkdir()
            result = call_beat_backend(
                backend, attempt, source, frames, rate, channels, should_cancel=should_cancel
            )
            _, evidence = validate_native_beats(
                attempt, result, source.path, should_cancel=should_cancel
            )
            witnesses.extend(evidence)
            results.append(result)
            attempts.append(attempt)
        if results[0].files != results[1].files:
            raise ValueError(f"Repeated complete rhythm outputs differ: {name}")
        fixtures.append(
            BeatFixtureEvidence(
                fixture=name, source=source, attempts=attempts, results=results, witnesses=witnesses
            )
        )
    report = BeatRuntimeProbe(
        backend_record=record, backend=backend, fixtures=fixtures, recipe=recipe
    )

    def verify() -> None:
        cancelled(should_cancel)
        verify_inputs([recipe.python_executable, *recipe.files])
        verify_inputs([record, *[i for f in fixtures for i in f.witnesses]])
        for fixture in fixtures:
            if fixture.source.path.read_bytes() != beat_fixture_wave(fixture.fixture):
                raise ValueError("Original probe fixture changed")
            for attempt, result in zip(fixture.attempts, fixture.results, strict=True):
                verify_beat_request(
                    backend,
                    attempt,
                    fixture.source,
                    result.frames,
                    result.sample_rate,
                    result.channels,
                )
                validate_native_beats(
                    attempt, result, fixture.source.path, should_cancel=should_cancel
                )
        if backend != read_beat_backend(backend.root, should_cancel=should_cancel):
            raise ValueError("Beat backend changed before probe publication")
        cancelled(should_cancel)

    publish_verified_report(
        target / "probe.json", report.model_dump_json(indent=2), [record.path], verify
    )
    return report
