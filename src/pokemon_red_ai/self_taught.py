from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SELF_TAUGHT_PROTOCOL = "self-generated-visual-skills-v1"

SELF_GENERATED_COMPOSITION_PROTOCOL = "agent-self-generated-composition-replay-v1"

SELF_GENERATED_REPLAY_SHARD_PROTOCOL = "bounded-self-generated-skill-replay-v1"

V8_REHEARSAL_MODES = frozenset({"self_evaluation", "self_mastery", "self_retention"})


def _entry_id(entry: Mapping[str, Any]) -> str:
    return str(entry["entry_id"])


def _entry_index(entry: Mapping[str, Any]) -> int:
    return int(entry["milestone_index"])


@dataclass(slots=True)
class SelfTaughtSkillLibrary:
    """Skills discovered and demonstrated only by the agent's own verified play."""

    root_entry_id: str
    window_size: int = 10
    threshold: float = 0.8
    skills: list[dict[str, Any]] = field(default_factory=list)
    total_rehearsal_attempts: int = 0
    total_rehearsal_successes: int = 0
    imitation_updates: int = 0
    imitation_examples: int = 0
    last_imitation_loss: float | None = None
    imitation_pending: bool = False
    v8_schedule_decisions: int = 0
    student_training_rounds: int = 0
    student_updates: int = 0
    student_examples: int = 0
    last_student_report: dict[str, Any] | None = None
    last_student_replay_rollout: int = -1
    exam_rng_state: list[Any] | None = None
    frozen_exam_rounds: int = 0
    frozen_exam_actions: int = 0
    last_frozen_exam_actions: int = 0
    composition_attempts: int = 0
    composition_successes: int = 0
    composition_window: list[bool] = field(default_factory=list)
    best_composition_index: int = 0
    hall_of_fame_completions: int = 0
    composition_replays: list[dict[str, Any]] = field(default_factory=list)
    composition_build_outcomes: dict[str, str] = field(default_factory=dict)
    composition_boundary_cursor: int = 0

    def __post_init__(self) -> None:
        if not self.root_entry_id:
            raise ValueError("Self-taught skills require a power-on entry")
        if self.window_size < 2 or not 0 < self.threshold <= 1:
            raise ValueError("Self-taught competence settings are invalid")
        identifiers = [str(skill["skill_id"]) for skill in self.skills]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Self-taught skill identifiers must be unique")
        composition_identifiers = [
            str(composition["composition_id"]) for composition in self.composition_replays
        ]
        if len(composition_identifiers) != len(set(composition_identifiers)):
            raise ValueError("Self-taught composition identifiers must be unique")
        if set(composition_identifiers).intersection(identifiers):
            raise ValueError("Composition and skill identifiers must be disjoint")
        if sum(bool(item.get("active", False)) for item in self.composition_replays) > 1:
            raise ValueError("Only one composition replay may be active")
        if self.composition_boundary_cursor < 0:
            raise ValueError("Composition boundary cursor cannot be negative")
        if any(
            outcome not in {"verified", "replay_failed"}
            for outcome in self.composition_build_outcomes.values()
        ):
            raise ValueError("Self-taught composition outcome is invalid")
        by_id = {str(skill["skill_id"]): skill for skill in self.skills}
        for skill in self.skills:
            for file_key, hash_key, optional in (
                ("target_frame_file", "target_frame_sha256", False),
                ("dataset_file", "dataset_sha256", False),
                ("distillation_audit_file", "distillation_audit_sha256", True),
            ):
                file_value = skill.get(file_key)
                hash_value = skill.get(hash_key)
                if optional and file_value is None and hash_value is None:
                    continue
                relative = Path(str(file_value or ""))
                digest = str(hash_value or "")
                if relative.is_absolute() or ".." in relative.parts or not relative.name:
                    raise ValueError("Self-taught skill artifact path is invalid")
                if len(digest) != 64 or any(
                    character not in "0123456789abcdef" for character in digest
                ):
                    raise ValueError("Self-taught skill artifact identity is invalid")
            shards = list(skill.get("replay_shards", []))
            replay_cursor = int(skill.get("replay_cursor", 0))
            if replay_cursor < 0:
                raise ValueError("Self-taught replay cursor cannot be negative")
            if not shards:
                continue
            cap = int(skill.get("replay_shard_example_cap", 0))
            burn_in = int(skill.get("replay_shard_burn_in", -1))
            if cap < 1 or burn_in < 0:
                raise ValueError("Self-taught replay shards require a positive example cap")
            expected_train_start = 0
            for index, shard in enumerate(shards):
                if shard.get("protocol") != SELF_GENERATED_REPLAY_SHARD_PROTOCOL:
                    raise ValueError("Unsupported self-generated replay shard")
                relative = Path(str(shard.get("file", "")))
                digest = str(shard.get("sha256", ""))
                source_digest = str(shard.get("source_dataset_sha256", ""))
                if relative.is_absolute() or ".." in relative.parts or not relative.name:
                    raise ValueError("Self-taught replay shard path is invalid")
                if not all(
                    len(value) == 64
                    and all(character in "0123456789abcdef" for character in value)
                    for value in (digest, source_digest)
                ):
                    raise ValueError("Self-taught replay shard identity is invalid")
                start = int(shard.get("source_start", -1))
                context_start = int(shard.get("source_context_start", -1))
                train_start = int(shard.get("source_train_start", -1))
                stop = int(shard.get("source_stop", -1))
                examples = int(shard.get("example_count", -1))
                context_examples = int(shard.get("context_example_count", -1))
                train_examples = int(shard.get("train_example_count", -1))
                if (
                    int(shard.get("shard_index", -1)) != index
                    or int(shard.get("shard_count", -1)) != len(shards)
                    or source_digest != str(skill["dataset_sha256"])
                    or train_start != expected_train_start
                    or context_start != start
                    or start != max(0, train_start - burn_in)
                    or stop <= start
                    or stop - start != examples
                    or train_start - start != context_examples
                    or stop - train_start != train_examples
                    or train_examples > cap
                    or examples > cap + burn_in
                    or int(shard.get("source_action_count", -1)) != int(skill["action_count"])
                    or int(shard.get("stored_bytes", 0)) < 1
                ):
                    raise ValueError("Self-taught replay shard coverage is invalid")
                expected_train_start = stop
            if expected_train_start != int(skill["action_count"]):
                raise ValueError("Self-taught replay shards do not cover the verified dataset")
        for composition in self.composition_replays:
            fingerprint = str(composition.get("fingerprint", ""))
            dataset_hash = str(composition.get("dataset_sha256", ""))
            audit_hash = str(composition.get("audit_sha256", ""))
            if not all(
                len(value) == 64 and all(character in "0123456789abcdef" for character in value)
                for value in (fingerprint, dataset_hash, audit_hash)
            ):
                raise ValueError("Self-taught composition artifact identity is invalid")
            if self.composition_build_outcomes.get(fingerprint) != "verified":
                raise ValueError("Self-taught composition is not paired with verified state")
            for file_key in ("dataset_file", "audit_file"):
                relative = Path(str(composition.get(file_key, "")))
                if relative.is_absolute() or ".." in relative.parts or not relative.name:
                    raise ValueError("Self-taught composition artifact path is invalid")
            skill_ids = [str(skill_id) for skill_id in composition.get("skill_ids", [])]
            try:
                chain = [by_id[skill_id] for skill_id in skill_ids]
            except KeyError as error:
                raise ValueError("Self-taught composition references an unknown skill") from error
            if str(chain[0]["source_entry_id"]) != self.root_entry_id or any(
                str(left["target_entry_id"]) != str(right["source_entry_id"])
                for left, right in zip(chain, chain[1:], strict=False)
            ):
                raise ValueError("Self-taught composition ledger contains a disconnected chain")

    @classmethod
    def initialize(
        cls,
        entries: Sequence[Mapping[str, Any]],
        *,
        window_size: int,
        threshold: float,
    ) -> SelfTaughtSkillLibrary:
        roots = [entry for entry in entries if _entry_index(entry) == 0]
        if len(roots) != 1:
            raise ValueError("Self-taught curriculum requires one power-on root")
        return cls(
            root_entry_id=_entry_id(roots[0]),
            window_size=window_size,
            threshold=threshold,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SelfTaughtSkillLibrary:
        if value.get("protocol") != SELF_TAUGHT_PROTOCOL:
            raise ValueError("Unsupported self-taught skill state")
        if int(value.get("schema_version", 1)) not in {1, 2}:
            raise ValueError("Unsupported self-taught skill schema")
        skills: list[dict[str, Any]] = []
        for raw in value.get("skills", []):
            item = dict(raw)
            item["source_index"] = int(item["source_index"])
            item["target_index"] = int(item["target_index"])
            item["action_count"] = int(item["action_count"])
            item["attempts"] = int(item.get("attempts", 0))
            item["successes"] = int(item.get("successes", 0))
            item["window"] = [bool(result) for result in item.get("window", [])]
            item["competent"] = bool(item.get("competent", False))
            item["last_retention_decision"] = int(item.get("last_retention_decision", 0))
            item["competence_losses"] = int(item.get("competence_losses", 0))
            item["original_action_count"] = int(
                item.get("original_action_count", item["action_count"])
            )
            item["compression_ratio"] = float(
                item.get(
                    "compression_ratio",
                    item["action_count"] / max(1, item["original_action_count"]),
                )
            )
            item["target_clip_channels"] = int(item.get("target_clip_channels", 1))
            item["distillation_oracle_calls"] = int(
                item.get("distillation_oracle_calls", 0)
            )
            item["distillation_oracle_actions_replayed"] = int(
                item.get("distillation_oracle_actions_replayed", 0)
            )
            item["distillation_edits_accepted"] = int(
                item.get("distillation_edits_accepted", 0)
            )
            item["distillation_edits_rejected"] = int(
                item.get("distillation_edits_rejected", 0)
            )
            item["replay_cursor"] = int(item.get("replay_cursor", 0))
            item["replay_shard_example_cap"] = int(
                item.get("replay_shard_example_cap", 0)
            )
            item["replay_shard_burn_in"] = int(item.get("replay_shard_burn_in", 0))
            normalized_shards: list[dict[str, Any]] = []
            for raw_shard in item.get("replay_shards", []):
                shard = dict(raw_shard)
                for key in (
                    "shard_index",
                    "shard_count",
                    "source_start",
                    "source_context_start",
                    "source_train_start",
                    "source_stop",
                    "source_action_count",
                    "context_example_count",
                    "train_example_count",
                    "example_count",
                    "stored_bytes",
                ):
                    shard[key] = int(shard[key])
                normalized_shards.append(shard)
            item["replay_shards"] = normalized_shards
            skills.append(item)
        compositions: list[dict[str, Any]] = []
        raw_compositions = list(value.get("composition_replays", []))
        has_explicit_active = any("active" in raw for raw in raw_compositions)
        for position, raw in enumerate(raw_compositions):
            item = dict(raw)
            if item.get("protocol") != SELF_GENERATED_COMPOSITION_PROTOCOL:
                raise ValueError("Unsupported self-generated composition replay")
            item["skill_ids"] = [str(skill_id) for skill_id in item.get("skill_ids", [])]
            item["goal_switch_offsets"] = [
                int(offset) for offset in item.get("goal_switch_offsets", [])
            ]
            item["full_goal_switch_offsets"] = [
                int(offset) for offset in item.get("full_goal_switch_offsets", [])
            ]
            item["excerpt_offsets"] = [int(offset) for offset in item.get("excerpt_offsets", [])]
            item["action_count"] = int(item["action_count"])
            item["full_action_count"] = int(item.get("full_action_count", item["action_count"]))
            item["target_index"] = int(item["target_index"])
            item["successful_replays"] = int(item.get("successful_replays", 0))
            item["active"] = bool(
                item.get(
                    "active",
                    not has_explicit_active and position == len(raw_compositions) - 1,
                )
            )
            if len(item["skill_ids"]) < 2 or item["successful_replays"] < 1:
                raise ValueError("Self-generated composition replay evidence is incomplete")
            offsets = item["goal_switch_offsets"]
            if (
                len(offsets) != len(item["skill_ids"]) - 1
                or any(not 0 < offset < item["action_count"] for offset in offsets)
                or any(left >= right for left, right in zip(offsets, offsets[1:], strict=False))
            ):
                raise ValueError("Self-generated composition boundaries are invalid")
            full_offsets = item["full_goal_switch_offsets"]
            excerpts = item["excerpt_offsets"]
            if (
                len(full_offsets) != len(offsets)
                or any(not 0 < offset < item["full_action_count"] for offset in full_offsets)
                or any(
                    left >= right
                    for left, right in zip(full_offsets, full_offsets[1:], strict=False)
                )
                or len(excerpts) != len(offsets) + 1
                or excerpts[0] != 0
                or excerpts[-1] != item["action_count"]
                or any(left >= right for left, right in zip(excerpts, excerpts[1:], strict=False))
            ):
                raise ValueError("Self-generated composition excerpt metadata is invalid")
            compositions.append(item)
        return cls(
            root_entry_id=str(value["root_entry_id"]),
            window_size=int(value["window_size"]),
            threshold=float(value["threshold"]),
            skills=skills,
            total_rehearsal_attempts=int(value.get("total_rehearsal_attempts", 0)),
            total_rehearsal_successes=int(value.get("total_rehearsal_successes", 0)),
            imitation_updates=int(value.get("imitation_updates", 0)),
            imitation_examples=int(value.get("imitation_examples", 0)),
            last_imitation_loss=(
                None
                if value.get("last_imitation_loss") is None
                else float(value["last_imitation_loss"])
            ),
            imitation_pending=bool(value.get("imitation_pending", False)),
            v8_schedule_decisions=int(value.get("v8_schedule_decisions", 0)),
            student_training_rounds=int(value.get("student_training_rounds", 0)),
            student_updates=int(value.get("student_updates", 0)),
            student_examples=int(value.get("student_examples", 0)),
            last_student_report=(
                None
                if value.get("last_student_report") is None
                else dict(value["last_student_report"])
            ),
            last_student_replay_rollout=int(value.get("last_student_replay_rollout", -1)),
            exam_rng_state=(
                None if value.get("exam_rng_state") is None else list(value["exam_rng_state"])
            ),
            frozen_exam_rounds=int(value.get("frozen_exam_rounds", 0)),
            frozen_exam_actions=int(value.get("frozen_exam_actions", 0)),
            last_frozen_exam_actions=int(value.get("last_frozen_exam_actions", 0)),
            composition_attempts=int(value.get("composition_attempts", 0)),
            composition_successes=int(value.get("composition_successes", 0)),
            composition_window=[bool(result) for result in value.get("composition_window", [])],
            best_composition_index=int(value.get("best_composition_index", 0)),
            hall_of_fame_completions=int(value.get("hall_of_fame_completions", 0)),
            composition_replays=compositions,
            composition_build_outcomes={
                str(fingerprint): str(outcome)
                for fingerprint, outcome in value.get("composition_build_outcomes", {}).items()
            },
            composition_boundary_cursor=int(value.get("composition_boundary_cursor", 0)),
        )

    def add_verified_skill(
        self,
        *,
        skill_id: str,
        source_entry_id: str,
        source_index: int,
        target_entry_id: str,
        target_index: int,
        target_label: str,
        target_frame_file: str,
        target_frame_sha256: str,
        dataset_file: str,
        dataset_sha256: str,
        action_count: int,
        original_action_count: int | None = None,
        distillation_audit_file: str | None = None,
        distillation_audit_sha256: str | None = None,
        distillation_oracle_calls: int = 0,
        distillation_oracle_actions_replayed: int = 0,
        distillation_edits_accepted: int = 0,
        distillation_edits_rejected: int = 0,
        target_clip_channels: int = 1,
        replay_shards: Sequence[Mapping[str, Any]] = (),
        replay_shard_example_cap: int = 0,
        replay_shard_burn_in: int = 0,
    ) -> bool:
        """Admit one option only after the agent's own trajectory passed replay."""

        if any(str(skill["skill_id"]) == skill_id for skill in self.skills):
            return False
        original_count = action_count if original_action_count is None else original_action_count
        if source_index >= target_index or action_count < 1:
            raise ValueError("Self-taught skill must advance from an earlier verified state")
        if original_count < action_count:
            raise ValueError("A distilled skill cannot be longer than its source trajectory")
        if target_clip_channels < 1:
            raise ValueError("A self-taught target clip needs at least one frame")
        if (distillation_audit_file is None) != (distillation_audit_sha256 is None):
            raise ValueError("Distillation audit path and hash must be recorded together")
        distillation_counts = (
            distillation_oracle_calls,
            distillation_oracle_actions_replayed,
            distillation_edits_accepted,
            distillation_edits_rejected,
        )
        if any(value < 0 for value in distillation_counts):
            raise ValueError("Distillation accounting cannot be negative")
        if distillation_audit_file is None and any(distillation_counts):
            raise ValueError("Distillation accounting requires a sealed audit")
        normalized_shards = [dict(shard) for shard in replay_shards]
        if bool(normalized_shards) != (replay_shard_example_cap > 0):
            raise ValueError("Replay shards and their example cap must be recorded together")
        if replay_shard_burn_in < 0:
            raise ValueError("Replay shard burn-in cannot be negative")
        self.skills.append(
            {
                "skill_id": skill_id,
                "source_entry_id": source_entry_id,
                "source_index": source_index,
                "target_entry_id": target_entry_id,
                "target_index": target_index,
                "target_label": target_label,
                "target_frame_file": target_frame_file,
                "target_frame_sha256": target_frame_sha256,
                "dataset_file": dataset_file,
                "dataset_sha256": dataset_sha256,
                "action_count": action_count,
                "original_action_count": original_count,
                "compression_ratio": action_count / original_count,
                "distillation_audit_file": distillation_audit_file,
                "distillation_audit_sha256": distillation_audit_sha256,
                "distillation_oracle_calls": distillation_oracle_calls,
                "distillation_oracle_actions_replayed": (
                    distillation_oracle_actions_replayed
                ),
                "distillation_edits_accepted": distillation_edits_accepted,
                "distillation_edits_rejected": distillation_edits_rejected,
                "target_clip_channels": target_clip_channels,
                "replay_shards": normalized_shards,
                "replay_shard_example_cap": int(replay_shard_example_cap),
                "replay_shard_burn_in": int(replay_shard_burn_in),
                "replay_cursor": 0,
                "attempts": 0,
                "successes": 0,
                "window": [],
                "competent": False,
                "last_retention_decision": self.v8_schedule_decisions,
                "competence_losses": 0,
                "discovered_at": datetime.now(UTC).isoformat(),
            }
        )
        # Re-run the complete structural checks before allowing newly supplied
        # shard metadata to become part of the mutable ledger.
        try:
            self.__post_init__()
        except Exception:
            self.skills.pop()
            raise
        self.imitation_pending = True
        return True

    def replay_shard(self, skill_id: str) -> dict[str, Any]:
        """Return the bounded shard selected by this skill's persistent cursor."""

        skill = self.skill(skill_id)
        shards = list(skill.get("replay_shards", []))
        if not shards:
            raise ValueError("V8 skill has no admission-time replay shards")
        return shards[int(skill.get("replay_cursor", 0)) % len(shards)]

    def advance_replay_cursors(self, skill_ids: Sequence[str]) -> None:
        """Advance only shards consumed by a completed Student training round."""

        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Replay cursor advancement contains duplicate skills")
        for skill_id in skill_ids:
            skill = self.skill(str(skill_id))
            if not skill.get("replay_shards"):
                raise ValueError("Cannot advance an unsharded V8 replay skill")
            skill["replay_cursor"] = int(skill.get("replay_cursor", 0)) + 1

    def skill(self, skill_id: str) -> dict[str, Any]:
        match = next(
            (skill for skill in self.skills if str(skill["skill_id"]) == skill_id),
            None,
        )
        if match is None:
            raise ValueError("Self-taught episode references an unknown skill")
        return match

    def add_verified_composition(
        self,
        *,
        composition_id: str,
        fingerprint: str,
        skill_ids: Sequence[str],
        target_index: int,
        dataset_file: str,
        dataset_sha256: str,
        audit_file: str,
        audit_sha256: str,
        action_count: int,
        goal_switch_offsets: Sequence[int],
        full_action_count: int,
        full_goal_switch_offsets: Sequence[int],
        excerpt_offsets: Sequence[int],
        successful_replays: int,
    ) -> bool:
        """Admit a continuous power-on chain only after its own replay succeeded."""

        if any(
            str(composition["composition_id"]) == composition_id
            for composition in self.composition_replays
        ):
            return False
        ordered_ids = [str(skill_id) for skill_id in skill_ids]
        if len(ordered_ids) < 2 or len(ordered_ids) != len(set(ordered_ids)):
            raise ValueError("A composition needs at least two unique verified skills")
        chain = [self.skill(skill_id) for skill_id in ordered_ids]
        if not all(bool(skill.get("competent", False)) for skill in chain):
            raise ValueError("A composition may include only competent skills")
        if str(chain[0]["source_entry_id"]) != self.root_entry_id or any(
            str(left["target_entry_id"]) != str(right["source_entry_id"])
            for left, right in zip(chain, chain[1:], strict=False)
        ):
            raise ValueError("A composition must be a continuous chain from power-on")
        offsets = [int(offset) for offset in goal_switch_offsets]
        full_offsets = [int(offset) for offset in full_goal_switch_offsets]
        excerpts = [int(offset) for offset in excerpt_offsets]
        if (
            action_count < 2
            or len(offsets) != len(ordered_ids) - 1
            or any(not 0 < offset < action_count for offset in offsets)
            or any(left >= right for left, right in zip(offsets, offsets[1:], strict=False))
        ):
            raise ValueError("Composition goal-switch boundaries are invalid")
        if (
            full_action_count < 2
            or len(full_offsets) != len(offsets)
            or any(not 0 < offset < full_action_count for offset in full_offsets)
            or any(
                left >= right for left, right in zip(full_offsets, full_offsets[1:], strict=False)
            )
            or len(excerpts) != len(offsets) + 1
            or excerpts[0] != 0
            or excerpts[-1] != action_count
            or any(left >= right for left, right in zip(excerpts, excerpts[1:], strict=False))
        ):
            raise ValueError("Composition bounded-excerpt metadata is invalid")
        if successful_replays < 1:
            raise ValueError("Composition training requires a successful continuous replay")
        if not all(
            value and len(value) == 64 for value in (dataset_sha256, audit_sha256, fingerprint)
        ):
            raise ValueError("Composition artifacts require SHA-256 identities")
        for previous in self.composition_replays:
            previous["active"] = False
        self.composition_replays.append(
            {
                "composition_id": composition_id,
                "protocol": SELF_GENERATED_COMPOSITION_PROTOCOL,
                "fingerprint": fingerprint,
                "skill_ids": ordered_ids,
                "target_index": int(target_index),
                "dataset_file": dataset_file,
                "dataset_sha256": dataset_sha256,
                "audit_file": audit_file,
                "audit_sha256": audit_sha256,
                "action_count": int(action_count),
                "goal_switch_offsets": offsets,
                "full_action_count": int(full_action_count),
                "full_goal_switch_offsets": full_offsets,
                "excerpt_offsets": excerpts,
                "successful_replays": int(successful_replays),
                "active": True,
                "verified_at": datetime.now(UTC).isoformat(),
            }
        )
        self.composition_build_outcomes[fingerprint] = "verified"
        self.composition_boundary_cursor = 0
        self.imitation_pending = True
        return True

    def activate_verified_composition(self, fingerprint: str | None) -> bool:
        """Select at most one verified full-prefix replay for bounded Student loading."""

        if fingerprint is not None and self.composition_build_outcomes.get(fingerprint) != (
            "verified"
        ):
            raise ValueError("Only a verified composition replay may become active")
        found = fingerprint is None
        changed = False
        for composition in self.composition_replays:
            active = fingerprint is not None and composition["fingerprint"] == fingerprint
            found |= active
            changed |= bool(composition.get("active", False)) != active
            composition["active"] = active
        if not found:
            raise ValueError("Verified composition replay is missing from the ledger")
        if changed:
            self.composition_boundary_cursor = 0
            self.imitation_pending = True
        return changed

    def active_composition_replays(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            composition
            for composition in self.composition_replays
            if bool(composition.get("active", False))
        )

    def record_composition_build_failure(self, fingerprint: str) -> None:
        """Remember deterministic replay rejection so resume does not retry bad data."""

        if len(fingerprint) != 64:
            raise ValueError("Composition build fingerprint must be SHA-256")
        previous = self.composition_build_outcomes.get(fingerprint)
        if previous == "verified":
            raise ValueError("A verified composition cannot become replay-failed")
        self.composition_build_outcomes[fingerprint] = "replay_failed"

    def weakest_skills(self) -> list[dict[str, Any]]:
        if not self.skills:
            return []

        def priority(skill: Mapping[str, Any]) -> tuple[int, float, int, int]:
            window = [bool(result) for result in skill.get("window", [])]
            rate = sum(window) / len(window) if window else 0.0
            return (
                int(bool(skill.get("competent", False))),
                rate,
                int(skill.get("successes", 0)),
                int(skill.get("attempts", 0)),
            )

        best_priority = min(priority(skill) for skill in self.skills)
        return [skill for skill in self.skills if priority(skill) == best_priority]

    def record_episode(
        self,
        *,
        mode: str,
        skill_id: str | None,
        best_reached_index: int,
    ) -> bool:
        if mode not in {"self_rehearsal", *V8_REHEARSAL_MODES} or skill_id is None:
            return False
        skill = self.skill(skill_id)
        success = best_reached_index >= int(skill["target_index"])
        skill["attempts"] = int(skill.get("attempts", 0)) + 1
        skill["successes"] = int(skill.get("successes", 0)) + int(success)
        window = [*skill.get("window", []), success][-self.window_size :]
        skill["window"] = window
        self.total_rehearsal_attempts += 1
        self.total_rehearsal_successes += int(success)
        passed_now = (
            not bool(skill.get("competent", False))
            and len(window) == self.window_size
            and sum(window) / self.window_size >= self.threshold
        )
        if passed_now:
            skill["competent"] = True
            skill["competent_at"] = datetime.now(UTC).isoformat()
            if mode in V8_REHEARSAL_MODES:
                skill["last_retention_decision"] = self.v8_schedule_decisions
        if mode in V8_REHEARSAL_MODES:
            qualified_now = (
                len(window) == self.window_size and sum(window) / self.window_size >= self.threshold
            )
            if bool(skill.get("competent", False)) and not qualified_now:
                skill["competent"] = False
                skill["competence_losses"] = int(skill.get("competence_losses", 0)) + 1
                skill["competence_lost_at"] = datetime.now(UTC).isoformat()
            if mode == "self_retention":
                skill["last_retention_decision"] = self.v8_schedule_decisions
        return passed_now

    def record_imitation(self, *, updates: int, examples: int, mean_loss: float) -> None:
        if updates < 1 or examples < 1:
            raise ValueError("Self-imitation accounting requires positive work")
        self.imitation_updates += updates
        self.imitation_examples += examples
        self.last_imitation_loss = float(mean_loss)
        self.imitation_pending = False

    def record_student_training(self, report: Mapping[str, Any]) -> None:
        """Persist one continuous, Student-only replay round."""

        updates = int(report.get("updates", 0))
        examples = int(report.get("train_examples", 0))
        if updates < 1 or examples < 1:
            raise ValueError("Student training accounting requires positive work")
        self.student_training_rounds += 1
        self.student_updates += updates
        self.student_examples += examples
        self.last_student_report = dict(report)
        self.imitation_pending = False

    def record_frozen_exam_round(self, *, actions: int) -> None:
        if actions < 0:
            raise ValueError("Frozen exam actions cannot be negative")
        self.frozen_exam_rounds += 1
        self.frozen_exam_actions += actions

    def record_composition_exam(
        self,
        *,
        success: bool,
        actions: int,
        target_index: int = 0,
        hall_of_fame_target: bool = False,
    ) -> None:
        if actions < 0:
            raise ValueError("Composition exam actions cannot be negative")
        if target_index < 0:
            raise ValueError("Composition target index cannot be negative")
        self.composition_attempts += 1
        self.composition_successes += int(success)
        self.composition_window = [*self.composition_window, bool(success)][-self.window_size :]
        if success:
            self.best_composition_index = max(self.best_composition_index, target_index)
            self.hall_of_fame_completions += int(hall_of_fame_target)

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "protocol": SELF_TAUGHT_PROTOCOL,
            "root_entry_id": self.root_entry_id,
            "window_size": self.window_size,
            "threshold": self.threshold,
            "skills": self.skills,
            "total_rehearsal_attempts": self.total_rehearsal_attempts,
            "total_rehearsal_successes": self.total_rehearsal_successes,
            "imitation_updates": self.imitation_updates,
            "imitation_examples": self.imitation_examples,
            "last_imitation_loss": self.last_imitation_loss,
            "imitation_pending": self.imitation_pending,
            "v8_schedule_decisions": self.v8_schedule_decisions,
            "student_training_rounds": self.student_training_rounds,
            "student_updates": self.student_updates,
            "student_examples": self.student_examples,
            "last_student_report": self.last_student_report,
            "last_student_replay_rollout": self.last_student_replay_rollout,
            "exam_rng_state": self.exam_rng_state,
            "frozen_exam_rounds": self.frozen_exam_rounds,
            "frozen_exam_actions": self.frozen_exam_actions,
            "last_frozen_exam_actions": self.last_frozen_exam_actions,
            "composition_attempts": self.composition_attempts,
            "composition_successes": self.composition_successes,
            "composition_window": self.composition_window,
            "best_composition_index": self.best_composition_index,
            "hall_of_fame_completions": self.hall_of_fame_completions,
            "composition_replays": self.composition_replays,
            "composition_build_outcomes": dict(sorted(self.composition_build_outcomes.items())),
            "composition_boundary_cursor": self.composition_boundary_cursor,
            "updated_at": datetime.now(UTC).isoformat(),
        }


