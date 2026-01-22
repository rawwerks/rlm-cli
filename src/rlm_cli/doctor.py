"""Diagnostics for rlm-cli."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from typing import Any


def run_doctor(*, json_mode: bool) -> dict[str, Any]:
    checks = []

    python_ok = sys.version_info >= (3, 9)
    checks.append(
        {
            "name": "python_version",
            "ok": python_ok,
            "detail": platform.python_version(),
            "hint": "Upgrade to Python 3.9+" if not python_ok else "",
        }
    )

    try:
        import rlm

        rlm_version = getattr(rlm, "__version__", "unknown")
        checks.append(
            {
                "name": "rlm_import",
                "ok": True,
                "detail": f"rlm {rlm_version}",
                "hint": "",
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            {
                "name": "rlm_import",
                "ok": False,
                "detail": str(exc),
                "hint": "Install rlm and ensure it is importable.",
            }
        )

    docker_ok = shutil.which("docker") is not None
    checks.append(
        {
            "name": "docker_available",
            "ok": docker_ok,
            "detail": "found" if docker_ok else "not found",
            "hint": "Install Docker if you plan to use --environment docker.",
        }
    )

    try:
        import modal  # noqa: F401

        checks.append(
            {
                "name": "modal_available",
                "ok": True,
                "detail": "imported",
                "hint": "",
            }
        )
    except Exception:
        checks.append(
            {
                "name": "modal_available",
                "ok": False,
                "detail": "not importable",
                "hint": "Install modal if you plan to use --environment modal.",
            }
        )

    try:
        import tantivy  # noqa: F401

        checks.append(
            {
                "name": "tantivy_available",
                "ok": True,
                "detail": "imported",
                "hint": "",
            }
        )
    except Exception:
        checks.append(
            {
                "name": "tantivy_available",
                "ok": False,
                "detail": "not importable",
                "hint": "Install tantivy for search: pip install 'rlm-cli[search]'",
            }
        )

    prime_key = os.getenv("RLM_PRIME_API_KEY") or os.getenv("PRIME_API_KEY")
    checks.append(
        {
            "name": "prime_key",
            "ok": bool(prime_key),
            "detail": "set" if prime_key else "missing",
            "hint": "Set PRIME_API_KEY if you plan to use --environment prime.",
        }
    )

    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        checks.append(
            {
                "name": key.lower(),
                "ok": bool(os.getenv(key)),
                "detail": "set" if os.getenv(key) else "missing",
                "hint": f"Set {key} for that provider.",
            }
        )

    if json_mode:
        return {"checks": checks, "warnings": []}

    lines = ["RLM CLI Doctor", ""]
    for check in checks:
        status = "OK" if check["ok"] else "FAIL"
        lines.append(f"[{status}] {check['name']}: {check['detail']}")
        if check["hint"] and not check["ok"]:
            lines.append(f"  hint: {check['hint']}")
    return {"text": "\n".join(lines), "warnings": []}
