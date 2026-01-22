---
name: rlm
description: CLI for querying LLMs with file/directory/URL context. Use when users want to ask questions about code, analyze files, review diffs, or process documents with AI. Triggers on "rlm ask", "rlm complete", "rlm search", "rlm index", analyzing codebases, reviewing changes, or any task involving LLM queries with file context.
---

# RLM CLI

CLI for querying LLMs with context from files, directories, URLs, or stdin. The LLM can recursively call itself and use search tools to explore large inputs.

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

- **rg.search(pattern, paths, globs)** - ripgrep for exact patterns, function names, imports
- **tv.search(query, limit)** - Tantivy BM25 for concepts, topics, related files

The LLM uses these automatically to explore before answering.
