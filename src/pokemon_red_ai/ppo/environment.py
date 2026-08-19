"""The Gymnasium environment and its feature extractor."""

from __future__ import annotations

import json
import os
import random
import uuid
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pokemon_red_ai.apprentice_data import preprocess_apprentice_frame
from pokemon_red_ai.blind import (
    BLIND_ACTIONS,
    FrozenSnapshot,
)
from pokemon_red_ai.consolidation import (
    BackwardConsolidation,
    choose_consolidation_entry,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    MilestoneProgress,
    milestone_progress_for_state,
    referee_summary_for_state,
)
from pokemon_red_ai.frontier_learning import FullGameRewardConfig, FullGameRewardTracker
from pokemon_red_ai.pixel_recovery import (
    PIXEL_LOOP_RECOVERY_PROTOCOL,
    PixelLoopRecovery,
    PixelLoopRecoveryConfig,
)
from pokemon_red_ai.ppo.artifacts import _atomic_gzip_json, _read_gzip_json, _sha256_file
from pokemon_red_ai.ppo.config import PpoEnvironmentConfig
from pokemon_red_ai.ppo.constants import (
    ACTION_HISTORY_LENGTH,
    GOAL_COUNT,
    MAP_CONTEXT_SIZE,
    MAP_MEMORY_FEATURES,
    MAP_MEMORY_SIZE,
    PRIVILEGED_STATE_SIZE,
    SKILL_COUNT,
    V10_RECOVERY_CYCLE_UNIQUE_LIMIT,
    V10_RECOVERY_CYCLE_WINDOW,
    V10_RECOVERY_STAGNATION_ACTIONS,
    BaseFeaturesExtractor,
    gym,
    spaces,
    torch,
)
from pokemon_red_ai.ppo.curriculum import (
    _load_curriculum_entry,
    _load_curriculum_manifest,
    _progress_from_value,
)
from pokemon_red_ai.ppo.modes import (
    _classify_episode_end,
    _is_distilled_student_mode,
    _is_self_taught_mode,
    _self_taught_reward_config,
    _uses_blind_watchdog,
    _uses_pixel_recovery,
)
from pokemon_red_ai.ppo.observations import (
    EpisodeMapMemory,
    VisualStagnationTracker,
    _action_history,
    _execute_action,
    _goal_observation,
    _map_context,
    _skill_observation,
    _state_vector,
)
from pokemon_red_ai.self_taught import (
    SelfTaughtSkillLibrary,
    choose_self_taught_episode,
)
from pokemon_red_ai.state import (
    PokemonRedState,
    PokemonRedStateReader,
)


class PokemonPpoFeatures(BaseFeaturesExtractor):
    """Exact apprentice visual encoder plus disclosed action/RAM channels."""

    def __init__(self, observation_space: Any) -> None:
        privileged = "state" in observation_space.spaces
        assisted = "map_memory" in observation_space.spaces
        self_taught = "target_pixels" in observation_space.spaces
        feature_count = (
            256
            + ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS)
            + (MAP_MEMORY_FEATURES + GOAL_COUNT + SKILL_COUNT + MAP_CONTEXT_SIZE if assisted else 0)
            + (128 if self_taught else 0)
            + (PRIVILEGED_STATE_SIZE if privileged else 0)
        )
        super().__init__(observation_space, features_dim=feature_count)
        self.pixel_encoder = torch.nn.Sequential(
            torch.nn.Conv2d(2, 16, kernel_size=8, stride=4),
            torch.nn.ReLU(),
            torch.nn.Conv2d(16, 32, kernel_size=4, stride=2),
            torch.nn.ReLU(),
            torch.nn.Conv2d(32, 32, kernel_size=3, stride=1),
            torch.nn.ReLU(),
            torch.nn.Flatten(),
            torch.nn.Linear(32 * 5 * 6, 256),
            torch.nn.ReLU(),
        )
        self.privileged = privileged
        self.assisted = assisted
        self.self_taught = self_taught
        if assisted:
            self.map_encoder = torch.nn.Sequential(
                torch.nn.Conv2d(2, 8, kernel_size=8, stride=4),
                torch.nn.ReLU(),
                torch.nn.Conv2d(8, 16, kernel_size=4, stride=2),
                torch.nn.ReLU(),
                torch.nn.Flatten(),
                torch.nn.Linear(16 * 6 * 6, MAP_MEMORY_FEATURES),
                torch.nn.ReLU(),
            )
        if self_taught:
            target_channels = int(observation_space.spaces["target_pixels"].shape[0])
            self.target_encoder = torch.nn.Sequential(
                torch.nn.Conv2d(target_channels, 8, kernel_size=8, stride=4),
                torch.nn.ReLU(),
                torch.nn.Conv2d(8, 16, kernel_size=4, stride=2),
                torch.nn.ReLU(),
                torch.nn.Flatten(),
                torch.nn.Linear(16 * 7 * 8, 128),
                torch.nn.ReLU(),
            )

    def forward(self, observations: Mapping[str, Any]) -> Any:
        pixels = observations["pixels"].float()
        if pixels.detach().max() > 1:
            pixels = pixels.div(255)
        values = [self.pixel_encoder(pixels), observations["action_history"].float()]
        if self.assisted:
            memory = observations["map_memory"].float()
            if memory.detach().max() > 1:
                memory = memory.div(255)
            values.extend(
                (
                    self.map_encoder(memory),
                    observations["goal"].float(),
                    observations["skill"].float(),
                    observations["map_context"].float(),
                )
            )
        if self.self_taught:
            target = observations["target_pixels"].float()
            if target.detach().max() > 1:
                target = target.div(255)
            values.append(self.target_encoder(target))
        if self.privileged:
            values.append(observations["state"].float())
        return torch.cat(values, dim=1)


