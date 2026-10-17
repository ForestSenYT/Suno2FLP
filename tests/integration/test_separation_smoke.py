"""The packaging smoke exercises real CLI failures and never loads a native model."""

import json
import subprocess
import sys
from pathlib import Path


def test_separation_smoke(tmp_path: Path) -> None:
    script = Path(__file__).parents[2] / "scripts/separation_smoke.py"
    workspace = tmp_path / "smoke"
    result = subprocess.run(
        [sys.executable, str(script), "--workspace", str(workspace)],
        capture_output=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((workspace / "smoke.json").read_text())
    assert report["native_inference"] == "not_executed" and not report["execution_allowed"]
