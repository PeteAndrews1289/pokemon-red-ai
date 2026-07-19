from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import json
import os
import platform
import random
import shutil
import signal
import zlib
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from types import FrameType
from typing import Any, Protocol

import numpy as np
from PIL import Image

from pokemon_red_ai.emulator import EmulatorSnapshot, PokemonRedEmulator
from pokemon_red_ai.learning import HashedQPolicy, RewardTracker, policy_state_key
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import RomFingerprint
from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader

BLIND_PROTOCOL_VERSION = "game-naive-pixels-v2"
OUTCOME_PROTOCOL_VERSION = "pixels-observation-outcome-reward-v2"
CONVENTIONAL_PROTOCOL_VERSION = "pixels-ram-explicit-objectives-v2"
CHECKPOINT_SCHEMA_VERSION = 3
EXPECTED_SCREEN_SHAPE = (144, 160, 3)
VISUAL_GRID_SHAPE = (18, 20)
VISUAL_QUANTIZATION_LEVELS = 8
NOOP_ACTION = "noop"
BLIND_ACTIONS = ("up", "down", "left", "right", "a", "b", "start", NOOP_ACTION)
ACTION_HOLD_FRAMES = 8
ACTION_RELEASE_FRAMES = 12
LEARNING_MODES = {"curious", "outcome", "conventional"}
ARCHIVE_MODES = {"archivist"}
RUN_MODES = {"monkey", "curious", "outcome", "conventional", "archivist"}


def protocol_version(mode: str) -> str:
    if mode == "outcome":
        return OUTCOME_PROTOCOL_VERSION
    if mode == "conventional":
        return CONVENTIONAL_PROTOCOL_VERSION
    return BLIND_PROTOCOL_VERSION


def mode_metadata(mode: str) -> dict[str, Any]:
    return {
        "monkey": {
            "run_name": "Pure Monkey — continuous uniform random from power-on",
            "actor": "uniform_random_controller",
            "policy_inputs": ["seeded_prng"],
            "reward_inputs": [],
            "trainer": "none",
        },
        "curious": {
            "run_name": "Visually Curious — online pixels-only novelty learner",
            "actor": "n_step_replay_q_pixel_policy",
            "policy_inputs": ["coarse_quantized_rendered_rgb", "seeded_prng"],
            "reward_inputs": ["coarse_quantized_rendered_rgb", "visual_visit_filter"],
            "trainer": "n_step_replay_q_learning_visual_novelty",
        },
        "outcome": {
            "run_name": "Outcome-Rewarded — pixels-only policy with semantic rewards",
            "actor": "n_step_replay_q_pixel_policy",
            "policy_inputs": ["coarse_quantized_rendered_rgb", "seeded_prng"],
            "reward_inputs": [
                "map_and_position",
                "party_count",
                "battle_state",
                "badge_bits",
                "pokedex_seen_and_owned",
                "event_flags",
                "bag_items",
            ],
            "trainer": "n_step_replay_q_learning_outcome_reward",
        },
        "conventional": {
            "run_name": "Conventional Agent — pixels, RAM, and explicit objectives",
            "actor": "scripted_bootstrap_then_n_step_replay_q_pixel_ram_policy",
            "policy_inputs": [
                "coarse_quantized_rendered_rgb",
                "map_and_position",
                "party_count",
                "battle_state",
                "badge_bits",
                "coarse_progress_state",
                "seeded_prng",
            ],
            "reward_inputs": [
                "map_and_position",
                "party_count",
                "battle_state",
                "badge_bits",
                "pokedex_seen_and_owned",
                "required_event_flags",
                "required_items",
            ],
            "trainer": "n_step_replay_q_learning_explicit_objectives",
        },
        "archivist": {
            "run_name": "Snapshot-assisted pixels-only Archivist from power-on",
            "actor": "uniform_random_controller",
            "policy_inputs": ["seeded_prng"],
            "reward_inputs": ["coarse_quantized_rendered_rgb", "visual_visit_filter"],
            "trainer": "pixel_novelty_archive",
        },
    }[mode]


class PixelController(Protocol):
    """The complete capability available to the blind actor."""

    def screen_rgb(self) -> np.ndarray: ...

    def tick(self, frames: int, *, render_last: bool = True) -> bool: ...

    def press(self, button: str, *, hold_frames: int = 8, release_frames: int = 16) -> bool: ...


@dataclass(frozen=True, slots=True)
class BlindAction:
    button: str
    hold_frames: int
    release_frames: int

    def __post_init__(self) -> None:
        if self.button not in BLIND_ACTIONS:
            raise ValueError(f"Unsupported blind action: {self.button}")
        if self.hold_frames < 1 or self.release_frames < 1:
            raise ValueError("Action frame counts must be positive")

    @property
    def total_frames(self) -> int:
        return self.hold_frames + self.release_frames

    def public_dict(self) -> dict[str, int | str]:
        return asdict(self)


class PixelsOnlyActor:
    """A deliberately narrow facade: rendered pixels in, controller actions out.

    The actor has no RAM, tile-map, save-state, raw-PyBoy, or game-state capability. Snapshot
    handling belongs to the trainer and is never passed to the novelty or action functions.
    """

    __slots__ = ("__controller",)

    def __init__(self, controller: PixelController) -> None:
        self.__controller = controller

    def observe(self) -> np.ndarray:
        pixels = self.__controller.screen_rgb()
        if pixels.shape != EXPECTED_SCREEN_SHAPE:
            raise RuntimeError(
                f"Expected rendered RGB shape {EXPECTED_SCREEN_SHAPE}, got {pixels.shape}"
            )
        if pixels.dtype != np.uint8:
            pixels = pixels.astype(np.uint8, copy=False)
        return pixels.copy()

    def act(self, action: BlindAction) -> bool:
        if action.button == NOOP_ACTION:
            return self.__controller.tick(action.total_frames, render_last=True)
        return self.__controller.press(
            action.button,
            hold_frames=action.hold_frames,
            release_frames=action.release_frames,
        )


def visual_signature(pixels: np.ndarray) -> bytes:
    """Map rendered pixels into a frozen, coarse visual cell.

    Eight-by-eight pixel blocks are averaged and quantized. This makes the cell less sensitive
    to individual sprite pixels while retaining the full-screen layout. No pretrained encoder,
    OCR, tile IDs, or game-specific features are involved.
    """

    if pixels.shape != EXPECTED_SCREEN_SHAPE:
        raise ValueError(f"Expected pixels with shape {EXPECTED_SCREEN_SHAPE}")
    rgb = pixels.astype(np.uint16, copy=False)
    gray = (rgb[:, :, 0] + rgb[:, :, 1] + rgb[:, :, 2]) // 3
    pooled = gray.reshape(18, 8, 20, 8).mean(axis=(1, 3))
    quantized = np.minimum(
        pooled.astype(np.uint16) * VISUAL_QUANTIZATION_LEVELS // 256,
        VISUAL_QUANTIZATION_LEVELS - 1,
    ).astype(np.uint8)
    return quantized.tobytes()