class PokemonRedPpoEnvironment(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, config: PpoEnvironmentConfig) -> None:
        super().__init__()
        self.config = config
        self.run_directory = Path(config.run_directory)
        self.curriculum_directory = Path(config.curriculum_directory)
        self.action_space = spaces.Discrete(len(BLIND_ACTIONS))
        observation: dict[str, Any] = {
            "pixels": spaces.Box(0, 255, shape=(2, 72, 80), dtype=np.uint8),
            "action_history": spaces.Box(
                0,
                1,
                shape=(ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS),),
                dtype=np.float32,
            ),
        }
        if config.mode == "privileged":
            observation["state"] = spaces.Box(
                0, 1, shape=(PRIVILEGED_STATE_SIZE,), dtype=np.float32
            )
        if config.mode == "assisted":
            observation.update(
                {
                    "map_memory": spaces.Box(
                        0,
                        255,
                        shape=(2, MAP_MEMORY_SIZE, MAP_MEMORY_SIZE),
                        dtype=np.uint8,
                    ),
                    "goal": spaces.Box(0, 1, shape=(GOAL_COUNT,), dtype=np.float32),
                    "skill": spaces.Box(0, 1, shape=(SKILL_COUNT,), dtype=np.float32),
                    "map_context": spaces.Box(0, 1, shape=(MAP_CONTEXT_SIZE,), dtype=np.float32),
                }
            )
        if _is_self_taught_mode(config.mode):
            target_channels = 3 if _is_distilled_student_mode(config.mode) else 1
            observation["target_pixels"] = spaces.Box(
                0, 255, shape=(target_channels, 72, 80), dtype=np.uint8
            )
        self.observation_space = spaces.Dict(observation)
        self.emulator = PokemonRedEmulator(Path(config.rom_path)).start()
        self.reader = PokemonRedStateReader(self.emulator)
        self.reward_tracker = (
            FullGameRewardTracker(
                config=(
                    _self_taught_reward_config() if config.self_taught else FullGameRewardConfig()
                )
            )
            if config.novelty_checkpoint_file is None
            else FullGameRewardTracker.from_checkpoint_dict(
                _read_gzip_json(self.run_directory / config.novelty_checkpoint_file)
            )
        )
        self.previous_frame = np.zeros((72, 80), dtype=np.uint8)
        self.recent_actions: deque[int] = deque(
            [-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH
        )
        # V8+ blind learners must not receive authored quest information through episode
        # length. V7 keeps its historical behavior for denominator compatibility.
        self.loop_tracker = VisualStagnationTracker(
            use_authored_guidance=not _uses_blind_watchdog(config.mode)
        )
        self.explorer_loop_recovery = (
            PixelLoopRecovery(
                PixelLoopRecoveryConfig(
                    action_count=len(BLIND_ACTIONS),
                    cycle_window=V10_RECOVERY_CYCLE_WINDOW,
                    cycle_unique_limit=V10_RECOVERY_CYCLE_UNIQUE_LIMIT,
                    recovery_actions=config.explorer_recovery_window_actions,
                    blocked_repeat_threshold=config.explorer_recovery_blocked_threshold,
                    stagnation_threshold=V10_RECOVERY_STAGNATION_ACTIONS,
                    escape_confirmations=config.explorer_recovery_escape_confirmations,
                    ineffective_change_fraction=(
                        config.explorer_recovery_ineffective_change_fraction
                    ),
                    ineffective_mean_absolute_error=(
                        config.explorer_recovery_ineffective_mean_absolute_error
                    ),
                    escape_change_fraction=config.explorer_recovery_escape_change_fraction,
                    escape_mean_absolute_error=(
                        config.explorer_recovery_escape_mean_absolute_error
                    ),
                )
            )
            if _uses_pixel_recovery(config.mode)
            else None
        )
        self.map_memory = EpisodeMapMemory()
        self.steps = 0
        self.episode_number = 0
        self.episode_actions: list[int] = []
        self.start_entry: dict[str, Any] | None = None
        self.start_progress = MilestoneProgress("power_on", 0, "Power-on")
        self.current_progress = self.start_progress
        self.episode_best = 0
        self.start_mode = "frontier"
        self.episode_target_index = 0
        self.self_skill_id: str | None = None
        self.target_frame = np.zeros(
            (3 if _is_distilled_student_mode(config.mode) else 1, 72, 80),
            dtype=np.uint8,
        )
        self.rng = random.Random(config.seed + config.rank)

    def _observation(
        self,
        state: PokemonRedState | None = None,
        current: np.ndarray | None = None,
    ) -> dict[str, np.ndarray]:
        if current is None:
            current = preprocess_apprentice_frame(self.emulator.screen_rgb())
        value: dict[str, np.ndarray] = {
            "pixels": np.stack((self.previous_frame, current)),
            "action_history": _action_history(self.recent_actions),
        }
        if self.config.mode == "privileged":
            value["state"] = _state_vector(state or self.reader.read())
        if self.config.mode == "assisted":
            observed_state = state or self.reader.read()
            self.map_memory.observe(observed_state)
            value.update(
                {
                    "map_memory": self.map_memory.observation(observed_state),
                    "goal": _goal_observation(self.current_progress),
                    "skill": _skill_observation(observed_state, self.current_progress),
                    "map_context": _map_context(
                        observed_state,
                        self.current_progress,
                        self.reward_tracker.seen_warps,
                    ),
                }
            )
        if self.config.self_taught:
            value["target_pixels"] = self.target_frame
        self.previous_frame = current
        return value

    def _choose_entry(self) -> tuple[dict[str, Any], str, int, str | None, str | None]:
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        entries = list(manifest["entries"])
        best_index = max(int(item["milestone_index"]) for item in entries)
        if _is_distilled_student_mode(self.config.mode):
            metadata = self.rng.choice(
                [item for item in entries if int(item["milestone_index"]) == best_index]
            )
            return (
                _load_curriculum_entry(self.curriculum_directory, metadata),
                "v8_explorer",
                best_index,
                None,
                None,
            )
        if self.config.self_taught:
            library = SelfTaughtSkillLibrary.from_dict(
                json.loads((self.run_directory / "self-skills.json").read_text(encoding="utf-8"))
            )
            metadata, mode, target, skill_id, target_frame = choose_self_taught_episode(
                entries,
                library,
                self.rng,
                frontier_probability=self.config.frontier_probability,
            )
            return (
                _load_curriculum_entry(self.curriculum_directory, metadata),
                mode,
                target,
                skill_id,
                target_frame,
            )
        if self.config.consolidation:
            state = BackwardConsolidation.from_dict(
                json.loads((self.run_directory / "consolidation.json").read_text(encoding="utf-8"))
            )
            metadata, mode, target = choose_consolidation_entry(
                entries,
                state,
                self.rng,
                frontier_probability=self.config.frontier_probability,
            )
            return (
                _load_curriculum_entry(self.curriculum_directory, metadata),
                mode,
                target,
                None,
                None,
            )
        frontier = [item for item in entries if int(item["milestone_index"]) == best_index]
        metadata = self.rng.choice(
            frontier if self.rng.random() < self.config.frontier_probability else entries
        )
        return (
            _load_curriculum_entry(self.curriculum_directory, metadata),
            "legacy",
            best_index,
            None,
            None,
        )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self.rng.seed(seed)
        (
            self.start_entry,
            self.start_mode,
            self.episode_target_index,
            self.self_skill_id,
            target_frame_file,
        ) = self._choose_entry()
        if target_frame_file is not None:
            frame = np.asarray(
                Image.open(self.run_directory / target_frame_file).convert("L").resize((80, 72))
            )
            self.target_frame = frame[None, :, :]
        else:
            self.target_frame = np.zeros(
                (3 if _is_distilled_student_mode(self.config.mode) else 1, 72, 80),
                dtype=np.uint8,
            )
        snapshot = FrozenSnapshot.from_checkpoint_dict(self.start_entry["snapshot"])
        self.emulator.load_state(snapshot.thaw())
        self.start_progress = _progress_from_value(self.start_entry["progress"])
        self.current_progress = self.start_progress
        state = self.reader.read()
        self.reward_tracker.prime(state, self.start_progress)
        current = preprocess_apprentice_frame(self.emulator.screen_rgb())
        self.previous_frame = current
        self.recent_actions = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
        self.steps = 0
        self.episode_actions = []
        self.episode_best = self.start_progress.index
        self.episode_number += 1
        self.loop_tracker.reset(state, self.start_progress)
        if self.explorer_loop_recovery is not None:
            self.explorer_loop_recovery.reset(current)
        self.map_memory.reset(state)
        return self._observation(state), {
            "curriculum_entry": self.start_entry["entry_id"],
            "starting_milestone": self.start_progress.key,
            "starting_milestone_index": self.start_progress.index,
            "start_mode": self.start_mode,
            "consolidation_target_index": self.episode_target_index,
            "self_skill_id": self.self_skill_id,
        }

    def _write_frame(self) -> None:
        path = self.run_directory / f"env-{self.config.rank}.png"
        temporary = path.with_suffix(".png.tmp")
        Image.fromarray(self.emulator.screen_rgb()).save(temporary, format="PNG")
        os.replace(temporary, path)

    def save_novelty_checkpoint(self, generation: int) -> dict[str, Any]:
        """Persist worker-lifetime novelty without sharing it with the actor."""

        filename = f"novelty-env-{self.config.rank}-{generation:012d}.json.gz"
        path = self.run_directory / filename
        _atomic_gzip_json(path, self.reward_tracker.checkpoint_dict())
        return {
            "rank": self.config.rank,
            "file": filename,
            "file_sha256": _sha256_file(path),
            "seen_maps": len(self.reward_tracker.seen_maps),
            "seen_positions": len(self.reward_tracker.seen_positions),
            "seen_warps": len(self.reward_tracker.seen_warps),
            "max_party_experience": self.reward_tracker.max_party_experience,
            "best_milestone_index": self.reward_tracker.best_milestone_index,
        }

    def _spool_candidate(self, progress: MilestoneProgress) -> str:
        if self.start_entry is None:
            raise RuntimeError("PPO episode has no curriculum parent")
        candidate_id = uuid.uuid4().hex
        snapshot = FrozenSnapshot.freeze(self.emulator.save_state())
        state = self.reader.read()
        payload = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "rank": self.config.rank,
            "parent_entry_id": self.start_entry["entry_id"],
            "progress": progress.public_dict(),
            "actions": self.episode_actions,
            "terminal_snapshot": snapshot.checkpoint_dict(),
            "terminal_snapshot_sha256": snapshot.sha256,
            "terminal_screen_sha256": self.emulator.screen_sha256(),
            "terminal_referee_summary": referee_summary_for_state(state, progress),
        }
        path = self.run_directory / "candidate-spool" / f"{candidate_id}.json.gz"
        _atomic_gzip_json(path, payload)
        Image.fromarray(self.emulator.screen_rgb()).save(
            self.run_directory / "candidate-spool" / f"{candidate_id}.png"
        )
        return str(path)

    def step(self, action: int) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        action_index = int(action)
        alive = _execute_action(self.emulator, action_index)
        self.steps += 1
        self.episode_actions.append(action_index)
        self.recent_actions.append(action_index)
        state = self.reader.read()
        progress = milestone_progress_for_state(state, inherited=self.start_progress)
        self.current_progress = progress
        current = preprocess_apprentice_frame(self.emulator.screen_rgb())
        recovery_step = (
            self.explorer_loop_recovery.observe(action_index, current)
            if self.explorer_loop_recovery is not None
            else None
        )
        loop_reason = self.loop_tracker.observe(
            current,
            state,
            progress,
            perceptual_activity=bool(
                recovery_step is not None and recovery_step.perceptually_changed
            ),
        )
        recovery_event = None if recovery_step is None else recovery_step.recovery_event
        recovery_trigger = None if recovery_step is None else recovery_step.recovery_trigger
        watchdog_loop_reason = loop_reason
        if recovery_event in {"started", "escaped", "context_changed"}:
            # A bounded lesson opened or resolved. Reset only the trainer's watchdog clock; the
            # emulator, recurrent state, and policy-selected action stream continue uninterrupted.
            self.loop_tracker.reset(state, progress)
            loop_reason = None
        terminal_loop_reason = loop_reason
        if recovery_event == "expired":
            terminal_loop_reason = "visual_recovery_expired"
        loop_triggered = watchdog_loop_reason is not None or (
            recovery_event == "started"
            and recovery_trigger in {"visual_cycle", "progress_stagnation"}
        )
        reward = self.reward_tracker.score(
            state,
            progress,
            action_button=BLIND_ACTIONS[action_index],
            loop_detected=loop_triggered,
        )
        reward_components = dict(reward.components)
        recovery_reward = 0.0
        if recovery_step is not None and recovery_step.repeated_blocked_attempt:
            recovery_reward -= self.config.explorer_recovery_blocked_penalty
            reward_components[
                "pixel_blocked_repeat"
            ] = -self.config.explorer_recovery_blocked_penalty
        if recovery_event == "escaped":
            recovery_reward += self.config.explorer_recovery_escape_reward
            reward_components["pixel_recovery_escape"] = self.config.explorer_recovery_escape_reward
        elif recovery_event == "expired":
            recovery_reward -= self.config.explorer_recovery_expiration_penalty
            reward_components[
                "pixel_recovery_expiration"
            ] = -self.config.explorer_recovery_expiration_penalty
        info: dict[str, Any] = {
            "rank": self.config.rank,
            "milestone_key": progress.key,
            "milestone_index": progress.index,
            "starting_milestone_index": self.start_progress.index,
            "start_mode": self.start_mode,
            "consolidation_target_index": self.episode_target_index,
            "self_skill_id": self.self_skill_id,
            "map_id": state.map_id,
            "x": state.player_x,
            "y": state.player_y,
            "reward_components": reward_components,
        }
        if reward.battle_event is not None:
            info["battle_event"] = reward.battle_event
        if watchdog_loop_reason is not None:
            info["loop_event"] = watchdog_loop_reason
        elif recovery_event == "started" and recovery_trigger in {
            "visual_cycle",
            "progress_stagnation",
        }:
            info["loop_event"] = recovery_trigger
        if recovery_step is not None:
            info["explorer_loop_recovery"] = {
                "protocol": PIXEL_LOOP_RECOVERY_PROTOCOL,
                "active": self.explorer_loop_recovery.active,
                "remaining_actions": self.explorer_loop_recovery.remaining_actions,
                "event": recovery_event,
                "trigger": recovery_trigger,
                "recovery_action": recovery_step.recovery_action,
                "blocked_direction_attempt": recovery_step.blocked_direction_attempt,
                "repeated_blocked_attempt": recovery_step.repeated_blocked_attempt,
                "changed_fraction": recovery_step.changed_fraction,
                "mean_absolute_error": recovery_step.mean_absolute_error,
                "submitted_action": recovery_step.submitted_action,
                "executed_action": recovery_step.executed_action,
            }
        if progress.index > self.episode_best:
            self.episode_best = progress.index
            manifest = _load_curriculum_manifest(self.curriculum_directory)
            global_best = int(manifest["best_milestone"]["index"])
            if progress.index > global_best:
                info["promotion_candidate"] = self._spool_candidate(progress)
        if self.steps % 128 == 0 or progress.index > self.start_progress.index:
            self._write_frame()
        terminated, truncated, episode_end_reason = _classify_episode_end(
            self.config.mode,
            alive=alive,
            loop_reason=terminal_loop_reason,
            action_limit=self.steps >= self.config.episode_actions,
        )
        if terminated or truncated:
            info["episode_end"] = True
            info["episode_best_index"] = self.episode_best
            info["consolidation_success"] = self.episode_best >= self.episode_target_index
            info["episode_end_reason"] = episode_end_reason
        return (
            self._observation(state, current),
            (reward.total + recovery_reward) * self.config.reward_scale,
            terminated,
            truncated,
            info,
        )

    def close(self) -> None:
        self.emulator.close()


def make_ppo_environment(config: PpoEnvironmentConfig) -> PokemonRedPpoEnvironment:
    return PokemonRedPpoEnvironment(config)
