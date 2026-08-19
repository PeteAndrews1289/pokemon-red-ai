"""Training-mode predicates and the protocol strings each mode declares."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pokemon_red_ai.frontier_learning import FullGameRewardConfig
from pokemon_red_ai.milestones import HALL_OF_FAME_KEY
from pokemon_red_ai.ppo.constants import (
    PPO_PROTOCOL,
    PPO_REWARD_PROTOCOL,
    PPO_V8_PROTOCOL,
    PPO_V8_REWARD_PROTOCOL,
    PPO_V9_PROTOCOL,
    PPO_V9_REWARD_PROTOCOL,
    PPO_V10_PROTOCOL,
    PPO_V10_REWARD_PROTOCOL,
    PPO_V12_PROTOCOL,
    PPO_V12_REWARD_PROTOCOL,
    V10_NARRATIVE_TELEMETRY_PROTOCOL,
    V12_NARRATIVE_TELEMETRY_PROTOCOL,
)
from pokemon_red_ai.self_taught import (
    SelfTaughtSkillLibrary,
)


def _is_self_taught_mode(mode: str) -> bool:
    return mode in {
        "self_taught",
        "self_taught_v8",
        "self_taught_v9",
        "self_taught_v10",
        "self_taught_v12",
    }


def _is_v8_mode(mode: str) -> bool:
    return mode == "self_taught_v8"


def _is_v9_mode(mode: str) -> bool:
    return mode == "self_taught_v9"


def _is_v10_mode(mode: str) -> bool:
    return mode == "self_taught_v10"


def _is_v12_mode(mode: str) -> bool:
    return mode == "self_taught_v12"


def _uses_pixel_recovery(mode: str) -> bool:
    return mode in {"self_taught_v10", "self_taught_v12"}


def _uses_blind_watchdog(mode: str) -> bool:
    return _is_distilled_student_mode(mode) or _is_v12_mode(mode)


def _requires_reproducible_source(mode: str) -> bool:
    return _is_distilled_student_mode(mode) or _is_v12_mode(mode)


def _uses_frozen_exam(mode: str) -> bool:
    return _is_distilled_student_mode(mode) or _is_v12_mode(mode)


def _narrative_telemetry_protocol(mode: str) -> str:
    return (
        V12_NARRATIVE_TELEMETRY_PROTOCOL
        if _is_v12_mode(mode)
        else V10_NARRATIVE_TELEMETRY_PROTOCOL
    )


def _uses_v9_practice(mode: str) -> bool:
    return mode in {"self_taught_v9", "self_taught_v10"}


def _is_distilled_student_mode(mode: str) -> bool:
    return mode in {"self_taught_v8", "self_taught_v9", "self_taught_v10"}


def _classify_episode_end(
    mode: str,
    *,
    alive: bool,
    loop_reason: str | None,
    action_limit: bool,
) -> tuple[bool, bool, str | None]:
    """Separate genuine V10 failures from the ordinary sampling time limit."""

    failure_reason = loop_reason or (None if alive else "emulator_stop")
    if failure_reason is not None:
        if _uses_pixel_recovery(mode):
            return True, False, failure_reason
        return False, True, failure_reason
    if action_limit:
        return False, True, "episode_action_limit"
    return False, False, None


def _ppo_protocol(mode: str) -> str:
    if _is_v12_mode(mode):
        return PPO_V12_PROTOCOL
    if _is_v10_mode(mode):
        return PPO_V10_PROTOCOL
    if _is_v9_mode(mode):
        return PPO_V9_PROTOCOL
    return PPO_V8_PROTOCOL if _is_v8_mode(mode) else PPO_PROTOCOL


def _ppo_reward_protocol(mode: str) -> str:
    if _is_v12_mode(mode):
        return PPO_V12_REWARD_PROTOCOL
    if _is_v10_mode(mode):
        return PPO_V10_REWARD_PROTOCOL
    if _is_v9_mode(mode):
        return PPO_V9_REWARD_PROTOCOL
    return PPO_V8_REWARD_PROTOCOL if _is_v8_mode(mode) else PPO_REWARD_PROTOCOL


def _hall_of_fame_stop_is_verified(
    mode: str,
    status: Mapping[str, Any],
    library: SelfTaughtSkillLibrary | None,
) -> bool:
    if _uses_frozen_exam(mode):
        return library is not None and library.hall_of_fame_completions > 0
    return status.get("best_milestone", {}).get("key") == HALL_OF_FAME_KEY


def _self_taught_reward_config() -> FullGameRewardConfig:
    """Remove authored quest directions while retaining consequence and novelty feedback."""

    return FullGameRewardConfig(
        milestone=0,
        lesson_navigation=0,
        lesson_progress=0,
        goal_navigation=0,
        navigation_recovery=0,
    )
