"""Actual selected encoder probes with complete independently checked stereo means."""

import math
import struct
from pathlib import Path

from suno2flp.core.drum_native import (
    DrumFixtureEvidence,
    DrumFixtureName,
    DrumProbe,
    NativeDrumResult,
)
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import capture_stream_input, verify_inputs
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.beat_backend import Cancel, cancelled
from suno2flp.integrations.drum_backend import call_drum_backend, read_drum_backend


def verify_drum_mono(pcm: FileIdentity, mono: FileIdentity, frames: int) -> None:
    """Oracle uses exact serialized f32 input pairs, not pre-rounding fixture literals."""
    if (pcm.size_bytes, mono.size_bytes) != (frames * 8, frames * 4):
        raise ValueError("Drum source/mono lengths changed")
    with pcm.path.open("rb") as source, mono.path.open("rb") as output:
        for _ in range(frames):
            left, right = struct.unpack("<ff", source.read(8))
            if not math.isfinite(left) or not math.isfinite(right):
                raise ValueError("Nonfinite drum source")
            expected = struct.pack("<f", (left + right) * 0.5)
            if output.read(4) != expected:
                raise ValueError(
                    "Drum mono differs from the independent pair-sum-f64-half-f32 oracle"
                )
        if source.read(1) or output.read(1):
            raise ValueError("Drum source/mono has undeclared tail bytes")
    verify_inputs([pcm, mono])


def probe_drum_backend(root: Path, output: Path, *, should_cancel: Cancel = None) -> DrumProbe:
    cancelled(should_cancel)
    backend = read_drum_backend(root, should_cancel=should_cancel)
    backend_record = capture_stream_input(backend.root / "backend.json")
    out = new_model_directory(output, [backend.root, *[i.path for i in backend.artifacts]])
    fixtures = []
    specifications: tuple[tuple[DrumFixtureName, int], ...] = (
        ("signed-pair-1025", 1025),
        ("stereo-tone-tail-44117", 44117),
    )
    for label, n in specifications:
        cancelled(should_cancel)
        directory = out / label
        directory.mkdir()
        pcm = directory / "source-stereo.f32"
        with pcm.open("xb") as stream:
            for j in range(n):
                if label == "signed-pair-1025":
                    left, right = (-0.0, -0.0) if j < 16 else (0.0, 0.0)
                    if j == 700:
                        left, right = 1.0, -0.5
                else:
                    left = 0.3 * math.sin(2 * math.pi * 220 * j / 44100)
                    right = 0.2 * math.sin(2 * math.pi * 330 * j / 44100)
                stream.write(struct.pack("<ff", left, right))
        source = capture_stream_input(pcm)
        attempts = []
        results: list[NativeDrumResult] = []
        for repeat in range(2):
            attempt = directory / f"attempt-{repeat}"
            attempt.mkdir()
            result = call_drum_backend(backend, attempt, source, n, should_cancel=should_cancel)
            mono = capture_stream_input(attempt / "mono.f32")
            verify_drum_mono(source, mono, n)
            attempts.append(attempt)
            results.append(result)
        if results[0].files != results[1].files:
            raise ValueError("Complete drum raw arrays differ across actual repeats")
        witnesses = capture_file_tree(directory, should_cancel=should_cancel)
        fixtures.append(
            DrumFixtureEvidence(
                fixture=label,
                source=source,
                model_frames=n,
                attempts=attempts,
                results=results,
                witnesses=witnesses,
            )
        )
    report = DrumProbe(root=out, backend_record=backend_record, backend=backend, fixtures=fixtures)

    def verify() -> None:
        cancelled(should_cancel)
        verify_inputs([backend_record, *[i for f in fixtures for i in f.witnesses]])
        if read_drum_backend(backend.root, should_cancel=should_cancel) != backend:
            raise ValueError("Drum backend changed during actual probes")
        for fixture in fixtures:
            expected = {i.path: i for i in fixture.witnesses}
            actual = {
                i.path: i
                for i in capture_file_tree(fixture.source.path.parent, should_cancel=should_cancel)
            }
            if expected != actual:
                raise ValueError("Complete drum probe membership changed")
        cancelled(should_cancel)

    publish_verified_report(
        out / "probe.json",
        report.model_dump_json(indent=2),
        [backend.root, *[i.path for i in backend.artifacts]],
        verify,
    )
    return report
