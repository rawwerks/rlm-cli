"""Output rendering for JSON and text modes."""

from __future__ import annotations

import io
import json
import sys
from contextlib import contextmanager, redirect_stdout
from typing import Iterator, Mapping, Sequence

OUTPUT_SCHEMA_VERSION = "rlm-cli.output.v1"


def build_output(
    *,
    ok: bool,
    exit_code: int,
    result: object | None = None,
    request: object | None = None,
    artifacts: dict[str, object] | None = None,
    stats: dict[str, object] | None = None,
    warnings: Sequence[str] | None = None,
    error: dict[str, object] | None = None,
    debug: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": OUTPUT_SCHEMA_VERSION,
        "ok": ok,
        "exit_code": exit_code,
        "result": result,
        "request": request,
        "artifacts": artifacts or {},
        "stats": stats or {},
        "warnings": list(warnings or []),
    }
    if error:
        payload["error"] = error
    if debug:
        payload["debug"] = debug
    return payload


def attach_captured_stdout(payload: dict[str, object], captured: str) -> None:
    if not captured.strip():
        return
    debug = payload.setdefault("debug", {})
    if isinstance(debug, dict):
        debug.setdefault("captured_stdout", captured)


def emit_json(payload: Mapping[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.write("\n")


def emit_text(result_text: str, *, warnings: Sequence[str] = ()) -> None:
    if result_text:
        sys.stdout.write(result_text)
        if not result_text.endswith("\n"):
            sys.stdout.write("\n")
    for warning in warnings:
        sys.stderr.write(f"Warning: {warning}\n")


@contextmanager
def capture_stdout() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        yield buffer
