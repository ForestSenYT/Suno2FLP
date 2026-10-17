"""Explicit development commands distinguish preparation from model and music proof."""

from typer.testing import CliRunner

from suno2flp.cli import app


def test_runtime_commands_are_available_without_native_dependencies() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "prepare-spleeter" in result.stdout and "verify-spleeter" in result.stdout


def test_missing_runtime_fails_without_creating_probe(tmp_path) -> None:
    result = CliRunner().invoke(
        app, ["verify-spleeter", str(tmp_path / "missing"), "--output", str(tmp_path / "probe")]
    )
    assert result.exit_code == 1 and "Error:" in result.output
    assert not (tmp_path / "probe").exists()


def test_existing_output_is_preserved(tmp_path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "original.txt"
    marker.write_bytes(b"unchanged")
    result = CliRunner().invoke(
        app, ["prepare-spleeter", "--artifacts", str(tmp_path), "--output", str(output)]
    )
    assert result.exit_code == 1 and "Error:" in result.output
    assert list(output.iterdir()) == [marker] and marker.read_bytes() == b"unchanged"
