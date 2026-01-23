---
name: rlm
description: Recursive Language Models (RLM) CLI - enables LLMs to recursively process large contexts by decomposing inputs and calling themselves over parts. Use for code analysis, diff reviews, codebase exploration. Triggers on "rlm ask", "rlm complete", "rlm search", "rlm index".
---

# RLM CLI

Recursive Language Models (RLM) CLI - enables LLMs to handle near-infinite context by recursively decomposing inputs and calling themselves over parts. Supports files, directories, URLs, and stdin.

## Installation

```bash
pip install rlm-cli    # or: pipx install rlm-cli
uvx rlm-cli ask ...    # run without installing
```

Set an API key for your backend (openrouter is default):
```bash
export OPENROUTER_API_KEY=...  # default backend
export OPENAI_API_KEY=...      # for --backend openai
export ANTHROPIC_API_KEY=...   # for --backend anthropic
```

## Commands

### ask - Query with context

```bash
rlm ask <inputs> -q "question"
```

**Inputs** (combinable):
| Type | Example | Notes |
|------|---------|-------|
| Directory | `rlm ask . -q "..."` | Recursive, respects .gitignore |
| File | `rlm ask main.py -q "..."` | Single file |
| URL | `rlm ask https://x.com -q "..."` | Auto-converts to markdown |
| stdin | `git diff \| rlm ask - -q "..."` | `-` reads from pipe |
| Literal | `rlm ask "text" -q "..." --literal` | Treat as raw text |
| Multiple | `rlm ask a.py b.py -q "..."` | Combine any types |

**Options:**
| Flag | Description |
|------|-------------|
| `-q "..."` | Question/prompt (required) |
| `--backend` | Provider: `openrouter` (default), `openai`, `anthropic` |
| `--model NAME` | Model override (format: `provider/model` or just `model`) |
| `--json` | Machine-readable output |
| `--extensions .py .ts` | Filter by extension |
| `--include/--exclude` | Glob patterns |
| `--max-iterations N` | Limit recursive calls (default: 30) |
| `--no-index` | Skip auto-indexing |

**JSON output structure:**
```json
{"ok": true, "exit_code": 0, "result": {"response": "..."}, "stats": {...}}
```

### complete - Query without context

```bash
rlm complete "prompt text"
rlm complete "Generate SQL" --json --backend openai
```

### search - Search indexed files

```bash
rlm search "query" [options]
```

| Flag | Description |
|------|-------------|
| `--limit N` | Max results (default: 20) |
| `--language python` | Filter by language |
| `--paths-only` | Output file paths only |
| `--json` | JSON output |

Auto-indexes on first use. Manual index: `rlm index .`

### index - Build search index

```bash
rlm index .              # Index current dir
rlm index ./src --force  # Force full reindex
```

### doctor - Check setup

```bash
rlm doctor       # Check config, API keys, deps
rlm doctor --json
```

## Workflows

**Git diff review:**
```bash
git diff | rlm ask - -q "Review for bugs"
git diff --cached | rlm ask - -q "Ready to commit?"
git diff HEAD~3 | rlm ask - -q "Summarize changes"
```

**Codebase analysis:**
```bash
rlm ask . -q "Explain architecture"
rlm ask src/ -q "How does auth work?" --extensions .py
```

**Search + analyze:**
```bash
rlm search "database" --paths-only
rlm ask src/db.py -q "How is connection pooling done?"
```

**Compare files:**
```bash
rlm ask old.py new.py -q "What changed?"
```

## Configuration

**Precedence:** CLI flags > env vars > config file > defaults

**Config locations:** `./rlm.yaml`, `./.rlm.yaml`, `~/.config/rlm/config.yaml`

```yaml
backend: openrouter
model: google/gemini-3-flash-preview
max_iterations: 30
```

**Environment variables:**
- `RLM_BACKEND` - Default backend
- `RLM_MODEL` - Default model
- `RLM_CONFIG` - Config file path
- `RLM_JSON=1` - Always output JSON

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | CLI usage error |
| 10 | Input error (file not found) |
| 11 | Config error (missing API key) |
| 20 | Backend/API error |
| 30 | Runtime error |
| 40 | Index/search error |

