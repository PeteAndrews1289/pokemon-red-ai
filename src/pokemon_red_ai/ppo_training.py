from __future__ import annotations

import gzip
import hashlib
import html
import json
import os
import random
import shutil
import threading
import time
import uuid
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pokemon_red_ai.apprentice_data import preprocess_apprentice_frame
from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    NOOP_ACTION,
    BlindAction,
    FrozenSnapshot,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    ExpeditionStore,
    MilestoneProgress,
    milestone_progress_for_state,
    referee_summary_for_state,
)
from pokemon_red_ai.frontier_learning import FullGameRewardTracker
from pokemon_red_ai.milestones import HALL_OF_FAME_KEY, MILESTONES
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import verify_rom
from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader

PPO_PROTOCOL = "parallel-recurrent-ppo-v4"
PPO_REWARD_PROTOCOL = "battle-local-credit-and-stagnation-v1"
PPO_MODES = frozenset({"pixels", "privileged"})
PRIVILEGED_STATE_SIZE = 24
ACTION_HISTORY_LENGTH = 3


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


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_json(value) + b"\n")
    os.replace(temporary, path)


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

    def __post_init__(self) -> None:
        if self.mode not in PPO_MODES:
            raise ValueError("PPO mode must be pixels or privileged")
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

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


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
    novelty_checkpoint_file: str | None = None


def _checkpoint_view(run_directory: Path) -> tuple[ExpeditionStore, dict[str, Any]]:
    checkpoint_path = run_directory / "checkpoint.json.gz"
    previous_path = run_directory / "checkpoint.previous.json.gz"
    error: Exception | None = None
    for path in (checkpoint_path, previous_path):
        try:
            checkpoint = _read_gzip_json(path)
            store_path = run_directory / "frontier"
            event_bytes = (store_path / "events.jsonl").read_bytes()
            offset = int(checkpoint["store_event_byte_offset"])
            if offset < 0 or offset > len(event_bytes):
                raise ValueError("Expedition checkpoint event boundary is invalid")
            store = ExpeditionStore.open_checkpoint_view(
                store_path,
                event_payload=event_bytes[:offset],
                cell_ids=checkpoint["store_cell_ids"],
            )
            return store, checkpoint
        except Exception as caught:  # The previous atomic checkpoint is the fallback.
            error = caught
    raise ValueError("No valid expedition checkpoint can seed PPO") from error


