"""Real original synthetic decoder/lineage; explicitly mocked drum native boundary."""

import json
import struct
from types import SimpleNamespace

import pytest
from test_separation_pipeline import protocol as protocol
from test_separation_pipeline import recipe as recipe

from suno2flp.core.drum_clock import drum_output_rows
from suno2flp.core.drum_native import DrumExecution, NativeDrumResult
from suno2flp.core.drum_runtime import DrumBackend
from suno2flp.core.drum_scoring import DRUM_CLASSES
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.integrations.drum_backend import drum_request, load_drum_pins
from suno2flp.pipeline.drum_transcription import export_drum_annotation, transcribe_drums
from suno2flp.pipeline.separation import separate_audio
from suno2flp.validator.drum_transcription import read_drum_candidate, verify_drum_transcription
from suno2flp.validator.separation import verify_separation


@pytest.fixture
def drums(protocol, tmp_path, monkeypatch):
    separate_audio(protocol.decode, protocol.backend, tmp_path / "separation")
    verify_separation(tmp_path / "separation/separation.json", tmp_path / "separation-replay")
    backend = tmp_path / "drum-backend"
    (backend / "packages/pkg").mkdir(parents=True)
    module = backend / "packages/pkg/__init__.py"
    module.write_bytes(b"# synthetic boundary, not native runtime")
    module_id = capture_stream_input(module)
    (backend / "backend.json").write_text("{}", encoding="utf-8")
    record = DrumBackend(
        root=backend,
        python=module_id,
        runtime=[],
        artifacts=[],
        adapters=[],
        payload={"pkg/__init__.py": module_id.sha256},
    )
    calls = []

    def read(root, **kwargs):
        if root != backend:
            raise ValueError("Missing synthetic drum backend")
        return record.model_copy(deep=True)

    def call(model, attempt, pcm, frames, **kwargs):
        calls.append(attempt)
        assert frames == 1025
        request = drum_request(model, pcm, frames)
        (attempt / "request.json").write_text(json.dumps(request), encoding="utf-8")
        stereo = list(struct.iter_unpack("<ff", pcm.path.read_bytes()))
        mono = b"".join(struct.pack("<f", (a + b) * 0.5) for a, b in stereo)
        rows = drum_output_rows(frames)
        onsets = [-1.0] * (9 * rows)
        onsets[DRUM_CLASSES.index("KD") * rows + 7] = 2.0
        raw = {
            "mono.f32": mono,
            "onsets.f32": struct.pack(f"<{len(onsets)}f", *onsets),
            "velocities.f32": struct.pack(f"<{len(onsets)}f", *([0.5] * len(onsets))),
        }
        files = {}
        for name, data in raw.items():
            (attempt / name).write_bytes(data)
            identity = capture_stream_input(attempt / name)
            files[name] = dict(
                shape=[frames] if name == "mono.f32" else [9, rows],
                size_bytes=len(data),
                sha256=identity.sha256,
            )
        for name in ("stdout.bin", "stderr.bin"):
            (attempt / name).write_bytes(b"")
        pins = load_drum_pins()
        result = NativeDrumResult(
            execution=DrumExecution(
                intra_op_threads=8,
                inter_op_threads=1,
                deterministic_algorithms=True,
                mkldnn=False,
                cuda=None,
                matmul_precision="highest",
                checkpoint_sha256=pins.checkpoint_sha256,
                geometry=pins.state,
                versions={p.distribution: p.version for p in pins.artifacts},
                modules={
                    name: module for name in ("torch", "torchaudio", "numpy", "einops", "idm")
                },
                time_convolutions=[[7, 3, 1, 1], [3, 3, 1, 1], [3, 3, 1, 1], [3, 3, 1, 1]],
            ),
            model_frames=frames,
            rows=rows,
            classes=list(DRUM_CLASSES),
            source_sha256=pcm.sha256,
            files=files,
            source_peak=max(abs(x) for pair in stereo for x in pair),
            mono_peak=max(abs(v[0]) for v in struct.iter_unpack("<f", mono)),
            inference_seconds=0.01,
            worker_seconds=0.02,
            peak_working_set=1024,
            peak_commit=2048,
        )
        (attempt / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    for module_name in (
        "suno2flp.pipeline.drum_transcription",
        "suno2flp.validator.drum_transcription",
    ):
        monkeypatch.setattr(module_name + ".read_drum_backend", read)
    monkeypatch.setattr("suno2flp.pipeline.drum_transcription.call_drum_backend", call)
    return SimpleNamespace(
        separation=tmp_path / "separation/separation.json",
        receipt=tmp_path / "separation-replay/replay.json",
        backend=backend,
        calls=calls,
        original=protocol.source,
    )


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
def test_source_bound_candidate_fresh_replay_and_annotation(drums, tmp_path):
    report = transcribe_drums(drums.separation, drums.receipt, drums.backend, tmp_path / "drums")
    path = report.root / "drum-transcription.json"
    assert len(drums.calls) == 1
    assert report.source.model_pcm == next(
        s.model for s in report.source.original.stems if s.stem == "drums"
    )
    assert [e.id for e in report.events] == ["KD.7"]
    assert report.writer_eligibility == "blocked" and report.execution_allowed is False
    before = capture_stream_input(path)
    _, loaded, _ = read_drum_candidate(path)
    assert loaded == report
    receipt = verify_drum_transcription(path, tmp_path / "drum-replay")
    assert receipt.complete_match is True and len(drums.calls) == 2
    assert capture_stream_input(path) == before
    annotation = export_drum_annotation(path, tmp_path / "annotation.json")
    assert annotation.origin == "inferred_candidate" and annotation.role == "candidate"
    assert annotation.source_audio == report.source.original.source_audio
    assert annotation.events == report.events


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
@pytest.mark.parametrize("target", ["source", "array", "recipe", "moved", "source_receipt"])
def test_current_reader_refuses_changes_and_foreign_reports(drums, tmp_path, target):
    report = transcribe_drums(drums.separation, drums.receipt, drums.backend, tmp_path / "drums")
    path = report.root / "drum-transcription.json"
    if target == "source":
        p = report.source.model_pcm.path
        p.write_bytes(p.read_bytes() + b"changed")
    elif target == "array":
        p = report.root / "native/onsets.f32"
        p.write_bytes(p.read_bytes()[:-4])
    elif target == "source_receipt":
        drums.receipt.write_text("{}", encoding="utf-8")
    elif target == "recipe":
        data = json.loads(path.read_bytes())
        data["recipe"]["files"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        moved = tmp_path / "drum-transcription.json"
        moved.write_bytes(path.read_bytes())
        path = moved
    with pytest.raises((ValueError, Suno2FLPError)):
        read_drum_candidate(path)


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
def test_late_producer_mutation_cannot_publish(drums, tmp_path, monkeypatch):
    import suno2flp.pipeline.drum_transcription as pipeline

    original = pipeline.publish_verified_report

    def late(path, content, protected, verify):
        drums.receipt.write_text("changed", encoding="utf-8")
        return original(path, content, protected, verify)

    monkeypatch.setattr(pipeline, "publish_verified_report", late)
    with pytest.raises((ValueError, Suno2FLPError)):
        transcribe_drums(drums.separation, drums.receipt, drums.backend, tmp_path / "drums")
    assert not (tmp_path / "drums/drum-transcription.json").exists()


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
def test_coherently_rehashed_logits_need_fresh_native_replay(drums, tmp_path):
    report = transcribe_drums(drums.separation, drums.receipt, drums.backend, tmp_path / "drums")
    path = report.root / "drum-transcription.json"
    raw = bytearray((report.root / "native/onsets.f32").read_bytes())
    offset = (DRUM_CLASSES.index("KD") * report.native.rows + 7) * 4
    raw[offset : offset + 4] = struct.pack("<f", 3.0)
    (report.root / "native/onsets.f32").write_bytes(raw)
    data = json.loads(path.read_bytes())
    data["native"]["files"]["onsets.f32"]["sha256"] = capture_stream_input(
        report.root / "native/onsets.f32"
    ).sha256
    (report.root / "native/result.json").write_text(json.dumps(data["native"]), encoding="utf-8")
    data["native_witnesses"] = [
        i.model_dump(mode="json") for i in capture_file_tree(report.root / "native")
    ]
    data["peaks"][0]["logit_bits"] = struct.unpack("<I", struct.pack("<f", 3.0))[0]
    path.write_text(json.dumps(data), encoding="utf-8")
    # Current arithmetic/declared hashes alone are not proof of actual model output.
    _, current, _ = read_drum_candidate(path)
    assert current.writer_eligibility == "blocked"
    before = capture_stream_input(path)
    with pytest.raises(ValueError, match="fresh native drum replay differs"):
        verify_drum_transcription(path, tmp_path / "replay")
    assert len(drums.calls) == 2
    assert capture_stream_input(path) == before
    assert not (tmp_path / "replay/drum-transcription.json").exists()
    assert not (tmp_path / "replay/replay.json").exists()


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
def test_cancellation_during_publication_guard_never_completes(drums, tmp_path, monkeypatch):
    from suno2flp.core.inference_snapshot import InferenceSnapshot

    output = tmp_path / "cancelled-drums"
    pending = output / "drum-transcription.pending.json"
    cancelled = False
    original = InferenceSnapshot.recheck

    def during_guard(self, **kwargs):
        nonlocal cancelled
        original(self, **kwargs)
        if pending.exists():
            cancelled = True

    monkeypatch.setattr(InferenceSnapshot, "recheck", during_guard)
    with pytest.raises(Suno2FLPError, match="cancel"):
        transcribe_drums(
            drums.separation, drums.receipt, drums.backend, output, should_cancel=lambda: cancelled
        )
    assert len(drums.calls) == 1 and pending.exists()
    assert not (output / "drum-transcription.json").exists()


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
def test_forged_input_peak_observation_rejected_from_current_samples(drums, tmp_path):
    report = transcribe_drums(drums.separation, drums.receipt, drums.backend, tmp_path / "drums")
    assert report.native.source_peak > 0
    path = report.root / "drum-transcription.json"
    data = json.loads(path.read_bytes())
    data["native"]["source_peak"] = 0.0
    (report.root / "native/result.json").write_text(json.dumps(data["native"]), encoding="utf-8")
    data["native_witnesses"] = [
        i.model_dump(mode="json") for i in capture_file_tree(report.root / "native")
    ]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="peak"):
        read_drum_candidate(path)


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
@pytest.mark.parametrize("mutation", ["changed-array", "new-member"])
def test_receipt_rechecks_complete_fresh_native_tree(drums, tmp_path, monkeypatch, mutation):
    import suno2flp.validator.drum_transcription as validator

    report = transcribe_drums(drums.separation, drums.receipt, drums.backend, tmp_path / "drums")
    output = tmp_path / "replay"
    publish = validator.publish_verified_report

    def late(path, content, protected, verify):
        def mutate_then_verify():
            if mutation == "changed-array":
                target = output / "native/onsets.f32"
                target.write_bytes(target.read_bytes()[:-4])
            else:
                (output / "native/unexpected.json").write_text("{}", encoding="utf-8")
            verify()

        return publish(path, content, protected, mutate_then_verify)

    monkeypatch.setattr(validator, "publish_verified_report", late)
    with pytest.raises((ValueError, Suno2FLPError)):
        verify_drum_transcription(report.root / "drum-transcription.json", output)
    assert (output / "drum-transcription.json").exists()
    assert not (output / "replay.json").exists()


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
@pytest.mark.parametrize("producer", ["candidate", "native", "source", "source-replay"])
def test_annotation_rejects_producer_roots_before_any_write(drums, tmp_path, producer):
    report = transcribe_drums(drums.separation, drums.receipt, drums.backend, tmp_path / "drums")
    roots = {
        "candidate": report.root,
        "native": report.root / "native",
        "source": drums.separation.parent / "native",
        "source-replay": drums.receipt.parent / "native",
    }
    root = roots[producer]
    before = capture_file_tree(root)
    with pytest.raises((ValueError, Suno2FLPError)):
        export_drum_annotation(report.root / "drum-transcription.json", root / "annotation.json")
    assert capture_file_tree(root) == before


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
def test_candidate_publication_rechecks_native_membership(drums, tmp_path, monkeypatch):
    import suno2flp.pipeline.drum_transcription as pipeline

    output = tmp_path / "drums"
    publish = pipeline.publish_verified_report

    def late(path, content, protected, verify):
        (output / "native/unexpected.json").write_text("{}", encoding="utf-8")
        return publish(path, content, protected, verify)

    monkeypatch.setattr(pipeline, "publish_verified_report", late)
    with pytest.raises(ValueError, match="payload changed"):
        transcribe_drums(drums.separation, drums.receipt, drums.backend, output)
    assert not (output / "drum-transcription.json").exists()
