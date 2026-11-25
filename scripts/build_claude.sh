#!/usr/bin/env bash
set -euo pipefail

# Build from an empty context so no repository file or local credential enters the image.
pin="2.1.325"  # Keep equal to CLAUDE_CODE_VERSION in claude/runner.py.
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
image_tag="${1:-nl2repobench-claude:$pin}"
build_context="$(mktemp -d)"
trap 'rm -rf -- "$build_context"' EXIT
docker build --tag "$image_tag" --build-arg "CLAUDE_CODE_VERSION=$pin" \
    --file "$repo_root/docker/claude.Dockerfile" "$build_context"
