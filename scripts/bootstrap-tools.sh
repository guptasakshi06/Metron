#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/.tools"
NODE_VERSION="24.22.2"
UV_VERSION="0.13.6"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) NODE_ARCH="x64"; UV_ARCH="x86_64-unknown-linux-gnu" ;;
  aarch64|arm64) NODE_ARCH="arm64"; UV_ARCH="aarch64-unknown-linux-gnu" ;;
  *) echo "Unsupported Linux architecture for local tools: $ARCH" >&2; exit 2 ;;
esac

if [[ ! -x "$TOOLS_DIR/node24/bin/node" ]]; then
  mkdir -p "$TOOLS_DIR/downloads" "$TOOLS_DIR/node24"
  NODE_ARCHIVE="node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"
  curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_ARCHIVE}" -o "$TOOLS_DIR/downloads/$NODE_ARCHIVE"
  curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" -o "$TOOLS_DIR/downloads/node-SHASUMS256.txt"
  (cd "$TOOLS_DIR/downloads" && grep " ${NODE_ARCHIVE}$" node-SHASUMS256.txt | sha256sum -c -)
  tar -xJf "$TOOLS_DIR/downloads/$NODE_ARCHIVE" -C "$TOOLS_DIR/node24" --strip-components=1
fi

if [[ ! -x "$TOOLS_DIR/uv-bin/uv" ]]; then
  mkdir -p "$TOOLS_DIR/downloads" "$TOOLS_DIR/uv-bin"
  curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" -o "$TOOLS_DIR/downloads/uv-install.sh"
  UV_INSTALL_DIR="$TOOLS_DIR/uv-bin" UV_NO_MODIFY_PATH=1 sh "$TOOLS_DIR/downloads/uv-install.sh"
fi

"$TOOLS_DIR/node24/bin/node" --version
PATH="$TOOLS_DIR/node24/bin:$PATH" npm --version
"$TOOLS_DIR/uv-bin/uv" --version
