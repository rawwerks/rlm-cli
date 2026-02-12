"""Helpers for parsing passthrough args for RLM adapters."""

from __future__ import annotations

import inspect
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import BackendError, InputError

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?\d+\.\d+([eE][+-]?\d+)?$")


@dataclass(frozen=True)
class RlmResult:
    response: str
    raw: object
    early_exit: bool = False
    early_exit_reason: str | None = None


def run_completion(
    *,
    question: str,
    context_payload: object,
    backend: str,
    environment: str,
    max_iterations: int,
    max_depth: int,
    max_budget: float | None = None,
    max_timeout: float | None = None,
    max_tokens: int | None = None,
    max_errors: int | None = None,
    backend_kwargs: Mapping[str, object] | None = None,
    environment_kwargs: Mapping[str, object] | None = None,
    rlm_kwargs: Mapping[str, object] | None = None,
    model: str | None = None,
    log_dir: str | None = None,
    verbose: bool = False,
    custom_system_prompt: str | None = None,
    inject_file: str | None = None,
) -> RlmResult:
    try:
        from rlm import RLM
    except Exception as exc:  # noqa: BLE001
        raise BackendError(
            "Failed to import rlm.",
            why=str(exc),
            fix="Install the rlm package and ensure it is importable.",
            try_steps=["python -c \"import rlm; print(rlm.__version__)\""],
        ) from exc

    _preflight_auth(backend, backend_kwargs)
    logger = _maybe_logger(log_dir)

    backend_payload = dict(backend_kwargs or {})
    if model and "model_name" not in backend_payload:
        backend_payload["model_name"] = model

    # Build environment kwargs, optionally adding inject_file
    env_kwargs = dict(environment_kwargs or {})
    if inject_file:
        env_kwargs["inject_file"] = inject_file

    rlm_init_kwargs: dict[str, object] = {
        "backend": backend,
        "environment": environment,
        "max_iterations": max_iterations,
        "max_depth": max_depth,
        "backend_kwargs": backend_payload,
        "environment_kwargs": env_kwargs,
    }
    if max_budget is not None:
        rlm_init_kwargs["max_budget"] = max_budget
    if max_timeout is not None:
        rlm_init_kwargs["max_timeout"] = max_timeout
    if max_tokens is not None:
        rlm_init_kwargs["max_tokens"] = max_tokens
    if max_errors is not None:
        rlm_init_kwargs["max_errors"] = max_errors
    if logger is not None:
        rlm_init_kwargs["logger"] = logger
    if verbose and (not rlm_kwargs or "verbose" not in rlm_kwargs):
        rlm_init_kwargs["verbose"] = True
    if custom_system_prompt:
        rlm_init_kwargs["custom_system_prompt"] = custom_system_prompt
    if rlm_kwargs:
        rlm_init_kwargs.update(rlm_kwargs)

    filtered_kwargs = _filter_init_kwargs(RLM, rlm_init_kwargs)
    try:
        rlm_instance = RLM(**filtered_kwargs)
    except TypeError as exc:
        raise BackendError(
            "Failed to initialize RLM.",
            why=str(exc),
            fix="Check rlm version compatibility and provided arguments.",
            try_steps=["rlm spec --json"],
        ) from exc

    try:
        completion = rlm_instance.completion(
            prompt=context_payload,
            root_prompt=question,
        )
    except Exception as exc:  # noqa: BLE001
        exc_name = type(exc).__name__
        partial = getattr(exc, "partial_answer", None)

        # Budget exceeded
        if exc_name == "BudgetExceededError":
            spent = getattr(exc, "spent", None)
            budget = getattr(exc, "budget", None)
            if spent is not None and budget is not None:
                why = f"Budget exceeded: spent ${spent:.6f} of ${budget:.6f} budget"
            else:
                why = str(exc)
            suggested_budget = max((budget or 0.01) * 10, 0.10)
            raise BackendError(
                "RLM completion failed.",
                why=why,
                fix="Increase --max-budget or reduce task complexity.",
                try_steps=[f"rlm complete '...' --max-budget {suggested_budget:.2f}"],
            ) from exc

        # Timeout exceeded
        if exc_name == "TimeoutExceededError":
            elapsed = getattr(exc, "elapsed", None)
            timeout = getattr(exc, "timeout", None)
            if elapsed is not None and timeout is not None:
                why = f"Timeout exceeded: {elapsed:.1f}s of {timeout:.1f}s limit"
            else:
                why = str(exc)
            if partial:
                why += f" (partial answer available: {len(partial)} chars)"
            suggested_timeout = max((timeout or 30) * 2, 60)
            raise BackendError(
                "RLM completion failed.",
                why=why,
                fix="Increase --max-timeout or simplify the task.",
                try_steps=[f"rlm complete '...' --max-timeout {suggested_timeout:.0f}"],
            ) from exc

        # Token limit exceeded
        if exc_name == "TokenLimitExceededError":
            tokens_used = getattr(exc, "tokens_used", None)
            token_limit = getattr(exc, "token_limit", None)
            if tokens_used is not None and token_limit is not None:
                why = f"Token limit exceeded: {tokens_used:,} of {token_limit:,} tokens"
            else:
                why = str(exc)
            if partial:
                why += f" (partial answer available: {len(partial)} chars)"
            suggested_tokens = max((token_limit or 10000) * 2, 20000)
            raise BackendError(
                "RLM completion failed.",
                why=why,
                fix="Increase --max-tokens or reduce context size.",
                try_steps=[f"rlm complete '...' --max-tokens {suggested_tokens}"],
            ) from exc

        # Error threshold exceeded
        if exc_name == "ErrorThresholdExceededError":
            error_count = getattr(exc, "error_count", None)
            threshold = getattr(exc, "threshold", None)
            last_error = getattr(exc, "last_error", None)
            if error_count is not None and threshold is not None:
                why = f"Error threshold exceeded: {error_count} consecutive errors (limit: {threshold})"
            else:
                why = str(exc)
            if last_error:
                why += f"\nLast error: {last_error[:200]}"
            if partial:
                why += f" (partial answer available: {len(partial)} chars)"
            raise BackendError(
                "RLM completion failed.",
                why=why,
                fix="Increase --max-errors or fix code causing errors.",
                try_steps=["rlm doctor --json"],
            ) from exc

        # User cancellation - return partial answer as success if available
        if exc_name == "CancellationError":
            if partial:
                # Return partial answer as success (exit code 0)
                return RlmResult(
                    response=str(partial),
                    raw=None,
                    early_exit=True,
                    early_exit_reason="user_cancelled",
                )
            # No partial answer available - raise error
            raise BackendError(
                "RLM completion cancelled.",
                why="Execution cancelled by user (Ctrl+C) - no partial answer available",
                fix="Re-run the command to continue.",
                try_steps=[],
            ) from exc

        # Generic error
        raise BackendError(
            "RLM completion failed.",
            why=str(exc),
            fix="Check backend credentials and environment settings.",
            try_steps=["rlm doctor --json"],
        ) from exc

    response = getattr(completion, "response", None)
    if response is None:
        response = str(completion)
    return RlmResult(response=str(response), raw=completion)


