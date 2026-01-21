"""Helpers for parsing passthrough args for RLM adapters."""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Iterable

from .errors import InputError

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?\d+\.\d+([eE][+-]?\d+)?$")


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
