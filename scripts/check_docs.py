from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".pytest_cache", ".ruff_cache", ".venv", "runs"}
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
PLACEHOLDERS = ("YOUR_USERNAME", "REPLACE_ME")


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not EXCLUDED_PARTS.intersection(path.relative_to(root).parts)
    )


def local_link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    target = target.split("#", 1)[0]
    return unquote(target) if target else None


def check_document(path: Path, root: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(root)
    problems = [
        f"{relative}: contains placeholder {value}" for value in PLACEHOLDERS if value in text
    ]

    for match in MARKDOWN_LINK.finditer(text):
        raw_target = match.group(1)
        target = local_link_target(raw_target)
        if target is None:
            continue
        destination = (path.parent / target).resolve()
        try:
            destination.relative_to(root.resolve())
        except ValueError:
            problems.append(f"{relative}: local link escapes the repository: {raw_target}")
            continue
        if not destination.exists():
            problems.append(f"{relative}: missing local link target: {raw_target}")
    return problems


def main() -> int:
    problems: list[str] = []
    for path in markdown_files(PROJECT_ROOT):
        problems.extend(check_document(path, PROJECT_ROOT))

    if problems:
        print("Documentation check failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print("Documentation links and placeholders check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
