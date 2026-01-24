"""CLI entrypoints for rlm."""

from __future__ import annotations

import importlib.metadata
import json
import time
from pathlib import Path
from typing import Any, Iterable

import typer

from .config import DEFAULT_CONFIG, load_effective_config, render_effective_config_text
from .context import WalkOptions, build_context_from_sources
from .errors import (
    CliError,
    CliUsageError,
    IndexError,
    ModelError,
    format_error_json,
    format_error_text,
)
from .inputs import parse_inputs
from .output import (
    attach_captured_stdout,
    build_output,
    capture_stdout,
    emit_json,
    emit_text,
)
from .rlm_adapter import parse_json_args, parse_kv_args, run_completion

DEFAULT_EXTENSIONS = [
    ".py",
    ".ts",
    ".js",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
]

DEFAULT_MAX_FILE_BYTES = 1_000_000
DEFAULT_MAX_TOTAL_BYTES = 50_000_000

APP_EPILOG = """\
Examples:
  rlm ask . -q "Find the entrypoint and explain config loading"
  rlm ask rlm/core/rlm.py -q "Summarize constructor params" --json
  git diff | rlm ask - -q "Review this diff" --json
  rlm complete "Write a commit message" --json

Precedence: CLI flags > environment > config > defaults.
"""

ASK_EPILOG = """\
Input modes:
  - paths (files/dirs), '-' for stdin, or literals with --literal.
  - use --path to force filesystem interpretation.
"""

# System prompt template for search tools when available
# Use SEARCH_TOOL_PROMPT_TEMPLATE.format(indexed_root=...) to fill in the path
SEARCH_TOOL_PROMPT_TEMPLATE = """\

You have access to two search tools for exploring the codebase:

## 1. rg.search() - Fast Pattern Scanning (ripgrep)
Use for exact/regex matches over raw files. Returns line-level hits.

```repl
from rlm_cli.tools_search import rg, scan

# Find exact pattern
hits = rg.search(pattern="TODO", paths=["{indexed_root}"], globs=["*.py"])
for h in hits:
    print(f"{{h['path']}}:{{h['line']}}: {{h['text']}}")

# Or use the alias
hits = scan(pattern="class.*Error", paths=["{indexed_root}"], regex=True)
```

## 2. tv.search() - Ranked Document Search (Tantivy)
Use for BM25 ranked search over indexed documents. Returns doc-level results.

```repl
from rlm_cli.tools_search import tv, recall

# Find relevant files by topic
results = tv.search(query="error handling", limit=10, root="{indexed_root}")
for r in results:
    print(f"{{r['path']}} (score: {{r['score']:.2f}})")

# Or use the alias
results = recall(query="authentication flow", limit=20, root="{indexed_root}")
```

**When to use which:**
- Use `rg.search()` / `scan()` for: exact strings, function names, imports, TODOs
- Use `tv.search()` / `recall()` for: concepts, topics, finding related files
"""

# System prompt template for Exa web search when enabled
EXA_TOOL_PROMPT_TEMPLATE = """\

## 3. exa.search() - Web Search (Exa)
Use for searching the web with neural search. Returns web page results.

```repl
from rlm_cli.tools_search import exa, web

# Search the web
results = exa.search(query="Python async best practices", limit=5)
for r in results:
    print(f"{{r['title']}}: {{r['url']}}")

# With highlights (relevant text excerpts)
results = exa.search(
    query="transformer architecture",
    limit=5,
    include_highlights=True
)

# Or use the alias
results = web(query="error handling patterns", limit=10)
```

**When to use exa.search() / web():**
- External documentation and tutorials
- Recent news or articles
- Finding similar pages to a URL
- Research beyond the local codebase
"""

app = typer.Typer(
    add_completion=False,
    help="Run RLM completions with optional context.",
    epilog=APP_EPILOG,
    no_args_is_help=True,
)


def _version_text() -> str:
    try:
        return importlib.metadata.version("rlm-cli")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _version_callback(value: bool) -> None:
    if not value:
        return
    typer.echo(_version_text())
    raise typer.Exit(code=0)


@app.callback()
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    ctx.obj = {"json": json_output, "version": version}


