"""Configuration loading and precedence handling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, cast

import yaml

from .errors import ConfigError

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
