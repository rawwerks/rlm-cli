import json

from typer.testing import CliRunner

import rlm_cli.cli as cli
from rlm_cli.rlm_adapter import RlmResult


def test_json_output_complete(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run_completion(**_kwargs):
        return RlmResult(response="ok", raw={})

    monkeypatch.setattr(cli, "run_completion", fake_run_completion)
    result = runner.invoke(cli.app, ["complete", "hello", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == "rlm-cli.output.v1"
    assert payload["ok"] is True
    assert payload["result"]["response"] == "ok"
