import re

from typer.testing import CliRunner

import rlm_cli.cli as cli


def test_root_help_includes_examples() -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.stdout)
    assert "Examples:" in output
    assert "rlm ask . -q" in output


def test_ask_help_includes_input_modes() -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["ask", "--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.stdout)
    assert "Input modes:" in output


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)
