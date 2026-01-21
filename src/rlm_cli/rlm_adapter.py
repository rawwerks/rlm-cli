"""Helpers for parsing passthrough args for RLM adapters."""

from __future__ import annotations

import inspect
import json
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


def run_completion(
    *,
    question: str,
    context_payload: object,
    backend: str,
    environment: str,
    max_iterations: int,
    max_depth: int,
    backend_kwargs: Mapping[str, object] | None = None,
    environment_kwargs: Mapping[str, object] | None = None,
    rlm_kwargs: Mapping[str, object] | None = None,
    model: str | None = None,
    log_dir: str | None = None,
) -> RlmResult:
    try:
        from rlm import RLM
    except Exception as exc:  # noqa: BLE001
        raise BackendError(
            "Failed to import rlm.",
            why=str(exc),
            fix="Install the rlm package and ensure it is importable.",
        ) from exc

    logger = _maybe_logger(log_dir)

    backend_payload = dict(backend_kwargs or {})
    if model and "model_name" not in backend_payload:
        backend_payload["model_name"] = model

    rlm_init_kwargs: dict[str, object] = {
        "backend": backend,
        "environment": environment,
        "max_iterations": max_iterations,
        "max_depth": max_depth,
        "backend_kwargs": backend_payload,
        "environment_kwargs": dict(environment_kwargs or {}),
    }
    if logger is not None:
        rlm_init_kwargs["logger"] = logger
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
        ) from exc

    try:
        completion = rlm_instance.completion(
            prompt=context_payload,
            root_prompt=question,
        )
    except Exception as exc:  # noqa: BLE001
        raise BackendError(
            "RLM completion failed.",
            why=str(exc),
            fix="Check backend credentials and environment settings.",
        ) from exc

    response = getattr(completion, "response", None)
    if response is None:
        response = str(completion)
    return RlmResult(response=str(response), raw=completion)


def _maybe_logger(log_dir: str | None) -> object | None:
    if not log_dir:
        return None
    try:
        from rlm import RLMLogger
    except Exception:
        return None
    try:
        return RLMLogger(log_dir=log_dir)
    except Exception:
        return None


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
