# rlm-cli

CLI wrapper for `rlm` with directory-as-context, JSON-first output, and self-documenting commands.

Upstream RLM: https://github.com/alexzhang13/rlm

## Claude Code Plugin

This repo includes a Claude Code plugin with an `rlm` skill. The skill teaches Claude how to use the rlm CLI for code analysis, diff reviews, and codebase exploration.

### Installation

**Claude Code (Interactive)**
```
/plugin marketplace add rawwerks/rlm-cli
/plugin install rlm@rlm-cli
```

**Claude CLI**
```bash
claude plugin marketplace add rawwerks/rlm-cli
claude plugin install rlm@rlm-cli
```

### What the skill provides

The `/rlm` skill gives Claude knowledge of:
- All rlm commands (`ask`, `complete`, `search`, `index`, `doctor`)
- Input types (files, directories, URLs, stdin, literal text)
- Common workflows (diff review, codebase analysis, search + analyze)
- Configuration and environment variables
- Exit codes for error handling

Once installed, Claude can use rlm to analyze code, review diffs, and explore codebases when you ask it to.

## Install

### pip/uv

```bash
uv venv
uv pip install -e .
```

### uvx (no checkout)

```bash
uvx --from git+https://github.com/rawwerks/rlm-cli.git rlm --help
```

## Authentication

Authentication depends on the backend you choose:

- `openrouter`: `OPENROUTER_API_KEY`
- `openai`: `OPENAI_API_KEY`
- `anthropic`: `ANTHROPIC_API_KEY`

Export the appropriate key in your shell environment, for example:

```bash
export OPENROUTER_API_KEY=sk-or-...
```

## Usage

### Ask about a repo

```bash
rlm ask . -q "Summarize this repo" --json
```

### Ask about a URL (auto-Markdown)

```bash
rlm ask https://www.anthropic.com/constitution -q "Summarize this page" --json
```

Same with `uvx` and OpenRouter:

```bash
uvx --from git+https://github.com/rawwerks/rlm-cli.git rlm ask https://www.anthropic.com/constitution -q "Summarize Claude's constitution" --backend openrouter --model google/gemini-3-flash-preview --json
```

### Ask about a file

```bash
rlm ask src/rlm_cli/cli.py -q "Explain the CLI flow" --json
```

### Use stdin as context

```bash
git diff | rlm ask - -q "Review this diff" --json
```

### No context, just a completion

```bash
rlm complete "Write a commit message" --json
```

### OpenRouter quickstart

```bash
rlm complete "Say hello" --backend openrouter --model z-ai/glm-4.7:turbo --json
```

## Options

- `--json` outputs JSON only on stdout.
- `--output-format text|json` sets output format.
- `--backend`, `--model`, `--environment` control the RLM backend.
- `--max-iterations N` sets max REPL iterations (default: 30).
- `--max-depth N` enables recursive RLM calls (default: 1, no recursion).
- `--max-budget N.NN` limits spending in USD (requires cost-tracking backend like OpenRouter).
- `--backend-arg/--env-arg/--rlm-arg KEY=VALUE` pass extra kwargs.
- `--backend-json/--env-json/--rlm-json @file.json` merge JSON kwargs.
- `--literal` treats inputs as literal text; `--path` forces filesystem paths.
- `--markitdown/--no-markitdown` toggles URL and non-text conversion to Markdown.
- `--verbose` or `--debug` enables verbose backend logging.

## Recursion and Budget Limits

### Recursive RLM Calls (`--max-depth`)

RLM can recursively call itself to handle complex tasks. When `--max-depth` > 1, the LLM's `llm_query()` function creates child RLM instances with `max_depth - 1`.

```bash
# Enable 2 levels of recursive calls
rlm ask . -q "Research this codebase thoroughly" --max-depth 2
```

### Budget Control (`--max-budget`)

Limit spending per completion with `--max-budget`. When the budget is exceeded, a `BudgetExceededError` is raised with details of spent vs budget.

```bash
# Cap spending at $1.00
rlm ask . -q "Analyze this complex codebase" --max-budget 1.00
```

**Requirements:**
- Cost tracking requires a backend that returns cost data (e.g., OpenRouter)
- Budget is propagated to child RLMs (remaining budget)
- Works with `--max-depth` for recursive cost control

### Stop Conditions

The RLM execution can stop for any of these reasons:
1. **Final answer found** - LLM calls `FINAL_VAR()` with result
2. **Max iterations reached** - Exceeds `--max-iterations` (graceful, forces final answer)
3. **Max budget exceeded** - Spending exceeds `--max-budget` (exit code 20, error with details)
4. **Max depth reached** - Child RLM at depth 0 cannot recurse further

**Note:** Max iterations is a soft limit. When exceeded, RLM prompts the LLM to provide a final answer. Modern LLMs typically complete in 1-2 iterations.

## Search Tools

Three search tools are available for the LLM to explore content:

