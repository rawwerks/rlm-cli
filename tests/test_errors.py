import json

from typer.testing import CliRunner

import rlm_cli.cli as cli


def test_missing_path_error_json() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        ["ask", "missing.txt", "-q", "hi", "--path", "--json"],
    )
    assert result.exit_code == 10
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 10
    assert "error" in payload
