"""Installed-wheel scoring with original fixtures, not a musical benchmark."""

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import suno2flp
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.importer.pcm_decode import decode_pcm_wave


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--require-installed", action="store_true")
    args = parser.parse_args()
    distribution = importlib.metadata.distribution("suno2flp")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    installed = (
        not direct.get("dir_info", {}).get("editable", False)
        and any(str(item) == "suno2flp/__init__.py" for item in distribution.files or [])
        and Path(distribution.locate_file("suno2flp/__init__.py")).resolve()
        == Path(suno2flp.__file__).resolve()
    )
    if args.require_installed and not installed:
        raise RuntimeError("Expected the installed wheel, not the checkout")
    root = args.workspace.absolute()
    root.mkdir(parents=True, exist_ok=False)
    audio = root / "合成 source.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x01\x00" * 16000)
    source_before = capture_stream_input(audio)
    decode = decode_pcm_wave(audio, root / "decode")
    producer = root / "producer.txt"
    producer.write_text("Original synthetic annotation; not a trained model or release corpus.")
    base = {
        "origin": "synthetic_fixture",
        "method": "installed-wheel synthetic check",
        "provenance_files": [capture_stream_input(producer).model_dump(mode="json")],
        "decode_report": capture_stream_input(root / "decode/decode.json").model_dump(mode="json"),
        "source_audio": decode.preflight.source.model_dump(mode="json"),
        "sample_rate": 8000,
        "channels": 1,
        "frames": 16000,
    }

    def note(identifier: str) -> dict[str, object]:
        return {
            "id": identifier,
            "pitch": 60,
            "onset_microseconds": {"numerator": 0, "denominator": 1},
            "offset_microseconds": {"numerator": 1_000_000, "denominator": 1},
        }

    for role, notes in [("reference", [note("r")]), ("candidate", [note("c1"), note("c2")])]:
        (root / f"{role}.json").write_text(
            json.dumps(base | {"role": role, "notes": notes}), encoding="utf-8"
        )

    def command(arguments: list[str], expected: int) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, "-m", "suno2flp.cli", *arguments],
            capture_output=True,
            timeout=60,
            text=True,
            encoding="utf-8",
            env=os.environ | {"PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode != expected:
            raise RuntimeError(f"CLI failed: {result.returncode}: {result.stderr!r}")
        return json.loads(result.stdout)

    report = root / "measured.json"
    data = command(
        [
            "score-pitched-notes",
            str(root / "candidate.json"),
            "--reference",
            str(root / "reference.json"),
            "--output",
            str(report),
        ],
        0,
    )
    assert data["result"]["f1"] == {"numerator": 2, "denominator": 3}
    identity = capture_stream_input(report)
    assert command(["verify-note-score", str(report)], 0) == data
    assert capture_stream_input(report) == identity
    missing = command(
        [
            "score-pitched-notes",
            str(root / "candidate.json"),
            "--output",
            str(root / "unavailable.json"),
        ],
        3,
    )
    assert missing["result"]["f1"] is None and missing["writer_eligibility"] == "blocked"
    # Alter only newly authored smoke metadata; never touch a private baseline.
    producer.write_text("changed producer evidence")
    failed = subprocess.run(
        [sys.executable, "-m", "suno2flp.cli", "verify-note-score", str(report)],
        capture_output=True,
        timeout=60,
    )
    assert failed.returncode == 1 and capture_stream_input(report) == identity
    assert capture_stream_input(audio) == source_before
    print(
        "Installed note scoring: exact F1, duplicates, replay, unavailable truth, "
        "tamper refusal passed."
    )


if __name__ == "__main__":
    main()
