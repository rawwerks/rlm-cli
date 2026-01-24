"""Unit tests for build_execution_tree and build_execution_summary functions."""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any

import sys
import os

# Add src path for local imports
tests_dir = os.path.dirname(__file__)
project_root = os.path.dirname(tests_dir)
sys.path.insert(0, os.path.join(project_root, "src"))

from rlm_cli.output import (
    build_execution_tree,
    build_execution_summary,
    _truncate,
)


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


class TestTruncate:
    """Test the _truncate helper function."""

    def test_short_text_unchanged(self):
        assert _truncate("short", 10) == "short"

    def test_long_text_truncated(self):
        result = _truncate("this is a long text", 10)
        assert result == "this is..."
        assert len(result) == 10

    def test_newlines_replaced(self):
        result = _truncate("line1\nline2\nline3", 100)
        assert "\n" not in result
        assert result == "line1 line2 line3"

    def test_empty_string(self):
        assert _truncate("", 10) == ""

    def test_none_handling(self):
        # _truncate expects a string, but let's test robustness
        assert _truncate("", 10) == ""


class TestBuildExecutionTree:
    """Test build_execution_tree function."""

    def test_none_input(self):
        assert build_execution_tree(None) is None

    def test_simple_completion(self):
        """Test with a simple completion without iterations."""
        completion = MockRLMChatCompletion(
            root_model="openai/gpt-4",
            prompt="Test prompt",
            response="Test response",
            execution_time=2.5,
            usage_summary=MockUsageSummary(total_cost=0.05),
        )

        tree = build_execution_tree(completion)

        assert tree is not None
        assert tree["depth"] == 0
        assert tree["model"] == "openai/gpt-4"
        assert tree["cost"] == 0.05
        assert tree["duration"] == 2.5
        assert "prompt_preview" in tree
        assert "response_preview" in tree

    def test_with_iterations(self):
        """Test with iterations."""
        iterations = [
            MockIteration(
                response="First iteration response",
                iteration_time=1.0,
                code_blocks=[MockCodeBlock(code="print('hello')")],
            ),
            MockIteration(
                response="Second iteration response",
                iteration_time=0.5,
                final_answer="Final result",
                code_blocks=[],
            ),
        ]

        completion = MockRLMChatCompletion(
            root_model="google/gemini-2.0-flash",
            prompt="Do something",
            response="Final result",
            execution_time=1.5,
            iterations=iterations,
        )

        tree = build_execution_tree(completion)

        assert tree is not None
        assert "iterations" in tree
        assert len(tree["iterations"]) == 2

        # Check first iteration
        iter1 = tree["iterations"][0]
        assert iter1["iteration"] == 1
        assert iter1["code_blocks"] == 1
        assert iter1["has_final_answer"] is False

        # Check second iteration
        iter2 = tree["iterations"][1]
        assert iter2["iteration"] == 2
        assert iter2["code_blocks"] == 0
        assert iter2["has_final_answer"] is True

    def test_nested_children(self):
        """Test with nested RLM calls (recursive depth)."""
        # Create a child completion
        child_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4o-mini",
            prompt="Child task",
            response="Child response",
            execution_time=0.5,
            usage_summary=MockUsageSummary(total_cost=0.01),
        )

        # Create parent with iteration that has child RLM call
        child_result = MockCodeBlockResult(rlm_calls=[child_completion])
        iterations = [
            MockIteration(
                response="Calling child...",
                iteration_time=1.0,
                code_blocks=[MockCodeBlock(code="llm_query('Child task')", result=child_result)],
            ),
        ]

        parent_completion = MockRLMChatCompletion(
            root_model="openai/gpt-4",
            prompt="Parent task",
            response="Parent response",
            execution_time=1.5,
            usage_summary=MockUsageSummary(total_cost=0.05),
            iterations=iterations,
        )

        tree = build_execution_tree(parent_completion)

        assert tree is not None
        assert tree["depth"] == 0
        assert "children" in tree
        assert len(tree["children"]) == 1

        child = tree["children"][0]
        assert child["depth"] == 1
        assert child["model"] == "openai/gpt-4o-mini"
        assert child["cost"] == 0.01

    def test_multiple_children(self):
        """Test with multiple child RLM calls in one iteration."""
        child1 = MockRLMChatCompletion(
            root_model="model-a",
            prompt="Task A",
            response="Response A",
            execution_time=0.3,
        )
        child2 = MockRLMChatCompletion(
            root_model="model-b",
            prompt="Task B",
            response="Response B",
            execution_time=0.4,
        )

        child_result = MockCodeBlockResult(rlm_calls=[child1, child2])
        iterations = [
            MockIteration(
                response="Running multiple queries...",
                iteration_time=0.7,
                code_blocks=[MockCodeBlock(code="x = llm_query('A')\ny = llm_query('B')", result=child_result)],
            ),
        ]

        parent = MockRLMChatCompletion(
            root_model="parent-model",
            prompt="Parent",
            response="Done",
            execution_time=1.0,
            iterations=iterations,
        )

        tree = build_execution_tree(parent)

        assert tree is not None
        assert "children" in tree
        assert len(tree["children"]) == 2

    def test_dict_prompt(self):
        """Test with dict prompt (context payload)."""
        completion = MockRLMChatCompletion(
            root_model="test/model",
            prompt={"content": "test content", "files": ["a.py"]},
            response="Response",
            execution_time=1.0,
        )

        tree = build_execution_tree(completion)

        assert tree is not None
        assert "prompt_preview" in tree
        assert len(tree["prompt_preview"]) > 0

    def test_message_list_prompt(self):
        """Test with message list prompt."""
        completion = MockRLMChatCompletion(
            root_model="test/model",
            prompt=[
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "What is 2+2?"},
            ],
            response="4",
            execution_time=0.5,
        )

        tree = build_execution_tree(completion)

        assert tree is not None
        assert "What is 2+2?" in tree["prompt_preview"]


