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


def _truncate(text: str, max_len: int = 100) -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def build_execution_tree(raw: object, depth: int = 0) -> dict[str, object] | None:
    """
    Build hierarchical execution tree from RLMChatCompletion.

    Returns a tree structure:
    {
        "depth": 0,
        "model": "openai/gpt-4",
        "prompt_preview": "Analyze the codebase...",
        "response_preview": "I'll start by...",
        "cost": 0.05,
        "duration": 2.3,
        "iterations": [...],  # list of iteration nodes
        "children": [...]     # nested sub-call trees
    }
    """
    if raw is None:
        return None

    # Extract fields from RLMChatCompletion
    root_model = getattr(raw, "root_model", None) or "unknown"
    prompt = getattr(raw, "prompt", None)
    response = getattr(raw, "response", None) or ""
    execution_time = getattr(raw, "execution_time", None) or 0.0
    usage_summary = getattr(raw, "usage_summary", None)
    iterations = getattr(raw, "iterations", None)

    # Get cost from usage_summary
    cost = None
    if usage_summary:
        cost = getattr(usage_summary, "total_cost", None)

    # Format prompt preview
    prompt_preview = ""
    if isinstance(prompt, str):
        prompt_preview = _truncate(prompt)
    elif isinstance(prompt, dict):
        # Try to extract meaningful preview from context dict
        if "query" in prompt:
            prompt_preview = _truncate(str(prompt["query"]))
        elif "root" in prompt:
            prompt_preview = f"[context: {prompt.get('root', 'unknown')}]"
        else:
            prompt_preview = _truncate(str(prompt), 60)
    elif isinstance(prompt, list) and prompt:
        # Message list - get last user message content
        for msg in reversed(prompt):
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    prompt_preview = _truncate(content)
                elif isinstance(content, dict) and "query" in content:
                    prompt_preview = _truncate(str(content["query"]))
                else:
                    prompt_preview = _truncate(str(content))
                break

    node: dict[str, object] = {
        "depth": depth,
        "model": root_model,
        "prompt_preview": prompt_preview,
        "response_preview": _truncate(response),
        "duration": round(execution_time, 3),
    }
    if cost is not None:
        node["cost"] = round(cost, 6)

    # Process iterations to build tree with children
    iteration_nodes: list[dict[str, object]] = []
    all_children: list[dict[str, object]] = []

    if iterations:
        for idx, iteration in enumerate(iterations):
            iter_node = _build_iteration_node(iteration, idx + 1, depth)
            iteration_nodes.append(iter_node)

            # Collect children from code blocks
            code_blocks = getattr(iteration, "code_blocks", []) or []
            for code_block in code_blocks:
                result = getattr(code_block, "result", None)
                if result:
                    rlm_calls = getattr(result, "rlm_calls", []) or []
                    for child_call in rlm_calls:
                        child_tree = build_execution_tree(child_call, depth + 1)
                        if child_tree:
                            all_children.append(child_tree)

    if iteration_nodes:
        node["iterations"] = iteration_nodes
    if all_children:
        node["children"] = all_children

    return node


def _build_iteration_node(iteration: object, num: int, depth: int) -> dict[str, object]:
    """Build a node for a single iteration."""
    response = getattr(iteration, "response", None) or ""
    iteration_time = getattr(iteration, "iteration_time", None)
    final_answer = getattr(iteration, "final_answer", None)
    code_blocks = getattr(iteration, "code_blocks", []) or []

    node: dict[str, object] = {
        "iteration": num,
        "response_preview": _truncate(response),
        "code_blocks": len(code_blocks),
        "has_final_answer": final_answer is not None,
    }
    if iteration_time is not None:
        node["duration"] = round(iteration_time, 3)

    # Count sub-calls in this iteration
    sub_call_count = 0
    for code_block in code_blocks:
        result = getattr(code_block, "result", None)
        if result:
            rlm_calls = getattr(result, "rlm_calls", []) or []
            sub_call_count += len(rlm_calls)
    if sub_call_count > 0:
        node["sub_calls"] = sub_call_count

    return node


