"""Authored audio/annotations exercise source-bound metrics and current replay."""

import json
import wave

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.pipeline.note_scoring import score_note_files
from suno2flp.validator.note_scoring import verify_note_score


@pytest.fixture
def annotations(tmp_path):
    audio = tmp_path / "合成 song.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x01\x00" * 16000)
    decoded = decode_pcm_wave(audio, tmp_path / "decode")
    provenance = tmp_path / "authored.txt"
    provenance.write_text("Original synthetic notes and PCM fixture; not a model benchmark.")
    base = {
        "schema_version": 1,
        "profile": "pitched-note-annotation-v1",
        "method": "authored synthetic fixture, no model",
        "origin": "synthetic_fixture",
        "provenance_files": [capture_stream_input(provenance).model_dump(mode="json")],
        "decode_report": capture_stream_input(tmp_path / "decode/decode.json").model_dump(
            mode="json"
        ),
        "source_audio": decoded.preflight.source.model_dump(mode="json"),
        "sample_rate": 8000,
        "channels": 1,
        "frames": 16000,
        "notes": [
            {
                "id": "n1",
                "pitch": 60,
                "onset_microseconds": {"numerator": 0, "denominator": 1},
                "offset_microseconds": {"numerator": 1_000_000, "denominator": 1},
            }
        ],
    }
    paths = []
    for role in ["candidate", "reference"]:
        path = tmp_path / f"{role}.json"
        path.write_text(json.dumps(base | {"role": role}), encoding="utf-8")
        paths.append(path)
    return paths[0], paths[1], tmp_path / "score.json", audio, provenance


def edit(path, mutate):
    data = json.loads(path.read_bytes())
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_bound_report_keeps_snapshots_and_replays_without_writes(annotations):
    candidate, reference, output, audio, provenance = annotations
    before = [capture_stream_input(p) for p in [candidate, reference, audio, provenance]]
    result = score_note_files(candidate, reference, output)
    identity = capture_stream_input(output)
    assert result.result.status == "measured" and result.result.f1.numerator == 1
    assert result.reference.annotation.role == "reference"
    assert result.annotation_truth_verified is False
    assert result.musical_correctness == "not_proven_per_song"
    assert result.writer_eligibility == "blocked" and result.execution_allowed is False
    assert result == verify_note_score(output)
    assert capture_stream_input(output) == identity
    assert before == [capture_stream_input(p) for p in [candidate, reference, audio, provenance]]


def test_absent_reference_is_explicit_and_never_synthesized(annotations):
    candidate, _, output, *_ = annotations
    report = score_note_files(candidate, None, output)
    assert report.reference is None and report.result.f1 is None
    assert verify_note_score(output).result.status == "reference_unavailable"


@pytest.mark.parametrize("change", ["frames", "source", "role", "origin", "tail", "duplicate_ids"])
def test_invalid_declarations_fail_before_publishing(annotations, change):
    candidate, reference, output, *_ = annotations

    def mutate(data):
        if change == "frames":
            data["frames"] -= 1
        elif change == "source":
            data["source_audio"]["sha256"] = "0" * 64
        elif change == "role":
            data["role"] = "reference"
        elif change == "origin":
            data["origin"] = "declared_reference"
        elif change == "tail":
            data["notes"][0]["offset_microseconds"]["numerator"] = 2_000_001
        else:
            data["notes"].append(data["notes"][0])

    edit(candidate, mutate)
    with pytest.raises((OfflineError, ValueError)):
        score_note_files(candidate, reference, output)
    assert not output.exists()


@pytest.mark.parametrize("target", ["annotation", "producer", "audio", "recipe", "result"])
def test_replay_rejects_changed_witness_or_fabricated_result(annotations, target):
    candidate, reference, output, audio, producer = annotations
    score_note_files(candidate, reference, output)
    if target == "annotation":
        edit(candidate, lambda data: data["notes"][0].update(pitch=61))
    elif target in {"producer", "audio"}:
        path = producer if target == "producer" else audio
        path.write_bytes(path.read_bytes() + b"changed")
    elif target == "recipe":
        edit(output, lambda data: data["recipe"]["files"][0].update(sha256="0" * 64))
    else:
        edit(output, lambda data: data["result"]["matches"][0].update(candidate_id="invented"))
    before = capture_stream_input(output)
    with pytest.raises((OfflineError, ValueError)):
        verify_note_score(output)
    assert capture_stream_input(output) == before


