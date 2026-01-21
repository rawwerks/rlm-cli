"""Input parsing for stdin, paths, and literal content."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .errors import InputError


class InputKind(str, Enum):
    STDIN = "stdin"
    FILE = "file"
    DIR = "dir"
    LITERAL = "literal"


@dataclass(frozen=True)
class InputSource:
    kind: InputKind
    value: str | Path | None


def parse_input_source(
    token: str | None,
    *,
    literal: bool = False,
    path: str | None = None,
) -> InputSource:
    if path:
        return _parse_path(path, required=True)

    if token is None:
        raise InputError(
            "Missing input.",
            why="No INPUT value was provided.",
            fix="Provide INPUT as a path, '-' for stdin, or use --literal.",
        )

    if token == "-":
        return InputSource(InputKind.STDIN, None)

    resolved = _parse_path(token, required=False)
    if resolved:
        return resolved

    if literal:
        return InputSource(InputKind.LITERAL, token)

    raise InputError(
        "Input path does not exist.",
        why=f"'{token}' is not a file or directory.",
        fix="Pass an existing path or add --literal to treat it as text.",
    )


def _parse_path(value: str, *, required: bool) -> InputSource | None:
    candidate = Path(value)
    if not candidate.exists():
        if required:
            raise InputError(
                "Input path does not exist.",
                why=f"'{value}' was provided with --path.",
                fix="Check the path or remove --path to treat the input as text.",
            )
        return None

    if candidate.is_file():
        return InputSource(InputKind.FILE, candidate)
    if candidate.is_dir():
        return InputSource(InputKind.DIR, candidate)

    raise InputError(
        "Input path is not a regular file or directory.",
        why=f"'{value}' is neither a file nor a directory.",
        fix="Point to a file or folder.",
    )
