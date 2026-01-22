"""Tantivy full-text search indexer for rlm-cli."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from .context import FileEntry, WalkOptions, collect_directory
from .errors import IndexError as RlmIndexError

if TYPE_CHECKING:
    import tantivy

# Check if tantivy is available
try:
    import tantivy

    TANTIVY_AVAILABLE = True
except ImportError:
    TANTIVY_AVAILABLE = False


def _require_tantivy() -> None:
    """Raise IndexError if tantivy is not installed."""
    if not TANTIVY_AVAILABLE:
        raise RlmIndexError(
            "Tantivy is not installed.",
            why="The 'tantivy' package is required for search functionality.",
            fix="Install with: pip install 'rlm-cli[search]'",
        )


@dataclass(frozen=True)
class IndexConfig:
    """Configuration for the Tantivy indexer."""

    index_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "rlm-cli" / "tantivy")
    heap_size_mb: int = 50
    boosts: dict[str, float] = field(
        default_factory=lambda: {
            "path_stem": 3.0,
            "path": 2.0,
            "content": 1.0,
        }
    )


@dataclass(frozen=True)
class SearchResult:
    """A single search result."""

    path: str
    score: float
    language: str
    doc_id: str
    sha256: str
    bytes_size: int
    snippet: str | None = None


@dataclass
class IndexResult:
    """Result of an indexing operation."""

    indexed_count: int
    skipped_count: int
    total_bytes: int
    warnings: list[str] = field(default_factory=list)
    index_path: Path | None = None


def _get_index_path(root: Path, config: IndexConfig) -> Path:
    """Get the index directory for a given root path."""
    root_hash = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return config.index_dir / root_hash


def _build_schema() -> "tantivy.Schema":
    """Build the Tantivy schema."""
    _require_tantivy()
    schema_builder = tantivy.SchemaBuilder()

    # Searchable fields
    schema_builder.add_text_field("path", stored=True)
    schema_builder.add_text_field("path_stem", stored=False)
    schema_builder.add_text_field("content", stored=False)

    # Stored metadata fields
    schema_builder.add_text_field("language", stored=True)
    schema_builder.add_text_field("doc_id", stored=True)
    schema_builder.add_text_field("sha256", stored=True)
    schema_builder.add_integer_field("bytes_size", stored=True)

    return schema_builder.build()


class RlmIndexer:
    """Tantivy-based full-text search indexer for rlm-cli."""

    def __init__(self, root: Path, config: IndexConfig | None = None) -> None:
        _require_tantivy()
        self.root = root.resolve()
        self.config = config or IndexConfig()
        self._index_path = _get_index_path(self.root, self.config)
        self._index: tantivy.Index | None = None
        self._schema: tantivy.Schema | None = None

    def _ensure_index(self, create: bool = False) -> "tantivy.Index":
        """Ensure the index exists and return it."""
        if self._index is not None:
            return self._index

        self._schema = _build_schema()

        if create:
            self._index_path.mkdir(parents=True, exist_ok=True)
            self._index = tantivy.Index(self._schema, str(self._index_path))
        else:
            if not self._index_path.exists():
                raise RlmIndexError(
                    "Index does not exist.",
                    why=f"No index found at '{self._index_path}'.",
                    fix=f"Run 'rlm index {self.root}' to create one.",
                )
            self._index = tantivy.Index(self._schema, str(self._index_path))

        return self._index

    def index_directory(
        self,
        options: WalkOptions | None = None,
        *,
        force: bool = False,
    ) -> IndexResult:
        """Index all files in the directory.

        Args:
            options: Walk options for collecting files.
            force: If True, clear and rebuild the entire index.

        Returns:
            IndexResult with statistics about the indexing operation.
        """
        if force:
            self.clear()

        index = self._ensure_index(create=True)
        writer = index.writer(self.config.heap_size_mb * 1024 * 1024)

        result = collect_directory(self.root, options=options)
        indexed_count = 0
        skipped_count = 0

        # Load metadata for incremental indexing
        metadata = self._load_metadata()

        for file_entry in result.files:
            path_str = file_entry.path.as_posix()
            content_bytes = file_entry.content.encode("utf-8")
            sha256 = hashlib.sha256(content_bytes).hexdigest()

            # Check if file is already indexed with same hash
            if not force and path_str in metadata.get("files", {}):
                if metadata["files"][path_str].get("sha256") == sha256:
                    skipped_count += 1
                    continue

            # Create document
            doc = tantivy.Document()
            doc.add_text("path", path_str)
            doc.add_text("path_stem", file_entry.path.stem)
            doc.add_text("content", file_entry.content)
            doc.add_text("language", _language_from_path(file_entry.path))
            doc.add_text("doc_id", f"doc-{indexed_count + 1:04d}")
            doc.add_text("sha256", sha256)
            doc.add_integer("bytes_size", file_entry.size)

            writer.add_document(doc)
            indexed_count += 1

            # Update metadata
            if "files" not in metadata:
                metadata["files"] = {}
            metadata["files"][path_str] = {
                "sha256": sha256,
                "indexed_at": _timestamp(),
            }

        writer.commit()
        self._save_metadata(metadata)

        return IndexResult(
            indexed_count=indexed_count,
            skipped_count=skipped_count,
            total_bytes=result.total_bytes,
            warnings=result.warnings,
            index_path=self._index_path,
        )

    def search(
        self,
        query: str,
        limit: int = 20,
        language: str | None = None,
    ) -> list[SearchResult]:
        """Search the index.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            language: Optional language filter.

        Returns:
            List of SearchResult objects, sorted by relevance.
        """
        index = self._ensure_index(create=False)
        index.reload()
        searcher = index.searcher()

        # Build query with field boosts
        boosts = self.config.boosts
        query_parts = []
        for field_name, boost in boosts.items():
            if field_name == "content":
                query_parts.append(f"content:{query}^{boost}")
            elif field_name == "path":
                query_parts.append(f"path:{query}^{boost}")
            elif field_name == "path_stem":
                query_parts.append(f"path_stem:{query}^{boost}")

        combined_query = " OR ".join(query_parts)
        parsed_query = index.parse_query(combined_query, ["path", "path_stem", "content"])

        search_results = searcher.search(parsed_query, limit).hits
        results: list[SearchResult] = []

        for score, doc_address in search_results:
            doc = searcher.doc(doc_address)
            doc_language = _get_field_value(doc, "language")

            # Apply language filter
            if language and doc_language != language:
                continue

            results.append(
                SearchResult(
                    path=_get_field_value(doc, "path"),
                    score=score,
                    language=doc_language,
                    doc_id=_get_field_value(doc, "doc_id"),
                    sha256=_get_field_value(doc, "sha256"),
                    bytes_size=_get_int_field_value(doc, "bytes_size"),
                )
            )

        return results

    def clear(self) -> None:
        """Clear the index and metadata."""
        import shutil

        if self._index_path.exists():
            shutil.rmtree(self._index_path)
        self._index = None
        self._schema = None

    def get_indexed_paths(self) -> set[str]:
        """Get the set of currently indexed file paths."""
        metadata = self._load_metadata()
        return set(metadata.get("files", {}).keys())

    def _load_metadata(self) -> dict:
        """Load index metadata from disk."""
        metadata_path = self._index_path / "rlm_metadata.json"
        if metadata_path.exists():
            try:
                return json.loads(metadata_path.read_text())
            except (json.JSONDecodeError, OSError):
                return {"root": str(self.root), "files": {}}
        return {"root": str(self.root), "files": {}}

    def _save_metadata(self, metadata: dict) -> None:
        """Save index metadata to disk."""
        metadata_path = self._index_path / "rlm_metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2))


def _language_from_path(path: Path) -> str:
    """Determine language from file extension."""
    ext = path.suffix.lower().lstrip(".")
    if not ext:
        return "text"
    return {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "jsx": "javascript",
        "tsx": "typescript",
        "json": "json",
        "yml": "yaml",
        "yaml": "yaml",
        "toml": "toml",
        "md": "markdown",
        "rst": "rst",
        "go": "go",
        "rs": "rust",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "h": "c",
    }.get(ext, ext)


def _get_field_value(doc: "tantivy.Document", field: str) -> str:
    """Extract a text field value from a Tantivy document."""
    values = doc.get_all(field)
    if values:
        return str(values[0])
    return ""


def _get_int_field_value(doc: "tantivy.Document", field: str) -> int:
    """Extract an integer field value from a Tantivy document."""
    values = doc.get_all(field)
    if values:
        try:
            return int(values[0])
        except (ValueError, TypeError):
            return 0
    return 0


def _timestamp() -> str:
    """Return current ISO timestamp."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def filter_files_by_search(
    files: Sequence[FileEntry],
    query: str,
    root: Path,
    config: IndexConfig | None = None,
    limit: int = 50,
) -> list[FileEntry]:
    """Filter a list of files using search results.

    This function takes already-collected files and filters them based on
    search results. Useful for the --search flag in the ask command.

    Args:
        files: List of FileEntry objects to filter.
        query: Search query string.
        root: Root directory for the index.
        config: Optional index configuration.
        limit: Maximum number of files to return.

    Returns:
        Filtered list of FileEntry objects, ordered by search relevance.
    """
    if not TANTIVY_AVAILABLE:
        # Fall back to simple substring matching if tantivy not available
        query_lower = query.lower()
        matched = [
            f for f in files
            if query_lower in f.content.lower() or query_lower in str(f.path).lower()
        ]
        return matched[:limit]

    indexer = RlmIndexer(root, config)
    results = indexer.search(query, limit=limit)

    # Filter and sort files by search result order
    path_to_entry = {f.path.as_posix(): f for f in files}
    filtered: list[FileEntry] = []

    for result in results:
        if result.path in path_to_entry:
            filtered.append(path_to_entry[result.path])

    return filtered
