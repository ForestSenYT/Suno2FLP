"""Installed pure transcription contracts/commands; deliberately no model downloads or imports."""

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-installed", action="store_true")
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.workspace.mkdir(parents=True, exist_ok=False)
    import suno2flp
    from suno2flp.core.transcription_clock import owned_prediction_rows
    from suno2flp.integrations.basic_pitch_backend import load_basic_pitch_pins

    if arguments.require_installed:
        distribution = importlib.metadata.distribution("suno2flp")
        package = Path(suno2flp.__file__).resolve()
        assert package.is_relative_to(Path(distribution.locate_file("")).resolve())
        assert not any(
            str(f).lower().endswith((".onnx", ".whl", ".sf2", ".flp", ".dll"))
            for f in distribution.files or ()
        )
    pins = load_basic_pitch_pins()
    assert len(pins.artifacts) == 42 and len(pins.source_correspondence) == 28
    rows = owned_prediction_rows(175 * 22050)
    assert len(rows) == 15152 and rows[-1].source_sample == 3858728
    assert all(
        name not in sys.modules for name in ("numpy", "onnxruntime", "tensorflow", "basic_pitch")
    )
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for command, expected in [
        (["--help"], 0),
        (
            [
                "verify-basic-pitch",
                str(arguments.workspace / "missing"),
                "--output",
                str(arguments.workspace / "probe"),
            ],
            1,
        ),
    ]:
        completed = subprocess.run(
            [sys.executable, "-m", "suno2flp.cli", *command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
            timeout=30,
        )
        assert completed.returncode == expected, completed.stderr
        if expected == 1:
            assert "Error:" in completed.stderr and not (arguments.workspace / "probe").exists()
    (arguments.workspace / "smoke.json").write_text(
        json.dumps(
            {
                "profile": "pure-transcription-smoke",
                "native_inference": "not_executed",
                "model_qualification": "not_assessed",
                "writer_eligibility": "blocked",
            }
        ),
        encoding="utf-8",
    )
    print(
        "Installed transcription contracts and missing-prerequisite failure passed; "
        "native inference not executed"
    )


if __name__ == "__main__":
    main()
