import hashlib
import json
import struct
import subprocess

import pytest

from suno2flp.core.errors import TemplateInspectionError
from suno2flp.integrations.music2daw import Music2DawInspector


@pytest.fixture
def inspection_setup(tmp_path, monkeypatch):
    backend = tmp_path / "backend"
    backend.mkdir()
    names = [
        "publish/music2daw.dll",
        "publish/music2daw.deps.json",
        "publish/music2daw.runtimeconfig.json",
        "publish/Music2Daw.Core.dll",
        "publish/Monad.FLParser.dll",
        "publish/Melanchall.DryWetMidi.dll",
        "source/LICENSE",
        "source/src/Monad.FLParser/LICENSE",
        "global.json",
        "source/src/Music2Daw.Cli/packages.lock.json",
        "source/src/Music2Daw.Core/packages.lock.json",
        "source/src/Monad.FLParser/packages.lock.json",
        "source/src/Music2Daw.Cli/obj/project.assets.json",
    ]
    hashes = {}
    for name in names:
        path = backend / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic backend artifact")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {
        "schema_version": 1,
        "backend": "music2daw",
        "repository": "https://github.com/jihadkhawaja/flstudio-mcp",
        "revision": "6def9463d6fa8636bbc81010581318a39c47d3c4",
        "license": "GPL-3.0-or-later",
        "sdk_version": "10.0.401",
        "packages": {"Melanchall.DryWetMidi": "8.0.3"},
        "files": hashes,
    }
    (backend / "backend.json").write_text(json.dumps(record))
    template = tmp_path / "original.flp"
    # Original synthetic input only: FLhd project header and empty FLdt chunk.
    template.write_bytes(b"FLhd" + struct.pack("<IHHH", 6, 0, 1, 96) + b"FLdt\0\0\0\0")
    payload = {
        "sourcePath": str(template.resolve()),
        "flStudioVersion": "25.1.2.4896",
        "tempo": 120.0,
        "ppq": 96,
        "title": "Synthetic",
        "author": "",
        "playlistItemCount": 0,
        "channels": [{"id": 0, "name": "Synthetic"}],
        "patterns": [],
        "inserts": [],
    }
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1:] == ["--list-runtimes"]:
            return subprocess.CompletedProcess(
                args, 0, "Microsoft.NETCore.App 10.0.12 [runtime]\n", ""
            )
        assert args[1:] == [str(backend / "publish/music2daw.dll"), "inspect", str(template)]
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    monkeypatch.setattr("shutil.which", lambda name: str(tmp_path / "dotnet.exe"))
    monkeypatch.setattr("subprocess.run", run)
    return backend, template, payload, calls


def test_inspection_hashes_template_and_pinned_backend_without_writing_flp(inspection_setup):
    backend, template, payload, calls = inspection_setup
    before = template.read_bytes()
    files = sorted(str(p.relative_to(backend)) for p in backend.rglob("*") if p.is_file())
    result = Music2DawInspector(backend).inspect(template)
    assert result.template_sha256_before == hashlib.sha256(before).hexdigest()
    assert result.template_sha256_after == result.template_sha256_before
    assert (
        result.backend_manifest_sha256
        == hashlib.sha256((backend / "backend.json").read_bytes()).hexdigest()
    )
    assert result.project.model_dump(by_alias=True, mode="json") == payload
    assert result.compatibility == "unverified" and result.runtime_version == "10.0.12"
    assert result.backend.packages == {"Melanchall.DryWetMidi": "8.0.3"}
    assert template.read_bytes() == before
    assert sorted(str(p.relative_to(backend)) for p in backend.rglob("*") if p.is_file()) == files
    assert len(calls) == 2
    assert any(d.code == "fl_studio_compatibility_unverified" for d in result.diagnostics)


