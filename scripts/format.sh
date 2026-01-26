#!/usr/bin/env bash
# ==============================================================================
# Code Formatter Script
# ==============================================================================
# This script uses the 'black' Python formatter to ensure consistent code style
# across the entire project. It targets all Python files in the current folder
# and subdirectories.
#
# Usage:
#   bash scripts/format.sh
# ==============================================================================
set -euo pipefail

python3 -m black .
