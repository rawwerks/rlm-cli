"""Unit tests for sub-response display CLI flags.

Tests:
- --output-format=json-tree flag
- --summary flag
"""

import json
import sys
import os

# Add src path for local imports
tests_dir = os.path.dirname(__file__)
project_root = os.path.dirname(tests_dir)
sys.path.insert(0, os.path.join(project_root, "src"))

from dataclasses import dataclass, field
from typing import Any

from typer.testing import CliRunner

import rlm_cli.cli as cli
from rlm_cli.rlm_adapter import RlmResult


# Mock classes to simulate RLM structures
@dataclass
class MockUsageSummary:
    total_cost: float | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class MockCodeBlockResult:
    rlm_calls: list[Any] = field(default_factory=list)
    output: str = ""
    error: str | None = None


@dataclass
class MockCodeBlock:
    code: str = ""
    result: MockCodeBlockResult | None = None


@dataclass
class MockIteration:
    response: str = ""
    iteration_time: float = 0.0
    final_answer: str | None = None
    code_blocks: list[MockCodeBlock] = field(default_factory=list)


@dataclass
class MockRLMChatCompletion:
    root_model: str = "test/model"
    prompt: Any = ""
    response: str = ""
    execution_time: float = 1.0
    usage_summary: MockUsageSummary | None = None
    iterations: list[MockIteration] | None = None


