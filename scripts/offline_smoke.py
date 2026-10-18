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
from suno2flp.integrations.yourmt3_source import load_yourmt3_moe_pins, load_yourmt3_pins


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
    # Both installed metadata recipes are required, without importing native ML libraries.
    moe, single = load_yourmt3_moe_pins(), load_yourmt3_pins()
    assert len(moe.state) == 655 and len(single.state) == 386
    assert moe.profile != single.profile and moe.generation_policy.retry_max_tokens == 1024
    assert not {"torch", "torchaudio", "transformers"} & set(sys.modules)
    if args.require_installed:
        # The distribution includes an Apache-derived isolated helper; first-party
        # files retain their MIT grant. Verify actual installed notices, not config alone.
        assert distribution.metadata["License-Expression"] == "MIT AND Apache-2.0"
        required = {
            "LICENSE",
            "src/suno2flp/integrations/notices/IDM-Apache-2.0.txt",
            "src/suno2flp/integrations/notices/IDM-NOTICE.txt",
        }
        assert set(distribution.metadata.get_all("License-File") or []) == required
        paths = list(distribution.files or [])
        for name in required:
            matching = [p for p in paths if str(p).endswith(".dist-info/licenses/" + name)]
            assert len(matching) == 1 and distribution.locate_file(matching[0]).is_file()
        notice = module_path.parent / "integrations/notices/IDM-Apache-2.0.txt"
        assert hashlib.sha256(notice.read_bytes()).hexdigest() == (
            "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
        )
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
    for command in (
        "export-yourmt3-moe-midi",
        "verify-yourmt3-moe-midi",
        "prepare-drum-backend",
        "verify-drum-backend",
        "transcribe-drums",
        "verify-drum-transcription",
        "export-drum-annotation",
        "compose-percussion-arrangement",
        "verify-percussion-arrangement",
    ):
        cli(command, "--help")
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
    created_job = json.loads(
        cli(
            "create-audio-job",
            project / "input/song.wav",
            "--output",
            root / "audio-job",
            "--job-id",
            "smoke-v1",
        )
    )
    audio_job = json.loads(cli("run-audio-job", created_job["record"]["path"], expected=3))
    checked_job = json.loads(cli("verify-audio-job", audio_job["record"]["path"]))
    if (
        checked_job != audio_job
        or audio_job["job"]["status"] != "blocked"
        or audio_job["job"]["stages"][0]["status"] != "succeeded"
        or audio_job["job"]["stages"][1]["status"] != "succeeded"
        or len(audio_job["job"]["stages"][1]["outputs"]) != 2
        or audio_job["job"]["stages"][2]["status"] != "queued"
        or audio_job["job"]["history"][-1]["code"] != "worker_unavailable"
    ):
        raise RuntimeError("Persistent PCM decode did not block at unavailable separation")
    cli("run-audio-job", created_job["record"]["path"], expected=1)
    cli(
        "create-audio-job",
        project / "input/song.wav",
        "--output",
        root / "audio-job",
        "--job-id",
        "reuse-v1",
        expected=1,
    )
    report_path = Path(audio_job["job"]["stages"][0]["outputs"][0]["path"])
    report_path.write_bytes(report_path.read_bytes() + b" ")
    cli("verify-audio-job", audio_job["record"]["path"], expected=1)
    cancel_source = root / "cancel-source.wav"
    cancel_source.write_bytes((project / "input/song.wav").read_bytes())
    cancellable = json.loads(
        cli(
            "create-audio-job",
            cancel_source,
            "--output",
            root / "cancel-job",
            "--job-id",
            "cancel-v1",
        )
    )
    cancel_source.unlink()  # Only this disposable synthetic copy, never an original.
    cancelled = json.loads(cli("cancel-audio-job", cancellable["record"]["path"]))
    if cancelled["job"]["status"] != "cancelled":
        raise RuntimeError("Persistent cancellation requires the vanished source")
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
    encoding_path = project / "intermediate/encoding.json"
    cli("assess-midi-encoding", performance_path, "--output", encoding_path)
    cli("verify-midi-encoding", encoding_path)
    encoding = json.loads(encoding_path.read_text(encoding="utf-8"))
    if (
        encoding["execution_allowed"] is not False
        or len(encoding["routes"]) != 1
        or len(encoding["routes"][0]["controls"]) != 2
        or encoding["hypothetical_end_error_microseconds"] != {"numerator": 0, "denominator": 1}
    ):
        raise RuntimeError("Encoding analysis lost controls or changed exact scalar time")
    cli("assess-midi-encoding", performance_path, "--output", encoding_path, expected=1)
    encoding["routes"][0]["controls"].reverse()
    damaged_encoding = project / "intermediate/intentional-encoding-corruption.json"
    damaged_encoding.write_text(json.dumps(encoding), encoding="utf-8")
    cli("verify-midi-encoding", damaged_encoding, expected=1)
    bindings_path = project / "intermediate/midi-bindings.json"
    bindings_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bindings": [
                    {
                        "source_input": 0,
                        "source_channel": 2,
                        "destination_port": 16,
                        "destination_channel": 2,
                        "receiver_id": "smoke-receiver",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    routing_path = project / "intermediate/midi-routing.json"
    routing_args = ("plan-midi-routing", performance_path, bindings_path, "--output", routing_path)
    cli(*routing_args)
    cli("verify-midi-routing", routing_path)
    routing = json.loads(routing_path.read_text(encoding="utf-8"))
    route = routing["routes"][0]
    if (
        route["binding"]["destination_channel"] != 2
        or [c["source_tick"] for c in route["source"]["controls"]] != [0, 480]
        or routing["receiver_delivery"] != "unverified"
        or routing["execution_allowed"] is not False
    ):
        raise RuntimeError("Routing changed source controls or granted execution")
    cli(*routing_args, expected=1)
    route["source"]["controls"].pop()
    damaged_routing = project / "intermediate/intentional-routing-corruption.json"
    damaged_routing.write_text(json.dumps(routing), encoding="utf-8")
    cli("verify-midi-routing", damaged_routing, expected=1)
    midi_comparison_path = project / "intermediate/midi-comparison.json"
    midi_source = project / "input/song.mid"
    midi_candidate = project / "intermediate/extra-control.mid"
    candidate = mido.MidiFile(midi_source)
    candidate.tracks[1].insert(-1, mido.Message("control_change", channel=2, control=7, value=100))
    candidate.save(midi_candidate)
    comparison_args = (
        "compare-midi-events",
        midi_source,
        midi_candidate,
        "--output",
        midi_comparison_path,
    )
    cli(*comparison_args, expected=1)
    comparison = json.loads(midi_comparison_path.read_text(encoding="utf-8"))
    if (
        comparison["equivalent"] is not False
        or comparison["clock_equal"] is not True
        or len(comparison["extra"]) != 1
        or comparison["missing"]
        or comparison["execution_allowed"] is not False
    ):
        raise RuntimeError("Extra MIDI control was lost or accepted as equivalent")
    cli("verify-midi-comparison", midi_comparison_path)
    cli(*comparison_args, expected=1)
    cli(
        "compare-midi-events",
        midi_source,
        midi_source,
        "--output",
        project / "intermediate/equal-midi.json",
    )
    comparison["extra"] = []
    corrupted_comparison = project / "intermediate/intentional-midi-comparison-corruption.json"
    corrupted_comparison.write_text(json.dumps(comparison), encoding="utf-8")
    cli("verify-midi-comparison", corrupted_comparison, expected=1)
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
                "encoding_assessment_replay": "passed",
                "midi_comparison_replay": "passed",
                "midi_routing_replay": "passed",
                "persistent_audio_jobs": "passed",
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
