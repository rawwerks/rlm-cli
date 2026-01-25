#!/bin/bash
set -e

# rlm-cli installer
# Usage: curl -sSL https://raw.githubusercontent.com/rawwerks/rlm-cli/master/install.sh | bash

REPO="https://github.com/rawwerks/rlm-cli.git"
INSTALL_DIR="${RLM_INSTALL_DIR:-$HOME/.local/share/rlm-cli}"
BIN_DIR="${RLM_BIN_DIR:-$HOME/.local/bin}"

echo "Installing rlm-cli..."

# Check for required tools
command -v git >/dev/null 2>&1 || { echo "Error: git is required"; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "Error: uv is required (https://docs.astral.sh/uv/)"; exit 1; }

# Clean up existing installation
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing existing installation..."
    rm -rf "$INSTALL_DIR"
fi

# Clone with submodules
echo "Cloning repository..."
git clone --recurse-submodules --depth 1 "$REPO" "$INSTALL_DIR"

# Create venv and install with uv
echo "Installing with uv..."
cd "$INSTALL_DIR"
uv venv
uv pip install -e .

# Create bin directory and symlink
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/.venv/bin/rlm" "$BIN_DIR/rlm"

echo ""
echo "rlm-cli installed successfully!"
echo ""
echo "Binary: $BIN_DIR/rlm"
echo ""

# Check if bin dir is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "Add to your PATH:"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    echo ""
fi

echo "Get started:"
echo "  rlm --help"
echo "  rlm ask . -q 'Summarize this repo' --json"
