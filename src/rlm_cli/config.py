"""Configuration loading and precedence handling."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

import yaml

from .errors import ConfigError

# Value coercion patterns
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?\d+\.\d+([eE][+-]?\d+)?$")

ENV_CONFIG_PATH = "RLM_CONFIG"
ENV_OUTPUT_FORMAT = "RLM_OUTPUT"
ENV_OUTPUT_JSON = "RLM_JSON"

DEFAULT_CONFIG: dict[str, object] = {
    "backend": "openai",
    "model": "",
    "environment": "local",
    "max_iterations": 30,
    "max_depth": 1,
    "backend_kwargs": {},
    "environment_kwargs": {},
    "output": {"format": "text", "log_dir": None},
    "search": {
        "enabled": True,
        "index_dir": "~/.cache/rlm-cli/tantivy",
        "heap_size_mb": 50,
        "auto_index": True,
        "default_limit": 50,
        "boosts": {
            "path_stem": 3.0,
            "path": 2.0,
            "content": 1.0,
        },
    },
}


@dataclass(frozen=True)
class EffectiveConfig:
    data: dict[str, object]
    config_path: Path | None


def iter_default_config_paths() -> list[Path]:
    cwd = Path.cwd()
    return [
        cwd / "rlm.yaml",
        cwd / ".rlm.yaml",
        Path.home() / ".config" / "rlm" / "config.yaml",
    ]


def resolve_config_path(
    *,
    cli_path: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    env_vars = env or os.environ
    if cli_path:
        candidate = Path(cli_path).expanduser()
        if not candidate.exists():
            raise ConfigError(
                "Config file not found.",
                why=f"'{cli_path}' was provided with --config.",
                fix="Check the path or remove --config.",
            )
        return candidate

    env_path = env_vars.get(ENV_CONFIG_PATH)
    if env_path:
        candidate = Path(env_path).expanduser()
        if not candidate.exists():
            raise ConfigError(
                "Config file not found.",
                why=f"${ENV_CONFIG_PATH} points to '{env_path}'.",
                fix="Update the environment variable or remove it.",
            )
        return candidate

    for candidate in iter_default_config_paths():
        if candidate.exists():
            return candidate
    return None


def load_config_file(path: Path) -> dict[str, object]:
    try:
        raw = yaml.safe_load(path.read_text())
    except OSError as exc:
        raise ConfigError(
            "Failed to read config file.",
            why=str(exc),
            fix="Check file permissions and retry.",
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(
            "Config file is not valid YAML.",
            why=str(exc),
            fix="Fix the YAML syntax.",
        ) from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(
            "Config file must be a mapping.",
            why=f"Top-level YAML type is {type(raw).__name__}.",
            fix="Use a mapping of keys to values.",
        )
    return raw


def load_effective_config(
    *,
    cli_overrides: dict[str, object] | None = None,
    cli_config_path: str | None = None,
    env: Mapping[str, str] | None = None,
    defaults: dict[str, object] | None = None,
) -> EffectiveConfig:
    env_vars = env or os.environ
    base = _deep_merge({}, defaults or DEFAULT_CONFIG)
    config_path = resolve_config_path(cli_path=cli_config_path, env=env_vars)
    if config_path:
        base = _deep_merge(base, load_config_file(config_path))
    base = _deep_merge(base, _env_overrides(env_vars))
    if cli_overrides:
        base = _deep_merge(base, cli_overrides)
    return EffectiveConfig(data=base, config_path=config_path)


def render_effective_config_text(config: Mapping[str, object]) -> str:
    return yaml.safe_dump(config, sort_keys=False)


def _env_overrides(env_vars: Mapping[str, str]) -> dict[str, object]:
    output_override = _env_output_format(env_vars)
    if output_override is None:
        return {}
    return {"output": {"format": output_override}}


def _env_output_format(env_vars: Mapping[str, str]) -> str | None:
    raw = env_vars.get(ENV_OUTPUT_FORMAT)
    if raw:
        normalized = raw.strip().lower()
        if normalized in {"json", "text"}:
            return normalized
        raise ConfigError(
            "Unsupported output format.",
            why=f"${ENV_OUTPUT_FORMAT} is set to '{raw}'.",
            fix="Use 'json' or 'text'.",
        )

    raw_json = env_vars.get(ENV_OUTPUT_JSON)
    if raw_json is None:
        return None
    normalized = raw_json.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return "json"
    if normalized in {"0", "false", "no", "off"}:
        return "text"
    raise ConfigError(
        "Unsupported JSON flag.",
        why=f"${ENV_OUTPUT_JSON} is set to '{raw_json}'.",
        fix="Use true/false, 1/0, or remove it.",
    )


def _deep_merge(
    base: dict[str, object],
    override: dict[str, object],
) -> dict[str, object]:
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            left = cast(dict[str, object], result[key])
            right = cast(dict[str, object], value)
            result[key] = _deep_merge(left, right)
        else:
            result[key] = value
    return result


def get_user_config_path() -> Path:
    """Return the user-level config path (~/.config/rlm/config.yaml)."""
    return Path.home() / ".config" / "rlm" / "config.yaml"


def get_local_config_path() -> Path:
    """Return the local/project-level config path (./rlm.yaml)."""
    return Path.cwd() / "rlm.yaml"


def get_nested_value(data: dict[str, Any], key: str) -> Any:
    """Get a value from nested dict using dot notation.

    Args:
        data: The dictionary to search
        key: Dot-separated key path (e.g., "backend_kwargs.temperature")

    Returns:
        The value at the key path, or None if not found
    """
    parts = key.split(".")
    current: Any = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def set_nested_value(data: dict[str, Any], key: str, value: Any) -> None:
    """Set a value in nested dict using dot notation.

    Args:
        data: The dictionary to modify (in-place)
        key: Dot-separated key path (e.g., "backend_kwargs.temperature")
        value: The value to set
    """
    parts = key.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def coerce_value(value: str) -> Any:
    """Coerce a string value to appropriate Python type.

    Handles: bool, null, int, float, JSON objects/arrays, strings.
    """
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
        except json.JSONDecodeError:
            pass  # Return as string if JSON parsing fails
    return value


def write_config_file(path: Path, data: dict[str, Any]) -> None:
    """Write config data to a YAML file.

    Creates parent directories if needed.

    Args:
        path: Path to write to
        data: Config data to write
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def load_or_create_config(path: Path) -> dict[str, Any]:
    """Load config from path, or return empty dict if not exists."""
    if path.exists():
        return load_config_file(path)
    return {}
