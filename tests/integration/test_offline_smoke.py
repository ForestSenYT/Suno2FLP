import json
import subprocess
import sys
from pathlib import Path


def test_smoke_script_exercises_workflow_and_refuses_reuse(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/offline_smoke.py"
    root = tmp_path / "fresh-smoke"
    args = [sys.executable, str(script), "--workspace", str(root)]
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["workflow"] == "passed" and report["negative_checks"] == "passed"
    assert report["original_inputs_unchanged"] and not report["flp_created"]
    assert report["performance_replay"] == "passed"
    assert report["performance_negative_checks"] == "passed"
    assert report["encoding_assessment_replay"] == "passed"
    assert report["midi_comparison_replay"] == "passed"
    assert report["host_compatibility"] == "unverified"
    again = subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert again.returncode != 0
