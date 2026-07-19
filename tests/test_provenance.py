from __future__ import annotations

import subprocess
from pathlib import Path

from pokemon_red_ai.provenance import SourceProvenance, detect_source_provenance


def test_source_provenance_reads_commit_and_dirty_state(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="a" * 40 + "\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=" M README.md\n", stderr=""),
        ]
    )

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(responses))  # type: ignore[attr-defined]

    provenance = detect_source_provenance(tmp_path)

    assert provenance == SourceProvenance("a" * 40, True)
    assert provenance.public_dict() == {"git_commit": "a" * 40, "worktree_dirty": True}


def test_source_provenance_hides_unavailable_git_details(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    unavailable = subprocess.CompletedProcess([], 1, stdout="", stderr="private failure")
    monkeypatch.setattr(  # type: ignore[attr-defined]
        subprocess,
        "run",
        lambda *args, **kwargs: unavailable,
    )

    provenance = detect_source_provenance(tmp_path)

    assert provenance.public_dict() == {"git_commit": "unknown", "worktree_dirty": "unknown"}
