from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

CONSOLIDATION_PROTOCOL = "backward-competence-consolidation-v1"


def _entry_index(entry: Mapping[str, Any]) -> int:
    return int(entry["milestone_index"])


def _available_indices(entries: Sequence[Mapping[str, Any]]) -> tuple[int, ...]:
    indices = tuple(sorted({_entry_index(entry) for entry in entries}))
    if not indices or indices[0] != 0:
        raise ValueError("Consolidation curriculum requires a power-on entry")
    return indices


def _previous_index(indices: Sequence[int], current: int) -> int:
    earlier = [index for index in indices if index < current]
    return earlier[-1] if earlier else int(indices[0])


@dataclass(slots=True)
class BackwardConsolidation:
    """Rolling training gates that expand one verified start state toward power-on."""

    available_indices: tuple[int, ...]
    target_index: int
    active_start_index: int
    window_size: int = 10
    threshold: float = 0.8
    gate_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    gates_passed: list[dict[str, Any]] = field(default_factory=list)
    power_on_training_gate_passed: bool = False

    def __post_init__(self) -> None:
        if not self.available_indices or self.available_indices[0] != 0:
            raise ValueError("Consolidation indices must begin at power-on")
        if tuple(sorted(set(self.available_indices))) != self.available_indices:
            raise ValueError("Consolidation indices must be sorted and unique")
        if self.target_index not in self.available_indices:
            raise ValueError("Consolidation target must exist in the curriculum")
        if self.active_start_index not in self.available_indices:
            raise ValueError("Consolidation start must exist in the curriculum")
        if self.active_start_index > self.target_index:
            raise ValueError("Consolidation start cannot follow its target")
        if self.window_size < 2 or not 0 < self.threshold <= 1:
            raise ValueError("Consolidation gate settings are invalid")

    @classmethod
    def initialize(
        cls,
        entries: Sequence[Mapping[str, Any]],
        *,
        window_size: int,
        threshold: float,
    ) -> BackwardConsolidation:
        indices = _available_indices(entries)
        target = indices[-1]
        return cls(
            available_indices=indices,
            target_index=target,
            active_start_index=_previous_index(indices, target),
            window_size=window_size,
            threshold=threshold,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BackwardConsolidation:
        if value.get("protocol") != CONSOLIDATION_PROTOCOL:
            raise ValueError("Unsupported consolidation state")
        return cls(
            available_indices=tuple(int(index) for index in value["available_indices"]),
            target_index=int(value["target_index"]),
            active_start_index=int(value["active_start_index"]),
            window_size=int(value["window_size"]),
            threshold=float(value["threshold"]),
            gate_results={
                str(key): {
                    "attempts": int(item.get("attempts", 0)),
                    "successes": int(item.get("successes", 0)),
                    "best_reached_index": int(item.get("best_reached_index", 0)),
                    "window": [bool(result) for result in item.get("window", [])],
                }
                for key, item in dict(value.get("gate_results", {})).items()
            },
            gates_passed=[dict(item) for item in value.get("gates_passed", [])],
            power_on_training_gate_passed=bool(
                value.get("power_on_training_gate_passed", False)
            ),
        )

    @property
    def active_key(self) -> str:
        return f"{self.active_start_index}->{self.target_index}"

    @property
    def active_window(self) -> tuple[bool, ...]:
        item = self.gate_results.get(self.active_key, {})
        return tuple(bool(result) for result in item.get("window", []))

    @property
    def active_window_rate(self) -> float:
        window = self.active_window
        return sum(window) / len(window) if window else 0.0

    def sync_curriculum(self, entries: Sequence[Mapping[str, Any]]) -> bool:
        """Move a newly promoted target to its immediately preceding verified start."""

        indices = _available_indices(entries)
        new_target = indices[-1]
        changed = indices != self.available_indices or new_target != self.target_index
        self.available_indices = indices
        if new_target > self.target_index:
            old_target = self.target_index
            self.target_index = new_target
            self.active_start_index = (
                old_target if old_target in indices else _previous_index(indices, new_target)
            )
            self.power_on_training_gate_passed = False
        elif self.active_start_index not in indices:
            self.active_start_index = _previous_index(indices, self.target_index)
        return changed

    def record_episode(
        self,
        *,
        start_mode: str,
        start_index: int,
        target_index: int,
        best_reached_index: int,
    ) -> bool:
        """Record one training episode and expand backward when the rolling gate passes."""

        if (
            start_mode != "consolidation"
            or start_index != self.active_start_index
            or target_index != self.target_index
        ):
            return False
        key = self.active_key
        item = self.gate_results.setdefault(
            key,
            {"attempts": 0, "successes": 0, "best_reached_index": 0, "window": []},
        )
        success = best_reached_index >= target_index
        item["attempts"] += 1
        item["successes"] += int(success)
        item["best_reached_index"] = max(item["best_reached_index"], best_reached_index)
        item["window"].append(success)
        item["window"] = item["window"][-self.window_size :]
        if self.active_start_index == 0 and self.power_on_training_gate_passed:
            return False
        if len(item["window"]) < self.window_size:
            return False
        if sum(item["window"]) / self.window_size < self.threshold:
            return False

        passed_start = self.active_start_index
        self.gates_passed.append(
            {
                "start_index": passed_start,
                "target_index": self.target_index,
                "window_successes": sum(item["window"]),
                "window_attempts": self.window_size,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )
        if passed_start == 0:
            self.power_on_training_gate_passed = True
        else:
            self.active_start_index = _previous_index(
                self.available_indices, self.active_start_index
            )
        return True

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "protocol": CONSOLIDATION_PROTOCOL,
            "available_indices": list(self.available_indices),
            "target_index": self.target_index,
            "active_start_index": self.active_start_index,
            "window_size": self.window_size,
            "threshold": self.threshold,
            "active_window": list(self.active_window),
            "active_window_rate": self.active_window_rate,
            "gate_results": self.gate_results,
            "gates_passed": self.gates_passed,
            "power_on_training_gate_passed": self.power_on_training_gate_passed,
            "updated_at": datetime.now(UTC).isoformat(),
        }


def choose_consolidation_entry(
    entries: Sequence[Mapping[str, Any]],
    state: BackwardConsolidation,
    rng: random.Random,
    *,
    frontier_probability: float,
) -> tuple[Mapping[str, Any], str, int]:
    """Choose either new-frontier practice or the active backward-composition gate."""

    if not 0 <= frontier_probability <= 1:
        raise ValueError("Frontier probability must be between zero and one")
    frontier = [entry for entry in entries if _entry_index(entry) == state.target_index]
    consolidation = [
        entry for entry in entries if _entry_index(entry) == state.active_start_index
    ]
    if not frontier or not consolidation:
        raise ValueError("Consolidation state references a missing curriculum entry")
    if rng.random() < frontier_probability:
        return rng.choice(frontier), "frontier", state.target_index
    return rng.choice(consolidation), "consolidation", state.target_index
