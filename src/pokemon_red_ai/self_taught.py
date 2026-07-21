from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SELF_TAUGHT_PROTOCOL = "self-generated-visual-skills-v1"


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

    def __post_init__(self) -> None:
        if not self.root_entry_id:
            raise ValueError("Self-taught skills require a power-on entry")
        if self.window_size < 2 or not 0 < self.threshold <= 1:
            raise ValueError("Self-taught competence settings are invalid")
        identifiers = [str(skill["skill_id"]) for skill in self.skills]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Self-taught skill identifiers must be unique")

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
            skills.append(item)
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
    ) -> bool:
        """Admit one option only after the agent's own trajectory passed replay."""

        if any(str(skill["skill_id"]) == skill_id for skill in self.skills):
            return False
        if source_index >= target_index or action_count < 1:
            raise ValueError("Self-taught skill must advance from an earlier verified state")
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
                "attempts": 0,
                "successes": 0,
                "window": [],
                "competent": False,
                "discovered_at": datetime.now(UTC).isoformat(),
            }
        )
        self.imitation_pending = True
        return True

    def skill(self, skill_id: str) -> dict[str, Any]:
        match = next(
            (skill for skill in self.skills if str(skill["skill_id"]) == skill_id),
            None,
        )
        if match is None:
            raise ValueError("Self-taught episode references an unknown skill")
        return match

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
        if mode != "self_rehearsal" or skill_id is None:
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
        return passed_now

    def record_imitation(self, *, updates: int, examples: int, mean_loss: float) -> None:
        if updates < 1 or examples < 1:
            raise ValueError("Self-imitation accounting requires positive work")
        self.imitation_updates += updates
        self.imitation_examples += examples
        self.last_imitation_loss = float(mean_loss)
        self.imitation_pending = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
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
            "updated_at": datetime.now(UTC).isoformat(),
        }


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
