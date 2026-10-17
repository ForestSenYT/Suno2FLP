"""Thin CLI routing; no host, plugin or external asset."""

from types import SimpleNamespace

from typer.testing import CliRunner

from suno2flp.cli import app


def test_export_audio_flp_cli_preserves_candidate_status(monkeypatch, tmp_path):
    import suno2flp.cli_audio_flp as command

    def export(*args):
        assert args == (
            tmp_path / "midi.json",
            tmp_path / "base.flp",
            tmp_path / "sampler.flp",
            tmp_path / "new",
        )
        return SimpleNamespace(
            root=tmp_path / "new", status="unqualified_candidate", blockers=["host-unverified"]
        )

    monkeypatch.setattr(command, "export_audio_flp", export)
    result = CliRunner().invoke(
        app,
        [
            "export-audio-flp",
            str(tmp_path / "midi.json"),
            "--base",
            str(tmp_path / "base.flp"),
            "--sampler",
            str(tmp_path / "sampler.flp"),
            "--output",
            str(tmp_path / "new"),
        ],
    )
    assert result.exit_code == 0 and "unqualified_candidate" in result.stdout
    assert "host-unverified" in result.stdout


def test_export_audio_flp_cli_reports_explicit_prerequisite_failure(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "export-audio-flp",
            str(tmp_path / "none.json"),
            "--base",
            str(tmp_path / "none.flp"),
            "--sampler",
            str(tmp_path / "sampler.flp"),
            "--output",
            str(tmp_path / "new"),
        ],
    )
    assert result.exit_code == 1 and not (tmp_path / "new").exists()
