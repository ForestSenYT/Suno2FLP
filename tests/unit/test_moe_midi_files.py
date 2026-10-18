"""Exclusive publication tests; only the unavailable native process is substituted."""

import json
from pathlib import Path

import pytest
from test_moe_midi import native_note
from test_yourmt3_moe_pipeline import setup

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.yourmt3 import FrameInterval
from suno2flp.pipeline import moe_midi as service
from suno2flp.pipeline.yourmt3_moe import transcribe_yourmt3_moe
from suno2flp.validator import yourmt3_moe as source_validator


@pytest.fixture
def producer(tmp_path, monkeypatch):
    notes = {
        0: [native_note().model_dump(), native_note(program=2).model_dump()],
        11: [native_note(program=100).model_dump()],
    }
    source, before, backend, calls = setup(tmp_path, monkeypatch, notes=notes)
    (backend / "packages").mkdir()
    record = transcribe_yourmt3_moe(
        tmp_path / "decode/decode.json",
        backend,
        tmp_path / "producer",
        [FrameInterval(start_frame=0, end_frame=98304)],
    )
    calls.clear()
    return record, source, before, calls


def test_complete_bundle_replays_one_decoder_not_inference(producer, tmp_path):
    record, source, before, calls = producer
    output = tmp_path / "bundle"
    result = service.export_moe_midi(record.root / "yourmt3-moe.json", output)
    assert calls == ["decode"]
    assert len(result.files) == 3
    assert [(f.source_channel, f.model_program) for f in result.files] == [
        (0, 0),
        (0, 2),
        (11, 100),
    ]
    assert result.score.inputs.model_channels[11].notes[0].program == 100
    assert result.score.writer_eligibility == "blocked" and not result.score.execution_allowed
    assert service.verify_moe_midi_export(output / "moe-midi.json") == result
    assert calls == ["decode", "decode"]
    assert capture_stream_input(source) == before


@pytest.mark.parametrize("path", ["existing", "producer/nested", "backend/nested", "bad.. "])
def test_unsafe_output_fails_before_source_calls(producer, tmp_path, monkeypatch, path):
    record, _, _, _ = producer
    (tmp_path / "existing").mkdir()

    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe output reached expensive source verification")

    monkeypatch.setattr(service, "collect_verified_moe", forbidden)
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        service.export_moe_midi(record.root / "yourmt3-moe.json", tmp_path / path)


@pytest.mark.parametrize(
    "change", ["midi", "source", "raw", "payload", "recipe", "cancel", "companion"]
)
def test_late_failure_has_no_completion(producer, tmp_path, monkeypatch, change):
    record, source, _, _ = producer
    output = tmp_path / "bundle"
    publish = service.publish_verified_report
    cancelled = False

    def late(path, content, protected, verify):
        nonlocal cancelled
        if change == "midi":
            next((output / "notes").glob("*.mid")).write_bytes(b"corrupted fixture")
        elif change == "source":
            source.write_bytes(source.read_bytes() + b"changed fixture")
        elif change == "raw":
            record.raw.path.write_bytes(b"{}")
        elif change == "payload":
            (record.backend.path.parent / "packages/invented.py").write_bytes(b"extra")
        elif change == "recipe":
            original = service.moe_midi_recipe

            def changed():
                recipe = original()
                recipe.python_version = "changed"
                return recipe

            monkeypatch.setattr(service, "moe_midi_recipe", changed)
        elif change == "companion":
            (output / "README.zh-CN.txt").write_bytes(b"changed companion")
        else:
            cancelled = True
        return publish(path, content, protected, verify)

    monkeypatch.setattr(service, "publish_verified_report", late)
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        service.export_moe_midi(
            record.root / "yourmt3-moe.json", output, should_cancel=lambda: cancelled
        )
    assert not (output / "moe-midi.json").exists()


