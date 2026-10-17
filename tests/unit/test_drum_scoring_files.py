"""Source-bound drum reports use tiny original PCM; no external music or DAW."""

import json
import wave

import pytest
from typer.testing import CliRunner

from suno2flp.cli import app
from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.pipeline.drum_scoring import score_drum_files
from suno2flp.validator.drum_scoring import verify_drum_score


@pytest.fixture
def files(tmp_path):
    audio = tmp_path / "原创 鼓.wav"
    with wave.open(str(audio), "wb") as out:
        out.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        out.writeframes(b"\x01\x00" * 16000)
    decoded = decode_pcm_wave(audio, tmp_path / "decode")
    producer = tmp_path / "producer.txt"
    producer.write_text("Original synthetic onset annotations, not a model benchmark.")
    base = dict(
        profile="source-clock-drum-annotation-v1",
        origin="synthetic_fixture",
        method="authored synthetic annotation",
        provenance_files=[capture_stream_input(producer).model_dump(mode="json")],
        decode_report=capture_stream_input(tmp_path / "decode/decode.json").model_dump(mode="json"),
        source_audio=decoded.preflight.source.model_dump(mode="json"),
        frames=16000,
        sample_rate=8000,
        channels=1,
        events=[dict(id="n1", label="KD", microseconds=dict(numerator=100_000, denominator=1))],
    )
    paths = [tmp_path / f"{role}.json" for role in ("candidate", "reference")]
    for path, role in zip(paths, ("candidate", "reference"), strict=True):
        path.write_text(json.dumps(base | dict(role=role)), encoding="utf-8")
    return *paths, tmp_path / "score.json", audio, producer


def edit(path, change):
    data = json.loads(path.read_bytes())
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_whole_report_replays_without_changing_inputs(files):
    c, r, output, audio, producer = files
    before = [capture_stream_input(p) for p in (c, r, audio, producer)]
    report = score_drum_files(c, r, output)
    assert report.result.f1.numerator == report.result.f1.denominator == 1
    assert report.reference.annotation.events[0].label == "KD"
    assert report.annotation_truth_verified is report.execution_allowed is False
    assert report.model_qualification == "not_assessed" and report.writer_eligibility == "blocked"
    assert report == verify_drum_score(output)
    assert before == [capture_stream_input(p) for p in (c, r, audio, producer)]
    assert output.read_bytes() == output.with_name("score.pending.json").read_bytes()
    with pytest.raises((ValueError, FileExistsError)):
        score_drum_files(c, r, output)


@pytest.mark.parametrize(
    "reference,status", [(None, "reference_unavailable"), ("empty", "no_reference_events")]
)
def test_unscored_reference_and_cli_exit(files, reference, status):
    c, r, output, *_ = files
    if reference:
        edit(r, lambda d: d.update(events=[]))
    args = ["score-drums", str(c), "--output", str(output)]
    if reference:
        args += ["--reference", str(r)]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 3, result.output
    assert verify_drum_score(output).result.status == status
    assert runner.invoke(app, ["verify-drum-score", str(output)]).exit_code == 3


@pytest.mark.parametrize(
    "change",
    ["frames", "source", "role", "origin", "tail", "duplicate", "label", "negative", "huge"],
)
def test_invalid_declarations_never_publish(files, change):
    c, r, output, *_ = files

    def mutate(d):
        if change == "frames":
            d["frames"] -= 1
        elif change == "source":
            d["source_audio"]["sha256"] = "0" * 64
        elif change == "role":
            d["role"] = "reference"
        elif change == "origin":
            d["origin"] = "declared_reference"
        elif change == "tail":
            d["events"][0]["microseconds"]["numerator"] = 2_000_000
        elif change == "duplicate":
            d["events"] *= 2
        elif change == "label":
            d["events"][0]["label"] = "kick"
        else:
            d["events"][0]["microseconds"]["numerator"] = -1 if change == "negative" else 2**200

    edit(c, mutate)
    with pytest.raises((ValueError, OfflineError)):
        score_drum_files(c, r, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "target", ["annotation", "producer", "audio", "recipe", "result", "relocated", "duplicate_json"]
)
def test_changed_or_forged_evidence_rejected_on_full_replay(files, target):
    c, r, output, audio, producer = files
    score_drum_files(c, r, output)
    if target == "annotation":
        edit(c, lambda d: d["events"][0].update(label="SD"))
    elif target in {"producer", "audio"}:
        p = producer if target == "producer" else audio
        p.write_bytes(p.read_bytes() + b"changed")
    elif target == "recipe":
        edit(output, lambda d: d["recipe"]["files"][0].update(sha256="0" * 64))
    elif target == "result":
        edit(output, lambda d: d["result"]["matches"][0].update(candidate_id="invented"))
    elif target == "duplicate_json":
        raw = output.read_text(encoding="utf-8")
        output.write_text(
            raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
            encoding="utf-8",
        )
    else:
        copied = output.with_name("copied.json")
        copied.write_bytes(output.read_bytes())
        output = copied
    before = capture_stream_input(output)
    with pytest.raises((ValueError, OfflineError)):
        verify_drum_score(output)
    assert capture_stream_input(output) == before


def test_cancellation_and_late_source_mutation_never_publish(files, monkeypatch):
    c, r, output, _, producer = files
    with pytest.raises(OfflineError, match="cancel"):
        score_drum_files(c, r, output, should_cancel=lambda: True)
    assert not output.exists()
    import suno2flp.pipeline.drum_scoring as pipeline

    publish = pipeline.publish_verified_report

    def late(path, content, protected, verify):
        producer.write_text("changed immediately before publication")
        return publish(path, content, protected, verify)

    monkeypatch.setattr(pipeline, "publish_verified_report", late)
    with pytest.raises((ValueError, OfflineError)):
        score_drum_files(c, r, output)
    assert not output.exists()


def test_rehashed_modified_pcm_is_not_valid_decode_evidence(files):
    c, r, output, *_ = files
    import hashlib

    pcm = c.parent / "decode/decoded.wav"
    raw = bytearray(pcm.read_bytes())
    raw[58:66] = b"\0" * 8
    pcm.write_bytes(raw)
    decode = c.parent / "decode/decode.json"
    edit(
        decode,
        lambda d: d.update(
            pcm=capture_stream_input(pcm).model_dump(mode="json"),
            samples_sha256=hashlib.sha256(raw[58:]).hexdigest(),
        ),
    )
    for p in (c, r):
        edit(
            p,
            lambda d: d.update(decode_report=capture_stream_input(decode).model_dump(mode="json")),
        )
    with pytest.raises((ValueError, OfflineError), match="sample|Sample"):
        score_drum_files(c, r, output)
    assert not output.exists()


def test_measured_and_error_cli_paths(files):
    c, r, output, *_ = files
    runner = CliRunner()
    assert (
        runner.invoke(
            app, ["score-drums", str(c), "--reference", str(r), "--output", str(output)]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["verify-drum-score", str(output)]).exit_code == 0
    assert runner.invoke(app, ["score-drums", str(c), "--output", str(output)]).exit_code == 1
    assert runner.invoke(app, ["verify-drum-score", str(c)]).exit_code == 1
