# tools_pageindex.py
"""PageIndex tool for hierarchical document retrieval via LLM-based tree navigation.

⚠️  IMPORTANT: COST AND PRIVACY CONSIDERATIONS ⚠️

Unlike rg.* (ripgrep) and tv.* (Tantivy) which are FREE and LOCAL:
- PageIndex indexing sends document content to external LLM APIs
- Each index operation costs money (LLM API calls)
- Each tree search costs money (LLM API calls)
- Document content is transmitted to third-party servers

Use PageIndex ONLY when:
1. User explicitly requests it
2. The document benefits from hierarchical navigation (PDFs, reports, manuals)
3. User understands and accepts the cost/privacy tradeoffs

DO NOT use PageIndex by default. Prefer rg.* and tv.* for most tasks.

Usage in REPL:
    from rlm_cli.tools_pageindex import pi

    # First: Configure the LLM backend (required before any operation)
    pi.configure(client)  # Uses whatever rlm backend is already configured

    # Index a PDF (⚠️ COSTS MONEY - sends content to LLM)
    tree = pi.index(path="document.pdf")

    # Search the tree (⚠️ COSTS MONEY - LLM navigates the tree)
    sections = pi.search(tree=tree, query="revenue recognition policy")
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from rlm.clients.base_lm import BaseLM

# ---- Module state -------------------------------------------------------------

_pi_client: Optional[Any] = None
_pi_configured: bool = False


# ---- Availability check -------------------------------------------------------

# Check if pageindex is available
PAGEINDEX_AVAILABLE = False
try:
    # Try to import from the pageindex submodule
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "pageindex"))
    from pageindex.lm_adapter import set_lm_client as _set_lm_client
    from pageindex.page_index import page_index as _page_index
    PAGEINDEX_AVAILABLE = True
except ImportError:
    _set_lm_client = None  # type: ignore
    _page_index = None  # type: ignore


def _require_pageindex() -> None:
    """Raise ImportError if PageIndex is not available."""
    if not PAGEINDEX_AVAILABLE:
        raise ImportError(
            "PageIndex is not available. "
            "Ensure the pageindex submodule is initialized."
        )


def _require_configured() -> None:
    """Raise RuntimeError if PageIndex LLM client is not configured."""
    if not _pi_configured:
        raise RuntimeError(
            "PageIndex LLM client not configured. "
            "Call pi.configure(client) first, where client is an rlm BaseLM instance."
        )


# ---- Data classes -------------------------------------------------------------

@dataclass
class PINode:
    """A node in the PageIndex tree structure.

    Attributes:
        title: Section title
        node_id: Unique identifier
        start_index: Starting page number
        end_index: Ending page number
        summary: Optional section summary
        children: Child nodes (subsections)
    """
    title: str
    node_id: str
    start_index: int
    end_index: int
    summary: Optional[str] = None
    children: Optional[List["PINode"]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = {
            "title": self.title,
            "node_id": self.node_id,
            "start_index": self.start_index,
            "end_index": self.end_index,
        }
        if self.summary:
            d["summary"] = self.summary
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass
class PITree:
    """A PageIndex tree for a document.

    Attributes:
        doc_name: Document filename
        doc_description: Optional document description
        nodes: Top-level tree nodes
        raw: Raw tree structure from PageIndex
    """
    doc_name: str
    nodes: List[PINode]
    doc_description: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = {
            "doc_name": self.doc_name,
            "nodes": [n.to_dict() for n in self.nodes],
        }
        if self.doc_description:
            d["doc_description"] = self.doc_description
        return d

    def __repr__(self) -> str:
        return f"PITree(doc_name={self.doc_name!r}, nodes={len(self.nodes)} top-level sections)"


# ---- PageIndex wrapper --------------------------------------------------------

class pi:
    """
    pi.* = PageIndex hierarchical document navigation.

    ⚠️  WARNING: COSTS MONEY AND SENDS DATA TO EXTERNAL APIs ⚠️

    Unlike rg.* and tv.* which are free and local, PageIndex:
    - Sends document content to LLM APIs during indexing
    - Makes LLM calls during tree search
    - Each operation costs money

    Use ONLY when explicitly requested and user accepts cost/privacy tradeoffs.

    Workflow:
        1. pi.configure(client)     # Set the rlm backend to use
        2. tree = pi.index(path)    # Build tree index (⚠️ COSTS $$$)
        3. pi.toc(tree)             # View table of contents (free)
        4. sections = pi.search(...)# Navigate tree (⚠️ COSTS $$$)

    Example:
        # Configure with existing rlm client
        from rlm.clients import get_client
        client = get_client(backend="openrouter", backend_kwargs={...})
        pi.configure(client)

        # Index a PDF
        tree = pi.index(path="annual_report.pdf")

        # View structure (free - just prints cached tree)
        pi.toc(tree)

        # Search would require additional LLM calls
        # sections = pi.search(tree=tree, query="revenue policy")
    """

    @staticmethod
    def configure(client: "BaseLM") -> None:
        """Configure the LLM backend for PageIndex operations.

        MUST be called before any other pi.* operations.

        Args:
            client: An rlm BaseLM instance (from get_client())

        Example:
            from rlm.clients import get_client
            client = get_client(backend="openrouter", backend_kwargs={"model_name": "..."})
            pi.configure(client)
        """
        _require_pageindex()
        global _pi_client, _pi_configured
        _pi_client = client
        _set_lm_client(client)
        _pi_configured = True

    @staticmethod
    def index(
        *,
        path: str,
        toc_check_pages: int = 20,
        max_pages_per_node: int = 10,
        add_summaries: bool = False,
        add_description: bool = False,
    ) -> PITree:
        """Build a hierarchical tree index for a PDF document.

        ⚠️  WARNING: This operation COSTS MONEY ⚠️
        - Sends document text to LLM API
        - Makes multiple LLM calls to build tree structure
        - Cost depends on document size and model used

        Args:
            path: Path to the PDF file
            toc_check_pages: Number of pages to check for existing TOC (default 20)
            max_pages_per_node: Maximum pages per tree node (default 10)
            add_summaries: Generate summaries for each node (more LLM calls = more $$$)
            add_description: Generate document description (more LLM calls = more $$$)

        Returns:
            PITree: The hierarchical tree structure

        Example:
            tree = pi.index(path="report.pdf")
            print(f"Indexed {tree.doc_name} with {len(tree.nodes)} top-level sections")
        """
        _require_pageindex()
        _require_configured()

        result = _page_index(
            doc=path,
            toc_check_page_num=toc_check_pages,
            max_page_num_each_node=max_pages_per_node,
            if_add_node_id="yes",
            if_add_node_summary="yes" if add_summaries else "no",
            if_add_doc_description="yes" if add_description else "no",
        )

        # Parse result into PITree
        def parse_node(node_dict: Dict[str, Any]) -> PINode:
            children = None
            if "nodes" in node_dict and node_dict["nodes"]:
                children = [parse_node(c) for c in node_dict["nodes"]]
            return PINode(
                title=node_dict.get("title", "Untitled"),
                node_id=node_dict.get("node_id", ""),
                start_index=node_dict.get("start_index", 0),
                end_index=node_dict.get("end_index", 0),
                summary=node_dict.get("summary"),
                children=children,
            )

        structure = result.get("structure", [])
        nodes = [parse_node(n) for n in structure] if structure else []

        return PITree(
            doc_name=result.get("doc_name", "Unknown"),
            doc_description=result.get("doc_description"),
            nodes=nodes,
            raw=result,
        )

    @staticmethod
    def toc(tree: PITree, max_depth: int = 3) -> str:
        """Display the table of contents for an indexed document.

        This operation is FREE - it just prints the cached tree structure.

        Args:
            tree: A PITree from pi.index()
            max_depth: Maximum depth to display (default 3)

        Returns:
            str: Formatted table of contents

        Example:
            tree = pi.index(path="report.pdf")
            print(pi.toc(tree))
        """
        lines = [f"📄 {tree.doc_name}"]
        if tree.doc_description:
            lines.append(f"   {tree.doc_description}")
        lines.append("")

        def format_node(node: PINode, depth: int = 0) -> None:
            if depth >= max_depth:
                return
            indent = "  " * depth
            pages = f"(p.{node.start_index}-{node.end_index})"
            lines.append(f"{indent}• {node.title} {pages}")
            if node.children:
                for child in node.children:
                    format_node(child, depth + 1)

        for node in tree.nodes:
            format_node(node)

        return "\n".join(lines)

    @staticmethod
    def get_section(tree: PITree, node_id: str) -> Optional[PINode]:
        """Get a specific section by node_id.

        This operation is FREE - just searches the cached tree.

        Args:
            tree: A PITree from pi.index()
            node_id: The node_id to find (e.g., "0007")

        Returns:
            PINode if found, None otherwise
        """
        def find_node(nodes: List[PINode]) -> Optional[PINode]:
            for node in nodes:
                if node.node_id == node_id:
                    return node
                if node.children:
                    found = find_node(node.children)
                    if found:
                        return found
            return None

        return find_node(tree.nodes)

    @staticmethod
    def available() -> bool:
        """Check if PageIndex is available."""
        return PAGEINDEX_AVAILABLE

    @staticmethod
    def configured() -> bool:
        """Check if PageIndex LLM client is configured."""
        return _pi_configured

    @staticmethod
    def status() -> Dict[str, Any]:
        """Get PageIndex status information."""
        return {
            "available": PAGEINDEX_AVAILABLE,
            "configured": _pi_configured,
            "warning": (
                "⚠️ PageIndex operations cost money and send data to external APIs. "
                "Use only when explicitly requested."
            ),
        }


# ---- Exports -----------------------------------------------------------------

__all__ = [
    "pi",
    "PINode",
    "PITree",
    "PAGEINDEX_AVAILABLE",
]