def test_inspection_includes_inventory_of_the_exact_input_snapshot(inspection_setup):
    backend, template, _, _ = inspection_setup
    before = template.read_bytes()
    result = Music2DawInspector(backend).inspect(template)
    inventory = getattr(result, "inventory", None)
    assert inventory is not None, "Inspection must retain a read-only byte-linked inventory"
    assert inventory.template_sha256 == hashlib.sha256(before).hexdigest()
    assert inventory.size_bytes == len(before)
    assert inventory.notes == inventory.clips == inventory.automation == []
    assert template.read_bytes() == before


def test_malformed_inventory_framing_fails_before_backend_execution(inspection_setup):
    backend, template, _, calls = inspection_setup
    raw = template.read_bytes()[:-4] + struct.pack("<I", 10) + b"short"
    template.write_bytes(raw)
    with pytest.raises(TemplateInspectionError, match="template_inventory_invalid"):
        Music2DawInspector(backend).inspect(template)
    assert not calls and template.read_bytes() == raw


@pytest.mark.parametrize(
    "fault,code",
    [
        ("no_record", "backend_manifest_invalid"),
        ("wrong_pin", "backend_manifest_invalid"),
        ("changed_dll", "backend_integrity_failed"),
        ("missing_dll", "backend_integrity_failed"),
        ("escaping_path", "backend_manifest_invalid"),
        ("missing_required_hash", "backend_manifest_invalid"),
        ("no_template", "template_unreadable"),
        ("invalid_header", "template_invalid"),
    ],
)
def test_bad_prerequisites_fail_before_any_backend_process(inspection_setup, fault, code):
    backend, template, _, calls = inspection_setup
    record_path = backend / "backend.json"
    record = json.loads(record_path.read_text())
    if fault == "no_record":
        record_path.unlink()
    elif fault == "wrong_pin":
        record["revision"] = "0" * 40
    elif fault == "changed_dll":
        (backend / "publish/music2daw.dll").write_bytes(b"changed")
    elif fault == "missing_dll":
        (backend / "publish/music2daw.dll").unlink()
    elif fault == "escaping_path":
        record["files"]["../outside"] = "0" * 64
    elif fault == "missing_required_hash":
        del record["files"]["publish/music2daw.dll"]
    elif fault == "no_template":
        template.unlink()
    elif fault == "invalid_header":
        template.write_bytes(b"not a project")
    if fault not in {"no_record"}:
        record_path.write_text(json.dumps(record))
    with pytest.raises(TemplateInspectionError) as error:
        Music2DawInspector(backend).inspect(template)
    assert error.value.code == code
    assert calls == []


@pytest.mark.parametrize(
    "result,code",
    [
        ("missing_runtime", "dotnet_runtime_missing"),
        ("process_failure", "backend_process_failed"),
        ("timeout", "backend_timeout"),
        ("not_json", "backend_output_invalid"),
        ("wrong_ppq", "backend_output_invalid"),
        ("wrong_path", "backend_output_invalid"),
        ("changed_template", "template_changed"),
        ("changed_on_error", "template_changed"),
        ("changed_backend", "backend_integrity_failed"),
    ],
)
def test_runtime_and_process_failures_never_become_success(
    inspection_setup, monkeypatch, result, code
):
    backend, template, payload, _ = inspection_setup

    def run(args, **kwargs):
        if args[1:] == ["--list-runtimes"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "Microsoft.NETCore.App 9.0.1 [runtime]"
                if result == "missing_runtime"
                else "Microsoft.NETCore.App 10.0.12 [runtime]",
                "",
            )
        if result == "timeout":
            raise subprocess.TimeoutExpired(args, 30)
        if result in {"changed_template", "changed_on_error"}:
            template.write_bytes(b"unexpected edit")
        if result == "changed_backend":
            (backend / "publish/music2daw.dll").write_bytes(b"changed")
        if result == "wrong_ppq":
            payload["ppq"] = 480
        if result == "wrong_path":
            payload["sourcePath"] = str(template.parent / "other.flp")
        return subprocess.CompletedProcess(
            args,
            1 if result in {"process_failure", "changed_on_error"} else 0,
            "invalid" if result == "not_json" else json.dumps(payload),
            "synthetic failure",
        )

    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(TemplateInspectionError) as error:
        Music2DawInspector(backend).inspect(template)
    assert error.value.code == code


