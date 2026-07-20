from __future__ import annotations

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
    MilestoneProgress,
    descriptor_from_state,
    milestone_progress_for_state,
    referee_summary_for_state,
    replay_frontier_cell,
)
from pokemon_red_ai.milestones import HALL_OF_FAME_KEY, MILESTONES, MilestoneTracker
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import RomFingerprint
from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader

EXPEDITION_RUNNER_PROTOCOL_VERSION = "checkpoint-expedition-runner-v1"
EXPEDITION_RUNNER_CHECKPOINT_SCHEMA = 1
POWER_ON_PROGRESS = MilestoneProgress("power_on", 0, "Power-on")


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

    def public_dict(self) -> dict[str, int | float | bool]:
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
    loop_stops: int = 0
    emulator_stops: int = 0
    replay_attempts: int = 0
    replay_actions: int = 0
    replay_passes: int = 0
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
            "loop_stops",
            "emulator_stops",
            "replay_attempts",
            "replay_actions",
            "replay_passes",
        )
        integers = {name: int(value.get(name, 0)) for name in names}
        if any(item < 0 for item in integers.values()):
            raise ValueError("Expedition counters cannot be negative")
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
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            with gzip.open(candidate, "rt", encoding="utf-8") as source:
                value = json.load(source)
            if int(value.get("schema_version", -1)) != EXPEDITION_RUNNER_CHECKPOINT_SCHEMA:
                raise ValueError("Unsupported expedition runner checkpoint schema")
            if value.get("protocol_version") != EXPEDITION_RUNNER_PROTOCOL_VERSION:
                raise ValueError("Expedition runner checkpoint uses a different protocol")
            return candidate, value
        except (OSError, EOFError, json.JSONDecodeError, ValueError) as error:
            failures.append(error)
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

    return {item: item.stat().st_size for item in path.rglob("*") if item.is_file()}


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
            raise RuntimeError(
                f"Expedition already has a live coordinator (PID {owner})"
            ) from None
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
        "schema_version": 1,
        "protocol_version": EXPEDITION_RUNNER_PROTOCOL_VERSION,
        "store_protocol_version": EXPEDITION_PROTOCOL_VERSION,
        "run_name": "Checkpoint Expedition — blind suffixes, privileged referee",
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
        "loop_stops": counters.loop_stops,
        "emulator_stops": counters.emulator_stops,
        "replay_attempts": counters.replay_attempts,
        "replay_actions": counters.replay_actions,
        "replay_passes": counters.replay_passes,
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
            "action_emitter": SeededRandomSequenceEmitter.policy_id,
            "action_emitter_inputs": ["seeded_prng"],
            "loop_detector_inputs": ["rendered_rgb"],
            "referee_inputs": ["documented_read_only_ram"],
            "archive_selection_inputs": ["referee_milestones", "frontier_descriptor"],
            "ram_used_by_actor": False,
            "ram_used_by_referee": True,
            "snapshots_visible_to_actor": False,
            "human_demonstrations": [],
            "pretrained_components": [],
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
<div class="eyebrow">RANDOM DISCOVERY BASELINE · NOT A LEARNED MODEL · {state}</div>
<h1>Evolution is allowed<br/>to remember.</h1>
<p class="lede">A seeded-random actor emits buttons without RAM or milestone access. A sealed
referee may recognize progress and choose restorable stepping stones. Named promotions must replay
their complete input lineage from power-on.</p>
<section class="grid"><article class="card">
<img src="latest.png?v={updated}" alt="Latest rendered Game Boy frame" />
<div class="stats"><div><span>Exploration actions</span>
<strong>{int(status.get('total_actions', 0)):,}</strong></div>
<div><span>Attempts</span><strong>{int(status.get('attempts', 0)):,}</strong></div>
<div><span>Active / stored cells</span>
<strong>{int(status.get('archive_cells', 0)):,} /
{int(status.get('stored_evidence_cells', 0)):,}</strong></div>
<div><span>Loop stops</span><strong>{int(status.get('loop_stops', 0)):,}</strong></div>
<div><span>Replay passes</span><strong>{int(status.get('replay_passes', 0)):,} /
{int(status.get('replay_attempts', 0)):,}</strong></div>
<div><span>Stop reason</span><strong>{reason}</strong></div></div></article>
<article class="card"><span>Best verified frontier</span>
<div class="milestone">{html.escape(str(best.get('label', 'Clean power-on')))}</div>
<div class="attempt">{html.escape(current_label)}</div>
<table><thead><tr><th>Milestone</th><th>Map</th><th>Depth</th><th>Selections</th></tr></thead>
<tbody>{rows}</tbody></table></article></section>
<div class="contract"><strong>Information boundary:</strong> buttons come only from a seeded PRNG.
The loop detector sees rendered pixels. RAM is read only by the referee, and checkpoints never enter
the actor. This is checkpoint-assisted discovery, not a continuous learned-policy completion.</div>
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
) -> dict[str, Any]:
    return {
        "schema_version": EXPEDITION_RUNNER_CHECKPOINT_SCHEMA,
        "protocol_version": EXPEDITION_RUNNER_PROTOCOL_VERSION,
        "store_protocol_version": EXPEDITION_PROTOCOL_VERSION,
        "config": config.public_dict(),
        "rom_sha256": rom.sha256,
        "source": dict(source),
        "implementation_sha256": implementation_sha256,
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
) -> ExpeditionRunResult:
    """Run a bounded checkpoint expedition; never pass referee state into the actor."""

    output = run_directory.expanduser().resolve()
    _validate_output_path(output)
    store_path = output / "frontier"
    trace_path = output / "trace.jsonl"
    checkpoint_path = output / "checkpoint.json.gz"
    stop_marker = output / "STOP"
    source = detect_source_provenance().public_dict()
    implementation = _implementation_sha256()
    run_config_sha256 = hashlib.sha256(
        _canonical_json(config.public_dict()).encode("utf-8")
    ).hexdigest()
    store_metadata = {
        "runner_protocol_version": EXPEDITION_RUNNER_PROTOCOL_VERSION,
        "actor": SeededRandomSequenceEmitter.policy_id,
        "actor_receives_ram": False,
        "referee_receives_ram": True,
        "run_config_sha256": run_config_sha256,
        "seed": config.seed,
        "implementation_sha256": implementation,
        "source": source,
    }
    checkpoint: dict[str, Any] | None = None

    if resume:
        if not output.is_dir():
            raise ValueError("Expedition resume requires an existing run directory")
        _checkpoint_used, checkpoint = _read_checkpoint(checkpoint_path)
        if checkpoint.get("config") != config.public_dict():
            raise ValueError("Expedition resume configuration does not match")
        if checkpoint.get("rom_sha256") != rom.sha256:
            raise ValueError("Expedition checkpoint belongs to a different ROM")
        if checkpoint.get("source") != source:
            raise ValueError("Expedition checkpoint source provenance does not match")
        if checkpoint.get("implementation_sha256") != implementation:
            raise ValueError("Expedition implementation changed since the checkpoint")
        previous_status = json.loads((output / "status.json").read_text(encoding="utf-8"))
        if previous_status.get("stop_reason") in {
            "action_limit",
            "duration_limit",
            "hall_of_fame_verified",
        }:
            raise ValueError("This expedition already reached a terminal budget or completion")
        _truncate_trace(trace_path, int(checkpoint["trace_offset"]))
        stop_marker.unlink(missing_ok=True)
        store = ExpeditionStore.open(store_path)
        if dict(store.manifest.get("metadata", {})) != store_metadata:
            raise ValueError("Expedition store provenance does not match this runner")
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "milestones").mkdir()
        store = ExpeditionStore.create(
            store_path,
            rom_sha256=rom.sha256,
            pyboy_version=version("pyboy"),
            metadata=store_metadata,
        )

    rng = random.Random(config.seed)
    counters = ExpeditionCounters()
    attempts_by_parent: dict[str, int] = {}
    reached_milestones: set[str] = set()
    best_progress = POWER_ON_PROGRESS
    completion_cell_id: str | None = None
    started_at = datetime.now(UTC).isoformat()
    base_elapsed = 0.0

    if checkpoint is not None:
        counters = ExpeditionCounters.from_checkpoint_dict(checkpoint["counters"])
        base_elapsed = counters.elapsed_seconds
        rng.setstate(_json_tuple(checkpoint["rng_state"]))
        attempts_by_parent = {
            str(cell_id): int(count)
            for cell_id, count in checkpoint.get("attempts_by_parent", {}).items()
        }
        if any(
            cell_id not in store.cells or count < 0
            for cell_id, count in attempts_by_parent.items()
        ):
            raise ValueError("Expedition checkpoint attempt counters are invalid")
        progress_value = checkpoint["best_progress"]
        best_progress = MilestoneProgress(
            str(progress_value["key"]),
            int(progress_value["index"]),
            str(progress_value["label"]),
        )
        reached_milestones = {str(key) for key in checkpoint.get("reached_milestones", [])}
        completion_cell_id = checkpoint.get("completion_cell_id")
        started_at = str(checkpoint["started_at"])
        archive = FrontierArchive.from_checkpoint_dict(store, checkpoint["archive"])
        if archive.capacity != config.archive_capacity:
            raise ValueError("Expedition checkpoint archive capacity does not match")
        if not any(cell.parent_id is None for cell in archive.active_cells):
            raise ValueError("Expedition checkpoint lost its power-on root")
    else:
        archive = FrontierArchive(store, config.archive_capacity)

    manifest = {
        "kind": "manifest",
        "schema_version": 1,
        "protocol_version": EXPEDITION_RUNNER_PROTOCOL_VERSION,
        "store_protocol_version": EXPEDITION_PROTOCOL_VERSION,
        "created_at": started_at,
        "rom": rom.public_dict(),
        "config": config.public_dict(),
        "actor": {
            "name": SeededRandomSequenceEmitter.policy_id,
            "inputs": ["seeded_prng"],
            "ram": False,
            "snapshots": False,
        },
        "trainer": {
            "loop_inputs": ["rendered_rgb"],
            "referee_inputs": ["documented_read_only_ram"],
            "checkpoint_restore": True,
            "writer_model": "single_process_coordinator",
        },
        "human_demonstrations": [],
        "pretrained_components": [],
        "source": source,
        "implementation_sha256": implementation,
        "run_config_sha256": run_config_sha256,
        "private_rom_path_recorded": False,
    }
    if not resume:
        _atomic_json(output / "manifest.json", manifest)
        _append_json(trace_path, manifest)
    else:
        _append_json(
            trace_path,
            {
                "kind": "run_resumed",
                "recorded_at": datetime.now(UTC).isoformat(),
                "checkpoint_total_actions": counters.total_actions,
                "checkpoint_attempts": counters.attempts,
                "checkpoint_archive_cells": len(archive.active_cells),
            },
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
    latest_pixels: np.ndarray | None = None
    latest_state: PokemonRedState | None = None
    current_attempt: dict[str, Any] | None = None
    start_clock = monotonic()
    last_status = 0.0
    emitter = SeededRandomSequenceEmitter(rng)

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

    def write_status(state: str, reason: str | None) -> None:
        nonlocal latest_pixels
        if latest_pixels is None:
            return
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
        )
        _write_live_artifacts(output, status, latest_pixels)
        disk_monitor.observe_files(
            output / "latest.png",
            output / "status.json",
            output / "index.html",
        )

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

    writer_lock = _acquire_single_writer(output)
    disk_monitor.observe_files(writer_lock)
    dashboard_server: ThreadingHTTPServer | None = None
    dashboard_thread: threading.Thread | None = None
    try:
        if config.dashboard_port:
            dashboard_server, dashboard_thread = _start_dashboard_server(
                output,
                config.dashboard_port,
            )
        with _SignalStop() as stopper, PokemonRedEmulator(rom_path) as emulator:
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
                counters.replay_actions += root_replay.action_count
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
                anchor = parent
                verified_progress = _progress_for_cell(parent)
                segment_actions: list[BlindAction] = []
                attempt_reason = "suffix_budget"
                current_attempt = {
                    "number": counters.attempts,
                    "parent_id": parent.cell_id,
                    "selection_channel": channel,
                    "budget": suffix_budget,
                    "actions": 0,
                    "adaptive_selection_count": selection_count,
                    "starting_milestone": verified_progress.key,
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

                    if capture_frontier and (
                        descriptor.key not in archive.active_by_key or milestone_advanced
                    ):
                        before_cells = len(store.cells)
                        cell = store.add_cell(
                            parent_id=anchor.cell_id,
                            snapshot=FrozenSnapshot.freeze(emulator.save_state()),
                            actions_from_parent=tuple(segment_actions),
                            descriptor=descriptor,
                            screen_sha256=hashlib.sha256(latest_pixels.tobytes()).hexdigest(),
                            discovered_global_action=counters.total_actions,
                            referee_summary=_referee_summary(
                                latest_state,
                                candidate_progress,
                                parent=anchor,
                                tracker=tracker,
                            ),
                            policy_id=emitter.policy_id,
                        )
                        if len(store.cells) > before_cells:
                            counters.cells_created += 1
                        decision = archive.consider(cell)
                        observe_cell_files(cell)
                        replay_passed = not decision.reason.startswith("quarantined_replay_")
                        if decision.reason.startswith("quarantined_replay_"):
                            replay_passed = True
                            required_replays = store.required_replay_count(cell.cell_id)
                            if milestone_advanced:
                                required_replays = max(
                                    required_replays,
                                    config.promotion_replay_passes,
                                )
                            completed_replays = store.successful_replay_count(cell.cell_id)
                            semantic_evaluator = None
                        if milestone_advanced and config.verify_milestone_replays:
                            milestone = MILESTONES[candidate_progress.index - 1]

                            def semantic_evaluator(
                                replay_state: PokemonRedState,
                                _pixels: np.ndarray,
                                target: Any = milestone,
                            ) -> bool:
                                return bool(target.reached_by(replay_state))

                        if decision.reason.startswith("quarantined_replay_"):
                            for replay_number in range(
                                completed_replays + 1,
                                required_replays + 1,
                            ):
                                replay = replay_frontier_cell(
                                    rom_path,
                                    store,
                                    cell.cell_id,
                                    evaluator=semantic_evaluator,
                                )
                                counters.replay_attempts += 1
                                counters.replay_actions += replay.action_count
                                counters.replay_passes += int(replay.passed)
                                disk_monitor.observe_files(store.path / "events.jsonl")
                                if not replay.passed:
                                    replay_passed = False
                                    store.audit(
                                        "frontier_verification_failed",
                                        cell_id=cell.cell_id,
                                        milestone_id=candidate_progress.key,
                                        replay_number=replay_number,
                                        reason=replay.failure_reason,
                                        semantic_predicate=(
                                            candidate_progress.key
                                            if milestone_advanced
                                            else "canonical_lineage_progress"
                                        ),
                                    )
                                    disk_monitor.observe_files(store.path / "events.jsonl")
                                    break
                            if replay_passed:
                                decision = archive.consider(cell)
                                disk_monitor.observe_files(store.path / "events.jsonl")

                        if replay_passed:
                            if decision.admitted:
                                counters.cells_admitted += 1
                                anchor = cell
                                segment_actions.clear()
                                verified_progress = candidate_progress
                                if verified_progress.index > best_progress.index:
                                    best_progress = verified_progress
                                    filename = (
                                        f"{verified_progress.index:03d}-"
                                        f"{verified_progress.key}.png"
                                    )
                                    _save_png(latest_pixels, output / "milestones" / filename)
                                    disk_monitor.observe_files(
                                        output / "milestones" / filename
                                    )
                                if verified_progress.key == HALL_OF_FAME_KEY:
                                    completion_cell_id = cell.cell_id
                            else:
                                counters.cells_rejected += 1
                        else:
                            counters.cells_rejected += 1

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

                counters.elapsed_seconds = elapsed()
                _append_json(
                    trace_path,
                    {
                        "kind": "suffix_completed",
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "attempt": counters.attempts,
                        "parent_id": parent.cell_id,
                        "final_anchor_id": anchor.cell_id,
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
        _release_single_writer(writer_lock)

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
    print(f"Stop reason: {status.get('stop_reason') or 'still running'}")
    return 0 if status.get("state") != "failed" else 1


def request_expedition_stop(run_directory: Path) -> int:
    output = run_directory.expanduser().resolve()
    if not (output / "status.json").is_file():
        raise ValueError("Expedition status.json does not exist")
    (output / "STOP").touch(exist_ok=True)
    print("Graceful expedition stop requested; the current short suffix will checkpoint.")
    return 0