def _maybe_logger(log_dir: str | None) -> object | None:
    if not log_dir:
        return None
    try:
        from rlm.logger import RLMLogger
    except Exception:
        return None
    try:
        return RLMLogger(log_dir=log_dir)
    except Exception:
        return None


def _preflight_auth(backend: str, backend_kwargs: Mapping[str, object] | None) -> None:
    backend_kwargs = backend_kwargs or {}
    if backend == "openrouter":
        if "api_key" not in backend_kwargs and not os.getenv("OPENROUTER_API_KEY"):
            raise BackendError(
                "Missing OpenRouter API key.",
                why="OPENROUTER_API_KEY is not set and no api_key was provided.",
                fix="Export OPENROUTER_API_KEY or pass --backend-arg api_key=...",
                try_steps=["export OPENROUTER_API_KEY=sk-or-..."],
            )
    if backend == "openai":
        if "api_key" not in backend_kwargs and not os.getenv("OPENAI_API_KEY"):
            raise BackendError(
                "Missing OpenAI API key.",
                why="OPENAI_API_KEY is not set and no api_key was provided.",
                fix="Export OPENAI_API_KEY or pass --backend-arg api_key=...",
                try_steps=["export OPENAI_API_KEY=sk-..."],
            )


def _filter_init_kwargs(
    cls: type[Any],
    kwargs: Mapping[str, object],
) -> dict[str, object]:
    try:
        signature = inspect.signature(getattr(cls, "__init__"))
    except (TypeError, ValueError):
        return dict(kwargs)

    for param in signature.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return dict(kwargs)

    allowed = {name for name in signature.parameters if name != "self"}
    return {key: value for key, value in kwargs.items() if key in allowed}


def parse_kv_args(values: Iterable[str], *, label: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for raw in values:
        key, value = _split_kv(raw, label=label)
        result[key] = _coerce_value(value, label=label, key=key)
    return result


def parse_json_args(values: Iterable[str], *, label: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for raw in values:
        path = _parse_json_path(raw, label=label)
        payload = _load_json_mapping(path, label=label)
        result = _merge_dicts(result, payload)
    return result


def _split_kv(raw: str, *, label: str) -> tuple[str, str]:
    if "=" not in raw:
        raise InputError(
            "Invalid KEY=VALUE argument.",
            why=f"{label} received '{raw}'.",
            fix="Use KEY=VALUE.",
        )
    key, value = raw.split("=", 1)
    key = key.strip()
    if not key:
        raise InputError(
            "Empty key in argument.",
            why=f"{label} received '{raw}'.",
            fix="Provide a non-empty key before '='.",
        )
    return key, value.strip()


def _coerce_value(value: str, *, label: str, key: str) -> object:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if _INT_RE.match(value):
        try:
            return int(value)
        except ValueError:
            pass
    if _FLOAT_RE.match(value):
        try:
            return float(value)
        except ValueError:
            pass
    if value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise InputError(
                "Invalid JSON argument.",
                why=f"{label} '{key}' contains invalid JSON.",
                fix="Pass valid JSON or quote the value.",
            ) from exc
    return value


def _parse_json_path(raw: str, *, label: str) -> Path:
    value = raw[1:] if raw.startswith("@") else raw
    path = Path(value).expanduser()
    if not path.exists():
        raise InputError(
            "JSON file not found.",
            why=f"{label} references '{value}'.",
            fix="Check the path or remove the argument.",
        )
    return path


def _load_json_mapping(path: Path, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise InputError(
            "Failed to read JSON file.",
            why=str(exc),
            fix="Check file permissions and retry.",
        ) from exc
    except json.JSONDecodeError as exc:
        raise InputError(
            "Invalid JSON file.",
            why=f"{label} received '{path}'.",
            fix="Fix the JSON content.",
        ) from exc
    if not isinstance(payload, dict):
        raise InputError(
            "JSON file must be an object.",
            why=f"{label} received non-object JSON in '{path}'.",
            fix="Use a JSON object at the top level.",
        )
    return payload


def _merge_dicts(
    base: dict[str, object],
    override: dict[str, object],
) -> dict[str, object]:
    merged = dict(base)
    merged.update(override)
    return merged
