# rlm-cli

CLI wrapper for `rlm` with directory-as-context, JSON-first output, and self-documenting commands.

Upstream RLM: https://github.com/alexzhang13/rlm

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

Full-text search via Tantivy for filtering large directories before LLM calls.

### Install search support

```bash
pip install 'rlm-cli[search]'
```

### Index a directory

```bash
rlm index ./src
```

### Search indexed documents

```bash
rlm search "error handling" --path ./src
```

### Filter context via search

```bash
rlm ask ./src -q "Explain error handling" --search "exception"
```

Options:
- `--search "query"` - Filter context via BM25 search
- `--search-limit N` - Max documents from search (default: 50)
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