def test_missing_dotnet_is_explicit(inspection_setup, monkeypatch):
    backend, template, _, calls = inspection_setup
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(TemplateInspectionError, match="dotnet_missing"):
        Music2DawInspector(backend).inspect(template)
    assert not calls


@pytest.mark.parametrize("channels,ppq", [(0, 96), (1001, 96), (1, 32768)])
def test_header_limits_of_pinned_parser_fail_before_process(inspection_setup, channels, ppq):
    backend, template, _, calls = inspection_setup
    template.write_bytes(b"FLhd" + struct.pack("<IHHH", 6, 0, channels, ppq) + b"FLdt\0\0\0\0")
    with pytest.raises(TemplateInspectionError, match="template_invalid"):
        Music2DawInspector(backend).inspect(template)
    assert not calls


@pytest.mark.parametrize(
    "field", ["schema_version", "backend", "repository", "revision", "license", "assets_hash"]
)
def test_incomplete_record_cannot_invent_backend_provenance(inspection_setup, field):
    backend, template, _, calls = inspection_setup
    path = backend / "backend.json"
    record = json.loads(path.read_text())
    if field == "assets_hash":
        del record["files"]["source/src/Music2Daw.Cli/obj/project.assets.json"]
    else:
        del record[field]
    path.write_text(json.dumps(record))
    with pytest.raises(TemplateInspectionError, match="backend_manifest_invalid"):
        Music2DawInspector(backend).inspect(template)
    assert not calls


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_nested_backend_metadata_is_rejected(inspection_setup, value):
    backend, template, payload, _ = inspection_setup
    payload["channels"][0]["nested"] = {"values": [value]}
    with pytest.raises(TemplateInspectionError, match="backend_output_invalid"):
        Music2DawInspector(backend).inspect(template)


def test_report_alternate_data_stream_is_rejected_before_inspection(inspection_setup, monkeypatch):
    from pathlib import Path

    from typer.testing import CliRunner

    from suno2flp.cli import app

    backend, template, _, calls = inspection_setup
    output = str(template) + ":inspection.json"
    original_open = Path.open

    def prevent_stream_write(path, *args, **kwargs):
        if path.name.endswith(":inspection.json"):
            raise AssertionError("Report attempted an NTFS alternate data stream write")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", prevent_stream_write)
    result = CliRunner().invoke(
        app, ["inspect-template", str(template), "--backend-dir", str(backend), "--output", output]
    )
    assert result.exit_code == 1
    assert "Error:" in result.output and not calls


def test_template_cli_json_report_and_overwrite_protection(inspection_setup, tmp_path):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    backend, template, _, calls = inspection_setup
    runner = CliRunner()
    args = ["inspect-template", str(template), "--backend-dir", str(backend)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert (
        json.loads(result.stdout)["template_sha256_before"]
        == hashlib.sha256(template.read_bytes()).hexdigest()
    )
    output = tmp_path / "inspection.json"
    result = runner.invoke(app, [*args, "--output", str(output)])
    assert result.exit_code == 0, result.output
    saved = output.read_bytes()
    calls.clear()
    assert runner.invoke(app, [*args, "--output", str(output)]).exit_code == 1
    assert not calls and output.read_bytes() == saved
    assert runner.invoke(app, [*args, "--output", str(backend / "new.json")]).exit_code == 1
    assert not calls and not (backend / "new.json").exists()
    assert runner.invoke(app, [*args, "--output", str(template)]).exit_code == 1


def test_template_cli_missing_prerequisite_never_creates_report(inspection_setup, tmp_path):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    backend, template, _, _ = inspection_setup
    (backend / "backend.json").unlink()
    output = tmp_path / "never.json"
    result = CliRunner().invoke(
        app,
        ["inspect-template", str(template), "--backend-dir", str(backend), "--output", str(output)],
    )
    assert result.exit_code == 1 and "backend_manifest_invalid" in result.output
    assert not output.exists()