@dataclass(frozen=True, slots=True)
class V8EpisodeChoice:
    """One explainable V8 scheduling decision.

    ``entry`` remains the curriculum state loaded for the episode. The actor still
    receives only its allowed visual observation; the prerequisite path and reason
    are trainer-side audit data.
    """

    entry: Mapping[str, Any]
    mode: str
    target_index: int
    skill_id: str | None
    target_frame_file: str | None
    reason: str
    prerequisite_skill_ids: tuple[str, ...] = ()

    def legacy_tuple(
        self,
    ) -> tuple[Mapping[str, Any], str, int, str | None, str | None]:
        """Return the five fields consumed by the V7 environment API."""

        return (
            self.entry,
            self.mode,
            self.target_index,
            self.skill_id,
            self.target_frame_file,
        )


def _competent_path_to_entry(
    library: SelfTaughtSkillLibrary,
    entry_id: str,
) -> tuple[str, ...] | None:
    """Return one fully competent path from power-on to ``entry_id``."""

    incoming: dict[str, list[Mapping[str, Any]]] = {}
    for skill in library.skills:
        incoming.setdefault(str(skill["target_entry_id"]), []).append(skill)

    def visit(current: str, visiting: frozenset[str]) -> tuple[str, ...] | None:
        if current == library.root_entry_id:
            return ()
        if current in visiting:
            return None
        candidates: list[tuple[str, ...]] = []
        for skill in incoming.get(current, []):
            if not bool(skill.get("competent", False)):
                continue
            prefix = visit(str(skill["source_entry_id"]), visiting | frozenset({current}))
            if prefix is not None:
                candidates.append((*prefix, str(skill["skill_id"])))
        if not candidates:
            return None
        return min(candidates, key=lambda path: (len(path), path))

    return visit(entry_id, frozenset())


