from typer.testing import CliRunner

import rlm_cli.cli as cli


def test_root_help_includes_examples() -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "rlm ask . -q" in result.stdout


def test_ask_help_includes_input_modes() -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["ask", "--help"])
    assert result.exit_code == 0
    assert "Input modes:" in result.stdout
