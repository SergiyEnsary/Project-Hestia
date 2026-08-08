#!/usr/bin/env bash
# Fail if backend or frontend line coverage is below 80%.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MIN_COVERAGE=80

echo "==> Backend coverage (min ${MIN_COVERAGE}%)"
if [[ -x "${ROOT}/.venv/bin/pytest" ]]; then
  PYTEST="${ROOT}/.venv/bin/pytest"
elif command -v pytest >/dev/null 2>&1; then
  PYTEST="pytest"
else
  echo "error: pytest not found (install with: pip install -e '.[dev]')" >&2
  exit 1
fi

"${PYTEST}" tests/ -q \
  --cov=hestia \
  --cov-fail-under="${MIN_COVERAGE}" \
  --cov-report=term-missing

echo "==> Frontend coverage (min ${MIN_COVERAGE}%)"
(
  cd hestia/interfaces/pythia
  npm run test:coverage
)

echo "Coverage check passed (>= ${MIN_COVERAGE}%)."
