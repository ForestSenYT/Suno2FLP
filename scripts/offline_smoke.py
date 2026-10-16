"""Original synthetic CLI lifecycle; CI also runs this against the installed wheel."""

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import wave
from pathlib import Path

import mido

import suno2flp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--require-installed", action="store_true")
    args = parser.parse_args()
    module_path = Path(suno2flp.__file__).resolve()
    distribution = importlib.metadata.distribution("suno2flp")
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    installed = (
        not direct_url.get("dir_info", {}).get("editable", False)
        and any(str(item) == "suno2flp/__init__.py" for item in distribution.files or [])
        and Path(distribution.locate_file("suno2flp/__init__.py")).resolve() == module_path
    )
    if args.require_installed and not installed:
        raise RuntimeError(f"Expected installed wheel, got {module_path}")
    root = args.workspace.absolute()
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(exist_ok=False)

    def cli(*values, expected=0):
        result = subprocess.run(
            [sys.executable, "-m", "suno2flp.cli", *(str(value) for value in values)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != expected:
            raise RuntimeError(
                f"CLI {values} returned {result.returncode}: {result.stdout} {result.stderr}"
            )
        return result.stdout

    cli("--help")
    cli("init-project", "song", "--directory", root)
    project = root / "song"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks = [
        mido.MidiTrack(
            [
                mido.MetaMessage("set_tempo", tempo=500000),
                mido.MetaMessage("set_tempo", tempo=600000, time=240),
                mido.MetaMessage("end_of_track"),
            ]
        ),
        mido.MidiTrack(
            [
                mido.Message("program_change", channel=2, program=0),
                mido.Message("note_on", channel=2, note=60, velocity=90, time=120),
                mido.Message("note_off", channel=2, note=60, velocity=30, time=240),
                mido.Message("control_change", channel=2, control=7, value=100, time=120),
                mido.MetaMessage("end_of_track"),
            ]
        ),
    ]
    midi.save(project / "input/song.mid")
    for name, raw in (("song.wav", b"\0\0" * 2), ("other.wav", b"\0\x40\0\xc0")):
        with wave.open(str(project / "input" / name), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(raw)

    def fingerprints():
        return {
            path.relative_to(project).as_posix(): (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_mtime_ns,
            )
            for path in [project / "project.yaml", *sorted((project / "input").iterdir())]
        }

    originals = fingerprints()
    output = project / "intermediate/ready"
    cli("prepare-project", project, "--output-dir", output)
    prepared = json.loads(cli("verify-preparation", output / "run.json"))
    quality = json.loads(cli("verify-arrangement", output / "arrangement.json"))
    if prepared["status"] != "offline_ready" or not quality["valid"]:
        raise RuntimeError("Preparation/quality did not verify")
    arrangement = json.loads((output / "arrangement.json").read_text(encoding="utf-8"))
    note = arrangement["tracks"][1]["notes"][0]
    if (note["start_tick"], note["duration_ticks"], note["channel"], note["pitch"]) != (
        120,
        240,
        2,
        60,
    ):
        raise RuntimeError("Original musical timing/channel/pitch changed")
    cli("prepare-project", project, "--output-dir", output, expected=1)
    performance_path = project / "intermediate/performance.json"
    performance_args = (
        "plan-midi-performance",
        output / "arrangement.json",
        "--target-ppq",
        960,
        "--output",
        performance_path,
    )
    cli(*performance_args)
    cli("verify-midi-performance", performance_path)
    performance = json.loads(performance_path.read_text(encoding="utf-8"))
    if (
        performance["execution_allowed"] is not False
        or len(performance["tempos"]) != 2
        or len(performance["untranslated_events"]) != 2
        or performance["notes"][0]["end"]["elapsed_microseconds"]
        != {"numerator": 400000, "denominator": 1}
    ):
        raise RuntimeError("Exact performance preparation lost events or changed time")
    cli(*performance_args, expected=1)
    performance["tracks"][1]["events"].reverse()
    damaged_performance = project / "intermediate/intentional-performance-corruption.json"
    damaged_performance.write_text(json.dumps(performance), encoding="utf-8")
    cli("verify-midi-performance", damaged_performance, expected=1)
    measured = json.loads(
        cli(
            "compare-renders",
            project / "input/song.wav",
            project / "input/song.wav",
            "--max-rms-error",
            0,
        )
    )
    if measured["rms_difference"] != 0 or not measured["within_tolerance"]:
        raise RuntimeError("Exact PCM comparison failed")
    rejected = json.loads(
        cli(
            "compare-renders",
            project / "input/song.wav",
            project / "input/other.wav",
            "--max-rms-error",
            0.1,
            expected=1,
        )
    )
    if rejected["within_tolerance"] is not False:
        raise RuntimeError("Bad numerical render comparison was accepted")
    damaged = project / "intermediate/intentional-corruption-test"
    cli("prepare-project", project, "--output-dir", damaged)
    # Only a newly generated synthetic output is damaged, never an original input.
    (damaged / "quality.json").write_text("{}\n", encoding="utf-8")
    cli("verify-preparation", damaged / "run.json", expected=1)
    if originals != fingerprints() or list(root.rglob("*.flp")):
        raise RuntimeError("Inputs changed or an FLP was unexpectedly created")
    print(
        json.dumps(
            {
                "workflow": "passed",
                "negative_checks": "passed",
                "performance_replay": "passed",
                "performance_negative_checks": "passed",
                "installed_wheel": installed,
                "package_path": str(module_path),
                "original_inputs_unchanged": True,
                "flp_created": False,
                "host_compatibility": "unverified",
                "writer_eligibility": "blocked",
                "ready_bundle": str(output / "run.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
