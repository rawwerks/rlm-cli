#!/bin/bash
set -e

# rlm-cli uninstaller

INSTALL_DIR="${RLM_INSTALL_DIR:-$HOME/.local/share/rlm-cli}"
BIN_DIR="${RLM_BIN_DIR:-$HOME/.local/bin}"

echo "Uninstalling rlm-cli..."

# Remove symlink
if [ -L "$BIN_DIR/rlm" ]; then
    rm "$BIN_DIR/rlm"
    echo "Removed $BIN_DIR/rlm"
fi

# Remove installation directory
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "Removed $INSTALL_DIR"
fi

echo "rlm-cli uninstalled."