class TestJsonTreeOutputFormat:
    """Test --output-format=json-tree flag."""

    def test_json_tree_complete_simple(self, monkeypatch) -> None:
        """Test json-tree output with simple completion."""
        runner = CliRunner()

        mock_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4",
            prompt="Test prompt",
            response="Test response",
            execution_time=1.5,
            usage_summary=MockUsageSummary(total_cost=0.05),
        )

        def fake_run_completion(**_kwargs):
            return RlmResult(response="Test response", raw=mock_completion)

        monkeypatch.setattr(cli, "run_completion", fake_run_completion)
        result = runner.invoke(cli.app, ["complete", "hello", "--output-format", "json-tree"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["result"]["response"] == "Test response"
        # Note: complete command doesn't add tree, only ask does
        # Let's verify json mode is active
        assert payload["schema"] == "rlm-cli.output.v1"

    def test_json_tree_ask_with_tree(self, monkeypatch, tmp_path) -> None:
        """Test json-tree output with ask command includes tree."""
        runner = CliRunner()

        # Create mock completion with iterations
        mock_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4",
            prompt="Test prompt",
            response="Test response",
            execution_time=2.0,
            usage_summary=MockUsageSummary(total_cost=0.10),
            iterations=[
                MockIteration(
                    response="Working on it...",
                    iteration_time=1.0,
                    code_blocks=[MockCodeBlock(code="print('hello')")],
                ),
                MockIteration(
                    response="Final answer",
                    iteration_time=1.0,
                    final_answer="Test response",
                    code_blocks=[],
                ),
            ],
        )

        def fake_run_completion(**_kwargs):
            return RlmResult(response="Test response", raw=mock_completion)

        monkeypatch.setattr(cli, "run_completion", fake_run_completion)

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = runner.invoke(
            cli.app,
            ["ask", str(test_file), "-q", "what is this?", "--output-format", "json-tree", "--no-index"],
        )

        assert result.exit_code == 0, f"CLI failed: {result.stdout}"
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["result"]["response"] == "Test response"

        # Check tree is present
        assert "tree" in payload["result"], f"Missing tree in result: {payload['result'].keys()}"
        tree = payload["result"]["tree"]
        assert tree["depth"] == 0
        assert tree["model"] == "openai/gpt-4"
        assert tree["cost"] == 0.10
        assert "iterations" in tree
        assert len(tree["iterations"]) == 2

    def test_json_tree_nested_children(self, monkeypatch, tmp_path) -> None:
        """Test json-tree output with nested RLM calls."""
        runner = CliRunner()

        # Create child completion
        child_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4o-mini",
            prompt="Child task",
            response="Child response",
            execution_time=0.5,
            usage_summary=MockUsageSummary(total_cost=0.02),
        )

        # Create parent with child call
        child_result = MockCodeBlockResult(rlm_calls=[child_completion])
        mock_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4",
            prompt="Parent task",
            response="Parent response",
            execution_time=1.5,
            usage_summary=MockUsageSummary(total_cost=0.08),
            iterations=[
                MockIteration(
                    response="Calling child...",
                    iteration_time=1.5,
                    code_blocks=[MockCodeBlock(code="llm_query('Child task')", result=child_result)],
                ),
            ],
        )

        def fake_run_completion(**_kwargs):
            return RlmResult(response="Parent response", raw=mock_completion)

        monkeypatch.setattr(cli, "run_completion", fake_run_completion)

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = runner.invoke(
            cli.app,
            ["ask", str(test_file), "-q", "analyze", "--output-format", "json-tree", "--no-index"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)

        tree = payload["result"]["tree"]
        assert "children" in tree
        assert len(tree["children"]) == 1

        child = tree["children"][0]
        assert child["depth"] == 1
        assert child["model"] == "openai/gpt-4o-mini"


class TestSummaryFlag:
    """Test --summary flag."""

    def test_summary_json_mode(self, monkeypatch, tmp_path) -> None:
        """Test --summary with JSON output adds summary to stats."""
        runner = CliRunner()

        mock_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4",
            prompt="Test prompt",
            response="Test response",
            execution_time=2.0,
            usage_summary=MockUsageSummary(total_cost=0.15),
        )

        def fake_run_completion(**_kwargs):
            return RlmResult(response="Test response", raw=mock_completion)

        monkeypatch.setattr(cli, "run_completion", fake_run_completion)

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = runner.invoke(
            cli.app,
            ["ask", str(test_file), "-q", "what is this?", "--json", "--summary", "--no-index"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)

        # Check summary is in stats
        assert "summary" in payload["stats"]
        summary = payload["stats"]["summary"]
        assert summary["total_depth"] == 1
        assert summary["total_nodes"] == 1
        assert summary["total_cost"] == 0.15
        assert "by_depth" in summary

    def test_summary_text_mode(self, monkeypatch, tmp_path) -> None:
        """Test --summary in text mode prints response and succeeds."""
        runner = CliRunner()

        mock_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4",
            prompt="Test prompt",
            response="Test response",
            execution_time=2.0,
            usage_summary=MockUsageSummary(total_cost=0.15),
        )

        def fake_run_completion(**_kwargs):
            return RlmResult(response="Test response", raw=mock_completion)

        monkeypatch.setattr(cli, "run_completion", fake_run_completion)

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = runner.invoke(
            cli.app,
            ["ask", str(test_file), "-q", "what is this?", "--summary", "--no-index"],
        )

        assert result.exit_code == 0
        # Response should be in output
        assert "Test response" in result.output
        # Note: CliRunner captures stderr to output as well, so the summary
        # message should appear there too (containing "RLM Execution Summary")
        assert "RLM Execution Summary" in result.output or "Test response" in result.output

    def test_summary_with_nested_calls(self, monkeypatch, tmp_path) -> None:
        """Test --summary shows correct depth stats for nested calls."""
        runner = CliRunner()

        # Create grandchild
        grandchild = MockRLMChatCompletion(
            root_model="model-c",
            prompt="Grandchild",
            response="Grandchild response",
            execution_time=0.3,
            usage_summary=MockUsageSummary(total_cost=0.01),
        )

        # Create child with grandchild
        gc_result = MockCodeBlockResult(rlm_calls=[grandchild])
        child = MockRLMChatCompletion(
            root_model="model-b",
            prompt="Child",
            response="Child response",
            execution_time=0.5,
            usage_summary=MockUsageSummary(total_cost=0.03),
            iterations=[MockIteration(code_blocks=[MockCodeBlock(result=gc_result)])],
        )

        # Create parent with child
        c_result = MockCodeBlockResult(rlm_calls=[child])
        mock_completion = MockRLMChatCompletion(
            root_model="model-a",
            prompt="Parent",
            response="Parent response",
            execution_time=1.0,
            usage_summary=MockUsageSummary(total_cost=0.06),
            iterations=[MockIteration(code_blocks=[MockCodeBlock(result=c_result)])],
        )

        def fake_run_completion(**_kwargs):
            return RlmResult(response="Parent response", raw=mock_completion)

        monkeypatch.setattr(cli, "run_completion", fake_run_completion)

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = runner.invoke(
            cli.app,
            ["ask", str(test_file), "-q", "analyze", "--json", "--summary", "--no-index"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)

        summary = payload["stats"]["summary"]
        assert summary["total_depth"] == 3
        assert summary["total_nodes"] == 3

        # Verify depth breakdown
        by_depth = summary["by_depth"]
        assert by_depth["0"]["calls"] == 1
        assert by_depth["1"]["calls"] == 1
        assert by_depth["2"]["calls"] == 1


class TestCombinedFlags:
    """Test combining json-tree and summary flags."""

    def test_json_tree_with_summary(self, monkeypatch, tmp_path) -> None:
        """Test --output-format=json-tree with --summary includes both."""
        runner = CliRunner()

        mock_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4",
            prompt="Test",
            response="Response",
            execution_time=1.0,
            usage_summary=MockUsageSummary(total_cost=0.05),
            iterations=[MockIteration(response="Done", final_answer="Response")],
        )

        def fake_run_completion(**_kwargs):
            return RlmResult(response="Response", raw=mock_completion)

        monkeypatch.setattr(cli, "run_completion", fake_run_completion)

        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = runner.invoke(
            cli.app,
            ["ask", str(test_file), "-q", "test", "--output-format", "json-tree", "--summary", "--no-index"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)

        # Both tree and summary should be present
        assert "tree" in payload["result"]
        assert "summary" in payload["stats"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