def freeze_verified_curriculum(expedition_run: Path, curriculum_directory: Path) -> dict[str, Any]:
    """Copy a stable, read-only curriculum out of a verified Archive-v2 checkpoint."""

    store, checkpoint = _checkpoint_view(expedition_run.expanduser().resolve())
    curriculum_directory.mkdir(parents=True, exist_ok=False)
    (curriculum_directory / "entries").mkdir()
    active_ids = [str(value) for value in checkpoint["archive"]["active_cell_ids"]]
    candidates = [store.cells[cell_id] for cell_id in active_ids]
    verified = [cell for cell in candidates if not store.verification_deficits(cell.cell_id)]
    if not verified:
        raise ValueError("Source expedition has no verified curriculum cells")

    selected: dict[tuple[int, int | None], Any] = {}
    for cell in verified:
        key = (cell.descriptor.milestone_index, cell.descriptor.map_id)
        current = selected.get(key)
        if current is None or (
            cell.discovered_global_action,
            -cell.depth_actions,
            cell.cell_id,
        ) > (
            current.discovered_global_action,
            -current.depth_actions,
            current.cell_id,
        ):
            selected[key] = cell
    roots = [cell for cell in verified if cell.parent_id is None]
    if len(roots) != 1:
        raise ValueError("PPO curriculum requires one verified power-on root")
    selected[(0, None)] = roots[0]

    entries: list[dict[str, Any]] = []
    for cell in sorted(
        selected.values(),
        key=lambda item: (item.descriptor.milestone_index, item.cell_id),
    ):
        index = cell.descriptor.milestone_index
        canonical_label = "Power-on" if index == 0 else MILESTONES[index - 1].label
        progress = MilestoneProgress(
            cell.descriptor.milestone_id,
            index,
            str(cell.referee_summary.get("milestone_label", canonical_label)),
        )
        payload = {
            "schema_version": 1,
            "entry_id": cell.cell_id,
            "source_cell_id": cell.cell_id,
            "progress": progress.public_dict(),
            "snapshot": store.read_snapshot(cell.snapshot_sha256).checkpoint_dict(),
            "lineage_actions": [
                action.public_dict() for action in store.lineage_actions(cell.cell_id)
            ],
        }
        path = curriculum_directory / "entries" / f"{cell.cell_id}.json.gz"
        _atomic_gzip_json(path, payload)
        entries.append(
            {
                "entry_id": cell.cell_id,
                "file": f"entries/{path.name}",
                "file_sha256": _sha256_file(path),
                "milestone_id": progress.key,
                "milestone_index": progress.index,
                "milestone_label": progress.label,
                "map_id": cell.descriptor.map_id,
                "depth_actions": cell.depth_actions,
                "source": "verified_expedition",
            }
        )
    best = max(entries, key=lambda item: int(item["milestone_index"]))
    manifest = {
        "schema_version": 1,
        "protocol": PPO_PROTOCOL,
        "source_run": expedition_run.name,
        "entries": entries,
        "best_milestone": {
            "key": best["milestone_id"],
            "index": best["milestone_index"],
            "label": best["milestone_label"],
        },
        "verified_promotions": 0,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _load_curriculum_manifest(directory: Path) -> dict[str, Any]:
    value = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if value.get("protocol") != PPO_PROTOCOL or not isinstance(value.get("entries"), list):
        raise ValueError("PPO curriculum manifest is invalid")
    return value


def _load_curriculum_entry(directory: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    path = directory / str(metadata["file"])
    if _sha256_file(path) != metadata["file_sha256"]:
        raise ValueError("PPO curriculum entry hash is invalid")
    return _read_gzip_json(path)


def _progress_from_value(value: Mapping[str, Any]) -> MilestoneProgress:
    return MilestoneProgress(str(value["key"]), int(value["index"]), str(value["label"]))


def _state_vector(state: PokemonRedState) -> np.ndarray:
    battle = np.zeros(4, dtype=np.float32)
    battle_index = {0: 0, 1: 1, 2: 2, 0xFF: 3}.get(state.battle_state or 0, 0)
    battle[battle_index] = 1
    badges = np.asarray(
        [float(bool((state.badge_bits or 0) & (1 << index))) for index in range(8)],
        dtype=np.float32,
    )
    base = np.asarray(
        [
            float(state.game_started),
            (state.map_id or 0) / 255,
            (state.player_x or 0) / 255,
            (state.player_y or 0) / 255,
            (state.party_count or 0) / 6,
        ],
        dtype=np.float32,
    )
    tail = np.asarray(
        [
            state.max_party_level / 100,
            state.pokedex_seen_count / 151,
            state.pokedex_owned_count / 151,
            state.event_flags_count / (319 * 8),
            len(state.bag_item_ids or ()) / 20,
            float(bool(state.got_pokedex)),
            len(set(state.party_species or ())) / 6,
        ],
        dtype=np.float32,
    )
    value = np.concatenate((base, battle, badges, tail))
    if value.shape != (PRIVILEGED_STATE_SIZE,):
        raise RuntimeError("Privileged PPO state vector changed without a protocol bump")
    return np.clip(value, 0, 1)


def _one_hot_action(action: int) -> np.ndarray:
    value = np.zeros(len(BLIND_ACTIONS), dtype=np.float32)
    if 0 <= action < len(BLIND_ACTIONS):
        value[action] = 1
    return value


def _action_history(actions: deque[int]) -> np.ndarray:
    return np.concatenate([_one_hot_action(action) for action in actions])


@dataclass(slots=True)
class VisualStagnationTracker:
    """Trainer-only loop watchdog; none of this state enters the actor observation."""

    cycle_window: int = 128
    cycle_unique_limit: int = 8
    hard_limit: int = 1_024
    _frames: deque[bytes] = field(default_factory=lambda: deque(maxlen=128))
    _seen_positions: set[tuple[int, int, int]] = field(default_factory=set)
    _best_progress: int = 0
    _max_experience: int = 0
    _max_events: int = 0
    _max_owned: int = 0
    _max_badges: int = 0
    _enemy_hp_floor: int | None = None
    _last_battle: int = 0
    _stagnant_actions: int = 0

    def reset(self, state: PokemonRedState, progress: MilestoneProgress) -> None:
        self._frames = deque(maxlen=self.cycle_window)
        self._seen_positions = set()
        if state.map_id is not None and state.player_x is not None and state.player_y is not None:
            self._seen_positions.add((state.map_id, state.player_x, state.player_y))
        self._best_progress = progress.index
        self._max_experience = state.total_party_experience
        self._max_events = state.event_flags_count
        self._max_owned = state.pokedex_owned_count
        self._max_badges = state.badge_count
        self._enemy_hp_floor = state.enemy_hp
        self._last_battle = state.battle_state or 0
        self._stagnant_actions = 0

    def observe(
        self,
        frame: np.ndarray,
        state: PokemonRedState,
        progress: MilestoneProgress,
    ) -> str | None:
        useful_progress = False
        position = (
            (state.map_id, state.player_x, state.player_y)
            if None not in (state.map_id, state.player_x, state.player_y)
            else None
        )
        if position is not None and position not in self._seen_positions:
            self._seen_positions.add(position)  # type: ignore[arg-type]
            useful_progress = True
        for current, name in (
            (progress.index, "_best_progress"),
            (state.total_party_experience, "_max_experience"),
            (state.event_flags_count, "_max_events"),
            (state.pokedex_owned_count, "_max_owned"),
            (state.badge_count, "_max_badges"),
        ):
            if current > getattr(self, name):
                setattr(self, name, current)
                useful_progress = True
        battle = state.battle_state or 0
        if battle in {1, 2}:
            if self._last_battle not in {1, 2}:
                self._enemy_hp_floor = state.enemy_hp
            elif (
                state.enemy_hp is not None
                and self._enemy_hp_floor is not None
                and state.enemy_hp < self._enemy_hp_floor
            ):
                self._enemy_hp_floor = state.enemy_hp
                useful_progress = True
        else:
            self._enemy_hp_floor = None
        self._last_battle = battle

        # Perceptual signatures ignore tiny animation changes but retain menus and cursor cycles.
        signature = hashlib.blake2b(
            (frame[::4, ::4] // 32).astype(np.uint8).tobytes(), digest_size=8
        ).digest()
        self._frames.append(signature)
        if useful_progress:
            self._stagnant_actions = 0
            self._frames.clear()
            self._frames.append(signature)
            return None
        self._stagnant_actions += 1
        if self._stagnant_actions >= self.hard_limit:
            return "progress_stagnation"
        if (
            len(self._frames) == self.cycle_window
            and len(set(self._frames)) <= self.cycle_unique_limit
        ):
            return "visual_cycle"
        return None


def _execute_action(emulator: PokemonRedEmulator, action_index: int) -> bool:
    action = BLIND_ACTIONS[action_index]
    if action == NOOP_ACTION:
        return emulator.tick(ACTION_HOLD_FRAMES + ACTION_RELEASE_FRAMES, render_last=True)
    return emulator.press(
        action,
        hold_frames=ACTION_HOLD_FRAMES,
        release_frames=ACTION_RELEASE_FRAMES,
    )


gym, spaces, torch, RecurrentPPO, BaseCallback, _rl_helpers = _require_rl()
BaseFeaturesExtractor, SubprocVecEnv = _rl_helpers


class PokemonPpoFeatures(BaseFeaturesExtractor):
    """Exact apprentice visual encoder plus disclosed action/RAM channels."""

    def __init__(self, observation_space: Any) -> None:
        privileged = "state" in observation_space.spaces
        feature_count = (
            256
            + ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS)
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

    def forward(self, observations: Mapping[str, Any]) -> Any:
        pixels = observations["pixels"].float()
        if pixels.detach().max() > 1:
            pixels = pixels.div(255)
        values = [self.pixel_encoder(pixels), observations["action_history"].float()]
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
        self.observation_space = spaces.Dict(observation)
        self.emulator = PokemonRedEmulator(Path(config.rom_path)).start()
        self.reader = PokemonRedStateReader(self.emulator)
        self.reward_tracker = (
            FullGameRewardTracker()
            if config.novelty_checkpoint_file is None
            else FullGameRewardTracker.from_checkpoint_dict(
                _read_gzip_json(self.run_directory / config.novelty_checkpoint_file)
            )
        )
        self.previous_frame = np.zeros((72, 80), dtype=np.uint8)
        self.recent_actions: deque[int] = deque(
            [-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH
        )
        self.loop_tracker = VisualStagnationTracker()
        self.steps = 0
        self.episode_number = 0
        self.episode_actions: list[int] = []
        self.start_entry: dict[str, Any] | None = None
        self.start_progress = MilestoneProgress("power_on", 0, "Power-on")
        self.episode_best = 0
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
        self.previous_frame = current
        return value

    def _choose_entry(self) -> dict[str, Any]:
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        entries = list(manifest["entries"])
        best_index = max(int(item["milestone_index"]) for item in entries)
        frontier = [item for item in entries if int(item["milestone_index"]) == best_index]
        metadata = self.rng.choice(frontier if self.rng.random() < 0.70 else entries)
        return _load_curriculum_entry(self.curriculum_directory, metadata)

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self.rng.seed(seed)
        self.start_entry = self._choose_entry()
        snapshot = FrozenSnapshot.from_checkpoint_dict(self.start_entry["snapshot"])
        self.emulator.load_state(snapshot.thaw())
        self.start_progress = _progress_from_value(self.start_entry["progress"])
        state = self.reader.read()
        self.reward_tracker.prime(state, self.start_progress)
        current = preprocess_apprentice_frame(self.emulator.screen_rgb())
        self.previous_frame = current
        self.recent_actions = deque(
            [-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH
        )
        self.steps = 0
        self.episode_actions = []
        self.episode_best = self.start_progress.index
        self.episode_number += 1
        self.loop_tracker.reset(state, self.start_progress)
        return self._observation(state), {
            "curriculum_entry": self.start_entry["entry_id"],
            "starting_milestone": self.start_progress.key,
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
        current = preprocess_apprentice_frame(self.emulator.screen_rgb())
        loop_reason = self.loop_tracker.observe(current, state, progress)
        reward = self.reward_tracker.score(
            state,
            progress,
            action_button=BLIND_ACTIONS[action_index],
            loop_detected=loop_reason is not None,
        )
        info: dict[str, Any] = {
            "rank": self.config.rank,
            "milestone_key": progress.key,
            "milestone_index": progress.index,
            "map_id": state.map_id,
            "x": state.player_x,
            "y": state.player_y,
            "reward_components": dict(reward.components),
        }
        if reward.battle_event is not None:
            info["battle_event"] = reward.battle_event
        if loop_reason is not None:
            info["loop_event"] = loop_reason
        if progress.index > self.episode_best:
            self.episode_best = progress.index
            manifest = _load_curriculum_manifest(self.curriculum_directory)
            global_best = int(manifest["best_milestone"]["index"])
            if progress.index > global_best:
                info["promotion_candidate"] = self._spool_candidate(progress)
        if self.steps % 128 == 0 or progress.index > self.start_progress.index:
            self._write_frame()
        truncated = (
            self.steps >= self.config.episode_actions
            or not alive
            or loop_reason is not None
        )
        if truncated:
            info["episode_end"] = True
            info["episode_end_reason"] = (
                loop_reason
                or (
                    "episode_action_limit"
                    if self.steps >= self.config.episode_actions
                    else "emulator_stop"
                )
            )
        return (
            self._observation(state, current),
            reward.total * self.config.reward_scale,
            False,
            truncated,
            info,
        )

    def close(self) -> None:
        self.emulator.close()


def make_ppo_environment(config: PpoEnvironmentConfig) -> PokemonRedPpoEnvironment:
    return PokemonRedPpoEnvironment(config)


def _load_action(value: Mapping[str, Any]) -> BlindAction:
    return BlindAction(
        str(value["button"]), int(value["hold_frames"]), int(value["release_frames"])
    )


def _replay_sequence(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
) -> tuple[FrozenSnapshot, MilestoneProgress, dict[str, Any], str]:
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        for action_index in actions:
            if not _execute_action(emulator, int(action_index)):
                raise RuntimeError("PPO promotion replay emulator stopped")
        state = PokemonRedStateReader(emulator).read()
        progress = milestone_progress_for_state(state, inherited=inherited)
        snapshot = FrozenSnapshot.freeze(emulator.save_state())
        return (
            snapshot,
            progress,
            referee_summary_for_state(state, progress),
            emulator.screen_sha256(),
        )


def verify_promotion_candidate(
    rom_path: Path,
    curriculum_directory: Path,
    candidate_path: Path,
    *,
    replay_passes: int,
) -> dict[str, Any]:
    candidate = _read_gzip_json(candidate_path)
    manifest = _load_curriculum_manifest(curriculum_directory)
    parent_metadata = next(
        (
            value
            for value in manifest["entries"]
            if value["entry_id"] == candidate["parent_entry_id"]
        ),
        None,
    )
    if parent_metadata is None:
        raise ValueError("PPO candidate parent is not in the curriculum")
    parent = _load_curriculum_entry(curriculum_directory, parent_metadata)
    parent_progress = _progress_from_value(parent["progress"])
    expected_progress = _progress_from_value(candidate["progress"])
    actions = [int(value) for value in candidate["actions"]]
    if not actions or any(not 0 <= value < len(BLIND_ACTIONS) for value in actions):
        raise ValueError("PPO promotion candidate actions are invalid")

    def matches(result: tuple[FrozenSnapshot, MilestoneProgress, dict[str, Any], str]) -> bool:
        snapshot, progress, summary, screen_sha256 = result
        return (
            snapshot.sha256 == candidate["terminal_snapshot_sha256"]
            and screen_sha256 == candidate["terminal_screen_sha256"]
            and progress == expected_progress
            and summary == candidate["terminal_referee_summary"]
        )

    parent_snapshot = FrozenSnapshot.from_checkpoint_dict(parent["snapshot"])
    if not matches(_replay_sequence(rom_path, parent_snapshot, actions, parent_progress)):
        raise ValueError("PPO candidate failed exact parent-edge replay")
    roots = [item for item in manifest["entries"] if int(item["milestone_index"]) == 0]
    if len(roots) != 1:
        raise ValueError("PPO curriculum has no unique power-on root")
    root = _load_curriculum_entry(curriculum_directory, roots[0])
    root_snapshot = FrozenSnapshot.from_checkpoint_dict(root["snapshot"])
    lineage: list[BlindAction] = [_load_action(value) for value in parent["lineage_actions"]]
    if any(
        action.hold_frames != ACTION_HOLD_FRAMES or action.release_frames != ACTION_RELEASE_FRAMES
        for action in lineage
    ):
        raise ValueError("PPO curriculum lineage uses a non-canonical action cadence")
    lineage_indices = [BLIND_ACTIONS.index(action.button) for action in lineage]
    full_actions = [*lineage_indices, *actions]
    root_progress = _progress_from_value(root["progress"])
    for _ in range(replay_passes):
        if not matches(_replay_sequence(rom_path, root_snapshot, full_actions, root_progress)):
            raise ValueError("PPO candidate failed fresh power-on replay")
    return {
        "candidate": candidate,
        "parent": parent,
        "full_actions": full_actions,
        "edge_replays": 1,
        "power_on_replays": replay_passes,
    }


def admit_verified_candidate(
    curriculum_directory: Path,
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = verification["candidate"]
    progress = _progress_from_value(candidate["progress"])
    manifest = _load_curriculum_manifest(curriculum_directory)
    if progress.index <= int(manifest["best_milestone"]["index"]):
        return manifest
    entry_id = str(candidate["candidate_id"])
    payload = {
        "schema_version": 1,
        "entry_id": entry_id,
        "source_cell_id": None,
        "progress": progress.public_dict(),
        "snapshot": candidate["terminal_snapshot"],
        "lineage_actions": [
            BlindAction(
                BLIND_ACTIONS[index], ACTION_HOLD_FRAMES, ACTION_RELEASE_FRAMES
            ).public_dict()
            for index in verification["full_actions"]
        ],
    }
    path = curriculum_directory / "entries" / f"{entry_id}.json.gz"
    _atomic_gzip_json(path, payload)
    manifest["entries"].append(
        {
            "entry_id": entry_id,
            "file": f"entries/{path.name}",
            "file_sha256": _sha256_file(path),
            "milestone_id": progress.key,
            "milestone_index": progress.index,
            "milestone_label": progress.label,
            "map_id": candidate["terminal_referee_summary"].get("map_id"),
            "depth_actions": len(verification["full_actions"]),
            "source": "ppo_verified_promotion",
        }
    )
    manifest["best_milestone"] = progress.public_dict()
    manifest["verified_promotions"] = int(manifest.get("verified_promotions", 0)) + 1
    manifest["updated_at"] = datetime.now(UTC).isoformat()
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _remap_warm_start_lstm_input(destination: Any, source: Any) -> None:
    """Put the one-action seed weights in Version 4's newest-action history slot."""

    pixel_features = 256
    action_features = len(BLIND_ACTIONS)
    expected_source = pixel_features + action_features
    expected_destination = pixel_features + ACTION_HISTORY_LENGTH * action_features
    if source.shape[1] != expected_source or destination.shape[1] < expected_destination:
        raise ValueError("Frontier learner LSTM input is incompatible with PPO Version 4")
    destination.zero_()
    destination[:, :pixel_features].copy_(source[:, :pixel_features])
    newest_action_start = pixel_features + (ACTION_HISTORY_LENGTH - 1) * action_features
    destination[:, newest_action_start : newest_action_start + action_features].copy_(
        source[:, pixel_features:]
    )


def _warm_start(model: Any, learner_path: Path, *, privileged: bool) -> dict[str, Any]:
    payload = torch.load(learner_path, map_location="cpu", weights_only=True)
    source = payload.get("model", payload)
    encoder_state = {
        key.removeprefix("encoder."): value
        for key, value in source.items()
        if key.startswith("encoder.")
    }
    extractors = {
        id(value): value
        for value in (
            model.policy.features_extractor,
            model.policy.pi_features_extractor,
            model.policy.vf_features_extractor,
        )
        if hasattr(value, "pixel_encoder")
    }
    for extractor in extractors.values():
        extractor.pixel_encoder.load_state_dict(encoder_state, strict=True)
    actor = model.policy.lstm_actor
    actor_state = actor.state_dict()
    source_recurrent = {
        key.removeprefix("recurrent."): value
        for key, value in source.items()
        if key.startswith("recurrent.")
    }
    for key, value in source_recurrent.items():
        if key == "weight_ih_l0" and actor_state[key].shape != value.shape:
            _remap_warm_start_lstm_input(actor_state[key], value)
        else:
            actor_state[key].copy_(value)
    actor.load_state_dict(actor_state)
    model.policy.action_net.load_state_dict(
        {
            "weight": source["policy_head.weight"],
            "bias": source["policy_head.bias"],
        }
    )
    return {
        "seed_file_sha256": _sha256_file(learner_path),
        "seed_updates": int(payload.get("updates", 0)),
        "seed_promotions": int(payload.get("promotions_learned", 0)),
        "privileged_actor": privileged,
        "privileged_lstm_columns_initialized_to_zero": privileged,
        "older_action_history_lstm_columns_initialized_to_zero": True,
        "seed_previous_action_mapped_to_newest_history_slot": True,
    }


def _render_dashboard(status: Mapping[str, Any]) -> str:
    best = status.get("best_milestone", {})
    mode = html.escape(str(status.get("mode", "unknown")))
    frame_cards = "".join(
        f'<figure><img src="env-{rank}.png?v={status.get("updated_at", "")}" '
        f'alt="Environment {rank}"/><figcaption>Environment {rank + 1}</figcaption></figure>'
        for rank in range(int(status.get("environments", 0)))
    )
    cards = "".join(
        f'<div class="card"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in (
            ("State", html.escape(str(status.get("state")))),
            ("Combined actions", f"{int(status.get('total_actions', 0)):,}"),
            (
                "Actions / second",
                f"{float(status.get('actions_per_second', 0)):,.1f}",
            ),
            (
                "Best verified milestone",
                html.escape(str(best.get("label", "Power-on"))),
            ),
            ("PPO updates", f"{int(status.get('ppo_updates', 0)):,}"),
            (
                "Verified promotions",
                f"{int(status.get('verified_promotions', 0)):,}",
            ),
            (
                "Unique map positions",
                f"{int(status.get('unique_positions', 0)):,}",
            ),
            ("Episodes", f"{int(status.get('episodes', 0)):,}"),
            (
                "Novelty memory",
                html.escape(str(status.get("novelty_scope", "unknown"))),
            ),
            (
                "Reward protocol",
                html.escape(str(status.get("reward_protocol", "unknown"))),
            ),
            (
                "Battle successes",
                f"{int(status.get('battle_events', {}).get('success', 0)):,}",
            ),
            (
                "No-progress battle exits",
                f"{int(status.get('battle_events', {}).get('ended_without_progress', 0)):,}",
            ),
            (
                "Opponent-damage credit",
                f"{float(status.get('reward_components', {}).get('opponent_damage', 0)):,.2f}",
            ),
            (
                "Visual loops cut short",
                f"{int(status.get('loop_events', {}).get('visual_cycle', 0)):,}",
            ),
            (
                "Long stagnations cut short",
                f"{int(status.get('loop_events', {}).get('progress_stagnation', 0)):,}",
            ),
        )
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"/>
<meta http-equiv="refresh" content="5"/><meta name="viewport" content="width=device-width"/>
<title>Parallel PPO · Pokémon Red</title><style>
body{{background:#10151f;color:#eef3e8;font:16px system-ui;margin:0;padding:24px}}
main{{max-width:1200px;margin:auto}}h1{{font-size:clamp(2rem,6vw,4.7rem);margin:.15em 0}}
.eyebrow{{color:#ffcc66;letter-spacing:.16em;font-weight:700}}.grid{{display:grid;
grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.card,figure{{background:#192232;border:1px solid #33445f;border-radius:14px;
padding:16px;margin:0}}strong{{display:block;font-size:1.7rem}}
span,figcaption{{color:#aebbd0}}img{{width:100%;image-rendering:pixelated;border-radius:8px}}
.frames{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:12px}}
@media(max-width:650px){{.frames{{grid-template-columns:1fr}}}}</style></head><body><main>
<div class="eyebrow">PARALLEL RECURRENT PPO · {mode.upper()}</div>
<h1>Failures now<br/>teach the policy.</h1>
<p>Several games collect experience for one shared recurrent policy. Trainer-only RAM computes
rewards and verifies promotions; the actor boundary is shown explicitly below.</p>
<section class="grid">{cards}</section><section class="frames">{frame_cards}</section>
<p><strong>Information boundary</strong> {html.escape(str(status.get("information_boundary")))}</p>
</main></body></html>"""


class PpoRunCallback(BaseCallback):
    def __init__(
        self,
        run_directory: Path,
        rom_path: Path,
        curriculum_directory: Path,
        config: ParallelPpoConfig,
        *,
        base_elapsed: float,
        started_at: str,
    ) -> None:
        super().__init__(verbose=0)
        self.run_directory = run_directory
        self.rom_path = rom_path
        self.curriculum_directory = curriculum_directory
        self.config = config
        self.base_elapsed = base_elapsed
        self.started_at = started_at
        self.clock_started = time.monotonic()
        self.last_status = 0.0
        self.last_narrative = 0.0
        self.last_checkpoint_step = 0
        self.episodes = 0
        self.reward_components: Counter[str] = Counter()
        self.battle_events: Counter[str] = Counter()
        self.loop_events: Counter[str] = Counter()
        self.episode_end_reasons: Counter[str] = Counter()
        self.positions: set[tuple[int, int, int]] = set()
        self.promotion_failures = 0
        self.stop_reason: str | None = None
        self.cached_run_bytes = 0
        self.cached_free_bytes = shutil.disk_usage(self.run_directory).free

    def elapsed(self) -> float:
        return self.base_elapsed + time.monotonic() - self.clock_started

    def _checkpoint(self) -> None:
        latest = self.run_directory / "ppo-latest.zip"
        previous = self.run_directory / "ppo-previous.zip"
        temporary = self.run_directory / "ppo-checkpoint.tmp.zip"
        novelty_files = self.training_env.env_method(
            "save_novelty_checkpoint", self.model.num_timesteps
        )
        self.model.save(temporary)
        if latest.exists():
            os.replace(latest, previous)
        os.replace(temporary, latest)
        _atomic_json(
            self.run_directory / "checkpoint.json",
            {
                "schema_version": 1,
                "protocol": PPO_PROTOCOL,
                "reward_protocol": PPO_REWARD_PROTOCOL,
                "model_file_sha256": _sha256_file(latest),
                "total_actions": self.model.num_timesteps,
                "elapsed_seconds": self.elapsed(),
                "config": self.config.public_dict(),
                "best_milestone": _load_curriculum_manifest(self.curriculum_directory)[
                    "best_milestone"
                ],
                "novelty_files": novelty_files,
                "resume_semantics": "model_optimizer_exact_environment_rollout_restarts",
            },
        )
        self.last_checkpoint_step = self.model.num_timesteps

    def _status(
        self,
        state: str,
        reason: str | None = None,
        *,
        refresh_disk: bool = True,
    ) -> dict[str, Any]:
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        elapsed = self.elapsed()
        rollout_size = self.config.rollout_steps * self.config.environments
        if refresh_disk:
            self.cached_run_bytes = sum(
                path.stat().st_size for path in self.run_directory.rglob("*") if path.is_file()
            )
            self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
        status = {
            "schema_version": 1,
            "protocol": PPO_PROTOCOL,
            "state": state,
            "stop_reason": reason,
            "mode": self.config.mode,
            "environments": self.config.environments,
            "started_at": self.started_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(elapsed, 3),
            "duration_seconds": self.config.duration_seconds,
            "total_actions": self.model.num_timesteps,
            "max_actions": self.config.max_actions,
            "actions_per_second": self.model.num_timesteps / max(elapsed, 0.001),
            "ppo_updates": self.model.num_timesteps // max(1, rollout_size),
            "episodes": self.episodes,
            "best_milestone": manifest["best_milestone"],
            "curriculum_entries": len(manifest["entries"]),
            "verified_promotions": manifest.get("verified_promotions", 0),
            "promotion_failures": self.promotion_failures,
            "unique_positions": len(self.positions),
            "reward_components": dict(sorted(self.reward_components.items())),
            "battle_events": dict(sorted(self.battle_events.items())),
            "loop_events": dict(sorted(self.loop_events.items())),
            "episode_end_reasons": dict(sorted(self.episode_end_reasons.items())),
            "reward_protocol": PPO_REWARD_PROTOCOL,
            "novelty_scope": "persistent per worker across episodes and resumes",
            "information_boundary": (
                "pixels + three recent actions; trainer-only RAM rewards and loop termination"
                if self.config.mode == "pixels"
                else "pixels + three recent actions + disclosed RAM state comparator"
            ),
            "resume_semantics": "exact model/optimizer; fresh environment rollouts",
            "dashboard_url": f"http://127.0.0.1:{self.config.dashboard_port}/index.html",
            "run_bytes": self.cached_run_bytes,
            "free_bytes": self.cached_free_bytes,
        }
        _atomic_json(self.run_directory / "status.json", status)
        (self.run_directory / "index.html").write_text(_render_dashboard(status), encoding="utf-8")
        return status

    def _narrative(
        self,
        event: str,
        *,
        state: str = "running",
        reason: str | None = None,
    ) -> None:
        status = self._status(state, reason, refresh_disk=False)
        path = self.run_directory / "NARRATIVE.md"
        first = not path.exists()
        with path.open("a", encoding="utf-8") as output:
            if first:
                output.write("# Parallel PPO learning chronicle\n\n")
            output.write(
                f"## {datetime.now(UTC).isoformat()} — {event}\n\n"
                f"- Best verified milestone: **{status['best_milestone']['label']}**\n"
                f"- Combined actions: {status['total_actions']:,}\n"
                f"- PPO updates: {status['ppo_updates']:,}\n"
                f"- Verified promotions: {status['verified_promotions']:,}\n"
                f"- Episodes: {status['episodes']:,}\n"
                f"- Unique map positions: {status['unique_positions']:,}\n\n"
                f"- Battle successes: {status['battle_events'].get('success', 0):,}\n"
                "- Battle exits without durable progress: "
                f"{status['battle_events'].get('ended_without_progress', 0):,}\n\n"
                f"- Opponent-damage credit: "
                f"{status['reward_components'].get('opponent_damage', 0):,.2f}\n"
                f"- Visual loops terminated: {status['loop_events'].get('visual_cycle', 0):,}\n"
                "- Long stagnations terminated: "
                f"{status['loop_events'].get('progress_stagnation', 0):,}\n\n"
            )

    def _handle_candidate(self, candidate_path: Path) -> None:
        try:
            current = _load_curriculum_manifest(self.curriculum_directory)
            candidate = _read_gzip_json(candidate_path)
            progress = _progress_from_value(candidate["progress"])
            if progress.index <= int(current["best_milestone"]["index"]):
                return
            verification = verify_promotion_candidate(
                self.rom_path,
                self.curriculum_directory,
                candidate_path,
                replay_passes=self.config.promotion_replays,
            )
            admit_verified_candidate(self.curriculum_directory, verification)
            source_png = candidate_path.with_suffix("").with_suffix(".png")
            if source_png.is_file():
                shutil.copy2(
                    source_png,
                    self.run_directory / "milestones" / f"{progress.index:03d}-{progress.key}.png",
                )
            self._checkpoint()
            self._narrative(f"verified {progress.label}")
        except Exception as error:
            self.promotion_failures += 1
            with (self.run_directory / "verification-failures.jsonl").open(
                "a", encoding="utf-8"
            ) as output:
                output.write(
                    json.dumps(
                        {
                            "recorded_at": datetime.now(UTC).isoformat(),
                            "candidate": candidate_path.name,
                            "error": f"{type(error).__name__}: {error}",
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        for info in infos:
            if not isinstance(info, Mapping):
                continue
            if info.get("episode_end"):
                self.episodes += 1
            map_id, x, y = info.get("map_id"), info.get("x"), info.get("y")
            if all(isinstance(value, int) for value in (map_id, x, y)):
                self.positions.add((map_id, x, y))
            self.reward_components.update(info.get("reward_components", {}))
            battle_event = info.get("battle_event")
            if isinstance(battle_event, str):
                self.battle_events[battle_event] += 1
            loop_event = info.get("loop_event")
            if isinstance(loop_event, str):
                self.loop_events[loop_event] += 1
            end_reason = info.get("episode_end_reason")
            if isinstance(end_reason, str):
                self.episode_end_reasons[end_reason] += 1
            candidate = info.get("promotion_candidate")
            if isinstance(candidate, str):
                self._handle_candidate(Path(candidate))

        elapsed = self.elapsed()
        if (self.run_directory / "STOP").exists():
            self.stop_reason = "stop_requested"
        elif elapsed >= self.config.duration_seconds:
            self.stop_reason = "duration_limit"
        elif self.model.num_timesteps >= self.config.max_actions:
            self.stop_reason = "action_limit"

        now = time.monotonic()
        if now - self.last_status >= self.config.status_seconds:
            status = self._status("running")
            if self.cached_free_bytes < self.config.min_free_bytes:
                self.stop_reason = "low_disk_space"
            elif self.cached_run_bytes >= self.config.max_output_bytes:
                self.stop_reason = "output_limit"
            elif status["best_milestone"]["key"] == HALL_OF_FAME_KEY:
                self.stop_reason = "hall_of_fame_verified"
            self.last_status = now
        if now - self.last_narrative >= self.config.narrative_seconds:
            self._narrative("scheduled observation")
            self.last_narrative = now
        if self.model.num_timesteps - self.last_checkpoint_step >= self.config.checkpoint_actions:
            self._checkpoint()
        return self.stop_reason is None


def _start_server(directory: Path, port: int) -> ThreadingHTTPServer | None:
    if port == 0:
        return None
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="ppo-dashboard").start()
    return server


def run_parallel_ppo(
    rom_path: Path,
    run_directory: Path,
    curriculum_source: Path,
    learner_path: Path,
    config: ParallelPpoConfig,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    verify_rom(rom_path)
    run_directory = run_directory.expanduser().resolve()
    if run_directory.exists() and not resume:
        raise ValueError("PPO output directory already exists")
    run_directory.mkdir(parents=True, exist_ok=resume)
    for name in ("candidate-spool", "milestones"):
        (run_directory / name).mkdir(exist_ok=True)
    curriculum_directory = run_directory / "curriculum"
    if not curriculum_directory.exists():
        freeze_verified_curriculum(curriculum_source, curriculum_directory)
    source = detect_source_provenance().public_dict()
    started_at = datetime.now(UTC).isoformat()
    base_elapsed = 0.0
    checkpoint_path = run_directory / "checkpoint.json"
    model_path = run_directory / "ppo-latest.zip"
    novelty_by_rank: dict[int, str] = {}
    if resume:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("protocol") != PPO_PROTOCOL:
            raise ValueError("PPO checkpoint uses a different protocol")
        if checkpoint.get("config") != config.public_dict():
            raise ValueError("PPO resume configuration does not match")
        if _sha256_file(model_path) != checkpoint.get("model_file_sha256"):
            raise ValueError("PPO model does not match its checkpoint")
        novelty_files = checkpoint.get("novelty_files")
        if not isinstance(novelty_files, list):
            raise ValueError("PPO checkpoint has no persistent novelty memory")
        for metadata in novelty_files:
            rank = int(metadata["rank"])
            filename = str(metadata["file"])
            if Path(filename).name != filename or rank in novelty_by_rank:
                raise ValueError("PPO novelty checkpoint metadata is invalid")
            path = run_directory / filename
            if _sha256_file(path) != metadata.get("file_sha256"):
                raise ValueError("PPO novelty memory does not match its checkpoint")
            novelty_by_rank[rank] = filename
        if set(novelty_by_rank) != set(range(config.environments)):
            raise ValueError("PPO novelty checkpoint does not cover every environment")
        previous_status = json.loads((run_directory / "status.json").read_text(encoding="utf-8"))
        if previous_status.get("stop_reason") in {
            "duration_limit",
            "action_limit",
            "hall_of_fame_verified",
        }:
            raise ValueError("PPO campaign already reached a terminal boundary")
        started_at = str(previous_status["started_at"])
        base_elapsed = float(checkpoint["elapsed_seconds"])
        (run_directory / "STOP").unlink(missing_ok=True)
    else:
        learner_copy = run_directory / "seed-frontier-learner.pt"
        shutil.copy2(learner_path, learner_copy)
        _atomic_json(
            run_directory / "manifest.json",
            {
                "schema_version": 1,
                "protocol": PPO_PROTOCOL,
                "config": config.public_dict(),
                "source": source,
                "actor_mode": config.mode,
                "human_demonstrations": [],
                "curriculum_source": curriculum_source.name,
                "novelty_scope": "persistent per worker across episodes and resumes",
                "reward_protocol": PPO_REWARD_PROTOCOL,
                "rom_path_recorded": False,
                "resume_semantics": "model_optimizer_exact_environment_rollout_restarts",
            },
        )
        learner_path = learner_copy

    env_fns = [
        partial(
            make_ppo_environment,
            PpoEnvironmentConfig(
                rom_path=str(rom_path),
                run_directory=str(run_directory),
                curriculum_directory=str(curriculum_directory),
                mode=config.mode,
                episode_actions=config.episode_actions,
                reward_scale=config.reward_scale,
                seed=config.seed,
                rank=rank,
                novelty_checkpoint_file=novelty_by_rank.get(rank),
            ),
        )
        for rank in range(config.environments)
    ]
    torch.set_num_threads(max(1, 4 // config.environments))
    vector = SubprocVecEnv(env_fns, start_method="forkserver")
    policy_kwargs = {
        "features_extractor_class": PokemonPpoFeatures,
        "features_extractor_kwargs": {},
        "lstm_hidden_size": 128,
        "n_lstm_layers": 1,
        "net_arch": [],
        "normalize_images": True,
    }
    if resume:
        model = RecurrentPPO.load(model_path, env=vector, device="cpu")
    else:
        model = RecurrentPPO(
            "MultiInputLstmPolicy",
            vector,
            learning_rate=config.learning_rate,
            n_steps=config.rollout_steps,
            batch_size=config.batch_size,
            n_epochs=config.epochs,
            gamma=config.gamma,
            ent_coef=config.entropy_coefficient,
            policy_kwargs=policy_kwargs,
            seed=config.seed,
            device="cpu",
            verbose=0,
            tensorboard_log=str(run_directory / "tensorboard"),
        )
        seed_info = _warm_start(model, learner_path, privileged=config.mode == "privileged")
        manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
        manifest["warm_start"] = seed_info
        _atomic_json(run_directory / "manifest.json", manifest)
    callback = PpoRunCallback(
        run_directory,
        rom_path,
        curriculum_directory,
        config,
        base_elapsed=base_elapsed,
        started_at=started_at,
    )
    server = _start_server(run_directory, config.dashboard_port)
    reason = "completed"
    try:
        remaining = max(1, config.max_actions - model.num_timesteps)
        model.learn(
            total_timesteps=remaining,
            callback=callback,
            reset_num_timesteps=not resume,
            progress_bar=False,
        )
        reason = callback.stop_reason or "action_limit"
    except KeyboardInterrupt:
        reason = "sigint"
    finally:
        callback.stop_reason = reason
        callback._checkpoint()
        status = callback._status("finished", reason)
        callback._narrative(f"campaign stopped: {reason}", state="finished", reason=reason)
        vector.close()
        if server is not None:
            server.shutdown()
            server.server_close()
    return status


def request_parallel_ppo_stop(run_directory: Path) -> None:
    run_directory = run_directory.expanduser().resolve()
    if not (run_directory / "status.json").is_file():
        raise ValueError("PPO status.json does not exist")
    (run_directory / "STOP").touch(exist_ok=True)


def show_parallel_ppo_status(run_directory: Path) -> dict[str, Any]:
    return json.loads(
        (run_directory.expanduser().resolve() / "status.json").read_text(encoding="utf-8")
    )