def test_companion_failure_precedes_publication(producer, tmp_path, monkeypatch):
    record, _, _, _ = producer
    original = Path.open

    def fail(path, *args, **kwargs):
        if path.name == "README.zh-CN.txt":
            raise OSError("synthetic companion write failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    output = tmp_path / "bundle"
    with pytest.raises(OSError):
        service.export_moe_midi(record.root / "yourmt3-moe.json", output)
    assert not (output / "moe-midi.json").exists()
    assert not (output / "moe-midi.pending.json").exists()


@pytest.mark.parametrize(
    "change", ["occurrence", "label", "path", "extra", "missing", "policy", "negative-zero"]
)
def test_saved_manifest_or_inventory_mutation_is_refused(producer, tmp_path, change):
    record, _, _, _ = producer
    output = tmp_path / "bundle"
    result = service.export_moe_midi(record.root / "yourmt3-moe.json", output)
    path = output / "moe-midi.json"
    data = json.loads(path.read_bytes())
    if change == "occurrence":
        data["score"]["parts"][0]["notes"][0]["source_index"] = 1
    elif change == "label":
        data["score"]["parts"][-1]["instrument_group_hint"] = "GM100"
    elif change == "path":
        data["files"][0]["midi"]["path"] = str(tmp_path / "outside.mid")
    elif change == "policy":
        data["score"]["blockers"] = []
    elif change == "negative-zero":
        data["score"]["inputs"]["model_channels"][0]["notes"][0]["onset"] = -0.0
    elif change == "extra":
        (output / "notes/extra.mid").write_bytes(b"extra fixture")
    else:
        result.files[0].midi.path.unlink()
    if change not in ("extra", "missing"):
        # Modifying a synthetic completion file only, never real reports.
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        service.verify_moe_midi_export(path)


def test_retained_evidence_owns_its_candidate_and_native_snapshots(producer):
    record, source, before, _ = producer
    receipt = source_validator.collect_verified_moe(record.root / "yourmt3-moe.json")
    candidate = receipt.candidate
    candidate.frames += 1
    native = receipt.native
    native.channels[0].notes[0].pitch = 70
    assert receipt.candidate.frames == record.frames
    assert receipt.native.channels[0].notes[0].pitch == 60
    receipt.recheck()
    assert capture_stream_input(source) == before


def test_source_collector_rejects_token_disagreement(producer, monkeypatch):
    record, _, _, _ = producer
    invoke = source_validator.call_yourmt3_moe_backend

    def changed(backend, attempt, request):
        result = invoke(backend, attempt, request)
        data = json.loads(result.path.read_bytes())
        data["channels"][0]["notes"][0]["pitch"] = 61
        result.path.write_text(json.dumps(data), encoding="utf-8")
        return capture_stream_input(result.path)

    monkeypatch.setattr(source_validator, "call_yourmt3_moe_backend", changed)
    with pytest.raises(ValueError, match="Independent MoE token"):
        source_validator.collect_verified_moe(record.root / "yourmt3-moe.json")


@pytest.mark.parametrize("change", ["runtime", "backend", "raw", "payload"])
def test_retained_receipt_rechecks_all_evidence(producer, change):
    record, _, _, _ = producer
    receipt = source_validator.collect_verified_moe(record.root / "yourmt3-moe.json")
    if change == "payload":
        (receipt.backend.root / "packages/extra.py").write_bytes(b"fixture")
    else:
        path = {
            "runtime": receipt.backend.python.path,
            "backend": record.backend.path,
            "raw": record.raw.path,
        }[change]
        path.write_bytes(path.read_bytes() + b"changed fixture")
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        receipt.recheck()


@pytest.mark.parametrize("phase", ["export", "verify"])
@pytest.mark.parametrize("extra", ["notes/extra.mid", "extra.txt"])
def test_output_inventory_is_current_after_slow_source_recheck(
    producer, tmp_path, monkeypatch, phase, extra
):
    record, _, _, _ = producer
    output = tmp_path / "bundle"
    if phase == "verify":
        service.export_moe_midi(record.root / "yourmt3-moe.json", output)
    original = source_validator.VerifiedMoESource.recheck

    def late(self, *, should_cancel=None):
        original(self, should_cancel=should_cancel)
        (output / extra).write_bytes(b"unexpected synthetic output")

    monkeypatch.setattr(source_validator.VerifiedMoESource, "recheck", late)
    with pytest.raises(ValueError, match="inventory"):
        if phase == "export":
            service.export_moe_midi(record.root / "yourmt3-moe.json", output)
        else:
            service.verify_moe_midi_export(output / "moe-midi.json")
    if phase == "export":
        assert not (output / "moe-midi.json").exists()
