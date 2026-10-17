"""CLI exposes discovery, absent prerequisites and API errors distinctly."""

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from suno2flp import cli_windows_audio
from suno2flp.cli import app


@pytest.mark.parametrize(
    "status,expected",
    [
        ("output_absent", 2),
        ("default_absent", 2),
        ("output_detected", 0),
    ],
)
def test_discovery_exit_codes_never_claim_host_qualification(
    tmp_path, monkeypatch, status, expected
):
    output = tmp_path / "new observation"

    def inspect(path):
        assert path == output
        return SimpleNamespace(
            root=output,
            assessment=SimpleNamespace(
                status=status,
                active_count=0 if status == "output_absent" else 1,
                default_roles=[0, 1, 2] if status == "output_detected" else [],
            ),
            host_compatibility="unverified",
            execution_allowed=False,
        )

    monkeypatch.setattr(cli_windows_audio, "inspect_windows_audio", inspect)
    result = CliRunner().invoke(app, ["inspect-windows-audio", "--output", str(output)])
    assert result.exit_code == expected, result.output
    assert status in result.output and '"execution_allowed": false' in result.output
    assert '"host_compatibility": "unverified"' in result.output


def test_api_failure_cannot_be_reported_as_missing_device(tmp_path, monkeypatch):
    def inspect(path):
        raise OSError("Core Audio unavailable")

    monkeypatch.setattr(cli_windows_audio, "inspect_windows_audio", inspect)
    result = CliRunner().invoke(app, ["inspect-windows-audio", "--output", str(tmp_path / "new")])
    assert result.exit_code == 1
    assert "Core Audio unavailable" in result.output
    assert "output_absent" not in result.output
