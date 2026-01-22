import os

import pytest
from typer.testing import CliRunner

import rlm_cli.cli as cli

DEFAULT_BACKEND = "openrouter"
DEFAULT_MODEL = "z-ai/glm-4.7:turbo"


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RLM_CLI_INTEGRATION") != "1",
    reason="Integration tests disabled.",
)
def test_complete_integration() -> None:
    runner = CliRunner()
    backend = os.getenv("RLM_CLI_INTEGRATION_BACKEND", DEFAULT_BACKEND)
    model = os.getenv("RLM_CLI_INTEGRATION_MODEL", DEFAULT_MODEL)
    result = runner.invoke(
        cli.app,
        ["complete", "Say hello", "--json", "--backend", backend, "--model", model],
    )
    assert result.exit_code == 0
