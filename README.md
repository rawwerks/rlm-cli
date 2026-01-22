# rlm-cli

CLI wrapper for `rlm` with directory-as-context, JSON-first output, and self-documenting commands.

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

## Usage

### Ask about a repo

```bash
rlm ask . -q "Summarize this repo" --json
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

## Options

- `--json` outputs JSON only on stdout.
- `--output-format text|json` sets output format.
- `--backend`, `--model`, `--environment` control the RLM backend.
- `--backend-arg/--env-arg/--rlm-arg KEY=VALUE` pass extra kwargs.
- `--backend-json/--env-json/--rlm-json @file.json` merge JSON kwargs.
- `--literal` treats inputs as literal text; `--path` forces filesystem paths.
- `--verbose` or `--debug` enables verbose backend logging.

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