def choose_v8_self_taught_episode(
    entries: Sequence[Mapping[str, Any]],
    library: SelfTaughtSkillLibrary,
    rng: random.Random,
    *,
    frontier_probability: float,
    minimum_evaluation_attempts: int | None = None,
    retention_interval: int = 50,
) -> V8EpisodeChoice:
    """Schedule V8 exploration, evaluation, mastery, or retention.

    The scheduler first preserves the configured frontier allocation. Rehearsal is
    then limited to skills whose source has a fully competent path from power-on.
    Eligible skills receive a minimum evaluation quota before mastery practice,
    least-practiced unqualified skills rotate fairly, and qualified skills are
    periodically re-tested for forgetting.
    """

    if not 0 <= frontier_probability <= 1:
        raise ValueError("Frontier probability must be between zero and one")
    evaluation_quota = (
        library.window_size if minimum_evaluation_attempts is None else minimum_evaluation_attempts
    )
    if evaluation_quota < 1:
        raise ValueError("Minimum evaluation attempts must be positive")
    if retention_interval < 1:
        raise ValueError("Retention interval must be positive")

    by_id = {_entry_id(entry): entry for entry in entries}
    best_index = max(_entry_index(entry) for entry in entries)
    frontier = [entry for entry in entries if _entry_index(entry) == best_index]
    library.v8_schedule_decisions += 1
    decision = library.v8_schedule_decisions

    def frontier_choice(reason: str) -> V8EpisodeChoice:
        return V8EpisodeChoice(
            entry=rng.choice(frontier),
            mode="self_frontier",
            target_index=best_index,
            skill_id=None,
            target_frame_file=None,
            reason=reason,
        )

    if not library.skills:
        return frontier_choice("no_verified_skills")
    if rng.random() < frontier_probability:
        return frontier_choice("configured_frontier_allocation")

    eligible: list[tuple[dict[str, Any], tuple[str, ...]]] = []
    for skill in library.skills:
        path = _competent_path_to_entry(library, str(skill["source_entry_id"]))
        if path is not None:
            eligible.append((skill, path))
    if not eligible:
        return frontier_choice("all_rehearsals_blocked_by_prerequisites")

    due_retention = [
        (skill, path)
        for skill, path in eligible
        if bool(skill.get("competent", False))
        and decision - int(skill.get("last_retention_decision", 0)) >= retention_interval
    ]
    if due_retention and decision % retention_interval == 0:
        most_overdue = max(
            decision - int(skill.get("last_retention_decision", 0))
            for skill, _path in due_retention
        )
        choices = [
            (skill, path)
            for skill, path in due_retention
            if decision - int(skill.get("last_retention_decision", 0)) == most_overdue
        ]
        skill, path = rng.choice(choices)
        mode = "self_retention"
        reason = "periodic_retention_due"
    else:
        evaluation = [
            (skill, path)
            for skill, path in eligible
            if int(skill.get("attempts", 0)) < evaluation_quota
        ]
        if evaluation:
            fewest_attempts = min(int(skill.get("attempts", 0)) for skill, _path in evaluation)
            choices = [
                (skill, path)
                for skill, path in evaluation
                if int(skill.get("attempts", 0)) == fewest_attempts
            ]
            skill, path = rng.choice(choices)
            mode = "self_evaluation"
            reason = "minimum_evaluation_quota"
        else:
            mastery = [
                (skill, path) for skill, path in eligible if not bool(skill.get("competent", False))
            ]
            if not mastery:
                return frontier_choice("all_available_skills_qualified")
            fewest_attempts = min(int(skill.get("attempts", 0)) for skill, _path in mastery)
            choices = [
                (skill, path)
                for skill, path in mastery
                if int(skill.get("attempts", 0)) == fewest_attempts
            ]
            skill, path = rng.choice(choices)
            mode = "self_mastery"
            reason = "least_practiced_unqualified_skill"

    source = by_id.get(str(skill["source_entry_id"]))
    if source is None:
        raise ValueError("Self-taught skill source is missing from the curriculum")
    return V8EpisodeChoice(
        entry=source,
        mode=mode,
        target_index=int(skill["target_index"]),
        skill_id=str(skill["skill_id"]),
        target_frame_file=str(skill["target_frame_file"]),
        reason=reason,
        prerequisite_skill_ids=path,
    )


def choose_self_taught_episode(
    entries: Sequence[Mapping[str, Any]],
    library: SelfTaughtSkillLibrary,
    rng: random.Random,
    *,
    frontier_probability: float,
) -> tuple[Mapping[str, Any], str, int, str | None, str | None]:
    """Choose open exploration or practice of the weakest self-discovered visual skill."""

    if not 0 <= frontier_probability <= 1:
        raise ValueError("Frontier probability must be between zero and one")
    by_id = {_entry_id(entry): entry for entry in entries}
    best_index = max(_entry_index(entry) for entry in entries)
    frontier = [entry for entry in entries if _entry_index(entry) == best_index]
    if not library.skills or rng.random() < frontier_probability:
        return rng.choice(frontier), "self_frontier", best_index, None, None

    skill = rng.choice(library.weakest_skills())
    source = by_id.get(str(skill["source_entry_id"]))
    if source is None:
        raise ValueError("Self-taught skill source is missing from the curriculum")
    return (
        source,
        "self_rehearsal",
        int(skill["target_index"]),
        str(skill["skill_id"]),
        str(skill["target_frame_file"]),
    )
