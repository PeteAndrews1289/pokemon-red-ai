"""Shared constants and module-level tables for the PPO training package."""

from __future__ import annotations

from typing import Any

from pokemon_red_ai.milestones import MILESTONES

PPO_PROTOCOL = "parallel-recurrent-ppo-v7"
PPO_REWARD_PROTOCOL = "self-generated-visual-skills-v1"
PPO_V8_PROTOCOL = "parallel-recurrent-ppo-v8"
PPO_V8_REWARD_PROTOCOL = "distilled-self-generated-skills-v1"
PPO_V9_PROTOCOL = "parallel-recurrent-ppo-v9"
PPO_V9_REWARD_PROTOCOL = "self-correcting-student-v1"
PPO_V10_PROTOCOL = "parallel-recurrent-ppo-v10"
PPO_V10_REWARD_PROTOCOL = "recovery-before-reset-v1"
PPO_V12_PROTOCOL = "parallel-recurrent-ppo-v12"
PPO_V12_REWARD_PROTOCOL = "self-generated-hindsight-goals-v1"
PPO_MODES = frozenset(
    {
        "pixels",
        "assisted",
        "privileged",
        "self_taught",
        "self_taught_v8",
        "self_taught_v9",
        "self_taught_v10",
        "self_taught_v12",
    }
)
V8_CONFIG_FIELDS = frozenset(
    {
        "distillation_attempts",
        "student_replay_interval",
        "student_replay_epochs",
        "student_burn_in",
        "student_train_horizon",
        "student_learning_rate",
        "frozen_exam_interval_actions",
        "frozen_exam_attempts",
        "frozen_exam_action_multiplier",
    }
)
V9_CONFIG_FIELDS = frozenset(
    {
        "student_practice_interval",
        "student_practice_attempts",
        "student_practice_window",
        "student_practice_required",
        "student_practice_confirmations",
        "student_practice_retention",
        "student_practice_rollout_multiplier",
        "student_practice_rollout_slack",
        "student_practice_reservoir",
    }
)
V10_CONFIG_FIELDS = frozenset(
    {
        "explorer_recovery_window_actions",
        "explorer_recovery_blocked_threshold",
        "explorer_recovery_escape_confirmations",
        "explorer_recovery_ineffective_change_fraction",
        "explorer_recovery_ineffective_mean_absolute_error",
        "explorer_recovery_escape_change_fraction",
        "explorer_recovery_escape_mean_absolute_error",
        "explorer_recovery_blocked_penalty",
        "explorer_recovery_escape_reward",
        "explorer_recovery_expiration_penalty",
    }
)
V12_CONFIG_FIELDS = frozenset(
    {
        "hindsight_max_lessons",
        "hindsight_min_actions",
        "hindsight_max_actions",
        "hindsight_min_changed_fraction",
        "hindsight_min_mean_absolute_error",
        "hindsight_epochs",
        "hindsight_contrastive_weight",
        "hindsight_contrastive_margin",
        "terminal_evaluation_actions",
    }
)
V9_PRACTICE_TERMINAL_REASONS = frozenset(
    {"exact_target", "timeout", "emulator_stopped", "milestone_wrong_state"}
)
V9_PRACTICE_CANCELLATION_REASONS = frozenset(
    {"stop_requested", "duration_limit", "action_limit", "low_disk_space", "output_limit"}
)
V9_DISK_BUDGET_REFRESH_SECONDS = 1.0
V10_NARRATIVE_TELEMETRY_PROTOCOL = "v10-narrative-telemetry-v1"
V12_NARRATIVE_TELEMETRY_PROTOCOL = "v12-narrative-telemetry-v1"
V12_LEARNING_STATE_PROTOCOL = "v12-hindsight-learning-state-v1"
V10_RECOVERY_CYCLE_WINDOW = 128
V10_RECOVERY_CYCLE_UNIQUE_LIMIT = 8
V10_RECOVERY_STAGNATION_ACTIONS = 1_024
PRIVILEGED_STATE_SIZE = 24
ACTION_HISTORY_LENGTH = 3
MAP_MEMORY_SIZE = 64
MAP_MEMORY_FEATURES = 64
SKILL_COUNT = 3
GOAL_COUNT = len(MILESTONES) + 1
MAP_CONTEXT_SIZE = 4


def _require_rl() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        import gymnasium as gym
        import torch
        from gymnasium import spaces
        from sb3_contrib import RecurrentPPO
        from stable_baselines3.common.callbacks import BaseCallback
        from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
        from stable_baselines3.common.vec_env import SubprocVecEnv
    except ImportError as error:  # pragma: no cover - dependency error is the behavior.
        raise RuntimeError(
            "Parallel PPO requires the rl extras: python -m pip install -e '.[rl,apprentice]'"
        ) from error
    return gym, spaces, torch, RecurrentPPO, BaseCallback, (BaseFeaturesExtractor, SubprocVecEnv)


gym, spaces, torch, RecurrentPPO, BaseCallback, _rl_helpers = _require_rl()
BaseFeaturesExtractor, SubprocVecEnv = _rl_helpers