def visual_key(pixels: np.ndarray) -> bytes:
    signature = visual_signature(pixels)
    return hashlib.blake2b(
        signature,
        digest_size=16,
        person=b"pkmn-pixels-v1",
    ).digest()


def policy_visual_key(pixels: np.ndarray) -> bytes:
    """A coarser pixels-only state used by online policies to revisit learnable situations."""

    if pixels.shape != EXPECTED_SCREEN_SHAPE:
        raise ValueError(f"Expected pixels with shape {EXPECTED_SCREEN_SHAPE}")
    rgb = pixels.astype(np.uint16, copy=False)
    gray = (rgb[:, :, 0] + rgb[:, :, 1] + rgb[:, :, 2]) // 3
    pooled = gray.reshape(9, 16, 10, 16).mean(axis=(1, 3))
    quantized = np.minimum(pooled.astype(np.uint16) * 4 // 256, 3).astype(np.uint8)
    return hashlib.blake2b(
        quantized.tobytes(),
        digest_size=16,
        person=b"pkmn-policy-px1",
    ).digest()


class SeenVisualFilter:
    """A bounded Bloom filter for coarse visual-cell first visits."""

    def __init__(self, size_bytes: int, *, hashes: int = 4, payload: bytes | None = None) -> None:
        if size_bytes < 1_024:
            raise ValueError("Visual filter must be at least 1 KiB")
        if not 1 <= hashes <= 16:
            raise ValueError("Visual filter hash count must be between 1 and 16")
        if payload is not None and len(payload) != size_bytes:
            raise ValueError("Visual filter payload has the wrong size")
        self._bits = bytearray(payload or bytes(size_bytes))
        self.hashes = hashes

    @property
    def size_bytes(self) -> int:
        return len(self._bits)

    def check_and_add(self, key: bytes) -> bool:
        """Return True only when the key was definitely not present before this call."""

        if len(key) != 16:
            raise ValueError("Visual keys must be 16 bytes")
        bit_count = len(self._bits) * 8
        first = int.from_bytes(key[:8], "big")
        second = int.from_bytes(key[8:], "big") | 1
        positions = [int((first + index * second) % bit_count) for index in range(self.hashes)]
        present = all(self._bits[position >> 3] & (1 << (position & 7)) for position in positions)
        for position in positions:
            self._bits[position >> 3] |= 1 << (position & 7)
        return not present

    def payload(self) -> bytes:
        return bytes(self._bits)


@dataclass(frozen=True, slots=True)
class FrozenSnapshot:
    logical_frame: int
    sha256: str
    rom_sha256: str
    pyboy_version: str
    compressed_payload: bytes = field(repr=False)

    @classmethod
    def freeze(cls, snapshot: EmulatorSnapshot) -> FrozenSnapshot:
        return cls(
            logical_frame=snapshot.logical_frame,
            sha256=snapshot.sha256,
            rom_sha256=snapshot.rom_sha256,
            pyboy_version=snapshot.pyboy_version,
            compressed_payload=zlib.compress(snapshot.payload, level=1),
        )

    def thaw(self) -> EmulatorSnapshot:
        payload = zlib.decompress(self.compressed_payload)
        return EmulatorSnapshot(
            logical_frame=self.logical_frame,
            sha256=self.sha256,
            rom_sha256=self.rom_sha256,
            pyboy_version=self.pyboy_version,
            payload=payload,
        )

    def checkpoint_dict(self) -> dict[str, int | str]:
        return {
            "logical_frame": self.logical_frame,
            "sha256": self.sha256,
            "rom_sha256": self.rom_sha256,
            "pyboy_version": self.pyboy_version,
            "compressed_payload": base64.b64encode(self.compressed_payload).decode("ascii"),
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any]) -> FrozenSnapshot:
        return cls(
            logical_frame=int(value["logical_frame"]),
            sha256=str(value["sha256"]),
            rom_sha256=str(value["rom_sha256"]),
            pyboy_version=str(value["pyboy_version"]),
            compressed_payload=base64.b64decode(str(value["compressed_payload"])),
        )


@dataclass(slots=True)
class ArchiveCell:
    cell_id: int
    pixel_key: bytes
    snapshot: FrozenSnapshot
    parent_id: int | None
    actions_from_parent: tuple[BlindAction, ...]
    depth: int
    discovered_action: int
    selections: int = 0
    visits: int = 1

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "pixel_key": self.pixel_key.hex(),
            "snapshot": self.snapshot.checkpoint_dict(),
            "parent_id": self.parent_id,
            "actions_from_parent": [action.public_dict() for action in self.actions_from_parent],
            "depth": self.depth,
            "discovered_action": self.discovered_action,
            "selections": self.selections,
            "visits": self.visits,
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any]) -> ArchiveCell:
        return cls(
            cell_id=int(value["cell_id"]),
            pixel_key=bytes.fromhex(str(value["pixel_key"])),
            snapshot=FrozenSnapshot.from_checkpoint_dict(value["snapshot"]),
            parent_id=None if value["parent_id"] is None else int(value["parent_id"]),
            actions_from_parent=tuple(
                BlindAction(
                    button=str(action["button"]),
                    hold_frames=int(action["hold_frames"]),
                    release_frames=int(action["release_frames"]),
                )
                for action in value["actions_from_parent"]
            ),
            depth=int(value["depth"]),
            discovered_action=int(value["discovered_action"]),
            selections=int(value["selections"]),
            visits=int(value["visits"]),
        )


class DiscoveryArchive:
    """Trainer-owned pixel cells and snapshots for game-naive branching exploration."""

    def __init__(self, cells: list[ArchiveCell] | None = None) -> None:
        self.cells = cells or []
        self._by_key = {cell.pixel_key: cell.cell_id for cell in self.cells}
        if any(cell.cell_id != index for index, cell in enumerate(self.cells)):
            raise ValueError("Archive cell IDs must be contiguous and ordered")
        if len(self._by_key) != len(self.cells):
            raise ValueError("Archive contains duplicate visual keys")

    def __len__(self) -> int:
        return len(self.cells)

    @property
    def max_depth(self) -> int:
        return max((cell.depth for cell in self.cells), default=0)

    def find(self, key: bytes) -> ArchiveCell | None:
        cell_id = self._by_key.get(key)
        return None if cell_id is None else self.cells[cell_id]

    def add(
        self,
        *,
        key: bytes,
        snapshot: FrozenSnapshot,
        parent_id: int | None,
        actions_from_parent: tuple[BlindAction, ...],
        discovered_action: int,
    ) -> ArchiveCell:
        if key in self._by_key:
            raise ValueError("Visual cell is already in the archive")
        if parent_id is None:
            depth = 0
        else:
            if not 0 <= parent_id < len(self.cells):
                raise ValueError("Archive parent does not exist")
            depth = self.cells[parent_id].depth + len(actions_from_parent)
        cell = ArchiveCell(
            cell_id=len(self.cells),
            pixel_key=key,
            snapshot=snapshot,
            parent_id=parent_id,
            actions_from_parent=actions_from_parent,
            depth=depth,
            discovered_action=discovered_action,
        )
        self.cells.append(cell)
        self._by_key[key] = cell.cell_id
        return cell

    def select(self, rng: random.Random, *, tournament_size: int = 32) -> ArchiveCell:
        if not self.cells:
            raise RuntimeError("Cannot select from an empty archive")
        sample_size = min(tournament_size, len(self.cells))
        candidates = [self.cells[rng.randrange(len(self.cells))] for _ in range(sample_size)]
        selected = min(
            candidates,
            key=lambda cell: (cell.selections, cell.visits, cell.cell_id),
        )
        selected.selections += 1
        return selected

    def checkpoint_list(self) -> list[dict[str, Any]]:
        return [cell.checkpoint_dict() for cell in self.cells]