## LLM Search Tools

When `rlm ask` runs on a directory, the LLM gets search tools:

| Tool | Cost | Privacy | Use For |
|------|------|---------|---------|
| `rg.search()` | Free | Local | Exact patterns, function names, imports |
| `tv.search()` | Free | Local | Topics, concepts, related files |
| `pi.*` | **$$$** | **API** | Hierarchical PDF/document navigation |

### Free Local Tools (auto-loaded)

- **rg.search(pattern, paths, globs)** - ripgrep for exact patterns
- **tv.search(query, limit)** - Tantivy BM25 for concepts

### PageIndex (pi.* - Opt-in, Costs Money)

⚠️ **WARNING**: PageIndex sends document content to LLM APIs and costs money.

**Only use when:**
1. User explicitly requests document/PDF analysis
2. Document has hierarchical structure (reports, manuals)
3. User accepts cost/privacy tradeoffs

**Prerequisites:**
- `OPENROUTER_API_KEY` (or other backend key) must be set in environment
- PageIndex submodule must be initialized
- Run within rlm-cli's virtual environment (has required dependencies)

**Setup (REQUIRED before any pi.* operation):**
```python
import sys
sys.path.insert(0, "/path/to/rlm-cli/rlm")        # rlm submodule
sys.path.insert(0, "/path/to/rlm-cli/pageindex")  # pageindex submodule

from rlm.clients import get_client
from rlm_cli.tools_pageindex import pi

# Configure with existing rlm backend
client = get_client(backend="openrouter", backend_kwargs={"model_name": "google/gemini-2.0-flash-001"})
pi.configure(client)
```

**Indexing (costs $$$):**
```python
# Build tree index - THIS COSTS MONEY (no caching, re-indexes each call)
tree = pi.index(path="report.pdf")
# Returns: PITree object with doc_name, nodes, doc_description, raw
```

**Viewing structure (free after indexing):**
```python
# Display table of contents
print(pi.toc(tree))

# Get section by node_id (IDs are "0000", "0001", "0002", etc.)
section = pi.get_section(tree, "0003")
# Returns: PINode with title, node_id, start_index, end_index, summary, children
# Returns: None if not found

if section:
    print(f"{section.title}: pages {section.start_index}-{section.end_index}")
```

**Finding node IDs:**
Node IDs are assigned sequentially ("0000", "0001", ...) in tree traversal order.
To see all node IDs, access the raw tree structure:
```python
import json
print(json.dumps(tree.raw["structure"], indent=2))
# Each node has: title, node_id, start_index, end_index
```

**pi.* API Reference:**
| Method | Cost | Returns | Description |
|--------|------|---------|-------------|
| `pi.configure(client)` | Free | None | Set rlm backend (REQUIRED first) |
| `pi.status()` | Free | dict | Check availability, config, warning |
| `pi.index(path=str)` | $$$ | PITree | Build tree from PDF |
| `pi.toc(tree, max_depth=3)` | Free | str | Formatted table of contents |
| `pi.get_section(tree, node_id)` | Free | PINode or None | Get section by ID |
| `pi.available()` | Free | bool | Check if PageIndex installed |
| `pi.configured()` | Free | bool | Check if client configured |

**PITree attributes:** `doc_name`, `nodes` (list of PINode), `doc_description`, `raw` (dict)
**PINode attributes:** `title`, `node_id`, `start_index`, `end_index`, `summary` (may be None), `children` (may be None)

**Notes:**
- `summary` is only populated if `add_summaries=True` in `pi.index()`
- `children` is None for leaf nodes (sections with no subsections)
- `tree.raw["structure"]` is a flat list; hierarchy is in PINode.children
- PageIndex extracts document structure (TOC), not content. Use page numbers to locate sections in the original PDF.

**Example output from pi.toc():**
```
📄 annual_report.pdf

• Executive Summary (p.1-5)
• Financial Overview (p.6-20)
  • Revenue (p.6-10)
  • Expenses (p.11-15)
  • Projections (p.16-20)
• Risk Factors (p.21-35)
```
