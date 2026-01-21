"""Output schema definition for rlm-cli."""

from __future__ import annotations

from typing import Any

from .output import OUTPUT_SCHEMA_VERSION


def output_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "rlm-cli output",
        "type": "object",
        "properties": {
            "schema": {"const": OUTPUT_SCHEMA_VERSION},
            "ok": {"type": "boolean"},
            "exit_code": {"type": "integer"},
            "result": {},
            "request": {},
            "artifacts": {"type": "object"},
            "stats": {"type": "object"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "error": {"type": "object"},
            "debug": {"type": "object"},
        },
        "required": [
            "schema",
            "ok",
            "exit_code",
            "result",
            "request",
            "artifacts",
            "stats",
            "warnings",
        ],
        "additionalProperties": True,
    }
