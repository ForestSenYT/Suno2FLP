"""Actual numeric readers with tiny authored signals; only native inference is fake."""

import json
from pathlib import Path

import pytest
from test_separation_pipeline import protocol as protocol
from test_separation_pipeline import recipe as recipe
from test_separation_runtime_config import SETTINGS

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.pipeline.separation import separate_audio
from suno2flp.validator.separation import verify_separation


def test_generated_context_is_owned_witnessed_and_freshly_replayed(protocol, tmp_path):
    original = capture_stream_input(protocol.source)
    report = separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    assert report.schema_version == 2 and report.profile.endswith("-v2")
    assert report.runtime_context.settings.model_dump() == SETTINGS
    assert report.runtime_context.file == capture_stream_input(
        tmp_path / "candidate/native/keras-cache/keras.json"
    )
    assert report.runtime_context.file in report.witnesses()
    assert verify_separation(tmp_path / "candidate/separation.json", tmp_path / "replay") == report
    assert capture_stream_input(protocol.source) == original
    assert not report.execution_allowed and report.writer_eligibility == "blocked"


@pytest.mark.parametrize(
    "kind", ["missing", "unsupported", "duplicate", "extra-setting", "oversized", "extra-native"]
)
def test_missing_unsupported_or_unlisted_runtime_evidence_blocks_completion(
    protocol, tmp_path, monkeypatch, kind
):
    def process(argv, **kwargs):
        returned = protocol.process(argv, **kwargs)
        config = Path(argv[-1]).parent / "keras-cache/keras.json"
        if kind == "missing":
            config.unlink()
        elif kind == "duplicate":
            config.write_text(
                '{"floatx":"float32","floatx":"float32","epsilon":1e-7,"backend":"tensorflow","image_data_format":"channels_last"}',
                encoding="utf-8",
            )
        elif kind == "oversized":
            config.write_bytes(b" " * 65537)
        elif kind == "extra-native":
            (config.parent / "unlisted.json").write_text("{}", encoding="utf-8")
        else:
            values = {**SETTINGS, **({"epsilon": 1e-6} if kind == "unsupported" else {"extra": 1})}
            config.write_text(json.dumps(values), encoding="utf-8")
        return returned

    monkeypatch.setattr(protocol.backend_module, "run_bounded_process", process)
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    assert not (tmp_path / "candidate/separation.json").exists()


@pytest.mark.parametrize("kind", ["config", "member"])
def test_runtime_changes_after_pending_never_publish(protocol, tmp_path, monkeypatch, kind):
    import suno2flp.core.report_publication as publication

    pending = tmp_path / "candidate/separation.pending.json"
    write = publication.new_report

    def late(path, *args, **kwargs):
        write(path, *args, **kwargs)
        if path == pending:
            config = pending.parent / "native/keras-cache/keras.json"
            if kind == "config":
                config.write_bytes(config.read_bytes() + b" ")
            else:
                (config.parent / "unlisted.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(publication, "new_report", late)
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        separate_audio(protocol.decode, protocol.backend, pending.parent)
    assert pending.exists() and not pending.with_name("separation.json").exists()


def test_replay_compares_complete_config_bytes_even_with_same_settings(protocol, tmp_path):
    separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    path = tmp_path / "candidate/separation.json"
    data = json.loads(path.read_bytes())
    config = tmp_path / "candidate/native/keras-cache/keras.json"
    config.write_bytes(config.read_bytes() + b" ")
    data["runtime_context"]["file"] = capture_stream_input(config).model_dump(mode="json")
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Fresh separation replay disagrees"):
        verify_separation(path, tmp_path / "replay")
    assert not (tmp_path / "replay/replay.json").exists()


def test_legacy_metadata_cannot_be_backfilled_or_replayed_as_v2(protocol, tmp_path, monkeypatch):
    separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    path = tmp_path / "candidate/separation.json"
    data = json.loads(path.read_bytes())
    data.update(
        schema_version=1,
        profile="source-bound-spleeter-four-stem-candidate-v1",
        runtime_context=None,
    )
    path.write_text(json.dumps(data), encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("Legacy metadata must fail before new inference")

    monkeypatch.setattr("suno2flp.pipeline.separation.separate_audio", forbidden)
    with pytest.raises(ValueError, match="Legacy separation metadata"):
        verify_separation(path, tmp_path / "replay")
    assert not (tmp_path / "replay").exists()


def test_consumers_reject_rebound_receipt_with_changed_config_bytes(protocol, tmp_path):
    from suno2flp.validator.stem_transcription import read_lineage_snapshots

    separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    original = tmp_path / "candidate/separation.json"
    verify_separation(original, tmp_path / "replay")
    replay = tmp_path / "replay/separation.json"
    data = json.loads(replay.read_bytes())
    config = tmp_path / "replay/native/keras-cache/keras.json"
    config.write_bytes(config.read_bytes() + b" ")
    data["runtime_context"]["file"] = capture_stream_input(config).model_dump(mode="json")
    replay.write_text(json.dumps(data), encoding="utf-8")
    receipt = tmp_path / "replay/replay.json"
    data = json.loads(receipt.read_bytes())
    data["replay_report"] = capture_stream_input(replay).model_dump(mode="json")
    receipt.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Complete separation replay evidence differs"):
        read_lineage_snapshots(capture_stream_input(original), capture_stream_input(receipt))


@pytest.mark.parametrize("consumer", ["stem", "drum"])
@pytest.mark.parametrize("changed", ["candidate", "replay"])
def test_v2_owned_proofs_retain_complete_native_membership(protocol, tmp_path, consumer, changed):
    from suno2flp.validator.drum_source import load_drum_source
    from suno2flp.validator.drum_transcription import drum_recipe
    from suno2flp.validator.stem_snapshot import capture_stem_evidence
    from suno2flp.validator.stem_transcription import read_separation, stem_recipe
    from suno2flp.validator.transcription import transcription_recipe

    original = separate_audio(protocol.decode, protocol.backend, tmp_path / "candidate")
    path = tmp_path / "candidate/separation.json"
    verify_separation(path, tmp_path / "replay")
    if consumer == "stem":
        _, replay = read_separation(tmp_path / "replay/separation.json")
        guard = capture_stem_evidence(
            original,
            replay,
            [],
            recipe=stem_recipe(),
            pitch_recipe=transcription_recipe(),
            identities=[],
        )
        recheck = guard.recheck
    else:
        recipe = drum_recipe()
        guard = load_drum_source(path, tmp_path / "replay/replay.json", recipe)

        def recheck():
            return guard.recheck(recipe)

    (tmp_path / changed / "native/keras-cache/extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="complete inference payload changed"):
        recheck()
