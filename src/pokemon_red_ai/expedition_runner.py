from __future__ import annotations

import base64
import binascii
import contextlib
import gzip
import hashlib
import html
import json
import os
import random
import shutil
import signal
import threading
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from types import FrameType
from typing import Any
from urllib.parse import urlsplit

import numpy as np
from PIL import Image

from pokemon_red_ai.apprentice_data import preprocess_apprentice_frame
from pokemon_red_ai.apprentice_model import build_apprentice_policy, require_torch
from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    FrozenSnapshot,
    PixelsOnlyActor,
    visual_key,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    EXPEDITION_PROTOCOL_VERSION,
    ExpeditionStore,
    FrontierArchive,
    FrontierCell,
    FrontierDescriptor,
    MilestoneProgress,
    ReplayResult,
    descriptor_from_state,
    milestone_progress_for_state,
    referee_summary_for_state,
    replay_frontier_cell,
    replay_frontier_edge,
)
from pokemon_red_ai.milestones import HALL_OF_FAME_KEY, MILESTONES, MilestoneTracker
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import RomFingerprint
from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader

EXPEDITION_RUNNER_PROTOCOL_VERSION = "checkpoint-expedition-runner-v2"
EXPEDITION_RUNNER_CHECKPOINT_SCHEMA = 2
POWER_ON_PROGRESS = MilestoneProgress("power_on", 0, "Power-on")
_CHECKPOINT_FRAME_SHAPE = (144, 160, 3)
_CHECKPOINT_FRAME_ENCODING = "rgb24-base64-v1"
RANDOM_EXPEDITION_EMITTER = "seeded_random"
APPRENTICE_HYBRID_EMITTER = "visual_apprentice_hybrid"
LEFT_HOME_MILESTONE_INDEX = next(
    index for index, milestone in enumerate(MILESTONES, start=1) if milestone.key == "left_home"
)


@dataclass(frozen=True, slots=True)
class ExpeditionRunConfig:
    """Bound every resource that can grow during a checkpoint expedition."""

    duration_seconds: float = 7_200
    max_actions: int = 1_000_000
    seed: int = 20_260_719
    archive_capacity: int = 4_096
    min_suffix_actions: int = 32
    max_suffix_actions: int = 1_024
    attempts_per_expansion: int = 8
    frontier_capture_interval_actions: int = 8
    loop_window_actions: int = 64
    loop_repeat_limit: int = 12
    frontier_probability: float = 0.75
    rehearsal_probability: float = 0.10
    verify_milestone_replays: bool = True
    promotion_replay_passes: int = 3
    dashboard_port: int = 0
    status_interval_seconds: float = 10
    disk_reconcile_interval_actions: int = 4_096
    disk_free_check_interval_seconds: float = 5
    max_output_bytes: int = 4 * 1024 * 1024 * 1024
    min_free_bytes: int = 50 * 1024 * 1024 * 1024
    emitter_kind: str = RANDOM_EXPEDITION_EMITTER
    apprentice_model_sha256: str = ""
    apprentice_pre_frontier_epsilon: float = 0.02
    apprentice_post_frontier_epsilon: float = 0.35

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0 or self.max_actions < 1:
            raise ValueError("Expedition duration and action limit must be positive")
        if self.archive_capacity < 2:
            raise ValueError("Expedition archive capacity must be at least two")
        if self.min_suffix_actions < 1 or self.max_suffix_actions < self.min_suffix_actions:
            raise ValueError("Expedition suffix limits are invalid")
        if self.attempts_per_expansion < 1:
            raise ValueError("Expedition attempts per expansion must be positive")
        if self.frontier_capture_interval_actions < 1:
            raise ValueError("Expedition frontier capture interval must be positive")
        if self.loop_window_actions < 2:
            raise ValueError("Expedition loop window must contain at least two actions")
        if not 2 <= self.loop_repeat_limit <= self.loop_window_actions:
            raise ValueError("Expedition loop repeat limit must fit inside the loop window")
        if not 0 <= self.frontier_probability <= 1:
            raise ValueError("Expedition frontier probability must be between zero and one")
        if not 0 <= self.rehearsal_probability <= 1:
            raise ValueError("Expedition rehearsal probability must be between zero and one")
        if self.frontier_probability + self.rehearsal_probability > 1:
            raise ValueError("Expedition selection probabilities cannot exceed one")
        if not self.verify_milestone_replays:
            raise ValueError("Expedition milestone replay verification cannot be disabled")
        if self.promotion_replay_passes < 3:
            raise ValueError("Expedition milestone promotions require at least three replays")
        if not 0 <= self.dashboard_port <= 65_535:
            raise ValueError("Expedition dashboard port must be zero or a valid TCP port")
        if self.status_interval_seconds <= 0:
            raise ValueError("Expedition status interval must be positive")
        if self.disk_reconcile_interval_actions < 1:
            raise ValueError("Expedition disk reconciliation interval must be positive")
        if self.disk_free_check_interval_seconds <= 0:
            raise ValueError("Expedition free-space check interval must be positive")
        if self.max_output_bytes < 1_048_576 or self.min_free_bytes < 0:
            raise ValueError("Expedition disk limits are invalid")
        if self.emitter_kind not in {RANDOM_EXPEDITION_EMITTER, APPRENTICE_HYBRID_EMITTER}:
            raise ValueError("Expedition emitter kind is invalid")
        if not 0 <= self.apprentice_pre_frontier_epsilon <= 1:
            raise ValueError("Pre-frontier apprentice exploration must be a probability")
        if not 0 <= self.apprentice_post_frontier_epsilon <= 1:
            raise ValueError("Post-frontier apprentice exploration must be a probability")
        if self.emitter_kind == APPRENTICE_HYBRID_EMITTER:
            if (
                len(self.apprentice_model_sha256) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in self.apprentice_model_sha256
                )
            ):
                raise ValueError("Hybrid expedition requires the frozen apprentice model SHA-256")
        elif self.apprentice_model_sha256:
            raise ValueError("Random expeditions cannot declare an apprentice model")

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ExpeditionCounters:
    total_actions: int = 0
    total_frames: int = 0
    attempts: int = 0
    archive_restores: int = 0
    cells_created: int = 0
    cells_admitted: int = 0
    cells_rejected: int = 0
    ordinary_preflight_rejections: int = 0
    loop_stops: int = 0
    emulator_stops: int = 0
    replay_attempts: int = 0
    replay_actions: int = 0
    replay_passes: int = 0
    edge_replay_attempts: int = 0
    edge_replay_actions: int = 0
    edge_replay_passes: int = 0
    promotion_power_on_replay_attempts: int = 0
    promotion_power_on_replay_actions: int = 0
    promotion_power_on_replay_passes: int = 0
    elapsed_seconds: float = 0
    action_counts: Counter[str] = field(default_factory=Counter)

    def checkpoint_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["action_counts"] = dict(sorted(self.action_counts.items()))
        return value

    @classmethod
    def from_checkpoint_dict(cls, value: Mapping[str, Any]) -> ExpeditionCounters:
        names = (
            "total_actions",
            "total_frames",
            "attempts",
            "archive_restores",
            "cells_created",
            "cells_admitted",
            "cells_rejected",
            "ordinary_preflight_rejections",
            "loop_stops",
            "emulator_stops",
            "replay_attempts",
            "replay_actions",
            "replay_passes",
            "edge_replay_attempts",
            "edge_replay_actions",
            "edge_replay_passes",
            "promotion_power_on_replay_attempts",
            "promotion_power_on_replay_actions",
            "promotion_power_on_replay_passes",
        )
        integers = {name: int(value.get(name, 0)) for name in names}
        if any(item < 0 for item in integers.values()):
            raise ValueError("Expedition counters cannot be negative")
        if (
            integers["edge_replay_passes"] > integers["edge_replay_attempts"]
            or integers["promotion_power_on_replay_passes"]
            > integers["promotion_power_on_replay_attempts"]
            or integers["edge_replay_actions"] > integers["total_actions"]
            or integers["edge_replay_attempts"] + integers["promotion_power_on_replay_attempts"]
            > integers["replay_attempts"]
            or integers["edge_replay_actions"] + integers["promotion_power_on_replay_actions"]
            > integers["replay_actions"]
            or integers["edge_replay_passes"] + integers["promotion_power_on_replay_passes"]
            > integers["replay_passes"]
        ):
            raise ValueError("Expedition replay counters are inconsistent")
        counts = Counter(
            {str(key): int(count) for key, count in value.get("action_counts", {}).items()}
        )
        if any(action not in BLIND_ACTIONS or count < 0 for action, count in counts.items()):
            raise ValueError("Expedition action counters are invalid")
        return cls(
            **integers,
            elapsed_seconds=float(value.get("elapsed_seconds", 0)),
            action_counts=counts,
        )


@dataclass(frozen=True, slots=True)
class BufferedSuffixCandidate:
    """One private in-memory capture that may become the suffix's sole stored cell."""

    snapshot: FrozenSnapshot
    actions_from_parent: tuple[BlindAction, ...]
    descriptor: FrontierDescriptor
    screen_sha256: str
    discovered_global_action: int
    referee_summary: Mapping[str, int | str | bool | None]
    progress: MilestoneProgress
    pixels: np.ndarray
    priority: tuple[Any, ...]


class SuffixCandidateBuffer:
    """Retain only the strongest ordinary capture until a suffix reaches its boundary."""

    def __init__(self) -> None:
        self.captures_observed = 0
        self.candidate: BufferedSuffixCandidate | None = None

    def offer(self, candidate: BufferedSuffixCandidate) -> bool:
        self.captures_observed += 1
        incumbent = self.candidate
        candidate_rank = (
            candidate.priority,
            -len(candidate.actions_from_parent),
            candidate.screen_sha256,
        )
        incumbent_rank = (
            (
                incumbent.priority,
                -len(incumbent.actions_from_parent),
                incumbent.screen_sha256,
            )
            if incumbent is not None
            else None
        )
        if incumbent_rank is None or candidate_rank > incumbent_rank:
            self.candidate = candidate
            return True
        return False


def _record_edge_replay(counters: ExpeditionCounters, replay: ReplayResult) -> None:
    counters.replay_attempts += 1
    counters.replay_actions += replay.executed_action_count
    counters.replay_passes += int(replay.passed)
    counters.edge_replay_attempts += 1
    counters.edge_replay_actions += replay.executed_action_count
    counters.edge_replay_passes += int(replay.passed)
    if counters.edge_replay_actions > counters.total_actions:
        raise RuntimeError("Ordinary edge replay actions exceeded exploration actions")


def _record_promotion_replay(counters: ExpeditionCounters, replay: ReplayResult) -> None:
    counters.replay_attempts += 1
    counters.replay_actions += replay.executed_action_count
    counters.replay_passes += int(replay.passed)
    counters.promotion_power_on_replay_attempts += 1
    counters.promotion_power_on_replay_actions += replay.executed_action_count
    counters.promotion_power_on_replay_passes += int(replay.passed)


@dataclass(frozen=True, slots=True)
class ExpeditionRunResult:
    run_directory: Path
    stop_reason: str
    counters: ExpeditionCounters
    archive_cells: int
    best_milestone: MilestoneProgress
    completion_cell_id: str | None


