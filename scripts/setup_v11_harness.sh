#!/usr/bin/env bash

set -euo pipefail

readonly UPSTREAM_URL="https://github.com/sethkarten/continual-harness.git"
readonly UPSTREAM_COMMIT="bbab97ad73e460b7cd7c08527d10ced30cc03fbe"

usage() {
  cat <<'EOF'
Usage: scripts/setup_v11_harness.sh TARGET_DIRECTORY

Create a fresh, pinned continual-harness checkout with the Pokemon Red V11
overlay and its lean Python 3.11 environment.

The target must be an explicit path that does not exist or is completely empty.
The script never copies a ROM, credentials, save state, or other private data,
and it does not launch gameplay.

Environment overrides:
  UV_BIN       Existing uv executable to use (otherwise uv is found on PATH)
  V11_PYTHON   Python 3.11 interpreter or uv Python selector (default: 3.11)
  UV_CACHE_DIR Optional uv cache location, handled directly by uv
EOF
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

[[ "$#" -eq 1 ]] || {
  usage >&2
  exit 2
}

command -v git >/dev/null 2>&1 || fail "git is required."

if [[ -n "${UV_BIN:-}" ]]; then
  [[ -x "$UV_BIN" ]] || fail "UV_BIN is not an executable file: $UV_BIN"
else
  UV_BIN="$(command -v uv || true)"
  [[ -n "$UV_BIN" ]] || fail "uv is required on PATH, or set UV_BIN to an existing uv executable."
fi

readonly UV_BIN
readonly V11_PYTHON="${V11_PYTHON:-3.11}"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
PATCH_FILE="$REPOSITORY_ROOT/patches/continual-harness-v11.patch"
readonly SCRIPT_DIR REPOSITORY_ROOT PATCH_FILE

[[ -f "$PATCH_FILE" ]] || fail "V11 overlay patch is missing: $PATCH_FILE"

TARGET_INPUT="$1"
[[ -n "$TARGET_INPUT" ]] || fail "TARGET_DIRECTORY cannot be empty."

case "$TARGET_INPUT" in
  /*) TARGET="$TARGET_INPUT" ;;
  *) TARGET="$(pwd)/$TARGET_INPUT" ;;
esac

# Remove a harmless trailing slash for consistent safety checks.
while [[ "$TARGET" != "/" && "$TARGET" == */ ]]; do
  TARGET="${TARGET%/}"
done
readonly TARGET

[[ "$TARGET" != "/" ]] || fail "The filesystem root cannot be used as the target."
[[ ! -L "$TARGET" ]] || fail "Refusing a symbolic-link target: $TARGET"

TARGET_PARENT="$(dirname -- "$TARGET")"
[[ -d "$TARGET_PARENT" ]] || fail "The target parent directory does not exist: $TARGET_PARENT"
[[ -w "$TARGET_PARENT" ]] || fail "The target parent directory is not writable: $TARGET_PARENT"

if [[ -e "$TARGET" ]]; then
  [[ -d "$TARGET" ]] || fail "The target exists and is not a directory: $TARGET"
  if [[ -n "$(find "$TARGET" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    fail "Refusing a nonempty target. Use a new empty directory: $TARGET"
  fi
fi

printf 'Cloning continual-harness at pinned commit %s...\n' "$UPSTREAM_COMMIT"
git clone --no-checkout "$UPSTREAM_URL" "$TARGET"
git -C "$TARGET" checkout --detach "$UPSTREAM_COMMIT"

ACTUAL_COMMIT="$(git -C "$TARGET" rev-parse HEAD)"
[[ "$ACTUAL_COMMIT" == "$UPSTREAM_COMMIT" ]] || \
  fail "Pinned checkout verification failed: expected $UPSTREAM_COMMIT, got $ACTUAL_COMMIT"

if [[ -n "$(git -C "$TARGET" status --porcelain)" ]]; then
  fail "Fresh checkout is unexpectedly dirty; the V11 patch was not applied."
fi

printf 'Checking and applying the V11 overlay...\n'
git -C "$TARGET" apply --check "$PATCH_FILE"
git -C "$TARGET" apply "$PATCH_FILE"
git -C "$TARGET" diff --check

VENV="$TARGET/.venv-red-codex"
[[ ! -e "$VENV" ]] || fail "Refusing to replace an existing environment: $VENV"

printf 'Creating lean Python 3.11 environment with %s...\n' "$UV_BIN"
"$UV_BIN" venv --python "$V11_PYTHON" "$VENV"
"$UV_BIN" pip install \
  --python "$VENV/bin/python" \
  --requirement "$TARGET/requirements-red-codex.txt"

(
  cd "$TARGET"
  "$VENV/bin/python" - <<'PY'
import sys

if sys.version_info[:2] != (3, 11):
    raise SystemExit(f"V11 requires Python 3.11; created {sys.version.split()[0]}")

import run_cli  # noqa: F401
import server.app  # noqa: F401
import server.cli.pokemon_mcp_server  # noqa: F401
from pokemon_red_env.red_emulator import RedEmulator  # noqa: F401
PY
)

printf '\nV11 harness is ready at:\n  %s\n' "$TARGET"
printf 'Pinned upstream commit:\n  %s\n' "$UPSTREAM_COMMIT"
printf 'No ROM, credentials, save state, or gameplay process was created.\n'
