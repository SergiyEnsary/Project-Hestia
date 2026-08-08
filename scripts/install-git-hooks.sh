#!/usr/bin/env bash
# Install repo git hooks into .git/hooks (no git config changes).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_SRC="${ROOT}/.githooks"
HOOKS_DST="${ROOT}/.git/hooks"

if [[ ! -d "${HOOKS_DST}" ]]; then
  echo "error: ${HOOKS_DST} not found; is this a git checkout?" >&2
  exit 1
fi

for hook in "${HOOKS_SRC}"/*; do
  name="$(basename "${hook}")"
  cp "${hook}" "${HOOKS_DST}/${name}"
  chmod +x "${HOOKS_DST}/${name}"
  echo "Installed ${name} -> .git/hooks/${name}"
done
