#!/usr/bin/env bash
# DEPRECATED: Lambda layers are no longer used.
# This script is kept for backward compatibility but does nothing.
set -euo pipefail

echo "Note: Lambda layers are deprecated. Dependencies are now bundled with each Lambda."
echo "Run 'make floci-build' to build Lambda packages with bundled dependencies."
