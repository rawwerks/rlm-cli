"""Error types and rendering helpers for the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence


@dataclass
class CliError(Exception):
    message: str
    why: str | None = None
    fix: str | None = None
    try_steps: Sequence[str] = field(default_factory=tuple)
    exit_code: int = 1
    error_type: str = "runtime_error"

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": self.error_type,
            "message": self.message,
        }
        if self.why:
            payload["detail"] = self.why
        if self.fix:
            payload["hint"] = self.fix
        if self.try_steps:
            payload["try"] = list(self.try_steps)
        return payload

    def to_text(self) -> str:
        return format_error_text(self)


class CliUsageError(CliError):
    def __init__(
        self,
        message: str,
        *,
        why: str | None = None,
        fix: str | None = None,
        try_steps: Iterable[str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            why=why,
            fix=fix,
            try_steps=tuple(try_steps or ()),
            exit_code=2,
            error_type="cli_usage_error",
        )


class InputError(CliError):
    def __init__(
        self,
        message: str,
        *,
        why: str | None = None,
        fix: str | None = None,
        try_steps: Iterable[str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            why=why,
            fix=fix,
            try_steps=tuple(try_steps or ()),
            exit_code=10,
            error_type="input_error",
        )


class ConfigError(CliError):
    def __init__(
        self,
        message: str,
        *,
        why: str | None = None,
        fix: str | None = None,
        try_steps: Iterable[str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            why=why,
            fix=fix,
            try_steps=tuple(try_steps or ()),
            exit_code=11,
            error_type="config_error",
        )


class BackendError(CliError):
    def __init__(
        self,
        message: str,
        *,
        why: str | None = None,
        fix: str | None = None,
        try_steps: Iterable[str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            why=why,
            fix=fix,
            try_steps=tuple(try_steps or ()),
            exit_code=20,
            error_type="backend_error",
        )


class RuntimeError(CliError):
    def __init__(
        self,
        message: str,
        *,
        why: str | None = None,
        fix: str | None = None,
        try_steps: Iterable[str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            why=why,
            fix=fix,
            try_steps=tuple(try_steps or ()),
            exit_code=30,
            error_type="runtime_error",
        )


def format_error_text(error: CliError) -> str:
    lines = [f"✗ {error.message}"]
    if error.why:
        lines.append("")
        lines.append("Why this happened")
        lines.append(f"- {error.why}")
    if error.fix:
        lines.append("")
        lines.append("How to fix")
        lines.append(f"- {error.fix}")
    if error.try_steps:
        lines.append("")
        lines.append("Try this")
        lines.extend(f"- {step}" for step in error.try_steps)
    return "\n".join(lines)


def format_error_json(error: CliError) -> dict[str, object]:
    payload = error.to_json()
    return payload
