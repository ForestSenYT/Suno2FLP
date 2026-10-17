"""Verified decoder/files plus an explicitly synthetic native boundary, never music quality."""

import hashlib
import importlib
import json
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_spleeter_backend import recipe as recipe

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.importer.pcm_decode import decode_pcm_wave

STEMS = ("vocals", "drums", "bass", "other")
WEIGHTS = (0.125, 0.25, 0.25, 0.375)


def services():
    return (
        importlib.import_module("suno2flp.pipeline.separation"),
        importlib.import_module("suno2flp.validator.separation"),
    )


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def float_wave_header(frames, rate):
    size = frames * 8
    return struct.pack(
        "<4sI4s4sIHHIIHHH4sII4sI",
        b"RIFF",
        size + 50,
        b"WAVE",
        b"fmt ",
        18,
        3,
        2,
        rate,
        rate * 8,
        8,
        32,
        0,
        b"fact",
        4,
        frames,
        b"data",
        size,
    )


@pytest.fixture
def protocol(recipe, tmp_path, monkeypatch, request):
    frames, channels = getattr(request, "param", (37, 1))
    backend, artifacts, pins, _, _ = recipe
    source = tmp_path / "original.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((channels, 2, 44100, 0, "NONE", "original synthetic fixture"))
        for start in range(0, frames, 4096):
            raw = bytearray()
            for index in range(start, min(frames, start + 4096)):
                left = ((index * 7) % 17 - 8) * 1024
                right = ((index * 11) % 19 - 9) * 896
                raw.extend(
                    struct.pack(
                        "<h" if channels == 1 else "<hh",
                        *([left] if channels == 1 else [left, right]),
                    )
                )
            stream.writeframesraw(raw)
    decoded = decode_pcm_wave(source, tmp_path / "decode")
    record = backend.provision_spleeter(tmp_path / "backend", artifacts)
    runs = []

    def process(argv, **kwargs):
        assert argv[1:4] == ["-I", "-S", "-B"] and kwargs["timeout"] == 1800
        request_path = Path(argv[-1])
        declared = json.loads(request_path.read_text())
        assert declared == dict(
            operation="separate",
            packages=str(record.root / "packages"),
            pcm=str(decoded.pcm.path),
            frames=frames,
            sample_rate=44100,
            channels=channels,
        )
        if kwargs.get("should_cancel") and kwargs["should_cancel"]():
            raise RuntimeError("cancelled synthetic owned process")
        runs.append(request_path.parent)
        attempt = request_path.parent
        with decoded.pcm.path.open("rb") as stream:
            stream.seek(58)
            original = [value[0] for value in struct.iter_unpack("<d", stream.read())]
        pairs = (
            [(original[i], original[i]) for i in range(frames)]
            if channels == 1
            else list(zip(original[::2], original[1::2], strict=True))
        )
        model_input = b"".join(struct.pack("<ff", *pair) for pair in pairs)
        (attempt / "model-input.f32").write_bytes(model_input)
        # Independently hand-derived geometry; the producer double does not call the planner.
        plans = (
            [dict(index=0, stft_start=0, stft_frames=5, virtual_start=-4096, waveform_frames=8192)]
            if frames == 37
            else [
                dict(
                    index=0, stft_start=0, stft_frames=6, virtual_start=-4096, waveform_frames=9216
                )
            ]
            if frames == 1025
            else [
                dict(
                    index=0,
                    stft_start=0,
                    stft_frames=512,
                    virtual_start=-4096,
                    waveform_frames=527360,
                ),
                dict(
                    index=1,
                    stft_start=512,
                    stft_frames=5,
                    virtual_start=520192,
                    waveform_frames=8192,
                ),
            ]
        )
        assert frames in (37, 1025, 524289)
        parts = attempt / "parts"
        parts.mkdir()
        part_results = []
        for part in plans:
            index, start, count = part["index"], part["virtual_start"], part["waveform_frames"]
            low, high = max(0, start), min(frames, start + count)
            padded = b"\0" * ((low - start) * 8) + model_input[low * 8 : high * 8]
            padded += b"\0" * ((start + count - high) * 8)
            input_path = parts / f"{index:04d}.input.f32"
            input_path.write_bytes(padded)
            hashes = {}
            for stem, weight in zip(STEMS, WEIGHTS, strict=True):
                raw = bytearray()
                for position, pair in enumerate(struct.iter_unpack("<ff", padded)):
                    coordinate = start + position
                    overlap = frames == 524289 and 520192 <= coordinate < 523264
                    factor = weight * (0.5 if overlap else 1.0)
                    raw.extend(struct.pack("<ff", pair[0] * factor, pair[1] * factor))
                output = parts / f"{index:04d}.{stem}.f32"
                output.write_bytes(raw)
                hashes[stem] = file_hash(output)
            part_results.append(
                dict(partition=part, input_sha256=file_hash(input_path), output_sha256=hashes)
            )
        model_hashes, source_hashes, tail_hashes = {}, {}, {}
        for stem, weight in zip(STEMS, WEIGHTS, strict=True):
            raw = b"".join(
                struct.pack("<ff", left * weight, right * weight) for left, right in pairs
            )
            model = attempt / f"model.{stem}.f32"
            model.write_bytes(raw)
            wav = attempt / f"{stem}.wav"
            wav.write_bytes(float_wave_header(frames, 44100) + raw)
            tail = attempt / f"{stem}.tail.f32"
            tail.write_bytes(b"")
            model_hashes[stem], source_hashes[stem], tail_hashes[stem] = (
                file_hash(model),
                file_hash(wav),
                file_hash(tail),
            )
        proof = dict(
            graph_profile="spleeter4-cpu-no-remapping-v1",
            device_types=["CPU"],
            intra_op_threads=8,
            inter_op_threads=1,
            versions={pin.distribution: pin.version for pin in pins.artifacts},
            modules={
                name: str(record.root / "packages" / name.replace(".", "/") / "__init__.py")
                for name in (
                    "numpy",
                    "tensorflow",
                    "keras",
                    "scipy",
                    "pandas",
                    "spleeter",
                    "spleeter.model",
                )
            },
            restored_variables={"synthetic_not_a_model_run": [1]},
            restored_values_sha256="1" * 64,
            tfio_loaded=False,
            ambient_plugins_enabled=False,
        )
        result = dict(
            execution=proof,
            source_frames=frames,
            sample_rate=44100,
            source_channels=channels,
            model_frames=frames,
            returned_source_frames=frames,
            model_input_sha256=file_hash(attempt / "model-input.f32"),
            partitions=part_results,
            model_output_sha256=model_hashes,
            source_output_sha256=source_hashes,
            resampling_tail_sha256=tail_hashes,
            peak_working_set_bytes=1024**2 + len(runs) * 4096,
            peak_commit_bytes=2 * 1024**2 + len(runs) * 4096,
            elapsed_seconds=0.01 + len(runs) / 1000,
        )
        (attempt / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return b"synthetic native boundary only", b"not a real model inference"

    monkeypatch.setattr(backend, "run_bounded_process", process)
    return SimpleNamespace(
        source=source,
        decode=tmp_path / "decode/decode.json",
        backend=record.root,
        backend_module=backend,
        record=record,
        process=process,
        frames=frames,
        channels=channels,
    )


@pytest.mark.parametrize("protocol", [(37, 1), (37, 2), (524289, 1)], indirect=True)
def test_source_bound_stems_replay_with_exact_clock_and_overlap(protocol, tmp_path):
    pipeline, validator = services()
    before = capture_stream_input(protocol.source)
    report = pipeline.separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    assert report.frames == protocol.frames and report.sample_rate == 44100
    assert report.channels == protocol.channels and report.output_channels == 2
    assert report.residual_peak == 0 and report.conservation_error == 0
    assert not report.execution_allowed and report.writer_eligibility == "blocked"
    assert (
        validator.verify_separation(tmp_path / "candidate/separation.json", tmp_path / "replay")
        == report
    )
    receipt = json.loads((tmp_path / "replay/replay.json").read_text())
    assert receipt["complete_match"] and receipt["model_qualification"] == "not_assessed"
    replay = json.loads((tmp_path / "replay/separation.json").read_text())
    assert replay["result"]["elapsed_seconds"] != report.result.elapsed_seconds
    assert capture_stream_input(protocol.source) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "runtime",
        "payload",
        "partial-input",
        "missing",
        "wav-header",
        "nonfinite",
        "duplicate-part",
    ],
)
def test_changed_or_incomplete_native_evidence_never_publishes(
    protocol, tmp_path, monkeypatch, mutation
):
    pipeline, _ = services()

    def process(argv, **kwargs):
        returned = protocol.process(argv, **kwargs)
        attempt = Path(argv[-1]).parent
        metadata = attempt / "result.json"
        raw = json.loads(metadata.read_text())
        if mutation == "source":
            protocol.source.write_bytes(protocol.source.read_bytes() + b"changed")
        elif mutation == "runtime":
            protocol.record.runtime[0].path.write_bytes(b"changed runtime")
        elif mutation == "payload":
            (protocol.backend / "packages/extra.bin").write_bytes(b"extra payload")
        elif mutation == "partial-input":
            path = attempt / "parts/0000.input.f32"
            path.write_bytes(b"changed")
        elif mutation == "missing":
            (attempt / "parts/0000.vocals.f32").unlink()
        elif mutation in ("wav-header", "nonfinite"):
            path = attempt / "vocals.wav"
            data = bytearray(path.read_bytes())
            if mutation == "wav-header":
                struct.pack_into("<I", data, 24, 48000)
            else:
                struct.pack_into("<f", data, 58, float("nan"))
            path.write_bytes(data)
            raw["source_output_sha256"]["vocals"] = file_hash(path)
        else:
            raw["partitions"] *= 2
        metadata.write_text(json.dumps(raw), encoding="utf-8")
        return returned

    monkeypatch.setattr(protocol.backend_module, "run_bounded_process", process)
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        pipeline.separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    assert not (tmp_path / "candidate/separation.json").exists()
    assert (tmp_path / "candidate/native/result.json").exists()