def test_rehashed_altered_pcm_cannot_become_truth_evidence(annotations):
    candidate, reference, output, *_ = annotations
    decoded_path = candidate.parent / "decode/decoded.wav"
    raw = bytearray(decoded_path.read_bytes())
    raw[58:66] = b"\0" * 8
    decoded_path.write_bytes(raw)
    decode = candidate.parent / "decode/decode.json"
    import hashlib

    edit(
        decode,
        lambda data: data.update(
            pcm=capture_stream_input(decoded_path).model_dump(mode="json"),
            samples_sha256=hashlib.sha256(raw[58:]).hexdigest(),
        ),
    )
    for path in [candidate, reference]:
        edit(
            path,
            lambda data: data.update(
                decode_report=capture_stream_input(decode).model_dump(mode="json")
            ),
        )
    with pytest.raises(OfflineError, match="sample|Sample"):
        score_note_files(candidate, reference, output)
    assert not output.exists()


@pytest.mark.parametrize("bad", ["oversized", "duplicate_json", "backend", "existing", "cancel"])
def test_bounded_reads_cancellation_and_output_protection(annotations, bad):
    candidate, reference, output, *_ = annotations
    if bad == "oversized":
        candidate.write_bytes(b" " * (4 * 1024**2 + 1))
    elif bad == "duplicate_json":
        candidate.write_bytes(candidate.read_bytes()[:-1] + b',"schema_version":1}')
    elif bad == "backend":
        (candidate.parent / "backend.json").write_text("{}")
    elif bad == "existing":
        output.write_text("keep")
    before = capture_stream_input(candidate)
    with pytest.raises((OfflineError, ValueError)):
        score_note_files(candidate, reference, output, should_cancel=lambda: bad == "cancel")
    assert capture_stream_input(candidate) == before
    if bad == "existing":
        assert output.read_text() == "keep"
    else:
        assert not output.exists()


@pytest.mark.parametrize("reference_kind, expected", [("present", 0), ("absent", 3), ("empty", 3)])
def test_cli_distinguishes_valid_measurement_from_unavailable_truth(
    annotations, reference_kind, expected
):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    candidate, reference, output, *_ = annotations
    if reference_kind == "empty":
        edit(reference, lambda data: data.update(notes=[]))
    args = ["score-pitched-notes", str(candidate), "--output", str(output)]
    if reference_kind != "absent":
        args += ["--reference", str(reference)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == expected, result.output
    assert "not_proven_per_song" in result.output
    replay = CliRunner().invoke(app, ["verify-note-score", str(output)])
    assert replay.exit_code == expected, replay.output


def test_cli_fails_explicitly_on_missing_input(annotations):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    candidate, _, output, *_ = annotations
    result = CliRunner().invoke(
        app,
        ["score-pitched-notes", str(candidate.parent / "missing.json"), "--output", str(output)],
    )
    assert result.exit_code == 1
    assert not output.exists()


def test_linked_annotation_path_is_rejected(annotations):
    candidate, reference, output, *_ = annotations
    link = candidate.parent / "linked.json"
    try:
        link.symlink_to(candidate)
    except OSError:
        pytest.skip("OS does not permit symbolic-link creation for this user")
    with pytest.raises(OfflineError, match="Linked"):
        score_note_files(link, reference, output)
    assert not output.exists()


@pytest.fixture
def compressed_evidence(annotations, monkeypatch):
    # Only adapter dispatch is mocked here; actual codec replay is covered by its
    # existing opt-in integration tests. Never treat this as native qualification.
    from types import SimpleNamespace

    import suno2flp.validator.note_scoring as service
    from suno2flp.core.codec_backend import CodecBackendRecord
    from suno2flp.core.encoded_decode import EncodedDecodeReport, EncodedDecodeRequest

    candidate, reference, output, audio, *_ = annotations
    decode = candidate.parent / "compressed-decode.json"
    decode.write_text(json.dumps({"profile": "qualified-compressed-to-float64-v1"}))
    for path in [candidate, reference]:
        edit(
            path,
            lambda data: data.update(
                decode_report=capture_stream_input(decode).model_dump(mode="json")
            ),
        )
    calls = []
    pcm = capture_stream_input(candidate.parent / "decode/decoded.wav")
    backend_root = candidate.parent / "synthetic-backend"
    (backend_root / "packages").mkdir(parents=True)
    names = ["backend.json", "adapter.py", "wheel.whl", "runtime.dll", "packages/native.dll"]
    identities = []
    for name in names:
        file = backend_root / name
        file.write_text("original synthetic decoder identity only")
        identities.append(capture_stream_input(file))
    manifest, adapter, wheel_file, runtime, native = identities
    request = EncodedDecodeRequest(
        source=capture_stream_input(audio),
        output_directory=candidate.parent / "decode",
        decoder_directory=backend_root,
        app_python=runtime,
        python_version="synthetic",
        adapters=[adapter],
    )
    attempt = candidate.parent / "attempt.json"
    attempt.write_text(request.model_dump_json(), encoding="utf-8")
    # model_construct builds only the typed verifier boundary needed here; the
    # native verifier itself is mocked, so this is NOT a qualified codec fixture.
    backend = CodecBackendRecord.model_construct(
        root=backend_root,
        python=runtime,
        python_runtime=[runtime],
        wheels=[wheel_file],
        adapter_files=[adapter],
        payload={"native.dll": native.sha256},
    )
    verified_report = EncodedDecodeReport.model_construct(
        inventory=SimpleNamespace(
            source=capture_stream_input(audio), frames=16000, channels=1, sample_rate=8000
        ),
        pcm=pcm,
        request=capture_stream_input(attempt),
        backend_manifest=manifest,
        backend=backend,
    )

    def verified(path, *, should_cancel=None):
        calls.append(path)
        return verified_report

    monkeypatch.setattr(service, "verify_encoded_decode", verified)
    return {
        "calls": calls,
        "decode": decode,
        "attempt": attempt,
        "adapter": adapter.path,
        "wheel": wheel_file.path,
        "runtime": runtime.path,
        "native": native.path,
        "extra": backend_root / "packages/extra.pth",
    }


def test_compressed_dispatch_uses_independent_verifier_and_actual_clock(
    annotations, compressed_evidence
):
    candidate, reference, output, *_ = annotations
    result = score_note_files(candidate, reference, output)
    assert result.result.true_positives == 1
    assert compressed_evidence["calls"] == [compressed_evidence["decode"]]
    for field in ["attempt", "adapter", "wheel", "runtime", "native"]:
        assert compressed_evidence[field] in result.protected_paths()


@pytest.mark.parametrize("field", ["attempt", "adapter", "wheel", "runtime", "native", "extra"])
def test_compressed_dependency_changes_after_verification_fail_before_success(
    annotations, compressed_evidence, monkeypatch, field
):
    import suno2flp.pipeline.note_scoring as publisher

    candidate, reference, output, *_ = annotations
    original = publisher.new_report

    def changed(*args, **kwargs):
        original(*args, **kwargs)
        compressed_evidence[field].write_text("changed after publication")

    monkeypatch.setattr(publisher, "new_report", changed)
    with pytest.raises(OfflineError, match="changed"):
        score_note_files(candidate, reference, output)


def test_file_changes_during_bounded_read_are_detected(annotations, monkeypatch):
    from pathlib import Path

    from suno2flp.importer.note_annotations import bounded_snapshot

    candidate, *_ = annotations
    original_open = Path.open

    class ChangingReader:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, maximum):
            with original_open(candidate, "rb") as stream:
                content = stream.read(maximum)
            with original_open(candidate, "ab") as stream:
                stream.write(b" ")
            return content

    monkeypatch.setattr(Path, "open", lambda path, *args, **kwargs: ChangingReader())
    with pytest.raises(OfflineError, match="changed"):
        bounded_snapshot(candidate, 4 * 1024**2)


