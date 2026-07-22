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
from collections.abc import Callable, Mapping, Sequence
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
from pokemon_red_ai.consolidation import (
    BackwardConsolidation,
    choose_consolidation_entry,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    ExpeditionStore,
    MilestoneProgress,
    milestone_progress_for_state,
    referee_summary_for_state,
)
from pokemon_red_ai.frontier_learning import FullGameRewardConfig, FullGameRewardTracker
from pokemon_red_ai.hindsight import (
    HINDSIGHT_PROTOCOL,
    HindsightConfig,
    extract_hindsight_lessons,
)
from pokemon_red_ai.milestones import HALL_OF_FAME_KEY, MILESTONE_BY_KEY, MILESTONES
from pokemon_red_ai.pixel_recovery import (
    PIXEL_LOOP_RECOVERY_PROTOCOL,
    RECOVERY_TRIGGERS,
    PixelLoopRecovery,
    PixelLoopRecoveryConfig,
)
from pokemon_red_ai.ppo_dashboard import render_ppo_dashboard
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.quest_navigation import route_guidance
from pokemon_red_ai.rom import verify_rom
from pokemon_red_ai.self_taught import (
    SELF_GENERATED_COMPOSITION_PROTOCOL,
    SELF_GENERATED_REPLAY_SHARD_PROTOCOL,
    SelfTaughtSkillLibrary,
    choose_self_taught_episode,
    choose_v8_self_taught_episode,
)
from pokemon_red_ai.skill_graph import (
    ObservedMilestoneFirstHit,
    StableStateIdentity,
    normalize_first_hit_replay,
)
from pokemon_red_ai.state import (
    MAX_BAG_ITEMS,
    PARTY_LENGTH,
    PARTY_MON_STRUCT_LENGTH,
    PokemonRedState,
    PokemonRedStateReader,
    RamAddress,
)
from pokemon_red_ai.student_practice import (
    ReversePracticeConfig,
    StudentPracticeLedger,
    SuccessfulRolloutMetadata,
)
from pokemon_red_ai.student_training import (
    BalancedSkillReplay,
    SelfGeneratedSkillDataset,
    SequenceAwareStudentTrainer,
    SequenceTrainingConfig,
    load_self_generated_datasets,
)
from pokemon_red_ai.trajectory_distillation import (
    DistillationConfig,
    ReplayEvidence,
    VerifiedSelfTrajectory,
    distill_self_generated_trajectory,
)

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


def _random_state_to_json(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_random_state_to_json(item) for item in value]
    return value


def _random_state_from_json(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_random_state_from_json(item) for item in value)
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_reproducible_v8_source(source: Mapping[str, Any]) -> None:
    """Refuse a V8 campaign whose executable source cannot be named exactly."""

    if source.get("git_commit") == "unknown" or source.get("worktree_dirty") is not False:
        raise ValueError("V8 requires a clean Git commit so checkpoints bind exact source")


def _validate_checkpoint_identity(
    checkpoint: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    rom: Mapping[str, Any],
    required: bool,
) -> None:
    if not required:
        return
    recorded_source = checkpoint.get("source")
    recorded_rom = checkpoint.get("rom")
    if recorded_source is None or recorded_rom is None:
        raise ValueError("V8 checkpoint has no bound source and ROM identity")
    if recorded_source != source:
        raise ValueError("PPO checkpoint source identity does not match this checkout")
    if recorded_rom != rom:
        raise ValueError("PPO checkpoint ROM identity does not match the verified ROM")


def _resolve_checkpoint_artifact(
    run_directory: Path,
    *,
    latest_name: str,
    previous_name: str,
    expected_sha256: object,
) -> Path:
    """Resolve and re-promote the generation named by the atomic JSON checkpoint."""

    for index, name in enumerate((latest_name, previous_name)):
        path = run_directory / name
        if path.is_file() and _sha256_file(path) == expected_sha256:
            if index == 0:
                return path
            latest = run_directory / latest_name
            temporary = latest.with_suffix(latest.suffix + ".recovered.tmp")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, temporary)
            os.replace(temporary, latest)
            if _sha256_file(latest) != expected_sha256:
                raise ValueError(f"Recovered {latest_name} failed its checkpoint hash")
            return latest
    raise ValueError(f"Neither {latest_name} nor its previous generation matches")


def _snapshot_v7_denominator(run_directory: Path) -> dict[str, Any]:
    """Lock one read-only V7 checkpoint for honest V8 dashboard comparison."""

    source = run_directory.expanduser().resolve()
    if not source.is_dir():
        raise ValueError("V7 denominator run directory does not exist")
    manifest_path = source / "manifest.json"
    checkpoint_path = source / "checkpoint.json"
    status_path = source / "status.json"
    if not manifest_path.is_file() or not checkpoint_path.is_file():
        raise ValueError("V7 denominator has no complete manifest and checkpoint")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol") != PPO_PROTOCOL or manifest.get("actor_mode") != "self_taught":
        raise ValueError("Denominator must be a Version-7 self-taught run")

    # The denominator may still be running. Its checkpoint and model generations
    # rotate atomically but separately, so retry the read-only pairing if one
    # rotation crosses this snapshot operation.
    for _attempt in range(3):
        checkpoint_bytes = checkpoint_path.read_bytes()
        checkpoint = json.loads(checkpoint_bytes)
        expected = checkpoint.get("model_file_sha256")
        checkpoint_config = checkpoint.get("config")
        if (
            checkpoint.get("protocol") != PPO_PROTOCOL
            or not isinstance(checkpoint_config, Mapping)
            or checkpoint_config.get("mode") != "self_taught"
            or not isinstance(expected, str)
            or len(expected) != 64
        ):
            raise ValueError("V7 denominator checkpoint identity is invalid")
        matching_model = next(
            (
                candidate
                for candidate in (source / "ppo-latest.zip", source / "ppo-previous.zip")
                if candidate.is_file() and _sha256_file(candidate) == expected
            ),
            None,
        )
        if matching_model is None:
            continue
        best = checkpoint.get("best_milestone")
        if not isinstance(best, Mapping):
            raise ValueError("V7 denominator checkpoint has no milestone evidence")
        status = (
            json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
        )
        return {
            "locked": True,
            "protocol": PPO_PROTOCOL,
            "run_id": source.name,
            "total_actions": int(checkpoint["total_actions"]),
            "best_index": int(best["index"]),
            "best_label": str(best["label"]),
            "checkpoint_sha256": expected,
            "checkpoint_json_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
            "source_state_at_lock": str(status.get("state", "unknown")),
            "source_updated_at": status.get("updated_at"),
            "locked_at": datetime.now(UTC).isoformat(),
            "source_path_recorded": False,
        }
    raise ValueError("V7 denominator model rotated before a checkpoint pair could be locked")


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_json(value) + b"\n")
    os.replace(temporary, path)


def _ensure_run_manifest_identity(
    path: Path,
    *,
    source: Mapping[str, Any],
    rom: Mapping[str, Any],
) -> dict[str, Any]:
    """Backfill identity for pre-V8 manifests without rewriting existing provenance."""

    value = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    if "source" not in value:
        value["source"] = dict(source)
        changed = True
    if "rom" not in value:
        value["rom"] = dict(rom)
        changed = True
    if changed:
        _atomic_json(path, value)
    return value


