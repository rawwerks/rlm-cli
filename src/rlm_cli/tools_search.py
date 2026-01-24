# tools_search.py
"""Unified search tools for LLM REPL: ripgrep (rg) and Tantivy (tv).

This module provides two complementary search capabilities:
- rg.* : Fast exact/regex pattern matching over files (line-level hits)
- tv.* : Ranked BM25 search over indexed documents (doc-level relevance)

Usage in REPL:
    from rlm_cli.tools_search import rg, tv, scan, recall

    # Exact pattern matching (ripgrep)
    hits = rg.search(pattern="TODO", paths=["src/"])
    hits = scan(pattern="class.*Error", paths=["."], regex=True)

    # Ranked recall (Tantivy index)
    results = tv.search(query="error handling", limit=10)
    results = recall(query="authentication flow", limit=20)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# ---- Module-level search root configuration ----------------------------------

# Global search root - set via configure_root() to override default "." paths
# This is critical for REPL environments where the working directory differs
# from the target codebase.
SEARCH_ROOT: Optional[str] = None


def configure_root(root: str) -> None:
    """Set the default search root for rg.search() and tv.search().

    Call this in REPL setup to ensure searches target the correct directory
    instead of the REPL's working directory.

    Args:
        root: Absolute path to the codebase root directory.
    """
    global SEARCH_ROOT
    SEARCH_ROOT = root


# ---- Ripgrep availability check ----------------------------------------------

try:
    import python_ripgrep

    RIPGREP_AVAILABLE = True
except ImportError:
    python_ripgrep = None
    RIPGREP_AVAILABLE = False


def _require_ripgrep() -> None:
    """Raise ImportError if python-ripgrep is not installed."""
    if not RIPGREP_AVAILABLE:
        raise ImportError(
            "python-ripgrep is not installed. "
            "Install with: pip install 'rlm-cli[search]'"
        )


# ---- Tantivy availability check ----------------------------------------------

try:
    from .indexer import TANTIVY_AVAILABLE, IndexConfig, RlmIndexer
except ImportError:
    TANTIVY_AVAILABLE = False
    IndexConfig = None  # type: ignore[assignment,misc]
    RlmIndexer = None  # type: ignore[assignment,misc]


def _require_tantivy() -> None:
    """Raise ImportError if tantivy is not installed."""
    if not TANTIVY_AVAILABLE:
        raise ImportError(
            "Tantivy is not installed. "
            "Install with: pip install 'rlm-cli[search]'"
        )


# ---- Exa availability check --------------------------------------------------

try:
    import exa_py

    EXA_AVAILABLE = True
except ImportError:
    exa_py = None  # type: ignore[assignment]
    EXA_AVAILABLE = False


def _require_exa() -> None:
    """Raise ImportError if exa-py is not installed."""
    if not EXA_AVAILABLE:
        raise ImportError(
            "exa-py is not installed. "
            "Install with: pip install 'rlm-cli[exa]'"
        )


# ---- Data classes ------------------------------------------------------------


@dataclass
class RGHit:
    """A single ripgrep hit (line-level match).

    Attributes:
        path: File path where match was found
        line: Line number (1-indexed)
        col: Column number (1-indexed, 0 if not available)
        text: The matching line text
    """

    path: str
    line: int
    col: int
    text: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"path": self.path, "line": self.line, "col": self.col, "text": self.text}


@dataclass
class TVHit:
    """A single Tantivy hit (document-level match).

    Attributes:
        doc_id: Document identifier
        score: BM25 relevance score
        path: File path
        language: Detected language
        bytes_size: File size in bytes
    """

    doc_id: str
    score: float
    path: str
    language: str
    bytes_size: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doc_id": self.doc_id,
            "score": self.score,
            "path": self.path,
            "language": self.language,
            "bytes_size": self.bytes_size,
        }


@dataclass
class ExaHit:
    """A single Exa search result (web search).

    Attributes:
        url: URL of the result
        title: Title of the page
        score: Relevance score
        published_date: Publication date (if available)
        author: Author (if available)
        text: Extracted text content (if requested)
        highlights: Relevant text highlights (if requested)
    """

    url: str
    title: str
    score: Optional[float]
    published_date: Optional[str]
    author: Optional[str]
    text: Optional[str]
    highlights: Optional[List[str]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            "url": self.url,
            "title": self.title,
        }
        if self.score is not None:
            result["score"] = self.score
        if self.published_date:
            result["published_date"] = self.published_date
        if self.author:
            result["author"] = self.author
        if self.text:
            result["text"] = self.text
        if self.highlights:
            result["highlights"] = self.highlights
        return result


# ---- Ripgrep wrapper ---------------------------------------------------------


class rg:
    """
    rg.* = ripgrep-style filesystem scan.

    Use for exact/regex matches over raw files.
    Returns line-level hits (path, line, col, text).

    This is FAST SCANNING - no index needed, searches file contents directly.
    Use when you need to find exact patterns, function definitions, imports, etc.

    Example:
        hits = rg.search(pattern="def main", paths=["src/"])
        for hit in hits:
            print(f"{hit['path']}:{hit['line']}: {hit['text']}")
    """

    @staticmethod
    def search(
        *,
        pattern: str,
        paths: Sequence[str] = (".",),
        regex: bool = False,
        globs: Optional[Sequence[str]] = None,
        max_hits: int = 200,
        case_sensitive: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Scan files for PATTERN (NOT indexed). Returns line-level hits.

        Args:
            pattern: The pattern to search for. Literal by default, regex if regex=True.
            paths: Directories or files to search in. Defaults to current directory.
            regex: If True, treat pattern as a regex. Default False (safer for LLMs).
            globs: Optional glob patterns to filter files (e.g., ["*.py", "*.js"]).
            max_hits: Maximum total hits to return. Default 200.
            case_sensitive: Case sensitivity. None = smart case (ripgrep default).

        Returns:
            List of dicts with keys: path, line, col, text

        Example:
            # Find all TODO comments in Python files
            hits = rg.search(pattern="TODO", paths=["src/"], globs=["*.py"])

            # Find function definitions with regex
            hits = rg.search(pattern=r"def\\s+\\w+\\(", paths=["."], regex=True)
        """
        _require_ripgrep()

        # Use SEARCH_ROOT as default when paths is the default (".",)
        effective_paths: Sequence[str] = paths
        if paths == (".",) and SEARCH_ROOT is not None:
            effective_paths = (SEARCH_ROOT,)

        # Escape pattern if not regex mode (safer for LLMs)
        search_pattern = pattern if regex else re.escape(pattern)

        # Build search arguments
        search_paths = [str(p) for p in effective_paths]

        # Call python_ripgrep
        raw_results = python_ripgrep.search(
            patterns=[search_pattern],
            paths=search_paths,
            globs=list(globs) if globs else None,
            line_number=True,
            max_count=max_hits,  # Per-file limit, we'll also enforce total limit
        )

        # Parse results into structured hits
        hits: List[Dict[str, Any]] = []

        # Determine if we're searching a single file (paths won't be in output)
        single_file_path = None
        if len(search_paths) == 1:
            import os
            if os.path.isfile(search_paths[0]):
                single_file_path = search_paths[0]

        for file_group in raw_results:
            # Each file_group is a string like:
            # "path:line:text\npath:line:text\n..." (multiple files)
            # or "line:text\nline:text\n..." (single file, no path prefix)
            for line in file_group.strip().split("\n"):
                if not line:
                    continue

                parts = line.split(":", 2)

                # Try to parse as "path:line:text" first
                if len(parts) >= 3:
                    try:
                        # Check if parts[1] is a line number
                        line_num = int(parts[1])
                        hit = RGHit(
                            path=parts[0],
                            line=line_num,
                            col=0,
                            text=parts[2],
                        )
                        hits.append(hit.to_dict())
                        continue
                    except ValueError:
                        pass

                # Fall back to "line:text" format (single file)
                if len(parts) >= 2 and single_file_path:
                    try:
                        line_num = int(parts[0])
                        hit = RGHit(
                            path=single_file_path,
                            line=line_num,
                            col=0,
                            text=parts[1] if len(parts) == 2 else ":".join(parts[1:]),
                        )
                        hits.append(hit.to_dict())
                    except ValueError:
                        continue

                if len(hits) >= max_hits:
                    break

            if len(hits) >= max_hits:
                break

        return hits

    @staticmethod
    def available() -> bool:
        """Check if ripgrep is available."""
        return RIPGREP_AVAILABLE


