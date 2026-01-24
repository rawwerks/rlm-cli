"""Unit tests for early exit (Ctrl+C / SIGUSR1) and inject file features."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from rlm_cli.rlm_adapter import RlmResult, run_completion


class TestRlmResult:
    """Tests for RlmResult dataclass."""

    def test_rlm_result_default_values(self) -> None:
        """Test that RlmResult has correct default values."""
        result = RlmResult(response="test response", raw=None)
        assert result.response == "test response"
        assert result.raw is None
        assert result.early_exit is False
        assert result.early_exit_reason is None

    def test_rlm_result_with_early_exit(self) -> None:
        """Test RlmResult with early exit fields."""
        result = RlmResult(
            response="partial answer",
            raw=None,
            early_exit=True,
            early_exit_reason="user_cancelled",
        )
        assert result.response == "partial answer"
        assert result.early_exit is True
        assert result.early_exit_reason == "user_cancelled"


# Custom exception class that mimics CancellationError
class MockCancellationError(Exception):
    """Mock CancellationError for testing."""
    def __init__(self, partial_answer: str | None = None):
        self.partial_answer = partial_answer
        super().__init__("Cancelled")


# Make it look like CancellationError to the code under test
MockCancellationError.__name__ = "CancellationError"


class TestCancellationHandling:
    """Tests for CancellationError handling in run_completion."""

    @patch("rlm.RLM")
    def test_cancellation_with_partial_answer_returns_success(
        self, mock_rlm_class: MagicMock
    ) -> None:
        """Test that CancellationError with partial answer returns success."""
        # Create exception with partial_answer
        exc = MockCancellationError(partial_answer="This is the partial answer from before interruption")

        # Setup mock RLM instance
        mock_instance = MagicMock()
        mock_instance.completion.side_effect = exc
        mock_rlm_class.return_value = mock_instance

        # Mock _preflight_auth to pass
        with patch("rlm_cli.rlm_adapter._preflight_auth"):
            result = run_completion(
                question="test question",
                context_payload="",
                backend="openrouter",
                environment="local",
                max_iterations=10,
                max_depth=1,
            )

        # Verify result is success with partial answer
        assert result.response == "This is the partial answer from before interruption"
        assert result.early_exit is True
        assert result.early_exit_reason == "user_cancelled"

    @patch("rlm.RLM")
    def test_cancellation_without_partial_answer_raises_error(
        self, mock_rlm_class: MagicMock
    ) -> None:
        """Test that CancellationError without partial answer raises BackendError."""
        from rlm_cli.errors import BackendError

        # Create exception without partial_answer
        exc = MockCancellationError(partial_answer=None)

        # Setup mock RLM instance
        mock_instance = MagicMock()
        mock_instance.completion.side_effect = exc
        mock_rlm_class.return_value = mock_instance

        # Mock _preflight_auth to pass
        with patch("rlm_cli.rlm_adapter._preflight_auth"):
            with pytest.raises(BackendError) as exc_info:
                run_completion(
                    question="test question",
                    context_payload="",
                    backend="openrouter",
                    environment="local",
                    max_iterations=10,
                    max_depth=1,
                )

        assert "cancelled" in str(exc_info.value).lower()


class TestInjectFile:
    """Tests for inject_file parameter."""

    @patch("rlm.RLM")
    def test_inject_file_passed_to_environment_kwargs(
        self, mock_rlm_class: MagicMock
    ) -> None:
        """Test that inject_file is passed to environment_kwargs."""
        mock_completion = MagicMock()
        mock_completion.response = "test response"

        mock_instance = MagicMock()
        mock_instance.completion.return_value = mock_completion
        mock_rlm_class.return_value = mock_instance

        with patch("rlm_cli.rlm_adapter._preflight_auth"):
            run_completion(
                question="test",
                context_payload="",
                backend="openrouter",
                environment="local",
                max_iterations=10,
                max_depth=1,
                inject_file="/tmp/inject.py",
            )

        # Check that RLM was called with inject_file in environment_kwargs
        call_kwargs = mock_rlm_class.call_args[1]
        assert "environment_kwargs" in call_kwargs
        assert call_kwargs["environment_kwargs"].get("inject_file") == "/tmp/inject.py"

    @patch("rlm.RLM")
    def test_inject_file_none_not_passed(
        self, mock_rlm_class: MagicMock
    ) -> None:
        """Test that inject_file=None is not added to environment_kwargs."""
        mock_completion = MagicMock()
        mock_completion.response = "test response"

        mock_instance = MagicMock()
        mock_instance.completion.return_value = mock_completion
        mock_rlm_class.return_value = mock_instance

        with patch("rlm_cli.rlm_adapter._preflight_auth"):
            run_completion(
                question="test",
                context_payload="",
                backend="openrouter",
                environment="local",
                max_iterations=10,
                max_depth=1,
                inject_file=None,
            )

        # Check that inject_file is not in environment_kwargs
        call_kwargs = mock_rlm_class.call_args[1]
        assert "environment_kwargs" in call_kwargs
        assert "inject_file" not in call_kwargs["environment_kwargs"]