@app.command(help="Ask the RLM backend with optional context.", epilog=ASK_EPILOG)
def ask(
    ctx: typer.Context,
    inputs: list[str] = typer.Argument(
        None,
        help="Files, directories, '-' for stdin, or text with --literal.",
    ),
    question: str = typer.Option(
        ...,
        "-q",
        "--question",
        help="Root question or instruction.",
    ),
    backend: str | None = typer.Option(None, help="Backend provider name."),
    model: str | None = typer.Option(None, help="Model override (backend-specific)."),
    environment: str | None = typer.Option(None, help="Execution environment."),
    max_iterations: int | None = typer.Option(None, help="Maximum iterations."),
    max_depth: int | None = typer.Option(None, help="Maximum recursion depth (enables recursive RLM calls)."),
    max_budget: float | None = typer.Option(None, help="Maximum budget in USD (requires cost-tracking backend like OpenRouter)."),
    max_timeout: float | None = typer.Option(None, help="Maximum execution time in seconds."),
    max_tokens: int | None = typer.Option(None, help="Maximum total tokens (input + output)."),
    max_errors: int | None = typer.Option(None, help="Maximum consecutive errors before stopping."),
    verbose: bool = typer.Option(False, help="Enable verbose logging."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    quiet: bool = typer.Option(False, help="Suppress non-error logs."),
    config: str | None = typer.Option(None, help="Path to YAML config file."),
    output_format: str | None = typer.Option(
        None,
        "--output-format",
        help="Output format: text or json.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON.",
    ),
    output: str | None = typer.Option(None, help="Write output to file."),
    log_dir: str | None = typer.Option(None, help="Enable RLM logging."),
    dir_mode: str | None = typer.Option(
        None,
        help="Directory mode: docs (structured) or files (raw).",
    ),
    extensions: list[str] = typer.Option(
        None,
        "--extensions",
        help="File extensions (repeat or comma-separated).",
    ),
    include: list[str] = typer.Option(
        (),
        "--include",
        help="Include glob patterns.",
    ),
    exclude: list[str] = typer.Option(
        (),
        "--exclude",
        help="Exclude glob patterns.",
    ),
    respect_gitignore: bool | None = typer.Option(
        None,
        "--respect-gitignore/--no-respect-gitignore",
        help="Respect .gitignore when present.",
    ),
    max_file_bytes: int | None = typer.Option(
        None,
        help="Maximum bytes per file.",
    ),
    max_total_bytes: int | None = typer.Option(
        None,
        help="Maximum total bytes across files.",
    ),
    encoding: str | None = typer.Option(None, help="File encoding."),
    binary: str | None = typer.Option(None, help="Binary handling: skip or error."),
    hidden: bool | None = typer.Option(
        None,
        "--hidden/--no-hidden",
        help="Include hidden files.",
    ),
    follow_symlinks: bool | None = typer.Option(
        None,
        "--follow-symlinks/--no-follow-symlinks",
        help="Follow symlinks when walking directories.",
    ),
    markitdown: bool = typer.Option(
        True,
        "--markitdown/--no-markitdown",
        help="Convert URLs and non-text files to Markdown when possible.",
    ),
    no_index: bool = typer.Option(
        False,
        "--no-index",
        help="Skip auto-indexing directories (search tool still available).",
    ),
    use_exa: bool = typer.Option(
        False,
        "--exa",
        help="Enable Exa web search (requires EXA_API_KEY env var).",
    ),
    backend_arg: list[str] = typer.Option(
        (),
        "--backend-arg",
        help="Backend KEY=VALUE arguments.",
    ),
    env_arg: list[str] = typer.Option(
        (),
        "--env-arg",
        help="Environment KEY=VALUE arguments.",
    ),
    rlm_arg: list[str] = typer.Option(
        (),
        "--rlm-arg",
        help="RLM KEY=VALUE arguments.",
    ),
    backend_json: list[str] = typer.Option(
        (),
        "--backend-json",
        help="Backend JSON file (prefix with @).",
    ),
    env_json: list[str] = typer.Option(
        (),
        "--env-json",
        help="Environment JSON file (prefix with @).",
    ),
    rlm_json: list[str] = typer.Option(
        (),
        "--rlm-json",
        help="RLM JSON file (prefix with @).",
    ),
    inject_file: str | None = typer.Option(
        None,
        "--inject-file",
        help="Python file to execute between iterations (update variables mid-run).",
    ),
    literal: bool = typer.Option(
        False,
        "--literal",
        help="Treat inputs as literal text.",
    ),
    path: bool = typer.Option(
        False,
        "--path",
        help="Treat inputs as filesystem paths.",
    ),
    print_effective_config: bool = typer.Option(
        False,
        "--print-effective-config",
        help="Print merged config for debugging.",
    ),
) -> None:
    _run_ask(
        ctx,
        inputs,
        question,
        backend,
        model,
        environment,
        max_iterations,
        max_depth,
        max_budget,
        max_timeout,
        max_tokens,
        max_errors,
        verbose,
        debug,
        quiet,
        config,
        output_format,
        json_output,
        output,
        log_dir,
        dir_mode,
        extensions,
        include,
        exclude,
        respect_gitignore,
        max_file_bytes,
        max_total_bytes,
        encoding,
        binary,
        hidden,
        follow_symlinks,
        markitdown,
        no_index,
        use_exa,
        backend_arg,
        env_arg,
        rlm_arg,
        backend_json,
        env_json,
        rlm_json,
        inject_file,
        literal,
        path,
        print_effective_config,
    )


@app.command(help="Complete a prompt without extra context.")
def complete(
    ctx: typer.Context,
    text: str = typer.Argument(..., help="Prompt text."),
    backend: str | None = typer.Option(None, help="Backend provider name."),
    model: str | None = typer.Option(None, help="Model override (backend-specific)."),
    environment: str | None = typer.Option(None, help="Execution environment."),
    max_iterations: int | None = typer.Option(None, help="Maximum iterations."),
    max_depth: int | None = typer.Option(None, help="Maximum recursion depth (enables recursive RLM calls)."),
    max_budget: float | None = typer.Option(None, help="Maximum budget in USD (requires cost-tracking backend like OpenRouter)."),
    max_timeout: float | None = typer.Option(None, help="Maximum execution time in seconds."),
    max_tokens: int | None = typer.Option(None, help="Maximum total tokens (input + output)."),
    max_errors: int | None = typer.Option(None, help="Maximum consecutive errors before stopping."),
    verbose: bool = typer.Option(False, help="Enable verbose logging."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    quiet: bool = typer.Option(False, help="Suppress non-error logs."),
    config: str | None = typer.Option(None, help="Path to YAML config file."),
    output_format: str | None = typer.Option(
        None,
        "--output-format",
        help="Output format: text or json.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON.",
    ),
    output: str | None = typer.Option(None, help="Write output to file."),
    log_dir: str | None = typer.Option(None, help="Enable RLM logging."),
    backend_arg: list[str] = typer.Option(
        (),
        "--backend-arg",
        help="Backend KEY=VALUE arguments.",
    ),
    env_arg: list[str] = typer.Option(
        (),
        "--env-arg",
        help="Environment KEY=VALUE arguments.",
    ),
    rlm_arg: list[str] = typer.Option(
        (),
        "--rlm-arg",
        help="RLM KEY=VALUE arguments.",
    ),
    backend_json: list[str] = typer.Option(
        (),
        "--backend-json",
        help="Backend JSON file (prefix with @).",
    ),
    env_json: list[str] = typer.Option(
        (),
        "--env-json",
        help="Environment JSON file (prefix with @).",
    ),
    rlm_json: list[str] = typer.Option(
        (),
        "--rlm-json",
        help="RLM JSON file (prefix with @).",
    ),
    inject_file: str | None = typer.Option(
        None,
        "--inject-file",
        help="Python file to execute between iterations (update variables mid-run).",
    ),
    print_effective_config: bool = typer.Option(
        False,
        "--print-effective-config",
        help="Print merged config for debugging.",
    ),
) -> None:
    _run_complete(
        ctx,
        text,
        backend,
        model,
        environment,
        max_iterations,
        max_depth,
        max_budget,
        max_timeout,
        max_tokens,
        max_errors,
        verbose,
        debug,
        quiet,
        config,
        output_format,
        json_output,
        output,
        log_dir,
        backend_arg,
        env_arg,
        rlm_arg,
        backend_json,
        env_json,
        rlm_json,
        inject_file,
        print_effective_config,
    )


@app.command(help="Run diagnostics on configuration and environment.")
def doctor(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output JSON diagnostics."),
) -> None:
    from .doctor import run_doctor

    json_mode = _resolve_json_mode(ctx, None, json_output)
    result = run_doctor(json_mode=json_mode)
    if json_mode:
        emit_json(result)
    else:
        emit_text(result["text"], warnings=result.get("warnings", []))


@app.command(help="Print the CLI spec.")
def spec(ctx: typer.Context, json_output: bool = typer.Option(True, "--json")) -> None:
    from .spec import build_spec

    payload = build_spec()
    if json_output:
        emit_json(payload)
    else:
        emit_text(json.dumps(payload, indent=2, ensure_ascii=True))


@app.command(help="Print the JSON schema for request/response.")
def schema(ctx: typer.Context) -> None:
    from .schema import output_schema

    emit_text(json.dumps(output_schema(), indent=2, ensure_ascii=True))


@app.command(help="List available OpenRouter models.")
def models(
    ctx: typer.Context,
    filter_query: str = typer.Argument(None, help="Filter models by name or ID."),
    sort_by: str = typer.Option(
        "id",
        "--sort",
        "-s",
        help="Sort by: id, name, context, or price.",
    ),
    show_pricing: bool = typer.Option(
        False,
        "--pricing",
        "-p",
        help="Show pricing information.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        "-r",
        help="Force refresh from API (bypass cache).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    from .models import fetch_models, format_model_list

    json_mode = _resolve_json_mode(ctx, None, json_output)

    try:
        model_list = fetch_models(force_refresh=refresh)
    except RuntimeError as exc:
        error = ModelError(
            "Failed to fetch models.",
            why=str(exc),
            fix="Check your OPENROUTER_API_KEY and network connection.",
            try_steps=["export OPENROUTER_API_KEY=sk-or-..."],
        )
        _handle_cli_error(error, json_mode, None)
        return

    if json_mode:
        # Filter if requested
        if filter_query:
            query_lower = filter_query.lower()
            model_list = [
                m for m in model_list
                if query_lower in m.id.lower() or query_lower in m.name.lower()
            ]

        payload = build_output(
            ok=True,
            exit_code=0,
            result={
                "count": len(model_list),
                "models": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "context_length": m.context_length,
                        "pricing_prompt": m.pricing_prompt,
                        "pricing_completion": m.pricing_completion,
                    }
                    for m in model_list
                ],
            },
            warnings=[],
        )
        emit_json(payload)
    else:
        output = format_model_list(
            model_list,
            filter_query=filter_query,
            sort_by=sort_by,
            show_pricing=show_pricing,
        )
        emit_text(output)


@app.command(help="Build or update the search index for a directory.")
def index(
    ctx: typer.Context,
    path: str = typer.Argument(".", help="Directory to index."),
    force: bool = typer.Option(False, "--force", help="Force full reindex."),
    extensions: list[str] = typer.Option(
        None,
        "--extensions",
        help="File extensions (repeat or comma-separated).",
    ),
    include: list[str] = typer.Option(
        (),
        "--include",
        help="Include glob patterns.",
    ),
    exclude: list[str] = typer.Option(
        (),
        "--exclude",
        help="Exclude glob patterns.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    from pathlib import Path as PathLib

    from .indexer import TANTIVY_AVAILABLE, IndexConfig, RlmIndexer

    json_mode = _resolve_json_mode(ctx, None, json_output)

    if not TANTIVY_AVAILABLE:
        error = IndexError(
            "Tantivy is not installed.",
            why="The 'tantivy' package is required for search functionality.",
            fix="Install with: pip install 'rlm-cli[search]'",
        )
        _handle_cli_error(error, json_mode, None)
        return

    try:
        root = PathLib(path).resolve()
        if not root.exists():
            raise IndexError(
                "Directory not found.",
                why=f"'{path}' does not exist.",
                fix="Check the path and try again.",
            )
        if not root.is_dir():
            raise IndexError(
                "Not a directory.",
                why=f"'{path}' is a file, not a directory.",
                fix="Provide a directory path.",
            )

        walk_opts = WalkOptions(
            extensions=_parse_extensions(extensions),
            include_globs=_flatten_list(include),
            exclude_globs=_flatten_list(exclude),
            respect_gitignore=True,
            include_hidden=False,
            follow_symlinks=False,
            max_file_bytes=DEFAULT_MAX_FILE_BYTES,
            max_total_bytes=DEFAULT_MAX_TOTAL_BYTES,
            binary_policy="skip",
            exclude_lockfiles=True,
            encoding="utf-8",
            use_markitdown=False,
        )

        indexer = RlmIndexer(root, IndexConfig())
        result = indexer.index_directory(walk_opts, force=force)

        if json_mode:
            payload = build_output(
                ok=True,
                exit_code=0,
                result={
                    "indexed": result.indexed_count,
                    "skipped": result.skipped_count,
                    "total_bytes": result.total_bytes,
                    "index_path": str(result.index_path) if result.index_path else None,
                },
                warnings=result.warnings,
            )
            emit_json(payload)
        else:
            emit_text(
                f"Indexed {result.indexed_count} files ({result.skipped_count} unchanged)\n"
                f"Total: {result.total_bytes:,} bytes\n"
                f"Index: {result.index_path}",
                warnings=result.warnings,
            )
    except CliError as exc:
        _handle_cli_error(exc, json_mode, None)


@app.command(help="Search indexed documents.")
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query."),
    path: str = typer.Option(".", "--path", "-p", help="Directory to search."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results."),
    language: str | None = typer.Option(None, "--language", "-l", help="Filter by language."),
    paths_only: bool = typer.Option(False, "--paths-only", help="Output paths only."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    from pathlib import Path as PathLib

    from .indexer import TANTIVY_AVAILABLE, IndexConfig, RlmIndexer

    json_mode = _resolve_json_mode(ctx, None, json_output)

    if not TANTIVY_AVAILABLE:
        error = IndexError(
            "Tantivy is not installed.",
            why="The 'tantivy' package is required for search functionality.",
            fix="Install with: pip install 'rlm-cli[search]'",
        )
        _handle_cli_error(error, json_mode, None)
        return

    try:
        root = PathLib(path).resolve()
        if not root.exists():
            raise IndexError(
                "Directory not found.",
                why=f"'{path}' does not exist.",
                fix="Check the path and try again.",
            )

        indexer = RlmIndexer(root, IndexConfig())
        results = indexer.search(query, limit=limit, language=language)

        if json_mode:
            payload = build_output(
                ok=True,
                exit_code=0,
                result={
                    "query": query,
                    "count": len(results),
                    "results": [
                        {
                            "path": r.path,
                            "score": r.score,
                            "language": r.language,
                            "doc_id": r.doc_id,
                            "bytes_size": r.bytes_size,
                        }
                        for r in results
                    ],
                },
                warnings=[],
            )
            emit_json(payload)
        elif paths_only:
            for r in results:
                typer.echo(r.path)
        else:
            if not results:
                emit_text("No results found.")
            else:
                lines = [f"Found {len(results)} result(s) for '{query}':", ""]
                for r in results:
                    lines.append(f"  {r.path} ({r.language}, score: {r.score:.2f})")
                emit_text("\n".join(lines))
    except CliError as exc:
        _handle_cli_error(exc, json_mode, None)


def _run_ask(
    ctx: typer.Context,
    inputs: list[str],
    question: str,
    backend: str | None,
    model: str | None,
    environment: str | None,
    max_iterations: int | None,
    max_depth: int | None,
    max_budget: float | None,
    max_timeout: float | None,
    max_tokens: int | None,
    max_errors: int | None,
    verbose: bool,
    debug: bool,
    quiet: bool,
    config: str | None,
    output_format: str | None,
    json_output: bool,
    output: str | None,
    log_dir: str | None,
    dir_mode: str | None,
    extensions: list[str] | None,
    include: Iterable[str],
    exclude: Iterable[str],
    respect_gitignore: bool | None,
    max_file_bytes: int | None,
    max_total_bytes: int | None,
    encoding: str | None,
    binary: str | None,
    hidden: bool | None,
    follow_symlinks: bool | None,
    markitdown: bool,
    no_index: bool,
    use_exa: bool,
    backend_arg: Iterable[str],
    env_arg: Iterable[str],
    rlm_arg: Iterable[str],
    backend_json: Iterable[str],
    env_json: Iterable[str],
    rlm_json: Iterable[str],
    inject_file: str | None,
    literal: bool,
    path: bool,
    print_effective_config: bool,
) -> None:
    effective_verbose = verbose or debug
    if effective_verbose and quiet:
        raise CliUsageError(
            "Cannot use --verbose and --quiet together.",
            fix="Choose only one verbosity flag.",
        )
    if literal and path:
        raise CliUsageError(
            "Cannot use --literal and --path together.",
            fix="Choose one input interpretation flag.",
        )

    try:
        json_flag = _resolve_json_mode(ctx, output_format, json_output)
        cli_overrides = _build_cli_overrides(
            backend=backend,
            model=model,
            environment=environment,
            max_iterations=max_iterations,
            max_depth=max_depth,
            output_format=output_format,
            log_dir=log_dir,
        )
        effective = load_effective_config(
            cli_overrides=cli_overrides,
            cli_config_path=config,
            defaults=DEFAULT_CONFIG,
        )
        output_format_final = _resolve_output_format(
            json_flag,
            output_format,
            effective,
        )
        json_mode = output_format_final == "json"

        effective_config_debug: dict[str, object] | None = None
        if print_effective_config:
            if json_mode:
                effective_config_debug = dict(effective.data)
            else:
                _emit_effective_config(effective.data, json_mode)

        sources = parse_inputs(inputs or [], literal=literal, path=path)
        walk_opts = WalkOptions(
            extensions=_parse_extensions(extensions),
            include_globs=_flatten_list(include),
            exclude_globs=_flatten_list(exclude),
            respect_gitignore=True if respect_gitignore is None else respect_gitignore,
            include_hidden=hidden if hidden is not None else False,
            follow_symlinks=follow_symlinks if follow_symlinks is not None else False,
            max_file_bytes=max_file_bytes
            if max_file_bytes is not None
            else DEFAULT_MAX_FILE_BYTES,
            max_total_bytes=max_total_bytes
            if max_total_bytes is not None
            else DEFAULT_MAX_TOTAL_BYTES,
            binary_policy=binary or "skip",
            exclude_lockfiles=True,
            encoding=encoding or "utf-8",
            use_markitdown=markitdown,
        )
        context_payload, context_result = build_context_from_sources(
            sources,
            options=walk_opts,
            dir_mode=dir_mode or "docs",
        )

        # Auto-index directories so search tool is available to the LLM
        search_tool_available = False
        indexed_root: Path | None = None
        if not no_index:
            from .indexer import TANTIVY_AVAILABLE, IndexConfig, RlmIndexer
            from .inputs import InputKind

            # Find directory inputs for indexing
            dir_roots = [
                s.value for s in sources
                if s.kind == InputKind.DIR and isinstance(s.value, Path)
            ]

            if dir_roots and TANTIVY_AVAILABLE:
                # Auto-index directories (use first directory as the indexed root)
                indexed_root = dir_roots[0].resolve()
                for dir_root in dir_roots:
                    indexer = RlmIndexer(dir_root, IndexConfig())
                    indexer.index_directory(walk_opts, force=False)
                search_tool_available = True

        # Build custom system prompt with search tool appended if available
        custom_system_prompt = None
        search_setup_code = None

        # Check Exa availability if requested
        exa_available = False
        if use_exa:
            import os

            from .tools_search import EXA_AVAILABLE
            if EXA_AVAILABLE and os.environ.get("EXA_API_KEY"):
                exa_available = True
            else:
                import sys
                if not EXA_AVAILABLE:
                    print("Warning: --exa requested but exa-py not installed. "
                          "Install with: pip install 'rlm-cli[exa]'", file=sys.stderr)
                elif not os.environ.get("EXA_API_KEY"):
                    print("Warning: --exa requested but EXA_API_KEY not set.", file=sys.stderr)

        if search_tool_available and indexed_root:
            try:
                from rlm.utils.prompts import RLM_SYSTEM_PROMPT
                search_prompt = SEARCH_TOOL_PROMPT_TEMPLATE.format(
                    indexed_root=str(indexed_root)
                )
                # Add Exa prompt if enabled
                if exa_available:
                    search_prompt += EXA_TOOL_PROMPT_TEMPLATE
                custom_system_prompt = RLM_SYSTEM_PROMPT + search_prompt
                # Setup code to pre-load search tools into REPL namespace
                # configure_root() sets SEARCH_ROOT so rg/tv use project root by default
                search_setup_code = f'''
from rlm_cli.tools_search import rg, tv, scan, recall, configure_root
configure_root("{indexed_root}")
tv.ensure_index(root="{indexed_root}", force=False)
'''
                # Add Exa imports if enabled
                if exa_available:
                    search_setup_code += '''
from rlm_cli.tools_search import exa, web
'''
            except ImportError:
                pass  # RLM not available, skip search tool prompt
        elif exa_available:
            # Exa only (no local search tools)
            try:
                from rlm.utils.prompts import RLM_SYSTEM_PROMPT
                custom_system_prompt = RLM_SYSTEM_PROMPT + EXA_TOOL_PROMPT_TEMPLATE
                search_setup_code = '''
from rlm_cli.tools_search import exa, web
'''
            except ImportError:
                pass

        context_payload_obj: object = context_payload
        if (dir_mode or "docs") == "files":
            context_payload_obj = [entry.content for entry in context_result.files]

        backend_kwargs = parse_kv_args(backend_arg, label="--backend-arg")
        environment_kwargs = parse_kv_args(env_arg, label="--env-arg")
        rlm_kwargs = parse_kv_args(rlm_arg, label="--rlm-arg")
        backend_kwargs = _merge_dicts(
            _config_mapping(effective.data.get("backend_kwargs")),
            backend_kwargs,
        )
        environment_kwargs = _merge_dicts(
            _config_mapping(effective.data.get("environment_kwargs")),
            environment_kwargs,
        )
        backend_kwargs = _merge_dicts(
            backend_kwargs,
            parse_json_args(backend_json, label="--backend-json"),
        )
        environment_kwargs = _merge_dicts(
            environment_kwargs,
            parse_json_args(env_json, label="--env-json"),
        )
        # Add search tool setup code to REPL environment
        if search_setup_code:
            environment_kwargs = _merge_dicts(
                environment_kwargs,
                {"setup_code": search_setup_code},
            )
        rlm_kwargs = _merge_dicts(
            rlm_kwargs,
            parse_json_args(rlm_json, label="--rlm-json"),
        )

        resolved_backend = backend or str(effective.data.get("backend"))
        resolved_model = model if model is not None else str(effective.data.get("model") or "")
        resolved_environment = environment or str(effective.data.get("environment"))
        resolved_max_iterations = (
            max_iterations
            if max_iterations is not None
            else _int_from_config(effective.data.get("max_iterations"), 30)
        )
        resolved_max_depth = (
            max_depth
            if max_depth is not None
            else _int_from_config(effective.data.get("max_depth"), 1)
        )
        resolved_log_dir = log_dir
        if resolved_log_dir is None:
            output_cfg = effective.data.get("output")
            if isinstance(output_cfg, dict):
                resolved_log_dir = output_cfg.get("log_dir")

        # Validate model for OpenRouter backend
        _validate_openrouter_model(resolved_model, resolved_backend)

        start = time.monotonic()
        if json_mode:
            with capture_stdout() as buffer:
                result = run_completion(
                    question=question,
                    context_payload=context_payload_obj,
                    backend=resolved_backend,
                    environment=resolved_environment,
                    max_iterations=resolved_max_iterations,
                    max_depth=resolved_max_depth,
                    max_budget=max_budget,
                    max_timeout=max_timeout,
                    max_tokens=max_tokens,
                    max_errors=max_errors,
                    backend_kwargs=backend_kwargs,
                    environment_kwargs=environment_kwargs,
                    rlm_kwargs=rlm_kwargs,
                    model=resolved_model or None,
                    log_dir=resolved_log_dir,
                    verbose=effective_verbose,
                    custom_system_prompt=custom_system_prompt,
                    inject_file=inject_file,
                )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result_data: dict[str, object] = {"response": result.response}
            if result.early_exit:
                result_data["early_exit"] = True
                result_data["early_exit_reason"] = result.early_exit_reason
            payload = build_output(
                ok=True,
                exit_code=0,
                result=result_data,
                request=_build_request(
                    question,
                    inputs,
                    resolved_backend,
                    resolved_model,
                    resolved_environment,
                    resolved_max_iterations,
                    resolved_max_depth,
                    walk_opts,
                    effective_verbose,
                ),
                artifacts=_build_artifacts(resolved_log_dir),
                stats=_build_stats(context_result, elapsed_ms),
                warnings=context_result.warnings,
                debug={"effective_config": effective_config_debug}
                if effective_config_debug is not None
                else None,
            )
            attach_captured_stdout(payload, buffer.getvalue())
            _emit_output(payload, output)
        else:
            result = run_completion(
                question=question,
                context_payload=context_payload_obj,
                backend=resolved_backend,
                environment=resolved_environment,
                max_iterations=resolved_max_iterations,
                max_depth=resolved_max_depth,
                max_budget=max_budget,
                max_timeout=max_timeout,
                max_tokens=max_tokens,
                max_errors=max_errors,
                backend_kwargs=backend_kwargs,
                environment_kwargs=environment_kwargs,
                rlm_kwargs=rlm_kwargs,
                model=resolved_model or None,
                log_dir=resolved_log_dir,
                verbose=effective_verbose,
                custom_system_prompt=custom_system_prompt,
                inject_file=inject_file,
            )
            warnings = list(context_result.warnings)
            if result.early_exit:
                warnings.insert(0, "Stopped early (Ctrl+C) - returning best answer so far")
            _emit_text_output(result.response, output, warnings)
    except CliError as exc:
        _handle_cli_error(exc, json_mode, output)


def _run_complete(
    ctx: typer.Context,
    text: str,
    backend: str | None,
    model: str | None,
    environment: str | None,
    max_iterations: int | None,
    max_depth: int | None,
    max_budget: float | None,
    max_timeout: float | None,
    max_tokens: int | None,
    max_errors: int | None,
    verbose: bool,
    debug: bool,
    quiet: bool,
    config: str | None,
    output_format: str | None,
    json_output: bool,
    output: str | None,
    log_dir: str | None,
    backend_arg: Iterable[str],
    env_arg: Iterable[str],
    rlm_arg: Iterable[str],
    backend_json: Iterable[str],
    env_json: Iterable[str],
    rlm_json: Iterable[str],
    inject_file: str | None,
    print_effective_config: bool,
) -> None:
    effective_verbose = verbose or debug
    if effective_verbose and quiet:
        raise CliUsageError(
            "Cannot use --verbose and --quiet together.",
            fix="Choose only one verbosity flag.",
        )

    try:
        json_flag = _resolve_json_mode(ctx, output_format, json_output)
        cli_overrides = _build_cli_overrides(
            backend=backend,
            model=model,
            environment=environment,
            max_iterations=max_iterations,
            max_depth=max_depth,
            output_format=output_format,
            log_dir=log_dir,
        )
        effective = load_effective_config(
            cli_overrides=cli_overrides,
            cli_config_path=config,
            defaults=DEFAULT_CONFIG,
        )
        output_format_final = _resolve_output_format(
            json_flag,
            output_format,
            effective,
        )
        json_mode = output_format_final == "json"

        effective_config_debug: dict[str, object] | None = None
        if print_effective_config:
            if json_mode:
                effective_config_debug = dict(effective.data)
            else:
                _emit_effective_config(effective.data, json_mode)

        backend_kwargs = parse_kv_args(backend_arg, label="--backend-arg")
        environment_kwargs = parse_kv_args(env_arg, label="--env-arg")
        rlm_kwargs = parse_kv_args(rlm_arg, label="--rlm-arg")
        backend_kwargs = _merge_dicts(
            _config_mapping(effective.data.get("backend_kwargs")),
            backend_kwargs,
        )
        environment_kwargs = _merge_dicts(
            _config_mapping(effective.data.get("environment_kwargs")),
            environment_kwargs,
        )
        backend_kwargs = _merge_dicts(
            backend_kwargs,
            parse_json_args(backend_json, label="--backend-json"),
        )
        environment_kwargs = _merge_dicts(
            environment_kwargs,
            parse_json_args(env_json, label="--env-json"),
        )
        rlm_kwargs = _merge_dicts(
            rlm_kwargs,
            parse_json_args(rlm_json, label="--rlm-json"),
        )

        resolved_backend = backend or str(effective.data.get("backend"))
        resolved_model = model if model is not None else str(effective.data.get("model") or "")
        resolved_environment = environment or str(effective.data.get("environment"))
        resolved_max_iterations = (
            max_iterations
            if max_iterations is not None
            else _int_from_config(effective.data.get("max_iterations"), 30)
        )
        resolved_max_depth = (
            max_depth
            if max_depth is not None
            else _int_from_config(effective.data.get("max_depth"), 1)
        )
        resolved_log_dir = log_dir
        if resolved_log_dir is None:
            output_cfg = effective.data.get("output")
            if isinstance(output_cfg, dict):
                resolved_log_dir = output_cfg.get("log_dir")

        # Validate model for OpenRouter backend
        _validate_openrouter_model(resolved_model, resolved_backend)

        start = time.monotonic()
        if json_mode:
            with capture_stdout() as buffer:
                result = run_completion(
                    question=text,
                    context_payload="",
                    backend=resolved_backend,
                    environment=resolved_environment,
                    max_iterations=resolved_max_iterations,
                    max_depth=resolved_max_depth,
                    max_budget=max_budget,
                    max_timeout=max_timeout,
                    max_tokens=max_tokens,
                    max_errors=max_errors,
                    backend_kwargs=backend_kwargs,
                    environment_kwargs=environment_kwargs,
                    rlm_kwargs=rlm_kwargs,
                    model=resolved_model or None,
                    log_dir=resolved_log_dir,
                    verbose=effective_verbose,
                    inject_file=inject_file,
                )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result_data: dict[str, object] = {"response": result.response}
            if result.early_exit:
                result_data["early_exit"] = True
                result_data["early_exit_reason"] = result.early_exit_reason
            payload = build_output(
                ok=True,
                exit_code=0,
                result=result_data,
                request=_build_request(
                    text,
                    [],
                    resolved_backend,
                    resolved_model,
                    resolved_environment,
                    resolved_max_iterations,
                    resolved_max_depth,
                    None,
                    effective_verbose,
                ),
                artifacts=_build_artifacts(resolved_log_dir),
                stats={"duration_ms": elapsed_ms},
                warnings=[],
                debug={"effective_config": effective_config_debug}
                if effective_config_debug is not None
                else None,
            )
            attach_captured_stdout(payload, buffer.getvalue())
            _emit_output(payload, output)
        else:
            result = run_completion(
                question=text,
                context_payload="",
                backend=resolved_backend,
                environment=resolved_environment,
                max_iterations=resolved_max_iterations,
                max_depth=resolved_max_depth,
                max_budget=max_budget,
                max_timeout=max_timeout,
                max_tokens=max_tokens,
                max_errors=max_errors,
                backend_kwargs=backend_kwargs,
                environment_kwargs=environment_kwargs,
                rlm_kwargs=rlm_kwargs,
                model=resolved_model or None,
                log_dir=resolved_log_dir,
                verbose=effective_verbose,
                inject_file=inject_file,
            )
            warnings: list[str] = []
            if result.early_exit:
                warnings.append("Stopped early (Ctrl+C) - returning best answer so far")
            _emit_text_output(result.response, output, warnings)
    except CliError as exc:
        _handle_cli_error(exc, json_mode, output)


def _resolve_json_mode(
    ctx: typer.Context,
    output_format: str | None,
    json_output: bool = False,
) -> bool:
    json_mode = bool(ctx.obj.get("json")) if ctx.obj else False
    if json_mode:
        return True
    if json_output:
        return True
    if output_format is None:
        return False
    return output_format.lower() == "json"


def _resolve_output_format(
    json_flag: bool,
    output_format: str | None,
    effective: Any,
) -> str:
    if json_flag:
        return "json"
    if output_format:
        return output_format
    output_cfg = effective.data.get("output")
    if isinstance(output_cfg, dict):
        return str(output_cfg.get("format") or "text")
    return "text"


def _parse_extensions(values: list[str] | None) -> list[str]:
    if not values:
        return list(DEFAULT_EXTENSIONS)
    flattened: list[str] = []
    for raw in values:
        flattened.extend(part.strip() for part in raw.split(",") if part.strip())
    return flattened


def _flatten_list(values: Iterable[str]) -> list[str]:
    flattened: list[str] = []
    for raw in values:
        flattened.extend(part.strip() for part in raw.split(",") if part.strip())
    return flattened


def _merge_dicts(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    merged.update(override)
    return merged


def _config_mapping(value: object | None) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _int_from_config(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _build_cli_overrides(
    *,
    backend: str | None,
    model: str | None,
    environment: str | None,
    max_iterations: int | None,
    max_depth: int | None,
    output_format: str | None,
    log_dir: str | None,
) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if backend is not None:
        overrides["backend"] = backend
    if model is not None:
        overrides["model"] = model
    if environment is not None:
        overrides["environment"] = environment
    if max_iterations is not None:
        overrides["max_iterations"] = max_iterations
    if max_depth is not None:
        overrides["max_depth"] = max_depth
    if output_format is not None or log_dir is not None:
        output_override: dict[str, object] = {}
        if output_format is not None:
            output_override["format"] = output_format
        if log_dir is not None:
            output_override["log_dir"] = log_dir
        overrides["output"] = output_override
    return overrides


def _build_request(
    question: str,
    inputs: list[str],
    backend: str,
    model: str,
    environment: str,
    max_iterations: int,
    max_depth: int,
    walk_opts: WalkOptions | None,
    verbose: bool,
) -> dict[str, object]:
    limits: dict[str, object] = {
        "max_iterations": max_iterations,
        "max_depth": max_depth,
    }
    request: dict[str, object] = {
        "question": question,
        "inputs": inputs,
        "backend": backend,
        "model": model,
        "environment": environment,
        "verbose": verbose,
        "limits": limits,
    }
    if walk_opts:
        limits.update(
            {
                "max_file_bytes": walk_opts.max_file_bytes,
                "max_total_bytes": walk_opts.max_total_bytes,
            }
        )
    return request


def _build_artifacts(log_dir: str | None) -> dict[str, object]:
    if not log_dir:
        return {}
    return {"log_dir": log_dir}


def _build_stats(result: Any, duration_ms: int) -> dict[str, object]:
    return {
        "documents": len(result.files),
        "bytes_total": result.total_bytes,
        "duration_ms": duration_ms,
    }


def _emit_effective_config(config: dict[str, object], json_mode: bool) -> None:
    if json_mode:
        return
    typer.echo(render_effective_config_text(config), err=True)


def _emit_output(payload: dict[str, object], output: str | None) -> None:
    if output:
        Path(output).write_text(json.dumps(payload, ensure_ascii=True) + "\n")
        return
    emit_json(payload)


def _emit_text_output(result_text: str, output: str | None, warnings: list[str]) -> None:
    if output:
        Path(output).write_text(result_text + "\n")
        for warning in warnings:
            typer.echo(f"Warning: {warning}", err=True)
        return
    emit_text(result_text, warnings=warnings)


def _handle_cli_error(error: CliError, json_mode: bool, output: str | None) -> None:
    if json_mode:
        payload = build_output(
            ok=False,
            exit_code=error.exit_code,
            error=format_error_json(error),
            warnings=[],
        )
        _emit_output(payload, output)
    else:
        typer.echo(format_error_text(error), err=True)
    raise typer.Exit(code=error.exit_code)


def _validate_openrouter_model(model: str, backend: str) -> None:
    """Validate model ID for OpenRouter backend.

    Raises ModelError if model is invalid.
    """
    if backend != "openrouter" or not model:
        return

    from .models import validate_model

    result = validate_model(model)

    # If there was an error fetching models, log warning but continue
    if result.error:
        import sys
        print(f"Warning: Could not validate model: {result.error}", file=sys.stderr)
        return

    if not result.valid:
        suggestions_text = ""
        if result.suggestions:
            suggestions_text = "\n  - ".join([""] + result.suggestions)
            fix = f"Use a valid model ID. Similar models:{suggestions_text}"
        else:
            fix = "Use 'rlm models' to list available models."

        raise ModelError(
            f"Invalid model: '{model}'",
            why="Model ID not found in OpenRouter's available models.",
            fix=fix,
            try_steps=[
                "rlm models --refresh",
                f"rlm models {model.split('/')[0]}",  # Filter by provider
            ],
        )


if __name__ == "__main__":
    app()
