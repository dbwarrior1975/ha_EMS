#!/usr/bin/env bash
set -euo pipefail
ROOT="${EMS_PROJECT_ROOT:-$(pwd)}"
cd "$ROOT"
pytest -q tests