@dataclass(frozen=True, slots=True)
class BlindRunConfig:
    mode: str = "archivist"
    duration_seconds: float = 28_800
    max_actions: int = 5_000_000
    seed: int = 20_260_719
    branch_actions: int = 32
    max_archive_cells: int = 10_000
    seen_filter_bytes: int = 8 * 1024 * 1024
    q_policy_buckets: int = 16_384
    q_n_step: int = 128
    replay_capacity: int = 100_000
    replay_batch_size: int = 16
    replay_interval: int = 4
    important_replay_capacity: int = 10_000
    screenshot_limit: int = 96
    timelapse_interval_seconds: float = 900
    timelapse_limit: int = 256
    status_interval_seconds: float = 30
    checkpoint_interval_seconds: float = 300
    max_output_bytes: int = 512 * 1024 * 1024
    min_free_bytes: int = 10 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.mode not in RUN_MODES:
            raise ValueError(f"mode must be one of: {', '.join(sorted(RUN_MODES))}")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if self.max_actions < 1:
            raise ValueError("max_actions must be positive")
        if self.branch_actions < 1:
            raise ValueError("branch_actions must be positive")
        if self.max_archive_cells < 1:
            raise ValueError("max_archive_cells must be positive")
        if self.seen_filter_bytes < 1_024:
            raise ValueError("seen_filter_bytes must be at least 1 KiB")
        if self.q_policy_buckets < 1_024:
            raise ValueError("q_policy_buckets must be at least 1,024")
        if self.q_n_step < 1:
            raise ValueError("q_n_step must be positive")
        if self.replay_capacity < 1:
            raise ValueError("replay_capacity must be positive")
        if not 1 <= self.replay_batch_size <= self.replay_capacity:
            raise ValueError("replay_batch_size must fit inside replay_capacity")
        if self.replay_interval < 1:
            raise ValueError("replay_interval must be positive")
        if self.important_replay_capacity < 1:
            raise ValueError("important_replay_capacity must be positive")
        if self.screenshot_limit < 1:
            raise ValueError("screenshot_limit must be positive")
        if self.timelapse_interval_seconds <= 0 or self.timelapse_limit < 1:
            raise ValueError("timelapse interval and limit must be positive")
        if self.status_interval_seconds <= 0 or self.checkpoint_interval_seconds <= 0:
            raise ValueError("status and checkpoint intervals must be positive")
        if self.max_output_bytes < 1_048_576:
            raise ValueError("max_output_bytes must be at least 1 MiB")
        if self.min_free_bytes < 0:
            raise ValueError("min_free_bytes cannot be negative")

    def public_dict(self) -> dict[str, int | float | str]:
        return asdict(self)


@dataclass(slots=True)
class BlindCounters:
    total_actions: int = 0
    total_frames: int = 0
    unique_visual_cells: int = 0
    not_definitely_new_observations: int = 0
    archive_additions: int = 0
    archive_restores: int = 0
    episodes: int = 1
    elapsed_seconds: float = 0
    action_counts: Counter[str] = field(default_factory=Counter)

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "total_actions": self.total_actions,
            "total_frames": self.total_frames,
            "unique_visual_cells": self.unique_visual_cells,
            "not_definitely_new_observations": self.not_definitely_new_observations,
            "archive_additions": self.archive_additions,
            "archive_restores": self.archive_restores,
            "episodes": self.episodes,
            "elapsed_seconds": self.elapsed_seconds,
            "action_counts": dict(self.action_counts),
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any]) -> BlindCounters:
        return cls(
            total_actions=int(value["total_actions"]),
            total_frames=int(value["total_frames"]),
            unique_visual_cells=int(value["unique_visual_cells"]),
            not_definitely_new_observations=int(value["not_definitely_new_observations"]),
            archive_additions=int(value["archive_additions"]),
            archive_restores=int(value["archive_restores"]),
            episodes=int(value["episodes"]),
            elapsed_seconds=float(value["elapsed_seconds"]),
            action_counts=Counter({str(k): int(v) for k, v in value["action_counts"].items()}),
        )


@dataclass(frozen=True, slots=True)
class BlindRunResult:
    run_directory: Path
    stop_reason: str
    counters: BlindCounters
    archive_cells: int


class _AppendTrace:
    def __init__(self, path: Path, *, resume: bool) -> None:
        self.path = path
        self._file = path.open("a" if resume else "x", encoding="utf-8")

    def write(self, kind: str, **payload: Any) -> None:
        record = {"schema_version": 1, "kind": kind, **payload}
        self._file.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self._file.flush()

    def position(self) -> int:
        self._file.flush()
        return self._file.buffer.tell()

    def close(self) -> None:
        self._file.close()


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
        self.reason = signal.Signals(event).name.lower()


def sample_blind_action(rng: random.Random) -> BlindAction:
    return BlindAction(
        button=rng.choice(BLIND_ACTIONS),
        hold_frames=ACTION_HOLD_FRAMES,
        release_frames=ACTION_RELEASE_FRAMES,
    )


def action_for_button(button: str, rng: random.Random) -> BlindAction:
    del rng
    return BlindAction(
        button=button,
        hold_frames=ACTION_HOLD_FRAMES,
        release_frames=ACTION_RELEASE_FRAMES,
    )


def conventional_bootstrap_actions() -> tuple[BlindAction, ...]:
    """The disclosed conventional-agent macro that reaches Red's bedroom.

    It is intentionally unavailable to the other arms. The timings reproduce the separately
    calibrated bootstrap while keeping every controller decision and emulated frame in the run's
    counters and trace.
    """

    def press(button: str, wait_frames: int) -> BlindAction:
        return BlindAction(button=button, hold_frames=8, release_frames=16 + wait_frames)

    normal = 240
    menu = 120
    actions = [BlindAction(NOOP_ACTION, 900, 900), press("start", normal)]
    actions.extend(press("a", normal) for _ in range(14))
    actions.extend((press("down", menu), press("a", normal)))
    actions.extend(press("a", normal) for _ in range(5))
    actions.extend((press("down", menu), press("a", normal)))
    actions.extend(press("a", normal) for _ in range(6))
    actions.append(press("a", 300))
    return tuple(actions)