class TestBuildExecutionSummary:
    """Test build_execution_summary function."""

    def test_none_input(self):
        assert build_execution_summary(None) is None

    def test_simple_completion(self):
        """Test summary for simple completion."""
        completion = MockRLMChatCompletion(
            root_model="test/model",
            prompt="Test",
            response="Response",
            execution_time=2.0,
            usage_summary=MockUsageSummary(total_cost=0.10),
        )

        summary = build_execution_summary(completion)

        assert summary is not None
        assert summary["total_depth"] == 1
        assert summary["total_nodes"] == 1
        assert summary["total_cost"] == 0.10
        assert summary["total_duration"] == 2.0
        assert "by_depth" in summary
        assert "0" in summary["by_depth"]
        assert summary["by_depth"]["0"]["calls"] == 1

    def test_nested_completion(self):
        """Test summary for nested completion."""
        # Create grandchild
        grandchild = MockRLMChatCompletion(
            root_model="grandchild-model",
            prompt="Grandchild task",
            response="Grandchild response",
            execution_time=0.3,
            usage_summary=MockUsageSummary(total_cost=0.01),
        )

        # Create child with grandchild
        child_of_child_result = MockCodeBlockResult(rlm_calls=[grandchild])
        child = MockRLMChatCompletion(
            root_model="child-model",
            prompt="Child task",
            response="Child response",
            execution_time=0.5,
            usage_summary=MockUsageSummary(total_cost=0.02),
            iterations=[
                MockIteration(
                    response="Calling grandchild...",
                    iteration_time=0.5,
                    code_blocks=[MockCodeBlock(result=child_of_child_result)],
                ),
            ],
        )

        # Create parent with child
        child_result = MockCodeBlockResult(rlm_calls=[child])
        parent = MockRLMChatCompletion(
            root_model="parent-model",
            prompt="Parent task",
            response="Parent response",
            execution_time=1.0,
            usage_summary=MockUsageSummary(total_cost=0.05),
            iterations=[
                MockIteration(
                    response="Calling child...",
                    iteration_time=1.0,
                    code_blocks=[MockCodeBlock(result=child_result)],
                ),
            ],
        )

        summary = build_execution_summary(parent)

        assert summary is not None
        assert summary["total_depth"] == 3  # depth 0, 1, 2
        assert summary["total_nodes"] == 3  # parent, child, grandchild

        # Check by_depth breakdown
        by_depth = summary["by_depth"]
        assert "0" in by_depth
        assert "1" in by_depth
        assert "2" in by_depth
        assert by_depth["0"]["calls"] == 1
        assert by_depth["1"]["calls"] == 1
        assert by_depth["2"]["calls"] == 1

    def test_multiple_siblings(self):
        """Test summary with multiple children at same depth."""
        child1 = MockRLMChatCompletion(
            root_model="model-a",
            prompt="Task A",
            response="Response A",
            execution_time=0.5,
            usage_summary=MockUsageSummary(total_cost=0.02),
        )
        child2 = MockRLMChatCompletion(
            root_model="model-b",
            prompt="Task B",
            response="Response B",
            execution_time=0.7,
            usage_summary=MockUsageSummary(total_cost=0.03),
        )

        children_result = MockCodeBlockResult(rlm_calls=[child1, child2])
        parent = MockRLMChatCompletion(
            root_model="parent-model",
            prompt="Parent task",
            response="Parent response",
            execution_time=1.0,
            usage_summary=MockUsageSummary(total_cost=0.05),
            iterations=[
                MockIteration(
                    response="Calling children...",
                    iteration_time=1.2,
                    code_blocks=[MockCodeBlock(result=children_result)],
                ),
            ],
        )

        summary = build_execution_summary(parent)

        assert summary is not None
        assert summary["total_depth"] == 2
        assert summary["total_nodes"] == 3

        # Depth 1 should have 2 calls
        assert summary["by_depth"]["1"]["calls"] == 2
        # Cost at depth 1 should be sum of children
        assert summary["by_depth"]["1"]["cost"] == 0.05  # 0.02 + 0.03

    def test_no_cost_data(self):
        """Test summary when cost data is not available."""
        completion = MockRLMChatCompletion(
            root_model="test/model",
            prompt="Test",
            response="Response",
            execution_time=2.0,
            usage_summary=None,  # No cost data
        )

        summary = build_execution_summary(completion)

        assert summary is not None
        assert summary["total_cost"] is None
        assert summary["by_depth"]["0"]["cost"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
