import os

import pytest
from typer.testing import CliRunner

import rlm_cli.cli as cli


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RLM_CLI_INTEGRATION") != "1",
    reason="Integration tests disabled.",
)
def test_complete_integration() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        ["complete", "Say hello", "--json"],
    )
    assert result.exit_code == 0