| Tool | Cost | Privacy | Best For |
|------|------|---------|----------|
| `rg.*` | Free | Local | Exact patterns, function names, imports |
| `tv.*` | Free | Local | Topics, concepts, finding related files |
| `pi.*` | **$$ LLM calls** | **Sends to API** | Hierarchical document navigation (PDFs) |

### Local Search (rg.* and tv.*)

Full-text search via Tantivy and ripgrep for the LLM to explore codebases efficiently.

### Install search support

```bash
pip install 'rlm-cli[search]'
```

This installs both Tantivy (ranked document search) and python-ripgrep (fast pattern matching).

### LLM Search Tools

When you run `rlm ask` on a directory, the LLM automatically gets access to two search tools in its REPL:

**`rg.search()` - Fast pattern matching (ripgrep)**
```python
# Find exact patterns or regex matches
hits = rg.search(pattern="class.*Error", paths=["src/"], regex=True)
for h in hits:
    print(f"{h['path']}:{h['line']}: {h['text']}")
```

**`tv.search()` - Ranked document search (Tantivy)**
```python
# Find relevant files by topic (BM25 ranking)
results = tv.search(query="error handling", limit=10)
for r in results:
    print(f"{r['path']} (score: {r['score']:.2f})")
```

**When to use which:**
- `rg.search()` for: exact strings, function names, class definitions, imports
- `tv.search()` for: concepts, topics, finding related files

The tools are pre-loaded - the LLM can use them directly without importing.

### CLI Search Commands

Index a directory:
```bash
rlm index ./src
```

Search indexed documents:
```bash
rlm search "error handling" --path ./src
```

Options:
- `--no-index` - Skip auto-indexing directories
- `--force` - Force full reindex (with `rlm index`)

### PageIndex (pi.* - Opt-in)

Hierarchical document navigation for PDFs and structured documents.

**⚠️ WARNING: PageIndex costs money and sends data to external APIs.**

Unlike `rg.*` and `tv.*` which are free and local, PageIndex:
- Sends document content to LLM APIs during indexing
- Makes LLM calls during tree navigation
- Requires explicit opt-in via `pi.configure(client)`

**When to use PageIndex:**
- Working with PDFs, reports, manuals, regulatory filings
- Documents with natural hierarchical structure (chapters, sections)
- When "find the section about X" is more useful than keyword search

**Usage in REPL:**
```python
import sys
sys.path.insert(0, "/path/to/rlm-cli/rlm")        # rlm submodule
sys.path.insert(0, "/path/to/rlm-cli/pageindex")  # pageindex submodule

from rlm.clients import get_client
from rlm_cli.tools_pageindex import pi

# 1. Configure with your rlm backend (REQUIRED before any operation)
client = get_client(backend="openrouter", backend_kwargs={"model_name": "google/gemini-2.0-flash-001"})
pi.configure(client)

# 2. Index a PDF (⚠️ COSTS MONEY - no caching, re-indexes each call)
tree = pi.index(path="annual_report.pdf")
# Returns: PITree(doc_name, nodes, doc_description, raw)

# 3. View table of contents (FREE - uses in-memory tree)
print(pi.toc(tree))

# 4. Get specific section by node_id (FREE)
# Node IDs are sequential: "0000", "0001", "0002", etc.
section = pi.get_section(tree, "0003")
if section:
    print(f"{section.title}: pages {section.start_index}-{section.end_index}")
# Returns: PINode(title, node_id, start_index, end_index, summary, children) or None
```

**pi.* API:**
| Method | Cost | Returns | Description |
|--------|------|---------|-------------|
| `pi.configure(client)` | Free | None | Set rlm backend (required first) |
| `pi.index(path=...)` | **$$$** | PITree | Build tree index from PDF |
| `pi.toc(tree)` | Free | str | Display table of contents |
| `pi.get_section(tree, id)` | Free | PINode/None | Get section by node_id |
| `pi.status()` | Free | dict | Check availability and config |

**Note:** PageIndex extracts document structure, not content. Use `start_index`/`end_index` to locate sections in the original PDF.

## Directory loading

Defaults for `rlm ask`:
- respects `.gitignore`
- skips common dirs like `.git`, `node_modules`, `.venv`
- limits file and total bytes

Adjust with:
- `--extensions` (repeat or comma-separated)
- `--include` / `--exclude`
- `--max-file-bytes` / `--max-total-bytes`
- `--hidden`, `--follow-symlinks`

## Config

Config files (YAML): `./rlm.yaml`, `./.rlm.yaml`, `~/.config/rlm/config.yaml`.
Precedence: CLI flags > env vars > config > defaults.

## Exit codes

- `0` success
- `2` CLI usage error
- `10` input error
- `11` config error
- `20` backend error
- `30` runtime error
- `40` index error (search)

## Security

Install the pre-commit hook to run gitleaks on staged changes:

```bash
pre-commit install
```
