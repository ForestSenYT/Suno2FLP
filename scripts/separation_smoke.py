"""Installed separation contracts and prerequisite failures, with no native model import."""

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
    root = arguments.workspace
    root.mkdir(parents=True, exist_ok=False)
    import suno2flp
    from suno2flp.core.separation_probe import fixture_bytes
    from suno2flp.integrations.spleeter_backend import load_spleeter_pins

    if arguments.require_installed:
        distribution = importlib.metadata.distribution("suno2flp")
        direct = json.loads(distribution.read_text("direct_url.json") or "{}")
        assert not direct.get("dir_info", {}).get("editable", False)
        assert (
            Path(suno2flp.__file__).resolve()
            == Path(distribution.locate_file("suno2flp/__init__.py")).resolve()
        )
    pins = load_spleeter_pins()
    assert len(pins.artifacts) == 50 and len(pins.model_members) == 5
    assert len(fixture_bytes("impulses")) == 12347 * 8
    assert all(name not in sys.modules for name in ("numpy", "tensorflow", "spleeter", "pandas"))
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for command, expected in (
        (["--help"], 0),
        (["verify-spleeter", str(root / "missing"), "--output", str(root / "probe")], 1),
        (["prepare-spleeter", "--artifacts", str(root), "--output", str(root)], 1),
        (
            [
                "separate-audio",
                str(root / "missing.json"),
                str(root / "backend"),
                "--output",
                str(root / "candidate"),
            ],
            1,
        ),
        (
            [
                "verify-separation",
                str(root / "missing.json"),
                "--replay-output",
                str(root / "replay"),
            ],
            1,
        ),
    ):
        result = subprocess.run(
            [sys.executable, "-m", "suno2flp.cli", *command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert result.returncode == expected, result.stderr
        if expected == 1:
            assert "Error:" in result.stderr and not (root / "probe").exists()
            assert not (root / "candidate").exists() and not (root / "replay").exists()
    assert all(name not in sys.modules for name in ("numpy", "tensorflow", "spleeter", "pandas"))
    (root / "smoke.json").write_text(
        json.dumps(
            {
                "profile": "pure-separation-runtime-smoke",
                "native_inference": "not_executed",
                "model_qualification": "not_assessed",
                "execution_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    print("Separation contracts and explicit prerequisites passed; native model not executed")


if __name__ == "__main__":
    main()
