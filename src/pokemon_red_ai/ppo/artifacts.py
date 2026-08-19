"""Atomic writes, canonical hashing, and run-artifact integrity checks."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_red_ai.ppo.constants import PPO_PROTOCOL, torch


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _random_state_to_json(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_random_state_to_json(item) for item in value]
    return value


def _random_state_from_json(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_random_state_from_json(item) for item in value)
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_reproducible_v8_source(source: Mapping[str, Any]) -> None:
    """Refuse a V8 campaign whose executable source cannot be named exactly."""

    if source.get("git_commit") == "unknown" or source.get("worktree_dirty") is not False:
        raise ValueError("V8 requires a clean Git commit so checkpoints bind exact source")


def _validate_checkpoint_identity(
    checkpoint: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    rom: Mapping[str, Any],
    required: bool,
) -> None:
    if not required:
        return
    recorded_source = checkpoint.get("source")
    recorded_rom = checkpoint.get("rom")
    if recorded_source is None or recorded_rom is None:
        raise ValueError("V8 checkpoint has no bound source and ROM identity")
    if recorded_source != source:
        raise ValueError("PPO checkpoint source identity does not match this checkout")
    if recorded_rom != rom:
        raise ValueError("PPO checkpoint ROM identity does not match the verified ROM")


def _resolve_checkpoint_artifact(
    run_directory: Path,
    *,
    latest_name: str,
    previous_name: str,
    expected_sha256: object,
) -> Path:
    """Resolve and re-promote the generation named by the atomic JSON checkpoint."""

    for index, name in enumerate((latest_name, previous_name)):
        path = run_directory / name
        if path.is_file() and _sha256_file(path) == expected_sha256:
            if index == 0:
                return path
            latest = run_directory / latest_name
            temporary = latest.with_suffix(latest.suffix + ".recovered.tmp")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, temporary)
            os.replace(temporary, latest)
            if _sha256_file(latest) != expected_sha256:
                raise ValueError(f"Recovered {latest_name} failed its checkpoint hash")
            return latest
    raise ValueError(f"Neither {latest_name} nor its previous generation matches")


def _snapshot_v7_denominator(run_directory: Path) -> dict[str, Any]:
    """Lock one read-only V7 checkpoint for honest V8 dashboard comparison."""

    source = run_directory.expanduser().resolve()
    if not source.is_dir():
        raise ValueError("V7 denominator run directory does not exist")
    manifest_path = source / "manifest.json"
    checkpoint_path = source / "checkpoint.json"
    status_path = source / "status.json"
    if not manifest_path.is_file() or not checkpoint_path.is_file():
        raise ValueError("V7 denominator has no complete manifest and checkpoint")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol") != PPO_PROTOCOL or manifest.get("actor_mode") != "self_taught":
        raise ValueError("Denominator must be a Version-7 self-taught run")

    # The denominator may still be running. Its checkpoint and model generations
    # rotate atomically but separately, so retry the read-only pairing if one
    # rotation crosses this snapshot operation.
    for _attempt in range(3):
        checkpoint_bytes = checkpoint_path.read_bytes()
        checkpoint = json.loads(checkpoint_bytes)
        expected = checkpoint.get("model_file_sha256")
        checkpoint_config = checkpoint.get("config")
        if (
            checkpoint.get("protocol") != PPO_PROTOCOL
            or not isinstance(checkpoint_config, Mapping)
            or checkpoint_config.get("mode") != "self_taught"
            or not isinstance(expected, str)
            or len(expected) != 64
        ):
            raise ValueError("V7 denominator checkpoint identity is invalid")
        matching_model = next(
            (
                candidate
                for candidate in (source / "ppo-latest.zip", source / "ppo-previous.zip")
                if candidate.is_file() and _sha256_file(candidate) == expected
            ),
            None,
        )
        if matching_model is None:
            continue
        best = checkpoint.get("best_milestone")
        if not isinstance(best, Mapping):
            raise ValueError("V7 denominator checkpoint has no milestone evidence")
        status = (
            json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
        )
        return {
            "locked": True,
            "protocol": PPO_PROTOCOL,
            "run_id": source.name,
            "total_actions": int(checkpoint["total_actions"]),
            "best_index": int(best["index"]),
            "best_label": str(best["label"]),
            "checkpoint_sha256": expected,
            "checkpoint_json_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
            "source_state_at_lock": str(status.get("state", "unknown")),
            "source_updated_at": status.get("updated_at"),
            "locked_at": datetime.now(UTC).isoformat(),
            "source_path_recorded": False,
        }
    raise ValueError("V7 denominator model rotated before a checkpoint pair could be locked")


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_json(value) + b"\n")
    os.replace(temporary, path)


def _ensure_run_manifest_identity(
    path: Path,
    *,
    source: Mapping[str, Any],
    rom: Mapping[str, Any],
) -> dict[str, Any]:
    """Backfill identity for pre-V8 manifests without rewriting existing provenance."""

    value = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    if "source" not in value:
        value["source"] = dict(source)
        changed = True
    if "rom" not in value:
        value["rom"] = dict(rom)
        changed = True
    if changed:
        _atomic_json(path, value)
    return value


def _atomic_torch_checkpoint(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as output:
        torch.save(value, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _validate_hashed_run_artifact(
    run_directory: Path,
    relative_value: object,
    expected_sha256: object,
    *,
    label: str,
) -> Path:
    """Resolve one ledger artifact inside the run and verify its sealed identity."""

    relative = Path(str(relative_value))
    expected = str(expected_sha256)
    if relative.is_absolute() or ".." in relative.parts or not relative.name:
        raise ValueError(f"{label} path is invalid")
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ValueError(f"{label} hash is invalid")
    root = run_directory.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or _sha256_file(path) != expected:
        raise ValueError(f"{label} failed its hash")
    return path


def _atomic_gzip_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=3) as output:
        json.dump(value, output, sort_keys=True, separators=(",", ":"))
    os.replace(temporary, path)


def _read_gzip_json(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value