class SeededRandomSequenceEmitter:
    """The disclosed first emitter: uniform random actions from a seeded PRNG.

    It receives no RAM, checkpoint, milestone, coordinate, reward, or screen value. The
    pixels-only facade remains in place so a learned visual emitter can replace this baseline
    without widening the actor boundary.
    """

    policy_id = "seeded-uniform-random-sequence-v1"

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng

    def emit(self) -> BlindAction:
        return BlindAction(
            button=self._rng.choice(BLIND_ACTIONS),
            hold_frames=ACTION_HOLD_FRAMES,
            release_frames=ACTION_RELEASE_FRAMES,
        )

    def reset(self, _actor: PixelsOnlyActor, *, exploration_probability: float) -> None:
        del exploration_probability

    def public_identity(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "inputs": ["seeded_prng"],
            "pretrained_components": [],
            "frozen_weights": True,
            "trainer_routes_exploration": False,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_parameter_sha256(model: Any) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous().numpy()
        descriptor = json.dumps(
            {"name": name, "dtype": value.dtype.str, "shape": list(value.shape)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(len(descriptor).to_bytes(8, "big"))
        digest.update(descriptor)
        digest.update(value.tobytes())
    return digest.hexdigest()


class VisualApprenticeHybridEmitter:
    """Frozen pixel policy with disclosed seeded exploration after checkpoint restores."""

    policy_id = "visual-apprentice-frozen-plus-seeded-exploration-v1"

    def __init__(
        self,
        rng: random.Random,
        model_directory: Path,
        *,
        expected_model_sha256: str,
    ) -> None:
        self._rng = rng
        self._actor: PixelsOnlyActor | None = None
        self._previous_frame: np.ndarray | None = None
        self._previous_action = -1
        self._recurrent_state: tuple[Any, Any] | None = None
        self._exploration_probability = 0.0
        directory = model_directory.expanduser().resolve()
        metadata_path = directory / "learner.json"
        model_path = directory / "learner.pt"
        if not metadata_path.is_file() or not model_path.is_file():
            raise ValueError("Hybrid expedition requires a completed apprentice learner bundle")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("development_only") is not True
            or metadata.get("file_sha256") != expected_model_sha256
            or _sha256_file(model_path) != expected_model_sha256
        ):
            raise ValueError("Apprentice learner file does not match its declared identity")
        self._torch = require_torch()
        self._torch.set_num_threads(1)
        with contextlib.suppress(RuntimeError):
            self._torch.set_num_interop_threads(1)
        self._torch.use_deterministic_algorithms(True)
        self._model = build_apprentice_policy().to("cpu")
        state = self._torch.load(model_path, map_location="cpu", weights_only=True)
        self._model.load_state_dict(state, strict=True)
        self._model.eval()
        parameter_sha256 = _model_parameter_sha256(self._model)
        if metadata.get("parameter_sha256") != parameter_sha256:
            raise ValueError("Apprentice learner tensor values do not match their metadata")
        self._identity = {
            "policy_id": self.policy_id,
            "inputs": [
                "two_processed_pixel_frames",
                "previous_action",
                "recurrent_state",
                "seeded_prng_exploration",
            ],
            "pretrained_components": [
                {
                    "kind": "visual_apprentice_reverse_curriculum_development_model",
                    "file_sha256": expected_model_sha256,
                    "parameter_sha256": parameter_sha256,
                }
            ],
            "frozen_weights": True,
            "trainer_routes_exploration": True,
        }

    def public_identity(self) -> dict[str, object]:
        return dict(self._identity)

    def reset(self, actor: PixelsOnlyActor, *, exploration_probability: float) -> None:
        if not 0 <= exploration_probability <= 1:
            raise ValueError("Hybrid exploration probability must be between zero and one")
        self._actor = actor
        current = preprocess_apprentice_frame(actor.observe())
        self._previous_frame = current
        self._previous_action = -1
        self._recurrent_state = None
        self._exploration_probability = exploration_probability

    def emit(self) -> BlindAction:
        if self._actor is None or self._previous_frame is None:
            raise RuntimeError("Hybrid emitter must reset after every checkpoint restore")
        current = preprocess_apprentice_frame(self._actor.observe())
        pair = np.stack((self._previous_frame, current), axis=0)
        with self._torch.no_grad():
            logits, self._recurrent_state = self._model.step(
                self._torch.from_numpy(pair).unsqueeze(0),
                self._torch.tensor([self._previous_action], dtype=self._torch.long),
                self._recurrent_state,
            )
        if self._rng.random() < self._exploration_probability:
            action_index = self._rng.randrange(len(BLIND_ACTIONS))
        else:
            action_index = int(logits.argmax(dim=-1).item())
        self._previous_frame = current
        self._previous_action = action_index
        return BlindAction(
            button=BLIND_ACTIONS[action_index],
            hold_frames=ACTION_HOLD_FRAMES,
            release_frames=ACTION_RELEASE_FRAMES,
        )


class VisualLoopDetector:
    """Stop suffixes that spend too much of a recent window on one rendered screen."""

    def __init__(self, window: int, repeat_limit: int) -> None:
        if window < 2 or not 2 <= repeat_limit <= window:
            raise ValueError("Visual loop settings are invalid")
        self.window = window
        self.repeat_limit = repeat_limit
        self._recent: deque[bytes] = deque()
        self._counts: Counter[bytes] = Counter()

    def observe(self, key: bytes) -> bool:
        if len(key) != 16:
            raise ValueError("Visual loop keys must contain 16 bytes")
        self._recent.append(key)
        self._counts[key] += 1
        if len(self._recent) > self.window:
            removed = self._recent.popleft()
            self._counts[removed] -= 1
            if not self._counts[removed]:
                del self._counts[removed]
        return len(self._recent) >= self.repeat_limit and self._counts[key] >= self.repeat_limit


def adaptive_suffix_budget(
    selection_count: int,
    *,
    minimum: int,
    maximum: int,
    attempts_per_expansion: int,
) -> int:
    """Double a stubborn frontier's horizon, while retaining an explicit hard ceiling."""

    if selection_count < 1 or minimum < 1 or maximum < minimum or attempts_per_expansion < 1:
        raise ValueError("Adaptive suffix inputs are invalid")
    expansions = (selection_count - 1) // attempts_per_expansion
    if expansions >= maximum.bit_length():
        return maximum
    return min(maximum, minimum * (1 << expansions))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _append_json(path: Path, value: Mapping[str, Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(_canonical_json(value) + "\n")
        output.flush()
        os.fsync(output.fileno())
        return output.tell()


def _save_png(pixels: np.ndarray, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    Image.fromarray(pixels).save(temporary, format="PNG", optimize=True)
    os.replace(temporary, path)


def _write_checkpoint(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    previous = path.with_name("checkpoint.previous.json.gz")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=3) as output:
        json.dump(value, output, sort_keys=True, separators=(",", ":"))
    with gzip.open(temporary, "rb") as verification:
        while verification.read(1024 * 1024):
            pass
    if path.exists():
        os.replace(path, previous)
    os.replace(temporary, path)


def _read_checkpoint(path: Path) -> tuple[Path, dict[str, Any]]:
    candidates = (path, path.with_name("checkpoint.previous.json.gz"))
    failures: list[Exception] = []
    legacy_checkpoint_seen = False
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            with gzip.open(candidate, "rt", encoding="utf-8") as source:
                value = json.load(source)
            checkpoint_schema = int(value.get("schema_version", -1))
            if checkpoint_schema == 1:
                legacy_checkpoint_seen = True
                raise ValueError("Legacy expedition runner checkpoint")
            if checkpoint_schema != EXPEDITION_RUNNER_CHECKPOINT_SCHEMA:
                raise ValueError("Unsupported expedition runner checkpoint schema")
            if value.get("protocol_version") != EXPEDITION_RUNNER_PROTOCOL_VERSION:
                raise ValueError("Expedition runner checkpoint uses a different protocol")
            return candidate, value
        except (OSError, EOFError, json.JSONDecodeError, ValueError) as error:
            failures.append(error)
    if legacy_checkpoint_seen:
        raise ValueError(
            "Checkpoint Expedition v1 runs are concluded artifacts and cannot resume under "
            "Archive v2; start a fresh run"
        )
    if failures:
        raise ValueError("No valid expedition runner checkpoint is available") from failures[0]
    raise ValueError("Expedition runner checkpoint does not exist")


def _json_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_json_tuple(item) for item in value)
    if isinstance(value, dict):
        return {key: _json_tuple(item) for key, item in value.items()}
    return value


def _implementation_sha256() -> str:
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in (
        "expedition_runner.py",
        "expedition.py",
        "milestones.py",
        "blind.py",
        "emulator.py",
        "state.py",
        "apprentice_data.py",
        "apprentice_model.py",
    ):
        digest.update(name.encode("utf-8"))
        digest.update((package / name).read_bytes())
    return digest.hexdigest()


def _directory_file_sizes(path: Path) -> dict[Path, int]:
    """Take one exact file-size snapshot of a run tree.

    Callers deliberately use this only at startup, declared action intervals, checkpoints,
    and status writes. Persistent writes between snapshots are accounted for by observing the
    bounded set of files that each operation can touch.
    """

    return {
        item: item.stat().st_size
        for item in path.rglob("*")
        if item.is_file() and item.name != "RUNNING.lock"
    }


def _directory_size(path: Path) -> int:
    return sum(_directory_file_sizes(path).values())


class _RunDiskMonitor:
    """Bound disk checks without recursively walking a growing archive per action."""

    def __init__(
        self,
        output: Path,
        *,
        max_output_bytes: int,
        min_free_bytes: int,
        reconcile_interval_actions: int,
        free_check_interval_seconds: float,
        initial_action_count: int = 0,
        now: float | None = None,
    ) -> None:
        if max_output_bytes < 1 or min_free_bytes < 0:
            raise ValueError("Disk monitor limits are invalid")
        if reconcile_interval_actions < 1 or free_check_interval_seconds <= 0:
            raise ValueError("Disk monitor intervals are invalid")
        self.output = output
        self.max_output_bytes = max_output_bytes
        self.min_free_bytes = min_free_bytes
        self.reconcile_interval_actions = reconcile_interval_actions
        self.free_check_interval_seconds = free_check_interval_seconds
        self.run_bytes = 0
        self.free_bytes = 0
        self.exact_reconciliations = 0
        self.incremental_file_checks = 0
        self.free_space_checks = 0
        self.last_reconciled_action = initial_action_count
        self.output_limit_observed = False
        self._known_file_sizes: dict[Path, int] = {}
        self._last_free_check_at = monotonic() if now is None else now
        self.reconcile(initial_action_count)
        self.check_free(now=self._last_free_check_at, force=True)

    def reconcile(self, action_count: int) -> int:
        """Refresh exact size and seed the incremental per-file ledger."""

        self._known_file_sizes = _directory_file_sizes(self.output)
        self.run_bytes = sum(self._known_file_sizes.values())
        self.exact_reconciliations += 1
        self.last_reconciled_action = action_count
        self.output_limit_observed |= self.run_bytes >= self.max_output_bytes
        return self.run_bytes

    def observe_files(self, *paths: Path) -> int:
        """Account for known persistent writes using bounded individual stat calls."""

        for path in dict.fromkeys(paths):
            previous = self._known_file_sizes.get(path, 0)
            try:
                current = path.stat().st_size if path.is_file() else 0
            except FileNotFoundError:
                current = 0
            self.incremental_file_checks += 1
            self.run_bytes += current - previous
            if current:
                self._known_file_sizes[path] = current
            else:
                self._known_file_sizes.pop(path, None)
        self.output_limit_observed |= self.run_bytes >= self.max_output_bytes
        return self.run_bytes

    def check_free(self, *, now: float | None = None, force: bool = False) -> int:
        checked_at = monotonic() if now is None else now
        if force or checked_at - self._last_free_check_at >= self.free_check_interval_seconds:
            self.free_bytes = shutil.disk_usage(self.output).free
            self.free_space_checks += 1
            self._last_free_check_at = checked_at
        return self.free_bytes

    def reason(self, action_count: int, *, now: float | None = None) -> str | None:
        if action_count - self.last_reconciled_action >= self.reconcile_interval_actions:
            self.reconcile(action_count)
        self.check_free(now=now)
        if self.free_bytes < self.min_free_bytes:
            return "low_disk_space"
        if self.output_limit_observed or self.run_bytes >= self.max_output_bytes:
            return "output_limit"
        return None

    def status_dict(self) -> dict[str, int | float | bool]:
        return {
            "run_bytes": self.run_bytes,
            "free_bytes": self.free_bytes,
            "exact_size_reconciliations": self.exact_reconciliations,
            "incremental_file_checks": self.incremental_file_checks,
            "free_space_checks": self.free_space_checks,
            "last_reconciled_action": self.last_reconciled_action,
            "reconcile_interval_actions": self.reconcile_interval_actions,
            "free_check_interval_seconds": self.free_check_interval_seconds,
            "output_limit_observed": self.output_limit_observed,
        }


def _validate_output_path(output: Path) -> None:
    """Keep private checkpoints out of tracked source directories."""

    project_root = Path(__file__).resolve().parents[2]
    try:
        relative = output.relative_to(project_root)
    except ValueError:
        return
    if not relative.parts or relative.parts[0] != "runs":
        raise ValueError(
            "Expedition output must be outside the Git checkout or inside its ignored "
            "runs/ directory"
        )


def _acquire_single_writer(output: Path) -> Path:
    """Refuse concurrent coordinators, while recovering a lock left by a dead process."""

    lock_path = output / "RUNNING.lock"
    for _attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                owner = int(lock_path.read_text(encoding="ascii").strip())
                os.kill(owner, 0)
            except (OSError, ValueError):
                lock_path.unlink(missing_ok=True)
                continue
            raise RuntimeError(f"Expedition already has a live coordinator (PID {owner})") from None
        with os.fdopen(descriptor, "w", encoding="ascii") as output_stream:
            output_stream.write(f"{os.getpid()}\n")
            output_stream.flush()
            os.fsync(output_stream.fileno())
        return lock_path
    raise RuntimeError("Could not acquire the expedition single-writer lock")


def _release_single_writer(lock_path: Path) -> None:
    try:
        owner = int(lock_path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return
    if owner == os.getpid():
        lock_path.unlink(missing_ok=True)


def _start_dashboard_server(
    output: Path,
    port: int,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Serve only sanitized live artifacts; private frontier payloads are never routable."""

    public_files = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/latest.png": ("latest.png", "image/png"),
        "/status.json": ("status.json", "application/json; charset=utf-8"),
    }

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP callback name
            route = urlsplit(self.path).path
            target = public_files.get(route)
            if target is None:
                self.send_error(404)
                return
            filename, content_type = target
            path = output / filename
            if not path.is_file():
                self.send_error(503, "Dashboard is starting")
                return
            payload = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever,
        name="pokemon-red-expedition-dashboard",
        daemon=True,
    )
    thread.start()
    return server, thread


def _stop_dashboard_server(
    server: ThreadingHTTPServer | None,
    thread: threading.Thread | None,
) -> None:
    if server is None:
        return
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=5)


def _truncate_trace(path: Path, offset: int) -> None:
    size = path.stat().st_size
    if not 0 <= offset <= size:
        raise ValueError("Expedition trace checkpoint is outside the trace")
    with path.open("r+b") as output:
        output.truncate(offset)
        output.flush()
        os.fsync(output.fileno())


def _progress_from_state(
    parent: MilestoneProgress,
    tracker: MilestoneTracker,
    state: PokemonRedState,
) -> tuple[MilestoneProgress, tuple[str, ...]]:
    newly_reached = tracker.observe(state)
    observed = tuple(milestone.key for milestone in newly_reached)
    return milestone_progress_for_state(state, inherited=parent), observed


def _progress_for_cell(cell: FrontierCell) -> MilestoneProgress:
    label = str(cell.referee_summary.get("milestone_label") or cell.descriptor.milestone_id)
    return MilestoneProgress(
        cell.descriptor.milestone_id,
        cell.descriptor.milestone_index,
        label,
    )


def _referee_summary(
    state: PokemonRedState,
    progress: MilestoneProgress,
    *,
    parent: FrontierCell | None,
    tracker: MilestoneTracker,
) -> dict[str, int | str | bool | None]:
    previous_count = 0 if parent is None else int(parent.referee_summary.get("named_milestones", 0))
    named_count = max(previous_count, len(tracker.reached), progress.index)
    summary = referee_summary_for_state(state, progress)
    summary.update(
        {
            "named_milestones": named_count,
            "game_started": state.game_started,
            "player_x": state.player_x,
            "player_y": state.player_y,
            "battle_kind": state.battle_kind,
            "max_party_level": state.max_party_level,
        }
    )
    return summary


def _next_milestone(progress: MilestoneProgress) -> dict[str, object] | None:
    if progress.key == HALL_OF_FAME_KEY:
        return None
    if progress.index < len(MILESTONES):
        return MILESTONES[progress.index].public_dict()
    return None


def _status_payload(
    *,
    state: str,
    stop_reason: str | None,
    config: ExpeditionRunConfig,
    counters: ExpeditionCounters,
    archive: FrontierArchive,
    best_progress: MilestoneProgress,
    started_at: str,
    elapsed_seconds: float,
    run_bytes: int,
    disk_monitor: Mapping[str, int | float | bool],
    current: Mapping[str, Any] | None,
    latest_referee_state: PokemonRedState | None,
    reached_milestones: set[str],
    completion_cell_id: str | None,
    emitter_identity: Mapping[str, object],
) -> dict[str, Any]:
    active = sorted(
        archive.active_cells,
        key=lambda cell: (cell.quality, cell.cell_id),
        reverse=True,
    )
    root = next((cell for cell in active if cell.parent_id is None), None)
    root_gate_passed = bool(
        root is not None and archive.store.successful_replay_count(root.cell_id) >= 1
    )
    return {
        "schema_version": 2,
        "protocol_version": EXPEDITION_RUNNER_PROTOCOL_VERSION,
        "store_protocol_version": EXPEDITION_PROTOCOL_VERSION,
        "run_name": (
            "Checkpoint Expedition — apprentice-guided full-game frontier"
            if emitter_identity.get("policy_id")
            == VisualApprenticeHybridEmitter.policy_id
            else "Checkpoint Expedition — blind suffixes, privileged referee"
        ),
        "run_class": "development",
        "state": state,
        "stop_reason": stop_reason,
        "started_at": started_at,
        "updated_at": datetime.now(UTC).isoformat(),
        "process_id": os.getpid(),
        "dashboard_url": (
            None
            if config.dashboard_port == 0
            else f"http://127.0.0.1:{config.dashboard_port}/index.html"
        ),
        "heartbeat_interval_seconds": config.status_interval_seconds,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "duration_seconds": config.duration_seconds,
        "total_actions": counters.total_actions,
        "max_actions": config.max_actions,
        "total_frames": counters.total_frames,
        "actions_per_second": round(
            counters.total_actions / elapsed_seconds if elapsed_seconds else 0,
            2,
        ),
        "attempts": counters.attempts,
        "archive_cells": len(active),
        "archive_capacity": config.archive_capacity,
        "stored_evidence_cells": len(archive.store.cells),
        "archive_restores": counters.archive_restores,
        "cells_created": counters.cells_created,
        "cells_admitted": counters.cells_admitted,
        "cells_rejected": counters.cells_rejected,
        "ordinary_preflight_rejections": counters.ordinary_preflight_rejections,
        "loop_stops": counters.loop_stops,
        "emulator_stops": counters.emulator_stops,
        "replay_attempts": counters.replay_attempts,
        "replay_actions": counters.replay_actions,
        "replay_passes": counters.replay_passes,
        "edge_replay_attempts": counters.edge_replay_attempts,
        "edge_replay_actions": counters.edge_replay_actions,
        "edge_replay_passes": counters.edge_replay_passes,
        "promotion_power_on_replay_attempts": (counters.promotion_power_on_replay_attempts),
        "promotion_power_on_replay_actions": counters.promotion_power_on_replay_actions,
        "promotion_power_on_replay_passes": counters.promotion_power_on_replay_passes,
        "edge_replay_action_ratio": round(
            counters.edge_replay_actions / counters.total_actions if counters.total_actions else 0,
            4,
        ),
        "power_on_replay_gate_passed": root_gate_passed,
        "action_counts": dict(sorted(counters.action_counts.items())),
        "best_milestone": best_progress.public_dict(),
        "next_milestone": _next_milestone(best_progress),
        "observed_milestones": sorted(reached_milestones),
        "completion_cell_id": completion_cell_id,
        "hall_of_fame_reached": completion_cell_id is not None,
        "current_attempt": None if current is None else dict(current),
        "latest_referee_state": (
            None if latest_referee_state is None else latest_referee_state.public_dict()
        ),
        "run_bytes": run_bytes,
        "max_output_bytes": config.max_output_bytes,
        "disk_monitor": dict(disk_monitor),
        "information_boundary": {
            "action_emitter": emitter_identity["policy_id"],
            "action_emitter_inputs": list(emitter_identity["inputs"]),
            "loop_detector_inputs": ["rendered_rgb"],
            "referee_inputs": ["documented_read_only_ram"],
            "archive_selection_inputs": ["referee_milestones", "frontier_descriptor"],
            "ram_used_by_actor": False,
            "ram_used_by_referee": True,
            "snapshots_visible_to_actor": False,
            "human_demonstrations": [],
            "pretrained_components": list(emitter_identity["pretrained_components"]),
            "frozen_actor_weights": bool(emitter_identity["frozen_weights"]),
            "trainer_routes_exploration": bool(
                emitter_identity["trainer_routes_exploration"]
            ),
        },
        "active_frontier": [
            {
                "cell_id": cell.cell_id,
                "parent_id": cell.parent_id,
                "depth_actions": cell.depth_actions,
                "milestone_id": cell.descriptor.milestone_id,
                "milestone_index": cell.descriptor.milestone_index,
                "map_id": cell.descriptor.map_id,
                "coordinates": {
                    "x_bucket": cell.descriptor.x_bucket,
                    "y_bucket": cell.descriptor.y_bucket,
                },
                "battle_kind": cell.descriptor.battle_kind,
                "selection_count": archive.selection_counts.get(cell.cell_id, 0),
            }
            for cell in active[:32]
        ],
    }


def render_expedition_dashboard(status: Mapping[str, Any]) -> str:
    """Render a compact, self-refreshing local dashboard without private payloads."""

    best = status.get("best_milestone", {})
    if not isinstance(best, Mapping):
        best = {}
    current = status.get("current_attempt")
    current_label = "Waiting for the next suffix"
    if isinstance(current, Mapping):
        current_label = (
            f"{current.get('selection_channel', 'frontier')} from "
            f"{str(current.get('parent_id', 'root'))[:12]} · "
            f"{int(current.get('actions', 0)):,}/{int(current.get('budget', 0)):,} actions"
        )
    frontier = status.get("active_frontier", [])
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(cell.get('milestone_id', 'unknown')))}</td>"
        f"<td>{html.escape(str(cell.get('map_id', '—')))}</td>"
        f"<td>{int(cell.get('depth_actions', 0)):,}</td>"
        f"<td>{int(cell.get('selection_count', 0)):,}</td>"
        "</tr>"
        for cell in frontier[:12]
        if isinstance(cell, Mapping)
    )
    if not rows:
        rows = '<tr><td colspan="4">Waiting for the power-on root.</td></tr>'
    updated = html.escape(str(status.get("updated_at", "starting")))
    state = html.escape(str(status.get("state", "starting")).upper())
    reason = html.escape(str(status.get("stop_reason") or "running"))
    boundary = status.get("information_boundary", {})
    hybrid = bool(
        isinstance(boundary, Mapping)
        and boundary.get("action_emitter") == VisualApprenticeHybridEmitter.policy_id
    )
    eyebrow = (
        "FROZEN VISUAL APPRENTICE + SEEDED EXPLORATION · FULL-GAME DEVELOPMENT"
        if hybrid
        else "RANDOM DISCOVERY BASELINE · NOT A LEARNED MODEL"
    )
    headline = (
        "Leaving home was<br/>only the beginning."
        if hybrid
        else "Evolution is allowed<br/>to remember."
    )
    lede = (
        "A frozen pixel policy supplies learned opening behavior. After the house frontier, "
        "seeded exploratory actions increase while Archive v2 preserves and replay-verifies "
        "later milestones toward the Hall of Fame."
        if hybrid
        else "A seeded-random actor emits buttons without RAM or milestone access. A sealed "
        "referee may recognize progress and choose restorable stepping stones. Named promotions "
        "must replay their complete input lineage from power-on."
    )
    contract = (
        "The actor receives pixels, previous action, recurrent state, and a seeded exploration "
        "coin. A trainer uses the verified parent milestone only to raise exploration after "
        "left_home. Neural weights are frozen; the archive and scheduler accumulate progress."
        if hybrid
        else "Buttons come only from a seeded PRNG. The loop detector sees rendered pixels. RAM "
        "is read only by the referee, and checkpoints never enter the actor. This is "
        "checkpoint-assisted discovery, not a continuous learned-policy completion."
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta http-equiv="refresh" content="5" />
<title>Pokémon Red — Checkpoint Expedition</title>
<style>
:root{{color-scheme:dark;--bg:#070a12;--panel:#111827;--line:#29344a;--ink:#f5f7ff;
--muted:#9aa8c2;--green:#78efa8;--gold:#ffd166}}*{{box-sizing:border-box}}body{{margin:0;
font:15px/1.45 system-ui,sans-serif;color:var(--ink);background:radial-gradient(circle at 20% 0,
#183451,var(--bg) 45%)}}main{{width:min(1100px,calc(100% - 28px));margin:auto;padding:34px 0 60px}}
.eyebrow{{color:var(--green);font-size:.72rem;font-weight:900;letter-spacing:.15em}}h1{{font-size:
clamp(2.2rem,6vw,5rem);line-height:.95;letter-spacing:-.055em;margin:.5rem 0}}.lede{{color:
var(--muted);max-width:800px}}.grid{{display:grid;grid-template-columns:1.1fr .9fr;gap:14px;
margin-top:20px}}.card{{background:linear-gradient(180deg,#121b2c,var(--panel));border:1px solid
var(--line);border-radius:18px;padding:16px}}img{{display:block;width:100%;image-rendering:pixelated;
background:#020409;border-radius:12px;border:1px solid var(--line)}}.stats{{display:grid;
grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}}.stats div{{background:#090e18;
border-radius:9px;padding:9px}}span{{display:block;color:var(--muted);font-size:.68rem}}strong{{font-size:
1.05rem}}.milestone{{color:var(--gold);font-size:1.6rem;margin:.2rem 0 1rem}}.attempt{{padding:
10px;border-left:3px solid var(--green);background:#09121a}}table{{width:100%;
border-collapse:collapse;font-size:.8rem;margin-top:12px}}th,td{{padding:7px;
border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--muted)}}.contract{{margin-top:14px;color:var(--muted);padding:13px;border:1px solid
var(--line);border-radius:12px}}footer{{color:var(--muted);font-size:.7rem;margin-top:15px}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}}.stats{{grid-template-columns:1fr 1fr}}}}
</style></head><body><main>
<div class="eyebrow">{eyebrow} · {state}</div>
<h1>{headline}</h1>
<p class="lede">{lede}</p>
<section class="grid"><article class="card">
<img src="latest.png?v={updated}" alt="Latest rendered Game Boy frame" />
<div class="stats"><div><span>Exploration actions</span>
<strong>{int(status.get("total_actions", 0)):,}</strong></div>
<div><span>Attempts</span><strong>{int(status.get("attempts", 0)):,}</strong></div>
	<div><span>Active / stored cells</span>
	<strong>{int(status.get("archive_cells", 0)):,} /
	{int(status.get("stored_evidence_cells", 0)):,}</strong></div>
	<div><span>Preflight drops</span>
	<strong>{int(status.get("ordinary_preflight_rejections", 0)):,}</strong></div>
	<div><span>Loop stops</span><strong>{int(status.get("loop_stops", 0)):,}</strong></div>
<div><span>Edge replay passes</span><strong>{int(status.get("edge_replay_passes", 0)):,} /
{int(status.get("edge_replay_attempts", 0)):,}</strong></div>
<div><span>Promotion replay passes</span>
<strong>{int(status.get("promotion_power_on_replay_passes", 0)):,} /
{int(status.get("promotion_power_on_replay_attempts", 0)):,}</strong></div>
<div><span>Stop reason</span><strong>{reason}</strong></div></div></article>
<article class="card"><span>Best verified frontier</span>
<div class="milestone">{html.escape(str(best.get("label", "Clean power-on")))}</div>
<div class="attempt">{html.escape(current_label)}</div>
<table><thead><tr><th>Milestone</th><th>Map</th><th>Depth</th><th>Selections</th></tr></thead>
<tbody>{rows}</tbody></table></article></section>
<div class="contract"><strong>Information boundary:</strong> {contract}</div>
<footer>Updated {updated} · private ROM bytes, snapshots, and action segments are not linked
here.</footer>
</main></body></html>"""


class _SignalStop:
    def __init__(self) -> None:
        self.reason: str | None = None
        self._previous: dict[signal.Signals, Any] = {}

    def __enter__(self) -> _SignalStop:
        for event in (signal.SIGINT, signal.SIGTERM):
            self._previous[event] = signal.getsignal(event)
            signal.signal(event, self._handle)
        return self

    def __exit__(self, *_: object) -> None:
        for event, handler in self._previous.items():
            signal.signal(event, handler)

    def _handle(self, event: int, _frame: FrameType | None) -> None:
        self.reason = "sigint" if event == signal.SIGINT else "sigterm"


@dataclass(frozen=True, slots=True)
class _StoreRecoveryPlan:
    checkpoint_event_bytes: bytes
    extra_event_bytes: bytes
    checkpoint_cell_ids: tuple[str, ...]
    extra_cells: tuple[tuple[str, bytes], ...]
    observed_event_sequence: int
    observed_event_head_sha256: str
    observed_cell_ids: tuple[str, ...]
    observed_index_cell_ids: tuple[str, ...]


def _parse_event_chain(payload: bytes) -> tuple[int, str, tuple[dict[str, Any], ...]]:
    """Validate a complete event byte prefix without invoking store recovery behavior."""

    if payload and not payload.endswith(b"\n"):
        raise ValueError("Expedition store event log has an incomplete tail")
    sequence = 0
    event_head = "0" * 64
    events: list[dict[str, Any]] = []
    for raw_line in payload.splitlines():
        try:
            value = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Expedition store event JSON is invalid") from error
        if not isinstance(value, dict):
            raise ValueError("Expedition store event must be an object")
        event = dict(value)
        event_hash = str(event.pop("event_sha256", ""))
        if int(event.get("event_sequence", -1)) != sequence + 1:
            raise ValueError("Expedition store event sequence is invalid")
        if event.get("previous_event_sha256") != event_head:
            raise ValueError("Expedition store event prefix is not hash chained")
        expected_hash = hashlib.sha256(
            _canonical_json(event).encode("utf-8")
        ).hexdigest()
        if event_hash != expected_hash:
            raise ValueError("Expedition store event hash is invalid")
        sequence += 1
        event_head = event_hash
        events.append(value)
    return sequence, event_head, tuple(events)


def _complete_event_prefix(payload: bytes) -> tuple[bytes, bytes]:
    """Separate durable newline-terminated events from a possibly torn final append."""

    if not payload or payload.endswith(b"\n"):
        return payload, b""
    boundary = payload.rfind(b"\n")
    if boundary < 0:
        return b"", payload
    return payload[: boundary + 1], payload[boundary + 1 :]


def _valid_cell_id(cell_id: str) -> bool:
    return len(cell_id) == 24 and all(
        character in "0123456789abcdef" for character in cell_id
    )


def _checkpoint_cell_ids(checkpoint: Mapping[str, Any]) -> tuple[str, ...]:
    value = checkpoint.get("store_cell_ids")
    if not isinstance(value, list):
        raise ValueError("Expedition checkpoint store cell IDs are missing")
    cell_ids = tuple(str(cell_id) for cell_id in value)
    if len(cell_ids) != len(set(cell_ids)) or any(
        not _valid_cell_id(cell_id) for cell_id in cell_ids
    ):
        raise ValueError("Expedition checkpoint store cell IDs are invalid")
    return cell_ids


def _inspect_store_for_resume(
    store_path: Path,
    checkpoint: Mapping[str, Any],
) -> tuple[ExpeditionStore, _StoreRecoveryPlan | None]:
    """Validate an exact or partially appended store without mutating crash evidence."""

    checkpoint_sequence = checkpoint.get("store_event_sequence")
    checkpoint_offset = checkpoint.get("store_event_byte_offset")
    checkpoint_head = str(checkpoint.get("store_event_head_sha256", ""))
    if (
        not isinstance(checkpoint_sequence, int)
        or isinstance(checkpoint_sequence, bool)
        or checkpoint_sequence < 0
        or not isinstance(checkpoint_offset, int)
        or isinstance(checkpoint_offset, bool)
        or checkpoint_offset < 0
        or len(checkpoint_head) != 64
        or any(character not in "0123456789abcdef" for character in checkpoint_head)
    ):
        raise ValueError("Expedition checkpoint store event identity is invalid")
    checkpoint_cells = _checkpoint_cell_ids(checkpoint)

    events_path = store_path / "events.jsonl"
    event_bytes = events_path.read_bytes()
    if checkpoint_offset > len(event_bytes):
        raise ValueError("Expedition store is behind its runner checkpoint")
    checkpoint_event_bytes = event_bytes[:checkpoint_offset]
    checkpoint_identity = _parse_event_chain(checkpoint_event_bytes)
    if checkpoint_identity[:2] != (checkpoint_sequence, checkpoint_head):
        raise ValueError("Expedition store checkpoint prefix does not match")
    complete_event_bytes, _torn_event_bytes = _complete_event_prefix(event_bytes)
    if len(complete_event_bytes) < checkpoint_offset:
        raise ValueError("Expedition store event log is torn inside its checkpoint prefix")
    current_sequence, current_head, events = _parse_event_chain(complete_event_bytes)

    index = json.loads((store_path / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or int(index.get("schema_version", -1)) != 1:
        raise ValueError("Expedition store index is invalid")
    indexed = index.get("cell_ids")
    if not isinstance(indexed, list):
        raise ValueError("Expedition store index cell IDs are invalid")
    indexed_cells = tuple(str(cell_id) for cell_id in indexed)
    if len(indexed_cells) != len(set(indexed_cells)) or any(
        not _valid_cell_id(cell_id) for cell_id in indexed_cells
    ):
        raise ValueError("Expedition store index contains duplicate cell IDs")
    cell_files = {item.stem: item for item in (store_path / "cells").glob("*.json")}
    if any(not _valid_cell_id(cell_id) for cell_id in cell_files):
        raise ValueError("Expedition store contains malformed cell metadata filenames")
    if indexed_cells[: len(checkpoint_cells)] != checkpoint_cells:
        raise ValueError("Expedition store ordered cell prefix does not match")
    if any(cell_id not in cell_files for cell_id in indexed_cells):
        raise ValueError("Expedition store index references missing cell metadata")
    if any(cell_id not in cell_files for cell_id in checkpoint_cells):
        raise ValueError("Expedition store is missing checkpoint cell metadata")

    exact = (
        current_sequence == checkpoint_sequence
        and current_head == checkpoint_head
        and len(event_bytes) == checkpoint_offset
        and indexed_cells == checkpoint_cells
        and set(cell_files) == set(checkpoint_cells)
    )
    if exact:
        store = ExpeditionStore.open(store_path)
        if (
            store.event_sequence != current_sequence
            or store.event_head_sha256 != current_head
            or tuple(store.cells) != indexed_cells
        ):
            raise ValueError("Expedition store changed during resume validation")
        return store, None

    tail_events = events[checkpoint_sequence:]
    added_cell_ids = [
        str(event.get("cell_id"))
        for event in tail_events
        if event.get("kind") == "frontier_cell_added"
    ]
    extra_index_cells = indexed_cells[len(checkpoint_cells) :]
    orphan_cells = tuple(sorted(set(cell_files) - set(indexed_cells)))
    extra_cell_ids = (*extra_index_cells, *orphan_cells)
    if len(extra_cell_ids) != len(set(extra_cell_ids)):
        raise ValueError("Expedition store recovery cell identities overlap")
    if any(cell_id not in cell_files for cell_id in added_cell_ids):
        raise ValueError("Expedition event tail references missing cell metadata")
    if any(cell_id not in added_cell_ids for cell_id in extra_index_cells):
        raise ValueError("Expedition index contains an unexplained post-checkpoint cell")
    if any(cell_id in checkpoint_cells for cell_id in added_cell_ids):
        raise ValueError("Expedition event tail re-adds a checkpoint cell")
    extra_cells = tuple(
        (cell_id, cell_files[cell_id].read_bytes()) for cell_id in extra_cell_ids
    )
    checkpoint_store = ExpeditionStore.open_checkpoint_view(
        store_path,
        event_payload=checkpoint_event_bytes,
        cell_ids=checkpoint_cells,
    )
    return checkpoint_store, _StoreRecoveryPlan(
        checkpoint_event_bytes=checkpoint_event_bytes,
        extra_event_bytes=event_bytes[checkpoint_offset:],
        checkpoint_cell_ids=checkpoint_cells,
        extra_cells=extra_cells,
        observed_event_sequence=current_sequence,
        observed_event_head_sha256=current_head,
        observed_cell_ids=(*checkpoint_cells, *extra_cell_ids),
        observed_index_cell_ids=indexed_cells,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_binary(path: Path, value: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _durable_binary(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())


_RECOVERY_IDENTITY_KEYS = (
    "checkpoint_event_sequence",
    "checkpoint_event_head_sha256",
    "checkpoint_event_byte_offset",
    "checkpoint_event_sha256",
    "checkpoint_cell_ids",
    "observed_event_sequence",
    "observed_event_head_sha256",
    "observed_cell_ids",
    "observed_index_cell_ids",
    "extra_event_bytes",
    "extra_event_sha256",
    "extra_cell_sha256",
)


def _checkpoint_identity_sha256(checkpoint: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(checkpoint).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class _ValidatedRecoveryBundle:
    recovery_id: str
    checkpoint_event_bytes: bytes
    extra_event_bytes: bytes
    checkpoint_cell_ids: tuple[str, ...]
    extra_cell_ids: tuple[str, ...]
    expected_sequence: int
    expected_head: str
    observed_sequence: int

    def disclosure(self, store_path: Path, recovery_directory: Path) -> dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "recovery_directory": str(recovery_directory.relative_to(store_path)),
            "recovered_event_bytes": len(self.extra_event_bytes),
            "recovered_event_count": self.observed_sequence - self.expected_sequence,
            "recovered_cell_ids": list(self.extra_cell_ids),
        }


@dataclass(frozen=True, slots=True)
class _PendingStoreRecovery:
    recovery_directory: Path
    pending_path: Path


def _validate_recovery_bundle(recovery_directory: Path) -> _ValidatedRecoveryBundle:
    """Validate every private recovery artifact without changing the live store."""

    manifest = json.loads((recovery_directory / "manifest.json").read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or int(manifest.get("schema_version", -1)) != 1
        or manifest.get("kind") != "runner_post_checkpoint_recovery"
    ):
        raise ValueError("Expedition recovery manifest is invalid")
    try:
        identity = {key: manifest[key] for key in _RECOVERY_IDENTITY_KEYS}
    except KeyError as error:
        raise ValueError("Expedition recovery manifest is incomplete") from error
    recovery_id = hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
    if manifest.get("recovery_id") != recovery_id:
        raise ValueError("Expedition recovery manifest identity is invalid")

    checkpoint_event_bytes = (recovery_directory / "events.checkpoint.jsonl").read_bytes()
    extra_event_bytes = (recovery_directory / "events.tail.jsonl").read_bytes()
    if (
        hashlib.sha256(checkpoint_event_bytes).hexdigest()
        != identity["checkpoint_event_sha256"]
        or hashlib.sha256(extra_event_bytes).hexdigest() != identity["extra_event_sha256"]
        or len(checkpoint_event_bytes) != int(identity["checkpoint_event_byte_offset"])
        or len(extra_event_bytes) != int(identity["extra_event_bytes"])
    ):
        raise ValueError("Expedition recovery event bytes failed integrity checks")
    expected_sequence, expected_head, _events = _parse_event_chain(checkpoint_event_bytes)
    if (
        expected_sequence != int(identity["checkpoint_event_sequence"])
        or expected_head != identity["checkpoint_event_head_sha256"]
    ):
        raise ValueError("Expedition recovery checkpoint event identity is invalid")

    checkpoint_cells = tuple(str(cell_id) for cell_id in identity["checkpoint_cell_ids"])
    observed_cells = tuple(str(cell_id) for cell_id in identity["observed_cell_ids"])
    observed_index_cells = tuple(
        str(cell_id) for cell_id in identity["observed_index_cell_ids"]
    )
    if (
        len(checkpoint_cells) != len(set(checkpoint_cells))
        or len(observed_cells) != len(set(observed_cells))
        or len(observed_index_cells) != len(set(observed_index_cells))
        or any(not _valid_cell_id(cell_id) for cell_id in observed_cells)
        or observed_cells[: len(checkpoint_cells)] != checkpoint_cells
        or observed_index_cells[: len(checkpoint_cells)] != checkpoint_cells
        or not set(observed_index_cells) <= set(observed_cells)
    ):
        raise ValueError("Expedition recovery cell identity is invalid")
    observed_index = json.loads(
        (recovery_directory / "index.observed.json").read_text(encoding="utf-8")
    )
    if observed_index != {"schema_version": 1, "cell_ids": list(observed_index_cells)}:
        raise ValueError("Expedition recovery observed index is invalid")
    extra_cell_ids = observed_cells[len(checkpoint_cells) :]
    extra_hashes = identity["extra_cell_sha256"]
    if not isinstance(extra_hashes, dict) or set(extra_hashes) != set(extra_cell_ids):
        raise ValueError("Expedition recovery cell identity is invalid")
    for cell_id in extra_cell_ids:
        payload = (recovery_directory / "cells" / f"{cell_id}.json").read_bytes()
        if hashlib.sha256(payload).hexdigest() != extra_hashes[cell_id]:
            raise ValueError("Expedition recovery cell metadata failed its integrity check")
    observed_sequence = int(identity["observed_event_sequence"])
    observed_head = str(identity["observed_event_head_sha256"])
    observed_complete_bytes, _observed_torn_tail = _complete_event_prefix(
        checkpoint_event_bytes + extra_event_bytes
    )
    recomputed_observed_sequence, recomputed_observed_head, _observed_events = (
        _parse_event_chain(observed_complete_bytes)
    )
    if (
        observed_sequence < expected_sequence
        or len(observed_head) != 64
        or any(character not in "0123456789abcdef" for character in observed_head)
        or observed_sequence != recomputed_observed_sequence
        or observed_head != recomputed_observed_head
    ):
        raise ValueError("Expedition recovery observed event identity is invalid")
    return _ValidatedRecoveryBundle(
        recovery_id=recovery_id,
        checkpoint_event_bytes=checkpoint_event_bytes,
        extra_event_bytes=extra_event_bytes,
        checkpoint_cell_ids=checkpoint_cells,
        extra_cell_ids=extra_cell_ids,
        expected_sequence=expected_sequence,
        expected_head=expected_head,
        observed_sequence=observed_sequence,
    )


def _apply_recovery_bundle(
    store_path: Path,
    recovery_directory: Path,
    pending_path: Path,
) -> tuple[ExpeditionStore, dict[str, Any]]:
    """Idempotently finish a validated recovery transaction at any mutation boundary."""

    bundle = _validate_recovery_bundle(recovery_directory)

    _atomic_binary(store_path / "events.jsonl", bundle.checkpoint_event_bytes)
    _atomic_binary(
        store_path / "index.json",
        (json.dumps(
            {"schema_version": 1, "cell_ids": bundle.checkpoint_cell_ids},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n").encode("utf-8"),
    )
    for cell_id in bundle.extra_cell_ids:
        (store_path / "cells" / f"{cell_id}.json").unlink(missing_ok=True)
    _fsync_directory(store_path / "cells")

    restored = ExpeditionStore.open(store_path)
    if (
        restored.event_sequence != bundle.expected_sequence
        or restored.event_head_sha256 != bundle.expected_head
        or tuple(restored.cells) != bundle.checkpoint_cell_ids
    ):
        raise RuntimeError("Expedition store did not restore to the runner checkpoint")
    return restored, bundle.disclosure(store_path, recovery_directory)


def _inspect_pending_store_recovery(
    store_path: Path,
    checkpoint: Mapping[str, Any],
) -> tuple[ExpeditionStore, _PendingStoreRecovery] | None:
    recovery_root = store_path / "recovery"
    pending_path = recovery_root / "PENDING.json"
    if not pending_path.is_file():
        return None
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    if (
        not isinstance(pending, dict)
        or pending.get("checkpoint_sha256") != _checkpoint_identity_sha256(checkpoint)
    ):
        raise ValueError("Expedition pending recovery belongs to a different checkpoint")
    directory_name = str(pending.get("recovery_directory", ""))
    if not directory_name.startswith("runner-crash-") or "/" in directory_name:
        raise ValueError("Expedition pending recovery path is invalid")
    recovery_directory = recovery_root / directory_name
    if pending.get("recovery_id") != json.loads(
        (recovery_directory / "manifest.json").read_text(encoding="utf-8")
    ).get("recovery_id"):
        raise ValueError("Expedition pending recovery identity is inconsistent")
    bundle = _validate_recovery_bundle(recovery_directory)
    if (
        bundle.recovery_id != pending.get("recovery_id")
        or bundle.expected_sequence != checkpoint.get("store_event_sequence")
        or bundle.expected_head != checkpoint.get("store_event_head_sha256")
        or len(bundle.checkpoint_event_bytes) != checkpoint.get("store_event_byte_offset")
        or bundle.checkpoint_cell_ids != _checkpoint_cell_ids(checkpoint)
    ):
        raise ValueError("Expedition pending recovery does not match its checkpoint")
    store = ExpeditionStore.open_checkpoint_view(
        store_path,
        event_payload=bundle.checkpoint_event_bytes,
        cell_ids=bundle.checkpoint_cell_ids,
    )
    return store, _PendingStoreRecovery(recovery_directory, pending_path)


def _recover_store_to_checkpoint(
    store_path: Path,
    plan: _StoreRecoveryPlan,
    checkpoint: Mapping[str, Any],
) -> tuple[ExpeditionStore, dict[str, Any]]:
    """Preserve a coherent crash window, then restore the checkpoint's exact store view."""

    expected_sequence, expected_head, _events = _parse_event_chain(
        plan.checkpoint_event_bytes
    )
    extra_cell_hashes = {
        cell_id: hashlib.sha256(payload).hexdigest() for cell_id, payload in plan.extra_cells
    }
    identity = {
        "checkpoint_event_sequence": expected_sequence,
        "checkpoint_event_head_sha256": expected_head,
        "checkpoint_event_byte_offset": len(plan.checkpoint_event_bytes),
        "checkpoint_event_sha256": hashlib.sha256(plan.checkpoint_event_bytes).hexdigest(),
        "checkpoint_cell_ids": list(plan.checkpoint_cell_ids),
        "observed_event_sequence": plan.observed_event_sequence,
        "observed_event_head_sha256": plan.observed_event_head_sha256,
        "observed_cell_ids": list(plan.observed_cell_ids),
        "observed_index_cell_ids": list(plan.observed_index_cell_ids),
        "extra_event_bytes": len(plan.extra_event_bytes),
        "extra_event_sha256": hashlib.sha256(plan.extra_event_bytes).hexdigest(),
        "extra_cell_sha256": extra_cell_hashes,
    }
    recovery_id = hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
    recovery_root = store_path / "recovery"
    recovery_root.mkdir(exist_ok=True)
    recovery_directory = recovery_root / f"runner-crash-{recovery_id[:24]}"
    manifest = {
        "schema_version": 1,
        "kind": "runner_post_checkpoint_recovery",
        "recovery_id": recovery_id,
        **identity,
        "shared_snapshot_and_segment_payloads_retained": True,
    }
    if not recovery_directory.exists():
        temporary = recovery_root / f".{recovery_directory.name}.{os.urandom(8).hex()}.tmp"
        temporary.mkdir()
        _durable_binary(temporary / "events.checkpoint.jsonl", plan.checkpoint_event_bytes)
        _durable_binary(temporary / "events.tail.jsonl", plan.extra_event_bytes)
        _durable_binary(
            temporary / "index.observed.json",
            (json.dumps(
                {"schema_version": 1, "cell_ids": plan.observed_index_cell_ids},
                sort_keys=True,
            )
            + "\n").encode("utf-8"),
        )
        for cell_id, payload in plan.extra_cells:
            _durable_binary(temporary / "cells" / f"{cell_id}.json", payload)
        _durable_binary(
            temporary / "manifest.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        _fsync_directory(temporary)
        os.replace(temporary, recovery_directory)
        _fsync_directory(recovery_root)
    else:
        existing_manifest = json.loads(
            (recovery_directory / "manifest.json").read_text(encoding="utf-8")
        )
        if existing_manifest != manifest:
            raise ValueError("Expedition recovery directory identity does not match")

    pending_path = recovery_root / "PENDING.json"
    pending = {
        "schema_version": 1,
        "checkpoint_sha256": _checkpoint_identity_sha256(checkpoint),
        "recovery_id": recovery_id,
        "recovery_directory": recovery_directory.name,
    }
    _atomic_binary(
        pending_path,
        (json.dumps(pending, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return _apply_recovery_bundle(store_path, recovery_directory, pending_path)


def _validated_trace_offset(path: Path, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("Expedition checkpoint trace offset is invalid")
    size = path.stat().st_size
    if value > size:
        raise ValueError("Expedition trace checkpoint is outside the trace")
    position = 0
    with path.open("rb") as trace:
        while position < value:
            line = trace.readline()
            if not line or not line.endswith(b"\n"):
                raise ValueError("Expedition checkpoint trace prefix is incomplete")
            position += len(line)
            if position > value:
                raise ValueError("Expedition checkpoint trace offset splits a record")
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("Expedition checkpoint trace prefix is invalid") from error
            if not isinstance(event, dict):
                raise ValueError("Expedition checkpoint trace record is invalid")
    if position != value:
        raise ValueError("Expedition checkpoint trace offset is invalid")
    return value


def _checkpoint_payload(
    *,
    config: ExpeditionRunConfig,
    rom: RomFingerprint,
    source: Mapping[str, Any],
    implementation_sha256: str,
    counters: ExpeditionCounters,
    rng: random.Random,
    archive: FrontierArchive,
    attempts_by_parent: Mapping[str, int],
    best_progress: MilestoneProgress,
    reached_milestones: set[str],
    completion_cell_id: str | None,
    started_at: str,
    trace_offset: int,
    latest_frame_pixels: np.ndarray,
) -> dict[str, Any]:
    if latest_frame_pixels.shape != _CHECKPOINT_FRAME_SHAPE:
        raise ValueError("Expedition checkpoint frame has an invalid shape")
    if latest_frame_pixels.dtype != np.uint8:
        raise ValueError("Expedition checkpoint frame must use uint8 RGB values")
    frame_bytes = latest_frame_pixels.tobytes(order="C")
    frame_sha256 = hashlib.sha256(frame_bytes).hexdigest()
    events_path = archive.store.path / "events.jsonl"
    return {
        "schema_version": EXPEDITION_RUNNER_CHECKPOINT_SCHEMA,
        "protocol_version": EXPEDITION_RUNNER_PROTOCOL_VERSION,
        "store_protocol_version": EXPEDITION_PROTOCOL_VERSION,
        "config": config.public_dict(),
        "rom_sha256": rom.sha256,
        "source": dict(source),
        "implementation_sha256": implementation_sha256,
        "store_event_sequence": archive.store.event_sequence,
        "store_event_head_sha256": archive.store.event_head_sha256,
        "store_event_byte_offset": events_path.stat().st_size,
        "store_cell_ids": list(archive.store.cells),
        "latest_frame_sha256": frame_sha256,
        "latest_frame": {
            "encoding": _CHECKPOINT_FRAME_ENCODING,
            "shape": list(_CHECKPOINT_FRAME_SHAPE),
            "payload_base64": base64.b64encode(frame_bytes).decode("ascii"),
        },
        "counters": counters.checkpoint_dict(),
        "rng_state": rng.getstate(),
        "archive": {
            **archive.checkpoint_dict(),
            "selection_counts": {
                cell.cell_id: archive.selection_counts.get(cell.cell_id, 0)
                for cell in archive.active_cells
            },
        },
        "attempts_by_parent": dict(sorted(attempts_by_parent.items())),
        "best_progress": best_progress.public_dict(),
        "reached_milestones": sorted(reached_milestones),
        "completion_cell_id": completion_cell_id,
        "started_at": started_at,
        "trace_offset": trace_offset,
    }


def _checkpoint_frame(checkpoint: Mapping[str, Any]) -> np.ndarray:
    """Decode the immutable frame carried by one atomic runner checkpoint."""

    value = checkpoint.get("latest_frame")
    if not isinstance(value, Mapping):
        raise ValueError("Expedition checkpoint frame is missing")
    if (
        value.get("encoding") != _CHECKPOINT_FRAME_ENCODING
        or value.get("shape") != list(_CHECKPOINT_FRAME_SHAPE)
    ):
        raise ValueError("Expedition checkpoint frame schema is invalid")
    payload = value.get("payload_base64")
    if not isinstance(payload, str):
        raise ValueError("Expedition checkpoint frame payload is invalid")
    try:
        frame_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Expedition checkpoint frame payload is invalid") from error
    if len(frame_bytes) != int(np.prod(_CHECKPOINT_FRAME_SHAPE)):
        raise ValueError("Expedition checkpoint frame has an invalid length")
    actual_sha256 = hashlib.sha256(frame_bytes).hexdigest()
    if checkpoint.get("latest_frame_sha256") != actual_sha256:
        raise ValueError("Expedition checkpoint frame does not match its hash")
    return np.frombuffer(frame_bytes, dtype=np.uint8).reshape(_CHECKPOINT_FRAME_SHAPE).copy()


def _write_live_artifacts(
    output: Path,
    status: dict[str, Any],
    pixels: np.ndarray,
) -> None:
    _save_png(pixels, output / "latest.png")
    _atomic_json(output / "status.json", status)
    _atomic_text(output / "index.html", render_expedition_dashboard(status))


def run_expedition(
    rom_path: Path,
    rom: RomFingerprint,
    *,
    config: ExpeditionRunConfig,
    run_directory: Path,
    resume: bool = False,
    apprentice_model_directory: Path | None = None,
) -> ExpeditionRunResult:
    """Run a bounded checkpoint expedition under one lease for every persistent write."""

    output = run_directory.expanduser().resolve()
    _validate_output_path(output)
    if resume:
        if not output.is_dir():
            raise ValueError("Expedition resume requires an existing run directory")
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "milestones").mkdir()

    writer_lock = _acquire_single_writer(output)
    try:
        return _run_expedition_locked(
            rom_path,
            rom,
            config=config,
            run_directory=output,
            resume=resume,
            writer_lock=writer_lock,
            apprentice_model_directory=apprentice_model_directory,
        )
    finally:
        _release_single_writer(writer_lock)


def _run_expedition_locked(
    rom_path: Path,
    rom: RomFingerprint,
    *,
    config: ExpeditionRunConfig,
    run_directory: Path,
    resume: bool,
    writer_lock: Path,
    apprentice_model_directory: Path | None,
) -> ExpeditionRunResult:
    """Implementation entered only after the run directory's writer lease is held."""

    output = run_directory.expanduser().resolve()
    if writer_lock != output / "RUNNING.lock" or not writer_lock.is_file():
        raise RuntimeError("Expedition writer lease is not held")
    store_path = output / "frontier"
    trace_path = output / "trace.jsonl"
    checkpoint_path = output / "checkpoint.json.gz"
    stop_marker = output / "STOP"
    source = detect_source_provenance().public_dict()
    implementation = _implementation_sha256()
    run_config_sha256 = hashlib.sha256(
        _canonical_json(config.public_dict()).encode("utf-8")
    ).hexdigest()
    rng = random.Random(config.seed)
    if config.emitter_kind == APPRENTICE_HYBRID_EMITTER:
        if apprentice_model_directory is None:
            raise ValueError("Hybrid expedition requires --apprentice-model")
        emitter: SeededRandomSequenceEmitter | VisualApprenticeHybridEmitter = (
            VisualApprenticeHybridEmitter(
                rng,
                apprentice_model_directory,
                expected_model_sha256=config.apprentice_model_sha256,
            )
        )
    else:
        if apprentice_model_directory is not None:
            raise ValueError("Random expedition cannot load an apprentice model")
        emitter = SeededRandomSequenceEmitter(rng)
    emitter_identity = emitter.public_identity()
    store_metadata = {
        "runner_protocol_version": EXPEDITION_RUNNER_PROTOCOL_VERSION,
        "verification_protocol": "edge-and-promotion-v2",
        "ordinary_cell_gate": "one_exact_parent_to_child_edge_replay",
        "named_promotion_gate": (f"{config.promotion_replay_passes}_exact_fresh_power_on_replays"),
        "actor": emitter.policy_id,
        "actor_identity": emitter_identity,
        "actor_receives_ram": False,
        "referee_receives_ram": True,
        "run_config_sha256": run_config_sha256,
        "seed": config.seed,
        "implementation_sha256": implementation,
        "source": source,
    }
    checkpoint: dict[str, Any] | None = None
    resume_pixels: np.ndarray | None = None
    counters = ExpeditionCounters()
    attempts_by_parent: dict[str, int] = {}
    reached_milestones: set[str] = set()
    best_progress = POWER_ON_PROGRESS
    completion_cell_id: str | None = None
    started_at = datetime.now(UTC).isoformat()
    base_elapsed = 0.0
    recovery_disclosure: dict[str, Any] | None = None
    pending_recovery_plan: _PendingStoreRecovery | None = None

    if resume:
        _checkpoint_used, checkpoint = _read_checkpoint(checkpoint_path)
        if checkpoint.get("config") != config.public_dict():
            raise ValueError("Expedition resume configuration does not match")
        if checkpoint.get("rom_sha256") != rom.sha256:
            raise ValueError("Expedition checkpoint belongs to a different ROM")
        if checkpoint.get("source") != source:
            raise ValueError("Expedition checkpoint source provenance does not match")
        if checkpoint.get("implementation_sha256") != implementation:
            raise ValueError("Expedition implementation changed since the checkpoint")
        if checkpoint.get("store_protocol_version") != EXPEDITION_PROTOCOL_VERSION:
            raise ValueError("Expedition checkpoint store protocol does not match")

        previous_status = json.loads((output / "status.json").read_text(encoding="utf-8"))
        if not isinstance(previous_status, dict):
            raise ValueError("Expedition status is invalid")
        if previous_status.get("stop_reason") in {
            "action_limit",
            "duration_limit",
            "hall_of_fame_verified",
        }:
            raise ValueError("This expedition already reached a terminal budget or completion")
        trace_offset = _validated_trace_offset(trace_path, checkpoint.get("trace_offset"))

        resume_pixels = _checkpoint_frame(checkpoint)
        checkpoint_cell_ids = _checkpoint_cell_ids(checkpoint)

        try:
            counters = ExpeditionCounters.from_checkpoint_dict(checkpoint["counters"])
            rng.setstate(_json_tuple(checkpoint["rng_state"]))
            progress_value = checkpoint["best_progress"]
            if not isinstance(progress_value, Mapping):
                raise ValueError("Expedition checkpoint best progress is invalid")
            best_progress = MilestoneProgress(
                str(progress_value["key"]),
                int(progress_value["index"]),
                str(progress_value["label"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Expedition checkpoint state is invalid") from error
        base_elapsed = counters.elapsed_seconds
        if not np.isfinite(base_elapsed) or base_elapsed < 0:
            raise ValueError("Expedition checkpoint elapsed time is invalid")

        attempt_values = checkpoint.get("attempts_by_parent")
        if not isinstance(attempt_values, Mapping):
            raise ValueError("Expedition checkpoint attempt counters are invalid")
        attempts_by_parent = {}
        for cell_id, count in attempt_values.items():
            if (
                not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
                or str(cell_id) not in checkpoint_cell_ids
            ):
                raise ValueError("Expedition checkpoint attempt counters are invalid")
            attempts_by_parent[str(cell_id)] = count
        if sum(attempts_by_parent.values()) != counters.attempts:
            raise ValueError("Expedition checkpoint attempt totals are inconsistent")

        reached_value = checkpoint.get("reached_milestones")
        if not isinstance(reached_value, list):
            raise ValueError("Expedition checkpoint reached milestones are invalid")
        reached_items = [str(key) for key in reached_value]
        milestone_keys = {milestone.key for milestone in MILESTONES}
        if (
            len(reached_items) != len(set(reached_items))
            or not set(reached_items) <= milestone_keys
        ):
            raise ValueError("Expedition checkpoint reached milestones are invalid")
        reached_milestones = set(reached_items)

        raw_completion = checkpoint.get("completion_cell_id")
        completion_cell_id = None if raw_completion is None else str(raw_completion)
        if completion_cell_id is not None and completion_cell_id not in checkpoint_cell_ids:
            raise ValueError("Expedition checkpoint completion cell is invalid")
        started_at = str(checkpoint.get("started_at", ""))
        try:
            parsed_started_at = datetime.fromisoformat(started_at)
        except ValueError as error:
            raise ValueError("Expedition checkpoint start time is invalid") from error
        if parsed_started_at.tzinfo is None:
            raise ValueError("Expedition checkpoint start time lacks a timezone")

        if (
            sum(counters.action_counts.values()) != counters.total_actions
            or counters.archive_restores != counters.attempts
            or counters.cells_created != len(checkpoint_cell_ids)
            or counters.cells_admitted + counters.cells_rejected != counters.cells_created
            or counters.replay_attempts
            != 1
            + counters.edge_replay_attempts
            + counters.promotion_power_on_replay_attempts
            or counters.replay_actions
            != counters.edge_replay_actions + counters.promotion_power_on_replay_actions
            or counters.replay_passes
            != 1 + counters.edge_replay_passes + counters.promotion_power_on_replay_passes
        ):
            raise ValueError("Expedition checkpoint counters are not internally exact")

        pending_recovery = _inspect_pending_store_recovery(store_path, checkpoint)
        if pending_recovery is None:
            current_store, recovery_plan = _inspect_store_for_resume(store_path, checkpoint)
        else:
            current_store, pending_recovery_plan = pending_recovery
            recovery_plan = None
        if dict(current_store.manifest.get("metadata", {})) != store_metadata:
            raise ValueError("Expedition store provenance does not match this runner")

        archive = FrontierArchive.from_checkpoint_dict(current_store, checkpoint["archive"])
        if archive.capacity != config.archive_capacity:
            raise ValueError("Expedition checkpoint archive capacity does not match")
        roots = [cell for cell in archive.active_cells if cell.parent_id is None]
        if len(roots) != 1:
            raise ValueError("Expedition checkpoint must retain exactly one power-on root")
        if archive.selection_total != counters.attempts:
            raise ValueError("Expedition checkpoint archive selection count is inconsistent")
        if any(cell.cell_id not in checkpoint_cell_ids for cell in archive.active_cells):
            raise ValueError("Expedition checkpoint archive references a later store cell")
        if best_progress.index < max(
            cell.descriptor.milestone_index for cell in archive.active_cells
        ):
            raise ValueError("Expedition checkpoint best progress is behind its archive")
        if completion_cell_id is not None:
            completion = current_store.cells[completion_cell_id]
            if completion.descriptor.milestone_id != HALL_OF_FAME_KEY:
                raise ValueError("Expedition checkpoint completion cell is not Hall of Fame")

        if pending_recovery_plan is not None:
            store, recovery_disclosure = _apply_recovery_bundle(
                store_path,
                pending_recovery_plan.recovery_directory,
                pending_recovery_plan.pending_path,
            )
            archive = FrontierArchive.from_checkpoint_dict(store, checkpoint["archive"])
        elif recovery_plan is not None:
            store, recovery_disclosure = _recover_store_to_checkpoint(
                store_path,
                recovery_plan,
                checkpoint,
            )
            archive = FrontierArchive.from_checkpoint_dict(store, checkpoint["archive"])
        else:
            store = current_store
        if (
            store.event_sequence != int(checkpoint["store_event_sequence"])
            or store.event_head_sha256 != checkpoint["store_event_head_sha256"]
            or tuple(store.cells) != checkpoint_cell_ids
        ):
            raise RuntimeError("Expedition store is not exact after resume validation")

        _truncate_trace(trace_path, trace_offset)
        stop_marker.unlink(missing_ok=True)
        if recovery_disclosure is not None:
            store.audit("runner_post_checkpoint_store_recovered", **recovery_disclosure)
    else:
        store = ExpeditionStore.create(
            store_path,
            rom_sha256=rom.sha256,
            pyboy_version=version("pyboy"),
            metadata=store_metadata,
        )
        archive = FrontierArchive(store, config.archive_capacity)

    manifest = {
        "kind": "manifest",
        "schema_version": 2,
        "protocol_version": EXPEDITION_RUNNER_PROTOCOL_VERSION,
        "store_protocol_version": EXPEDITION_PROTOCOL_VERSION,
        "created_at": started_at,
        "rom": rom.public_dict(),
        "config": config.public_dict(),
        "actor": {
            "name": emitter.policy_id,
            "inputs": list(emitter_identity["inputs"]),
            "ram": False,
            "snapshots": False,
            "frozen_weights": bool(emitter_identity["frozen_weights"]),
        },
        "trainer": {
            "loop_inputs": ["rendered_rgb"],
            "referee_inputs": ["documented_read_only_ram"],
            "checkpoint_restore": True,
            "writer_model": "single_process_coordinator",
        },
        "verification": {
            "protocol": "edge-and-promotion-v2",
            "root_gate": "one_exact_fresh_power_on_replay",
            "ordinary_cell_gate": "one_exact_parent_to_child_edge_replay",
            "named_promotion_gate": (
                f"{config.promotion_replay_passes}_exact_fresh_power_on_replays"
            ),
            "ordinary_cells_persisted_per_suffix_maximum": 1,
        },
        "human_demonstrations": [],
        "pretrained_components": list(emitter_identity["pretrained_components"]),
        "source": source,
        "implementation_sha256": implementation,
        "run_config_sha256": run_config_sha256,
        "private_rom_path_recorded": False,
    }
    if not resume:
        _atomic_json(output / "manifest.json", manifest)
        _append_json(trace_path, manifest)
    else:
        if recovery_disclosure is not None:
            _append_json(
                trace_path,
                {
                    "kind": "runner_post_checkpoint_store_recovered",
                    "recorded_at": datetime.now(UTC).isoformat(),
                    **recovery_disclosure,
                },
            )
        _append_json(
            trace_path,
            {
                "kind": "run_resumed",
                "recorded_at": datetime.now(UTC).isoformat(),
                "checkpoint_total_actions": counters.total_actions,
                "checkpoint_attempts": counters.attempts,
                "checkpoint_archive_cells": len(archive.active_cells),
                "store_recovery_id": (
                    None
                    if recovery_disclosure is None
                    else recovery_disclosure["recovery_id"]
                ),
            },
        )
        if recovery_disclosure is not None:
            assert resume_pixels is not None
            pending_path = store_path / "recovery" / "PENDING.json"
            pending_path.unlink(missing_ok=True)
            _fsync_directory(pending_path.parent)
            recovery_trace_offset = trace_path.stat().st_size
            _write_checkpoint(
                checkpoint_path,
                _checkpoint_payload(
                    config=config,
                    rom=rom,
                    source=source,
                    implementation_sha256=implementation,
                    counters=counters,
                    rng=rng,
                    archive=archive,
                    attempts_by_parent=attempts_by_parent,
                    best_progress=best_progress,
                    reached_milestones=reached_milestones,
                    completion_cell_id=completion_cell_id,
                    started_at=started_at,
                    trace_offset=recovery_trace_offset,
                    latest_frame_pixels=resume_pixels,
                ),
            )

    disk_monitor = _RunDiskMonitor(
        output,
        max_output_bytes=config.max_output_bytes,
        min_free_bytes=config.min_free_bytes,
        reconcile_interval_actions=config.disk_reconcile_interval_actions,
        free_check_interval_seconds=config.disk_free_check_interval_seconds,
        initial_action_count=counters.total_actions,
    )

    stop_reason = "unknown"
    latest_pixels = resume_pixels
    latest_state: PokemonRedState | None = None
    current_attempt: dict[str, Any] | None = None
    start_clock = monotonic()
    last_status = 0.0
    active_stopper: _SignalStop | None = None

    def elapsed() -> float:
        return base_elapsed + monotonic() - start_clock

    def budget_reason(stopper: _SignalStop) -> str | None:
        if stopper.reason:
            return stopper.reason
        if stop_marker.exists():
            return "stop_requested"
        if disk_reason := disk_monitor.reason(counters.total_actions):
            return disk_reason
        if counters.total_actions >= config.max_actions:
            return "action_limit"
        if elapsed() >= config.duration_seconds:
            return "duration_limit"
        return None

    def verification_cancel_requested() -> bool:
        """Cancel long promotion replays only for an explicit or storage-safety stop."""

        if active_stopper is not None and active_stopper.reason is not None:
            return True
        if stop_marker.exists():
            return True
        return disk_monitor.reason(counters.total_actions) in {
            "low_disk_space",
            "output_limit",
        }

    def write_status(state: str, reason: str | None) -> None:
        nonlocal latest_pixels
        if latest_pixels is None:
            return
        attempts = 1 if state == "running" else 16
        for _attempt in range(attempts):
            disk_monitor.reconcile(counters.total_actions)
            disk_monitor.check_free(force=True)
            status = _status_payload(
                state=state,
                stop_reason=reason,
                config=config,
                counters=counters,
                archive=archive,
                best_progress=best_progress,
                started_at=started_at,
                elapsed_seconds=elapsed(),
                run_bytes=disk_monitor.run_bytes,
                disk_monitor=disk_monitor.status_dict(),
                current=current_attempt,
                latest_referee_state=latest_state,
                reached_milestones=reached_milestones,
                completion_cell_id=completion_cell_id,
                emitter_identity=emitter_identity,
            )
            reported_bytes = disk_monitor.run_bytes
            _write_live_artifacts(output, status, latest_pixels)
            disk_monitor.observe_files(
                output / "latest.png",
                output / "status.json",
                output / "index.html",
            )
            if state == "running" or disk_monitor.run_bytes == reported_bytes:
                break

    def checkpoint_written() -> None:
        disk_monitor.observe_files(
            checkpoint_path,
            checkpoint_path.with_name("checkpoint.previous.json.gz"),
        )
        disk_monitor.reconcile(counters.total_actions)

    def observe_cell_files(cell: FrontierCell) -> None:
        disk_monitor.observe_files(
            store.path / "events.jsonl",
            store.path / "index.json",
            store.path / "cells" / f"{cell.cell_id}.json",
            store.path / "snapshots" / f"{cell.snapshot_sha256}.json.gz",
            store.path / "segments" / f"{cell.segment_sha256}.json",
        )

    def persist_and_verify_candidate(
        candidate: BufferedSuffixCandidate,
        parent: FrontierCell,
        *,
        milestone_advanced: bool,
    ) -> tuple[FrontierCell, bool]:
        """Persist one buffered capture, prove its edge, then promote it if eligible."""

        nonlocal best_progress, completion_cell_id
        before_cells = len(store.cells)
        cell = store.add_cell(
            parent_id=parent.cell_id,
            snapshot=candidate.snapshot,
            actions_from_parent=candidate.actions_from_parent,
            descriptor=candidate.descriptor,
            screen_sha256=candidate.screen_sha256,
            discovered_global_action=candidate.discovered_global_action,
            referee_summary=candidate.referee_summary,
            policy_id=emitter.policy_id,
        )
        if len(store.cells) > before_cells:
            counters.cells_created += 1
        observe_cell_files(cell)

        semantic_evaluator = None
        if milestone_advanced:
            milestone = MILESTONES[candidate.progress.index - 1]

            def semantic_evaluator(
                replay_state: PokemonRedState,
                _pixels: np.ndarray,
                target: Any = milestone,
            ) -> bool:
                return bool(target.reached_by(replay_state))

        edge_replay = replay_frontier_edge(
            rom_path,
            store,
            cell.cell_id,
            evaluator=semantic_evaluator,
        )
        _record_edge_replay(counters, edge_replay)
        disk_monitor.observe_files(store.path / "events.jsonl")
        verification_passed = edge_replay.passed
        if not edge_replay.passed:
            store.audit(
                "frontier_verification_failed",
                verification_kind="edge",
                cell_id=cell.cell_id,
                milestone_id=candidate.progress.key,
                reason=edge_replay.failure_reason,
            )

        if milestone_advanced and edge_replay.passed:
            promotion_passed = True
            for replay_number in range(1, config.promotion_replay_passes + 1):
                replay = replay_frontier_cell(
                    rom_path,
                    store,
                    cell.cell_id,
                    evaluator=semantic_evaluator,
                    cancel_requested=verification_cancel_requested,
                )
                _record_promotion_replay(counters, replay)
                disk_monitor.observe_files(store.path / "events.jsonl")
                if not replay.passed:
                    promotion_passed = False
                    store.audit(
                        "frontier_verification_failed",
                        verification_kind="promotion_power_on",
                        cell_id=cell.cell_id,
                        milestone_id=candidate.progress.key,
                        replay_number=replay_number,
                        reason=replay.failure_reason,
                    )
                if "replay_cancelled" in replay.mismatch_reasons:
                    break
            verification_passed = promotion_passed

        if not verification_passed:
            counters.cells_rejected += 1
            disk_monitor.observe_files(store.path / "events.jsonl")
            return cell, False

        decision = archive.consider(cell)
        disk_monitor.observe_files(store.path / "events.jsonl")
        if not decision.admitted:
            counters.cells_rejected += 1
            return cell, False

        counters.cells_admitted += 1
        if candidate.progress.index > best_progress.index:
            best_progress = candidate.progress
            filename = f"{best_progress.index:03d}-{best_progress.key}.png"
            _save_png(candidate.pixels, output / "milestones" / filename)
            disk_monitor.observe_files(output / "milestones" / filename)
        if candidate.progress.key == HALL_OF_FAME_KEY:
            completion_cell_id = cell.cell_id
        return cell, True

    dashboard_server: ThreadingHTTPServer | None = None
    dashboard_thread: threading.Thread | None = None
    try:
        if config.dashboard_port:
            dashboard_server, dashboard_thread = _start_dashboard_server(
                output,
                config.dashboard_port,
            )
        with _SignalStop() as stopper, PokemonRedEmulator(rom_path) as emulator:
            active_stopper = stopper
            actor = PixelsOnlyActor(emulator)
            reader = PokemonRedStateReader(emulator)

            if checkpoint is None:
                latest_pixels = actor.observe()
                latest_state = reader.read()
                root_snapshot = FrozenSnapshot.freeze(emulator.save_state())
                root_descriptor = descriptor_from_state(
                    latest_state,
                    milestone_id=POWER_ON_PROGRESS.key,
                    milestone_index=POWER_ON_PROGRESS.index,
                    visual_key=visual_key(latest_pixels),
                )
                root = store.add_root(
                    snapshot=root_snapshot,
                    descriptor=root_descriptor,
                    screen_sha256=hashlib.sha256(latest_pixels.tobytes()).hexdigest(),
                    referee_summary=_referee_summary(
                        latest_state,
                        POWER_ON_PROGRESS,
                        parent=None,
                        tracker=MilestoneTracker(),
                    ),
                )
                root_replay = replay_frontier_cell(rom_path, store, root.cell_id)
                counters.replay_attempts += 1
                counters.replay_actions += root_replay.executed_action_count
                counters.replay_passes += int(root_replay.passed)
                store.audit(
                    "power_on_replay_gate",
                    cell_id=root.cell_id,
                    passed=root_replay.passed,
                    mismatch_reasons=list(root_replay.mismatch_reasons),
                )
                if not root_replay.passed:
                    raise RuntimeError("The exact power-on root failed its replay gate")
                decision = archive.consider(root)
                if not decision.admitted:
                    raise RuntimeError("The power-on root was not admitted to its empty archive")
                counters.cells_created = 1
                counters.cells_admitted = 1
                _save_png(latest_pixels, output / "milestones" / "000-power-on.png")
                _append_json(
                    trace_path,
                    {
                        "kind": "power_on_root",
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "cell_id": root.cell_id,
                        "snapshot_sha256": root.snapshot_sha256,
                        "screen_sha256": root.screen_sha256,
                    },
                )
                disk_monitor.observe_files(
                    trace_path,
                    store.path / "events.jsonl",
                    store.path / "index.json",
                    store.path / "cells" / f"{root.cell_id}.json",
                    store.path / "snapshots" / f"{root.snapshot_sha256}.json.gz",
                    store.path / "segments" / f"{root.segment_sha256}.json",
                    output / "milestones" / "000-power-on.png",
                )
                counters.elapsed_seconds = elapsed()
                trace_offset = trace_path.stat().st_size
                _write_checkpoint(
                    checkpoint_path,
                    _checkpoint_payload(
                        config=config,
                        rom=rom,
                        source=source,
                        implementation_sha256=implementation,
                        counters=counters,
                        rng=rng,
                        archive=archive,
                        attempts_by_parent=attempts_by_parent,
                        best_progress=best_progress,
                        reached_milestones=reached_milestones,
                        completion_cell_id=completion_cell_id,
                        started_at=started_at,
                        trace_offset=trace_offset,
                        latest_frame_pixels=latest_pixels,
                    ),
                )
                checkpoint_written()
                write_status("running", None)

            while (reason := budget_reason(stopper)) is None and completion_cell_id is None:
                parent, channel = archive.select(
                    rng,
                    frontier_probability=config.frontier_probability,
                    rehearsal_probability=config.rehearsal_probability,
                )
                attempts_by_parent[parent.cell_id] = attempts_by_parent.get(parent.cell_id, 0) + 1
                selection_count = attempts_by_parent[parent.cell_id]
                suffix_budget = adaptive_suffix_budget(
                    selection_count,
                    minimum=config.min_suffix_actions,
                    maximum=config.max_suffix_actions,
                    attempts_per_expansion=config.attempts_per_expansion,
                )
                suffix_budget = min(suffix_budget, config.max_actions - counters.total_actions)
                emulator.load_state(store.read_snapshot(parent.snapshot_sha256).thaw())
                counters.archive_restores += 1
                counters.attempts += 1
                tracker = MilestoneTracker()
                loop_detector = VisualLoopDetector(
                    config.loop_window_actions,
                    config.loop_repeat_limit,
                )
                verified_progress = _progress_for_cell(parent)
                exploration_probability = (
                    config.apprentice_post_frontier_epsilon
                    if verified_progress.index >= LEFT_HOME_MILESTONE_INDEX
                    else config.apprentice_pre_frontier_epsilon
                )
                emitter.reset(
                    actor,
                    exploration_probability=exploration_probability,
                )
                segment_actions: list[BlindAction] = []
                candidate_buffer = SuffixCandidateBuffer()
                committed_cell: FrontierCell | None = None
                committed_admitted = False
                attempt_reason = "suffix_budget"
                current_attempt = {
                    "number": counters.attempts,
                    "parent_id": parent.cell_id,
                    "selection_channel": channel,
                    "budget": suffix_budget,
                    "actions": 0,
                    "adaptive_selection_count": selection_count,
                    "starting_milestone": verified_progress.key,
                    "action_emitter": emitter.policy_id,
                    "exploration_probability": exploration_probability,
                    "candidate_captures": 0,
                    "ordinary_candidates_persisted": 0,
                    "ordinary_candidate_preflight": None,
                }
                _append_json(
                    trace_path,
                    {
                        "kind": "suffix_started",
                        "recorded_at": datetime.now(UTC).isoformat(),
                        **current_attempt,
                    },
                )
                disk_monitor.observe_files(trace_path, store.path / "events.jsonl")

                for suffix_action in range(1, suffix_budget + 1):
                    action = emitter.emit()
                    segment_actions.append(action)
                    alive = actor.act(action)
                    counters.total_actions += 1
                    counters.total_frames += action.total_frames
                    counters.action_counts[action.button] += 1
                    current_attempt["actions"] = suffix_action
                    latest_pixels = actor.observe()
                    latest_state = reader.read()
                    key = visual_key(latest_pixels)
                    candidate_progress, observed_keys = _progress_from_state(
                        verified_progress,
                        tracker,
                        latest_state,
                    )
                    reached_milestones.update(observed_keys)
                    milestone_advanced = candidate_progress.index > verified_progress.index
                    descriptor = descriptor_from_state(
                        latest_state,
                        milestone_id=candidate_progress.key,
                        milestone_index=candidate_progress.index,
                        visual_key=key,
                    )
                    loop_detected = loop_detector.observe(key)
                    capture_frontier = (
                        milestone_advanced
                        or suffix_action % config.frontier_capture_interval_actions == 0
                        or suffix_action == suffix_budget
                        or loop_detected
                    )

                    if capture_frontier:
                        summary = _referee_summary(
                            latest_state,
                            candidate_progress,
                            parent=parent,
                            tracker=tracker,
                        )
                        screen_sha256 = hashlib.sha256(latest_pixels.tobytes()).hexdigest()
                        candidate = BufferedSuffixCandidate(
                            snapshot=FrozenSnapshot.freeze(emulator.save_state()),
                            actions_from_parent=tuple(segment_actions),
                            descriptor=descriptor,
                            screen_sha256=screen_sha256,
                            discovered_global_action=counters.total_actions,
                            referee_summary=summary,
                            progress=candidate_progress,
                            pixels=latest_pixels.copy(),
                            priority=archive.candidate_priority(
                                descriptor,
                                summary,
                                parent.depth_actions + len(segment_actions),
                            ),
                        )
                        current_attempt["candidate_captures"] = (
                            candidate_buffer.captures_observed + 1
                        )
                        if milestone_advanced:
                            committed_cell, committed_admitted = persist_and_verify_candidate(
                                candidate,
                                parent,
                                milestone_advanced=True,
                            )
                            attempt_reason = (
                                "named_milestone_promoted"
                                if committed_admitted
                                else "named_milestone_rejected"
                            )
                            break
                        candidate_buffer.offer(candidate)

                    if loop_detected:
                        counters.loop_stops += 1
                        attempt_reason = "visual_loop"
                        break
                    if not alive:
                        counters.emulator_stops += 1
                        attempt_reason = "emulator_stopped"
                        break
                    if (reason := budget_reason(stopper)) is not None:
                        attempt_reason = reason
                        break
                    now = elapsed()
                    if now - last_status >= config.status_interval_seconds:
                        counters.elapsed_seconds = now
                        write_status("running", None)
                        last_status = now

                if committed_cell is None and candidate_buffer.candidate is not None:
                    ordinary_candidate = candidate_buffer.candidate
                    preflight = archive.preflight_ordinary_candidate(
                        ordinary_candidate.descriptor,
                        ordinary_candidate.referee_summary,
                        parent.depth_actions + len(ordinary_candidate.actions_from_parent),
                    )
                    current_attempt["ordinary_candidate_preflight"] = asdict(preflight)
                    if preflight.admitted:
                        committed_cell, committed_admitted = persist_and_verify_candidate(
                            ordinary_candidate,
                            parent,
                            milestone_advanced=False,
                        )
                        current_attempt["ordinary_candidates_persisted"] = 1
                    else:
                        counters.ordinary_preflight_rejections += 1

                counters.elapsed_seconds = elapsed()
                _append_json(
                    trace_path,
                    {
                        "kind": "suffix_completed",
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "attempt": counters.attempts,
                        "parent_id": parent.cell_id,
                        "final_anchor_id": (
                            committed_cell.cell_id if committed_admitted else parent.cell_id
                        ),
                        "persisted_candidate_id": (
                            None if committed_cell is None else committed_cell.cell_id
                        ),
                        "candidate_admitted": committed_admitted,
                        "candidate_captures": int(current_attempt["candidate_captures"]),
                        "ordinary_candidates_persisted": int(
                            current_attempt["ordinary_candidates_persisted"]
                        ),
                        "ordinary_candidate_preflight": current_attempt[
                            "ordinary_candidate_preflight"
                        ],
                        "selection_channel": channel,
                        "suffix_budget": suffix_budget,
                        "actions_executed": int(current_attempt["actions"]),
                        "stop_reason": attempt_reason,
                        "best_milestone": best_progress.public_dict(),
                    },
                )
                disk_monitor.observe_files(trace_path)
                current_attempt = None
                trace_offset = trace_path.stat().st_size
                _write_checkpoint(
                    checkpoint_path,
                    _checkpoint_payload(
                        config=config,
                        rom=rom,
                        source=source,
                        implementation_sha256=implementation,
                        counters=counters,
                        rng=rng,
                        archive=archive,
                        attempts_by_parent=attempts_by_parent,
                        best_progress=best_progress,
                        reached_milestones=reached_milestones,
                        completion_cell_id=completion_cell_id,
                        started_at=started_at,
                        trace_offset=trace_offset,
                        latest_frame_pixels=latest_pixels,
                    ),
                )
                checkpoint_written()
                write_status("running", None)

            if completion_cell_id is not None:
                stop_reason = "hall_of_fame_verified"
            else:
                stop_reason = reason or "unknown"

        counters.elapsed_seconds = elapsed()
        _append_json(
            trace_path,
            {
                "kind": "run_finished",
                "recorded_at": datetime.now(UTC).isoformat(),
                "stop_reason": stop_reason,
                "total_actions": counters.total_actions,
                "attempts": counters.attempts,
                "best_milestone": best_progress.public_dict(),
                "completion_cell_id": completion_cell_id,
            },
        )
        disk_monitor.observe_files(trace_path)
        resume_trace_offset = trace_path.stat().st_size
        _write_checkpoint(
            checkpoint_path,
            _checkpoint_payload(
                config=config,
                rom=rom,
                source=source,
                implementation_sha256=implementation,
                counters=counters,
                rng=rng,
                archive=archive,
                attempts_by_parent=attempts_by_parent,
                best_progress=best_progress,
                reached_milestones=reached_milestones,
                completion_cell_id=completion_cell_id,
                started_at=started_at,
                trace_offset=resume_trace_offset,
                latest_frame_pixels=latest_pixels,
            ),
        )
        checkpoint_written()
        write_status("finished", stop_reason)
    except Exception as error:
        counters.elapsed_seconds = elapsed()
        if latest_pixels is not None:
            with np.errstate(all="ignore"):
                write_status("failed", f"{type(error).__name__}: {error}")
        raise
    finally:
        _stop_dashboard_server(dashboard_server, dashboard_thread)

    return ExpeditionRunResult(
        run_directory=output,
        stop_reason=stop_reason,
        counters=counters,
        archive_cells=len(archive.active_cells),
        best_milestone=best_progress,
        completion_cell_id=completion_cell_id,
    )


def show_expedition_status(run_directory: Path) -> int:
    path = run_directory.expanduser().resolve() / "status.json"
    if not path.is_file():
        raise ValueError("Expedition status.json does not exist")
    status = json.loads(path.read_text(encoding="utf-8"))
    print(f"State: {status['state']}")
    print(f"Actions: {int(status['total_actions']):,}")
    print(f"Attempts: {int(status['attempts']):,}")
    print(f"Active frontier cells: {int(status['archive_cells']):,}")
    best = status.get("best_milestone", {})
    print(f"Best milestone: {best.get('label', 'Clean power-on')}")
    print(f"Replay passes: {int(status.get('replay_passes', 0)):,}")
    print(
        "Edge replay passes: "
        f"{int(status.get('edge_replay_passes', 0)):,}/"
        f"{int(status.get('edge_replay_attempts', 0)):,}"
    )
    print(
        "Promotion power-on replay passes: "
        f"{int(status.get('promotion_power_on_replay_passes', 0)):,}/"
        f"{int(status.get('promotion_power_on_replay_attempts', 0)):,}"
    )
    print(f"Stop reason: {status.get('stop_reason') or 'still running'}")
    return 0 if status.get("state") != "failed" else 1


def request_expedition_stop(run_directory: Path) -> int:
    output = run_directory.expanduser().resolve()
    if not (output / "status.json").is_file():
        raise ValueError("Expedition status.json does not exist")
    (output / "STOP").touch(exist_ok=True)
    print("Graceful expedition stop requested; the current short suffix will checkpoint.")
    return 0