def default_blind_run_directory(mode: str, base: Path = Path("runs")) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = base / f"blind-{mode}-{timestamp}"
    counter = 1
    while candidate.exists():
        candidate = base / f"blind-{mode}-{timestamp}-{counter}"
        counter += 1
    return candidate


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _json_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_json_tuple(item) for item in value)
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _save_png(pixels: np.ndarray, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    Image.fromarray(pixels).save(temporary, format="PNG", optimize=True)
    os.replace(temporary, path)


def _implementation_sha256() -> str:
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in (
        "blind.py",
        "blind_report.py",
        "cli.py",
        "constants.py",
        "emulator.py",
        "learning.py",
        "state.py",
    ):
        digest.update(name.encode("utf-8"))
        digest.update((package / name).read_bytes())
    return digest.hexdigest()


def _checkpoint_payload(
    *,
    config: BlindRunConfig,
    rom: RomFingerprint,
    counters: BlindCounters,
    rng: random.Random,
    seen: SeenVisualFilter,
    archive: DiscoveryArchive,
    current_snapshot: FrozenSnapshot,
    current_parent_id: int | None,
    pending_actions: list[BlindAction],
    branch_remaining: int,
    history: list[dict[str, int | float]],
    screenshots: list[dict[str, Any]],
    policy: HashedQPolicy | None,
    reward_tracker: RewardTracker | None,
    referee_tracker: RewardTracker,
    conventional_bootstrap_index: int,
    source_identity: dict[str, str | bool],
    implementation_sha256: str,
    trace_offset: int,
) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "protocol_version": protocol_version(config.mode),
        "rom_sha256": rom.sha256,
        "source": source_identity,
        "implementation_sha256": implementation_sha256,
        "trace_offset": trace_offset,
        "config": config.public_dict(),
        "counters": counters.checkpoint_dict(),
        "rng_state": rng.getstate(),
        "seen_filter": {
            "size_bytes": seen.size_bytes,
            "hashes": seen.hashes,
            "payload": base64.b64encode(seen.payload()).decode("ascii"),
        },
        "archive": archive.checkpoint_list(),
        "current_snapshot": current_snapshot.checkpoint_dict(),
        "current_parent_id": current_parent_id,
        "pending_actions": [action.public_dict() for action in pending_actions],
        "branch_remaining": branch_remaining,
        "history": history,
        "screenshots": screenshots,
        "policy": None if policy is None else policy.checkpoint_dict(),
        "reward_tracker": (None if reward_tracker is None else reward_tracker.checkpoint_dict()),
        "referee_tracker": referee_tracker.checkpoint_dict(),
        "conventional_bootstrap_index": conventional_bootstrap_index,
    }


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    previous = path.with_name("checkpoint.previous.json.gz")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=3) as output:
        json.dump(payload, output, sort_keys=True, separators=(",", ":"))
    with gzip.open(temporary, "rb") as verification:
        while verification.read(1024 * 1024):
            pass
    with temporary.open("rb") as checkpoint_file:
        os.fsync(checkpoint_file.fileno())
    if path.exists():
        os.replace(path, previous)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _read_checkpoint(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        value = json.load(source)
    if int(value.get("schema_version", -1)) != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("Unsupported blind-run checkpoint schema")
    mode = str(value.get("config", {}).get("mode", ""))
    if mode not in RUN_MODES or value.get("protocol_version") != protocol_version(mode):
        raise ValueError("Checkpoint uses a different blindness protocol")
    return value


def _read_available_checkpoint(path: Path) -> tuple[Path, dict[str, Any]]:
    candidates = (path, path.with_name("checkpoint.previous.json.gz"))
    errors: list[str] = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            return candidate, _read_checkpoint(candidate)
        except (OSError, ValueError, EOFError, gzip.BadGzipFile, json.JSONDecodeError) as error:
            errors.append(f"{candidate.name}: {type(error).__name__}")
    detail = "; ".join(errors) or "no checkpoint generation exists"
    raise ValueError(f"No valid checkpoint is available ({detail})")


def _truncate_trace_to_checkpoint(trace_path: Path, checkpoint: dict[str, Any]) -> int:
    offset = int(checkpoint["trace_offset"])
    size = trace_path.stat().st_size
    if not 0 <= offset <= size:
        raise ValueError("Checkpoint trace offset is outside the trace file")
    with trace_path.open("r+b") as trace_file:
        trace_file.truncate(offset)
        trace_file.flush()
        os.fsync(trace_file.fileno())
    return offset


def _status_payload(
    *,
    mode: str,
    state: str,
    stop_reason: str | None,
    counters: BlindCounters,
    archive: DiscoveryArchive,
    config: BlindRunConfig,
    started_at: str,
    run_bytes: int,
    policy: HashedQPolicy | None,
    reward_tracker: RewardTracker | None,
    referee_tracker: RewardTracker,
    referee_state: PokemonRedState | None,
) -> dict[str, Any]:
    novelty_actions = max(counters.unique_visual_cells - 1, 0)
    novelty_rate = novelty_actions / counters.total_actions if counters.total_actions else 0.0
    metadata = mode_metadata(mode)
    return {
        "schema_version": 1,
        "protocol_version": protocol_version(mode),
        "run_name": metadata["run_name"],
        "run_class": "development",
        "mode": mode,
        "state": state,
        "stop_reason": stop_reason,
        "started_at": started_at,
        "updated_at": datetime.now(UTC).isoformat(),
        "process_id": os.getpid(),
        "heartbeat_interval_seconds": config.status_interval_seconds,
        "elapsed_seconds": round(counters.elapsed_seconds, 3),
        "duration_seconds": config.duration_seconds,
        "total_actions": counters.total_actions,
        "max_actions": config.max_actions,
        "total_frames": counters.total_frames,
        "unique_visual_cells": counters.unique_visual_cells,
        "not_definitely_new_observations": counters.not_definitely_new_observations,
        "novelty_rate": round(novelty_rate, 6),
        "archive_cells": len(archive),
        "archive_capacity": config.max_archive_cells if mode in ARCHIVE_MODES else 0,
        "archive_saturated": mode in ARCHIVE_MODES and len(archive) >= config.max_archive_cells,
        "archive_restores": counters.archive_restores,
        "max_action_depth": archive.max_depth if mode in ARCHIVE_MODES else counters.total_actions,
        "actions_per_second": round(
            counters.total_actions / counters.elapsed_seconds if counters.elapsed_seconds else 0,
            2,
        ),
        "action_counts": dict(sorted(counters.action_counts.items())),
        "run_bytes": run_bytes,
        "max_output_bytes": config.max_output_bytes,
        "button_policy_inputs": metadata["policy_inputs"],
        "trainer_inputs": metadata["reward_inputs"],
        "intrinsic_score": "definite first visit to a coarse visual pixel cell",
        "snapshot_assisted": mode in ARCHIVE_MODES,
        "continuous_playthrough": mode not in ARCHIVE_MODES,
        "ram_used_by_actor": mode == "conventional",
        "ram_used_by_reward": mode in {"outcome", "conventional"},
        "ram_used_by_actor_or_reward": mode in {"outcome", "conventional"},
        "ram_used_by_referee": True,
        "pretrained_components": [],
        "human_demonstrations": [],
        "learning_updates": 0 if policy is None else policy.updates,
        "policy_buckets_visited": 0 if policy is None else policy.occupied_buckets,
        "exploratory_actions": 0 if policy is None else policy.exploratory_actions,
        "replay_transitions": 0 if policy is None else policy.replay_size,
        "replay_updates": 0 if policy is None else policy.replay_updates,
        "important_replay_transitions": 0 if policy is None else len(policy.important),
        "pending_n_step_transitions": 0 if policy is None else len(policy.pending),
        "n_step_horizon": 0 if policy is None else policy.n_step,
        "reward_total": 0.0 if reward_tracker is None else round(reward_tracker.total_reward, 3),
        "visual_reward": 0.0 if reward_tracker is None else round(reward_tracker.visual_reward, 3),
        "outcome_reward": (
            0.0 if reward_tracker is None else round(reward_tracker.outcome_reward, 3)
        ),
        "maps_seen": len(referee_tracker.seen_maps),
        "positions_seen": len(referee_tracker.seen_positions),
        "warps_seen": len(referee_tracker.seen_warps),
        "max_party_count": referee_tracker.max_party_count,
        "max_party_level": referee_tracker.max_party_level,
        "pokedex_seen": len(referee_tracker.seen_pokedex_species),
        "pokedex_owned": len(referee_tracker.owned_pokedex_species),
        "event_flags_seen": len(referee_tracker.seen_event_flags),
        "bag_items_seen": len(referee_tracker.seen_bag_items),
        "moves_seen": len(referee_tracker.seen_moves),
        "blackouts": referee_tracker.blackouts,
        "badge_count": referee_tracker.badge_bits.bit_count(),
        "reward_components": (
            {} if reward_tracker is None else dict(sorted(reward_tracker.component_totals.items()))
        ),
        "referee_state": None if referee_state is None else referee_state.public_dict(),
    }


def _write_dashboard(
    run_directory: Path,
    status: dict[str, Any],
    history: list[dict[str, int | float]],
    screenshots: list[dict[str, Any]],
) -> None:
    from pokemon_red_ai.blind_report import render_blind_dashboard

    rendered = render_blind_dashboard(status, history, screenshots)
    destination = run_directory / "index.html"
    temporary = destination.with_suffix(".html.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, destination)


def _should_capture(unique_cells: int, saved: int, limit: int) -> bool:
    if saved >= limit:
        return False
    if unique_cells <= 64:
        return unique_cells > 0 and unique_cells & (unique_cells - 1) == 0
    return unique_cells % 250 == 0


def _load_run_state(
    checkpoint: dict[str, Any],
    *,
    config: BlindRunConfig,
    rom: RomFingerprint,
    source_identity: dict[str, str | bool],
    implementation_sha256: str,
) -> tuple[
    BlindCounters,
    random.Random,
    SeenVisualFilter,
    DiscoveryArchive,
    FrozenSnapshot,
    int | None,
    list[BlindAction],
    int,
    list[dict[str, int | float]],
    list[dict[str, Any]],
    HashedQPolicy | None,
    RewardTracker | None,
    RewardTracker,
    int,
]:
    if checkpoint["rom_sha256"] != rom.sha256:
        raise ValueError("Checkpoint belongs to a different ROM revision")
    if checkpoint["config"] != config.public_dict():
        raise ValueError("Resume configuration does not match the checkpoint")
    if checkpoint.get("source") != source_identity:
        raise ValueError("Resume source commit or worktree state does not match the checkpoint")
    if checkpoint.get("implementation_sha256") != implementation_sha256:
        raise ValueError("Resume implementation does not match the checkpoint")
    rng = random.Random()
    rng.setstate(_json_tuple(checkpoint["rng_state"]))
    seen_value = checkpoint["seen_filter"]
    seen = SeenVisualFilter(
        int(seen_value["size_bytes"]),
        hashes=int(seen_value["hashes"]),
        payload=base64.b64decode(seen_value["payload"]),
    )
    archive = DiscoveryArchive(
        [ArchiveCell.from_checkpoint_dict(value) for value in checkpoint["archive"]]
    )
    pending_actions = [
        BlindAction(
            button=str(value["button"]),
            hold_frames=int(value["hold_frames"]),
            release_frames=int(value["release_frames"]),
        )
        for value in checkpoint["pending_actions"]
    ]
    return (
        BlindCounters.from_checkpoint_dict(checkpoint["counters"]),
        rng,
        seen,
        archive,
        FrozenSnapshot.from_checkpoint_dict(checkpoint["current_snapshot"]),
        checkpoint["current_parent_id"],
        pending_actions,
        int(checkpoint["branch_remaining"]),
        list(checkpoint["history"]),
        list(checkpoint["screenshots"]),
        (
            None
            if checkpoint.get("policy") is None
            else HashedQPolicy.from_checkpoint_dict(checkpoint["policy"])
        ),
        (
            None
            if checkpoint.get("reward_tracker") is None
            else RewardTracker.from_checkpoint_dict(checkpoint["reward_tracker"])
        ),
        RewardTracker.from_checkpoint_dict(checkpoint["referee_tracker"]),
        int(checkpoint.get("conventional_bootstrap_index", 0)),
    )


def run_blind_experiment(
    rom_path: Path,
    rom: RomFingerprint,
    *,
    config: BlindRunConfig,
    run_directory: Path | None = None,
    resume: bool = False,
) -> BlindRunResult:
    """Run a bounded game-naive experiment from a clean power-on state."""

    output = run_directory or default_blind_run_directory(config.mode)
    checkpoint_path = output / "checkpoint.json.gz"
    stop_marker = output / "STOP"
    source = detect_source_provenance()
    source_identity = source.public_dict()
    implementation_sha256 = _implementation_sha256()
    resume_checkpoint: dict[str, Any] | None = None
    resumed_checkpoint_name: str | None = None
    invalidated_trace_offset: int | None = None
    if resume:
        if not output.is_dir():
            raise ValueError("--resume requires an existing run directory with a checkpoint")
        checkpoint_used, resume_checkpoint = _read_available_checkpoint(checkpoint_path)
        resumed_checkpoint_name = checkpoint_used.name
        previous_status = json.loads((output / "status.json").read_text(encoding="utf-8"))
        terminal_reasons = {"action_limit", "duration_limit", "output_limit", "low_disk_space"}
        if previous_status.get("stop_reason") in terminal_reasons:
            raise ValueError("This run already reached a terminal budget and cannot be resumed")
        if resume_checkpoint["rom_sha256"] != rom.sha256:
            raise ValueError("Checkpoint belongs to a different ROM revision")
        if resume_checkpoint["config"] != config.public_dict():
            raise ValueError("Resume configuration does not match the checkpoint")
        if resume_checkpoint.get("source") != source_identity:
            raise ValueError("Resume source commit or worktree state does not match the checkpoint")
        if resume_checkpoint.get("implementation_sha256") != implementation_sha256:
            raise ValueError("Resume implementation does not match the checkpoint")
        invalidated_trace_offset = _truncate_trace_to_checkpoint(
            output / "trace.jsonl", resume_checkpoint
        )
        stop_marker.unlink(missing_ok=True)
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "screenshots").mkdir()

    started_at = datetime.now(UTC).isoformat()
    trace = _AppendTrace(output / "trace.jsonl", resume=resume)
    stop_reason = "unknown"
    counters = BlindCounters()
    archive = DiscoveryArchive()
    status_history: list[dict[str, int | float]] = []
    screenshots: list[dict[str, Any]] = []
    current_parent_id: int | None = None
    pending_actions: list[BlindAction] = []
    branch_remaining = 0
    policy: HashedQPolicy | None = None
    reward_tracker: RewardTracker | None = None
    referee_tracker = RewardTracker("observer")
    conventional_bootstrap_index = 0
    referee_state: PokemonRedState | None = None

    try:
        with PokemonRedEmulator(rom_path) as emulator:
            actor = PixelsOnlyActor(emulator)
            referee_reader = PokemonRedStateReader(emulator)
            if resume:
                if resume_checkpoint is None:
                    raise RuntimeError("Resume checkpoint was not loaded")
                (
                    counters,
                    rng,
                    seen,
                    archive,
                    current_snapshot,
                    current_parent_id,
                    pending_actions,
                    branch_remaining,
                    status_history,
                    screenshots,
                    policy,
                    reward_tracker,
                    referee_tracker,
                    conventional_bootstrap_index,
                ) = _load_run_state(
                    resume_checkpoint,
                    config=config,
                    rom=rom,
                    source_identity=source_identity,
                    implementation_sha256=implementation_sha256,
                )
                emulator.load_state(current_snapshot.thaw())
                current_pixels = actor.observe()
                started_at = str(
                    json.loads((output / "status.json").read_text(encoding="utf-8"))["started_at"]
                )
                trace.write(
                    "run_resumed",
                    resumed_at=datetime.now(UTC).isoformat(),
                    checkpoint_action=counters.total_actions,
                    checkpoint_generation=resumed_checkpoint_name,
                    invalidated_trace_after_offset=invalidated_trace_offset,
                    source=source_identity,
                    implementation_sha256=implementation_sha256,
                )
                resume_checkpoint = None
            else:
                counters = BlindCounters()
                rng = random.Random(config.seed)
                seen = SeenVisualFilter(config.seen_filter_bytes)
                archive = DiscoveryArchive()
                emulator.tick(1, render_last=True)
                root_pixels = actor.observe()
                root_key = visual_key(root_pixels)
                seen.check_and_add(root_key)
                counters.unique_visual_cells = 1
                current_snapshot = FrozenSnapshot.freeze(emulator.save_state())
                current_parent_id = None
                pending_actions = []
                status_history = []
                screenshots = []
                policy = (
                    HashedQPolicy(
                        len(BLIND_ACTIONS),
                        bucket_count=config.q_policy_buckets,
                        n_step=config.q_n_step,
                        replay_capacity=config.replay_capacity,
                        replay_batch_size=config.replay_batch_size,
                        replay_interval=config.replay_interval,
                        important_capacity=config.important_replay_capacity,
                    )
                    if config.mode in LEARNING_MODES
                    else None
                )
                reward_tracker = (
                    RewardTracker(config.mode) if config.mode in LEARNING_MODES else None
                )
                referee_tracker = RewardTracker("observer")
                conventional_bootstrap_index = 0
                if config.mode in ARCHIVE_MODES:
                    root = archive.add(
                        key=root_key,
                        snapshot=current_snapshot,
                        parent_id=None,
                        actions_from_parent=(),
                        discovered_action=0,
                    )
                    current_parent_id = root.cell_id
                current_pixels = root_pixels
                root_name = "screenshots/cell-000000.png"
                _save_png(root_pixels, output / root_name)
                screenshots.append(
                    {
                        "file": root_name,
                        "label": "Power-on cell",
                        "action": 0,
                        "unique_visual_cells": 1,
                        "capture_type": "power_on",
                        "elapsed_seconds": 0.0,
                    }
                )
                metadata = mode_metadata(config.mode)
                trace.write(
                    "manifest",
                    created_at=started_at,
                    run_type="development",
                    run_name=metadata["run_name"],
                    actor=metadata["actor"],
                    trainer=metadata["trainer"],
                    start_condition="clean_power_on",
                    blindness_protocol=protocol_version(config.mode),
                    button_policy_inputs=metadata["policy_inputs"],
                    trainer_inputs=metadata["reward_inputs"],
                    intrinsic_score_inputs=metadata["reward_inputs"],
                    forbidden_policy_sources=(
                        [
                            "ram",
                            "tile_ids",
                            "game_area",
                            "ocr",
                            "walkthroughs",
                            "demonstrations",
                            "pretrained_visual_encoder",
                        ]
                        if config.mode != "conventional"
                        else [
                            "memory_writes",
                            "walkthroughs_beyond_disclosed_bootstrap",
                            "demonstrations",
                            "pretrained_visual_encoder",
                        ]
                    ),
                    ram_used_by_actor=config.mode == "conventional",
                    ram_used_by_reward=config.mode in {"outcome", "conventional"},
                    ram_used_by_actor_or_reward=config.mode in {"outcome", "conventional"},
                    ram_used_by_referee=True,
                    referee_outputs_never_enter_policy_or_reward=(
                        config.mode in {"monkey", "curious"}
                    ),
                    archive_selection_inputs=(
                        ["pixel_cell", "selection_count", "visit_count"]
                        if config.mode in ARCHIVE_MODES
                        else []
                    ),
                    snapshot_assisted=config.mode in ARCHIVE_MODES,
                    continuous_playthrough=config.mode not in ARCHIVE_MODES,
                    scripted_bootstrap_actions=(
                        len(conventional_bootstrap_actions())
                        if config.mode == "conventional"
                        else 0
                    ),
                    config=config.public_dict(),
                    rom=rom.public_dict(),
                    source=source.public_dict(),
                    implementation_sha256=implementation_sha256,
                    software={
                        "python": platform.python_version(),
                        "pyboy": version("pyboy"),
                        "project": version("pokemon-red-ai"),
                    },
                )

            segment_start = monotonic()
            last_status = segment_start - config.status_interval_seconds
            last_checkpoint = segment_start - config.checkpoint_interval_seconds
            base_elapsed = counters.elapsed_seconds
            timelapse_captures = sum(
                shot.get("capture_type") == "timelapse" for shot in screenshots
            )
            last_timelapse_elapsed = max(
                (
                    float(shot.get("elapsed_seconds", 0))
                    for shot in screenshots
                    if shot.get("capture_type") == "timelapse"
                ),
                default=base_elapsed,
            )
            with _SignalStop() as signal_stop:
                while True:
                    now = monotonic()
                    counters.elapsed_seconds = base_elapsed + (now - segment_start)
                    if signal_stop.reason:
                        stop_reason = signal_stop.reason
                        break
                    if stop_marker.exists():
                        stop_reason = "stop_requested"
                        break
                    if counters.elapsed_seconds >= config.duration_seconds:
                        stop_reason = "duration_limit"
                        break
                    if counters.total_actions >= config.max_actions:
                        stop_reason = "action_limit"
                        break
                    if config.mode in ARCHIVE_MODES and branch_remaining <= 0:
                        selected = archive.select(rng)
                        emulator.load_state(selected.snapshot.thaw())
                        current_pixels = actor.observe()
                        counters.archive_restores += 1
                        current_parent_id = selected.cell_id
                        pending_actions = []
                        branch_remaining = config.branch_actions

                    selected_bucket: int | None = None
                    selected_action_index: int | None = None
                    if config.mode == "conventional" and conventional_bootstrap_index < len(
                        conventional_bootstrap_actions()
                    ):
                        action = conventional_bootstrap_actions()[conventional_bootstrap_index]
                        conventional_bootstrap_index += 1
                    elif policy is not None:
                        policy_observation = (
                            referee_reader.read()
                            if config.mode == "conventional" and referee_reader is not None
                            else None
                        )
                        choice_key = policy_state_key(
                            policy_visual_key(current_pixels),
                            policy_observation,
                        )
                        selected_action_index, selected_bucket, _epsilon = policy.select(
                            choice_key, rng
                        )
                        action = action_for_button(BLIND_ACTIONS[selected_action_index], rng)
                    else:
                        action = sample_blind_action(rng)
                    alive = actor.act(action)
                    counters.total_actions += 1
                    counters.total_frames += action.total_frames
                    counters.action_counts[action.button] += 1
                    if config.mode in ARCHIVE_MODES:
                        pending_actions.append(action)
                        branch_remaining -= 1
                    if not alive:
                        stop_reason = "emulator_stopped"
                        break

                    pixels = actor.observe()
                    key = visual_key(pixels)
                    definitely_new = seen.check_and_add(key)
                    if definitely_new:
                        counters.unique_visual_cells += 1
                    else:
                        counters.not_definitely_new_observations += 1

                    referee_state = referee_reader.read()
                    referee_tracker.score(
                        visually_novel=definitely_new,
                        state=referee_state,
                    )
                    if reward_tracker is not None:
                        reward, reward_components = reward_tracker.score(
                            visually_novel=definitely_new,
                            state=referee_state,
                            action_button=action.button,
                        )
                        if (
                            policy is not None
                            and selected_bucket is not None
                            and selected_action_index is not None
                        ):
                            next_policy_state = (
                                referee_state if config.mode == "conventional" else None
                            )
                            policy.observe_transition(
                                selected_bucket,
                                selected_action_index,
                                reward,
                                policy_state_key(
                                    policy_visual_key(pixels),
                                    next_policy_state,
                                ),
                                rng,
                            )
                        semantic_components = {
                            name: value
                            for name, value in reward_components.items()
                            if name != "visual_novelty"
                        }
                        if semantic_components:
                            significant_components = {
                                name: value
                                for name, value in semantic_components.items()
                                if name
                                not in {
                                    "new_position",
                                    "repeated_action",
                                    "revisited_position",
                                    "stationary_loop",
                                }
                            }
                            event_capture: dict[str, Any] | None = None
                            if significant_components:
                                event_slug = "-".join(sorted(significant_components))
                                event_filename = (
                                    f"screenshots/event-{counters.total_actions:010d}-{event_slug}.png"
                                )
                                _save_png(pixels, output / event_filename)
                                event_capture = {
                                    "file": event_filename,
                                    "label": "Milestone: "
                                    + ", ".join(sorted(significant_components)),
                                    "action": counters.total_actions,
                                    "unique_visual_cells": counters.unique_visual_cells,
                                    "capture_type": "reward_event",
                                    "elapsed_seconds": round(counters.elapsed_seconds, 3),
                                }
                                screenshots.append(event_capture)
                            trace.write(
                                "reward_event",
                                action=counters.total_actions,
                                elapsed_seconds=round(counters.elapsed_seconds, 3),
                                components=semantic_components,
                                cumulative_reward=round(reward_tracker.total_reward, 3),
                                referee_state=(
                                    None
                                    if referee_state is None
                                    else referee_state.public_dict()
                                ),
                                exact_event_visual=(
                                    None if event_capture is None else event_capture["file"]
                                ),
                            )
                    current_pixels = pixels

                    existing = archive.find(key) if config.mode in ARCHIVE_MODES else None
                    if existing is not None:
                        existing.visits += 1
                    elif (
                        config.mode in ARCHIVE_MODES
                        and definitely_new
                        and len(archive) < config.max_archive_cells
                    ):
                        frozen = FrozenSnapshot.freeze(emulator.save_state())
                        cell = archive.add(
                            key=key,
                            snapshot=frozen,
                            parent_id=current_parent_id,
                            actions_from_parent=tuple(pending_actions),
                            discovered_action=counters.total_actions,
                        )
                        counters.archive_additions += 1
                        current_parent_id = cell.cell_id
                        pending_actions = []

                    if definitely_new and _should_capture(
                        counters.unique_visual_cells,
                        sum(
                            shot.get("capture_type") in {None, "power_on", "discovery"}
                            for shot in screenshots
                        ),
                        config.screenshot_limit,
                    ):
                        filename = f"screenshots/discovery-{counters.unique_visual_cells:08d}.png"
                        _save_png(pixels, output / filename)
                        capture = {
                            "file": filename,
                            "label": f"Visual cell {counters.unique_visual_cells:,}",
                            "action": counters.total_actions,
                            "unique_visual_cells": counters.unique_visual_cells,
                            "capture_type": "discovery",
                            "elapsed_seconds": round(counters.elapsed_seconds, 3),
                        }
                        screenshots.append(capture)
                        trace.write("visual_milestone", **capture)

                    now = monotonic()
                    counters.elapsed_seconds = base_elapsed + (now - segment_start)
                    if (
                        timelapse_captures < config.timelapse_limit
                        and counters.elapsed_seconds - last_timelapse_elapsed
                        >= config.timelapse_interval_seconds
                    ):
                        filename = f"screenshots/timelapse-{int(counters.elapsed_seconds):09d}.png"
                        _save_png(pixels, output / filename)
                        capture = {
                            "file": filename,
                            "label": f"Time-lapse at {int(counters.elapsed_seconds // 60):,} min",
                            "action": counters.total_actions,
                            "unique_visual_cells": counters.unique_visual_cells,
                            "capture_type": "timelapse",
                            "elapsed_seconds": round(counters.elapsed_seconds, 3),
                        }
                        screenshots.append(capture)
                        trace.write("timelapse", **capture)
                        timelapse_captures += 1
                        last_timelapse_elapsed = counters.elapsed_seconds
                    if now - last_status >= config.status_interval_seconds:
                        _save_png(pixels, output / "latest.png")
                        run_bytes = _directory_size(output)
                        free_bytes = shutil.disk_usage(output).free
                        status_history.append(
                            {
                                "elapsed_seconds": round(counters.elapsed_seconds, 3),
                                "total_actions": counters.total_actions,
                                "unique_visual_cells": counters.unique_visual_cells,
                                "archive_cells": len(archive),
                                "maps_seen": len(referee_tracker.seen_maps),
                                "positions_seen": len(referee_tracker.seen_positions),
                                "pokedex_seen": len(referee_tracker.seen_pokedex_species),
                                "pokedex_owned": len(referee_tracker.owned_pokedex_species),
                                "max_party_level": referee_tracker.max_party_level,
                                "reward_total": (
                                    0.0 if reward_tracker is None else reward_tracker.total_reward
                                ),
                            }
                        )
                        status_history = status_history[-20_000:]
                        status = _status_payload(
                            mode=config.mode,
                            state="running",
                            stop_reason=None,
                            counters=counters,
                            archive=archive,
                            config=config,
                            started_at=started_at,
                            run_bytes=run_bytes,
                            policy=policy,
                            reward_tracker=reward_tracker,
                            referee_tracker=referee_tracker,
                            referee_state=referee_state,
                        )
                        _atomic_json(output / "status.json", status)
                        _write_dashboard(output, status, status_history, screenshots)
                        trace.write(
                            "status",
                            elapsed_seconds=status["elapsed_seconds"],
                            total_actions=status["total_actions"],
                            unique_visual_cells=status["unique_visual_cells"],
                            archive_cells=status["archive_cells"],
                            novelty_rate=status["novelty_rate"],
                            run_bytes=run_bytes,
                            free_bytes=free_bytes,
                            reward_total=status["reward_total"],
                            outcome_reward=status["outcome_reward"],
                            maps_seen=status["maps_seen"],
                            positions_seen=status["positions_seen"],
                            warps_seen=status["warps_seen"],
                            max_party_count=status["max_party_count"],
                            max_party_level=status["max_party_level"],
                            pokedex_seen=status["pokedex_seen"],
                            pokedex_owned=status["pokedex_owned"],
                            event_flags_seen=status["event_flags_seen"],
                            blackouts=status["blackouts"],
                            badge_count=status["badge_count"],
                            replay_transitions=status["replay_transitions"],
                            replay_updates=status["replay_updates"],
                        )
                        last_status = now
                        if run_bytes >= config.max_output_bytes:
                            stop_reason = "output_limit"
                            break
                        if free_bytes <= config.min_free_bytes:
                            stop_reason = "low_disk_space"
                            break

                    if now - last_checkpoint >= config.checkpoint_interval_seconds:
                        current_snapshot = FrozenSnapshot.freeze(emulator.save_state())
                        payload = _checkpoint_payload(
                            config=config,
                            rom=rom,
                            counters=counters,
                            rng=rng,
                            seen=seen,
                            archive=archive,
                            current_snapshot=current_snapshot,
                            current_parent_id=current_parent_id,
                            pending_actions=pending_actions,
                            branch_remaining=branch_remaining,
                            history=status_history,
                            screenshots=screenshots,
                            policy=policy,
                            reward_tracker=reward_tracker,
                            referee_tracker=referee_tracker,
                            conventional_bootstrap_index=conventional_bootstrap_index,
                            source_identity=source_identity,
                            implementation_sha256=implementation_sha256,
                            trace_offset=trace.position(),
                        )
                        _write_checkpoint(checkpoint_path, payload)
                        trace.write(
                            "checkpoint",
                            action=counters.total_actions,
                            elapsed_seconds=round(counters.elapsed_seconds, 3),
                            archive_cells=len(archive),
                        )
                        last_checkpoint = now

                counters.elapsed_seconds = base_elapsed + (monotonic() - segment_start)
                status_history.append(
                    {
                        "elapsed_seconds": round(counters.elapsed_seconds, 3),
                        "total_actions": counters.total_actions,
                        "unique_visual_cells": counters.unique_visual_cells,
                        "archive_cells": len(archive),
                    }
                )
                status_history = status_history[-20_000:]
                current_snapshot = FrozenSnapshot.freeze(emulator.save_state())
                final_checkpoint = _checkpoint_payload(
                    config=config,
                    rom=rom,
                    counters=counters,
                    rng=rng,
                    seen=seen,
                    archive=archive,
                    current_snapshot=current_snapshot,
                    current_parent_id=current_parent_id,
                    pending_actions=pending_actions,
                    branch_remaining=branch_remaining,
                    history=status_history,
                    screenshots=screenshots,
                    policy=policy,
                    reward_tracker=reward_tracker,
                    referee_tracker=referee_tracker,
                    conventional_bootstrap_index=conventional_bootstrap_index,
                    source_identity=source_identity,
                    implementation_sha256=implementation_sha256,
                    trace_offset=trace.position(),
                )
                _write_checkpoint(checkpoint_path, final_checkpoint)
                pixels = actor.observe()
                _save_png(pixels, output / "latest.png")
                run_bytes = _directory_size(output)
                final_status = _status_payload(
                    mode=config.mode,
                    state="finished",
                    stop_reason=stop_reason,
                    counters=counters,
                    archive=archive,
                    config=config,
                    started_at=started_at,
                    run_bytes=run_bytes,
                    policy=policy,
                    reward_tracker=reward_tracker,
                    referee_tracker=referee_tracker,
                    referee_state=referee_state,
                )
                _atomic_json(output / "status.json", final_status)
                _write_dashboard(output, final_status, status_history, screenshots)
                trace.write(
                    "result",
                    stop_reason=stop_reason,
                    elapsed_seconds=round(counters.elapsed_seconds, 3),
                    total_actions=counters.total_actions,
                    unique_visual_cells=counters.unique_visual_cells,
                    archive_cells=len(archive),
                    archive_restores=counters.archive_restores,
                    max_action_depth=archive.max_depth if config.mode == "archivist" else 0,
                    reward_total=(
                        0.0 if reward_tracker is None else round(reward_tracker.total_reward, 3)
                    ),
                )
                return BlindRunResult(output, stop_reason, counters, len(archive))
    except Exception as error:
        failure_reason = f"error:{type(error).__name__}"
        with contextlib.suppress(Exception):
            trace.write(
                "failure",
                failed_at=datetime.now(UTC).isoformat(),
                error_type=type(error).__name__,
                last_checkpoint=(
                    checkpoint_path.name if checkpoint_path.is_file() else "unavailable"
                ),
            )
        with contextlib.suppress(Exception):
            run_bytes = _directory_size(output)
            failure_status = _status_payload(
                mode=config.mode,
                state="failed",
                stop_reason=failure_reason,
                counters=counters,
                archive=archive,
                config=config,
                started_at=started_at,
                run_bytes=run_bytes,
                policy=policy,
                reward_tracker=reward_tracker,
                referee_tracker=referee_tracker,
                referee_state=referee_state,
            )
            _atomic_json(output / "status.json", failure_status)
            if (output / "latest.png").is_file():
                _write_dashboard(output, failure_status, status_history, screenshots)
        raise
    finally:
        trace.close()
