import json
import subprocess

import pytest

from suno2flp.core.errors import BackendProvisionError
from suno2flp.integrations.music2daw_provision import provision_music2daw, verify_backend


def build_process(tmp_path, monkeypatch, *, wrong_pin=False, fail_restore=False):
    root = tmp_path / "isolated"
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs.get("shell", False) is False
        assert kwargs["env"]["NUGET_PACKAGES"] == str(root / "nuget")
        assert kwargs["env"]["NUGET_HTTP_CACHE_PATH"] == str(root / "nuget-http-cache")
        output = ""
        if args[-1] == "--version":
            output = "10.0.401\n"
        elif "init" in args:
            source = root / "source"
            for name in ["LICENSE", "src/Monad.FLParser/LICENSE"]:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("GPL-3.0-or-later synthetic notice")
        elif "rev-parse" in args:
            output = "0" * 40 if wrong_pin else "6def9463d6fa8636bbc81010581318a39c47d3c4"
        elif "restore" in args:
            if fail_restore:
                return subprocess.CompletedProcess(args, 1, "", "restore failed")
            for name in ["Music2Daw.Cli", "Music2Daw.Core", "Monad.FLParser"]:
                folder = root / "source/src" / name
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "packages.lock.json").write_text("{}")
            assets = root / "source/src/Music2Daw.Cli/obj/project.assets.json"
            assets.parent.mkdir()
            assets.write_text(
                json.dumps({"libraries": {"Melanchall.DryWetMidi/8.0.3": {"type": "package"}}})
            )
        elif "publish" in args:
            publish = root / "publish"
            publish.mkdir()
            for name in [
                "music2daw.dll",
                "music2daw.deps.json",
                "music2daw.runtimeconfig.json",
                "Music2Daw.Core.dll",
                "Monad.FLParser.dll",
                "Melanchall.DryWetMidi.dll",
            ]:
                (publish / name).write_bytes(b"synthetic published artifact")
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr("shutil.which", lambda name: str(tmp_path / name))
    monkeypatch.setattr("subprocess.run", run)
    return root, calls


def test_provision_exact_pin_in_new_isolated_root_and_record_hashes(tmp_path, monkeypatch):
    root, calls = build_process(tmp_path, monkeypatch)
    record = provision_music2daw(root)
    assert record.sdk_version == "10.0.401"
    assert record.packages == {"Melanchall.DryWetMidi": "8.0.3"}
    assert verify_backend(root)[0] == record
    assert any(
        "--depth" in call and "6def9463d6fa8636bbc81010581318a39c47d3c4" in call for call in calls
    )
    assert any("--use-lock-file" in call for call in calls)
    assert any("--no-restore" in call for call in calls)
    assert not any(
        "test" in call or "edit" in call or "export" in call or "launch" in call for call in calls
    )
    before = (root / "backend.json").read_bytes()
    with pytest.raises(BackendProvisionError, match="destination_exists"):
        provision_music2daw(root)
    assert (root / "backend.json").read_bytes() == before


@pytest.mark.parametrize("fault", ["wrong_pin", "fail_restore"])
def test_failed_provision_never_records_a_success(tmp_path, monkeypatch, fault):
    root, calls = build_process(tmp_path, monkeypatch, **{fault: True})
    with pytest.raises(BackendProvisionError):
        provision_music2daw(root)
    assert not (root / "backend.json").exists()
    assert not any("publish" in call for call in calls)


def test_missing_tools_do_not_create_installation(tmp_path, monkeypatch):
    root = tmp_path / "backend"
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(BackendProvisionError, match="prerequisite_missing"):
        provision_music2daw(root)
    assert not root.exists()


def test_provision_cli_uses_explicit_new_directory(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    root, _ = build_process(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["provision-music2daw", str(root)])
    assert result.exit_code == 0, result.output
    assert (root / "backend.json").exists()