def _atomic_torch_checkpoint(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as output:
        torch.save(value, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _validate_hashed_run_artifact(
    run_directory: Path,
    relative_value: object,
    expected_sha256: object,
    *,
    label: str,
) -> Path:
    """Resolve one ledger artifact inside the run and verify its sealed identity."""

    relative = Path(str(relative_value))
    expected = str(expected_sha256)
    if relative.is_absolute() or ".." in relative.parts or not relative.name:
        raise ValueError(f"{label} path is invalid")
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ValueError(f"{label} hash is invalid")
    root = run_directory.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or _sha256_file(path) != expected:
        raise ValueError(f"{label} failed its hash")
    return path


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
        if self.hindsight_epochs < 1:
            raise ValueError("Hindsight training epochs must be positive")
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


def _canonical_progress(key: str) -> MilestoneProgress:
    if key == "power_on":
        return MilestoneProgress("power_on", 0, "Power-on")
    milestone = MILESTONE_BY_KEY.get(key)
    if milestone is None:
        raise ValueError(f"Curriculum uses unknown milestone {key!r}")
    return MilestoneProgress(milestone.key, milestone.ordinal + 1, milestone.label)


def _milestone_label(index: int) -> str:
    if index == 0:
        return "Power-on"
    if not 0 < index <= len(MILESTONES):
        raise ValueError("Milestone index is outside the canonical catalogue")
    return MILESTONES[index - 1].label


def _import_verified_ppo_curriculum(
    source_run: Path,
    curriculum_directory: Path,
    *,
    target_protocol: str = PPO_PROTOCOL,
) -> dict[str, Any]:
    """Import only replay-admitted curriculum from a cleanly finished PPO run."""

    source_manifest_path = source_run / "curriculum" / "manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_protocol = source_manifest.get("protocol")
    if source_protocol not in {
        "parallel-recurrent-ppo-v4",
        "parallel-recurrent-ppo-v5",
        "parallel-recurrent-ppo-v5.1",
        "parallel-recurrent-ppo-v5.2",
        "parallel-recurrent-ppo-v6",
        "parallel-recurrent-ppo-v7",
        "parallel-recurrent-ppo-v8",
        "parallel-recurrent-ppo-v9",
        "parallel-recurrent-ppo-v10",
        "parallel-recurrent-ppo-v12",
    }:
        raise ValueError("Version 7 can import only a verified Version-4-or-later curriculum")
    source_status = json.loads((source_run / "status.json").read_text(encoding="utf-8"))
    source_checkpoint = json.loads((source_run / "checkpoint.json").read_text(encoding="utf-8"))
    if source_status.get("state") != "finished" or source_status.get("stop_reason") not in {
        "stop_requested",
        "duration_limit",
        "action_limit",
        "hall_of_fame_verified",
    }:
        raise ValueError("PPO curriculum source is not a cleanly finished run")
    if source_checkpoint.get("protocol") != source_protocol:
        raise ValueError("PPO curriculum source checkpoint has the wrong protocol")
    if source_checkpoint.get("best_milestone") != source_manifest.get("best_milestone"):
        raise ValueError("PPO curriculum source best milestone is inconsistent")
    if source_checkpoint.get("total_actions") != source_status.get("total_actions"):
        raise ValueError("PPO curriculum source terminal action counts disagree")
    if _sha256_file(source_run / "ppo-latest.zip") != source_checkpoint.get("model_file_sha256"):
        raise ValueError("PPO curriculum source model failed its checkpoint hash")
    novelty_files = source_checkpoint.get("novelty_files")
    expected_environments = int(source_checkpoint.get("config", {}).get("environments", 0))
    if not isinstance(novelty_files, list) or len(novelty_files) != expected_environments:
        raise ValueError("PPO curriculum source lacks one novelty memory per worker")
    novelty_ranks: set[int] = set()
    for metadata in novelty_files:
        rank = int(metadata.get("rank", -1))
        if rank < 0 or rank >= expected_environments or rank in novelty_ranks:
            raise ValueError("PPO curriculum source novelty ranks are invalid")
        novelty_ranks.add(rank)
        filename = str(metadata.get("file", ""))
        if Path(filename).name != filename:
            raise ValueError("PPO curriculum source novelty filename is unsafe")
        if _sha256_file(source_run / filename) != metadata.get("file_sha256"):
            raise ValueError("PPO curriculum source novelty memory failed its hash")

    source_entries = source_manifest.get("entries")
    if not isinstance(source_entries, list) or not source_entries:
        raise ValueError("PPO curriculum source has no entries")
    validated: list[tuple[dict[str, Any], Path, Path, MilestoneProgress]] = []
    for metadata in source_entries:
        relative = Path(str(metadata.get("file", "")))
        if len(relative.parts) != 2 or relative.parts[0] != "entries":
            raise ValueError("PPO curriculum entry path is unsafe")
        source_path = source_run / "curriculum" / relative
        if _sha256_file(source_path) != metadata.get("file_sha256"):
            raise ValueError("PPO curriculum entry failed its source hash")
        payload = _read_gzip_json(source_path)
        progress = _canonical_progress(str(payload.get("progress", {}).get("key", "")))
        source_progress = _progress_from_value(payload["progress"])
        if progress.key != source_progress.key or progress.index != source_progress.index:
            raise ValueError("PPO curriculum entry changed ordinal across protocols")
        validated.append((dict(metadata), relative, source_path, progress))
    source_best = max(validated, key=lambda item: item[3].index)[3].public_dict()
    if source_best != source_manifest.get("best_milestone"):
        raise ValueError("PPO curriculum source entries disagree with its best milestone")

    curriculum_directory.mkdir(parents=True, exist_ok=False)
    target_entries = curriculum_directory / "entries"
    target_entries.mkdir()
    entries: list[dict[str, Any]] = []
    for metadata, relative, source_path, progress in validated:
        target_path = target_entries / relative.name
        shutil.copy2(source_path, target_path)
        entry = metadata
        entry.update(
            {
                "file": f"entries/{relative.name}",
                "file_sha256": _sha256_file(target_path),
                "milestone_id": progress.key,
                "milestone_index": progress.index,
                "milestone_label": progress.label,
            }
        )
        entries.append(entry)
    if sum(int(item["milestone_index"]) == 0 for item in entries) != 1:
        raise ValueError("PPO curriculum import requires one power-on root")
    best = max(entries, key=lambda item: int(item["milestone_index"]))
    manifest = {
        "schema_version": 1,
        "protocol": target_protocol,
        "source_protocol": source_manifest["protocol"],
        "source_run": source_run.name,
        "entries": entries,
        "best_milestone": {
            "key": best["milestone_id"],
            "index": best["milestone_index"],
            "label": best["milestone_label"],
        },
        "verified_promotions": int(source_manifest.get("verified_promotions", 0)),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _copy_retained_ppo_policy(
    source_run: Path,
    destination: Path,
    config: ParallelPpoConfig,
) -> dict[str, Any]:
    """Copy one clean compatible PPO policy and optimizer into a new campaign."""

    status = json.loads((source_run / "status.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((source_run / "checkpoint.json").read_text(encoding="utf-8"))
    manifest = json.loads((source_run / "manifest.json").read_text(encoding="utf-8"))
    source_protocol = checkpoint.get("protocol")
    if source_protocol not in {
        "parallel-recurrent-ppo-v5.2",
        "parallel-recurrent-ppo-v6",
        "parallel-recurrent-ppo-v7",
    }:
        raise ValueError("Consolidation requires a Version-5.2-or-later PPO policy")
    if status.get("state") != "finished" or status.get("stop_reason") not in {
        "stop_requested",
        "duration_limit",
        "action_limit",
        "hall_of_fame_verified",
    }:
        raise ValueError("Retained PPO policy source is not a cleanly finished run")
    if checkpoint.get("total_actions") != status.get("total_actions"):
        raise ValueError("Retained PPO policy terminal action counts disagree")
    if manifest.get("actor_mode") != config.mode:
        raise ValueError("Retained PPO policy actor mode is incompatible")
    source_config = checkpoint.get("config", {})
    compatible = (
        "mode",
        "rollout_steps",
        "batch_size",
        "epochs",
        "learning_rate",
        "gamma",
        "entropy_coefficient",
    )
    mismatched = [
        name for name in compatible if source_config.get(name) != config.public_dict().get(name)
    ]
    if mismatched:
        raise ValueError(
            "Retained PPO policy training shape changed: " + ", ".join(sorted(mismatched))
        )
    source_model = source_run / "ppo-latest.zip"
    expected_hash = checkpoint.get("model_file_sha256")
    if _sha256_file(source_model) != expected_hash:
        raise ValueError("Retained PPO policy failed its terminal hash")
    shutil.copy2(source_model, destination)
    return {
        "kind": "retained_ppo_policy_and_optimizer",
        "source_run": source_run.name,
        "source_protocol": source_protocol,
        "source_total_actions": int(status["total_actions"]),
        "source_best_milestone": status["best_milestone"],
        "file": destination.name,
        "file_sha256": _sha256_file(destination),
        "optimizer_state_retained": True,
        "new_campaign_timestep_counter": True,
    }


def freeze_verified_curriculum(
    expedition_run: Path,
    curriculum_directory: Path,
    *,
    target_protocol: str = PPO_PROTOCOL,
) -> dict[str, Any]:
    """Copy a verified Archive-v2 or completed PPO curriculum into a private run."""

    expedition_run = expedition_run.expanduser().resolve()
    if (expedition_run / "curriculum" / "manifest.json").is_file():
        return _import_verified_ppo_curriculum(
            expedition_run,
            curriculum_directory,
            target_protocol=target_protocol,
        )

    store, checkpoint = _checkpoint_view(expedition_run)
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
        "protocol": target_protocol,
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


def create_verified_power_on_curriculum(
    rom_path: Path,
    curriculum_directory: Path,
    *,
    target_protocol: str = PPO_V12_PROTOCOL,
) -> dict[str, Any]:
    """Create V12's sole starting state directly from two clean ROM boots.

    Earlier self-taught versions imported a completed run merely to obtain its power-on snapshot
    and then deleted every later entry. V12 removes that awkward dependency: it creates the root
    itself and proves that a second clean emulator accepts the exact frozen state before training.
    No controller action, predecessor snapshot, or predecessor policy participates.
    """

    if curriculum_directory.exists():
        raise ValueError("Direct power-on curriculum output already exists")
    curriculum_directory.mkdir(parents=True)
    (curriculum_directory / "entries").mkdir()
    progress = MilestoneProgress("power_on", 0, "Power-on")
    with PokemonRedEmulator(rom_path) as emulator:
        state = PokemonRedStateReader(emulator).read()
        screen = preprocess_apprentice_frame(emulator.screen_rgb())
        snapshot = FrozenSnapshot.freeze(emulator.save_state())
        screen_sha256 = hashlib.sha256(screen.tobytes()).hexdigest()
        referee = referee_summary_for_state(state, progress)
    with PokemonRedEmulator(rom_path) as verifier:
        verifier.load_state(snapshot.thaw())
        verified_state = PokemonRedStateReader(verifier).read()
        verified_screen = preprocess_apprentice_frame(verifier.screen_rgb())
        if verified_state != state or hashlib.sha256(verified_screen.tobytes()).hexdigest() != (
            screen_sha256
        ):
            raise RuntimeError("Direct power-on snapshot failed its clean-emulator replay gate")

    entry_id = f"power-on-{snapshot.sha256[:16]}"
    payload = {
        "schema_version": 1,
        "entry_id": entry_id,
        "source_cell_id": None,
        "progress": progress.public_dict(),
        "snapshot": snapshot.checkpoint_dict(),
        "lineage_actions": [],
        "terminal_referee_summary": referee,
        "clean_boot_replay_passes": 1,
        "controller_actions": 0,
    }
    path = curriculum_directory / "entries" / f"{entry_id}.json.gz"
    _atomic_gzip_json(path, payload)
    entry = {
        "entry_id": entry_id,
        "file": f"entries/{path.name}",
        "file_sha256": _sha256_file(path),
        "milestone_id": progress.key,
        "milestone_index": progress.index,
        "milestone_label": progress.label,
        "map_id": None,
        "depth_actions": 0,
        "source": "direct_verified_clean_boot",
    }
    manifest = {
        "schema_version": 1,
        "protocol": target_protocol,
        "source_protocol": "direct-verified-clean-boot-v1",
        "source_run": None,
        "entries": [entry],
        "best_milestone": progress.public_dict(),
        "verified_promotions": 0,
        "power_on_only": True,
        "discarded_inherited_entries": 0,
        "clean_boot_replay_passes": 1,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _retain_power_on_only(curriculum_directory: Path) -> dict[str, Any]:
    """Remove inherited lessons while retaining one verified clean-start snapshot."""

    manifest = _load_curriculum_manifest(curriculum_directory)
    roots = [entry for entry in manifest["entries"] if int(entry["milestone_index"]) == 0]
    if len(roots) != 1:
        raise ValueError("Fresh self-taught curriculum requires one power-on root")
    root = roots[0]
    retained = curriculum_directory / str(root["file"])
    for entry in manifest["entries"]:
        path = curriculum_directory / str(entry["file"])
        if path != retained:
            path.unlink()
    manifest["discarded_inherited_entries"] = len(manifest["entries"]) - 1
    manifest["entries"] = [root]
    manifest["best_milestone"] = {
        "key": "power_on",
        "index": 0,
        "label": "Power-on",
    }
    manifest["verified_promotions"] = 0
    manifest["power_on_only"] = True
    manifest["updated_at"] = datetime.now(UTC).isoformat()
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _load_curriculum_manifest(directory: Path) -> dict[str, Any]:
    value = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if value.get("protocol") not in {
        PPO_PROTOCOL,
        PPO_V8_PROTOCOL,
        PPO_V9_PROTOCOL,
        PPO_V10_PROTOCOL,
        PPO_V12_PROTOCOL,
    } or not isinstance(value.get("entries"), list):
        raise ValueError("PPO curriculum manifest is invalid")
    return value


def _load_curriculum_entry(directory: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    path = directory / str(metadata["file"])
    if _sha256_file(path) != metadata["file_sha256"]:
        raise ValueError("PPO curriculum entry hash is invalid")
    return _read_gzip_json(path)


def _validate_curriculum_state(
    directory: Path,
    value: Mapping[str, Any],
    *,
    expected_protocol: str,
) -> None:
    if value.get("protocol") != expected_protocol:
        raise ValueError("PPO curriculum checkpoint uses the wrong protocol")
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("PPO curriculum checkpoint has no entries")
    identifiers: set[str] = set()
    roots = 0
    best_entry: Mapping[str, Any] | None = None
    for metadata in entries:
        if not isinstance(metadata, Mapping):
            raise ValueError("PPO curriculum checkpoint entry is invalid")
        entry_id = str(metadata.get("entry_id", ""))
        if not entry_id or entry_id in identifiers:
            raise ValueError("PPO curriculum checkpoint entry IDs are invalid")
        identifiers.add(entry_id)
        relative = Path(str(metadata.get("file", "")))
        if (
            relative.is_absolute()
            or len(relative.parts) != 2
            or relative.parts[0] != "entries"
            or ".." in relative.parts
        ):
            raise ValueError("PPO curriculum checkpoint entry path is unsafe")
        payload = _load_curriculum_entry(directory, metadata)
        if str(payload.get("entry_id")) != entry_id:
            raise ValueError("PPO curriculum checkpoint entry ID changed")
        progress = _progress_from_value(payload["progress"])
        if progress.index != int(metadata["milestone_index"]):
            raise ValueError("PPO curriculum checkpoint milestone index changed")
        roots += int(progress.index == 0)
        if best_entry is None or int(metadata["milestone_index"]) > int(
            best_entry["milestone_index"]
        ):
            best_entry = metadata
    if roots != 1 or best_entry is None:
        raise ValueError("PPO curriculum checkpoint needs one power-on root")
    best = value.get("best_milestone")
    if (
        not isinstance(best, Mapping)
        or int(best.get("index", -1)) != int(best_entry["milestone_index"])
        or str(best.get("key")) != str(best_entry["milestone_id"])
        or str(best.get("label")) != str(best_entry["milestone_label"])
    ):
        raise ValueError("PPO curriculum checkpoint best milestone is inconsistent")


def _checkpoint_curriculum_state(
    run_directory: Path,
    curriculum_directory: Path,
    *,
    protocol: str,
) -> dict[str, str]:
    value = _load_curriculum_manifest(curriculum_directory)
    _validate_curriculum_state(
        curriculum_directory,
        value,
        expected_protocol=protocol,
    )
    snapshot = curriculum_directory / "manifest.checkpoint.json"
    previous = curriculum_directory / "manifest.checkpoint.previous.json"
    if snapshot.exists():
        os.replace(snapshot, previous)
    _atomic_json(snapshot, value)
    return {
        "curriculum_checkpoint_file": "curriculum/manifest.checkpoint.json",
        "curriculum_file_sha256": _sha256_file(snapshot),
    }


def _restore_curriculum_state(
    run_directory: Path,
    curriculum_directory: Path,
    checkpoint: Mapping[str, Any],
    *,
    protocol: str,
) -> dict[str, Any]:
    filename = checkpoint.get("curriculum_checkpoint_file")
    if filename != "curriculum/manifest.checkpoint.json":
        raise ValueError("PPO checkpoint has no valid curriculum snapshot")
    try:
        snapshot = _resolve_checkpoint_artifact(
            run_directory,
            latest_name=filename,
            previous_name="curriculum/manifest.checkpoint.previous.json",
            expected_sha256=checkpoint.get("curriculum_file_sha256"),
        )
    except ValueError as error:
        raise ValueError("PPO curriculum snapshot does not match its checkpoint") from error
    value = json.loads(snapshot.read_text(encoding="utf-8"))
    _validate_curriculum_state(
        curriculum_directory,
        value,
        expected_protocol=protocol,
    )
    _atomic_json(curriculum_directory / "manifest.json", value)
    return value


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


def _goal_observation(progress: MilestoneProgress) -> np.ndarray:
    value = np.zeros(GOAL_COUNT, dtype=np.float32)
    value[min(progress.index + 1, GOAL_COUNT - 1)] = 1
    return value


def _skill_observation(state: PokemonRedState, progress: MilestoneProgress) -> np.ndarray:
    value = np.zeros(SKILL_COUNT, dtype=np.float32)
    if state.battle_state in {1, 2}:
        index = 2  # battle
    elif progress.index < len(MILESTONES) and MILESTONES[progress.index].kind == "landmark":
        index = 0  # navigation
    else:
        index = 1  # interaction/dialogue/menu
    value[index] = 1
    return value


@dataclass(slots=True)
class EpisodeMapMemory:
    """Trainer-built visited map disclosed only to the assisted actor."""

    visited: dict[int, set[tuple[int, int]]] = field(default_factory=dict)

    def reset(self, state: PokemonRedState) -> None:
        self.visited = {}
        self.observe(state)

    def observe(self, state: PokemonRedState) -> None:
        if None in (state.map_id, state.player_x, state.player_y):
            return
        x, y = int(state.player_x), int(state.player_y)
        if 0 <= x < MAP_MEMORY_SIZE and 0 <= y < MAP_MEMORY_SIZE:
            self.visited.setdefault(int(state.map_id), set()).add((x, y))

    def observation(self, state: PokemonRedState) -> np.ndarray:
        value = np.zeros((2, MAP_MEMORY_SIZE, MAP_MEMORY_SIZE), dtype=np.uint8)
        if state.map_id is None:
            return value
        for x, y in self.visited.get(state.map_id, set()):
            value[0, y, x] = 255
        if state.player_x is not None and state.player_y is not None:
            x, y = int(state.player_x), int(state.player_y)
            if 0 <= x < MAP_MEMORY_SIZE and 0 <= y < MAP_MEMORY_SIZE:
                value[1, y, x] = 255
        return value


def _map_context(
    state: PokemonRedState,
    progress: MilestoneProgress,
    observed_edges: set[tuple[int, int]] | tuple[()] = (),
) -> np.ndarray:
    guidance = route_guidance(state, progress, observed_edges)
    return np.asarray(
        [
            (state.map_id or 0) / 255,
            min(progress.index + 1, GOAL_COUNT - 1) / max(1, GOAL_COUNT - 1),
            0.0 if guidance.next_map is None else (guidance.next_map + 1) / 256,
            0.0 if guidance.distance is None else min(guidance.distance, 8) / 8,
        ],
        dtype=np.float32,
    )


@dataclass(slots=True)
class VisualStagnationTracker:
    """Trainer-only loop watchdog; none of this state enters the actor observation."""

    cycle_window: int = 128
    cycle_unique_limit: int = 8
    hard_limit: int = 1_024
    use_authored_guidance: bool = True
    _frames: deque[bytes] = field(default_factory=lambda: deque(maxlen=128))
    _seen_positions: set[tuple[int, int, int]] = field(default_factory=set)
    _best_progress: int = 0
    _max_experience: int = 0
    _max_events: int = 0
    _max_owned: int = 0
    _max_badges: int = 0
    _enemy_hp_floor: int | None = None
    _last_battle: int = 0
    _max_mart_script: int = 0
    _goal_key: str | None = None
    _best_route_distance: int | None = None
    _stagnant_actions: int = 0

    def reset(self, state: PokemonRedState, progress: MilestoneProgress) -> None:
        self._frames = deque(maxlen=self.cycle_window)
        self._seen_positions = set()
        if state.map_id is not None and state.player_x is not None and state.player_y is not None:
            self._seen_positions.add((state.map_id, state.player_x, state.player_y))
        self._best_progress = progress.index if self.use_authored_guidance else 0
        self._max_experience = state.total_party_experience
        self._max_events = state.event_flags_count
        self._max_owned = state.pokedex_owned_count
        self._max_badges = state.badge_count
        self._enemy_hp_floor = state.enemy_hp
        self._last_battle = state.battle_state or 0
        self._max_mart_script = state.viridian_mart_script or 0 if self.use_authored_guidance else 0
        if self.use_authored_guidance:
            guidance = route_guidance(state, progress)
            self._goal_key = guidance.goal_key
            self._best_route_distance = guidance.distance
        else:
            self._goal_key = None
            self._best_route_distance = None
        self._stagnant_actions = 0

    def observe(
        self,
        frame: np.ndarray,
        state: PokemonRedState,
        progress: MilestoneProgress,
        *,
        perceptual_activity: bool = False,
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
        generic_progress = (
            (state.total_party_experience, "_max_experience"),
            (state.event_flags_count, "_max_events"),
            (state.pokedex_owned_count, "_max_owned"),
            (state.badge_count, "_max_badges"),
        )
        authored_progress = (
            (progress.index, "_best_progress"),
            (state.viridian_mart_script or 0, "_max_mart_script"),
        )
        for current, name in generic_progress + (
            authored_progress if self.use_authored_guidance else ()
        ):
            if current > getattr(self, name):
                setattr(self, name, current)
                useful_progress = True
        if self.use_authored_guidance:
            guidance = route_guidance(state, progress)
            if guidance.goal_key != self._goal_key:
                self._goal_key = guidance.goal_key
                self._best_route_distance = guidance.distance
                useful_progress = True
            elif guidance.distance is not None and (
                self._best_route_distance is None or guidance.distance < self._best_route_distance
            ):
                self._best_route_distance = guidance.distance
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
        if perceptual_activity:
            # V10 treats visually effective backtracking as activity without clearing the
            # signature window that still detects short oscillations.  Earlier protocols pass
            # the default False and retain their frozen watchdog behavior.
            self._stagnant_actions = 0
        else:
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


def _load_action(value: Mapping[str, Any]) -> BlindAction:
    return BlindAction(
        str(value["button"]), int(value["hold_frames"]), int(value["release_frames"])
    )


def _replay_sequence(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
    *,
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[FrozenSnapshot, MilestoneProgress, dict[str, Any], str]:
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        for action_index in actions:
            _check_v9_practice_cancellation(cancellation_check)
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


def _lineage_action_indices(entry: Mapping[str, Any]) -> list[int]:
    actions = [_load_action(value) for value in entry.get("lineage_actions", [])]
    if any(
        action.hold_frames != ACTION_HOLD_FRAMES or action.release_frames != ACTION_RELEASE_FRAMES
        for action in actions
    ):
        raise ValueError("PPO curriculum lineage uses a non-canonical action cadence")
    return [BLIND_ACTIONS.index(action.button) for action in actions]


def _nearest_verified_lineage_prefix(
    curriculum_directory: Path,
    full_actions: list[int],
    *,
    target_index: int,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Find the deepest admitted state on the exact self-generated action lineage."""

    manifest = _load_curriculum_manifest(curriculum_directory)
    matches: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for metadata in manifest["entries"]:
        index = int(metadata["milestone_index"])
        if index >= target_index:
            continue
        entry = _load_curriculum_entry(curriculum_directory, metadata)
        lineage = _lineage_action_indices(entry)
        if len(lineage) <= len(full_actions) and full_actions[: len(lineage)] == lineage:
            matches.append((len(lineage), index, dict(metadata), entry))
    if not matches:
        raise ValueError("Verified candidate has no admitted lineage prefix")
    length, _index, metadata, entry = max(matches, key=lambda value: (value[0], value[1]))
    return metadata, entry, length


def _stable_semantic_state_signature(
    emulator: PokemonRedEmulator,
    state: PokemonRedState,
) -> tuple[Any, ...]:
    """Return gameplay state that survives an emulator save/load boundary.

    PyBoy's complete game-area hash is a derived emulator view that is not
    guaranteed to be identical immediately across ``load_state``. Keep that stricter hash in the
    distillation oracle, whose candidates all replay from the same snapshot, but
    do not use it to compare a live composition with a separately loaded target
    snapshot.  The processed visual hash and all gameplay RAM fields remain exact.
    """

    frame = preprocess_apprentice_frame(emulator.screen_rgb())
    visual = hashlib.blake2b(frame.tobytes(), digest_size=16).digest()
    party_blob = bytes(
        emulator.read_u8(int(RamAddress.PARTY_COUNT) + offset)
        for offset in range(
            int(RamAddress.PARTY_MONS)
            - int(RamAddress.PARTY_COUNT)
            + PARTY_LENGTH * PARTY_MON_STRUCT_LENGTH
        )
    )
    bag_blob = bytes(
        emulator.read_u8(int(RamAddress.NUM_BAG_ITEMS) + offset)
        for offset in range(1 + MAX_BAG_ITEMS * 2)
    )
    money_blob = bytes(emulator.read_u8(0xD347 + offset) for offset in range(3))
    status_blob = bytes(emulator.read_u8(0xD730 + offset) for offset in range(7))
    return (
        state.game_started,
        state.map_id,
        state.player_x,
        state.player_y,
        state.battle_state,
        state.party_count,
        state.party_species,
        state.party_levels,
        state.party_moves,
        state.party_experience,
        state.party_hp,
        state.party_max_hp,
        state.badge_bits,
        state.pokedex_owned,
        state.pokedex_seen,
        state.event_flags,
        state.bag_item_ids,
        state.got_pokedex,
        state.enemy_hp,
        state.enemy_max_hp,
        state.viridian_mart_script,
        party_blob,
        bag_blob,
        money_blob,
        status_blob,
        visual,
    )


@dataclass(frozen=True, slots=True)
class _V9FirstHit:
    observed: ObservedMilestoneFirstHit
    progress: MilestoneProgress
    snapshot: FrozenSnapshot
    referee_summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _PreparedV9Skills:
    skills: tuple[dict[str, Any], ...]
    graph: Any
    hits: tuple[_V9FirstHit, ...]
    source_entry_id: str
    final_entry_id: str
    full_actions: tuple[int, ...]
    source_prefix_length: int


def _v9_stable_state_sha256(
    emulator: PokemonRedEmulator,
    state: PokemonRedState,
) -> str:
    signature = _stable_semantic_state_signature(emulator, state)
    return hashlib.sha256(repr(signature).encode("utf-8")).hexdigest()


def _collect_v9_first_hit_graph(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
    target: MilestoneProgress,
    *,
    replay_id: str,
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[Any, tuple[_V9FirstHit, ...]]:
    """Replay one verified discovery and capture every concrete adjacent milestone edge."""

    hits: list[_V9FirstHit] = []
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        reader = PokemonRedStateReader(emulator)

        def capture(progress: MilestoneProgress, offset: int) -> None:
            state = reader.read()
            snapshot = FrozenSnapshot.freeze(emulator.save_state())
            stable = _v9_stable_state_sha256(emulator, state)
            verification_id = hashlib.sha256(
                f"{replay_id}:{progress.index}:{offset}:{snapshot.sha256}:{stable}".encode()
            ).hexdigest()
            hits.append(
                _V9FirstHit(
                    observed=ObservedMilestoneFirstHit(
                        milestone_id=progress.key,
                        milestone_index=progress.index,
                        action_offset=offset,
                        state_identity=StableStateIdentity(
                            stable_state_sha256=stable,
                            snapshot_sha256=snapshot.sha256,
                        ),
                        verification_id=verification_id,
                    ),
                    progress=progress,
                    snapshot=snapshot,
                    referee_summary=referee_summary_for_state(state, progress),
                )
            )

        current = milestone_progress_for_state(reader.read(), inherited=inherited)
        capture(current, 0)
        for offset, action in enumerate(actions, start=1):
            _check_v9_practice_cancellation(cancellation_check)
            if not _execute_action(emulator, action):
                raise RuntimeError("V9 first-hit replay emulator stopped")
            progress = milestone_progress_for_state(reader.read(), inherited=current)
            if progress.index > current.index:
                if progress.index != current.index + 1:
                    raise ValueError("V9 replay skipped an unobserved milestone boundary")
                current = progress
                capture(current, offset)
        if current.index != target.index or hits[-1].observed.action_offset != len(actions):
            raise ValueError("V9 verified replay did not terminate on its target first hit")
    graph = normalize_first_hit_replay(
        actions,
        tuple(hit.observed for hit in hits),
        replay_id=replay_id,
    )
    return graph, tuple(hits)


def _distillation_state_signature(
    emulator: PokemonRedEmulator,
    state: PokemonRedState,
    progress: MilestoneProgress,
) -> tuple[Any, ...]:
    return (
        *_stable_semantic_state_signature(emulator, state),
        emulator.game_area_sha256(),
        progress.index,
    )


def _composition_state_signature(
    emulator: PokemonRedEmulator,
    state: PokemonRedState,
    progress: MilestoneProgress,
) -> tuple[Any, ...]:
    """Fail-closed endpoint identity for comparisons across save/load boundaries."""

    return (*_stable_semantic_state_signature(emulator, state), progress.index)


def _collect_distillation_signatures(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
    *,
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[tuple[Any, ...], ...]:
    signatures: list[tuple[Any, ...]] = []
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        reader = PokemonRedStateReader(emulator)
        state = reader.read()
        progress = milestone_progress_for_state(state, inherited=inherited)
        signatures.append(_distillation_state_signature(emulator, state, progress))
        for action in actions:
            _check_v9_practice_cancellation(cancellation_check)
            if not _execute_action(emulator, action):
                raise RuntimeError("Trajectory distillation replay emulator stopped")
            state = reader.read()
            progress = milestone_progress_for_state(state, inherited=inherited)
            signatures.append(_distillation_state_signature(emulator, state, progress))
    return tuple(signatures)


def _replay_distillation_terminal_signature(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: tuple[int, ...],
    inherited: MilestoneProgress,
    *,
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[Any, ...]:
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        for action in actions:
            _check_v9_practice_cancellation(cancellation_check)
            if not _execute_action(emulator, action):
                raise RuntimeError("Trajectory distillation replay emulator stopped")
        state = PokemonRedStateReader(emulator).read()
        progress = milestone_progress_for_state(state, inherited=inherited)
        return _distillation_state_signature(emulator, state, progress)


def _distill_verified_actions(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
    target: MilestoneProgress,
    *,
    verification_id: str,
    successful_replays: int,
    max_attempts: int,
    cancellation_check: Callable[[], str | None] | None = None,
) -> Any:
    """Shorten an agent-generated edge using only replayed outcome evidence."""

    signatures = _collect_distillation_signatures(
        rom_path,
        start_snapshot,
        actions,
        inherited,
        cancellation_check=cancellation_check,
    )
    protected_outcome = signatures[-1]

    def oracle(candidate: tuple[int, ...]) -> bool:
        try:
            signature = _replay_distillation_terminal_signature(
                rom_path,
                start_snapshot,
                candidate,
                inherited,
                cancellation_check=cancellation_check,
            )
        except V9PracticeCancelled:
            raise
        except RuntimeError:
            return False
        return signature == protected_outcome and int(signature[-1]) >= target.index

    return distill_self_generated_trajectory(
        VerifiedSelfTrajectory(
            actions=tuple(actions),
            state_signatures=signatures,
            evidence=ReplayEvidence(
                verification_id=verification_id,
                successful_replays=successful_replays,
            ),
        ),
        oracle,
        config=DistillationConfig(
            max_loop_attempts=max_attempts // 2,
            max_chunk_attempts=max_attempts - max_attempts // 2,
        ),
    )


def _collect_v8_student_dataset(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    *,
    compressed_to_original: tuple[int, ...],
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Build a recurrent Student sequence and a three-frame self-observed goal clip."""

    if not actions:
        raise ValueError("V8 Student dataset requires a non-empty distilled edge")
    pixels: list[np.ndarray] = []
    histories: list[np.ndarray] = []
    frames: list[np.ndarray] = []
    recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        current = preprocess_apprentice_frame(emulator.screen_rgb())
        previous = current
        frames.append(current)
        for action_index in actions:
            _check_v9_practice_cancellation(cancellation_check)
            pixels.append(np.stack((previous, current)))
            histories.append(_action_history(recent))
            if not _execute_action(emulator, int(action_index)):
                raise RuntimeError("V8 Student replay emulator stopped")
            recent.append(int(action_index))
            previous = current
            current = preprocess_apprentice_frame(emulator.screen_rgb())
            frames.append(current)
    target_frames = frames[-3:]
    while len(target_frames) < 3:
        target_frames.insert(0, target_frames[0])
    target_clip = np.stack(target_frames).astype(np.uint8, copy=False)
    # Distillation already proved that every retained action is necessary to the
    # accepted replay. Give those actions equal authority instead of importing
    # PPO's future-return discount into supervised sequence imitation.
    weights = np.ones(len(actions), dtype=np.float32)
    return (
        {
            "pixels": np.stack(pixels).astype(np.uint8, copy=False),
            "action_history": np.stack(histories).astype(np.float32, copy=False),
            "target_pixels": target_clip,
            "actions": np.asarray(actions, dtype=np.int64),
            "weights": weights,
            "episode_starts": np.asarray([True, *([False] * (len(actions) - 1))], dtype=np.bool_),
            "compressed_to_original": np.asarray(compressed_to_original, dtype=np.int64),
        },
        target_clip,
    )


def _v8_composition_fingerprint(chain: list[Mapping[str, Any]]) -> str:
    """Name one exact ordered chain and every artifact that supplies its actions."""

    if len(chain) < 2:
        raise ValueError("V8 composition replay requires at least two skills")
    identity = {
        "protocol": SELF_GENERATED_COMPOSITION_PROTOCOL,
        "skills": [
            {
                "skill_id": str(skill["skill_id"]),
                "source_entry_id": str(skill["source_entry_id"]),
                "target_entry_id": str(skill["target_entry_id"]),
                "dataset_sha256": str(skill["dataset_sha256"]),
                "distillation_audit_sha256": str(skill["distillation_audit_sha256"]),
            }
            for skill in chain
        ],
    }
    return hashlib.sha256(_canonical_json(identity)).hexdigest()


def _curriculum_snapshot_signature(
    rom_path: Path,
    entry: Mapping[str, Any],
) -> tuple[Any, ...]:
    inherited = _progress_from_value(entry["progress"])
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(FrozenSnapshot.from_checkpoint_dict(entry["snapshot"]).thaw())
        state = PokemonRedStateReader(emulator).read()
        progress = milestone_progress_for_state(state, inherited=inherited)
        return _composition_state_signature(emulator, state, progress)


def _v8_composition_training_weights(action_count: int) -> np.ndarray:
    """Keep both sides of long goal switches visible to normalized BC loss."""

    if action_count < 1:
        raise ValueError("V8 composition weights require at least one action")
    return np.ones(action_count, dtype=np.float32)


def _collect_v8_composition_dataset(
    rom_path: Path,
    curriculum_directory: Path,
    chain: list[Mapping[str, Any]],
    sources: Mapping[str, tuple[np.ndarray, np.ndarray]],
    *,
    burn_in: int,
    train_length: int,
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    """Stream-verify a chain and retain only bounded goal-switch excerpts.

    Every action comes from an individually replay-verified self-generated skill.
    Concatenation is admitted only when one uninterrupted replay from the exact
    power-on snapshot reaches the protected terminal state of every edge. Pixels
    are retained only around internal goal switches; full lineage remains bound by
    the source hashes and replay audit without quadratic prefix materialization.
    """

    if len(chain) < 2:
        raise ValueError("V8 composition replay requires at least two skills")
    if burn_in < 0 or train_length < 2:
        raise ValueError("V8 composition excerpts require valid recurrent context")
    if any(
        str(left["target_entry_id"]) != str(right["source_entry_id"])
        for left, right in zip(chain, chain[1:], strict=False)
    ):
        raise ValueError("V8 composition skills are not a continuous chain")
    manifest = _load_curriculum_manifest(curriculum_directory)
    metadata_by_id = {str(item["entry_id"]): item for item in manifest["entries"]}

    def load_entry(entry_id: str) -> tuple[Mapping[str, Any], dict[str, Any]]:
        metadata = metadata_by_id.get(entry_id)
        if metadata is None:
            raise ValueError("V8 composition curriculum entry is missing")
        return metadata, _load_curriculum_entry(curriculum_directory, metadata)

    root_id = str(chain[0]["source_entry_id"])
    root_metadata, root = load_entry(root_id)
    if int(root_metadata["milestone_index"]) != 0:
        raise ValueError("V8 composition replay must begin at the exact power-on entry")
    inherited = _progress_from_value(root["progress"])
    expected: list[tuple[Mapping[str, Any], dict[str, Any], tuple[Any, ...]]] = []
    ordered_actions: list[np.ndarray] = []
    target_clips: list[np.ndarray] = []
    for skill in chain:
        skill_id = str(skill["skill_id"])
        source = sources.get(skill_id)
        if source is None:
            raise ValueError("V8 composition source dataset is missing")
        actions, target_clip = source
        if actions.ndim != 1 or len(actions) != int(skill["action_count"]):
            raise ValueError("V8 composition source actions disagree with the skill ledger")
        if target_clip.shape != (3, 72, 80):
            raise ValueError("V8 composition source needs one verified three-frame goal clip")
        metadata, entry = load_entry(str(skill["target_entry_id"]))
        expected.append((metadata, entry, _curriculum_snapshot_signature(rom_path, entry)))
        ordered_actions.append(actions.astype(np.int64, copy=False))
        target_clips.append(target_clip.astype(np.uint8, copy=False))

    full_offsets = [0]
    for actions in ordered_actions:
        full_offsets.append(full_offsets[-1] + len(actions))
    left_train = max(1, train_length // 2)
    right_train = max(1, train_length - left_train)
    before = burn_in + left_train
    after = right_train
    excerpt_ranges = [
        (
            max(full_offsets[index - 1], boundary - before),
            min(full_offsets[index + 1], boundary + after),
        )
        for index, boundary in enumerate(full_offsets[1:-1], start=1)
    ]
    excerpt_pixels: list[list[np.ndarray]] = [[] for _ in excerpt_ranges]
    excerpt_histories: list[list[np.ndarray]] = [[] for _ in excerpt_ranges]
    excerpt_actions: list[list[int]] = [[] for _ in excerpt_ranges]
    excerpt_goals: list[list[int]] = [[] for _ in excerpt_ranges]
    boundaries: list[dict[str, Any]] = []
    recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
    global_action = 0
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(FrozenSnapshot.from_checkpoint_dict(root["snapshot"]).thaw())
        reader = PokemonRedStateReader(emulator)
        current = preprocess_apprentice_frame(emulator.screen_rgb())
        previous = current
        for goal_index, (skill, segment_actions, (metadata, target_entry, protected)) in enumerate(
            zip(
                chain,
                ordered_actions,
                expected,
                strict=True,
            )
        ):
            for raw_action in segment_actions:
                action = int(raw_action)
                for excerpt, (start, stop) in enumerate(excerpt_ranges):
                    if start <= global_action < stop:
                        excerpt_pixels[excerpt].append(np.stack((previous, current)))
                        excerpt_histories[excerpt].append(_action_history(recent))
                        excerpt_actions[excerpt].append(action)
                        excerpt_goals[excerpt].append(goal_index)
                if not _execute_action(emulator, action):
                    raise CompositionReplayRejected(
                        "V8 composition emulator stopped during continuous replay"
                    )
                recent.append(action)
                previous = current
                current = preprocess_apprentice_frame(emulator.screen_rgb())
                global_action += 1
            state = reader.read()
            progress = milestone_progress_for_state(state, inherited=inherited)
            observed = _composition_state_signature(emulator, state, progress)
            if observed[:-1] != protected[:-1] or progress.index < int(skill["target_index"]):
                raise CompositionReplayRejected(
                    "V8 compressed skills did not compose to a protected target state"
                )
            boundaries.append(
                {
                    "full_action_offset": global_action,
                    "skill_id": str(skill["skill_id"]),
                    "target_entry_id": str(skill["target_entry_id"]),
                    "target_entry_file_sha256": str(metadata["file_sha256"]),
                    "target_index": int(skill["target_index"]),
                    "observed_index": progress.index,
                    "semantic_signature_sha256": hashlib.sha256(
                        repr(observed[:-1]).encode("utf-8")
                    ).hexdigest(),
                }
            )
            inherited = _progress_from_value(target_entry["progress"])

    pixels = [np.stack(values).astype(np.uint8, copy=False) for values in excerpt_pixels]
    histories = [np.stack(values).astype(np.float32, copy=False) for values in excerpt_histories]
    actions = [np.asarray(values, dtype=np.int64) for values in excerpt_actions]
    goals = [np.asarray(values, dtype=np.int64) for values in excerpt_goals]
    excerpt_offsets = [0]
    training_switches: list[int] = []
    for excerpt, ((start, _stop), full_boundary) in enumerate(
        zip(excerpt_ranges, full_offsets[1:-1], strict=True)
    ):
        training_switches.append(excerpt_offsets[-1] + full_boundary - start)
        excerpt_offsets.append(excerpt_offsets[-1] + len(actions[excerpt]))
    count = excerpt_offsets[-1]
    episode_starts = np.zeros(count, dtype=np.bool_)
    episode_starts[np.asarray(excerpt_offsets[:-1], dtype=np.int64)] = True
    return (
        {
            "pixels": np.concatenate(pixels),
            "action_history": np.concatenate(histories),
            "target_pixels": np.stack(target_clips).astype(np.uint8, copy=False),
            "actions": np.concatenate(actions),
            "weights": _v8_composition_training_weights(count),
            "episode_starts": episode_starts,
            "goal_indices": np.concatenate(goals),
            "excerpt_offsets": np.asarray(excerpt_offsets, dtype=np.int64),
            "dataset_kind": np.asarray("composition"),
            "replay_protocol": np.asarray(SELF_GENERATED_COMPOSITION_PROTOCOL),
            "successful_replays": np.asarray(1, dtype=np.int64),
            "source_skill_ids": np.asarray([str(skill["skill_id"]) for skill in chain]),
            "goal_switch_offsets": np.asarray(training_switches, dtype=np.int64),
            "full_goal_switch_offsets": np.asarray(full_offsets[1:-1], dtype=np.int64),
            "full_action_count": np.asarray(full_offsets[-1], dtype=np.int64),
            "excerpt_full_ranges": np.asarray(excerpt_ranges, dtype=np.int64),
        },
        boundaries,
    )


def _collect_self_imitation_dataset(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    target_frame: np.ndarray,
) -> dict[str, np.ndarray]:
    """Replay the agent's own verified edge into exact visual/action training examples."""

    if not actions:
        raise ValueError("Self-imitation requires a non-empty verified edge")
    pixels: list[np.ndarray] = []
    histories: list[np.ndarray] = []
    recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        current = preprocess_apprentice_frame(emulator.screen_rgb())
        previous = current
        for action_index in actions:
            pixels.append(np.stack((previous, current)))
            histories.append(_action_history(recent))
            if not _execute_action(emulator, int(action_index)):
                raise RuntimeError("Self-imitation replay emulator stopped")
            recent.append(int(action_index))
            previous = current
            current = preprocess_apprentice_frame(emulator.screen_rgb())
    return {
        "pixels": np.stack(pixels).astype(np.uint8, copy=False),
        "action_history": np.stack(histories).astype(np.float32, copy=False),
        "target_pixels": target_frame[None, :, :].astype(np.uint8, copy=False),
        "actions": np.asarray(actions, dtype=np.int64),
    }


def _atomic_self_imitation_dataset(path: Path, dataset: Mapping[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.npz")
    with temporary.open("wb") as output:
        np.savez_compressed(output, **dataset)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _write_v8_replay_shards(
    run_directory: Path,
    *,
    skill_id: str,
    dataset: Mapping[str, np.ndarray],
    source_dataset_sha256: str,
    max_examples: int,
    burn_in: int,
    cancellation_check: Callable[[], str | None] | None = None,
) -> list[dict[str, Any]]:
    """Seal bounded training chunks while the verified full dataset is in memory.

    The full artifact remains the immutable provenance source.  Later replay rounds
    open only one of these small hash-bound derivatives, never the monolithic NPZ.
    """

    skill_component = Path(skill_id)
    if (
        not skill_id
        or skill_component.is_absolute()
        or skill_component.name != skill_id
        or skill_id in {".", ".."}
        or max_examples < 1
        or burn_in < 0
    ):
        raise ValueError("V8 replay shards require a skill and positive example cap")
    if len(source_dataset_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in source_dataset_sha256
    ):
        raise ValueError("V8 replay shards require a sealed source dataset")
    required = {"pixels", "action_history", "target_pixels", "actions", "weights"}
    if missing := sorted(required.difference(dataset)):
        raise ValueError(f"V8 replay shard source is missing: {', '.join(missing)}")
    action_count = len(np.asarray(dataset["actions"]))
    if action_count < 1:
        raise ValueError("V8 replay shards require at least one source action")
    for key in ("pixels", "action_history", "weights"):
        if len(np.asarray(dataset[key])) != action_count:
            raise ValueError("V8 replay shard source arrays disagree on action count")

    shard_count = (action_count + max_examples - 1) // max_examples
    metadata: list[dict[str, Any]] = []
    for shard_index, train_start in enumerate(range(0, action_count, max_examples)):
        _check_v9_practice_cancellation(cancellation_check)
        context_start = max(0, train_start - burn_in)
        stop = min(action_count, train_start + max_examples)
        stored_count = stop - context_start
        train_count = stop - train_start
        relative = (
            Path("self-skills")
            / "replay"
            / skill_id
            / f"shard-{shard_index:06d}-of-{shard_count:06d}.npz"
        )
        path = run_directory / relative
        episode_starts = np.zeros(stored_count, dtype=np.bool_)
        episode_starts[0] = True
        payload: dict[str, np.ndarray] = {
            "pixels": np.asarray(dataset["pixels"])[context_start:stop],
            "action_history": np.asarray(dataset["action_history"])[context_start:stop],
            "target_pixels": np.asarray(dataset["target_pixels"]),
            "actions": np.asarray(dataset["actions"])[context_start:stop],
            "weights": np.asarray(dataset["weights"])[context_start:stop],
            "episode_starts": episode_starts,
            "replay_shard_protocol": np.asarray(SELF_GENERATED_REPLAY_SHARD_PROTOCOL),
            "source_dataset_sha256": np.asarray(source_dataset_sha256),
            "source_skill_id": np.asarray(skill_id),
            "source_action_count": np.asarray(action_count, dtype=np.int64),
            "source_action_offset": np.asarray(context_start, dtype=np.int64),
            "source_context_start": np.asarray(context_start, dtype=np.int64),
            "source_train_start": np.asarray(train_start, dtype=np.int64),
            "source_train_stop": np.asarray(stop, dtype=np.int64),
            "replay_train_offset": np.asarray(
                train_start - context_start,
                dtype=np.int64,
            ),
            "replay_shard_index": np.asarray(shard_index, dtype=np.int64),
            "replay_shard_count": np.asarray(shard_count, dtype=np.int64),
        }
        if "compressed_to_original" in dataset:
            payload["compressed_to_original"] = np.asarray(dataset["compressed_to_original"])[
                context_start:stop
            ]
        _atomic_self_imitation_dataset(path, payload)
        metadata.append(
            {
                "protocol": SELF_GENERATED_REPLAY_SHARD_PROTOCOL,
                "file": relative.as_posix(),
                "sha256": _sha256_file(path),
                "stored_bytes": path.stat().st_size,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "source_dataset_sha256": source_dataset_sha256,
                "source_action_count": action_count,
                "source_start": context_start,
                "source_context_start": context_start,
                "source_train_start": train_start,
                "source_stop": stop,
                "context_example_count": train_start - context_start,
                "train_example_count": train_count,
                "example_count": stored_count,
            }
        )
    if (
        len(metadata) != shard_count
        or metadata[-1]["source_stop"] != action_count
        or sum(int(item["train_example_count"]) for item in metadata) != action_count
    ):
        raise RuntimeError("V8 replay shard admission did not cover the verified source")
    return metadata


def _self_imitation_windows(length: int, width: int = 256) -> list[tuple[int, int]]:
    if length < 1:
        return []
    if length <= width:
        return [(0, length)]
    starts = np.linspace(0, length - width, num=min(8, max(2, length // width)), dtype=int)
    return [(int(start), min(length, int(start) + width)) for start in sorted(set(starts))]


def _train_self_imitation_policy(
    model: Any,
    datasets: list[Path],
    *,
    epochs: int,
) -> dict[str, Any]:
    """Apply direct action likelihood updates on self-generated, replay-verified skills."""

    from sb3_contrib.common.recurrent.type_aliases import RNNStates

    if epochs < 1 or not datasets:
        raise ValueError("Self-imitation training requires data and positive epochs")
    losses: list[float] = []
    examples = 0
    updates = 0
    policy = model.policy
    policy.set_training_mode(True)
    for _epoch in range(epochs):
        for path in datasets:
            with np.load(path, allow_pickle=False) as data:
                actions = np.asarray(data["actions"], dtype=np.int64)
                pixels = np.asarray(data["pixels"], dtype=np.uint8)
                histories = np.asarray(data["action_history"], dtype=np.float32)
                target = np.asarray(data["target_pixels"], dtype=np.uint8)
            for begin, end in _self_imitation_windows(len(actions)):
                count = end - begin
                observations = {
                    "pixels": torch.as_tensor(pixels[begin:end], device=policy.device),
                    "action_history": torch.as_tensor(histories[begin:end], device=policy.device),
                    "target_pixels": torch.as_tensor(
                        np.repeat(target[None, ...], count, axis=0),
                        device=policy.device,
                    ),
                }
                action_tensor = torch.as_tensor(
                    actions[begin:end], dtype=torch.long, device=policy.device
                )
                episode_starts = torch.zeros(count, device=policy.device)
                episode_starts[0] = 1
                actor_shape = (
                    policy.lstm_actor.num_layers,
                    1,
                    policy.lstm_actor.hidden_size,
                )
                actor_zero = torch.zeros(actor_shape, device=policy.device)
                critic_lstm = policy.lstm_critic or policy.lstm_actor
                critic_shape = (
                    critic_lstm.num_layers,
                    1,
                    critic_lstm.hidden_size,
                )
                critic_zero = torch.zeros(critic_shape, device=policy.device)
                states = RNNStates(
                    pi=(actor_zero, actor_zero.clone()),
                    vf=(critic_zero, critic_zero.clone()),
                )
                _values, log_probability, _entropy = policy.evaluate_actions(
                    observations,
                    action_tensor,
                    states,
                    episode_starts,
                )
                loss = -log_probability.mean()
                policy.optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(policy.parameters(), model.max_grad_norm)
                policy.optimizer.step()
                losses.append(float(loss.detach().item()))
                examples += count
                updates += 1
    policy.set_training_mode(False)
    return {
        "updates": updates,
        "examples": examples,
        "mean_loss": sum(losses) / len(losses),
    }


def verify_promotion_candidate(
    rom_path: Path,
    curriculum_directory: Path,
    candidate_path: Path,
    *,
    replay_passes: int,
    cancellation_check: Callable[[], str | None] | None = None,
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
    if not matches(
        _replay_sequence(
            rom_path,
            parent_snapshot,
            actions,
            parent_progress,
            cancellation_check=cancellation_check,
        )
    ):
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
        if not matches(
            _replay_sequence(
                rom_path,
                root_snapshot,
                full_actions,
                root_progress,
                cancellation_check=cancellation_check,
            )
        ):
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


def _warm_start(
    model: Any, learner_path: Path, *, privileged: bool, assisted: bool
) -> dict[str, Any]:
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
        "assisted_memory_and_goal_columns_initialized_to_zero": assisted,
    }


def _render_dashboard_legacy(status: Mapping[str, Any]) -> str:
    best = status.get("best_milestone", {})
    focus = status.get("training_focus", {})
    rewards = status.get("reward_components", {})
    consolidation = status.get("consolidation", {})
    self_taught = status.get("self_taught", {})
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
            (
                "Explorer actions"
                if _is_distilled_student_mode(str(status.get("mode", "")))
                else "Combined actions",
                f"{int(status.get('total_actions', 0)):,}",
            ),
            (
                "Actions / second",
                f"{float(status.get('actions_per_second', 0)):,.1f}",
            ),
            (
                "Best verified milestone",
                html.escape(str(best.get("label", "Power-on"))),
            ),
            (
                "Current lesson",
                html.escape(str(focus.get("label", "Finish the game"))),
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
                "Consolidation start",
                html.escape(str(consolidation.get("active_start_label", "disabled"))),
            ),
            (
                "Consolidation target",
                html.escape(str(consolidation.get("target_label", "disabled"))),
            ),
            (
                "Rolling competence",
                (
                    f"{int(consolidation.get('active_window_successes', 0))}/"
                    f"{int(consolidation.get('active_window_attempts', 0))}"
                ),
            ),
            (
                "Backward gates passed",
                f"{int(consolidation.get('gates_passed_count', 0)):,}",
            ),
            (
                "Self-discovered skills",
                f"{int(self_taught.get('skills_discovered', 0)):,}",
            ),
            (
                "Competent skills",
                f"{int(self_taught.get('skills_competent', 0)):,}",
            ),
            (
                "Weakest skill",
                html.escape(str(self_taught.get("weakest_skill") or "none yet")),
            ),
            (
                "Weakest skill window",
                (
                    f"{int(self_taught.get('weakest_window_successes', 0))}/"
                    f"{int(self_taught.get('weakest_window_attempts', 0))}"
                ),
            ),
            (
                "Self-imitation examples",
                f"{int(self_taught.get('imitation_examples', 0)):,}",
            ),
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
                f"{float(rewards.get('opponent_damage', 0)):,.2f}",
            ),
            (
                "Net active-route credit",
                f"{float(rewards.get('goal_route_progress', 0)):,.2f}",
            ),
            (
                "Navigation-recovery credit",
                f"{float(rewards.get('navigation_recovery', 0)):,.2f}",
            ),
            (
                "New-best Mart approach credit",
                f"{float(rewards.get('mart_approach', 0)):,.2f}",
            ),
            (
                "Mart dialogue-stage credit",
                f"{float(rewards.get('mart_dialogue_progress', 0)):,.2f}",
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


def _render_dashboard(status: Mapping[str, Any]) -> str:
    return render_ppo_dashboard(status)


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
        student_model: Any | None = None,
        student_trainer: SequenceAwareStudentTrainer | None = None,
    ) -> None:
        super().__init__(verbose=0)
        self.run_directory = run_directory
        self.rom_path = rom_path
        self.curriculum_directory = curriculum_directory
        self.config = config
        self.base_elapsed = base_elapsed
        self.started_at = started_at
        self.student_model = student_model
        self.student_trainer = student_trainer
        if _is_distilled_student_mode(config.mode) != (student_model is not None):
            raise ValueError("Distilled-Student mode requires one separate Student model")
        if (student_model is None) != (student_trainer is None):
            raise ValueError("Student model and optimizer must be configured together")
        self.clock_started = time.monotonic()
        self.last_status = 0.0
        self.last_narrative = 0.0
        self.last_checkpoint_step = 0
        self.episodes = 0
        self.reward_components: Counter[str] = Counter()
        self.battle_events: Counter[str] = Counter()
        self.loop_events: Counter[str] = Counter()
        self.episode_end_reasons: Counter[str] = Counter()
        self.explorer_loop_recovery_events: Counter[str] = Counter()
        self.explorer_loop_recovery_active: dict[int, bool] = {}
        self.positions: set[tuple[int, int, int]] = set()
        self.promotion_failures = 0
        self.stop_reason: str | None = None
        self.cached_run_bytes = (
            sum(path.stat().st_size for path in self.run_directory.rglob("*") if path.is_file())
            if _uses_v9_practice(config.mode)
            else 0
        )
        self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
        self.last_v9_disk_budget_refresh = time.monotonic()
        run_manifest = json.loads(
            (self.run_directory / "manifest.json").read_text(encoding="utf-8")
        )
        checkpoint_path = self.run_directory / "checkpoint.json"
        if _uses_pixel_recovery(config.mode) and checkpoint_path.is_file():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            telemetry = _v10_narrative_telemetry(
                checkpoint.get("narrative_telemetry"),
                expected_protocol=_narrative_telemetry_protocol(config.mode),
            )
            self.episodes = telemetry["episodes"]
            self.promotion_failures = telemetry["promotion_failures"]
            self.reward_components = telemetry["reward_components"]
            self.battle_events = telemetry["battle_events"]
            self.loop_events = telemetry["loop_events"]
            self.episode_end_reasons = telemetry["episode_end_reasons"]
            self.explorer_loop_recovery_events = telemetry["explorer_loop_recovery_events"]
            self.positions = telemetry["positions"]
            self.explorer_loop_recovery_active = {
                rank: True for rank in telemetry["active_environment_ranks"]
            }
            self._abandon_active_recoveries("resume")
        self.v7_denominator = (
            dict(run_manifest["v7_denominator"])
            if isinstance(run_manifest.get("v7_denominator"), Mapping)
            else None
        )
        self.consolidation = (
            BackwardConsolidation.from_dict(
                json.loads((self.run_directory / "consolidation.json").read_text(encoding="utf-8"))
            )
            if config.consolidation
            else None
        )
        self.self_skills = (
            SelfTaughtSkillLibrary.from_dict(
                json.loads((self.run_directory / "self-skills.json").read_text(encoding="utf-8"))
            )
            if _is_self_taught_mode(config.mode)
            else None
        )
        self.self_imitation_pending = bool(
            self.self_skills is not None and self.self_skills.imitation_pending
        )
        self.last_student_replay_rollout = (
            -1 if self.self_skills is None else self.self_skills.last_student_replay_rollout
        )
        self.exam_rng = random.Random(config.seed + 80_008)
        if self.self_skills is not None and self.self_skills.exam_rng_state is not None:
            self.exam_rng.setstate(_random_state_from_json(self.self_skills.exam_rng_state))
        self.last_exam_skill_label: str | None = None
        self.student_practice_ledgers: dict[str, StudentPracticeLedger] = {}
        self.student_practice_actions = 0
        self.student_practice_verification_actions = 0
        self.student_practice_training_updates = 0
        self.student_practice_terminal_reasons: Counter[str] = Counter()
        self.last_student_practice_rollout = -1
        practice_path = self.run_directory / "student-practice.json"
        if _uses_v9_practice(config.mode) and practice_path.is_file():
            practice = json.loads(practice_path.read_text(encoding="utf-8"))
            if practice.get("schema_version") != 1 or practice.get("protocol") != (
                "v9-student-closed-loop-practice-state-v1"
            ):
                raise ValueError("V9 Student practice state has the wrong protocol")
            self.student_practice_ledgers = {
                str(item["skill_id"]): StudentPracticeLedger.from_dict(item)
                for item in practice.get("ledgers", [])
            }
            self.student_practice_actions = int(practice.get("emulator_actions", 0))
            self.student_practice_verification_actions = int(
                practice.get("verification_actions", 0)
            )
            self.student_practice_training_updates = int(practice.get("training_updates", 0))
            self.student_practice_terminal_reasons = _v9_practice_terminal_reason_counts(
                practice.get("terminal_reasons")
            )
            self.last_student_practice_rollout = int(practice.get("last_explorer_rollout", -1))
        self.v12_learning: dict[str, Any] | None = None
        v12_learning_path = self.run_directory / "v12-learning.json"
        if _is_v12_mode(config.mode):
            if not v12_learning_path.is_file():
                raise ValueError("V12 run has no hindsight learning state")
            self.v12_learning = _validate_v12_learning_state(
                json.loads(v12_learning_path.read_text(encoding="utf-8"))
            )
            for item in self.v12_learning["pending_lessons"]:
                path = self.run_directory / str(item["file"])
                if not path.is_file() or _sha256_file(path) != item["sha256"]:
                    raise ValueError("V12 pending hindsight lesson failed its recorded hash")

    def _write_v12_learning(self) -> None:
        if self.v12_learning is None:
            return
        self.v12_learning["updated_at"] = datetime.now(UTC).isoformat()
        validated = _validate_v12_learning_state(self.v12_learning)
        _atomic_json(self.run_directory / "v12-learning.json", validated)

    def _collect_v12_hindsight(self) -> None:
        if self.v12_learning is None:
            return
        if self.v12_learning["pending_lessons"]:
            raise RuntimeError("V12 cannot overwrite untrained hindsight lessons")
        buffer = self.model.rollout_buffer
        observations = buffer.observations
        if not isinstance(observations, Mapping):
            raise RuntimeError("V12 requires a dictionary recurrent rollout buffer")
        lessons = extract_hindsight_lessons(
            np.asarray(observations["pixels"]),
            np.asarray(observations["action_history"]),
            np.asarray(buffer.actions),
            np.asarray(buffer.episode_starts),
            HindsightConfig(
                max_lessons=self.config.hindsight_max_lessons,
                min_actions=self.config.hindsight_min_actions,
                max_actions=self.config.hindsight_max_actions,
                min_changed_fraction=self.config.hindsight_min_changed_fraction,
                min_mean_absolute_error=(self.config.hindsight_min_mean_absolute_error),
            ),
        )
        self.v12_learning["rollouts_observed"] += 1
        if lessons:
            self.v12_learning["rollouts_with_lessons"] += 1
        pending: list[dict[str, Any]] = []
        rollout = int(self.v12_learning["rollouts_observed"])
        for index, lesson in enumerate(lessons):
            relative = Path("hindsight") / (
                f"pending-rollout-{rollout:08d}-lesson-{index:03d}.npz"
            )
            path = self.run_directory / relative
            _atomic_self_imitation_dataset(path, lesson.dataset())
            pending.append(
                {
                    **lesson.public_dict(),
                    "file": relative.as_posix(),
                    "sha256": _sha256_file(path),
                    "stored_bytes": path.stat().st_size,
                }
            )
        self.v12_learning["lessons_generated"] += len(pending)
        self.v12_learning["pending_lessons"] = pending
        self._write_v12_learning()
        with (self.run_directory / "hindsight" / "audit.jsonl").open(
            "a", encoding="utf-8"
        ) as output:
            output.write(
                json.dumps(
                    {
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "rollout": rollout,
                        "total_actions": self.model.num_timesteps,
                        "lessons": pending,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    def _train_pending_v12_hindsight(self) -> bool:
        if self.v12_learning is None or not self.v12_learning["pending_lessons"]:
            return False
        pending = list(self.v12_learning["pending_lessons"])
        paths: list[Path] = []
        for item in pending:
            path = self.run_directory / str(item["file"])
            if not path.is_file() or _sha256_file(path) != item["sha256"]:
                raise ValueError("V12 pending hindsight lesson changed before training")
            paths.append(path)
        result = _train_self_imitation_policy(
            self.model,
            paths,
            epochs=self.config.hindsight_epochs,
        )
        self.v12_learning["lessons_trained"] += len(paths)
        self.v12_learning["examples_trained"] += int(result["examples"])
        self.v12_learning["optimizer_updates"] += int(result["updates"])
        self.v12_learning["last_mean_loss"] = float(result["mean_loss"])
        self.v12_learning["pending_lessons"] = []
        self._write_v12_learning()
        for path in paths:
            path.unlink(missing_ok=True)
        return True

    def _write_consolidation(self) -> None:
        if self.consolidation is not None:
            _atomic_json(
                self.run_directory / "consolidation.json",
                self.consolidation.public_dict(),
            )

    def _consolidation_status(self) -> dict[str, Any]:
        if self.consolidation is None:
            return {"enabled": False}
        window = self.consolidation.active_window
        return {
            "enabled": True,
            "active_start_index": self.consolidation.active_start_index,
            "active_start_label": _milestone_label(self.consolidation.active_start_index),
            "target_index": self.consolidation.target_index,
            "target_label": _milestone_label(self.consolidation.target_index),
            "active_window_successes": sum(window),
            "active_window_attempts": len(window),
            "active_window_rate": self.consolidation.active_window_rate,
            "required_window": self.consolidation.window_size,
            "required_rate": self.consolidation.threshold,
            "gates_passed_count": len(self.consolidation.gates_passed),
            "power_on_training_gate_passed": (self.consolidation.power_on_training_gate_passed),
        }

    def _explorer_loop_recovery_status(self) -> dict[str, Any]:
        if not _uses_pixel_recovery(self.config.mode):
            return {"enabled": False}
        started = self.explorer_loop_recovery_events["windows_started"]
        escaped = self.explorer_loop_recovery_events["escapes"]
        context_changes = self.explorer_loop_recovery_events["context_changes"]
        expirations = self.explorer_loop_recovery_events["expirations"]
        completed = escaped + context_changes + expirations
        abandoned_on_resume = self.explorer_loop_recovery_events["abandoned_on_resume"]
        abandoned_on_episode_end = self.explorer_loop_recovery_events["abandoned_on_episode_end"]
        abandoned_on_campaign_end = self.explorer_loop_recovery_events["abandoned_on_campaign_end"]
        abandoned = abandoned_on_resume + abandoned_on_episode_end + abandoned_on_campaign_end
        active = sum(self.explorer_loop_recovery_active.values())
        return {
            "enabled": True,
            "protocol": PIXEL_LOOP_RECOVERY_PROTOCOL,
            "window_actions": self.config.explorer_recovery_window_actions,
            "blocked_repeat_threshold": self.config.explorer_recovery_blocked_threshold,
            "cycle_window_actions": V10_RECOVERY_CYCLE_WINDOW,
            "cycle_unique_limit": V10_RECOVERY_CYCLE_UNIQUE_LIMIT,
            "long_stagnation_actions": V10_RECOVERY_STAGNATION_ACTIONS,
            "escape_confirmations": self.config.explorer_recovery_escape_confirmations,
            "ineffective_change_fraction": (
                self.config.explorer_recovery_ineffective_change_fraction
            ),
            "ineffective_mean_absolute_error": (
                self.config.explorer_recovery_ineffective_mean_absolute_error
            ),
            "escape_change_fraction": self.config.explorer_recovery_escape_change_fraction,
            "escape_mean_absolute_error": (
                self.config.explorer_recovery_escape_mean_absolute_error
            ),
            "blocked_penalty": self.config.explorer_recovery_blocked_penalty,
            "escape_credit": self.config.explorer_recovery_escape_reward,
            "context_change_credit": 0.0,
            "expiration_penalty": self.config.explorer_recovery_expiration_penalty,
            "windows_started": started,
            "blocked_repeat_triggers": self.explorer_loop_recovery_events[
                "blocked_repeat_triggers"
            ],
            "visual_cycle_triggers": self.explorer_loop_recovery_events["visual_cycle_triggers"],
            "progress_stagnation_triggers": self.explorer_loop_recovery_events[
                "progress_stagnation_triggers"
            ],
            "escapes": escaped,
            "context_changes": context_changes,
            "expirations": expirations,
            "completed_windows": completed,
            "escape_rate": 0.0 if completed == 0 else escaped / completed,
            "abandoned_on_resume": abandoned_on_resume,
            "abandoned_on_episode_end": abandoned_on_episode_end,
            "abandoned_on_campaign_end": abandoned_on_campaign_end,
            "abandoned_windows": abandoned,
            "unresolved_windows": max(0, started - completed - abandoned - active),
            "actions": self.explorer_loop_recovery_events["actions"],
            "blocked_direction_attempts": self.explorer_loop_recovery_events[
                "blocked_direction_attempts"
            ],
            "repeated_blocked_attempts": self.explorer_loop_recovery_events[
                "repeated_blocked_attempts"
            ],
            "active_environments": active,
            "actor_action_overrides": 0,
            "uses_authored_guidance": False,
            "episode_local_state": True,
            "resume_behavior": "fresh_rollout_counts_inflight_windows_abandoned",
        }

    def _v12_learning_status(self) -> dict[str, Any]:
        if self.v12_learning is None:
            return {"enabled": False}
        rollouts = int(self.v12_learning["rollouts_observed"])
        lessons = int(self.v12_learning["lessons_generated"])
        return {
            "enabled": True,
            "protocol": HINDSIGHT_PROTOCOL,
            "rollouts_observed": rollouts,
            "rollouts_with_lessons": int(self.v12_learning["rollouts_with_lessons"]),
            "lessons_generated": lessons,
            "lessons_trained": int(self.v12_learning["lessons_trained"]),
            "examples_trained": int(self.v12_learning["examples_trained"]),
            "optimizer_updates": int(self.v12_learning["optimizer_updates"]),
            "pending_lessons": len(self.v12_learning["pending_lessons"]),
            "last_mean_loss": self.v12_learning["last_mean_loss"],
            "lessons_per_rollout": lessons / rollouts if rollouts else 0.0,
            "terminal_evaluation": self.v12_learning["terminal_evaluation"],
            "human_demonstration_examples": 0,
            "imported_action_examples": 0,
            "online_decision_model_calls": 0,
        }

    def _abandon_active_recoveries(self, reason: str) -> int:
        if reason not in {"resume", "campaign_end"}:
            raise ValueError("Explorer recovery abandonment reason is unsupported")
        active_ranks = [
            rank for rank, active in self.explorer_loop_recovery_active.items() if active
        ]
        if active_ranks:
            self.explorer_loop_recovery_events[f"abandoned_on_{reason}"] += len(active_ranks)
            for rank in active_ranks:
                self.explorer_loop_recovery_active[rank] = False
        return len(active_ranks)

    def _record_explorer_loop_recovery(self, info: Mapping[str, Any]) -> None:
        recovery = info.get("explorer_loop_recovery")
        if not isinstance(recovery, Mapping):
            return
        submitted = recovery.get("submitted_action")
        executed = recovery.get("executed_action")
        if submitted != executed:
            raise RuntimeError("Explorer loop recovery changed the PPO-selected action")
        rank = info.get("rank")
        if isinstance(rank, int):
            self.explorer_loop_recovery_active[rank] = bool(recovery.get("active", False))
        if recovery.get("recovery_action") is True:
            self.explorer_loop_recovery_events["actions"] += 1
        if recovery.get("blocked_direction_attempt") is True:
            self.explorer_loop_recovery_events["blocked_direction_attempts"] += 1
        if recovery.get("repeated_blocked_attempt") is True:
            self.explorer_loop_recovery_events["repeated_blocked_attempts"] += 1
        recovery_event = recovery.get("event")
        if recovery_event == "started":
            self.explorer_loop_recovery_events["windows_started"] += 1
            trigger = recovery.get("trigger")
            if trigger in RECOVERY_TRIGGERS:
                self.explorer_loop_recovery_events[f"{trigger}_triggers"] += 1
        elif recovery_event == "escaped":
            self.explorer_loop_recovery_events["escapes"] += 1
        elif recovery_event == "context_changed":
            self.explorer_loop_recovery_events["context_changes"] += 1
        elif recovery_event == "expired":
            self.explorer_loop_recovery_events["expirations"] += 1
        if info.get("episode_end") is True and recovery.get("active") is True:
            self.explorer_loop_recovery_events["abandoned_on_episode_end"] += 1
            if isinstance(rank, int):
                self.explorer_loop_recovery_active[rank] = False

    def _write_self_skills(self) -> None:
        if self.self_skills is not None:
            _atomic_json(
                self.run_directory / "self-skills.json",
                self.self_skills.public_dict(),
            )

    def _write_student_practice(self) -> None:
        if not _uses_v9_practice(self.config.mode):
            return
        _atomic_json(
            self.run_directory / "student-practice.json",
            {
                "schema_version": 1,
                "protocol": "v9-student-closed-loop-practice-state-v1",
                "updated_at": datetime.now(UTC).isoformat(),
                "last_explorer_rollout": self.last_student_practice_rollout,
                "emulator_actions": self.student_practice_actions,
                "verification_actions": self.student_practice_verification_actions,
                "training_updates": self.student_practice_training_updates,
                "terminal_reasons": dict(sorted(self.student_practice_terminal_reasons.items())),
                "ledgers": [
                    ledger.public_dict()
                    for _skill_id, ledger in sorted(self.student_practice_ledgers.items())
                ],
            },
        )

    def _self_taught_status(self) -> dict[str, Any]:
        if self.self_skills is None:
            return {"enabled": False}
        competent = sum(bool(skill.get("competent", False)) for skill in self.self_skills.skills)
        weakest = self.self_skills.weakest_skills()
        active = weakest[0] if weakest else None
        window = [] if active is None else [bool(value) for value in active.get("window", [])]
        original_actions = sum(
            int(skill.get("original_action_count", skill["action_count"]))
            for skill in self.self_skills.skills
        )
        distilled_actions = sum(int(skill["action_count"]) for skill in self.self_skills.skills)
        sharded_skills = [skill for skill in self.self_skills.skills if skill.get("replay_shards")]
        replay_cursors = [int(skill.get("replay_cursor", 0)) for skill in sharded_skills]
        coverage_cycles = [
            int(skill.get("replay_cursor", 0)) // len(skill["replay_shards"])
            for skill in sharded_skills
        ]
        report = self.self_skills.last_student_report or {}
        diagnostics = dict(report.get("diagnostics", {}))
        competence_losses = sum(
            int(skill.get("competence_losses", 0)) for skill in self.self_skills.skills
        )
        composition_window = [bool(result) for result in self.self_skills.composition_window]
        deepest_distilled = max(
            self.self_skills.skills,
            key=lambda skill: int(skill["target_index"]),
            default=None,
        )
        deepest_competent = max(
            (skill for skill in self.self_skills.skills if bool(skill.get("competent", False))),
            key=lambda skill: int(skill["target_index"]),
            default=None,
        )
        return {
            "enabled": True,
            "skills_discovered": len(self.self_skills.skills),
            "skills_competent": competent,
            "rehearsal_attempts": self.self_skills.total_rehearsal_attempts,
            "rehearsal_successes": self.self_skills.total_rehearsal_successes,
            "weakest_skill": None if active is None else active.get("target_label"),
            "weakest_window_successes": sum(window),
            "weakest_window_attempts": len(window),
            "imitation_updates": self.self_skills.imitation_updates,
            "imitation_examples": self.self_skills.imitation_examples,
            "last_imitation_loss": self.self_skills.last_imitation_loss,
            "imitation_pending": self.self_skills.imitation_pending,
            "distillation": {
                "original_actions": original_actions,
                "distilled_actions": distilled_actions,
                "skills_distilled": sum(
                    skill.get("distillation_audit_file") is not None
                    for skill in self.self_skills.skills
                ),
                "compression_ratio": (
                    distilled_actions / original_actions if original_actions else 1.0
                ),
                "best_index": (
                    None if deepest_distilled is None else int(deepest_distilled["target_index"])
                ),
                "best_label": (
                    None if deepest_distilled is None else deepest_distilled["target_label"]
                ),
                "total_oracle_calls": sum(
                    int(skill.get("distillation_oracle_calls", 0))
                    for skill in self.self_skills.skills
                ),
                "oracle_actions_replayed": sum(
                    int(skill.get("distillation_oracle_actions_replayed", 0))
                    for skill in self.self_skills.skills
                ),
                "edits_accepted": sum(
                    int(skill.get("distillation_edits_accepted", 0))
                    for skill in self.self_skills.skills
                ),
                "edits_rejected": sum(
                    int(skill.get("distillation_edits_rejected", 0))
                    for skill in self.self_skills.skills
                ),
            },
            "student": {
                "state": (
                    "not_applicable"
                    if not _is_distilled_student_mode(self.config.mode)
                    else (
                        "training_from_self_discoveries"
                        if self.self_skills.skills
                        else "waiting_for_first_discovery"
                    )
                ),
                "training_rounds": self.self_skills.student_training_rounds,
                "optimizer_updates": self.self_skills.student_updates,
                "examples": self.self_skills.student_examples,
                "diagnostics": diagnostics,
                "replay_memory": {
                    "individual_skill_datasets": int(report.get("individual_skill_datasets", 0)),
                    "active_composition_datasets": int(report.get("composition_datasets", 0)),
                    "retained_examples": int(report.get("replay_examples_retained", 0)),
                    "retained_bytes": int(report.get("replay_bytes_retained", 0)),
                    "max_examples_per_individual_skill": int(
                        report.get("max_examples_per_individual_skill", 0)
                    ),
                    "retained_example_ceiling": int(report.get("replay_example_ceiling", 0)),
                    "train_example_ceiling": int(report.get("replay_train_example_ceiling", 0)),
                    "sampling_cycle_size": int(report.get("sampling_cycle_size", 0)),
                    "skill_shards_total": sum(
                        len(skill["replay_shards"]) for skill in sharded_skills
                    ),
                    "skill_shards_loaded": int(report.get("replay_shards_loaded", 0)),
                    "shard_examples_loaded": int(report.get("replay_shard_examples_loaded", 0)),
                    "shard_train_examples_loaded": int(
                        report.get("replay_shard_train_examples_loaded", 0)
                    ),
                    "shard_context_examples_loaded": int(
                        report.get("replay_shard_context_examples_loaded", 0)
                    ),
                    "shard_bytes_read": int(report.get("replay_shard_bytes_read", 0)),
                    "full_skill_artifacts_opened": int(
                        report.get("replay_full_skill_artifacts_opened", 0)
                    ),
                    "cursor_min": min(replay_cursors, default=0),
                    "cursor_max": max(replay_cursors, default=0),
                    "minimum_completed_coverage_cycles": int(min(coverage_cycles, default=0)),
                    "shard_selections": list(report.get("replay_shard_selections", [])),
                },
            },
            "frozen_exams": {
                "rounds": self.self_skills.frozen_exam_rounds,
                "attempts": self.self_skills.total_rehearsal_attempts,
                "successes": self.self_skills.total_rehearsal_successes,
                "actions": self.self_skills.frozen_exam_actions,
                "next_at_action": (
                    self.self_skills.last_frozen_exam_actions
                    + self.config.frozen_exam_interval_actions
                ),
                "current_skill": self.last_exam_skill_label,
                "competence_losses": competence_losses,
                "best_competent_index": (
                    None if deepest_competent is None else int(deepest_competent["target_index"])
                ),
                "best_competent_label": (
                    None if deepest_competent is None else deepest_competent["target_label"]
                ),
            },
            "composition": {
                "attempts": self.self_skills.composition_attempts,
                "successes": self.self_skills.composition_successes,
                "window_attempts": len(composition_window),
                "window_successes": sum(composition_window),
                "best_index": self.self_skills.best_composition_index,
                "best_label": _milestone_label(self.self_skills.best_composition_index),
                "hall_of_fame_completions": (self.self_skills.hall_of_fame_completions),
                "training_datasets": len(self.self_skills.active_composition_replays()),
                "archived_training_datasets": len(self.self_skills.composition_replays)
                - len(self.self_skills.active_composition_replays()),
                "training_actions": sum(
                    int(item["action_count"])
                    for item in self.self_skills.active_composition_replays()
                ),
                "build_failures": sum(
                    outcome == "replay_failed"
                    for outcome in self.self_skills.composition_build_outcomes.values()
                ),
            },
        }

    def _student_practice_status(self) -> dict[str, Any]:
        if not _uses_v9_practice(self.config.mode):
            return {"enabled": False}
        ledgers = list(self.student_practice_ledgers.values())
        active = next((ledger for ledger in ledgers if not ledger.curriculum_complete), None)
        attempts = sum(ledger.attempts for ledger in ledgers)
        successes = sum(ledger.successes for ledger in ledgers)
        retained = sum(len(rung.successful_rollouts) for ledger in ledgers for rung in ledger.rungs)
        completed = sum(ledger.curriculum_complete for ledger in ledgers)
        report = (
            {}
            if self.self_skills is None or self.self_skills.last_student_report is None
            else self.self_skills.last_student_report
        )
        return {
            "enabled": True,
            "protocol": "v9-student-closed-loop-practice-state-v1",
            "skills_with_ladders": len(ledgers),
            "skills_completed": completed,
            "attempts": attempts,
            "successes": successes,
            "success_rate": successes / attempts if attempts else 0.0,
            "emulator_actions": self.student_practice_actions,
            "verification_actions": self.student_practice_verification_actions,
            "training_updates": self.student_practice_training_updates,
            "terminal_reasons": dict(sorted(self.student_practice_terminal_reasons.items())),
            "promotion_window": self.config.student_practice_window,
            "promotion_required_successes": self.config.student_practice_required,
            "promotion_confirmations": self.config.student_practice_confirmations,
            "retention_fraction": self.config.student_practice_retention,
            "retained_success_rollouts": retained,
            "aggregated_datasets_loaded_last_round": int(
                report.get("practice_replay_datasets_loaded", 0)
            ),
            "aggregated_train_examples_last_round": int(
                report.get("practice_replay_train_examples_loaded", 0)
            ),
            "aggregated_bytes_read_last_round": int(report.get("practice_replay_bytes_read", 0)),
            "active_skill_id": None if active is None else active.skill_id,
            "active_rung_index": None if active is None else active.active_rung_index,
            "active_remaining_actions": (
                None
                if active is None or active.active_rung is None
                else active.active_rung.remaining_actions
            ),
            "closed_loop": True,
            "success_only_gradient": True,
            "recurrent_state_reset_each_attempt": True,
            "recovery_ppo": "gated_future_escalation_not_active",
        }

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
        run_manifest = json.loads(
            (self.run_directory / "manifest.json").read_text(encoding="utf-8")
        )
        checkpoint: dict[str, Any] = {
            "schema_version": 1,
            "protocol": _ppo_protocol(self.config.mode),
            "reward_protocol": _ppo_reward_protocol(self.config.mode),
            "model_file_sha256": _sha256_file(latest),
            "total_actions": self.model.num_timesteps,
            "elapsed_seconds": self.elapsed(),
            "config": self.config.public_dict(),
            "source": run_manifest["source"],
            "rom": run_manifest["rom"],
            "best_milestone": _load_curriculum_manifest(self.curriculum_directory)[
                "best_milestone"
            ],
            "novelty_files": novelty_files,
            "resume_semantics": "model_optimizer_exact_environment_rollout_restarts",
        }
        if _uses_pixel_recovery(self.config.mode):
            checkpoint["narrative_telemetry"] = {
                "protocol": _narrative_telemetry_protocol(self.config.mode),
                "episodes": self.episodes,
                "promotion_failures": self.promotion_failures,
                "reward_components": dict(sorted(self.reward_components.items())),
                "battle_events": dict(sorted(self.battle_events.items())),
                "loop_events": dict(sorted(self.loop_events.items())),
                "episode_end_reasons": dict(sorted(self.episode_end_reasons.items())),
                "explorer_loop_recovery_events": dict(
                    sorted(self.explorer_loop_recovery_events.items())
                ),
                "positions": [list(item) for item in sorted(self.positions)],
                "active_environment_ranks": sorted(
                    rank for rank, active in self.explorer_loop_recovery_active.items() if active
                ),
                "episode_local_recovery_state_persisted": False,
            }
        if self.v12_learning is not None:
            self._write_v12_learning()
            learning_path = self.run_directory / "v12-learning.json"
            checkpoint.update(
                {
                    "v12_learning_file": learning_path.name,
                    "v12_learning_file_sha256": _sha256_file(learning_path),
                    "hindsight_pending_lessons": len(
                        self.v12_learning["pending_lessons"]
                    ),
                    "online_decision_model_calls": 0,
                    "network_gameplay_calls": 0,
                }
            )
        if isinstance(run_manifest.get("v7_denominator"), Mapping):
            checkpoint["v7_denominator"] = dict(run_manifest["v7_denominator"])
        if self.student_model is not None and self.student_trainer is not None:
            student_latest = self.run_directory / "student-latest.zip"
            student_previous = self.run_directory / "student-previous.zip"
            student_temporary = self.run_directory / "student-checkpoint.tmp.zip"
            self.student_model.save(student_temporary)
            if student_latest.exists():
                os.replace(student_latest, student_previous)
            os.replace(student_temporary, student_latest)
            optimizer_path = self.run_directory / "student-optimizer.pt"
            optimizer_previous = self.run_directory / "student-optimizer.previous.pt"
            if optimizer_path.exists():
                os.replace(optimizer_path, optimizer_previous)
            _atomic_torch_checkpoint(
                optimizer_path,
                self.student_trainer.optimizer_state_dict(),
            )
            checkpoint.update(
                {
                    "student_model_file": student_latest.name,
                    "student_model_file_sha256": _sha256_file(student_latest),
                    "student_optimizer_file": optimizer_path.name,
                    "student_optimizer_file_sha256": _sha256_file(optimizer_path),
                    "student_training_isolated_from_ppo": True,
                }
            )
        if self.consolidation is not None:
            self._write_consolidation()
            checkpoint["consolidation_file_sha256"] = _sha256_file(
                self.run_directory / "consolidation.json"
            )
        if self.self_skills is not None:
            self._write_self_skills()
            checkpoint.update(_checkpoint_self_skill_state(self.run_directory))
        if _uses_v9_practice(self.config.mode):
            self._write_student_practice()
            checkpoint.update(_checkpoint_student_practice_state(self.run_directory))
        checkpoint.update(
            _checkpoint_curriculum_state(
                self.run_directory,
                self.curriculum_directory,
                protocol=_ppo_protocol(self.config.mode),
            )
        )
        _atomic_json(
            self.run_directory / "checkpoint.json",
            checkpoint,
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
        best_index = int(manifest["best_milestone"]["index"])
        next_milestone = MILESTONES[best_index] if best_index < len(MILESTONES) else None
        elapsed = self.elapsed()
        rollout_size = self.config.rollout_steps * self.config.environments
        if refresh_disk:
            self.cached_run_bytes = sum(
                path.stat().st_size for path in self.run_directory.rglob("*") if path.is_file()
            )
            self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
        checkpoint_hashes: dict[str, str] = {}
        checkpoint_path = self.run_directory / "checkpoint.json"
        if checkpoint_path.is_file():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            explorer_hash = checkpoint.get("model_file_sha256")
            student_hash = checkpoint.get("student_model_file_sha256")
            if isinstance(explorer_hash, str):
                checkpoint_hashes["explorer_sha256"] = explorer_hash
            if isinstance(student_hash, str):
                checkpoint_hashes["student_sha256"] = student_hash
        status = {
            "schema_version": 1,
            "protocol": _ppo_protocol(self.config.mode),
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
            "milestone_count": len(MILESTONES),
            "training_focus": (
                {
                    "key": next_milestone.key,
                    "label": next_milestone.label,
                    "chapter": next_milestone.chapter,
                    "kind": next_milestone.kind,
                }
                if next_milestone is not None
                else {"key": HALL_OF_FAME_KEY, "label": "Hall of Fame complete"}
            ),
            "curriculum_entries": len(manifest["entries"]),
            "verified_promotions": manifest.get("verified_promotions", 0),
            "promotion_failures": self.promotion_failures,
            "unique_positions": len(self.positions),
            "reward_components": dict(sorted(self.reward_components.items())),
            "battle_events": dict(sorted(self.battle_events.items())),
            "loop_events": dict(sorted(self.loop_events.items())),
            "episode_end_reasons": dict(sorted(self.episode_end_reasons.items())),
            "explorer_loop_recovery": self._explorer_loop_recovery_status(),
            "hindsight_learning": self._v12_learning_status(),
            "consolidation": self._consolidation_status(),
            "self_taught": self._self_taught_status(),
            "student_practice": self._student_practice_status(),
            "checkpoints": checkpoint_hashes,
            **({"v7_denominator": self.v7_denominator} if self.v7_denominator is not None else {}),
            "policy_roles": (
                {
                    "explorer": "online PPO discovery",
                    "student": "offline distilled self-replay",
                    "shared_parameters": False,
                    "competence_source": "frozen Student exams",
                }
                if _is_distilled_student_mode(self.config.mode)
                else (
                    {
                        "actor": "one recurrent goal-conditioned policy",
                        "online_ppo": "learns from every sampled consequence",
                        "hindsight": "relabels its own future visual states as local goals",
                        "verified_skills": "rehearses replay-verified rare discoveries",
                        "shared_parameters": True,
                        "competence_source": "deterministic no-update checkpoint exams",
                    }
                    if _is_v12_mode(self.config.mode)
                    else {"explorer_and_student": "one shared policy"}
                )
            ),
            "reward_protocol": _ppo_reward_protocol(self.config.mode),
            "novelty_scope": "persistent per worker across episodes and resumes",
            "information_boundary": (
                "pixels + three recent actions; trainer-only RAM rewards and loop termination"
                if self.config.mode == "pixels"
                else (
                    "Explorer: pixels + three recent actions. Separate Student: the same input "
                    "plus a three-frame self-observed goal clip. Trainer-only RAM grades rewards, "
                    "replays, and exams and switches among self-generated goal clips at declared "
                    "milestone endpoints during composition; no imported actions, route graph, "
                    "coordinates, or authored quest plan"
                    + (
                        ". Explorer loop recovery reads only rendered pixels and the exact "
                        "policy-selected action; it supplies no direction and never replaces, "
                        "masks, or chooses a button"
                        if _uses_pixel_recovery(self.config.mode)
                        else ""
                    )
                    if _is_distilled_student_mode(self.config.mode)
                    else (
                        "One recurrent actor: current/previous pixels + three recent actions + "
                        "a self-observed goal frame. During open exploration the goal is blank; "
                        "afterward, future frames from the actor's own rollout become hindsight "
                        "goals. Trainer-only RAM grades durable consequences and verifies rare "
                        "promotions, but no RAM, maps, coordinates, route, walkthrough, LLM "
                        "output, or imported action reaches the actor. Pixel recovery never "
                        "chooses or replaces a button"
                        if _is_v12_mode(self.config.mode)
                        else (
                        "pixels + three recent actions + a self-discovered target screen; "
                        "trainer-only RAM retains V7's historical route/Mart/milestone watchdog "
                        "shaping; no imported actions, actor-visible route graph, or target "
                        "coordinates"
                        if _is_self_taught_mode(self.config.mode)
                        else (
                            "pixels + three recent actions + trainer-built visited map + "
                            "active goal/skill "
                            "+ next certified route map; assisted teacher lane"
                            if self.config.mode == "assisted"
                            else "pixels + three recent actions + disclosed RAM state comparator"
                        )
                        )
                    )
                )
            ),
            "resume_semantics": (
                "exact Explorer PPO and separate Student optimizer; fresh environment rollouts"
                if _is_distilled_student_mode(self.config.mode)
                else "exact model/optimizer; fresh environment rollouts"
            ),
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
        student_accuracy = float(
            status["self_taught"]
            .get("student", {})
            .get("diagnostics", {})
            .get("action_accuracy", 0)
        )
        path = self.run_directory / "NARRATIVE.md"
        first = not path.exists()
        action_label = (
            "Explorer actions"
            if _is_distilled_student_mode(self.config.mode)
            else "Combined actions"
        )
        exam_actor_label = "V12 checkpoint" if _is_v12_mode(self.config.mode) else "Student"
        hindsight = status.get("hindsight_learning", {})
        recovery = status.get("explorer_loop_recovery", {})
        if _uses_pixel_recovery(self.config.mode):
            loop_lines = (
                f"- Visual-loop detections: {status['loop_events'].get('visual_cycle', 0):,}\n"
                "- Long-stagnation detections: "
                f"{status['loop_events'].get('progress_stagnation', 0):,}\n\n"
            )
            recovery_lines = (
                f"- Recovery windows opened: {recovery.get('windows_started', 0):,}\n"
                f"- Blocked-repeat triggers: {recovery.get('blocked_repeat_triggers', 0):,}\n"
                f"- Visual-cycle triggers: {recovery.get('visual_cycle_triggers', 0):,}\n"
                "- Long-stagnation triggers: "
                f"{recovery.get('progress_stagnation_triggers', 0):,}\n"
                f"- Credited policy escapes: {recovery.get('escapes', 0):,}\n"
                f"- No-credit context changes: {recovery.get('context_changes', 0):,}\n"
                f"- Recovery expirations: {recovery.get('expirations', 0):,}\n"
                f"- Completed recovery windows: {recovery.get('completed_windows', 0):,}\n"
                f"- Active recovery environments: {recovery.get('active_environments', 0):,}\n"
                f"- Abandoned recovery windows: {recovery.get('abandoned_windows', 0):,}\n"
                f"- Abandoned on resume: {recovery.get('abandoned_on_resume', 0):,}\n"
                "- Abandoned at episode end: "
                f"{recovery.get('abandoned_on_episode_end', 0):,}\n"
                "- Abandoned at campaign end: "
                f"{recovery.get('abandoned_on_campaign_end', 0):,}\n"
                f"- Unresolved inactive windows: {recovery.get('unresolved_windows', 0):,}\n"
                f"- Recovery actions: {recovery.get('actions', 0):,}\n"
                f"- Trainer-selected buttons: {recovery.get('actor_action_overrides', 0):,}\n\n"
            )
        else:
            loop_lines = (
                f"- Visual loops terminated: {status['loop_events'].get('visual_cycle', 0):,}\n"
                "- Long stagnations terminated: "
                f"{status['loop_events'].get('progress_stagnation', 0):,}\n\n"
            )
            recovery_lines = ""
        with path.open("a", encoding="utf-8") as output:
            if first:
                output.write("# Parallel PPO learning chronicle\n\n")
            output.write(
                f"## {datetime.now(UTC).isoformat()} — {event}\n\n"
                f"- Best verified milestone: **{status['best_milestone']['label']}**\n"
                f"- Current lesson: **{status['training_focus']['label']}**\n"
                f"- {action_label}: {status['total_actions']:,}\n"
                f"- PPO updates: {status['ppo_updates']:,}\n"
                f"- Verified promotions: {status['verified_promotions']:,}\n"
                f"- Episodes: {status['episodes']:,}\n"
                f"- Unique map positions: {status['unique_positions']:,}\n\n"
                f"- Consolidation start: "
                f"**{status['consolidation'].get('active_start_label', 'disabled')}**\n"
                f"- Consolidation target: "
                f"**{status['consolidation'].get('target_label', 'disabled')}**\n"
                f"- Rolling training competence: "
                f"{status['consolidation'].get('active_window_successes', 0)}/"
                f"{status['consolidation'].get('active_window_attempts', 0)}\n"
                f"- Backward gates passed: "
                f"{status['consolidation'].get('gates_passed_count', 0)}\n\n"
                f"- Self-discovered skills: "
                f"{status['self_taught'].get('skills_discovered', 0)}\n"
                f"- Competent self-discovered skills: "
                f"{status['self_taught'].get('skills_competent', 0)}\n"
                f"- Self-imitation examples: "
                f"{status['self_taught'].get('imitation_examples', 0):,}\n\n"
                f"- Hindsight lessons generated: "
                f"{hindsight.get('lessons_generated', 0):,}\n"
                f"- Hindsight lessons trained: "
                f"{hindsight.get('lessons_trained', 0):,}\n"
                f"- Hindsight action examples: "
                f"{hindsight.get('examples_trained', 0):,}\n"
                f"- Online decision-model calls: "
                f"{hindsight.get('online_decision_model_calls', 0):,}\n\n"
                f"- Distilled self-generated actions: "
                f"{status['self_taught'].get('distillation', {}).get('distilled_actions', 0):,}/"
                f"{status['self_taught'].get('distillation', {}).get('original_actions', 0):,}\n"
                f"- Separate Student updates: "
                f"{status['self_taught'].get('student', {}).get('optimizer_updates', 0):,}\n"
                f"- Separate Student action accuracy: "
                f"{student_accuracy:.1%}\n"
                f"- Frozen {exam_actor_label} exams: "
                f"{status['self_taught'].get('frozen_exams', {}).get('successes', 0)}/"
                f"{status['self_taught'].get('frozen_exams', {}).get('attempts', 0)}\n"
                f"- Power-on composition exams: "
                f"{status['self_taught'].get('composition', {}).get('successes', 0)}/"
                f"{status['self_taught'].get('composition', {}).get('attempts', 0)}\n\n"
                f"- Battle successes: {status['battle_events'].get('success', 0):,}\n"
                "- Battle exits without durable progress: "
                f"{status['battle_events'].get('ended_without_progress', 0):,}\n\n"
                f"- Opponent-damage credit: "
                f"{status['reward_components'].get('opponent_damage', 0):,.2f}\n"
                f"- Net active-route credit: "
                f"{status['reward_components'].get('goal_route_progress', 0):,.2f}\n"
                f"- Navigation-recovery credit: "
                f"{status['reward_components'].get('navigation_recovery', 0):,.2f}\n"
                f"- New-best Mart approach credit: "
                f"{status['reward_components'].get('mart_approach', 0):,.2f}\n"
                f"- Mart dialogue-stage credit: "
                f"{status['reward_components'].get('mart_dialogue_progress', 0):,.2f}\n"
                f"{loop_lines}"
                f"{recovery_lines}"
            )

    def _admit_v9_split_boundaries(
        self,
        graph: Any,
        hits: tuple[_V9FirstHit, ...],
        *,
        source_entry_id: str,
        final_entry_id: str,
        full_actions: Sequence[int],
        source_prefix_length: int,
    ) -> tuple[str, ...]:
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        existing = {str(item["entry_id"]): item for item in manifest["entries"]}
        if source_entry_id not in existing or final_entry_id not in existing:
            raise ValueError("V9 split commit requires admitted source and final entries")
        entry_ids = [source_entry_id]
        split_metadata: list[dict[str, Any]] = []
        for node, hit in zip(graph.nodes[1:-1], hits[1:-1], strict=True):
            entry_id = node.node_id
            if entry_id in existing:
                raise ValueError("V9 split boundary already exists in the curriculum")
            path = self.curriculum_directory / "entries" / f"{entry_id}.json.gz"
            payload = {
                "schema_version": 1,
                "entry_id": entry_id,
                "source_cell_id": None,
                "progress": hit.progress.public_dict(),
                "snapshot": hit.snapshot.checkpoint_dict(),
                "stable_state_identity": hit.observed.state_identity.public_dict(),
                "lineage_actions": [
                    BlindAction(
                        BLIND_ACTIONS[index], ACTION_HOLD_FRAMES, ACTION_RELEASE_FRAMES
                    ).public_dict()
                    for index in full_actions[: source_prefix_length + hit.observed.action_offset]
                ],
            }
            _atomic_gzip_json(path, payload)
            split_metadata.append(
                {
                    "entry_id": entry_id,
                    "file": f"entries/{path.name}",
                    "file_sha256": _sha256_file(path),
                    "milestone_id": hit.progress.key,
                    "milestone_index": hit.progress.index,
                    "milestone_label": hit.progress.label,
                    "map_id": hit.referee_summary.get("map_id"),
                    "depth_actions": source_prefix_length + hit.observed.action_offset,
                    "source": "v9_replay_local_first_hit",
                    "stable_state_sha256": hit.observed.state_identity.stable_state_sha256,
                    "snapshot_sha256": hit.observed.state_identity.snapshot_sha256,
                }
            )
            entry_ids.append(entry_id)
        entry_ids.append(final_entry_id)
        final_metadata = existing[final_entry_id]
        split_ids = set(entry_ids[1:-1])
        manifest["entries"] = [
            item
            for item in manifest["entries"]
            if str(item["entry_id"]) != final_entry_id and str(item["entry_id"]) not in split_ids
        ]
        manifest["entries"].extend(split_metadata)
        manifest["entries"].append(final_metadata)
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        _atomic_json(self.curriculum_directory / "manifest.json", manifest)
        return tuple(entry_ids)

    def _prepare_v9_normalized_skills(
        self,
        verification: Mapping[str, Any],
        progress: MilestoneProgress,
    ) -> _PreparedV9Skills:
        if self.student_trainer is None:
            raise RuntimeError("V9 edge normalization has no Student trainer")
        candidate = verification["candidate"]
        replay_id = str(candidate["candidate_id"])
        full_actions = [int(value) for value in verification["full_actions"]]
        source_metadata, source_entry, prefix_length = _nearest_verified_lineage_prefix(
            self.curriculum_directory,
            full_actions,
            target_index=progress.index,
        )
        source_actions = full_actions[prefix_length:]
        source_progress = _progress_from_value(source_entry["progress"])
        source_snapshot = FrozenSnapshot.from_checkpoint_dict(source_entry["snapshot"])
        graph, hits = _collect_v9_first_hit_graph(
            self.rom_path,
            source_snapshot,
            source_actions,
            source_progress,
            progress,
            replay_id=replay_id,
            cancellation_check=self._v9_practice_cancellation_reason,
        )
        candidate_snapshot = FrozenSnapshot.from_checkpoint_dict(candidate["terminal_snapshot"])
        if hits[0].progress != source_progress or hits[0].snapshot.sha256 != source_snapshot.sha256:
            raise ValueError("V9 graph source is not the selected concrete curriculum state")
        if (
            hits[-1].progress != progress
            or hits[-1].snapshot.sha256 != candidate_snapshot.sha256
            or candidate_snapshot.sha256 != str(candidate["terminal_snapshot_sha256"])
        ):
            raise ValueError("V9 graph target is not the verified candidate terminal state")
        graph_relative = f"self-skills/{replay_id}.skill-graph.json"
        graph_path = self.run_directory / graph_relative
        _atomic_json(graph_path, graph.public_audit())
        graph_sha256 = _sha256_file(graph_path)
        entry_ids = (
            str(source_metadata["entry_id"]),
            *(node.node_id for node in graph.nodes[1:-1]),
            replay_id,
        )
        prepared: list[dict[str, Any]] = []
        for edge_index, edge in enumerate(graph.edges):
            _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            source_hit = hits[edge_index]
            target_hit = hits[edge_index + 1]
            skill_id = edge.edge_id
            original_actions = [int(value) for value in edge.actions]
            distilled = _distill_verified_actions(
                self.rom_path,
                source_hit.snapshot,
                original_actions,
                source_hit.progress,
                target_hit.progress,
                verification_id=skill_id,
                successful_replays=(
                    int(verification["edge_replays"]) + int(verification["power_on_replays"])
                ),
                max_attempts=self.config.distillation_attempts,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            compressed_actions = [int(value) for value in distilled.actions]
            dataset, target_clip = _collect_v8_student_dataset(
                self.rom_path,
                source_hit.snapshot,
                compressed_actions,
                compressed_to_original=distilled.compressed_to_original,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            target_relative = f"self-skills/{skill_id}.png"
            dataset_relative = f"self-skills/{skill_id}.npz"
            audit_relative = f"self-skills/{skill_id}.distillation.json"
            target_path = self.run_directory / target_relative
            dataset_path = self.run_directory / dataset_relative
            audit_path = self.run_directory / audit_relative
            temporary_target = target_path.with_suffix(".tmp.png")
            Image.fromarray(target_clip[-1]).save(temporary_target, format="PNG")
            os.replace(temporary_target, target_path)
            _atomic_self_imitation_dataset(dataset_path, dataset)
            dataset_sha256 = _sha256_file(dataset_path)
            replay_shards = _write_v8_replay_shards(
                self.run_directory,
                skill_id=skill_id,
                dataset=dataset,
                source_dataset_sha256=dataset_sha256,
                max_examples=self.student_trainer.config.max_examples_per_dataset,
                burn_in=self.student_trainer.config.burn_in,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            self._refresh_v9_written_artifact_budget()
            _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            _atomic_json(
                audit_path,
                {
                    "schema_version": 1,
                    "protocol": _ppo_reward_protocol(self.config.mode),
                    "verification_id": skill_id,
                    "source_entry_id": entry_ids[edge_index],
                    "source_milestone": source_hit.progress.public_dict(),
                    "target_entry_id": entry_ids[edge_index + 1],
                    "target_milestone": target_hit.progress.public_dict(),
                    "expected_target_snapshot_sha256": target_hit.snapshot.sha256,
                    "skill_graph_audit_file": graph_relative,
                    "skill_graph_audit_sha256": graph_sha256,
                    "graph_edge_id": edge.edge_id,
                    "graph_start_action_offset": edge.start_action_offset,
                    "graph_end_action_offset": edge.end_action_offset,
                    "full_self_generated_action_count": len(full_actions),
                    "source_lineage_action_count": (prefix_length + edge.start_action_offset),
                    "compressed_to_original": list(distilled.compressed_to_original),
                    "original_to_compressed": list(distilled.original_to_compressed),
                    "distillation": distilled.audit.as_dict(),
                    "human_actions": [],
                },
            )
            prepared.append(
                {
                    "skill_id": skill_id,
                    "source_entry_id": entry_ids[edge_index],
                    "source_index": source_hit.progress.index,
                    "target_entry_id": entry_ids[edge_index + 1],
                    "target_index": target_hit.progress.index,
                    "target_label": target_hit.progress.label,
                    "target_frame_file": target_relative,
                    "target_frame_sha256": _sha256_file(target_path),
                    "dataset_file": dataset_relative,
                    "dataset_sha256": dataset_sha256,
                    "action_count": len(compressed_actions),
                    "original_action_count": len(original_actions),
                    "distillation_audit_file": audit_relative,
                    "distillation_audit_sha256": _sha256_file(audit_path),
                    "skill_graph_audit_file": graph_relative,
                    "skill_graph_audit_sha256": graph_sha256,
                    "graph_edge_id": edge.edge_id,
                    "distillation_oracle_calls": distilled.audit.total_oracle_calls,
                    "distillation_oracle_actions_replayed": (
                        distilled.audit.oracle_actions_replayed
                    ),
                    "distillation_edits_accepted": (
                        distilled.audit.loop_deletions_accepted
                        + distilled.audit.chunk_deletions_accepted
                    ),
                    "distillation_edits_rejected": (
                        distilled.audit.loop_deletions_rejected
                        + distilled.audit.chunk_deletions_rejected
                    ),
                    "target_clip_channels": int(target_clip.shape[0]),
                    "replay_shards": replay_shards,
                    "replay_shard_example_cap": (
                        self.student_trainer.config.max_examples_per_dataset
                    ),
                    "replay_shard_burn_in": self.student_trainer.config.burn_in,
                }
            )
        return _PreparedV9Skills(
            skills=tuple(prepared),
            graph=graph,
            hits=hits,
            source_entry_id=str(source_metadata["entry_id"]),
            final_entry_id=replay_id,
            full_actions=tuple(full_actions),
            source_prefix_length=prefix_length,
        )

    def _prepare_self_generated_skill(
        self,
        verification: Mapping[str, Any],
        progress: MilestoneProgress,
        source_png: Path,
    ) -> dict[str, Any] | list[dict[str, Any]] | _PreparedV9Skills | None:
        if self.self_skills is None:
            return None
        if not source_png.is_file():
            raise ValueError("Self-generated skill has no terminal visual target")
        candidate = verification["candidate"]
        parent = verification["parent"]
        skill_id = str(candidate["candidate_id"])
        target_relative = f"self-skills/{skill_id}.png"
        dataset_relative = f"self-skills/{skill_id}.npz"
        target_path = self.run_directory / target_relative
        dataset_path = self.run_directory / dataset_relative
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if _uses_v9_practice(self.config.mode):
            return self._prepare_v9_normalized_skills(verification, progress)

        if _is_distilled_student_mode(self.config.mode):
            full_actions = [int(value) for value in verification["full_actions"]]
            source_metadata, source_entry, prefix_length = _nearest_verified_lineage_prefix(
                self.curriculum_directory,
                full_actions,
                target_index=progress.index,
            )
            original_actions = full_actions[prefix_length:]
            if not original_actions:
                raise ValueError("V8 discovery has no actions after its nearest verified state")
            source_progress = _progress_from_value(source_entry["progress"])
            source_snapshot = FrozenSnapshot.from_checkpoint_dict(source_entry["snapshot"])
            distilled = _distill_verified_actions(
                self.rom_path,
                source_snapshot,
                original_actions,
                source_progress,
                progress,
                verification_id=skill_id,
                successful_replays=(
                    int(verification["edge_replays"]) + int(verification["power_on_replays"])
                ),
                max_attempts=self.config.distillation_attempts,
            )
            compressed_actions = [int(value) for value in distilled.actions]
            dataset, target_clip = _collect_v8_student_dataset(
                self.rom_path,
                source_snapshot,
                compressed_actions,
                compressed_to_original=distilled.compressed_to_original,
            )
            temporary_target = target_path.with_suffix(".tmp.png")
            Image.fromarray(target_clip[-1]).save(temporary_target, format="PNG")
            os.replace(temporary_target, target_path)
            _atomic_self_imitation_dataset(dataset_path, dataset)
            dataset_sha256 = _sha256_file(dataset_path)
            if self.student_trainer is None:
                raise RuntimeError("V8 replay shard admission has no Student trainer")
            replay_shards = _write_v8_replay_shards(
                self.run_directory,
                skill_id=skill_id,
                dataset=dataset,
                source_dataset_sha256=dataset_sha256,
                max_examples=self.student_trainer.config.max_examples_per_dataset,
                burn_in=self.student_trainer.config.burn_in,
            )
            audit_relative = f"self-skills/{skill_id}.distillation.json"
            audit_path = self.run_directory / audit_relative
            _atomic_json(
                audit_path,
                {
                    "schema_version": 1,
                    "protocol": _ppo_reward_protocol(self.config.mode),
                    "verification_id": skill_id,
                    "source_entry_id": str(source_entry["entry_id"]),
                    "source_milestone": source_progress.public_dict(),
                    "target_entry_id": skill_id,
                    "target_milestone": progress.public_dict(),
                    "expected_target_snapshot_sha256": str(candidate["terminal_snapshot_sha256"]),
                    "distillation_acceptance": (
                        "same expanded trainer-observed gameplay state, full processed "
                        "terminal visual, and game-area hash; emulator clocks may differ"
                    ),
                    "full_self_generated_action_count": len(full_actions),
                    "source_lineage_action_count": prefix_length,
                    "compressed_to_original": list(distilled.compressed_to_original),
                    "original_to_compressed": list(distilled.original_to_compressed),
                    "distillation": distilled.audit.as_dict(),
                    "human_actions": [],
                },
            )
            return {
                "skill_id": skill_id,
                "source_entry_id": str(source_metadata["entry_id"]),
                "source_index": source_progress.index,
                "target_entry_id": skill_id,
                "target_index": progress.index,
                "target_label": progress.label,
                "target_frame_file": target_relative,
                "target_frame_sha256": _sha256_file(target_path),
                "dataset_file": dataset_relative,
                "dataset_sha256": dataset_sha256,
                "action_count": len(compressed_actions),
                "original_action_count": len(original_actions),
                "distillation_audit_file": audit_relative,
                "distillation_audit_sha256": _sha256_file(audit_path),
                "distillation_oracle_calls": distilled.audit.total_oracle_calls,
                "distillation_oracle_actions_replayed": (distilled.audit.oracle_actions_replayed),
                "distillation_edits_accepted": (
                    distilled.audit.loop_deletions_accepted
                    + distilled.audit.chunk_deletions_accepted
                ),
                "distillation_edits_rejected": (
                    distilled.audit.loop_deletions_rejected
                    + distilled.audit.chunk_deletions_rejected
                ),
                "target_clip_channels": int(target_clip.shape[0]),
                "replay_shards": replay_shards,
                "replay_shard_example_cap": (self.student_trainer.config.max_examples_per_dataset),
                "replay_shard_burn_in": self.student_trainer.config.burn_in,
            }

        target_frame = preprocess_apprentice_frame(
            np.asarray(Image.open(source_png).convert("RGB"))
        )
        temporary_target = target_path.with_suffix(".tmp.png")
        Image.fromarray(target_frame).save(temporary_target, format="PNG")
        os.replace(temporary_target, target_path)
        edge_actions = [int(value) for value in candidate["actions"]]
        dataset = _collect_self_imitation_dataset(
            self.rom_path,
            FrozenSnapshot.from_checkpoint_dict(parent["snapshot"]),
            edge_actions,
            target_frame,
        )
        _atomic_self_imitation_dataset(dataset_path, dataset)
        source_progress = _progress_from_value(parent["progress"])
        return {
            "skill_id": skill_id,
            "source_entry_id": str(parent["entry_id"]),
            "source_index": source_progress.index,
            "target_entry_id": skill_id,
            "target_index": progress.index,
            "target_label": progress.label,
            "target_frame_file": target_relative,
            "target_frame_sha256": _sha256_file(target_path),
            "dataset_file": dataset_relative,
            "dataset_sha256": _sha256_file(dataset_path),
            "action_count": len(edge_actions),
        }

    def _commit_self_generated_skill(
        self,
        prepared: Mapping[str, Any] | list[dict[str, Any]] | None,
    ) -> None:
        if self.self_skills is None or prepared is None:
            return
        skills = prepared if isinstance(prepared, list) else [prepared]
        admitted = False
        for skill in skills:
            admitted = self.self_skills.add_verified_skill(**skill) or admitted
        if admitted:
            self.self_imitation_pending = self.self_skills.imitation_pending
            self._write_self_skills()

    def _commit_v9_candidate(
        self,
        verification: Mapping[str, Any],
        prepared: _PreparedV9Skills,
    ) -> None:
        if self.self_skills is None:
            raise RuntimeError("V9 promotion has no Student skill library")
        previous_manifest = _load_curriculum_manifest(self.curriculum_directory)
        previous_library = self.self_skills.public_dict()
        proposed_library = SelfTaughtSkillLibrary.from_dict(previous_library)
        for skill in prepared.skills:
            if not proposed_library.add_verified_skill(**skill):
                raise ValueError("V9 normalized skill batch contains a duplicate edge")
        try:
            admit_verified_candidate(self.curriculum_directory, verification)
            self._admit_v9_split_boundaries(
                prepared.graph,
                prepared.hits,
                source_entry_id=prepared.source_entry_id,
                final_entry_id=prepared.final_entry_id,
                full_actions=prepared.full_actions,
                source_prefix_length=prepared.source_prefix_length,
            )
            self.self_skills = proposed_library
            self.self_imitation_pending = proposed_library.imitation_pending
            self._write_self_skills()
        except Exception:
            _atomic_json(self.curriculum_directory / "manifest.json", previous_manifest)
            self.self_skills = SelfTaughtSkillLibrary.from_dict(previous_library)
            self.self_imitation_pending = self.self_skills.imitation_pending
            self._write_self_skills()
            raise

    def _refresh_v8_composition_replay(self) -> bool:
        """Build one new replay-verified continuous chain when competence advances."""

        if self.self_skills is None:
            return False
        chain = self._competent_skill_chain()
        if len(chain) < 2:
            changed = self.self_skills.activate_verified_composition(None)
            if changed:
                self._write_self_skills()
            return changed
        fingerprint = _v8_composition_fingerprint(chain)
        outcome = self.self_skills.composition_build_outcomes.get(fingerprint)
        if outcome == "verified":
            changed = self.self_skills.activate_verified_composition(fingerprint)
            if changed:
                self._write_self_skills()
            return changed
        if outcome == "replay_failed":
            return False
        sources: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for skill in chain:
            path = self.run_directory / str(skill["dataset_file"])
            if _sha256_file(path) != skill["dataset_sha256"]:
                raise ValueError("V8 composition source dataset failed its hash")
            audit_path = self.run_directory / str(skill["distillation_audit_file"])
            if _sha256_file(audit_path) != skill["distillation_audit_sha256"]:
                raise ValueError("V8 composition source audit failed its hash")
            with np.load(path, allow_pickle=False) as archive:
                actions = np.asarray(archive["actions"], dtype=np.int64)
                target = np.asarray(archive["target_pixels"], dtype=np.uint8)
            sources[str(skill["skill_id"])] = (actions, target)
        try:
            dataset, boundaries = _collect_v8_composition_dataset(
                self.rom_path,
                self.curriculum_directory,
                chain,
                sources,
                burn_in=self.student_trainer.config.burn_in,
                train_length=self.student_trainer.config.train_length,
            )
        except CompositionReplayRejected:
            self.self_skills.record_composition_build_failure(fingerprint)
            self._write_self_skills()
            return False

        composition_id = f"composition-{fingerprint[:24]}"
        dataset_relative = f"self-skills/{composition_id}.npz"
        audit_relative = f"self-skills/{composition_id}.audit.json"
        dataset_path = self.run_directory / dataset_relative
        audit_path = self.run_directory / audit_relative
        _atomic_self_imitation_dataset(dataset_path, dataset)
        dataset_hash = _sha256_file(dataset_path)
        offsets = [int(value) for value in dataset["goal_switch_offsets"]]
        full_offsets = [int(value) for value in dataset["full_goal_switch_offsets"]]
        excerpt_offsets = [int(value) for value in dataset["excerpt_offsets"]]
        _atomic_json(
            audit_path,
            {
                "schema_version": 1,
                "protocol": SELF_GENERATED_COMPOSITION_PROTOCOL,
                "composition_id": composition_id,
                "fingerprint": fingerprint,
                "root_entry_id": self.self_skills.root_entry_id,
                "skill_ids": [str(skill["skill_id"]) for skill in chain],
                "source_artifacts": [
                    {
                        "skill_id": str(skill["skill_id"]),
                        "dataset_sha256": str(skill["dataset_sha256"]),
                        "distillation_audit_sha256": str(skill["distillation_audit_sha256"]),
                        "competent_when_built": bool(skill.get("competent", False)),
                    }
                    for skill in chain
                ],
                "dataset_sha256": dataset_hash,
                "action_count": int(len(dataset["actions"])),
                "goal_switch_offsets": offsets,
                "full_action_count": int(dataset["full_action_count"]),
                "full_goal_switch_offsets": full_offsets,
                "excerpt_offsets": excerpt_offsets,
                "excerpt_full_ranges": np.asarray(dataset["excerpt_full_ranges"]).tolist(),
                "boundaries": boundaries,
                "successful_continuous_replays": 1,
                "episode_starts": excerpt_offsets[:-1],
                "goal_storage": "one clip per declared segment; expanded per sampled window",
                "pixel_storage": "bounded switch excerpts only",
                "hidden_state_resets_at_excerpt_boundaries": True,
                "hidden_state_resets_at_goal_switches": False,
                "frozen_exam_actions_used_for_training": False,
                "human_actions": [],
            },
        )
        admitted = self.self_skills.add_verified_composition(
            composition_id=composition_id,
            fingerprint=fingerprint,
            skill_ids=[str(skill["skill_id"]) for skill in chain],
            target_index=int(chain[-1]["target_index"]),
            dataset_file=dataset_relative,
            dataset_sha256=dataset_hash,
            audit_file=audit_relative,
            audit_sha256=_sha256_file(audit_path),
            action_count=int(len(dataset["actions"])),
            goal_switch_offsets=offsets,
            full_action_count=int(dataset["full_action_count"]),
            full_goal_switch_offsets=full_offsets,
            excerpt_offsets=excerpt_offsets,
            successful_replays=1,
        )
        if admitted:
            self.self_imitation_pending = self.self_skills.imitation_pending
            self._write_self_skills()
        return admitted

    def _selected_v9_practice_replays(
        self,
    ) -> tuple[dict[str, Path], list[dict[str, Any]]]:
        if not _uses_v9_practice(self.config.mode) or self.self_skills is None:
            return {}, []
        paths: dict[str, Path] = {}
        selections: list[dict[str, Any]] = []
        round_index = self.self_skills.student_training_rounds
        for skill_id, ledger in sorted(self.student_practice_ledgers.items()):
            for rung in ledger.rungs:
                rollouts = rung.successful_rollouts
                if not rollouts:
                    continue
                offset = int.from_bytes(
                    hashlib.sha256(f"{skill_id}:{rung.rung.index}".encode()).digest()[:8],
                    "big",
                )
                rollout = rollouts[(round_index + offset) % len(rollouts)]
                if not rollout.replay_shards:
                    raise ValueError("V9 retained success has no bounded replay shards")
                shard = rollout.replay_shards[
                    (round_index // len(rollouts) + offset) % len(rollout.replay_shards)
                ]
                dataset_id = f"practice-{rollout.rollout_id}"
                if dataset_id in paths:
                    raise ValueError("V9 practice replay selection repeats a rollout")
                shard_path = _validate_hashed_run_artifact(
                    self.run_directory,
                    shard["file"],
                    shard["sha256"],
                    label="V9 bounded successful-practice replay shard",
                )
                if shard_path.stat().st_size != int(shard["stored_bytes"]):
                    raise ValueError("V9 practice replay shard size disagrees with its ledger")
                paths[dataset_id] = shard_path
                selections.append(
                    {
                        "dataset_id": dataset_id,
                        "source_skill_id": skill_id,
                        "rung_index": rung.rung.index,
                        "rollout_id": rollout.rollout_id,
                        "rollout_reservoir_size": len(rollouts),
                        "shard_index": int(shard["shard_index"]),
                        "shard_count": int(shard["shard_count"]),
                        "context_examples": int(shard["context_example_count"]),
                        "train_examples": int(shard["train_example_count"]),
                        "stored_examples": int(shard["example_count"]),
                        "stored_bytes": int(shard["stored_bytes"]),
                    }
                )
        return paths, selections

    def _load_v8_student_datasets(
        self,
    ) -> tuple[tuple[Any, ...], list[dict[str, Any]], list[dict[str, Any]]]:
        if self.self_skills is None or not self.self_skills.skills:
            return (), [], []
        paths: dict[str, Path] = {}
        selections: list[dict[str, Any]] = []
        for skill in self.self_skills.skills:
            skill_id = str(skill["skill_id"])
            if int(skill.get("replay_shard_example_cap", 0)) != (
                self.student_trainer.config.max_examples_per_dataset
            ):
                raise ValueError("V8 replay shard cap disagrees with the Student configuration")
            if int(skill.get("replay_shard_burn_in", -1)) != self.student_trainer.config.burn_in:
                raise ValueError("V8 replay shard burn-in disagrees with Student configuration")
            shard = self.self_skills.replay_shard(skill_id)
            shard_path = _validate_hashed_run_artifact(
                self.run_directory,
                shard["file"],
                shard["sha256"],
                label="V8 bounded Student replay shard",
            )
            if shard_path.stat().st_size != int(shard["stored_bytes"]):
                raise ValueError("V8 bounded Student replay shard size disagrees with ledger")
            paths[skill_id] = shard_path
            cursor = int(skill.get("replay_cursor", 0))
            shard_count = len(skill["replay_shards"])
            selections.append(
                {
                    "skill_id": skill_id,
                    "cursor": cursor,
                    "shard_index": int(shard["shard_index"]),
                    "shard_count": shard_count,
                    "coverage_cycle": cursor // shard_count,
                    "source_start": int(shard["source_start"]),
                    "source_context_start": int(shard["source_context_start"]),
                    "source_train_start": int(shard["source_train_start"]),
                    "source_stop": int(shard["source_stop"]),
                    "context_examples": int(shard["context_example_count"]),
                    "train_examples": int(shard["train_example_count"]),
                    "stored_examples": int(shard["example_count"]),
                    "stored_bytes": int(shard["stored_bytes"]),
                }
            )
        for composition in self.self_skills.composition_replays:
            if not bool(composition.get("active", False)):
                continue
            dataset_path = _validate_hashed_run_artifact(
                self.run_directory,
                composition["dataset_file"],
                composition["dataset_sha256"],
                label="V8 active composition dataset",
            )
            _validate_hashed_run_artifact(
                self.run_directory,
                composition["audit_file"],
                composition["audit_sha256"],
                label="V8 active composition audit",
            )
            composition_id = str(composition["composition_id"])
            if composition_id in paths:
                raise ValueError("V8 composition identifier collides with an individual skill")
            paths[composition_id] = dataset_path
        practice_paths, practice_selections = self._selected_v9_practice_replays()
        if set(paths).intersection(practice_paths):
            raise ValueError("V9 practice replay identifier collides with a verified lesson")
        paths.update(practice_paths)
        datasets = load_self_generated_datasets(
            paths,
        )
        by_id = {dataset.skill_id: dataset for dataset in datasets}
        for skill in self.self_skills.skills:
            skill_id = str(skill["skill_id"])
            dataset = by_id[skill_id]
            shard = self.self_skills.replay_shard(skill_id)
            if (
                dataset.dataset_kind != "skill"
                or dataset.source_action_count != int(skill["action_count"])
                or dataset.source_action_offset != int(shard["source_start"])
                or len(dataset) != int(shard["example_count"])
                or dataset.train_offset
                != int(shard["source_train_start"]) - int(shard["source_start"])
                or dataset.trainable_examples != int(shard["train_example_count"])
                or dataset.source_train_start != int(shard["source_train_start"])
                or dataset.source_train_stop != int(shard["source_stop"])
                or dataset.replay_shard_protocol != SELF_GENERATED_REPLAY_SHARD_PROTOCOL
                or dataset.source_dataset_sha256 != str(skill["dataset_sha256"])
                or dataset.replay_shard_index != int(shard["shard_index"])
                or dataset.replay_shard_count != int(shard["shard_count"])
                or dataset.target_pixels.shape
                != (int(skill.get("target_clip_channels", 1)), 72, 80)
            ):
                raise ValueError("V8 individual dataset disagrees with its verified ledger")
        for composition in self.self_skills.active_composition_replays():
            dataset = by_id[str(composition["composition_id"])]
            if (
                dataset.dataset_kind != "composition"
                or dataset.source_skill_ids != tuple(composition["skill_ids"])
                or dataset.goal_switch_offsets
                != tuple(int(value) for value in composition["goal_switch_offsets"])
                or dataset.successful_replays != int(composition["successful_replays"])
                or len(dataset) != int(composition["action_count"])
                or dataset.excerpt_offsets != tuple(composition["excerpt_offsets"])
            ):
                raise ValueError("V8 composition dataset disagrees with its verified ledger")
        for selection in practice_selections:
            dataset = by_id[str(selection["dataset_id"])]
            rollout_id = str(selection["rollout_id"])
            rollout = next(
                item
                for ledger in self.student_practice_ledgers.values()
                for rung in ledger.rungs
                for item in rung.successful_rollouts
                if item.rollout_id == rollout_id
            )
            if (
                dataset.dataset_kind != "skill"
                or dataset.source_action_count != rollout.action_count
                or dataset.source_dataset_sha256 != rollout.dataset_sha256
                or dataset.replay_shard_index != int(selection["shard_index"])
                or dataset.replay_shard_count != int(selection["shard_count"])
                or dataset.target_pixels.shape != (3, 72, 80)
            ):
                raise ValueError("V9 practice dataset disagrees with its verified ledger")
        return datasets, selections, practice_selections

    def _train_v8_student(self) -> None:
        if self.self_skills is None or self.student_trainer is None or not self.self_skills.skills:
            return
        rollout_size = self.config.rollout_steps * self.config.environments
        rollout = self.model.num_timesteps // max(1, rollout_size)
        due = rollout % self.config.student_replay_interval == 0
        if not self.self_skills.imitation_pending and (
            not due or rollout == self.last_student_replay_rollout
        ):
            return
        self._refresh_v8_composition_replay()
        datasets, shard_selections, practice_selections = self._load_v8_student_datasets()
        replay = BalancedSkillReplay(
            datasets,
            self.student_trainer.config,
            seed=self.config.seed + self.self_skills.student_training_rounds,
            composition_boundary_cursor=self.self_skills.composition_boundary_cursor,
        )
        updates = self.config.student_replay_epochs * replay.sampling_cycle_size
        report = self.student_trainer.train(replay, updates=updates)
        self.self_skills.composition_boundary_cursor = replay.next_composition_boundary_cursor
        measured = self.student_trainer.diagnose(datasets)
        total = sum(item.examples for item in measured.values())
        diagnostics = {
            "action_nll": sum(item.action_nll * item.examples for item in measured.values())
            / total,
            "action_accuracy": sum(
                item.action_accuracy * item.examples for item in measured.values()
            )
            / total,
            "policy_entropy": sum(item.policy_entropy * item.examples for item in measured.values())
            / total,
            "demonstration_entropy": sum(
                item.demonstration_entropy * item.examples for item in measured.values()
            )
            / total,
        }
        recorded = report.public_dict()
        recorded["diagnostics"] = diagnostics
        recorded["per_skill_diagnostics"] = {
            skill_id: item.public_dict() for skill_id, item in sorted(measured.items())
        }
        recorded["individual_skill_datasets"] = sum(
            dataset.dataset_kind == "skill" for dataset in datasets
        )
        recorded["composition_datasets"] = sum(
            dataset.dataset_kind == "composition" for dataset in datasets
        )
        recorded["replay_examples_retained"] = sum(len(dataset) for dataset in datasets)
        recorded["replay_bytes_retained"] = sum(dataset.retained_bytes for dataset in datasets)
        recorded["max_examples_per_individual_skill"] = (
            self.student_trainer.config.max_examples_per_dataset
        )
        recorded["replay_example_ceiling"] = recorded["individual_skill_datasets"] * (
            self.student_trainer.config.max_examples_per_dataset
            + self.student_trainer.config.burn_in
        ) + sum(len(dataset) for dataset in datasets if dataset.dataset_kind == "composition")
        recorded["replay_train_example_ceiling"] = recorded[
            "individual_skill_datasets"
        ] * self.student_trainer.config.max_examples_per_dataset + sum(
            dataset.trainable_examples
            for dataset in datasets
            if dataset.dataset_kind == "composition"
        )
        recorded["sampling_cycle_size"] = replay.sampling_cycle_size
        recorded["replay_shards_total"] = sum(
            len(skill.get("replay_shards", [])) for skill in self.self_skills.skills
        )
        recorded["replay_shards_loaded"] = len(shard_selections)
        recorded["replay_shard_examples_loaded"] = sum(
            int(item["stored_examples"]) for item in shard_selections
        )
        recorded["replay_shard_train_examples_loaded"] = sum(
            int(item["train_examples"]) for item in shard_selections
        )
        recorded["replay_shard_context_examples_loaded"] = sum(
            int(item["context_examples"]) for item in shard_selections
        )
        recorded["replay_shard_bytes_read"] = sum(
            int(item["stored_bytes"]) for item in shard_selections
        )
        recorded["practice_replay_datasets_loaded"] = len(practice_selections)
        recorded["practice_replay_train_examples_loaded"] = sum(
            int(item["train_examples"]) for item in practice_selections
        )
        recorded["practice_replay_context_examples_loaded"] = sum(
            int(item["context_examples"]) for item in practice_selections
        )
        recorded["practice_replay_bytes_read"] = sum(
            int(item["stored_bytes"]) for item in practice_selections
        )
        recorded["practice_replay_selections"] = practice_selections
        recorded["replay_full_skill_artifacts_opened"] = 0
        recorded["replay_shard_selections"] = shard_selections
        recorded["replay_cursor_min"] = min(
            (int(item["cursor"]) for item in shard_selections),
            default=0,
        )
        recorded["replay_cursor_max"] = max(
            (int(item["cursor"]) for item in shard_selections),
            default=0,
        )
        recorded["replay_coverage_cycle_min"] = min(
            (int(item["coverage_cycle"]) for item in shard_selections),
            default=0,
        )
        self.self_skills.advance_replay_cursors(
            [str(item["skill_id"]) for item in shard_selections]
        )
        self.self_skills.record_student_training(recorded)
        self.self_imitation_pending = self.self_skills.imitation_pending
        self.last_student_replay_rollout = rollout
        self.self_skills.last_student_replay_rollout = rollout
        self._write_self_skills()
        self._checkpoint()
        self._narrative("Student replayed distilled self-discovered skills")

    def _v8_target_clip(self, skill: Mapping[str, Any]) -> np.ndarray:
        if self.self_skills is None:
            raise RuntimeError("Frozen Student exam has no self-generated skill ledger")
        if _is_v12_mode(self.config.mode):
            path = _validate_hashed_run_artifact(
                self.run_directory,
                skill["target_frame_file"],
                skill["target_frame_sha256"],
                label="V12 checkpoint exam target frame",
            )
            target = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)[None, :, :]
            if target.shape != (1, 72, 80):
                raise ValueError("V12 checkpoint exam requires one self-observed goal frame")
            return target
        shard = self.self_skills.replay_shard(str(skill["skill_id"]))
        path = _validate_hashed_run_artifact(
            self.run_directory,
            shard["file"],
            shard["sha256"],
            label="Frozen Student exam target shard",
        )
        with np.load(path, allow_pickle=False) as archive:
            target = np.asarray(archive["target_pixels"], dtype=np.uint8)
        if target.shape != (3, 72, 80):
            raise ValueError("V8 frozen exam requires a three-frame self-observed goal")
        return target

    def _predict_student_action(
        self,
        observation: Mapping[str, np.ndarray],
        recurrent_state: Any | None,
        *,
        episode_start: bool,
        deterministic: bool = True,
    ) -> tuple[int, Any]:
        evaluation_model = self.model if _is_v12_mode(self.config.mode) else self.student_model
        if evaluation_model is None:
            raise RuntimeError("Frozen checkpoint exam has no evaluation model")
        action, next_state = evaluation_model.predict(
            observation,
            state=recurrent_state,
            episode_start=np.asarray([episode_start], dtype=np.bool_),
            deterministic=deterministic,
        )
        return int(np.asarray(action).reshape(-1)[0]), next_state

    def _v9_practice_cancellation_reason(self) -> str | None:
        """Expose campaign boundaries to long, synchronous Student practice loops."""

        if self.stop_reason in V9_PRACTICE_CANCELLATION_REASONS:
            return self.stop_reason
        if (self.run_directory / "STOP").exists():
            return "stop_requested"
        if self.elapsed() >= self.config.duration_seconds:
            return "duration_limit"
        if self.model.num_timesteps >= self.config.max_actions:
            return "action_limit"
        now = time.monotonic()
        if now - self.last_v9_disk_budget_refresh >= V9_DISK_BUDGET_REFRESH_SECONDS:
            self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
            self.last_v9_disk_budget_refresh = now
        if self.cached_free_bytes < self.config.min_free_bytes:
            return "low_disk_space"
        if self.cached_run_bytes >= self.config.max_output_bytes:
            return "output_limit"
        return None

    def _refresh_v9_written_artifact_budget(self) -> None:
        """Refresh output accounting after a synchronous V9 artifact batch."""

        self.cached_run_bytes = sum(
            path.stat().st_size for path in self.run_directory.rglob("*") if path.is_file()
        )
        self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
        self.last_v9_disk_budget_refresh = time.monotonic()

    def _sync_v9_practice_ledgers(self) -> None:
        if not _uses_v9_practice(self.config.mode) or self.self_skills is None:
            return
        settings = ReversePracticeConfig(
            first_rung_actions=8,
            promotion_window=self.config.student_practice_window,
            promotion_required_successes=self.config.student_practice_required,
            promotion_confirmations=self.config.student_practice_confirmations,
            retention_fraction=self.config.student_practice_retention,
            success_reservoir_capacity=self.config.student_practice_reservoir,
            action_history_length=ACTION_HISTORY_LENGTH,
        )
        changed = False
        for skill in self.self_skills.skills:
            skill_id = str(skill["skill_id"])
            if skill_id in self.student_practice_ledgers:
                continue
            self.student_practice_ledgers[skill_id] = StudentPracticeLedger.initialize(
                skill_id=skill_id,
                source_action_count=int(skill["action_count"]),
                seed=self.config.seed + int(skill["target_index"]) * 10_007,
                config=settings,
            )
            changed = True
        if changed:
            self._write_student_practice()

    def _v9_practice_skill(self) -> tuple[dict[str, Any], StudentPracticeLedger] | None:
        if self.self_skills is None:
            return None
        self._sync_v9_practice_ledgers()
        skills = sorted(self.self_skills.skills, key=lambda item: int(item["target_index"]))
        choices = [
            (skill, self.student_practice_ledgers[str(skill["skill_id"])]) for skill in skills
        ]
        unfinished = [item for item in choices if not item[1].curriculum_complete]
        if unfinished:
            return min(unfinished, key=lambda item: (item[1].active_rung_index, item[1].attempts))
        if not choices:
            return None
        return min(choices, key=lambda item: item[1].attempts)

    def _train_v9_success_rollout(self, path: Path, rollout_id: str, seed: int) -> None:
        if self.student_trainer is None or self.self_skills is None:
            raise RuntimeError("V9 success replay has no Student trainer")
        dataset = SelfGeneratedSkillDataset.load(path, skill_id=f"practice-{rollout_id}")
        replay = BalancedSkillReplay((dataset,), self.student_trainer.config, seed=seed)
        immediate = self.student_trainer.train(
            replay,
            updates=self.config.student_replay_epochs,
        ).public_dict()
        report = _merge_v9_success_student_report(
            self.self_skills.last_student_report,
            immediate,
        )
        self.self_skills.record_student_training(report)
        self.student_practice_training_updates += int(immediate["updates"])

    def _run_v9_practice_attempt(
        self,
        skill: Mapping[str, Any],
        ledger: StudentPracticeLedger,
    ) -> bool:
        if self.student_model is None:
            raise RuntimeError("V9 closed-loop practice has no Student model")
        choice = ledger.next_choice()
        # Persist the deterministic choice before touching the emulator. If the
        # attempt is interrupted, resume repeats this exact seed and rung.
        self._write_student_practice()
        skill_path = _validate_hashed_run_artifact(
            self.run_directory,
            skill["dataset_file"],
            skill["dataset_sha256"],
            label="V9 practice source skill",
        )
        with np.load(skill_path, allow_pickle=False) as archive:
            demonstrated_actions = np.asarray(archive["actions"], dtype=np.int64)
            target_clip = np.asarray(archive["target_pixels"], dtype=np.uint8)
        if len(demonstrated_actions) != ledger.source_action_count:
            raise ValueError("V9 practice ladder no longer matches its source skill")
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        metadata_by_id = {str(entry["entry_id"]): entry for entry in manifest["entries"]}
        source_metadata = metadata_by_id.get(str(skill["source_entry_id"]))
        if source_metadata is None:
            raise ValueError("V9 practice source curriculum entry is missing")
        target_metadata = metadata_by_id.get(str(skill["target_entry_id"]))
        if target_metadata is None:
            raise ValueError("V9 practice target curriculum entry is missing")
        source = _load_curriculum_entry(self.curriculum_directory, source_metadata)
        source_progress = _progress_from_value(source["progress"])
        target_index = int(skill["target_index"])
        target = _load_curriculum_entry(self.curriculum_directory, target_metadata)
        target_progress = _progress_from_value(target["progress"])
        if target_progress.index != target_index:
            raise ValueError("V9 practice target entry disagrees with its normalized skill")
        target_signature = _curriculum_snapshot_signature(self.rom_path, target)
        target_signature_sha256 = hashlib.sha256(repr(target_signature).encode()).hexdigest()
        pixels: list[np.ndarray] = []
        histories: list[np.ndarray] = []
        student_actions: list[int] = []
        recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
        success = False
        terminal_reason = "timeout"
        practice_snapshot: FrozenSnapshot | None = None
        practice_progress = source_progress
        previous_mode = bool(self.student_model.policy.training)
        python_state = random.getstate()
        numpy_state = np.random.get_state()
        try:
            import torch

            torch_state = torch.random.get_rng_state()
            self.student_model.set_random_seed(choice.attempt_seed)
            self.student_model.policy.set_training_mode(False)
            with PokemonRedEmulator(self.rom_path) as emulator:
                emulator.load_state(FrozenSnapshot.from_checkpoint_dict(source["snapshot"]).thaw())
                reader = PokemonRedStateReader(emulator)
                for action in demonstrated_actions[: choice.start_action]:
                    _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
                    if not _execute_action(emulator, int(action)):
                        raise RuntimeError("V9 practice ladder replay stopped")
                    self.student_practice_actions += 1
                practice_progress = milestone_progress_for_state(
                    reader.read(), inherited=source_progress
                )
                practice_snapshot = FrozenSnapshot.freeze(emulator.save_state())
                current = preprocess_apprentice_frame(emulator.screen_rgb())
                previous = current
                recurrent_state: Any | None = None
                limit = max(
                    1,
                    int(
                        np.ceil(
                            choice.remaining_actions
                            * self.config.student_practice_rollout_multiplier
                        )
                    )
                    + self.config.student_practice_rollout_slack,
                )
                for step in range(limit):
                    _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
                    observation = {
                        "pixels": np.stack((previous, current)),
                        "action_history": _action_history(recent),
                        "target_pixels": target_clip,
                    }
                    action, recurrent_state = self._predict_student_action(
                        observation,
                        recurrent_state,
                        episode_start=step == 0,
                        deterministic=False,
                    )
                    pixels.append(observation["pixels"])
                    histories.append(observation["action_history"])
                    student_actions.append(action)
                    self.student_practice_actions += 1
                    if not _execute_action(emulator, action):
                        terminal_reason = "emulator_stopped"
                        break
                    recent.append(action)
                    previous = current
                    current = preprocess_apprentice_frame(emulator.screen_rgb())
                    state = reader.read()
                    progress = milestone_progress_for_state(state, inherited=practice_progress)
                    signature_outcome = _v9_practice_signature_outcome(
                        progress.index,
                        target_index,
                        _composition_state_signature(emulator, state, progress),
                        target_signature,
                    )
                    if signature_outcome is not None:
                        terminal_reason = signature_outcome
                        success = signature_outcome == "exact_target"
                        break
        finally:
            self.student_model.policy.set_training_mode(previous_mode)
            random.setstate(python_state)
            np.random.set_state(numpy_state)
            if "torch_state" in locals():
                torch.random.set_rng_state(torch_state)

        metadata: SuccessfulRolloutMetadata | None = None
        dataset_path: Path | None = None
        if success:
            if practice_snapshot is None or not student_actions:
                raise RuntimeError("V9 successful practice has no replayable actions")
            replay_snapshot, replay_progress, _summary, _screen = _replay_sequence(
                self.rom_path,
                practice_snapshot,
                student_actions,
                practice_progress,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            self.student_practice_verification_actions += len(student_actions)
            replay_signature = _curriculum_snapshot_signature(
                self.rom_path,
                {
                    "progress": replay_progress.public_dict(),
                    "snapshot": replay_snapshot.checkpoint_dict(),
                },
            )
            replay_outcome = _v9_practice_signature_outcome(
                replay_progress.index,
                target_index,
                replay_signature,
                target_signature,
            )
            if replay_outcome != "exact_target":
                success = False
                terminal_reason = "milestone_wrong_state"
        if success:
            identity = {
                "skill_id": ledger.skill_id,
                "decision": choice.decision,
                "attempt_seed": choice.attempt_seed,
                "actions": student_actions,
                "practice_snapshot_sha256": practice_snapshot.sha256,
                "target_entry_id": str(skill["target_entry_id"]),
                "target_signature_sha256": target_signature_sha256,
            }
            rollout_id = hashlib.sha256(_canonical_json(identity)).hexdigest()
            relative = (
                f"student-practice/{ledger.skill_id}/"
                f"success-{choice.decision:08d}-{rollout_id[:16]}.npz"
            )
            dataset_path = self.run_directory / relative
            rollout_dataset = {
                "pixels": np.stack(pixels).astype(np.uint8, copy=False),
                "action_history": np.stack(histories).astype(np.float32, copy=False),
                "target_pixels": target_clip,
                "actions": np.asarray(student_actions, dtype=np.int64),
                "weights": np.ones(len(student_actions), dtype=np.float32),
                "episode_starts": np.asarray(
                    [True, *([False] * (len(student_actions) - 1))],
                    dtype=np.bool_,
                ),
            }
            _atomic_self_imitation_dataset(dataset_path, rollout_dataset)
            dataset_sha256 = _sha256_file(dataset_path)
            replay_shards = _write_v8_replay_shards(
                self.run_directory,
                skill_id=f"practice-{rollout_id}",
                dataset=rollout_dataset,
                source_dataset_sha256=dataset_sha256,
                max_examples=self.student_trainer.config.max_examples_per_dataset,
                burn_in=self.student_trainer.config.burn_in,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            self._refresh_v9_written_artifact_budget()
            _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            metadata = SuccessfulRolloutMetadata(
                rollout_id=rollout_id,
                skill_id=ledger.skill_id,
                rung_index=choice.rung_index,
                remaining_actions=choice.remaining_actions,
                attempt_seed=choice.attempt_seed,
                action_count=len(student_actions),
                dataset_file=relative,
                dataset_sha256=dataset_sha256,
                verification_id=hashlib.sha256(
                    _canonical_json(
                        {
                            "rollout_id": rollout_id,
                            "target_entry_id": str(skill["target_entry_id"]),
                            "target_signature_sha256": target_signature_sha256,
                            "replay_snapshot_sha256": replay_snapshot.sha256,
                        }
                    )
                ).hexdigest(),
                replay_shards=tuple(replay_shards),
            )
        outcome = ledger.record_attempt(choice, success=success, rollout=metadata)
        self.student_practice_terminal_reasons[terminal_reason] += 1
        if metadata is not None and dataset_path is not None:
            if outcome.rollout_retained:
                first_shard = self.run_directory / str(metadata.replay_shards[0]["file"])
                self._train_v9_success_rollout(
                    first_shard,
                    metadata.rollout_id,
                    choice.attempt_seed,
                )
            else:
                dataset_path.unlink(missing_ok=True)
                for shard in metadata.replay_shards:
                    (self.run_directory / str(shard["file"])).unlink(missing_ok=True)
        # An evicted rollout may still be referenced by the previous committed
        # checkpoint generation. Its immutable files are therefore left in place
        # for crash rollback; a later storage compactor may remove unreachable data.
        self._write_student_practice()
        self._write_self_skills()
        return outcome.promoted

    def _run_v9_practice_round(self) -> bool:
        if not _uses_v9_practice(self.config.mode):
            return False
        rollout_size = self.config.rollout_steps * self.config.environments
        explorer_rollout = self.model.num_timesteps // max(1, rollout_size)
        if (
            explorer_rollout == self.last_student_practice_rollout
            or explorer_rollout % self.config.student_practice_interval
        ):
            return False
        self.last_student_practice_rollout = explorer_rollout
        promoted = False
        for _ in range(self.config.student_practice_attempts):
            reason = self._v9_practice_cancellation_reason()
            if reason is not None:
                self.stop_reason = reason
                break
            selected = self._v9_practice_skill()
            if selected is None:
                break
            skill, ledger = selected
            try:
                promoted |= self._run_v9_practice_attempt(skill, ledger)
            except V9PracticeCancelled as cancellation:
                self.stop_reason = cancellation.reason
                break
        self._write_student_practice()
        return promoted

    def _run_frozen_skill_attempt(
        self,
        skill: Mapping[str, Any],
    ) -> tuple[bool, int, int]:
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        source_metadata = next(
            (
                entry
                for entry in manifest["entries"]
                if str(entry["entry_id"]) == str(skill["source_entry_id"])
            ),
            None,
        )
        if source_metadata is None:
            raise ValueError("Frozen Student exam source is missing")
        source = _load_curriculum_entry(self.curriculum_directory, source_metadata)
        inherited = _progress_from_value(source["progress"])
        target_index = int(skill["target_index"])
        target_clip = self._v8_target_clip(skill)
        limit = max(
            1,
            int(np.ceil(int(skill["action_count"]) * self.config.frozen_exam_action_multiplier)),
        )
        recurrent_state: Any | None = None
        recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
        best = inherited.index
        actions = 0
        cancellation_check = (
            self._v9_practice_cancellation_reason if _uses_v9_practice(self.config.mode) else None
        )
        with PokemonRedEmulator(self.rom_path) as emulator:
            emulator.load_state(FrozenSnapshot.from_checkpoint_dict(source["snapshot"]).thaw())
            reader = PokemonRedStateReader(emulator)
            current = preprocess_apprentice_frame(emulator.screen_rgb())
            previous = current
            for step in range(limit):
                _check_v9_practice_cancellation(cancellation_check)
                action, recurrent_state = self._predict_student_action(
                    {
                        "pixels": np.stack((previous, current)),
                        "action_history": _action_history(recent),
                        "target_pixels": target_clip,
                    },
                    recurrent_state,
                    episode_start=step == 0,
                )
                actions += 1
                if not _execute_action(emulator, action):
                    break
                recent.append(action)
                previous = current
                current = preprocess_apprentice_frame(emulator.screen_rgb())
                state = reader.read()
                progress = milestone_progress_for_state(state, inherited=inherited)
                best = max(best, progress.index)
                if progress.index >= target_index:
                    return True, best, actions
        return False, best, actions

    def _competent_skill_chain(self) -> list[dict[str, Any]]:
        if self.self_skills is None:
            return []
        by_source: dict[str, list[dict[str, Any]]] = {}
        for skill in self.self_skills.skills:
            if bool(skill.get("competent", False)):
                by_source.setdefault(str(skill["source_entry_id"]), []).append(skill)

        def best_path(
            current: str,
            visiting: frozenset[str],
        ) -> list[dict[str, Any]]:
            if current in visiting:
                return []
            candidates = [
                [
                    skill,
                    *best_path(
                        str(skill["target_entry_id"]),
                        visiting | frozenset({current}),
                    ),
                ]
                for skill in by_source.get(current, [])
            ]
            if not candidates:
                return []
            return max(
                candidates,
                key=lambda path: (
                    int(path[-1]["target_index"]),
                    len(path),
                    tuple(str(item["skill_id"]) for item in path),
                ),
            )

        return best_path(self.self_skills.root_entry_id, frozenset())

    def _run_frozen_composition_attempt(
        self,
        chain: list[dict[str, Any]],
    ) -> tuple[bool, int]:
        if not chain:
            return False, 0
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        root_metadata = next(
            entry
            for entry in manifest["entries"]
            if str(entry["entry_id"]) == str(chain[0]["source_entry_id"])
        )
        root = _load_curriculum_entry(self.curriculum_directory, root_metadata)
        inherited = _progress_from_value(root["progress"])
        targets = [self._v8_target_clip(skill) for skill in chain]
        limit = max(
            1,
            int(
                np.ceil(
                    sum(int(skill["action_count"]) for skill in chain)
                    * self.config.frozen_exam_action_multiplier
                )
            ),
        )
        recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
        recurrent_state: Any | None = None
        current_skill = 0
        actions = 0
        cancellation_check = (
            self._v9_practice_cancellation_reason if _uses_v9_practice(self.config.mode) else None
        )
        with PokemonRedEmulator(self.rom_path) as emulator:
            emulator.load_state(FrozenSnapshot.from_checkpoint_dict(root["snapshot"]).thaw())
            reader = PokemonRedStateReader(emulator)
            current = preprocess_apprentice_frame(emulator.screen_rgb())
            previous = current
            for step in range(limit):
                _check_v9_practice_cancellation(cancellation_check)
                action, recurrent_state = self._predict_student_action(
                    {
                        "pixels": np.stack((previous, current)),
                        "action_history": _action_history(recent),
                        "target_pixels": targets[current_skill],
                    },
                    recurrent_state,
                    episode_start=step == 0,
                )
                actions += 1
                if not _execute_action(emulator, action):
                    break
                recent.append(action)
                previous = current
                current = preprocess_apprentice_frame(emulator.screen_rgb())
                progress = milestone_progress_for_state(reader.read(), inherited=inherited)
                while current_skill < len(chain) and progress.index >= int(
                    chain[current_skill]["target_index"]
                ):
                    current_skill += 1
                if current_skill == len(chain):
                    return True, actions
        return False, actions

    def _run_frozen_exam_round(self) -> bool:
        if self.self_skills is None or not _uses_frozen_exam(self.config.mode):
            return False
        if not self.self_skills.skills:
            self.self_skills.last_frozen_exam_actions = self.model.num_timesteps
            self._write_self_skills()
            return False
        evaluation_model = self.model if _is_v12_mode(self.config.mode) else self.student_model
        if evaluation_model is None:
            return False
        previous_mode = bool(evaluation_model.policy.training)
        previous_exam_rng_state = self.exam_rng.getstate()
        evaluation_model.policy.set_training_mode(False)
        actions = 0
        competence_passed = False
        try:
            if _uses_v9_practice(self.config.mode):
                _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            manifest = _load_curriculum_manifest(self.curriculum_directory)
            choice = choose_v8_self_taught_episode(
                manifest["entries"],
                self.self_skills,
                self.exam_rng,
                frontier_probability=0,
            )
            if choice.skill_id is not None:
                skill = self.self_skills.skill(choice.skill_id)
                self.last_exam_skill_label = str(skill["target_label"])
                success, best, used = self._run_frozen_skill_attempt(skill)
                actions += used
                competence_passed |= self.self_skills.record_episode(
                    mode=choice.mode,
                    skill_id=choice.skill_id,
                    best_reached_index=(int(skill["target_index"]) if success else best),
                )
            else:
                chain = self._competent_skill_chain()
                self.last_exam_skill_label = "Power-on composition"
                target_index = int(chain[-1]["target_index"]) if chain else 0
                hall_of_fame_target = (
                    target_index > 0 and MILESTONES[target_index - 1].key == HALL_OF_FAME_KEY
                )
                success, used = self._run_frozen_composition_attempt(chain)
                actions += used
                self.self_skills.record_composition_exam(
                    success=success,
                    actions=used,
                    target_index=target_index,
                    hall_of_fame_target=hall_of_fame_target,
                )
        except V9PracticeCancelled as cancellation:
            self.exam_rng.setstate(previous_exam_rng_state)
            self.stop_reason = cancellation.reason
            return False
        finally:
            evaluation_model.policy.set_training_mode(previous_mode)
        self.self_skills.record_frozen_exam_round(actions=actions)
        self.self_skills.last_frozen_exam_actions = self.model.num_timesteps
        self.self_skills.exam_rng_state = _random_state_to_json(self.exam_rng.getstate())
        self._write_self_skills()
        self._checkpoint()
        exam_label = "V12 checkpoint" if _is_v12_mode(self.config.mode) else "Student"
        self._narrative(
            f"frozen {exam_label} exam: {self.last_exam_skill_label or 'unknown skill'}"
        )
        return competence_passed

    def _run_v12_terminal_evaluation(self) -> dict[str, Any] | None:
        """Evaluate the terminal V12 checkpoint once with no learning or restored subskills."""

        if self.v12_learning is None or self.self_skills is None:
            return None
        model_path = self.run_directory / "ppo-latest.zip"
        if not model_path.is_file():
            raise RuntimeError("V12 terminal evaluation has no sealed policy checkpoint")
        chain = self._competent_skill_chain()
        target_index = int(chain[-1]["target_index"]) if chain else 0
        target_label = _milestone_label(target_index)
        previous_mode = bool(self.model.policy.training)
        self.model.policy.set_training_mode(False)
        try:
            success, actions = self._run_frozen_composition_attempt(chain)
        finally:
            self.model.policy.set_training_mode(previous_mode)
        hall_of_fame_target = (
            target_index > 0 and MILESTONES[target_index - 1].key == HALL_OF_FAME_KEY
        )
        if chain:
            self.self_skills.record_composition_exam(
                success=success,
                actions=actions,
                target_index=target_index,
                hall_of_fame_target=hall_of_fame_target,
            )
            self._write_self_skills()
        result = {
            "protocol": "v12-terminal-frozen-composition-v1",
            "evaluated_at": datetime.now(UTC).isoformat(),
            "policy_file": model_path.name,
            "policy_sha256": _sha256_file(model_path),
            "policy_actions": actions,
            "policy_updates_during_evaluation": 0,
            "restores_between_skills": 0,
            "trainer_selected_buttons": 0,
            "competent_skill_count": len(chain),
            "skill_ids": [str(skill["skill_id"]) for skill in chain],
            "target_index": target_index,
            "target_label": target_label,
            "success": success,
            "hall_of_fame_target": hall_of_fame_target,
            "hall_of_fame_verified": bool(success and hall_of_fame_target),
        }
        self.v12_learning["terminal_evaluation"] = result
        self._write_v12_learning()
        _atomic_json(self.run_directory / "terminal-evaluation.json", result)
        return result

    def _on_rollout_start(self) -> None:
        if _is_v12_mode(self.config.mode):
            self._train_pending_v12_hindsight()
        if _is_distilled_student_mode(self.config.mode):
            if _uses_v9_practice(self.config.mode):
                reason = self._v9_practice_cancellation_reason()
                if reason is not None:
                    self.stop_reason = reason
                    return
            self._train_v8_student()
            if self._run_v9_practice_round():
                self._narrative("closed-loop Student practice expanded one rung backward")
            return
        if self.self_skills is None or not self.self_imitation_pending:
            return
        skills = self.self_skills.skills
        selected = (
            skills
            if len(skills) <= 8
            else [skills[int(index)] for index in np.linspace(0, len(skills) - 1, num=8, dtype=int)]
        )
        datasets: list[Path] = []
        for skill in selected:
            path = self.run_directory / str(skill["dataset_file"])
            if _sha256_file(path) != skill["dataset_sha256"]:
                raise ValueError("Self-imitation dataset failed its recorded hash")
            target = self.run_directory / str(skill["target_frame_file"])
            if _sha256_file(target) != skill["target_frame_sha256"]:
                raise ValueError("Self-generated visual target failed its recorded hash")
            datasets.append(path)
        result = _train_self_imitation_policy(
            self.model,
            datasets,
            epochs=self.config.self_imitation_epochs,
        )
        self.self_skills.record_imitation(
            updates=int(result["updates"]),
            examples=int(result["examples"]),
            mean_loss=float(result["mean_loss"]),
        )
        self.self_imitation_pending = self.self_skills.imitation_pending
        self._write_self_skills()
        self._narrative("rehearsed self-generated verified skills")

    def _on_rollout_end(self) -> None:
        if _is_v12_mode(self.config.mode):
            self._collect_v12_hindsight()

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
                cancellation_check=(
                    self._v9_practice_cancellation_reason
                    if _uses_v9_practice(self.config.mode)
                    else None
                ),
            )
            source_png = candidate_path.with_suffix("").with_suffix(".png")
            prepared_skill = self._prepare_self_generated_skill(verification, progress, source_png)
            if _uses_v9_practice(self.config.mode):
                _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            if isinstance(prepared_skill, _PreparedV9Skills):
                self._commit_v9_candidate(verification, prepared_skill)
            else:
                admit_verified_candidate(self.curriculum_directory, verification)
                self._commit_self_generated_skill(prepared_skill)
            if self.consolidation is not None:
                updated_manifest = _load_curriculum_manifest(self.curriculum_directory)
                self.consolidation.sync_curriculum(updated_manifest["entries"])
                self._write_consolidation()
            if source_png.is_file():
                shutil.copy2(
                    source_png,
                    self.run_directory / "milestones" / f"{progress.index:03d}-{progress.key}.png",
                )
            self._checkpoint()
            self._narrative(f"verified {progress.label}")
        except V9PracticeCancelled as cancellation:
            # Candidate preparation is intentionally staged before curriculum
            # admission. A campaign boundary can therefore discard partial private
            # artifacts without admitting a lesson or training from it.
            self.stop_reason = cancellation.reason
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
        competence_gate_passed = False
        self_skill_passed = False
        for info in infos:
            if not isinstance(info, Mapping):
                continue
            if info.get("episode_end"):
                self.episodes += 1
                if self.consolidation is not None:
                    competence_gate_passed |= self.consolidation.record_episode(
                        start_mode=str(info.get("start_mode", "")),
                        start_index=int(info.get("starting_milestone_index", -1)),
                        target_index=int(info.get("consolidation_target_index", -1)),
                        best_reached_index=int(info.get("episode_best_index", -1)),
                    )
                    self._write_consolidation()
                if self.self_skills is not None and not _is_v12_mode(self.config.mode):
                    self_skill_passed |= self.self_skills.record_episode(
                        mode=str(info.get("start_mode", "")),
                        skill_id=(
                            str(info["self_skill_id"])
                            if info.get("self_skill_id") is not None
                            else None
                        ),
                        best_reached_index=int(info.get("episode_best_index", -1)),
                    )
                    self._write_self_skills()
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
            self._record_explorer_loop_recovery(info)
            end_reason = info.get("episode_end_reason")
            if isinstance(end_reason, str):
                self.episode_end_reasons[end_reason] += 1
            candidate = info.get("promotion_candidate")
            if isinstance(candidate, str):
                self._handle_candidate(Path(candidate))
                if self.stop_reason is not None:
                    break

        if (
            self.stop_reason is None
            and _uses_frozen_exam(self.config.mode)
            and self.self_skills is not None
            and self.model.num_timesteps - self.self_skills.last_frozen_exam_actions
            >= self.config.frozen_exam_interval_actions
        ):
            self_skill_passed |= self._run_frozen_exam_round()

        if competence_gate_passed:
            self._narrative("training competence gate expanded one checkpoint backward")
        if self_skill_passed:
            self._narrative("self-generated skill passed its rolling competence gate")

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
            elif _hall_of_fame_stop_is_verified(self.config.mode, status, self.self_skills):
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


def _remaining_action_budget(max_actions: int, current_actions: int, *, resume: bool) -> int:
    """Give a retained fresh campaign a new counter while continuing a true resume counter."""

    return max(1, max_actions - current_actions) if resume else max_actions


def run_parallel_ppo(
    rom_path: Path,
    run_directory: Path,
    curriculum_source: Path | None,
    learner_path: Path | None,
    config: ParallelPpoConfig,
    *,
    resume: bool = False,
    policy_source: Path | None = None,
    v7_denominator: Path | None = None,
) -> dict[str, Any]:
    rom = verify_rom(rom_path).public_dict()
    source = detect_source_provenance(
        include_untracked=_requires_reproducible_source(config.mode)
    ).public_dict()
    if _requires_reproducible_source(config.mode):
        _require_reproducible_v8_source(source)
    if _is_v12_mode(config.mode) and curriculum_source is not None:
        raise ValueError("V12 creates its own clean power-on root and rejects curriculum imports")
    if not _is_v12_mode(config.mode) and curriculum_source is None:
        raise ValueError("This PPO mode requires a verified curriculum source")
    if v7_denominator is not None and (not _is_v8_mode(config.mode) or resume):
        raise ValueError("A V7 denominator may be locked only when a fresh V8 run begins")
    denominator_snapshot = (
        _snapshot_v7_denominator(v7_denominator) if v7_denominator is not None else None
    )
    if policy_source is not None and not config.consolidation:
        raise ValueError("A retained policy source requires consolidation mode")
    if _is_self_taught_mode(config.mode) and policy_source is not None:
        raise ValueError("Self-taught PPO cannot import a predecessor policy")
    run_directory = run_directory.expanduser().resolve()
    if run_directory.exists() and not resume:
        raise ValueError("PPO output directory already exists")
    run_directory.mkdir(parents=True, exist_ok=resume)
    for name in (
        "candidate-spool",
        "milestones",
        "self-skills",
        "student-practice",
        "hindsight",
    ):
        (run_directory / name).mkdir(exist_ok=True)
    curriculum_directory = run_directory / "curriculum"
    if not curriculum_directory.exists():
        if _is_v12_mode(config.mode):
            create_verified_power_on_curriculum(
                rom_path,
                curriculum_directory,
                target_protocol=_ppo_protocol(config.mode),
            )
        else:
            if curriculum_source is None:
                raise ValueError("This PPO mode requires a verified curriculum source")
            freeze_verified_curriculum(
                curriculum_source,
                curriculum_directory,
                target_protocol=_ppo_protocol(config.mode),
            )
            if config.power_on_only:
                _retain_power_on_only(curriculum_directory)
    consolidation_path = run_directory / "consolidation.json"
    if config.consolidation and not consolidation_path.exists() and not resume:
        curriculum_manifest = _load_curriculum_manifest(curriculum_directory)
        consolidation = BackwardConsolidation.initialize(
            curriculum_manifest["entries"],
            window_size=config.competence_window,
            threshold=config.competence_threshold,
        )
        _atomic_json(consolidation_path, consolidation.public_dict())
    self_skills_path = run_directory / "self-skills.json"
    if _is_self_taught_mode(config.mode) and not self_skills_path.exists() and not resume:
        curriculum_manifest = _load_curriculum_manifest(curriculum_directory)
        library = SelfTaughtSkillLibrary.initialize(
            curriculum_manifest["entries"],
            window_size=config.competence_window,
            threshold=config.competence_threshold,
        )
        _atomic_json(self_skills_path, library.public_dict())
    v12_learning_path = run_directory / "v12-learning.json"
    if _is_v12_mode(config.mode) and not v12_learning_path.exists() and not resume:
        _atomic_json(v12_learning_path, _new_v12_learning_state())
    started_at = datetime.now(UTC).isoformat()
    base_elapsed = 0.0
    checkpoint_path = run_directory / "checkpoint.json"
    model_path = run_directory / "ppo-latest.zip"
    student_model_path = run_directory / "student-latest.zip"
    student_optimizer_path = run_directory / "student-optimizer.pt"
    retained_policy_path: Path | None = None
    retained_policy_info: dict[str, Any] | None = None
    novelty_by_rank: dict[int, str] = {}
    if resume:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("protocol") != _ppo_protocol(config.mode):
            raise ValueError("PPO checkpoint uses a different protocol")
        if checkpoint.get("config") != config.public_dict():
            raise ValueError("PPO resume configuration does not match")
        _validate_checkpoint_identity(
            checkpoint,
            source=source,
            rom=rom,
            required=_requires_reproducible_source(config.mode),
        )
        run_manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
        if _is_v8_mode(config.mode) and checkpoint.get("v7_denominator") != (
            run_manifest.get("v7_denominator")
        ):
            raise ValueError("V8 denominator identity does not match its checkpoint")
        if checkpoint.get("curriculum_checkpoint_file") is not None:
            _restore_curriculum_state(
                run_directory,
                curriculum_directory,
                checkpoint,
                protocol=_ppo_protocol(config.mode),
            )
        elif _requires_reproducible_source(config.mode):
            raise ValueError("Modern self-taught checkpoint has no bound curriculum snapshot")
        else:
            legacy_curriculum = _load_curriculum_manifest(curriculum_directory)
            if legacy_curriculum.get("best_milestone") != checkpoint.get("best_milestone"):
                raise ValueError("Legacy PPO curriculum moved beyond its checkpoint")
        try:
            model_path = _resolve_checkpoint_artifact(
                run_directory,
                latest_name="ppo-latest.zip",
                previous_name="ppo-previous.zip",
                expected_sha256=checkpoint.get("model_file_sha256"),
            )
        except ValueError as error:
            raise ValueError("PPO model does not match its checkpoint") from error
        if config.consolidation:
            expected_consolidation_hash = checkpoint.get("consolidation_file_sha256")
            if (
                not consolidation_path.is_file()
                or _sha256_file(consolidation_path) != expected_consolidation_hash
            ):
                raise ValueError("PPO consolidation state does not match its checkpoint")
        if _is_self_taught_mode(config.mode):
            library = _restore_self_skill_state(run_directory, checkpoint)
            for skill in library.skills:
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
                        label="PPO self-taught skill artifact",
                    )
                for shard in skill.get("replay_shards", []):
                    shard_path = _validate_hashed_run_artifact(
                        run_directory,
                        shard["file"],
                        shard["sha256"],
                        label="PPO bounded replay shard",
                    )
                    if shard_path.stat().st_size != int(shard["stored_bytes"]):
                        raise ValueError("PPO bounded replay shard size disagrees with ledger")
            for composition in library.composition_replays:
                for file_key, hash_key in (
                    ("dataset_file", "dataset_sha256"),
                    ("audit_file", "audit_sha256"),
                ):
                    _validate_hashed_run_artifact(
                        run_directory,
                        composition[file_key],
                        composition.get(hash_key),
                        label="PPO composition replay artifact",
                    )
        if _is_distilled_student_mode(config.mode):
            if checkpoint.get("student_model_file") != "student-latest.zip":
                raise ValueError("Checkpoint has no separate Student model")
            try:
                student_model_path = _resolve_checkpoint_artifact(
                    run_directory,
                    latest_name="student-latest.zip",
                    previous_name="student-previous.zip",
                    expected_sha256=checkpoint.get("student_model_file_sha256"),
                )
            except ValueError as error:
                raise ValueError("Student model does not match its checkpoint") from error
            if checkpoint.get("student_optimizer_file") != "student-optimizer.pt":
                raise ValueError("Checkpoint has no separate Student optimizer")
            try:
                student_optimizer_path = _resolve_checkpoint_artifact(
                    run_directory,
                    latest_name="student-optimizer.pt",
                    previous_name="student-optimizer.previous.pt",
                    expected_sha256=checkpoint.get("student_optimizer_file_sha256"),
                )
            except ValueError as error:
                raise ValueError("Student optimizer does not match its checkpoint") from error
        if _uses_v9_practice(config.mode):
            _restore_student_practice_state(run_directory, checkpoint)
        if _is_v12_mode(config.mode):
            if checkpoint.get("v12_learning_file") != "v12-learning.json":
                raise ValueError("V12 checkpoint has no hindsight learning state")
            if (
                not v12_learning_path.is_file()
                or _sha256_file(v12_learning_path)
                != checkpoint.get("v12_learning_file_sha256")
            ):
                raise ValueError("V12 hindsight learning state does not match its checkpoint")
            _validate_v12_learning_state(
                json.loads(v12_learning_path.read_text(encoding="utf-8"))
            )
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
        if config.consolidation:
            if policy_source is None:
                raise ValueError("Consolidation requires a finished PPO policy source")
            retained_policy_path = run_directory / "seed-ppo-policy.zip"
            retained_policy_info = _copy_retained_ppo_policy(
                policy_source.expanduser().resolve(),
                retained_policy_path,
                config,
            )
        elif not config.random_initialization:
            if learner_path is None:
                raise ValueError("Warm-start PPO requires a frontier learner checkpoint")
            shutil.copy2(learner_path, learner_copy)
        _atomic_json(
            run_directory / "manifest.json",
            {
                "schema_version": 1,
                "protocol": _ppo_protocol(config.mode),
                "config": config.public_dict(),
                "source": source,
                "rom": rom,
                "actor_mode": config.mode,
                "human_demonstrations": [],
                "self_generated_verified_curriculum": True,
                "curriculum_source": (
                    "direct_verified_clean_boot"
                    if curriculum_source is None
                    else curriculum_source.name
                ),
                "novelty_scope": "persistent per worker across episodes and resumes",
                "reward_protocol": _ppo_reward_protocol(config.mode),
                "rom_path_recorded": False,
                "resume_semantics": "model_optimizer_exact_environment_rollout_restarts",
                **(
                    {"v7_denominator": denominator_snapshot}
                    if denominator_snapshot is not None
                    else {}
                ),
                "policy_initialization": (
                    {
                        "kind": "random_untrained_policy",
                        "imported_actions": 0,
                        "imported_parameters": 0,
                    }
                    if config.random_initialization
                    else retained_policy_info
                ),
                **(
                    {
                        "v12_architecture": {
                            "actor": "one recurrent goal-conditioned visual PPO policy",
                            "online_decision_model_calls": 0,
                            "network_gameplay_calls": 0,
                            "pretrained_components": [],
                            "imported_actions": 0,
                            "imported_parameters": 0,
                            "starting_state": "direct replay-verified clean ROM power-on",
                            "ordinary_learning": (
                                "on-policy PPO plus future-frame hindsight imitation from the "
                                "same policy's own rollouts"
                            ),
                            "rare_discovery_learning": (
                                "replay-verified self-generated visual skills and rehearsal"
                            ),
                            "competence_authority": (
                                "deterministic no-update checkpoint exams and terminal "
                                "power-on composition evaluation"
                            ),
                            "recovery": PIXEL_LOOP_RECOVERY_PROTOCOL,
                            "trainer_selected_buttons": 0,
                            "actor_visible_ram": False,
                            "actor_visible_maps_or_coordinates": False,
                            "authored_route_or_quest_plan": False,
                        },
                        "fixed_experiment_contract": {
                            "duration_seconds": config.duration_seconds,
                            "maximum_actions": config.max_actions,
                            "configuration_sha256": hashlib.sha256(
                                json.dumps(
                                    config.public_dict(),
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ).encode("utf-8")
                            ).hexdigest(),
                            "mid_run_rule_changes_allowed": False,
                            "human_controller_actions_after_launch": 0,
                        },
                    }
                    if _is_v12_mode(config.mode)
                    else {}
                ),
            },
        )
        if retained_policy_path is None and not config.random_initialization:
            learner_path = learner_copy

    _ensure_run_manifest_identity(
        run_directory / "manifest.json",
        source=source,
        rom=rom,
    )

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
                frontier_probability=config.frontier_probability,
                consolidation=config.consolidation,
                self_taught=_is_self_taught_mode(config.mode),
                novelty_checkpoint_file=novelty_by_rank.get(rank),
                explorer_recovery_window_actions=config.explorer_recovery_window_actions,
                explorer_recovery_blocked_threshold=(config.explorer_recovery_blocked_threshold),
                explorer_recovery_escape_confirmations=(
                    config.explorer_recovery_escape_confirmations
                ),
                explorer_recovery_ineffective_change_fraction=(
                    config.explorer_recovery_ineffective_change_fraction
                ),
                explorer_recovery_ineffective_mean_absolute_error=(
                    config.explorer_recovery_ineffective_mean_absolute_error
                ),
                explorer_recovery_escape_change_fraction=(
                    config.explorer_recovery_escape_change_fraction
                ),
                explorer_recovery_escape_mean_absolute_error=(
                    config.explorer_recovery_escape_mean_absolute_error
                ),
                explorer_recovery_blocked_penalty=config.explorer_recovery_blocked_penalty,
                explorer_recovery_escape_reward=config.explorer_recovery_escape_reward,
                explorer_recovery_expiration_penalty=(config.explorer_recovery_expiration_penalty),
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
    elif retained_policy_path is not None:
        model = RecurrentPPO.load(retained_policy_path, env=vector, device="cpu")
        model.tensorboard_log = str(run_directory / "tensorboard")
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
        if not config.random_initialization:
            if learner_path is None:
                raise ValueError("Warm-start PPO requires a frontier learner checkpoint")
            seed_info = _warm_start(
                model,
                learner_path,
                privileged=config.mode == "privileged",
                assisted=config.mode == "assisted",
            )
            manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
            manifest["warm_start"] = seed_info
            _atomic_json(run_directory / "manifest.json", manifest)
    student_model: Any | None = None
    student_trainer: SequenceAwareStudentTrainer | None = None
    if _is_distilled_student_mode(config.mode):
        if resume:
            student_model = RecurrentPPO.load(student_model_path, device="cpu")
        else:
            temporary_seed = run_directory / "student-seed.tmp.zip"
            model.save(temporary_seed)
            try:
                student_model = RecurrentPPO.load(temporary_seed, device="cpu")
            finally:
                temporary_seed.unlink(missing_ok=True)
        student_config = SequenceTrainingConfig(
            burn_in=config.student_burn_in,
            train_length=config.student_train_horizon,
            stride=max(1, config.student_train_horizon // 2),
            learning_rate=config.student_learning_rate,
            diagnostic_chunk_length=max(128, config.student_train_horizon * 4),
        )
        student_trainer = SequenceAwareStudentTrainer(
            student_model,
            student_config,
        )
        if resume:
            optimizer_state = torch.load(
                student_optimizer_path,
                map_location="cpu",
                weights_only=True,
            )
            student_trainer.load_optimizer_state_dict(optimizer_state)
        else:
            manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
            architecture_key = (
                "v10_architecture"
                if _is_v10_mode(config.mode)
                else "v9_architecture"
                if _is_v9_mode(config.mode)
                else "v8_architecture"
            )
            manifest[architecture_key] = {
                "explorer": "PPO policy updated only from online blind exploration",
                "student": (
                    "independent recurrent policy updated from distilled replay and closed-loop "
                    "success-only self-practice"
                    if _uses_v9_practice(config.mode)
                    else "independent recurrent policy updated only from self-generated replay"
                ),
                "initial_parameters_identical": True,
                "shared_parameters_after_initialization": False,
                "human_demonstrations": [],
                "goal_observation": "three self-observed terminal frames",
                "competence_authority": "frozen deterministic Student exams",
                "closed_loop_practice": _uses_v9_practice(config.mode),
                "recovery_ppo": (
                    "gated_future_escalation" if _uses_v9_practice(config.mode) else None
                ),
                **(
                    {
                        "explorer_loop_recovery": {
                            "protocol": PIXEL_LOOP_RECOVERY_PROTOCOL,
                            "inputs": ["preprocessed_rendered_pixels", "policy_selected_action"],
                            "actor_action_overrides": 0,
                            "uses_authored_guidance": False,
                            "episode_local_state": True,
                            "cycle_window_actions": V10_RECOVERY_CYCLE_WINDOW,
                            "cycle_unique_limit": V10_RECOVERY_CYCLE_UNIQUE_LIMIT,
                            "long_stagnation_actions": V10_RECOVERY_STAGNATION_ACTIONS,
                            "resume_behavior": ("fresh_rollout_counts_inflight_windows_abandoned"),
                        }
                    }
                    if _is_v10_mode(config.mode)
                    else {}
                ),
            }
            _atomic_json(run_directory / "manifest.json", manifest)
    callback = PpoRunCallback(
        run_directory,
        rom_path,
        curriculum_directory,
        config,
        base_elapsed=base_elapsed,
        started_at=started_at,
        student_model=student_model,
        student_trainer=student_trainer,
    )
    server = _start_server(run_directory, config.dashboard_port)
    reason = "completed"
    try:
        remaining = _remaining_action_budget(
            config.max_actions,
            model.num_timesteps,
            resume=resume,
        )
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
        callback._abandon_active_recoveries("campaign_end")
        if _is_v12_mode(config.mode):
            callback._train_pending_v12_hindsight()
            callback._checkpoint()
            terminal = callback._run_v12_terminal_evaluation()
            if terminal is not None and terminal["hall_of_fame_verified"]:
                reason = "hall_of_fame_verified"
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
