"""Checkpoint and restore for self-skill and student-practice state."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_red_ai.ppo.artifacts import (
    _atomic_json,
    _resolve_checkpoint_artifact,
    _sha256_file,
    _validate_hashed_run_artifact,
)
from pokemon_red_ai.ppo.telemetry import _v9_practice_terminal_reason_counts
from pokemon_red_ai.self_taught import (
    SelfTaughtSkillLibrary,
)
from pokemon_red_ai.student_practice import (
    StudentPracticeLedger,
)


def _checkpoint_self_skill_state(run_directory: Path) -> dict[str, str]:
    """Freeze the mutable skill ledger beside the model checkpoint."""

    live = run_directory / "self-skills.json"
    snapshot = run_directory / "self-skills.checkpoint.json"
    previous = run_directory / "self-skills.checkpoint.previous.json"
    value = json.loads(live.read_text(encoding="utf-8"))
    library = SelfTaughtSkillLibrary.from_dict(value)

    # Only an artifact ledger whose hash is already bound by checkpoint.json can
    # suppress another full-file validation.  In particular, an interrupted
    # checkpoint may have published a newer skill snapshot, but it is untrusted
    # until checkpoint.json commits its hash.  Keeping track of the matching path
    # also lets a second interrupted rotation preserve the last committed copy.
    committed_path: Path | None = None
    committed_library: SelfTaughtSkillLibrary | None = None
    checkpoint_path = run_directory / "checkpoint.json"
    if checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        expected = str(checkpoint.get("self_skills_file_sha256", ""))
        if len(expected) == 64:
            for candidate in (snapshot, previous):
                if candidate.is_file() and _sha256_file(candidate) == expected:
                    committed_path = candidate
                    committed_library = SelfTaughtSkillLibrary.from_dict(
                        json.loads(candidate.read_text(encoding="utf-8"))
                    )
                    break

    def skill_seal(skill: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            str(skill["target_frame_file"]),
            str(skill["target_frame_sha256"]),
            str(skill["dataset_file"]),
            str(skill["dataset_sha256"]),
            str(skill.get("distillation_audit_file")),
            str(skill.get("distillation_audit_sha256")),
            str(skill.get("skill_graph_audit_file")),
            str(skill.get("skill_graph_audit_sha256")),
            str(skill.get("graph_edge_id")),
            int(skill.get("replay_shard_example_cap", 0)),
            int(skill.get("replay_shard_burn_in", 0)),
            tuple(
                (
                    str(shard["protocol"]),
                    str(shard["file"]),
                    str(shard["sha256"]),
                    str(shard["source_dataset_sha256"]),
                    int(shard["shard_index"]),
                    int(shard["shard_count"]),
                    int(shard["source_start"]),
                    int(shard["source_context_start"]),
                    int(shard["source_train_start"]),
                    int(shard["source_stop"]),
                    int(shard["source_action_count"]),
                    int(shard["context_example_count"]),
                    int(shard["train_example_count"]),
                    int(shard["example_count"]),
                    int(shard["stored_bytes"]),
                )
                for shard in skill.get("replay_shards", [])
            ),
        )

    committed_skills = (
        {str(skill["skill_id"]): skill_seal(skill) for skill in committed_library.skills}
        if committed_library is not None
        else {}
    )
    for skill in library.skills:
        if committed_skills.get(str(skill["skill_id"])) == skill_seal(skill):
            continue
        for file_key, hash_key in (
            ("target_frame_file", "target_frame_sha256"),
            ("dataset_file", "dataset_sha256"),
            ("distillation_audit_file", "distillation_audit_sha256"),
            ("skill_graph_audit_file", "skill_graph_audit_sha256"),
        ):
            if skill.get(file_key) is None:
                continue
            _validate_hashed_run_artifact(
                run_directory,
                skill[file_key],
                skill.get(hash_key),
                label="Self-taught skill artifact before checkpoint",
            )
        for shard in skill.get("replay_shards", []):
            shard_path = _validate_hashed_run_artifact(
                run_directory,
                shard["file"],
                shard["sha256"],
                label="V8 bounded replay shard before checkpoint",
            )
            if shard_path.stat().st_size != int(shard["stored_bytes"]):
                raise ValueError("V8 bounded replay shard size changed before checkpoint")

    committed_compositions = (
        {
            str(composition["fingerprint"]): (
                str(composition["dataset_file"]),
                str(composition["dataset_sha256"]),
                str(composition["audit_file"]),
                str(composition["audit_sha256"]),
            )
            for composition in committed_library.composition_replays
        }
        if committed_library is not None
        else {}
    )
    for composition in library.composition_replays:
        seal = (
            str(composition["dataset_file"]),
            str(composition["dataset_sha256"]),
            str(composition["audit_file"]),
            str(composition["audit_sha256"]),
        )
        if (
            not bool(composition.get("active", False))
            and committed_compositions.get(str(composition["fingerprint"])) == seal
        ):
            continue
        for file_key, hash_key in (
            ("dataset_file", "dataset_sha256"),
            ("audit_file", "audit_sha256"),
        ):
            _validate_hashed_run_artifact(
                run_directory,
                composition[file_key],
                composition.get(hash_key),
                label="V8 composition replay artifact before checkpoint",
            )
    if committed_path == snapshot or (not checkpoint_path.is_file() and snapshot.is_file()):
        os.replace(snapshot, previous)
    _atomic_json(snapshot, value)
    return {
        "self_skills_checkpoint_file": snapshot.name,
        "self_skills_file_sha256": _sha256_file(snapshot),
    }


def _restore_self_skill_state(
    run_directory: Path,
    checkpoint: Mapping[str, Any],
) -> SelfTaughtSkillLibrary:
    """Roll the live ledger back to the exact state paired with the saved model."""

    filename = checkpoint.get("self_skills_checkpoint_file")
    if filename != "self-skills.checkpoint.json":
        raise ValueError("PPO checkpoint has no valid self-taught skill snapshot")
    try:
        snapshot = _resolve_checkpoint_artifact(
            run_directory,
            latest_name=filename,
            previous_name="self-skills.checkpoint.previous.json",
            expected_sha256=checkpoint.get("self_skills_file_sha256"),
        )
    except ValueError as error:
        raise ValueError("PPO self-taught skill snapshot does not match its checkpoint") from error
    value = json.loads(snapshot.read_text(encoding="utf-8"))
    library = SelfTaughtSkillLibrary.from_dict(value)
    _atomic_json(run_directory / "self-skills.json", value)
    return library


def _validate_student_practice_state(
    run_directory: Path,
    value: Mapping[str, Any],
) -> tuple[StudentPracticeLedger, ...]:
    if value.get("schema_version") != 1 or value.get("protocol") != (
        "v9-student-closed-loop-practice-state-v1"
    ):
        raise ValueError("V9 Student practice state has the wrong protocol")
    raw_ledgers = value.get("ledgers")
    if not isinstance(raw_ledgers, list):
        raise ValueError("V9 Student practice state has no ledgers")
    ledgers = tuple(StudentPracticeLedger.from_dict(item) for item in raw_ledgers)
    identifiers = [ledger.skill_id for ledger in ledgers]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("V9 Student practice state repeats a skill ledger")
    terminal_reasons = _v9_practice_terminal_reason_counts(value.get("terminal_reasons"))
    if "terminal_reasons" in value and (
        sum(terminal_reasons.values()) != sum(ledger.attempts for ledger in ledgers)
        or terminal_reasons["exact_target"] != sum(ledger.successes for ledger in ledgers)
    ):
        raise ValueError("V9 Student practice terminal reasons disagree with its ledgers")
    for ledger in ledgers:
        for rung in ledger.rungs:
            for rollout in rung.successful_rollouts:
                _validate_hashed_run_artifact(
                    run_directory,
                    rollout.dataset_file,
                    rollout.dataset_sha256,
                    label="V9 successful Student rollout",
                )
                if not rollout.replay_shards:
                    raise ValueError("V9 successful Student rollout has no bounded replay shards")
                if len(rollout.replay_shards) != int(rollout.replay_shards[0]["shard_count"]):
                    raise ValueError("V9 successful Student rollout shard set is incomplete")
                for expected_index, shard in enumerate(rollout.replay_shards):
                    path = _validate_hashed_run_artifact(
                        run_directory,
                        shard["file"],
                        shard["sha256"],
                        label="V9 successful Student replay shard",
                    )
                    if (
                        path.stat().st_size != int(shard["stored_bytes"])
                        or int(shard["shard_index"]) != expected_index
                        or int(shard["source_action_count"]) != rollout.action_count
                        or str(shard["source_dataset_sha256"]) != rollout.dataset_sha256
                    ):
                        raise ValueError("V9 successful Student replay shard is inconsistent")
    return ledgers


def _checkpoint_student_practice_state(run_directory: Path) -> dict[str, str]:
    """Bind mutable V9 practice scheduling to the same Student generation."""

    live = run_directory / "student-practice.json"
    snapshot = run_directory / "student-practice.checkpoint.json"
    previous = run_directory / "student-practice.checkpoint.previous.json"
    value = json.loads(live.read_text(encoding="utf-8"))
    _validate_student_practice_state(run_directory, value)
    committed_path: Path | None = None
    checkpoint_path = run_directory / "checkpoint.json"
    if checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        expected = str(checkpoint.get("student_practice_file_sha256", ""))
        if len(expected) == 64:
            committed_path = next(
                (
                    candidate
                    for candidate in (snapshot, previous)
                    if candidate.is_file() and _sha256_file(candidate) == expected
                ),
                None,
            )
    if committed_path == snapshot or (not checkpoint_path.is_file() and snapshot.is_file()):
        os.replace(snapshot, previous)
    _atomic_json(snapshot, value)
    return {
        "student_practice_file": snapshot.name,
        "student_practice_file_sha256": _sha256_file(snapshot),
    }


def _restore_student_practice_state(
    run_directory: Path,
    checkpoint: Mapping[str, Any],
) -> tuple[StudentPracticeLedger, ...]:
    filename = checkpoint.get("student_practice_file")
    if filename != "student-practice.checkpoint.json":
        raise ValueError("V9 checkpoint has no Student practice snapshot")
    try:
        snapshot = _resolve_checkpoint_artifact(
            run_directory,
            latest_name=filename,
            previous_name="student-practice.checkpoint.previous.json",
            expected_sha256=checkpoint.get("student_practice_file_sha256"),
        )
    except ValueError as error:
        raise ValueError("V9 Student practice snapshot does not match its checkpoint") from error
    value = json.loads(snapshot.read_text(encoding="utf-8"))
    ledgers = _validate_student_practice_state(run_directory, value)
    _atomic_json(run_directory / "student-practice.json", value)
    return ledgers
