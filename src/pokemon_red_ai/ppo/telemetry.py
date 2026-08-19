"""Run telemetry counters, learning-state validation, and control exceptions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from pokemon_red_ai.hindsight import (
    HINDSIGHT_PROTOCOL,
)
from pokemon_red_ai.ppo.constants import (
    V9_PRACTICE_CANCELLATION_REASONS,
    V9_PRACTICE_TERMINAL_REASONS,
    V10_NARRATIVE_TELEMETRY_PROTOCOL,
    V12_LEARNING_STATE_PROTOCOL,
)


class CompositionReplayRejected(RuntimeError):
    """A verified skill chain did not compose continuously from power-on."""


class V9PracticeCancelled(RuntimeError):
    """A campaign boundary interrupted practice before it could become training data."""

    def __init__(self, reason: str) -> None:
        if reason not in V9_PRACTICE_CANCELLATION_REASONS:
            raise ValueError("V9 Student practice cancellation reason is unsupported")
        super().__init__(reason)
        self.reason = reason


def _check_v9_practice_cancellation(
    cancellation_check: Callable[[], str | None] | None,
) -> None:
    if cancellation_check is None:
        return
    reason = cancellation_check()
    if reason is not None:
        raise V9PracticeCancelled(reason)


def _merge_v9_success_student_report(
    previous: Mapping[str, Any] | None,
    immediate: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep the last full replay diagnostics while recording an immediate success update."""

    merged = {} if previous is None else dict(previous)
    merged.update(immediate)
    merged["training_kind"] = "closed_loop_success_only"
    return merged


def _v9_practice_signature_outcome(
    observed_index: int,
    target_index: int,
    observed_signature: tuple[Any, ...],
    target_signature: tuple[Any, ...],
) -> str | None:
    """Classify a target crossing without admitting an ordinal-only match."""

    if observed_index < target_index:
        return None
    return "exact_target" if observed_signature == target_signature else "milestone_wrong_state"


def _v9_practice_terminal_reason_counts(value: object) -> Counter[str]:
    """Load the bounded public V9 attempt denominator fail-closed."""

    if value is None:
        return Counter()
    if not isinstance(value, Mapping):
        raise ValueError("V9 Student practice terminal reasons must be a mapping")
    counts: Counter[str] = Counter()
    for raw_reason, raw_count in value.items():
        reason = str(raw_reason)
        if reason not in V9_PRACTICE_TERMINAL_REASONS:
            raise ValueError("V9 Student practice terminal reason is unsupported")
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
            raise ValueError("V9 Student practice terminal reason count is invalid")
        if raw_count:
            counts[reason] = raw_count
    return counts


def _v10_integer_counter(value: object, *, label: str) -> Counter[str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"V10 {label} telemetry must be a mapping")
    result: Counter[str] = Counter()
    for raw_key, raw_count in value.items():
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
            raise ValueError(f"V10 {label} telemetry count is invalid")
        if raw_count:
            result[str(raw_key)] = raw_count
    return result


def _v10_reward_counter(value: object) -> Counter[str]:
    if not isinstance(value, Mapping):
        raise ValueError("V10 reward telemetry must be a mapping")
    result: Counter[str] = Counter()
    for raw_key, raw_total in value.items():
        if isinstance(raw_total, bool) or not isinstance(raw_total, (int, float)):
            raise ValueError("V10 reward telemetry total is invalid")
        total = float(raw_total)
        if not np.isfinite(total):
            raise ValueError("V10 reward telemetry total must be finite")
        if total:
            result[str(raw_key)] = total
    return result


