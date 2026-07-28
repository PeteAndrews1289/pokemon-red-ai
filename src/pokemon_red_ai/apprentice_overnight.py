from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import os
import platform
import random
import resource
import shutil
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np

from pokemon_red_ai.apprentice_data import (
    PREVIOUS_ACTION_SENTINEL,
    ApprenticeDataset,
    load_apprentice_dataset,
    preprocess_apprentice_frame,
    verify_apprentice_dataset,
)
from pokemon_red_ai.apprentice_model import require_torch
from pokemon_red_ai.apprentice_stage0 import load_stage0_model
from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    PixelsOnlyActor,
)
from pokemon_red_ai.emulator import EmulatorSnapshot, PokemonRedEmulator
from pokemon_red_ai.expedition import MilestoneProgress, milestone_progress_for_state
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import verify_rom
from pokemon_red_ai.state import PokemonRedStateReader

OVERNIGHT_PROTOCOL = "visual-apprentice-reverse-curriculum-dev-v1"
CHECKPOINT_SCHEMA = 1
DEFAULT_RUNG_HORIZONS = (8, 16, 32, 64, 128, 256, 419)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: object) -> None:
    _atomic_bytes(path, _canonical_json(value) + b"\n")


def _append_json(path: Path, value: object) -> None:
    with path.open("ab") as output:
        output.write(_canonical_json(value) + b"\n")
        output.flush()
        os.fsync(output.fileno())


def _maximum_rss_mib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        value *= 1024
    return value / (1024 * 1024)


def _parameter_sha256(model: Any) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous().numpy()
        descriptor = _canonical_json(
            {"name": name, "dtype": value.dtype.str, "shape": list(value.shape)}
        )
        digest.update(len(descriptor).to_bytes(8, "big"))
        digest.update(descriptor)
        digest.update(value.tobytes())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class OvernightApprenticeConfig:
    """Boundaries for one development-only reverse-curriculum run."""

    seed: int = 20_260_743
    max_seconds: float = 8 * 60 * 60
    max_emulator_actions: int = 15_000_000
    max_actions_without_promotion: int = 2_000_000
    max_rss_mib: float = 1_536
    minimum_free_gib: float = 50
    torch_threads: int = 4
    learning_rate: float = 2e-4
    gradient_clip: float = 1.0
    success_loss_weight: float = 0.5
    temperature: float = 1.0
    exploration_epsilon: float = 0.02
    rollout_multiplier: float = 2.0
    rollout_slack: int = 16
    demo_bootstrap_updates: int = 20
    promotion_window: int = 30
    promotion_required: int = 27
    promotion_confirmations: int = 2
    checkpoint_interval_episodes: int = 10
    status_interval_actions: int = 25
    rung_horizons: tuple[int, ...] = DEFAULT_RUNG_HORIZONS
    dashboard_port: int | None = None

    def __post_init__(self) -> None:
        if (
            self.seed < 0
            or self.max_seconds <= 0
            or self.max_emulator_actions < 1
            or self.max_actions_without_promotion < 1
        ):
            raise ValueError("Seed and run limits must be valid and positive")
        if self.max_rss_mib <= 0 or self.minimum_free_gib < 0:
            raise ValueError("Memory and disk boundaries must be valid")
        if not 1 <= self.torch_threads <= 4:
            raise ValueError("The overnight learner supports one to four Torch threads")
        if not 0 < self.learning_rate <= 0.1 or self.gradient_clip <= 0:
            raise ValueError("Training hyperparameters are outside their safe range")
        if self.success_loss_weight < 0:
            raise ValueError("Success loss weight cannot be negative")
        if self.temperature <= 0 or not 0 <= self.exploration_epsilon <= 1:
            raise ValueError("Sampling configuration is invalid")
        if self.rollout_multiplier < 1 or self.rollout_slack < 0:
            raise ValueError("Rollout budget must cover the demonstrated suffix")
        if self.demo_bootstrap_updates < 0:
            raise ValueError("Demo bootstrap updates cannot be negative")
        if not 1 <= self.promotion_required <= self.promotion_window:
            raise ValueError("Promotion requires a valid successes-per-window threshold")
        if self.promotion_confirmations < 1:
            raise ValueError("Promotion confirmation count must be positive")
        if self.checkpoint_interval_episodes < 1 or self.status_interval_actions < 1:
            raise ValueError("Checkpoint and status intervals must be positive")
        if (
            not self.rung_horizons
            or tuple(sorted(set(self.rung_horizons))) != self.rung_horizons
            or self.rung_horizons[-1] != 419
            or self.rung_horizons[0] < 1
        ):
            raise ValueError("Curriculum horizons must be unique, ascending, and end at 419")
        if self.dashboard_port is not None and not 1 <= self.dashboard_port <= 65_535:
            raise ValueError("Dashboard port is invalid")

    def public_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["rung_horizons"] = list(self.rung_horizons)
        return {"protocol": OVERNIGHT_PROTOCOL, **value}

    @classmethod
    def canary(cls, *, dashboard_port: int | None = None) -> OvernightApprenticeConfig:
        """A short plumbing check; its relaxed gate is never qualification evidence."""

        return cls(
            max_seconds=3 * 60,
            max_emulator_actions=20_000,
            max_actions_without_promotion=20_000,
            minimum_free_gib=50,
            torch_threads=1,
            demo_bootstrap_updates=2,
            promotion_window=3,
            promotion_required=2,
            promotion_confirmations=1,
            checkpoint_interval_episodes=1,
            dashboard_port=dashboard_port,
        )


