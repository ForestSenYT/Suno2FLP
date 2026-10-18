"""Real source/publication checks with only the unavailable native boundary replaced."""

import json
import wave
from copy import deepcopy

import pytest

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.yourmt3 import FrameInterval
from suno2flp.core.yourmt3_moe import YourMT3MoEBackend
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.integrations.yourmt3_source import load_yourmt3_moe_pins
from suno2flp.pipeline import yourmt3_moe as pipeline
from suno2flp.validator import yourmt3_moe as validator


def setup(tmp_path, monkeypatch, failure=None, notes=None):
    source = tmp_path / "original.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 48000, 98304, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 98304)
    before = capture_stream_input(source)
    decode_pcm_wave(source, tmp_path / "decode")
    root = tmp_path / "backend"
    root.mkdir()
    python = tmp_path / "fixture-python.exe"
    python.write_bytes(b"Never executed; native call is explicitly replaced")
    backend = YourMT3MoEBackend(
        root=root,
        python=capture_stream_input(python),
        runtime=[],
        artifacts=[],
        adapters=[],
        payload={},
    )
    (root / "backend.json").write_text(backend.model_dump_json(), encoding="utf-8")
    pins = load_yourmt3_moe_pins()
    native = dict(
        windows=[
            dict(
                index=i,
                start_frame=i * 32767,
                valid_frames=32767 if i == 0 else 1,
                initial=[dict(channel=c, tokens=[339, 1]) for c in range(13)],
                retry=None,
            )
            for i in range(2)
        ],
        channels=[
            dict(
                channel=c,
                notes=[],
                decoded_windows=[[[], [], [], 0.0], [[], [], [], 32767 / 16000]],
                events=[[], []],
                decode_errors={},
                merge_errors={},
            )
            for c in range(13)
        ],
        configuration=pins.configuration,
        versions={p.distribution: p.version for p in pins.wheels},
        seconds=1.0,
        peak_working_set_bytes=1000,
        peak_commit_bytes=2000,
    )
    if failure == "tail":
        native["windows"][-1]["valid_frames"] = 2
    if failure == "versions":
        native["versions"]["torch"] = "unreviewed"
    if notes is not None:
        for channel, values in notes.items():
            native["channels"][channel]["notes"] = deepcopy(values)
    calls = []

    def invoke(record, attempt, request):
        calls.append(request["mode"])
        attempt.mkdir()
        (attempt / "request.json").write_text(json.dumps(request), encoding="utf-8")
        for name in ["stdout.txt", "stderr.txt"]:
            (attempt / name).write_bytes(b"synthetic native boundary")
        result = deepcopy(
            native if request["mode"] == "infer" else {"channels": native["channels"]}
        )
        if request["mode"] == "decode":
            if failure == "replay":
                result["channels"][0]["decode_errors"] = {"invented": 1}
            if failure == "source":
                # Adversarial mutation of this test's synthetic source, never a user asset.
                source.write_bytes(source.read_bytes() + b"changed during verification")
        path = attempt / "native.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        return capture_stream_input(path)

    for module in [pipeline, validator]:
        monkeypatch.setattr(module, "read_yourmt3_moe_backend", lambda root: backend)
        monkeypatch.setattr(module, "call_yourmt3_moe_backend", invoke)
    return source, before, root, calls


def test_moe_publishes_only_source_bound_independently_decoded_candidate(tmp_path, monkeypatch):
    source, before, backend, calls = setup(tmp_path, monkeypatch)
    report = pipeline.transcribe_yourmt3_moe(
        tmp_path / "decode/decode.json",
        backend,
        tmp_path / "candidate",
        [FrameInterval(start_frame=0, end_frame=98304)],
    )
    assert calls == ["infer", "decode"]
    assert capture_stream_input(source) == before
    assert report.writer_eligibility == "blocked" and report.unresolved_generations == []
    assert (report.root / "yourmt3-moe.json").is_file()
    assert report == validator.verify_yourmt3_moe(report.root / "yourmt3-moe.json")
    assert capture_stream_input(source) == before


@pytest.mark.parametrize("failure", ["tail", "versions", "replay", "source"])
def test_moe_rejection_never_publishes_completion_name(tmp_path, monkeypatch, failure):
    source, before, backend, calls = setup(tmp_path, monkeypatch, failure)
    with pytest.raises((ValueError, Suno2FLPError)):
        pipeline.transcribe_yourmt3_moe(
            tmp_path / "decode/decode.json",
            backend,
            tmp_path / "candidate",
            [FrameInterval(start_frame=0, end_frame=98304)],
        )
    assert not (tmp_path / "candidate/yourmt3-moe.json").exists()
    assert (tmp_path / "candidate/attempt/native.json").is_file()
    if failure != "source":
        assert capture_stream_input(source) == before
    assert calls[0] == "infer"
