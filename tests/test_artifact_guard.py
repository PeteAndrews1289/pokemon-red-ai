from __future__ import annotations

from pokemon_red_ai.safety import sensitive_text_reasons


def test_sensitive_text_reasons_detects_realistic_private_values() -> None:
    github_token = "gh" + "o_" + ("a" * 24)
    private_path = "/" + "Users/" + "private-owner/project"
    text = f"home={private_path}\ntoken={github_token}"

    assert sensitive_text_reasons(text) == ["private home-directory path", "GitHub token"]


def test_sensitive_text_reasons_allows_documentation_placeholders() -> None:
    text = "Use /Users/example/project or C:\\Users\\username\\project in a test."

    assert sensitive_text_reasons(text) == []