def render_execution_tree(raw: object) -> str | None:
    """
    Render execution tree as ASCII art for terminal display.

    Returns a string like:
    ┌─ [openai/gpt-4] 2.3s $0.05
    │  Q: Analyze the codebase...
    │  A: I'll start by...
    │
    └─┬─ [google/gemini] 1.2s $0.02
      │  Q: What is X?
      │  A: X is...
      │
      └── [openai/gpt-4] 0.5s
          Q: Details?
          A: The details...
    """
    tree = build_execution_tree(raw)
    if tree is None:
        return None

    lines: list[str] = []

    def format_node_header(node: dict[str, object]) -> str:
        model = node.get("model", "unknown")
        duration = node.get("duration", 0)
        cost = node.get("cost")
        header = f"[{model}] {duration}s"
        if cost:
            header += f" ${cost:.4f}"
        return header

    def render_node(node: dict[str, object], prefix: str, is_last: bool, is_root: bool) -> None:
        # Determine box drawing characters
        if is_root:
            branch = "┌─ "
            child_prefix = "│  "
        elif is_last:
            branch = "└── "
            child_prefix = "    "
        else:
            branch = "├── "
            child_prefix = "│   "

        # Node header
        header = format_node_header(node)
        lines.append(f"{prefix}{branch}{header}")

        # Content prefix for Q/A lines
        content_prefix = prefix + child_prefix

        # Show prompt/response previews
        prompt = node.get("prompt_preview", "")
        response = node.get("response_preview", "")
        if prompt:
            lines.append(f"{content_prefix}Q: {prompt}")
        if response:
            lines.append(f"{content_prefix}A: {response}")

        # Process children
        children = node.get("children", []) or []
        if children:
            lines.append(content_prefix.rstrip())  # blank line before children
            for i, child in enumerate(children):
                if isinstance(child, dict):
                    is_last_child = i == len(children) - 1
                    render_node(child, content_prefix, is_last_child, False)

    render_node(tree, "", True, True)
    return "\n".join(lines)


def build_execution_summary(raw: object) -> dict[str, object] | None:
    """
    Build summary statistics from execution tree.

    Returns:
    {
        "total_depth": 3,
        "total_nodes": 7,
        "total_cost": 0.15,
        "total_duration": 9.6,
        "by_depth": {
            0: {"calls": 1, "cost": 0.05, "duration": 2.3},
            1: {"calls": 2, "cost": 0.06, "duration": 4.1},
            2: {"calls": 4, "cost": 0.04, "duration": 3.2}
        }
    }
    """
    if raw is None:
        return None

    tree = build_execution_tree(raw)
    if tree is None:
        return None

    by_depth: dict[int, dict[str, float]] = {}
    total_nodes = 0
    max_depth = 0

    def traverse(node: dict[str, object]) -> None:
        nonlocal total_nodes, max_depth
        total_nodes += 1
        d = int(node.get("depth", 0))
        max_depth = max(max_depth, d)

        if d not in by_depth:
            by_depth[d] = {"calls": 0, "cost": 0.0, "duration": 0.0}

        by_depth[d]["calls"] += 1
        by_depth[d]["cost"] += float(node.get("cost", 0) or 0)
        by_depth[d]["duration"] += float(node.get("duration", 0) or 0)

        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                traverse(child)

    traverse(tree)

    total_cost = sum(d["cost"] for d in by_depth.values())
    total_duration = sum(d["duration"] for d in by_depth.values())

    return {
        "total_depth": max_depth + 1,
        "total_nodes": total_nodes,
        "total_cost": round(total_cost, 6) if total_cost > 0 else None,
        "total_duration": round(total_duration, 3),
        "by_depth": {
            str(d): {
                "calls": int(stats["calls"]),
                "cost": round(stats["cost"], 6) if stats["cost"] > 0 else None,
                "duration": round(stats["duration"], 3),
            }
            for d, stats in sorted(by_depth.items())
        },
    }
