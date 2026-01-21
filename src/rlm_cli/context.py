"""Directory walking and content collection for context building."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
from typing import Iterable, Sequence

import pathspec

from .errors import InputError

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}

DEFAULT_EXCLUDE_FILES = {
    ".DS_Store",
}


@dataclass(frozen=True)
class WalkOptions:
    extensions: Sequence[str] | None = None
    include_globs: Sequence[str] = ()
    exclude_globs: Sequence[str] = ()
    respect_gitignore: bool = True
    include_hidden: bool = False
    follow_symlinks: bool = False
    max_file_bytes: int | None = None
    max_total_bytes: int | None = None
    binary_policy: str = "skip"
    exclude_lockfiles: bool = False


@dataclass(frozen=True)
class FileEntry:
    path: Path
    size: int
    content: str


@dataclass
class WalkResult:
    files: list[FileEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    total_bytes: int = 0


def collect_directory(
    root: Path,
    *,
    options: WalkOptions | None = None,
) -> WalkResult:
    opts = options or WalkOptions()
    root = root.resolve()
    extensions = _normalize_extensions(opts.extensions)
    exclude_spec = _build_spec(opts.exclude_globs)
    include_spec = _build_spec(opts.include_globs)
    gitignore_spec = _load_gitignore(root) if opts.respect_gitignore else None

    result = WalkResult()
    stop = False

    for dirpath, dirnames, filenames in os.walk(
        root, followlinks=opts.follow_symlinks
    ):
        if stop:
            break
        dirpath_path = Path(dirpath)
        rel_dir = dirpath_path.relative_to(root)

        dirnames[:] = [
            d
            for d in dirnames
            if not _should_skip_dir(
                rel_dir / d,
                d,
                include_hidden=opts.include_hidden,
                gitignore_spec=gitignore_spec,
            )
        ]

        for filename in filenames:
            if stop:
                break
            rel_path = rel_dir / filename if rel_dir != Path(".") else Path(filename)
            if _should_skip_file(
                rel_path,
                filename,
                include_hidden=opts.include_hidden,
                extensions=extensions,
                include_spec=include_spec,
                exclude_spec=exclude_spec,
                gitignore_spec=gitignore_spec,
                exclude_lockfiles=opts.exclude_lockfiles,
            ):
                continue

            full_path = root / rel_path
            try:
                size = full_path.stat().st_size
            except OSError as exc:
                result.warnings.append(f"Failed to stat {rel_path}: {exc}")
                continue

            if opts.max_file_bytes is not None and size > opts.max_file_bytes:
                result.warnings.append(
                    f"Skipping {rel_path} (size {size} > max {opts.max_file_bytes})"
                )
                continue

            if opts.max_total_bytes is not None and (
                result.total_bytes + size > opts.max_total_bytes
            ):
                result.warnings.append(
                    "Total byte limit reached; remaining files skipped."
                )
                result.truncated = True
                stop = True
                break

            if _is_binary(full_path):
                if opts.binary_policy == "error":
                    raise InputError(
                        "Binary file detected.",
                        why=f"'{rel_path}' appears to be binary.",
                        fix="Remove the file or adjust binary handling.",
                    )
                result.warnings.append(f"Skipping binary file {rel_path}.")
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                result.warnings.append(f"Failed to read {rel_path}: {exc}")
                continue

            result.files.append(
                FileEntry(
                    path=rel_path,
                    size=size,
                    content=content,
                )
            )
            result.total_bytes += size

    result.files.sort(key=lambda entry: entry.path.as_posix())
    return result


def build_context_payload(
    *,
    root: Path,
    files: Sequence[FileEntry],
    notes: Sequence[str] | None = None,
) -> dict[str, object]:
    root_path = root.resolve()
    notes_list = list(notes or [])
    documents: list[dict[str, object]] = []
    sorted_files = sorted(files, key=lambda entry: entry.path.as_posix())

    for index, entry in enumerate(sorted_files, start=1):
        content_bytes = entry.content.encode("utf-8")
        documents.append(
            {
                "id": f"doc-{index:04d}",
                "path": entry.path.as_posix(),
                "language": _language_from_path(entry.path),
                "bytes": len(content_bytes),
                "sha256": hashlib.sha256(content_bytes).hexdigest(),
                "content": entry.content,
            }
        )

    return {
        "type": "rlm_cli_context_v1",
        "root": root_path.as_posix(),
        "documents": documents,
        "notes": notes_list,
    }


def _normalize_extensions(extensions: Sequence[str] | None) -> set[str] | None:
    if not extensions:
        return None
    normalized: set[str] = set()
    for ext in extensions:
        ext_value = ext.lower()
        if not ext_value.startswith("."):
            ext_value = f".{ext_value}"
        normalized.add(ext_value)
    return normalized


def _build_spec(patterns: Sequence[str]) -> pathspec.PathSpec | None:
    if not patterns:
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return None
    try:
        lines = gitignore_path.read_text().splitlines()
    except OSError:
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _should_skip_dir(
    rel_path: Path,
    name: str,
    *,
    include_hidden: bool,
    gitignore_spec: pathspec.PathSpec | None,
) -> bool:
    if name in DEFAULT_EXCLUDE_DIRS:
        return True
    if not include_hidden and name.startswith("."):
        return True
    if gitignore_spec and gitignore_spec.match_file(rel_path.as_posix() + "/"):
        return True
    return False


def _should_skip_file(
    rel_path: Path,
    name: str,
    *,
    include_hidden: bool,
    extensions: set[str] | None,
    include_spec: pathspec.PathSpec | None,
    exclude_spec: pathspec.PathSpec | None,
    gitignore_spec: pathspec.PathSpec | None,
    exclude_lockfiles: bool,
) -> bool:
    if name in DEFAULT_EXCLUDE_FILES:
        return True
    if exclude_lockfiles and name.endswith(".lock"):
        return True
    if not include_hidden and name.startswith("."):
        return True
    if extensions is not None and rel_path.suffix.lower() not in extensions:
        return True
    if include_spec and not include_spec.match_file(rel_path.as_posix()):
        return True
    if exclude_spec and exclude_spec.match_file(rel_path.as_posix()):
        return True
    if gitignore_spec and gitignore_spec.match_file(rel_path.as_posix()):
        return True
    return False


def _is_binary(path: Path, sample_size: int = 8192) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(sample_size)
    except OSError:
        return False
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    nontext = sum(1 for byte in chunk if byte < 9 or (13 < byte < 32))
    return (nontext / len(chunk)) > 0.3


def _language_from_path(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if not ext:
        return "text"
    return {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "json": "json",
        "yml": "yaml",
        "yaml": "yaml",
        "toml": "toml",
        "md": "markdown",
        "rst": "rst",
    }.get(ext, ext)
