"""Configuration dataclasses for parallel PPO runs and their environments."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from pokemon_red_ai.hindsight import (
    HindsightConfig,
)
from pokemon_red_ai.ppo.constants import (
    PPO_MODES,
    V8_CONFIG_FIELDS,
    V9_CONFIG_FIELDS,
    V10_CONFIG_FIELDS,
    V12_CONFIG_FIELDS,
)
from pokemon_red_ai.ppo.modes import (
    _is_distilled_student_mode,
    _is_self_taught_mode,
    _is_v12_mode,
    _uses_pixel_recovery,
    _uses_v9_practice,
)


@dataclass(frozen=True, slots=True)
class ParallelPpoConfig:
    mode: str = "pixels"
    duration_seconds: float = 28_800
    max_actions: int = 20_000_000
    seed: int = 20_260_752
    environments: int = 4
    episode_actions: int = 16_384
    rollout_steps: int = 256
    batch_size: int = 256
    epochs: int = 4
    learning_rate: float = 0.00025
    gamma: float = 0.997
    entropy_coefficient: float = 0.01
    reward_scale: float = 0.01
    promotion_replays: int = 3
    checkpoint_actions: int = 16_384
    status_seconds: float = 2
    narrative_seconds: float = 3_600
    dashboard_port: int = 8_773
    max_output_bytes: int = 100 * 1024**3
    min_free_bytes: int = 50 * 1024**3
    frontier_probability: float = 0.90
    consolidation: bool = False
    competence_window: int = 10
    competence_threshold: float = 0.80
    random_initialization: bool = False
    power_on_only: bool = False
    self_imitation_epochs: int = 2
    distillation_attempts: int = 32
    student_replay_interval: int = 4
    student_replay_epochs: int = 2
    student_burn_in: int = 32
    student_train_horizon: int = 64
    student_learning_rate: float = 0.0005
    frozen_exam_interval_actions: int = 16_384
    frozen_exam_attempts: int = 1
    frozen_exam_action_multiplier: float = 2.0
    student_practice_interval: int = 4
    student_practice_attempts: int = 2
    student_practice_window: int = 30
    student_practice_required: int = 27
    student_practice_confirmations: int = 2
    student_practice_retention: float = 0.25
    student_practice_rollout_multiplier: float = 2.0
    student_practice_rollout_slack: int = 16
    student_practice_reservoir: int = 32
    explorer_recovery_window_actions: int = 32
    explorer_recovery_blocked_threshold: int = 3
    explorer_recovery_escape_confirmations: int = 1
    explorer_recovery_ineffective_change_fraction: float = 0.02
    explorer_recovery_ineffective_mean_absolute_error: float = 2.0
    explorer_recovery_escape_change_fraction: float = 0.05
    explorer_recovery_escape_mean_absolute_error: float = 5.0
    explorer_recovery_blocked_penalty: float = 0.25
    explorer_recovery_escape_reward: float = 0.25
    explorer_recovery_expiration_penalty: float = 1.0
    hindsight_max_lessons: int = 16
    hindsight_min_actions: int = 8
    hindsight_max_actions: int = 128
    hindsight_min_changed_fraction: float = 0.03
    hindsight_min_mean_absolute_error: float = 3.0
    hindsight_epochs: int = 1
    hindsight_contrastive_weight: float = 0.25
    hindsight_contrastive_margin: float = 0.10
    terminal_evaluation_actions: int = 32_768

    def __post_init__(self) -> None:
        if self.mode not in PPO_MODES:
            raise ValueError("PPO mode must be pixels, assisted, privileged, or self_taught")
        if self.duration_seconds <= 0 or self.max_actions < 1:
            raise ValueError("PPO budgets must be positive")
        if not 1 <= self.environments <= 16:
            raise ValueError("PPO environment count must be between 1 and 16")
        if self.episode_actions < 64 or self.rollout_steps < 8:
            raise ValueError("PPO episode and rollout lengths are too small")
        rollout_size = self.rollout_steps * self.environments
        if self.batch_size < 8 or rollout_size % self.batch_size:
            raise ValueError("PPO batch size must divide environments × rollout steps")
        if self.epochs < 1 or self.learning_rate <= 0 or not 0 < self.gamma <= 1:
            raise ValueError("PPO optimizer settings are invalid")
        if self.entropy_coefficient < 0 or self.reward_scale <= 0:
            raise ValueError("PPO reward settings are invalid")
        if self.promotion_replays < 1 or self.checkpoint_actions < rollout_size:
            raise ValueError("PPO verification/checkpoint settings are invalid")
        if self.status_seconds <= 0 or self.narrative_seconds <= 0:
            raise ValueError("PPO reporting intervals must be positive")
        if not 0 <= self.dashboard_port <= 65_535:
            raise ValueError("PPO dashboard port is invalid")
        if self.max_output_bytes < 1024**2 or self.min_free_bytes < 0:
            raise ValueError("PPO disk limits are invalid")
        if not 0 <= self.frontier_probability <= 1:
            raise ValueError("PPO frontier probability must be between zero and one")
        if self.competence_window < 2 or not 0 < self.competence_threshold <= 1:
            raise ValueError("PPO competence gate settings are invalid")
        if self.self_imitation_epochs < 1:
            raise ValueError("PPO self-imitation epochs must be positive")
        if self.distillation_attempts < 0:
            raise ValueError("Trajectory distillation attempts cannot be negative")
        if self.student_replay_interval < 1 or self.student_replay_epochs < 1:
            raise ValueError("Student replay settings must be positive")
        if self.student_burn_in < 0 or self.student_train_horizon < 1:
            raise ValueError("Student recurrent sequence settings are invalid")
        if self.student_learning_rate <= 0:
            raise ValueError("Student learning rate must be positive")
        if self.frozen_exam_interval_actions < 1 or self.frozen_exam_attempts < 1:
            raise ValueError("Frozen Student exam settings must be positive")
        if _is_distilled_student_mode(self.mode) and self.frozen_exam_attempts != 1:
            raise ValueError(
                "Distilled-Student runs exactly one deterministic frozen attempt per checkpoint"
            )
        if self.frozen_exam_action_multiplier < 1:
            raise ValueError("Frozen Student exam multiplier must be at least one")
        if self.student_practice_interval < 1 or self.student_practice_attempts < 1:
            raise ValueError("Student practice cadence must be positive")
        if (
            self.student_practice_window < 2
            or not 1 <= self.student_practice_required <= self.student_practice_window
            or self.student_practice_confirmations < 1
        ):
            raise ValueError("Student practice requires a valid success window")
        if not 0.20 <= self.student_practice_retention <= 0.25:
            raise ValueError("Student practice retention must remain between 20% and 25%")
        if (
            self.student_practice_rollout_multiplier < 1
            or self.student_practice_rollout_slack < 0
            or self.student_practice_reservoir < 1
        ):
            raise ValueError("Student practice rollout and reservoir settings are invalid")
        if (
            self.explorer_recovery_window_actions < 1
            or self.explorer_recovery_blocked_threshold < 1
            or not 1
            <= self.explorer_recovery_escape_confirmations
            <= self.explorer_recovery_window_actions
            or not 0
            < self.explorer_recovery_ineffective_change_fraction
            <= self.explorer_recovery_escape_change_fraction
            <= 1
            or not 0
            <= self.explorer_recovery_ineffective_mean_absolute_error
            <= self.explorer_recovery_escape_mean_absolute_error
        ):
            raise ValueError("Explorer loop-recovery detection settings are invalid")
        if any(
            not np.isfinite(value) or value < 0
            for value in (
                self.explorer_recovery_blocked_penalty,
                self.explorer_recovery_escape_reward,
                self.explorer_recovery_expiration_penalty,
            )
        ):
            raise ValueError("Explorer loop-recovery rewards must be finite and non-negative")
        if self.explorer_recovery_escape_reward > self.explorer_recovery_blocked_penalty:
            raise ValueError("Explorer recovery escape credit cannot exceed its activation penalty")
        HindsightConfig(
            max_lessons=self.hindsight_max_lessons,
            min_actions=self.hindsight_min_actions,
            max_actions=self.hindsight_max_actions,
            min_changed_fraction=self.hindsight_min_changed_fraction,
            min_mean_absolute_error=self.hindsight_min_mean_absolute_error,
        )
        if self.hindsight_epochs < 1 or self.terminal_evaluation_actions < 1:
            raise ValueError("Hindsight epochs and terminal evaluation actions must be positive")
        if self.hindsight_contrastive_weight < 0 or self.hindsight_contrastive_margin < 0:
            raise ValueError("Hindsight contrastive settings must be non-negative")
        if _is_self_taught_mode(self.mode) and (
            not self.random_initialization or not self.power_on_only or self.consolidation
        ):
            raise ValueError(
                "Self-taught PPO requires random power-on initialization without consolidation"
            )

    def public_dict(self) -> dict[str, object]:
        value = asdict(self)
        if not _is_distilled_student_mode(self.mode):
            # Keep the serialized V7 configuration compatible with campaigns that
            # began before V8-only Student controls existed.
            for name in V8_CONFIG_FIELDS:
                value.pop(name)
        if not _uses_v9_practice(self.mode):
            for name in V9_CONFIG_FIELDS:
                value.pop(name)
        if not _uses_pixel_recovery(self.mode):
            for name in V10_CONFIG_FIELDS:
                value.pop(name)
        if not _is_v12_mode(self.mode):
            for name in V12_CONFIG_FIELDS:
                value.pop(name)
        return value


@dataclass(frozen=True, slots=True)
class PpoEnvironmentConfig:
    rom_path: str
    run_directory: str
    curriculum_directory: str
    mode: str
    episode_actions: int
    reward_scale: float
    seed: int
    rank: int
    frontier_probability: float
    consolidation: bool = False
    self_taught: bool = False
    novelty_checkpoint_file: str | None = None
    explorer_recovery_window_actions: int = 32
    explorer_recovery_blocked_threshold: int = 3
    explorer_recovery_escape_confirmations: int = 1
    explorer_recovery_ineffective_change_fraction: float = 0.02
    explorer_recovery_ineffective_mean_absolute_error: float = 2.0
    explorer_recovery_escape_change_fraction: float = 0.05
    explorer_recovery_escape_mean_absolute_error: float = 5.0
    explorer_recovery_blocked_penalty: float = 0.25
    explorer_recovery_escape_reward: float = 0.25
    explorer_recovery_expiration_penalty: float = 1.0
