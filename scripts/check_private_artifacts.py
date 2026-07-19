#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRECTORIES = {".git", ".venv", ".pytest_cache", ".ruff_cache", "runs"}
FORBIDDEN_SUFFIXES = {".gb", ".gbc", ".gba", ".ram", ".rtc", ".sav", ".state"}
KNOWN_ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def project_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in IGNORED_DIRECTORIES for part in path.parts)
    ]


def main() -> int:
    problems: list[str] = []
    for path in project_files():
        relative = path.relative_to(ROOT)
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"forbidden private artifact extension: {relative}")
            continue
        if path.stat().st_size == 1_048_576:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest == KNOWN_ROM_SHA256:
                problems.append(f"Pokemon Red ROM content detected: {relative}")

    if problems:
        print("Private-artifact check failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print("Private-artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
