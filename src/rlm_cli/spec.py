"""CLI spec for automation."""

from __future__ import annotations

import importlib.metadata
import inspect
from typing import Any

from .output import OUTPUT_SCHEMA_VERSION


def build_spec() -> dict[str, Any]:
    cli_version = _version("rlm-cli")
    rlm_version = _rlm_version()
    signature = _rlm_signature()

    return {
        "cli_version": cli_version,
        "rlm_version": rlm_version,
        "output_schema": OUTPUT_SCHEMA_VERSION,
        "rlm_init_signature": signature,
        "commands": _command_spec(),
    }


def _command_spec() -> list[dict[str, Any]]:
    return [
        {
            "name": "ask",
            "options": [
                {"name": "--question", "required": True},
                {"name": "--backend", "default": "openai"},
                {"name": "--model", "default": ""},
                {"name": "--environment", "default": "local"},
                {"name": "--max-iterations", "default": 30},
                {"name": "--max-depth", "default": 1},
                {"name": "--output-format", "default": "text"},
                {"name": "--json", "default": False},
            ],
        },
        {
            "name": "complete",
            "options": [
                {"name": "TEXT", "required": True},
                {"name": "--backend", "default": "openai"},
                {"name": "--model", "default": ""},
                {"name": "--environment", "default": "local"},
            ],
        },
        {"name": "doctor", "options": [{"name": "--json", "default": False}]},
        {"name": "spec", "options": [{"name": "--json", "default": True}]},
        {"name": "schema", "options": []},
    ]


def _rlm_version() -> str:
    try:
        import rlm

        return getattr(rlm, "__version__", "unknown")
    except Exception:
        return "unavailable"


def _rlm_signature() -> str | None:
    try:
        from rlm import RLM

        return str(inspect.signature(RLM.__init__))
    except Exception:
        return None


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"
