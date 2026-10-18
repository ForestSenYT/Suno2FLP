from typer.testing import CliRunner

from suno2flp.cli import app


def test_fixed_backend_commands_are_explicit_and_do_not_start_inference():
    runner = CliRunner()
    for command, flag in [
        ("prepare-yourmt3-backend", "--artifacts"),
        ("transcribe-yourmt3", "--intervals"),
        ("verify-yourmt3", "--help"),
    ]:
        result = runner.invoke(app, [command, "--help"], color=False)
        assert result.exit_code == 0, result.output
        assert flag in result.output