# ---- Tantivy wrapper ---------------------------------------------------------

# Global indexer cache for tv.* operations
_tv_indexer: Any = None
_tv_root: Optional[Path] = None


def _get_tv_indexer(root: Path) -> Any:
    """Get or create a Tantivy indexer for the given root."""
    global _tv_indexer, _tv_root

    root = root.resolve()
    if _tv_indexer is None or _tv_root != root:
        _tv_indexer = RlmIndexer(root, IndexConfig())
        _tv_root = root

    return _tv_indexer


class tv:
    """
    tv.* = Tantivy indexed ranked search.

    Use for document-level recall with relevance scoring (BM25).
    Returns ranked docs (doc_id, score, path, language, bytes_size).

    This is SEMANTIC RECALL - requires index to be built first.
    Use when you need to find relevant files by topic/concept.

    Example:
        results = tv.search(query="error handling", limit=10)
        for r in results:
            print(f"{r['path']} (score: {r['score']:.2f})")
    """

    @staticmethod
    def search(
        *,
        query: str,
        limit: int = 20,
        root: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query the Tantivy index (ranked search). Returns doc-level results.

        Args:
            query: Search query string (uses BM25 ranking).
            limit: Maximum number of results. Default 20.
            root: Root directory for the index. Default is current directory.
            language: Optional language filter (e.g., "python", "javascript").

        Returns:
            List of dicts with keys: doc_id, score, path, language, bytes_size

        Example:
            # Find files related to authentication
            results = tv.search(query="authentication login session", limit=10)

            # Find Python files about error handling
            results = tv.search(query="error exception", limit=10, language="python")
        """
        _require_tantivy()

        # Use SEARCH_ROOT as default when root is not specified
        effective_root = root if root is not None else SEARCH_ROOT
        root_path = Path(effective_root) if effective_root else Path(".")
        indexer = _get_tv_indexer(root_path)

        search_results = indexer.search(query, limit=limit, language=language)

        return [
            TVHit(
                doc_id=r.doc_id,
                score=r.score,
                path=r.path,
                language=r.language,
                bytes_size=r.bytes_size,
            ).to_dict()
            for r in search_results
        ]

    @staticmethod
    def available() -> bool:
        """Check if Tantivy is available."""
        return TANTIVY_AVAILABLE

    @staticmethod
    def ensure_index(root: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """Ensure the index exists for the given root directory.

        Args:
            root: Root directory to index. Default is current directory.
            force: If True, rebuild the index from scratch.

        Returns:
            Dict with indexing stats: indexed_count, skipped_count, total_bytes
        """
        _require_tantivy()
        global _tv_indexer, _tv_root

        from .context import WalkOptions

        root_path = Path(root) if root else Path(".")
        # Reset global indexer to force re-creation after indexing
        _tv_indexer = None
        _tv_root = None
        indexer = _get_tv_indexer(root_path)

        # Default walk options for indexing
        walk_opts = WalkOptions(
            extensions=[
                ".py", ".ts", ".js", ".jsx", ".tsx", ".java", ".go", ".rs",
                ".cpp", ".c", ".h", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
            ],
            respect_gitignore=True,
            include_hidden=False,
            follow_symlinks=False,
            max_file_bytes=1_000_000,
            max_total_bytes=50_000_000,
            binary_policy="skip",
            exclude_lockfiles=True,
            encoding="utf-8",
            use_markitdown=False,
        )

        result = indexer.index_directory(walk_opts, force=force)

        return {
            "indexed_count": result.indexed_count,
            "skipped_count": result.skipped_count,
            "total_bytes": result.total_bytes,
            "index_path": str(result.index_path) if result.index_path else None,
        }


# ---- Exa wrapper -------------------------------------------------------------

# Global Exa client cache
_exa_client: Any = None


def _get_exa_client() -> Any:
    """Get or create an Exa client."""
    global _exa_client
    import os

    if _exa_client is None:
        _require_exa()
        api_key = os.environ.get("EXA_API_KEY")
        if not api_key:
            raise ValueError(
                "EXA_API_KEY environment variable is not set. "
                "Get your API key from https://exa.ai and set it in your environment."
            )
        _exa_client = exa_py.Exa(api_key)  # type: ignore[union-attr]

    return _exa_client


class exa:
    """
    exa.* = Exa web search (external API).

    Use for searching the web with neural/keyword search.
    Returns web page results (url, title, text, highlights).

    This is EXTERNAL WEB SEARCH - requires EXA_API_KEY environment variable.
    Use when you need to find information beyond the local codebase.

    Example:
        results = exa.search(query="Python async best practices", limit=5)
        for r in results:
            print(f"{r['title']}: {r['url']}")
    """

    @staticmethod
    def search(
        *,
        query: str,
        limit: int = 10,
        search_type: str = "auto",
        include_domains: Optional[Sequence[str]] = None,
        exclude_domains: Optional[Sequence[str]] = None,
        start_published_date: Optional[str] = None,
        end_published_date: Optional[str] = None,
        include_text: bool = False,
        include_highlights: bool = True,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search the web using Exa. Returns ranked web results.

        Args:
            query: Search query string.
            limit: Maximum number of results. Default 10.
            search_type: Search type - "auto", "neural", or "keyword". Default "auto".
            include_domains: Only include results from these domains.
            exclude_domains: Exclude results from these domains.
            start_published_date: Filter results published after this date (YYYY-MM-DD).
            end_published_date: Filter results published before this date (YYYY-MM-DD).
            include_text: Include full page text in results. Default False.
            include_highlights: Include relevant text highlights. Default True.
            category: Filter by category (e.g., "company", "research paper", "news").

        Returns:
            List of dicts with keys: url, title, score, published_date, author,
            text (if include_text=True), highlights (if include_highlights=True)

        Example:
            # Find recent articles about a topic
            results = exa.search(
                query="transformer architecture explained",
                limit=5,
                include_highlights=True
            )

            # Search specific domains
            results = exa.search(
                query="Python typing",
                include_domains=["docs.python.org", "realpython.com"],
                limit=10
            )
        """
        _require_exa()
        client = _get_exa_client()

        # Build search kwargs
        kwargs: Dict[str, Any] = {
            "query": query,
            "num_results": limit,
            "type": search_type,
        }

        if include_domains:
            kwargs["include_domains"] = list(include_domains)
        if exclude_domains:
            kwargs["exclude_domains"] = list(exclude_domains)
        if start_published_date:
            kwargs["start_published_date"] = start_published_date
        if end_published_date:
            kwargs["end_published_date"] = end_published_date
        if category:
            kwargs["category"] = category

        # Use search_and_contents if we need text or highlights
        if include_text or include_highlights:
            kwargs["text"] = include_text
            kwargs["highlights"] = include_highlights
            response = client.search_and_contents(**kwargs)
        else:
            response = client.search(**kwargs)

        # Parse results into structured hits
        hits: List[Dict[str, Any]] = []
        for result in response.results:
            hit = ExaHit(
                url=result.url,
                title=result.title or "",
                score=getattr(result, "score", None),
                published_date=getattr(result, "published_date", None),
                author=getattr(result, "author", None),
                text=getattr(result, "text", None) if include_text else None,
                highlights=getattr(result, "highlights", None) if include_highlights else None,
            )
            hits.append(hit.to_dict())

        return hits

    @staticmethod
    def find_similar(
        *,
        url: str,
        limit: int = 10,
        exclude_source_domain: bool = True,
        include_text: bool = False,
        include_highlights: bool = True,
    ) -> List[Dict[str, Any]]:
        """Find web pages similar to a given URL.

        Args:
            url: URL to find similar pages for.
            limit: Maximum number of results. Default 10.
            exclude_source_domain: Exclude results from the same domain. Default True.
            include_text: Include full page text in results. Default False.
            include_highlights: Include relevant text highlights. Default True.

        Returns:
            List of dicts with keys: url, title, score, published_date, author,
            text (if include_text=True), highlights (if include_highlights=True)

        Example:
            # Find similar articles
            results = exa.find_similar(
                url="https://example.com/article",
                limit=5
            )
        """
        _require_exa()
        client = _get_exa_client()

        kwargs: Dict[str, Any] = {
            "url": url,
            "num_results": limit,
            "exclude_source_domain": exclude_source_domain,
        }

        if include_text or include_highlights:
            kwargs["text"] = include_text
            kwargs["highlights"] = include_highlights
            response = client.find_similar_and_contents(**kwargs)
        else:
            response = client.find_similar(**kwargs)

        hits: List[Dict[str, Any]] = []
        for result in response.results:
            hit = ExaHit(
                url=result.url,
                title=result.title or "",
                score=getattr(result, "score", None),
                published_date=getattr(result, "published_date", None),
                author=getattr(result, "author", None),
                text=getattr(result, "text", None) if include_text else None,
                highlights=getattr(result, "highlights", None) if include_highlights else None,
            )
            hits.append(hit.to_dict())

        return hits

    @staticmethod
    def available() -> bool:
        """Check if Exa is available (package installed and API key set)."""
        if not EXA_AVAILABLE:
            return False
        import os
        return bool(os.environ.get("EXA_API_KEY"))


# ---- Semantic aliases --------------------------------------------------------

# These provide planner-friendly names for the two search modes:
# - scan() = exact/regex filesystem search (rg.search)
# - recall() = ranked index search (tv.search)


def scan(
    *,
    pattern: str,
    paths: Sequence[str] = (".",),
    regex: bool = False,
    globs: Optional[Sequence[str]] = None,
    max_hits: int = 200,
    case_sensitive: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Alias for rg.search() - scan files for exact/regex patterns.

    Use this for finding exact text matches, function definitions,
    imports, TODOs, etc.

    See rg.search() for full documentation.
    """
    return rg.search(
        pattern=pattern,
        paths=paths,
        regex=regex,
        globs=globs,
        max_hits=max_hits,
        case_sensitive=case_sensitive,
    )


def recall(
    *,
    query: str,
    limit: int = 20,
    root: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Alias for tv.search() - recall relevant documents from index.

    Use this for finding files by topic or concept using
    BM25 ranked search.

    See tv.search() for full documentation.
    """
    return tv.search(query=query, limit=limit, root=root, language=language)


def web(
    *,
    query: str,
    limit: int = 10,
    include_text: bool = False,
    include_highlights: bool = True,
) -> List[Dict[str, Any]]:
    """Alias for exa.search() - search the web for information.

    Use this for finding external information, documentation,
    articles, and web resources.

    See exa.search() for full documentation.
    """
    return exa.search(
        query=query,
        limit=limit,
        include_text=include_text,
        include_highlights=include_highlights,
    )


# ---- Exports -----------------------------------------------------------------

__all__ = [
    "rg",
    "tv",
    "exa",
    "scan",
    "recall",
    "web",
    "configure_root",
    "SEARCH_ROOT",
    "RGHit",
    "TVHit",
    "ExaHit",
    "RIPGREP_AVAILABLE",
    "TANTIVY_AVAILABLE",
    "EXA_AVAILABLE",
]
