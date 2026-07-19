from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

GIT_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    git_commit: str | None
    worktree_dirty: bool | None

    def public_dict(self) -> dict[str, str | bool]:
        return {
            "git_commit": self.git_commit or "unknown",
            "worktree_dirty": self.worktree_dirty if self.worktree_dirty is not None else "unknown",
        }


def detect_source_provenance(project_root: Path | None = None) -> SourceProvenance:
    """Read public Git identity without recording a checkout path or command error."""
    root = project_root or Path(__file__).resolve().parents[2]
    commit = _git_output(root, "rev-parse", "HEAD")
    if commit is None or GIT_COMMIT.fullmatch(commit) is None:
        return SourceProvenance(None, None)

    status = _git_output(root, "status", "--porcelain", "--untracked-files=no")
    return SourceProvenance(commit, None if status is None else bool(status))


def _git_output(root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()
