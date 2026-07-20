#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from pokemon_red_ai.safety import private_artifact_path_reason, sensitive_text_reasons

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRECTORIES = {".git", ".venv", ".pytest_cache", ".ruff_cache", "runs"}
FORBIDDEN_SUFFIXES = {
    ".ckpt",
    ".gb",
    ".gba",
    ".gbc",
    ".npy",
    ".npz",
    ".pt",
    ".pth",
    ".ram",
    ".rtc",
    ".sav",
    ".state",
}
KNOWN_ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"
MAX_TEXT_SCAN_BYTES = 1_000_000


def project_files() -> list[Path]:
    discovered = {
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in IGNORED_DIRECTORIES for part in path.parts)
    }
    # Ignored run directories intentionally contain private local evidence, so walking every
    # untracked run would make the guard unusable. Git-tracked files are a different authority
    # boundary: include all of them, even below runs/, so `git add -f` cannot bypass CI.
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        tracked_paths: set[Path] = set()
    else:
        tracked_paths = (
            {
                ROOT / raw.decode("utf-8", errors="surrogateescape")
                for raw in tracked.stdout.split(b"\0")
                if raw
            }
            if tracked.returncode == 0
            else set()
        )
    return sorted(path for path in discovered | tracked_paths if path.is_file())


def readable_text(path: Path) -> str | None:
    if path.stat().st_size > MAX_TEXT_SCAN_BYTES:
        return None
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def main() -> int:
    problems: list[str] = []
    for path in project_files():
        relative = path.relative_to(ROOT)
        private_path_reason = private_artifact_path_reason(relative.parts, path.name)
        if private_path_reason is not None:
            problems.append(f"{private_path_reason}: {relative}")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"forbidden private artifact extension: {relative}")
            continue
        if path.stat().st_size == 1_048_576:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest == KNOWN_ROM_SHA256:
                problems.append(f"Pokemon Red ROM content detected: {relative}")
                continue

        text = readable_text(path)
        if text is not None:
            for reason in sensitive_text_reasons(text):
                problems.append(f"{reason} detected: {relative}")

    if problems:
        print("Private-artifact check failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print("Private-artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