@pytest.mark.parametrize("mutation", ["source", "provisional", "cancel"])
def test_late_failure_keeps_only_provisional_candidate(protocol, tmp_path, monkeypatch, mutation):
    pipeline, _ = services()
    publication = importlib.import_module("suno2flp.core.report_publication")
    original = publication.new_report
    target = tmp_path / "candidate/separation.pending.json"

    def late(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path == target and mutation != "cancel":
            changed = protocol.source if mutation == "source" else target
            changed.write_bytes(changed.read_bytes() + b"changed after serialization")

    monkeypatch.setattr(publication, "new_report", late)
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        pipeline.separate_audio(
            protocol.decode,
            protocol.backend,
            tmp_path / "candidate",
            should_cancel=(target.exists if mutation == "cancel" else None),
        )
    assert target.exists() and not target.with_name("separation.json").exists()


@pytest.mark.parametrize("kind", ["provisional", "nested", "foreign"])
def test_replay_cannot_accept_a_provisional_or_change_the_original_root(protocol, tmp_path, kind):
    pipeline, validator = services()
    pipeline.separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    report = tmp_path / "candidate/separation.json"
    output = tmp_path / "replay"
    if kind == "provisional":
        report = report.with_name("separation.pending.json")
    elif kind == "nested":
        output = tmp_path / "candidate/replay"
    else:
        copied = tmp_path / "copied"
        copied.mkdir()
        foreign = copied / "separation.json"
        foreign.write_bytes(report.read_bytes())
        report = foreign
        output = tmp_path / "candidate/foreign-replay"
    with pytest.raises(ValueError):
        validator.verify_separation(report, output)
    assert not output.exists()


def test_coherently_rehashed_forgery_cannot_replace_fresh_model_replay(protocol, tmp_path):
    pipeline, validator = services()
    from suno2flp.core.separation import SeparationCandidate

    root = tmp_path / "candidate"
    pipeline.separate_audio(protocol.decode, protocol.backend, root)
    manifest = root / "separation.json"
    raw = json.loads(manifest.read_text())
    native = root / "native"
    for path, offset in (
        (native / "parts/0000.vocals.f32", 4096 * 8),
        (native / "model.vocals.f32", 0),
        (native / "vocals.wav", 58),
    ):
        data = bytearray(path.read_bytes())
        for channel in range(2):
            position = offset + channel * 4
            struct.pack_into(
                "<f", data, position, struct.unpack_from("<f", data, position)[0] + 0.125
            )
        path.write_bytes(data)
    residual = root / "unassigned-residual.f64"
    data = bytearray(residual.read_bytes())
    struct.pack_into("<dd", data, 0, -0.125, -0.125)
    residual.write_bytes(data)
    result = json.loads((native / "result.json").read_text())
    result["partitions"][0]["output_sha256"]["vocals"] = file_hash(native / "parts/0000.vocals.f32")
    result["model_output_sha256"]["vocals"] = file_hash(native / "model.vocals.f32")
    result["source_output_sha256"]["vocals"] = file_hash(native / "vocals.wav")
    (native / "result.json").write_text(json.dumps(result), encoding="utf-8")
    raw["result"] = result
    raw["native_result"] = capture_stream_input(native / "result.json").model_dump(mode="json")
    raw["partitions"][0]["outputs"][0]["file"] = capture_stream_input(
        native / "parts/0000.vocals.f32"
    ).model_dump(mode="json")
    raw["stems"][0]["model"] = capture_stream_input(native / "model.vocals.f32").model_dump(
        mode="json"
    )
    raw["stems"][0]["source"] = capture_stream_input(native / "vocals.wav").model_dump(mode="json")
    raw["residual"] = capture_stream_input(residual).model_dump(mode="json")
    raw["residual_peak"] = 0.125
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    forged = SeparationCandidate.model_validate(raw)
    validator.validate_separation_artifacts(
        forged
    )  # assembly and conservation alone cannot prove inference
    with pytest.raises(ValueError, match="Fresh separation replay disagrees"):
        validator.verify_separation(manifest, tmp_path / "replay")
    assert (tmp_path / "replay/separation.json").exists()
    assert not (tmp_path / "replay/replay.json").exists()


def test_replay_receipt_requires_the_actual_serialized_replay_candidate(
    protocol, tmp_path, monkeypatch
):
    pipeline, validator = services()
    original = pipeline.separate_audio
    root = tmp_path / "candidate"
    original(protocol.decode, protocol.backend, root)
    replay = tmp_path / "replay"

    def replaced(*args, **kwargs):
        report = original(*args, **kwargs)
        (replay / "separation.json").write_text("{}", encoding="utf-8")
        return report

    monkeypatch.setattr(pipeline, "separate_audio", replaced)
    with pytest.raises(ValueError):
        validator.verify_separation(root / "separation.json", replay)
    assert not (replay / "replay.json").exists()