def _v10_narrative_telemetry(
    value: object,
    *,
    expected_protocol: str = V10_NARRATIVE_TELEMETRY_PROTOCOL,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("protocol") != expected_protocol:
        raise ValueError("V10 checkpoint has invalid narrative telemetry")
    episodes = value.get("episodes")
    promotion_failures = value.get("promotion_failures")
    if (
        isinstance(episodes, bool)
        or not isinstance(episodes, int)
        or episodes < 0
        or isinstance(promotion_failures, bool)
        or not isinstance(promotion_failures, int)
        or promotion_failures < 0
    ):
        raise ValueError("V10 narrative telemetry totals are invalid")
    raw_positions = value.get("positions")
    if not isinstance(raw_positions, list):
        raise ValueError("V10 narrative telemetry positions must be a list")
    positions: set[tuple[int, int, int]] = set()
    for item in raw_positions:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or any(isinstance(part, bool) or not isinstance(part, int) for part in item)
        ):
            raise ValueError("V10 narrative telemetry position is invalid")
        positions.add((item[0], item[1], item[2]))
    raw_active_ranks = value.get("active_environment_ranks")
    if not isinstance(raw_active_ranks, list) or any(
        isinstance(rank, bool) or not isinstance(rank, int) or rank < 0 for rank in raw_active_ranks
    ):
        raise ValueError("V10 narrative telemetry active ranks are invalid")
    active_environment_ranks = set(raw_active_ranks)
    if len(active_environment_ranks) != len(raw_active_ranks):
        raise ValueError("V10 narrative telemetry active ranks repeat")
    recovery_events = _v10_integer_counter(
        value.get("explorer_loop_recovery_events"), label="loop-recovery"
    )
    accounted_windows = sum(
        recovery_events[name]
        for name in (
            "escapes",
            "context_changes",
            "expirations",
            "abandoned_on_resume",
            "abandoned_on_episode_end",
            "abandoned_on_campaign_end",
        )
    ) + len(active_environment_ranks)
    if recovery_events["windows_started"] != accounted_windows:
        raise ValueError("V10 loop-recovery window denominator is inconsistent")
    return {
        "episodes": episodes,
        "promotion_failures": promotion_failures,
        "reward_components": _v10_reward_counter(value.get("reward_components")),
        "battle_events": _v10_integer_counter(value.get("battle_events"), label="battle"),
        "loop_events": _v10_integer_counter(value.get("loop_events"), label="loop"),
        "episode_end_reasons": _v10_integer_counter(
            value.get("episode_end_reasons"), label="episode-end"
        ),
        "explorer_loop_recovery_events": recovery_events,
        "positions": positions,
        "active_environment_ranks": active_environment_ranks,
    }


def _new_v12_learning_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol": V12_LEARNING_STATE_PROTOCOL,
        "hindsight_protocol": HINDSIGHT_PROTOCOL,
        "rollouts_observed": 0,
        "rollouts_with_lessons": 0,
        "lessons_generated": 0,
        "lessons_trained": 0,
        "examples_trained": 0,
        "optimizer_updates": 0,
        "last_mean_loss": None,
        "last_contrastive_loss": None,
        "last_goal_log_probability_advantage": None,
        "pending_lessons": [],
        "terminal_evaluation": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _validate_v12_learning_state(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("protocol") != V12_LEARNING_STATE_PROTOCOL:
        raise ValueError("V12 learning state has the wrong protocol")
    if value.get("hindsight_protocol") != HINDSIGHT_PROTOCOL:
        raise ValueError("V12 learning state has the wrong hindsight protocol")
    result = dict(value)
    for name in (
        "rollouts_observed",
        "rollouts_with_lessons",
        "lessons_generated",
        "lessons_trained",
        "examples_trained",
        "optimizer_updates",
    ):
        raw = result.get(name)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise ValueError(f"V12 learning state has invalid {name}")
    pending = result.get("pending_lessons")
    if not isinstance(pending, list):
        raise ValueError("V12 learning state pending lessons must be a list")
    for item in pending:
        if not isinstance(item, Mapping):
            raise ValueError("V12 pending lesson metadata must be an object")
        filename = str(item.get("file", ""))
        digest = str(item.get("sha256", ""))
        if Path(filename).is_absolute() or Path(filename).parts[:1] != ("hindsight",):
            raise ValueError("V12 pending lesson path is unsafe")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("V12 pending lesson hash is invalid")
    if result["lessons_trained"] > result["lessons_generated"]:
        raise ValueError("V12 trained more hindsight lessons than it generated")
    if result["rollouts_with_lessons"] > result["rollouts_observed"]:
        raise ValueError("V12 lesson rollouts exceed observed rollouts")
    return result
