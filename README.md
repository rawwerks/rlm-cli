# rlm-cli

CLI wrapper for `rlm` with directory-as-context, JSON-first output, and self-documenting commands.

Upstream RLM: https://github.com/alexzhang13/rlm

## Claude Code Plugin

This repo includes a Claude Code plugin with an `rlm` skill. The skill teaches Claude how to use the rlm CLI for code analysis, diff reviews, and codebase exploration.

### Install as local plugin

```bash
# Clone the repo
git clone https://github.com/rawwerks/rlm-cli.git

# Create local-plugins directory if needed
mkdir -p ~/.claude/local-plugins

# Remove existing rlm plugin if present, then symlink
rm -rf ~/.claude/local-plugins/rlm
ln -s "$(pwd)/rlm-cli" ~/.claude/local-plugins/rlm
```

Restart Claude Code to load the plugin.

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
- `--backend-arg/--env-arg/--rlm-arg KEY=VALUE` pass extra kwargs.
- `--backend-json/--env-json/--rlm-json @file.json` merge JSON kwargs.
- `--literal` treats inputs as literal text; `--path` forces filesystem paths.
- `--markitdown/--no-markitdown` toggles URL and non-text conversion to Markdown.
- `--verbose` or `--debug` enables verbose backend logging.

## Search (optional)

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
