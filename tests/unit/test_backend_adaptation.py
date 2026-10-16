"""Original recipe fixtures; no upstream backend source is distributed."""

import hashlib
import json
import subprocess

import pytest
from test_music2daw_provision import build_process
from test_template_inspection import inspection_setup as inspection_setup

from suno2flp.core.backend_models import BackendProvisionRecord
from suno2flp.core.errors import BackendProvisionError, TemplateInspectionError
from suno2flp.integrations.music2daw_provision import provision_music2daw, verify_backend

AUTHORED_SOURCE = (
    b"// Original synthetic recipe fixture, not a working upstream parser.\n"
    b"if (eventId < Enums.Event.Word) ParseByteEvent(eventId, reader);\n"
    b"var playlistRecordSize = GetPlaylistRecordSize(dataLen);\n"
)


def adapted_build(tmp_path, monkeypatch):
    from suno2flp.core import backend_adaptation

    root, calls = build_process(tmp_path, monkeypatch)
    upstream_run = subprocess.run
    monkeypatch.setattr(
        backend_adaptation, "UPSTREAM_PARSER_SHA256", hashlib.sha256(AUTHORED_SOURCE).hexdigest()
    )

    def run(args, **kwargs):
        result = upstream_run(args, **kwargs)
        if "checkout" in args:
            path = root / backend_adaptation.PARSER_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(AUTHORED_SOURCE)
        if "status" in args:
            return subprocess.CompletedProcess(
                args, 0, " M src/Monad.FLParser/ProjectParser.cs\n", ""
            )
        return result

    monkeypatch.setattr("subprocess.run", run)
    return root, calls


def test_legacy_manifest_serialization_stays_byte_structurally_compatible(inspection_setup):
    directory, *_ = inspection_setup
    raw = json.loads((directory / "backend.json").read_bytes())
    assert BackendProvisionRecord.model_validate(raw).model_dump(mode="json") == raw


def test_explicit_profile_records_deterministic_recipe_and_source_evidence(tmp_path, monkeypatch):
    from suno2flp.core.backend_adaptation import BASELINE_PATH, PARSER_PATH

    root, calls = adapted_build(tmp_path, monkeypatch)
    record = provision_music2daw(root, fl26_read_only=True)
    assert record.adaptation.profile == "fl26-26.1.7.5654-inspect-v1"
    assert (root / BASELINE_PATH).read_bytes() == AUTHORED_SOURCE
    assert (root / PARSER_PATH).read_bytes() != AUTHORED_SOURCE
    assert record.files[BASELINE_PATH] == hashlib.sha256(AUTHORED_SOURCE).hexdigest()
    assert verify_backend(root)[0] == record
    assert not any(x in call for call in calls for x in ("edit", "export", "launch"))


def test_unknown_source_fails_without_build_or_success_record(tmp_path, monkeypatch):
    root, calls = adapted_build(tmp_path, monkeypatch)
    monkeypatch.setattr("suno2flp.core.backend_adaptation.UPSTREAM_PARSER_SHA256", "0" * 64)
    with pytest.raises(BackendProvisionError):
        provision_music2daw(root, fl26_read_only=True)
    assert not (root / "backend.json").exists()
    assert not any("restore" in call or "publish" in call for call in calls)


@pytest.mark.parametrize("fault", ["source", "baseline", "notice", "recipe", "missing_record"])
def test_resigned_tampering_cannot_change_the_assessed_recipe(tmp_path, monkeypatch, fault):
    from suno2flp.core.backend_adaptation import BASELINE_PATH, NOTICE_PATH, PARSER_PATH

    root, _ = adapted_build(tmp_path, monkeypatch)
    provision_music2daw(root, fl26_read_only=True)
    data = json.loads((root / "backend.json").read_text())
    if fault == "recipe":
        data["adaptation"]["recipe_sha256"] = "0" * 64
    elif fault == "missing_record":
        data["files"].pop(BASELINE_PATH)
    else:
        name = {"source": PARSER_PATH, "baseline": BASELINE_PATH, "notice": NOTICE_PATH}[fault]
        (root / name).write_bytes(b"changed declared source")
        data["files"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if fault == "source":
            data["adaptation"]["adapted_source_sha256"] = data["files"][name]
        if fault == "baseline":
            data["adaptation"]["upstream_source_sha256"] = data["files"][name]
    (root / "backend.json").write_text(json.dumps(data))
    with pytest.raises(TemplateInspectionError):
        verify_backend(root)


def test_new_installation_cannot_be_nested_inside_an_existing_backend(tmp_path, monkeypatch):
    old = tmp_path / "old-backend"
    old.mkdir()
    (old / "backend.json").write_text("retained original manifest")
    with pytest.raises(BackendProvisionError):
        provision_music2daw(old / "new-adapter", fl26_read_only=True)
    assert not (old / "new-adapter").exists()


@pytest.mark.parametrize("name", ["new:stream", "new.", "new ", "CON", "../outside"])
def test_adaptation_refuses_ambiguous_install_paths_before_creation(tmp_path, monkeypatch, name):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with pytest.raises(BackendProvisionError, match="destination_unsafe"):
        provision_music2daw(tmp_path / name, fl26_read_only=True)


@pytest.mark.parametrize("raw", [b"wrong source", AUTHORED_SOURCE * 2])
def test_recipe_rejects_wrong_hash_or_repeated_anchors_without_changing_input(raw):
    from suno2flp.core.backend_adaptation import adapt_parser_bytes

    with pytest.raises(ValueError):
        adapt_parser_bytes(raw)
    assert raw in (b"wrong source", AUTHORED_SOURCE * 2)


@pytest.mark.parametrize(
    "fault", ["other_build", "no_version", "early_172", "old_clip", "duplicate_version"]
)
def test_exact_adapted_profile_refuses_unassessed_inputs_before_any_process(
    tmp_path, monkeypatch, fault
):
    from test_fl26_inventory import event, project

    from suno2flp.integrations.music2daw import Music2DawInspector

    root, calls = adapted_build(tmp_path, monkeypatch)
    provision_music2daw(root, fl26_read_only=True)
    version = event(199, b"26.1.7.5654\0")
    payload = version + event(172, b"\0\0\0")
    if fault == "other_build":
        payload = event(199, b"26.1.7.5655\0")
    elif fault == "no_version":
        payload = b""
    elif fault == "early_172":
        payload = event(172, b"\0\0\0\0") + version
    elif fault == "old_clip":
        payload += event(233, bytes(80))
    else:
        payload += version
    path = tmp_path / "unassessed-synthetic.flp"
    path.write_bytes(project(payload))
    count = len(calls)
    with pytest.raises(
        TemplateInspectionError, match="backend_profile_unsupported|template_inventory_invalid"
    ):
        Music2DawInspector(root).inspect(path)
    assert len(calls) == count