@dataclass(slots=True)
class PromotionGate:
    """Two non-overlapping adaptive promotion windows; 27/30 twice by default."""

    window_size: int
    required_successes: int
    required_confirmations: int
    current: list[bool] = field(default_factory=list)
    consecutive_confirmations: int = 0
    completed_windows: int = 0

    def record(self, success: bool) -> tuple[bool, dict[str, int | bool] | None]:
        self.current.append(bool(success))
        if len(self.current) < self.window_size:
            return False, None
        successes = sum(self.current)
        passed = successes >= self.required_successes
        self.consecutive_confirmations = (
            self.consecutive_confirmations + 1 if passed else 0
        )
        self.completed_windows += 1
        evidence: dict[str, int | bool] = {
            "window": self.completed_windows,
            "attempts": self.window_size,
            "successes": successes,
            "required_successes": self.required_successes,
            "passed": passed,
            "consecutive_confirmations": self.consecutive_confirmations,
        }
        self.current.clear()
        return self.consecutive_confirmations >= self.required_confirmations, evidence

    def public_dict(self) -> dict[str, object]:
        return {
            "window_size": self.window_size,
            "required_successes": self.required_successes,
            "required_confirmations": self.required_confirmations,
            "current": list(self.current),
            "consecutive_confirmations": self.consecutive_confirmations,
            "completed_windows": self.completed_windows,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PromotionGate:
        return cls(
            window_size=int(value["window_size"]),
            required_successes=int(value["required_successes"]),
            required_confirmations=int(value["required_confirmations"]),
            current=[bool(item) for item in value.get("current", [])],
            consecutive_confirmations=int(value.get("consecutive_confirmations", 0)),
            completed_windows=int(value.get("completed_windows", 0)),
        )


@dataclass(frozen=True, slots=True)
class CurriculumRung:
    index: int
    remaining_actions: int
    start_action: int
    rollout_limit: int


def build_curriculum_rungs(
    action_count: int, config: OvernightApprenticeConfig
) -> tuple[CurriculumRung, ...]:
    if action_count != config.rung_horizons[-1]:
        raise ValueError("Dataset length does not match the curriculum terminal horizon")
    return tuple(
        CurriculumRung(
            index=index,
            remaining_actions=horizon,
            start_action=action_count - horizon,
            rollout_limit=max(
                horizon,
                int(round(horizon * config.rollout_multiplier)) + config.rollout_slack,
            ),
        )
        for index, horizon in enumerate(config.rung_horizons)
    )


def build_suffix_arrays(
    dataset: ApprenticeDataset, start_action: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return a demonstrated suffix with reset visual/action/recurrent history."""

    action_count = int(dataset.actions.shape[0])
    if not 0 <= start_action < action_count:
        raise ValueError("Suffix start is outside the demonstration")
    frames = np.asarray(dataset.frames[start_action:action_count], dtype=np.uint8)
    previous_frames = np.concatenate((frames[:1], frames[:-1]), axis=0)
    pairs = np.stack((previous_frames, frames), axis=1)
    targets = np.asarray(dataset.actions[start_action:], dtype=np.int64)
    previous = np.empty(targets.shape, dtype=np.int64)
    previous[0] = PREVIOUS_ACTION_SENTINEL
    previous[1:] = targets[:-1]
    return pairs, previous, targets


@dataclass(slots=True)
class _RunState:
    created_epoch: float
    rung_index: int = 0
    episodes: int = 0
    successes: int = 0
    updates: int = 0
    demo_updates: int = 0
    self_imitation_updates: int = 0
    emulator_actions: int = 0
    checkpoint_replay_actions: int = 0
    evaluation_actions: int = 0
    actions_at_last_promotion: int = 0
    bootstrapped_rungs: list[int] = field(default_factory=list)
    gate: PromotionGate | None = None

    def public_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["gate"] = None if self.gate is None else self.gate.public_dict()
        return value


@dataclass(frozen=True, slots=True)
class OvernightRunResult:
    output_directory: Path
    state: str
    stop_reason: str
    elapsed_seconds: float
    episodes: int
    successes: int
    updates: int
    emulator_actions: int
    highest_completed_horizon: int
    current_horizon: int | None
    model_parameter_sha256: str


@dataclass(frozen=True, slots=True)
class _LadderEntry:
    rung: CurriculumRung
    snapshot: EmulatorSnapshot
    frame: np.ndarray = field(repr=False)


@dataclass(frozen=True, slots=True)
class _Rollout:
    success: bool
    stop_reason: str
    action_count: int
    final_milestone: str
    action_sha256: str
    frame_pairs: np.ndarray | None = field(repr=False)
    previous_actions: np.ndarray | None = field(repr=False)
    actions: np.ndarray | None = field(repr=False)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def _dashboard_html() -> bytes:
    html = (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width">'
        "<title>Visual Apprentice Overnight</title><style>"
        ":root{color-scheme:dark;font-family:ui-monospace,monospace}"
        "body{max-width:1000px;margin:32px auto;padding:0 20px;background:#0b1020;color:#eef}"
        "h1{font-family:system-ui}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}"
        ".card{background:#17213a;border:1px solid #344469;border-radius:12px;padding:16px}"
        ".v{font-size:1.6rem;color:#75e6bd}.wide{grid-column:1/-1}"
        "@media(max-width:700px){.grid{grid-template-columns:1fr}}</style></head><body>"
        "<h1>Visual Apprentice: overnight curriculum</h1>"
        "<p>A development run. Pixels act; RAM only judges the declared boundary.</p>"
        "<div class=grid><div class=card>STATE<div class=v id=state>loading</div></div>"
        "<div class=card>RUNG<div class=v id=rung>-</div></div>"
        "<div class=card>ELAPSED<div class=v id=elapsed>-</div></div>"
        "<div class=card>EPISODES<div class=v id=episodes>-</div></div>"
        "<div class=card>SUCCESSES<div class=v id=successes>-</div></div>"
        "<div class=card>DEMO PRIMING<div class=v id=demo_updates>-</div></div>"
        "<div class=card>LEARNER UPDATES<div class=v id=self_imitation_updates>-</div></div>"
        '<div class="card wide">PROMOTION WINDOW<div class=v id=window>-</div>'
        "<p id=note>This development run makes no generalization claim.</p></div></div>"
        "<script>async function r(){try{"
        "const s=await(await fetch('status.json?'+Date.now())).json();"
        "for(const k of ['state','episodes','successes','demo_updates','self_imitation_updates'])"
        "document.getElementById(k).textContent=s[k]??'-';"
        "document.getElementById('rung').textContent=s.current_horizon?"
        "`${s.current_horizon} actions remaining`:'complete';"
        "document.getElementById('elapsed').textContent="
        "((s.elapsed_seconds??0)/3600).toFixed(2)+' h';"
        "document.getElementById('window').textContent="
        "`${s.window_successes??0}/${s.window_attempts??0}; confirmations "
        "${s.confirmations??0}/${s.required_confirmations??2}`;"
        "document.getElementById('note').textContent=s.note??"
        "document.getElementById('note').textContent}catch(e){}}"
        "r();setInterval(r,2000)</script></body></html>"
    )
    return html.encode("utf-8")


class OvernightApprenticeRunner:
    """One emulator, one pixels-only learner, and a trainer-owned checkpoint ladder."""

    def __init__(
        self,
        rom_path: Path,
        dataset_path: Path,
        stage0_model_directory: Path,
        output_path: Path,
        *,
        config: OvernightApprenticeConfig | None = None,
        resume: bool = False,
    ) -> None:
        self.rom_path = rom_path.expanduser().resolve()
        self.dataset_path = dataset_path.expanduser().resolve()
        self.model_directory = stage0_model_directory.expanduser().resolve()
        self.output = output_path.expanduser().resolve()
        self.config = config or OvernightApprenticeConfig()
        self.resume = resume
        self.torch = require_torch()
        self.dataset: ApprenticeDataset | None = None
        self.model: Any = None
        self.optimizer: Any = None
        self.state: _RunState | None = None
        self.rungs: tuple[CurriculumRung, ...] = ()
        self.random = random.Random(self.config.seed)
        self.torch_generator = self.torch.Generator(device="cpu")
        self.torch_generator.manual_seed(self.config.seed)
        self._http_server: ThreadingHTTPServer | None = None

    @property
    def _events_path(self) -> Path:
        return self.output / "events.jsonl"

    def _event(self, kind: str, **fields: object) -> None:
        _append_json(
            self._events_path,
            {"timestamp": datetime.now(UTC).isoformat(), "kind": kind, **fields},
        )

    def _elapsed(self) -> float:
        assert self.state is not None
        return max(0.0, time.time() - self.state.created_epoch)

    def _limit_reason(self) -> str | None:
        assert self.state is not None
        if (self.output / "STOP").exists():
            return "stop_marker"
        if self._elapsed() >= self.config.max_seconds:
            return "time_limit"
        if self.state.emulator_actions >= self.config.max_emulator_actions:
            return "action_limit"
        if (
            self.state.emulator_actions - self.state.actions_at_last_promotion
            >= self.config.max_actions_without_promotion
        ):
            return "stagnation_action_limit"
        if _maximum_rss_mib() >= self.config.max_rss_mib:
            return "rss_limit"
        free_gib = shutil.disk_usage(self.output).free / (1024**3)
        if free_gib < self.config.minimum_free_gib:
            return "disk_free_limit"
        return None

    def _status(self, state_name: str, *, note: str, stop_reason: str | None = None) -> None:
        assert self.state is not None
        rung = (
            self.rungs[self.state.rung_index]
            if self.state.rung_index < len(self.rungs)
            else None
        )
        gate = self.state.gate
        _atomic_json(
            self.output / "status.json",
            {
                "schema_version": 1,
                "protocol": OVERNIGHT_PROTOCOL,
                "updated_at": datetime.now(UTC).isoformat(),
                "state": state_name,
                "process_id": os.getpid(),
                "stop_reason": stop_reason,
                "elapsed_seconds": self._elapsed(),
                "max_seconds": self.config.max_seconds,
                "rung_index": self.state.rung_index,
                "current_horizon": None if rung is None else rung.remaining_actions,
                "episodes": self.state.episodes,
                "successes": self.state.successes,
                "updates": self.state.updates,
                "demo_updates": self.state.demo_updates,
                "self_imitation_updates": self.state.self_imitation_updates,
                "emulator_actions": self.state.emulator_actions,
                "actions_per_second": self.state.emulator_actions / max(self._elapsed(), 1e-9),
                "success_rate": self.state.successes / max(self.state.episodes, 1),
                "max_emulator_actions": self.config.max_emulator_actions,
                "actions_since_promotion": (
                    self.state.emulator_actions - self.state.actions_at_last_promotion
                ),
                "max_actions_without_promotion": self.config.max_actions_without_promotion,
                "window_attempts": 0 if gate is None else len(gate.current),
                "window_successes": 0 if gate is None else sum(gate.current),
                "confirmations": 0 if gate is None else gate.consecutive_confirmations,
                "required_confirmations": self.config.promotion_confirmations,
                "maximum_rss_mib": _maximum_rss_mib(),
                "free_disk_gib": shutil.disk_usage(self.output).free / (1024**3),
                "note": note,
            },
        )

    def _start_dashboard(self) -> None:
        if self.config.dashboard_port is None:
            return
        handler = functools.partial(_QuietHandler, directory=str(self.output))
        self._http_server = ThreadingHTTPServer(
            ("127.0.0.1", self.config.dashboard_port), handler
        )
        thread = threading.Thread(target=self._http_server.serve_forever, daemon=True)
        thread.start()

    def _configure_torch(self) -> None:
        self.torch.manual_seed(self.config.seed)
        self.torch.set_num_threads(self.config.torch_threads)
        with contextlib.suppress(RuntimeError):
            self.torch.set_num_interop_threads(1)
        self.torch.use_deterministic_algorithms(True)

    def _prepare(self) -> None:
        source = detect_source_provenance()
        if source.git_commit is None or source.worktree_dirty is not False:
            raise ValueError("Overnight runs require a committed, clean implementation")
        dataset_manifest = verify_apprentice_dataset(self.dataset_path)
        self.dataset = load_apprentice_dataset(self.dataset_path)
        self.rungs = build_curriculum_rungs(int(self.dataset.actions.shape[0]), self.config)
        rom = verify_rom(self.rom_path)
        self._configure_torch()
        self.model, model_metadata = load_stage0_model(self.model_directory)
        self.model.to("cpu")
        self.optimizer = self.torch.optim.Adam(
            self.model.parameters(), lr=self.config.learning_rate
        )
        dataset_sha = str(dataset_manifest["dataset_sha256"])
        if model_metadata.get("dataset_sha256") != dataset_sha:
            raise ValueError("Overnight dataset does not match the sealed Stage-0 model")
        identity = {
            "dataset_sha256": dataset_sha,
            "base_model_sha256": str(model_metadata["model_sha256"]),
            "source": source.public_dict(),
            "rom": rom.public_dict(),
            "runtime": {
                "python": platform.python_version(),
                "pyboy": version("pyboy"),
                "torch": str(self.torch.__version__),
            },
            "configuration": self.config.public_dict(),
        }
        if self.resume:
            if not self.output.is_dir():
                raise ValueError("Resume output directory does not exist")
            manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("identity") != identity:
                raise ValueError("Resume identity differs from the original run")
            self._load_checkpoint()
            self._event("run_resumed", checkpoint_episode=self.state.episodes)
        else:
            if self.output.exists():
                raise ValueError("Overnight output directory already exists")
            self.output.mkdir(parents=True)
            (self.output / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
            self._events_path.touch()
            _atomic_bytes(self.output / "index.html", _dashboard_html())
            self.state = _RunState(
                created_epoch=time.time(),
                gate=PromotionGate(
                    self.config.promotion_window,
                    self.config.promotion_required,
                    self.config.promotion_confirmations,
                ),
            )
            _atomic_json(
                self.output / "manifest.json",
                {
                    "schema_version": 1,
                    "protocol": OVERNIGHT_PROTOCOL,
                    "created_at": datetime.now(UTC).isoformat(),
                    "identity": identity,
                    "claim_boundary": (
                        "development-only reverse curriculum; checkpoint resets and trainer RAM "
                        "referee; no generalization or clean-power-on completion claim"
                    ),
                    "actor_inputs": [
                        "two_processed_pixel_frames",
                        "previous_action",
                        "recurrent_state",
                    ],
                    "actor_forbidden_inputs": [
                        "ram",
                        "checkpoint_identity",
                        "route_position",
                        "milestone",
                    ],
                    "trainer_only": ["emulator_snapshots", "RAM milestone referee"],
                },
            )
            self._event("run_started", identity=identity)
            self._save_checkpoint()

    def _save_checkpoint(self) -> None:
        assert self.state is not None and self.model is not None and self.optimizer is not None
        payload = {
            "schema_version": CHECKPOINT_SCHEMA,
            "protocol": OVERNIGHT_PROTOCOL,
            "state": self.state.public_dict(),
            "model_state": self.model.state_dict(),
            "optimizer_state": self.optimizer.state_dict(),
            "python_random_state": self.random.getstate(),
            "torch_generator_state": self.torch_generator.get_state(),
        }
        path = self.output / "checkpoint.pt"
        temporary = self.output / f".checkpoint.pt.tmp-{os.getpid()}"
        self.torch.save(payload, temporary)
        with temporary.open("rb") as source:
            os.fsync(source.fileno())
        os.replace(temporary, path)
        _atomic_json(
            self.output / "checkpoint.json",
            {
                "schema_version": CHECKPOINT_SCHEMA,
                "protocol": OVERNIGHT_PROTOCOL,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
                "episode": self.state.episodes,
                "rung_index": self.state.rung_index,
                "saved_at": datetime.now(UTC).isoformat(),
            },
        )

    def _load_checkpoint(self) -> None:
        receipt = json.loads((self.output / "checkpoint.json").read_text(encoding="utf-8"))
        path = self.output / "checkpoint.pt"
        if (
            receipt.get("schema_version") != CHECKPOINT_SCHEMA
            or receipt.get("protocol") != OVERNIGHT_PROTOCOL
            or receipt.get("sha256") != _sha256_file(path)
            or receipt.get("bytes") != path.stat().st_size
        ):
            raise ValueError("Overnight checkpoint receipt does not match its payload")
        payload = self.torch.load(path, map_location="cpu", weights_only=False)
        if payload.get("schema_version") != CHECKPOINT_SCHEMA or payload.get(
            "protocol"
        ) != OVERNIGHT_PROTOCOL:
            raise ValueError("Overnight checkpoint protocol is invalid")
        raw = payload["state"]
        gate_raw = raw.get("gate")
        self.state = _RunState(
            created_epoch=float(raw["created_epoch"]),
            rung_index=int(raw["rung_index"]),
            episodes=int(raw["episodes"]),
            successes=int(raw["successes"]),
            updates=int(raw["updates"]),
            demo_updates=int(raw.get("demo_updates", 0)),
            self_imitation_updates=int(raw.get("self_imitation_updates", 0)),
            emulator_actions=int(raw["emulator_actions"]),
            checkpoint_replay_actions=int(raw["checkpoint_replay_actions"]),
            evaluation_actions=int(raw["evaluation_actions"]),
            actions_at_last_promotion=int(raw.get("actions_at_last_promotion", 0)),
            bootstrapped_rungs=[int(item) for item in raw["bootstrapped_rungs"]],
            gate=None if gate_raw is None else PromotionGate.from_dict(gate_raw),
        )
        self.model.load_state_dict(payload["model_state"], strict=True)
        self.optimizer.load_state_dict(payload["optimizer_state"])
        self.random.setstate(payload["python_random_state"])
        self.torch_generator.set_state(payload["torch_generator_state"])

    def _execute_action(self, actor: PixelsOnlyActor, action_index: int) -> bool:
        assert self.state is not None
        action = BlindAction(
            BLIND_ACTIONS[action_index], ACTION_HOLD_FRAMES, ACTION_RELEASE_FRAMES
        )
        alive = actor.act(action)
        self.state.emulator_actions += 1
        return alive

    def _build_ladder(self, emulator: PokemonRedEmulator) -> tuple[_LadderEntry, ...]:
        assert self.dataset is not None and self.state is not None
        starts = {rung.start_action: rung for rung in self.rungs}
        entries: dict[int, _LadderEntry] = {}
        actor = PixelsOnlyActor(emulator)
        for action_index in range(int(self.dataset.actions.shape[0]) + 1):
            if action_index in starts:
                frame = preprocess_apprentice_frame(actor.observe())
                expected = np.asarray(self.dataset.frames[action_index], dtype=np.uint8)
                if not np.array_equal(frame, expected):
                    raise RuntimeError("Checkpoint replay pixels differ from the certified demo")
                entries[action_index] = _LadderEntry(
                    starts[action_index], emulator.save_state(), frame
                )
            if action_index == int(self.dataset.actions.shape[0]):
                break
            reason = self._limit_reason()
            if reason is not None:
                raise RuntimeError(f"Run boundary reached while rebuilding ladder: {reason}")
            if not self._execute_action(actor, int(self.dataset.actions[action_index])):
                raise RuntimeError("Emulator stopped while rebuilding the certified route")
            self.state.checkpoint_replay_actions += 1
        reader = PokemonRedStateReader(emulator)
        progress = milestone_progress_for_state(reader.read())
        if progress.key != "left_home" or len(entries) != len(self.rungs):
            raise RuntimeError("Certified route did not reconstruct the complete ladder")
        self._event(
            "ladder_reconstructed",
            checkpoints=len(entries),
            replay_actions=int(self.dataset.actions.shape[0]),
        )
        return tuple(entries[rung.start_action] for rung in self.rungs)

    def _train_update(
        self,
        rung: CurriculumRung,
        *,
        successful_rollout: _Rollout | None,
        kind: str,
    ) -> float:
        assert self.dataset is not None and self.model is not None and self.optimizer is not None
        demo_pairs, demo_previous, demo_targets = build_suffix_arrays(
            self.dataset, rung.start_action
        )
        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)
        logits, _ = self.model(
            self.torch.from_numpy(demo_pairs).unsqueeze(0),
            self.torch.from_numpy(demo_previous).unsqueeze(0),
        )
        loss = self.torch.nn.functional.cross_entropy(
            logits[0], self.torch.from_numpy(demo_targets)
        )
        success_steps = 0
        if successful_rollout is not None:
            if not successful_rollout.success or successful_rollout.frame_pairs is None:
                raise ValueError("Only successful learner trajectories may enter an update")
            success_logits, _ = self.model(
                self.torch.from_numpy(successful_rollout.frame_pairs).unsqueeze(0),
                self.torch.from_numpy(successful_rollout.previous_actions).unsqueeze(0),
            )
            success_targets = self.torch.from_numpy(successful_rollout.actions)
            success_loss = self.torch.nn.functional.cross_entropy(
                success_logits[0], success_targets
            )
            loss = loss + self.config.success_loss_weight * success_loss
            success_steps = int(success_targets.shape[0])
        loss.backward()
        self.torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.gradient_clip)
        self.optimizer.step()
        self.state.updates += 1
        if kind == "demo_bootstrap":
            self.state.demo_updates += 1
        elif kind == "successful_self_imitation":
            self.state.self_imitation_updates += 1
        else:
            raise ValueError(f"Unknown curriculum update kind: {kind}")
        loss_value = float(loss.detach().item())
        _append_json(
            self.output / "updates.jsonl",
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "update": self.state.updates,
                "kind": kind,
                "rung_index": rung.index,
                "remaining_actions": rung.remaining_actions,
                "demo_steps": int(demo_targets.shape[0]),
                "successful_rollout_steps": success_steps,
                "loss": loss_value,
                "parameter_sha256": _parameter_sha256(self.model),
            },
        )
        return loss_value

    def _select_action(self, logits: Any) -> int:
        if self.random.random() < self.config.exploration_epsilon:
            return self.random.randrange(len(BLIND_ACTIONS))
        probabilities = self.torch.softmax(logits[0] / self.config.temperature, dim=-1)
        return int(
            self.torch.multinomial(
                probabilities, 1, generator=self.torch_generator
            ).item()
        )

    def _rollout(
        self,
        emulator: PokemonRedEmulator,
        entry: _LadderEntry,
        *,
        deterministic: bool,
    ) -> _Rollout:
        emulator.load_state(entry.snapshot)
        actor = PixelsOnlyActor(emulator)
        reader = PokemonRedStateReader(emulator)
        current = preprocess_apprentice_frame(actor.observe())
        if not np.array_equal(current, entry.frame):
            raise RuntimeError("Restored checkpoint pixels changed")
        previous_frame = current
        previous_action = PREVIOUS_ACTION_SENTINEL
        recurrent_state = None
        pairs: list[np.ndarray] = []
        priors: list[int] = []
        actions: list[int] = []
        progress = MilestoneProgress("power_on", 0, "Power-on")
        stop_reason = "rollout_limit"
        self.model.eval()
        for _ in range(entry.rung.rollout_limit):
            reason = self._limit_reason()
            if reason is not None:
                stop_reason = reason
                break
            pair = np.stack((previous_frame, current), axis=0).astype(np.uint8, copy=False)
            with self.torch.no_grad():
                logits, recurrent_state = self.model.step(
                    self.torch.from_numpy(pair).unsqueeze(0),
                    self.torch.tensor([previous_action], dtype=self.torch.long),
                    recurrent_state,
                )
            action_index = (
                int(logits.argmax(dim=-1).item())
                if deterministic
                else self._select_action(logits)
            )
            pairs.append(pair.copy())
            priors.append(previous_action)
            actions.append(action_index)
            alive = self._execute_action(actor, action_index)
            state = reader.read()
            progress = milestone_progress_for_state(state, inherited=progress)
            previous_frame = current
            current = preprocess_apprentice_frame(actor.observe())
            previous_action = action_index
            if progress.key == "left_home":
                stop_reason = "left_home_reached"
                break
            if not alive:
                stop_reason = "emulator_stopped"
                break
            if len(actions) % self.config.status_interval_actions == 0:
                self._status(
                    "running",
                    note=f"Episode {self.state.episodes + 1} is still executing.",
                )
        action_array = np.asarray(actions, dtype=np.int64)
        success = stop_reason == "left_home_reached"
        return _Rollout(
            success=success,
            stop_reason=stop_reason,
            action_count=len(actions),
            final_milestone=progress.key,
            action_sha256=hashlib.sha256(action_array.astype(np.uint8).tobytes()).hexdigest(),
            frame_pairs=(np.asarray(pairs, dtype=np.uint8) if success else None),
            previous_actions=(np.asarray(priors, dtype=np.int64) if success else None),
            actions=(action_array if success else None),
        )

    def _record_evaluation(self, phase: str, entry: _LadderEntry, result: _Rollout) -> None:
        assert self.state is not None
        self.state.evaluation_actions += result.action_count
        _append_json(
            self.output / "evaluations.jsonl",
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "phase": phase,
                "rung_index": entry.rung.index,
                "remaining_actions": entry.rung.remaining_actions,
                "success": result.success,
                "actions": result.action_count,
                "stop_reason": result.stop_reason,
                "final_milestone": result.final_milestone,
                "action_sha256": result.action_sha256,
                "updates": False,
                "policy": "deterministic_argmax",
            },
        )

    def _activate_rung(self, emulator: PokemonRedEmulator, entry: _LadderEntry) -> None:
        assert self.state is not None
        if entry.rung.index in self.state.bootstrapped_rungs:
            return
        baseline = self._rollout(emulator, entry, deterministic=True)
        self._record_evaluation("baseline_before_demo_bootstrap", entry, baseline)
        for number in range(1, self.config.demo_bootstrap_updates + 1):
            if self._limit_reason() is not None:
                break
            loss = self._train_update(entry.rung, successful_rollout=None, kind="demo_bootstrap")
            self._status(
                "running",
                note=(
                    f"Preparing {entry.rung.remaining_actions}-action rung: "
                    f"demo update {number}/{self.config.demo_bootstrap_updates}, loss {loss:.4f}."
                ),
            )
        self.state.bootstrapped_rungs.append(entry.rung.index)
        post = self._rollout(emulator, entry, deterministic=True)
        self._record_evaluation("after_demo_bootstrap", entry, post)
        self._event(
            "rung_activated",
            rung_index=entry.rung.index,
            remaining_actions=entry.rung.remaining_actions,
            baseline_success=baseline.success,
            post_bootstrap_success=post.success,
        )
        self._save_checkpoint()

    def _save_final_model(self) -> str:
        path = self.output / "learner.pt"
        temporary = self.output / f".learner.pt.tmp-{os.getpid()}"
        self.torch.save(self.model.state_dict(), temporary)
        os.replace(temporary, path)
        parameter_sha = _parameter_sha256(self.model)
        _atomic_json(
            self.output / "learner.json",
            {
                "schema_version": 1,
                "protocol": OVERNIGHT_PROTOCOL,
                "file_sha256": _sha256_file(path),
                "parameter_sha256": parameter_sha,
                "updates": self.state.updates,
                "development_only": True,
            },
        )
        return parameter_sha

    def run(self) -> OvernightRunResult:
        stop_reason = "unknown"
        run_state_name = "stopped"
        ladder: tuple[_LadderEntry, ...] = ()
        try:
            self._prepare()
            assert self.state is not None
            self._start_dashboard()
            self._status("starting", note="Reconstructing seven trainer-owned checkpoints.")
            with PokemonRedEmulator(self.rom_path) as emulator:
                ladder = self._build_ladder(emulator)
                self._save_checkpoint()
                while self.state.rung_index < len(ladder):
                    reason = self._limit_reason()
                    if reason is not None:
                        stop_reason = reason
                        break
                    entry = ladder[self.state.rung_index]
                    self._activate_rung(emulator, entry)
                    reason = self._limit_reason()
                    if reason is not None:
                        stop_reason = reason
                        break
                    result = self._rollout(emulator, entry, deterministic=False)
                    if result.stop_reason in {
                        "time_limit",
                        "action_limit",
                        "rss_limit",
                        "disk_free_limit",
                        "stop_marker",
                        "stagnation_action_limit",
                    }:
                        stop_reason = result.stop_reason
                        break
                    self.state.episodes += 1
                    if result.success:
                        self.state.successes += 1
                        self._train_update(
                            entry.rung,
                            successful_rollout=result,
                            kind="successful_self_imitation",
                        )
                    _append_json(
                        self.output / "episodes.jsonl",
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "episode": self.state.episodes,
                            "sampling_seed": self.config.seed,
                            "rung_index": entry.rung.index,
                            "remaining_actions": entry.rung.remaining_actions,
                            "success": result.success,
                            "actions": result.action_count,
                            "stop_reason": result.stop_reason,
                            "final_milestone": result.final_milestone,
                            "action_sha256": result.action_sha256,
                            "gradient_update": result.success,
                        },
                    )
                    promoted, window = self.state.gate.record(result.success)
                    if window is not None:
                        self._event(
                            "promotion_window_completed",
                            rung_index=entry.rung.index,
                            remaining_actions=entry.rung.remaining_actions,
                            **window,
                        )
                    if promoted:
                        completed = entry.rung
                        self.state.rung_index += 1
                        self.state.actions_at_last_promotion = self.state.emulator_actions
                        self.state.gate = PromotionGate(
                            self.config.promotion_window,
                            self.config.promotion_required,
                            self.config.promotion_confirmations,
                        )
                        self._event(
                            "rung_promoted",
                            rung_index=completed.index,
                            remaining_actions=completed.remaining_actions,
                            episodes=self.state.episodes,
                        )
                        self._save_checkpoint()
                    self._status(
                        "running",
                        note=(
                            "Success was rehearsed with the fixed demo."
                            if result.success
                            else "Failure was logged but did not enter a gradient update."
                        ),
                    )
                    if self.state.episodes % self.config.checkpoint_interval_episodes == 0:
                        self._save_checkpoint()
                else:
                    stop_reason = "curriculum_complete"
                    run_state_name = "completed"

                if (
                    ladder
                    and self.state.rung_index < len(ladder)
                    and self._limit_reason() is None
                ):
                    final_eval = self._rollout(
                        emulator, ladder[self.state.rung_index], deterministic=True
                    )
                    self._record_evaluation(
                        "final_at_stop", ladder[self.state.rung_index], final_eval
                    )
            self._save_checkpoint()
        except Exception as error:
            stop_reason = f"error:{type(error).__name__}"
            run_state_name = "failed"
            if self.state is not None and self.output.exists():
                self._event("run_failed", error_type=type(error).__name__, message=str(error))
                self._status("failed", note=str(error), stop_reason=stop_reason)
                with contextlib.suppress(Exception):
                    self._save_checkpoint()
            raise
        finally:
            if self._http_server is not None:
                self._http_server.shutdown()
                self._http_server.server_close()

        assert self.state is not None
        parameter_sha = self._save_final_model()
        completed_index = min(self.state.rung_index - 1, len(self.rungs) - 1)
        highest = 0 if completed_index < 0 else self.rungs[completed_index].remaining_actions
        current = (
            None
            if self.state.rung_index >= len(self.rungs)
            else self.rungs[self.state.rung_index].remaining_actions
        )
        summary = {
            "schema_version": 1,
            "protocol": OVERNIGHT_PROTOCOL,
            "state": run_state_name,
            "stop_reason": stop_reason,
            "elapsed_seconds": self._elapsed(),
            "episodes": self.state.episodes,
            "successes": self.state.successes,
            "updates": self.state.updates,
            "demo_updates": self.state.demo_updates,
            "self_imitation_updates": self.state.self_imitation_updates,
            "emulator_actions": self.state.emulator_actions,
            "checkpoint_replay_actions": self.state.checkpoint_replay_actions,
            "evaluation_actions": self.state.evaluation_actions,
            "highest_completed_horizon": highest,
            "current_horizon": current,
            "model_parameter_sha256": parameter_sha,
            "claim_boundary": (
                "development checkpoint curriculum only; not evidence of recovery, "
                "generalization, clean-power-on progress, or game completion"
            ),
        }
        _atomic_json(self.output / "summary.json", summary)
        self._event("run_finished", **summary)
        self._status(run_state_name, note=summary["claim_boundary"], stop_reason=stop_reason)
        return OvernightRunResult(
            output_directory=self.output,
            state=run_state_name,
            stop_reason=stop_reason,
            elapsed_seconds=self._elapsed(),
            episodes=self.state.episodes,
            successes=self.state.successes,
            updates=self.state.updates,
            emulator_actions=self.state.emulator_actions,
            highest_completed_horizon=highest,
            current_horizon=current,
            model_parameter_sha256=parameter_sha,
        )


def run_overnight_apprentice(
    rom_path: Path,
    dataset_path: Path,
    stage0_model_directory: Path,
    output_path: Path,
    *,
    config: OvernightApprenticeConfig | None = None,
    resume: bool = False,
) -> OvernightRunResult:
    """Launch the bounded learner through a stable, CLI-independent Python API."""

    return OvernightApprenticeRunner(
        rom_path,
        dataset_path,
        stage0_model_directory,
        output_path,
        config=config,
        resume=resume,
    ).run()
