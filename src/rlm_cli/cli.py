"""CLI entrypoints for rlm."""

from __future__ import annotations

import importlib.metadata

import typer


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


app = typer.Typer(
    add_completion=False,
    help="RLM CLI.",
    no_args_is_help=True,
)


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


def _not_implemented(name: str) -> None:
    typer.echo(f"{name} not implemented yet.", err=True)
    raise typer.Exit(code=1)


@app.command(help="Ask the RLM backend with optional context.")
def ask(ctx: typer.Context) -> None:
    _not_implemented("ask")


@app.command(help="Complete a prompt without extra context.")
def complete(ctx: typer.Context) -> None:
    _not_implemented("complete")


@app.command(help="Run diagnostics on configuration and environment.")
def doctor(ctx: typer.Context) -> None:
    _not_implemented("doctor")


@app.command(help="Print the CLI spec.")
def spec(ctx: typer.Context) -> None:
    _not_implemented("spec")


@app.command(help="Print the JSON schema for request/response.")
def schema(ctx: typer.Context) -> None:
    _not_implemented("schema")