@pytest.mark.parametrize("when", ["matching", "publication"])
def test_verified_decoder_witnesses_remain_bound_through_publication(
    annotations, monkeypatch, when
):
    import suno2flp.pipeline.note_scoring as publisher
    import suno2flp.validator.note_scoring as service
    import suno2flp.validator.pcm_decode as verifier

    candidate, reference, output, *_ = annotations
    decode = candidate.parent / "decode/decode.json"
    witness = candidate.parent / "authored-decoder-witness.txt"
    witness.write_text("original synthetic runtime witness")
    runtime = verifier.verify_pcm_decode(decode).runtime.model_copy(
        update={"decoder": capture_stream_input(witness)}
    )
    edit(decode, lambda data: data.update(runtime=runtime.model_dump(mode="json")))
    for annotation in [candidate, reference]:
        edit(
            annotation,
            lambda data: data.update(
                decode_report=capture_stream_input(decode).model_dump(mode="json")
            ),
        )
    # Preserve actual source/PCM inverse verification; only its synthetic runtime
    # identity witness is substituted, avoiding any production-code mutation.
    monkeypatch.setattr(verifier, "pcm_runtime", lambda: runtime)
    if when == "matching":
        original = service.score_notes

        def changed(*args, **kwargs):
            witness.write_text("changed during matching")
            return original(*args, **kwargs)

        monkeypatch.setattr(service, "score_notes", changed)
    else:
        original = publisher.new_report

        def changed(*args, **kwargs):
            original(*args, **kwargs)
            witness.write_text("changed after publication")

        monkeypatch.setattr(publisher, "new_report", changed)
    with pytest.raises(OfflineError, match="changed"):
        score_note_files(candidate, reference, output)
    assert output.exists() == (when == "publication")
