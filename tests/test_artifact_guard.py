from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import scripts.check_private_artifacts as artifact_guard
from pokemon_red_ai.safety import private_artifact_path_reason, sensitive_text_reasons


def test_sensitive_text_reasons_detects_realistic_private_values() -> None:
    github_token = "gh" + "o_" + ("a" * 24)
    private_path = "/" + "Users/" + "private-owner/project"
    text = f"home={private_path}\ntoken={github_token}"

    assert sensitive_text_reasons(text) == ["private home-directory path", "GitHub token"]


def test_sensitive_text_reasons_allows_documentation_placeholders() -> None:
    text = "Use /Users/example/project or C:\\Users\\username\\project in a test."

    assert sensitive_text_reasons(text) == []


def test_private_artifact_path_reason_catches_expedition_payloads() -> None:
    assert (
        private_artifact_path_reason(
            ("frontier", "snapshots", "abc.json.gz"),
            "abc.json.gz",
        )
        == "compressed expedition emulator snapshot"
    )
    assert (
        private_artifact_path_reason(
            ("frontier", "segments", "abc.json"),
            "abc.json",
        )
        == "private expedition action segment"
    )
    assert private_artifact_path_reason(("docs", "example.json"), "example.json") is None


def test_publication_guard_forbids_apprentice_arrays_and_models() -> None:
    assert {".npy", ".npz", ".pt", ".pth", ".ckpt"}.issubset(
        artifact_guard.FORBIDDEN_SUFFIXES
    )


def test_tracked_file_below_ignored_runs_directory_is_still_scanned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forced = tmp_path / "runs" / "forced-private.sav"
    forced.parent.mkdir()
    forced.write_bytes(b"private")
    completed = subprocess.CompletedProcess(
        args=["git", "ls-files", "-z"],
        returncode=0,
        stdout=b"runs/forced-private.sav\0",
        stderr=b"",
    )
    monkeypatch.setattr(artifact_guard, "ROOT", tmp_path)
    monkeypatch.setattr(artifact_guard.subprocess, "run", lambda *args, **kwargs: completed)

    assert forced in artifact_guard.project_files()
