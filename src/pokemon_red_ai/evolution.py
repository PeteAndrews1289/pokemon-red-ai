from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import json
import math
import os
import shutil
import signal
import zlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from types import FrameType
from typing import Any

import numpy as np
from PIL import Image

from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    FrozenSnapshot,
    PixelsOnlyActor,
    SeenVisualFilter,
    visual_key,
    visual_signature,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.learning import RewardTracker
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import RomFingerprint
from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader

EVOLUTION_PROTOCOL_VERSION = "pixels-recurrent-map-elites-v1"
EVOLUTION_CHECKPOINT_SCHEMA = 1
PIXEL_INPUTS = 18 * 20
PREVIOUS_ACTION_INPUTS = len(BLIND_ACTIONS)
HIDDEN_UNITS = 32
INPUT_UNITS = PIXEL_INPUTS + PREVIOUS_ACTION_INPUTS
OUTPUT_UNITS = len(BLIND_ACTIONS)


def _parameter_count() -> int:
    return (
        HIDDEN_UNITS * INPUT_UNITS
        + HIDDEN_UNITS * HIDDEN_UNITS
        + HIDDEN_UNITS
        + OUTPUT_UNITS * HIDDEN_UNITS
        + OUTPUT_UNITS
    )


PARAMETER_COUNT = _parameter_count()


@dataclass(frozen=True, slots=True)
class EvolutionConfig:
    duration_seconds: float = 7_200
    max_actions: int = 20_000_000
    seed: int = 20_260_723
    population_size: int = 16
    candidate_actions: int = 12_000
    archive_capacity: int = 512
    mutation_probability: float = 0.10
    mutation_sigma: float = 0.05
    large_mutation_probability: float = 0.05
    large_mutation_sigma: float = 0.20
    seen_filter_bytes: int = 8 * 1024 * 1024
    screenshot_limit: int = 128
    status_interval_seconds: float = 10
    checkpoint_interval_seconds: float = 300
    max_output_bytes: int = 2_048 * 1024 * 1024
    min_free_bytes: int = 50 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0 or self.max_actions < 1:
            raise ValueError("Evolution duration and total action budget must be positive")
        if self.population_size < 2 or self.candidate_actions < 1:
            raise ValueError("Evolution population and candidate action budget are invalid")
        if self.archive_capacity < 1:
            raise ValueError("Evolution archive capacity must be positive")
        for name, value in (
            ("mutation_probability", self.mutation_probability),
            ("large_mutation_probability", self.large_mutation_probability),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between zero and one")
        if self.mutation_sigma <= 0 or self.large_mutation_sigma <= 0:
            raise ValueError("Evolution mutation sigmas must be positive")
        if self.seen_filter_bytes < 1_024:
            raise ValueError("Evolution visual filter must be at least 1 KiB")
        if self.screenshot_limit < 1:
            raise ValueError("Evolution screenshot limit must be positive")
        if self.status_interval_seconds <= 0 or self.checkpoint_interval_seconds <= 0:
            raise ValueError("Evolution status and checkpoint intervals must be positive")
        if self.max_output_bytes < 1_048_576 or self.min_free_bytes < 0:
            raise ValueError("Evolution disk limits are invalid")

    def public_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvolutionGenome:
    parameters: np.ndarray = field(repr=False)

    def __post_init__(self) -> None:
        values = np.asarray(self.parameters, dtype=np.float32)
        if values.shape != (PARAMETER_COUNT,):
            raise ValueError(f"Evolution genome must contain {PARAMETER_COUNT:,} parameters")
        if not np.all(np.isfinite(values)):
            raise ValueError("Evolution genome contains non-finite parameters")
        values = values.copy()
        values.flags.writeable = False
        object.__setattr__(self, "parameters", values)

    @classmethod
    def random(cls, seed: int) -> EvolutionGenome:
        rng = np.random.default_rng(seed)
        pieces = (
            rng.normal(0, 1 / math.sqrt(INPUT_UNITS), HIDDEN_UNITS * INPUT_UNITS),
            rng.normal(0, 1 / math.sqrt(HIDDEN_UNITS), HIDDEN_UNITS * HIDDEN_UNITS),
            np.zeros(HIDDEN_UNITS),
            rng.normal(0, 1 / math.sqrt(HIDDEN_UNITS), OUTPUT_UNITS * HIDDEN_UNITS),
            np.zeros(OUTPUT_UNITS),
        )
        return cls(np.concatenate(pieces).astype(np.float32))

    @property
    def genome_id(self) -> str:
        digest = hashlib.sha256()
        digest.update(EVOLUTION_PROTOCOL_VERSION.encode("ascii"))
        digest.update(self.parameters.tobytes())
        return digest.hexdigest()[:16]

    def mutate(
        self,
        *,
        seed: int,
        probability: float,
        sigma: float,
    ) -> tuple[EvolutionGenome, int]:
        rng = np.random.default_rng(seed)
        mask = rng.random(PARAMETER_COUNT) < probability
        if not np.any(mask):
            mask[int(rng.integers(PARAMETER_COUNT))] = True
        child = self.parameters.copy()
        child[mask] += rng.normal(0, sigma, int(np.count_nonzero(mask))).astype(np.float32)
        np.clip(child, -5, 5, out=child)
        return EvolutionGenome(child), int(np.count_nonzero(mask))

    def checkpoint_dict(self) -> dict[str, Any]:
        compressed = zlib.compress(self.parameters.tobytes(), level=3)
        return {
            "schema_version": 1,
            "genome_id": self.genome_id,
            "parameter_count": PARAMETER_COUNT,
            "parameters_f32_zlib": base64.b64encode(compressed).decode("ascii"),
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any]) -> EvolutionGenome:
        if int(value.get("parameter_count", -1)) != PARAMETER_COUNT:
            raise ValueError("Evolution checkpoint uses a different network shape")
        raw = zlib.decompress(base64.b64decode(str(value["parameters_f32_zlib"])))
        parameters = np.frombuffer(raw, dtype=np.float32).copy()
        genome = cls(parameters)
        if value.get("genome_id") != genome.genome_id:
            raise ValueError("Evolution genome hash does not match its parameters")
        return genome


class RecurrentPixelPolicy:
    """A deterministic pixels-only policy; selection is never visible to this object."""

    def __init__(self, genome: EvolutionGenome, hidden: np.ndarray | None = None) -> None:
        self.genome = genome
        self.hidden = (
            np.zeros(HIDDEN_UNITS, dtype=np.float32)
            if hidden is None
            else np.asarray(hidden, dtype=np.float32).copy()
        )
        if self.hidden.shape != (HIDDEN_UNITS,) or not np.all(np.isfinite(self.hidden)):
            raise ValueError("Evolution recurrent state is invalid")
        values = genome.parameters
        offset = 0
        size = HIDDEN_UNITS * INPUT_UNITS
        self.input_weights = values[offset : offset + size].reshape(HIDDEN_UNITS, INPUT_UNITS)
        offset += size
        size = HIDDEN_UNITS * HIDDEN_UNITS
        self.recurrent_weights = values[offset : offset + size].reshape(
            HIDDEN_UNITS, HIDDEN_UNITS
        )
        offset += size
        self.hidden_bias = values[offset : offset + HIDDEN_UNITS]
        offset += HIDDEN_UNITS
        size = OUTPUT_UNITS * HIDDEN_UNITS
        self.output_weights = values[offset : offset + size].reshape(OUTPUT_UNITS, HIDDEN_UNITS)
        offset += size
        self.output_bias = values[offset : offset + OUTPUT_UNITS]

    def select(self, signature: bytes, previous_action: int | None) -> int:
        if len(signature) != PIXEL_INPUTS:
            raise ValueError("Evolution policy received the wrong pixel signature size")
        pixels = np.frombuffer(signature, dtype=np.uint8).astype(np.float32) / 7.0
        previous = np.zeros(PREVIOUS_ACTION_INPUTS, dtype=np.float32)
        if previous_action is not None:
            if not 0 <= previous_action < PREVIOUS_ACTION_INPUTS:
                raise ValueError("Evolution previous action is invalid")
            previous[previous_action] = 1
        inputs = np.concatenate((pixels, previous))
        self.hidden = np.tanh(
            self.input_weights @ inputs
            + self.recurrent_weights @ self.hidden
            + self.hidden_bias
        ).astype(np.float32)
        logits = self.output_weights @ self.hidden + self.output_bias
        return int(np.argmax(logits))


@dataclass(frozen=True, slots=True)
class EvolutionElite:
    genome: EvolutionGenome
    parent_id: str | None
    generation: int
    descriptor: tuple[int, ...]
    fitness: tuple[int, ...]
    metrics: dict[str, int]
    mutation_seed: int | None
    mutation_sigma: float
    mutated_parameters: int

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "genome": self.genome.checkpoint_dict(),
            "parent_id": self.parent_id,
            "generation": self.generation,
            "descriptor": list(self.descriptor),
            "fitness": list(self.fitness),
            "metrics": self.metrics,
            "mutation_seed": self.mutation_seed,
            "mutation_sigma": self.mutation_sigma,
            "mutated_parameters": self.mutated_parameters,
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any]) -> EvolutionElite:
        return cls(
            genome=EvolutionGenome.from_checkpoint_dict(value["genome"]),
            parent_id=value.get("parent_id"),
            generation=int(value["generation"]),
            descriptor=tuple(int(item) for item in value["descriptor"]),
            fitness=tuple(int(item) for item in value["fitness"]),
            metrics={str(key): int(item) for key, item in value["metrics"].items()},
            mutation_seed=(
                None if value.get("mutation_seed") is None else int(value["mutation_seed"])
            ),
            mutation_sigma=float(value.get("mutation_sigma", 0)),
            mutated_parameters=int(value.get("mutated_parameters", 0)),
        )


class QualityDiversityArchive:
    def __init__(self, capacity: int, elites: list[EvolutionElite] | None = None) -> None:
        self.capacity = capacity
        self._elites: dict[tuple[int, ...], EvolutionElite] = {}
        for elite in elites or []:
            if elite.descriptor in self._elites:
                raise ValueError("Evolution archive contains duplicate descriptors")
            self._elites[elite.descriptor] = elite
        if len(self._elites) > capacity:
            raise ValueError("Evolution archive exceeds its configured capacity")

    def __len__(self) -> int:
        return len(self._elites)

    @property
    def elites(self) -> list[EvolutionElite]:
        return [self._elites[key] for key in sorted(self._elites)]

    def consider(self, elite: EvolutionElite) -> tuple[bool, str | None]:
        existing = self._elites.get(elite.descriptor)
        if existing is not None and elite.fitness <= existing.fitness:
            return False, existing.genome.genome_id
        if existing is None and len(self._elites) >= self.capacity:
            return False, None
        replaced = None if existing is None else existing.genome.genome_id
        self._elites[elite.descriptor] = elite
        return True, replaced

    def select_parent(self, rng: np.random.Generator) -> EvolutionElite:
        values = self.elites
        if not values:
            raise RuntimeError("Cannot select a parent from an empty evolution archive")
        return values[int(rng.integers(len(values)))]

    def checkpoint_list(self) -> list[dict[str, Any]]:
        return [elite.checkpoint_dict() for elite in self.elites]


@dataclass(slots=True)
class EvolutionCounters:
    total_actions: int = 0
    total_frames: int = 0
    unique_visual_cells: int = 0
    evaluations: int = 0
    archive_insertions: int = 0
    archive_replacements: int = 0
    generation: int = 0
    candidate_index: int = 0
    candidate_actions: int = 0
    elapsed_seconds: float = 0

    def checkpoint_dict(self) -> dict[str, int | float]:
        return asdict(self)

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any]) -> EvolutionCounters:
        return cls(**{key: value[key] for key in cls.__dataclass_fields__})


@dataclass(frozen=True, slots=True)
class EvolutionRunResult:
    run_directory: Path
    stop_reason: str
    total_actions: int
    evaluations: int
    archive_cells: int


def _metrics(
    tracker: RewardTracker,
    final_state: PokemonRedState | None,
    action_counts: dict[str, int] | None = None,
) -> dict[str, int]:
    got_pokedex = bool(final_state and final_state.got_pokedex)
    badge_count = tracker.badge_bits.bit_count()
    counts = action_counts or {}
    used_actions = [index for index, action in enumerate(BLIND_ACTIONS) if counts.get(action, 0)]
    dominant_action = max(
        range(len(BLIND_ACTIONS)),
        key=lambda index: (counts.get(BLIND_ACTIONS[index], 0), -index),
    )
    diversity_bin = min(len(used_actions) // 3, 2)
    return {
        "game_started": int(tracker.game_started_seen),
        "maps_seen": len(tracker.seen_maps),
        "positions_seen": len(tracker.seen_positions),
        "warps_seen": len(tracker.seen_warps),
        "max_party_count": tracker.max_party_count,
        "max_party_level": tracker.max_party_level,
        "pokedex_seen": len(tracker.seen_pokedex_species),
        "pokedex_owned": len(tracker.owned_pokedex_species),
        "got_pokedex": int(got_pokedex),
        "event_flags_seen": len(tracker.seen_event_flags),
        "bag_items_seen": len(tracker.seen_bag_items),
        "moves_seen": len(tracker.seen_moves),
        "battle_kinds_seen": len(tracker.seen_battles & {1, 2}),
        "badges": badge_count,
        "blackouts": tracker.blackouts,
        "unique_actions": len(used_actions),
        "action_profile": dominant_action * 3 + diversity_bin,
    }


def _milestone_tier(metrics: dict[str, int]) -> int:
    if metrics["badges"]:
        return 6 + metrics["badges"]
    if metrics["pokedex_owned"] >= 2:
        return 5
    if metrics["got_pokedex"]:
        return 4
    if metrics["max_party_count"]:
        return 3
    if metrics["maps_seen"] >= 4:
        return 2
    return metrics["game_started"]


def behavior_descriptor(metrics: dict[str, int]) -> tuple[int, ...]:
    collection = 0
    if metrics["got_pokedex"]:
        collection = 1
    if metrics["pokedex_seen"] >= 2:
        collection = 2
    if metrics["pokedex_owned"] >= 2:
        collection = 3
    return (
        min(_milestone_tier(metrics), 15),
        min(metrics["maps_seen"], 7),
        collection,
        min(metrics["battle_kinds_seen"], 2),
        min(metrics.get("action_profile", 0), 23),
    )


def fitness_vector(metrics: dict[str, int], actions: int) -> tuple[int, ...]:
    return (
        _milestone_tier(metrics),
        metrics["badges"],
        metrics["event_flags_seen"],
        metrics["warps_seen"],
        metrics["pokedex_owned"],
        metrics["pokedex_seen"],
        min(metrics["maps_seen"], 32),
        min(metrics["positions_seen"], 2_000),
        metrics["max_party_level"],
        -metrics["blackouts"],
        -actions,
    )


def _best_metrics(archive: QualityDiversityArchive, current: dict[str, int]) -> dict[str, int]:
    result = dict(current)
    for elite in archive.elites:
        for key, value in elite.metrics.items():
            result[key] = max(result.get(key, 0), value)
    return result


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _save_png(pixels: np.ndarray, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    Image.fromarray(pixels).save(temporary, format="PNG", optimize=True)
    os.replace(temporary, path)


def _append_json(path: Path, value: dict[str, Any]) -> int:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
        return output.tell()


def _write_checkpoint(path: Path, value: dict[str, Any]) -> None:
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


def _read_checkpoint(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        value = json.load(source)
    if int(value.get("schema_version", -1)) != EVOLUTION_CHECKPOINT_SCHEMA:
        raise ValueError("Unsupported evolution checkpoint schema")
    if value.get("protocol_version") != EVOLUTION_PROTOCOL_VERSION:
        raise ValueError("Evolution checkpoint uses a different protocol")
    return value


def _implementation_sha256() -> str:
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in ("evolution.py", "evolution_report.py", "blind.py", "learning.py", "state.py"):
        digest.update(name.encode("utf-8"))
        digest.update((package / name).read_bytes())
    return digest.hexdigest()


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


class _SignalStop:
    def __init__(self) -> None:
        self.reason: str | None = None

    def handler(self, event: int, _frame: FrameType | None) -> None:
        self.reason = "sigint" if event == signal.SIGINT else "sigterm"


def _new_candidate(
    counters: EvolutionCounters,
    archive: QualityDiversityArchive,
    rng: np.random.Generator,
    config: EvolutionConfig,
) -> tuple[EvolutionGenome, str | None, int | None, float, int]:
    seed = int(rng.integers(0, np.iinfo(np.int64).max))
    if counters.generation == 0:
        return EvolutionGenome.random(seed), None, seed, 0.0, PARAMETER_COUNT
    parent = archive.select_parent(rng)
    large = bool(rng.random() < config.large_mutation_probability)
    sigma = config.large_mutation_sigma if large else config.mutation_sigma
    genome, changed = parent.genome.mutate(
        seed=seed,
        probability=config.mutation_probability,
        sigma=sigma,
    )
    return genome, parent.genome.genome_id, seed, sigma, changed


def _status_payload(
    *,
    state: str,
    stop_reason: str | None,
    started_at: str,
    counters: EvolutionCounters,
    config: EvolutionConfig,
    archive: QualityDiversityArchive,
    genome: EvolutionGenome,
    parent_id: str | None,
    mutation_seed: int | None,
    mutation_sigma: float,
    mutated_parameters: int,
    tracker: RewardTracker,
    candidate_action_counts: dict[str, int],
    referee_state: PokemonRedState | None,
    run_bytes: int,
) -> dict[str, Any]:
    current = _metrics(tracker, referee_state, candidate_action_counts)
    progress = _best_metrics(archive, current)
    best_fitness = max((elite.fitness for elite in archive.elites), default=())
    return {
        "schema_version": 1,
        "protocol_version": EVOLUTION_PROTOCOL_VERSION,
        "run_name": "Evolutionary Explorer — recurrent pixel-policy population",
        "run_class": "development",
        "mode": "evolution",
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
        "actions_per_second": round(
            counters.total_actions / counters.elapsed_seconds if counters.elapsed_seconds else 0,
            2,
        ),
        "generation": counters.generation,
        "candidate_index": counters.candidate_index,
        "population_size": config.population_size,
        "candidate_actions": counters.candidate_actions,
        "candidate_action_budget": config.candidate_actions,
        "evaluations": counters.evaluations,
        "learning_updates": counters.evaluations,
        "archive_cells": len(archive),
        "archive_capacity": archive.capacity,
        "archive_insertions": counters.archive_insertions,
        "archive_replacements": counters.archive_replacements,
        "current_genome_id": genome.genome_id,
        "current_parent_id": parent_id,
        "mutation_seed": mutation_seed,
        "mutation_sigma": mutation_sigma,
        "mutated_parameters": mutated_parameters,
        "parameter_count": PARAMETER_COUNT,
        "best_fitness": list(best_fitness),
        "fitness_tier": 0 if not best_fitness else best_fitness[0],
        "reward_total": 0,
        "unique_visual_cells": counters.unique_visual_cells,
        "maps_seen": progress.get("maps_seen", 0),
        "positions_seen": progress.get("positions_seen", 0),
        "warps_seen": progress.get("warps_seen", 0),
        "max_party_count": progress.get("max_party_count", 0),
        "max_party_level": progress.get("max_party_level", 0),
        "pokedex_seen": progress.get("pokedex_seen", 0),
        "pokedex_owned": progress.get("pokedex_owned", 0),
        "event_flags_seen": progress.get("event_flags_seen", 0),
        "bag_items_seen": progress.get("bag_items_seen", 0),
        "moves_seen": progress.get("moves_seen", 0),
        "blackouts": progress.get("blackouts", 0),
        "badge_count": progress.get("badges", 0),
        "replay_transitions": 0,
        "important_replay_transitions": 0,
        "ram_used_by_actor": False,
        "ram_used_by_reward": False,
        "ram_used_by_selection": True,
        "ram_used_by_referee": True,
        "snapshot_assisted": False,
        "continuous_playthrough": False,
        "start_condition": "clean_power_on_for_every_candidate",
        "run_bytes": run_bytes,
        "max_output_bytes": config.max_output_bytes,
        "current_metrics": current,
        "candidate_action_counts": candidate_action_counts,
        "referee_state": None if referee_state is None else referee_state.public_dict(),
        "elites": [
            {
                "genome_id": elite.genome.genome_id,
                "parent_id": elite.parent_id,
                "generation": elite.generation,
                "descriptor": list(elite.descriptor),
                "fitness": list(elite.fitness),
                "metrics": elite.metrics,
            }
            for elite in sorted(archive.elites, key=lambda item: item.fitness, reverse=True)[:64]
        ],
    }


def _write_dashboard(
    output: Path,
    status: dict[str, Any],
    history: list[dict[str, Any]],
    genealogy: list[dict[str, Any]],
) -> None:
    from pokemon_red_ai.evolution_report import render_evolution_dashboard

    _atomic_text(output / "index.html", render_evolution_dashboard(status, history, genealogy))


def run_evolution_experiment(
    rom_path: Path,
    rom: RomFingerprint,
    *,
    config: EvolutionConfig,
    run_directory: Path,
    resume: bool = False,
) -> EvolutionRunResult:
    output = run_directory
    checkpoint_path = output / "checkpoint.json.gz"
    stop_marker = output / "STOP"
    source = detect_source_provenance().public_dict()
    implementation = _implementation_sha256()
    checkpoint: dict[str, Any] | None = None
    if resume:
        if not checkpoint_path.is_file():
            raise ValueError("Evolution resume requires an existing checkpoint")
        checkpoint = _read_checkpoint(checkpoint_path)
        if checkpoint["config"] != config.public_dict():
            raise ValueError("Evolution resume configuration does not match")
        if checkpoint["rom_sha256"] != rom.sha256:
            raise ValueError("Evolution checkpoint belongs to a different ROM")
        if checkpoint["source"] != source or checkpoint["implementation_sha256"] != implementation:
            raise ValueError("Evolution checkpoint source does not match this implementation")
        stop_marker.unlink(missing_ok=True)
        for name, key in (("trace.jsonl", "trace_offset"), ("genealogy.jsonl", "genealogy_offset")):
            path = output / name
            with path.open("r+b") as stream:
                stream.truncate(int(checkpoint[key]))
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "screenshots").mkdir()

    started_at = datetime.now(UTC).isoformat()
    trace_path = output / "trace.jsonl"
    genealogy_path = output / "genealogy.jsonl"
    if not resume:
        manifest = {
            "kind": "manifest",
            "schema_version": 1,
            "protocol_version": EVOLUTION_PROTOCOL_VERSION,
            "created_at": started_at,
            "rom": rom.public_dict(),
            "config": config.public_dict(),
            "network": {
                "pixel_inputs": PIXEL_INPUTS,
                "previous_action_inputs": PREVIOUS_ACTION_INPUTS,
                "hidden_units": HIDDEN_UNITS,
                "outputs": list(BLIND_ACTIONS),
                "parameter_count": PARAMETER_COUNT,
            },
            "actor_inputs": ["20x18_quantized_rendered_pixels", "previous_action"],
            "selection_inputs": ["sealed_referee_progress", "behavior_descriptor"],
            "ram_used_by_actor": False,
            "ram_used_by_selection": True,
            "snapshot_assisted": False,
            "source": source,
            "implementation_sha256": implementation,
            "private_rom_path_recorded": False,
        }
        _atomic_json(output / "manifest.json", manifest)
        _append_json(trace_path, manifest)
        genealogy_path.touch()

    counters = EvolutionCounters()
    rng = np.random.default_rng(config.seed)
    archive = QualityDiversityArchive(config.archive_capacity)
    seen = SeenVisualFilter(config.seen_filter_bytes)
    history: list[dict[str, Any]] = []
    genealogy: list[dict[str, Any]] = []
    screenshots: list[dict[str, Any]] = []
    tracker = RewardTracker("observer")
    candidate_action_counts = {action: 0 for action in BLIND_ACTIONS}
    genome: EvolutionGenome
    parent_id: str | None
    mutation_seed: int | None
    mutation_sigma: float
    mutated_parameters: int
    policy: RecurrentPixelPolicy
    previous_action: int | None = None
    clean_snapshot: FrozenSnapshot
    current_snapshot: FrozenSnapshot | None = None
    referee_state: PokemonRedState | None = None

    stopper = _SignalStop()
    previous_sigint = signal.signal(signal.SIGINT, stopper.handler)
    previous_sigterm = signal.signal(signal.SIGTERM, stopper.handler)
    stop_reason = "unknown"
    start_clock = monotonic()
    base_elapsed = 0.0
    last_status = 0.0
    last_checkpoint = 0.0

    try:
        with PokemonRedEmulator(rom_path) as emulator:
            actor = PixelsOnlyActor(emulator)
            reader = PokemonRedStateReader(emulator)
            if checkpoint is None:
                clean_snapshot = FrozenSnapshot.freeze(emulator.save_state())
                (
                    genome,
                    parent_id,
                    mutation_seed,
                    mutation_sigma,
                    mutated_parameters,
                ) = _new_candidate(counters, archive, rng, config)
                policy = RecurrentPixelPolicy(genome)
                _append_json(
                    trace_path,
                    {
                        "kind": "candidate_started",
                        "generation": 0,
                        "candidate_index": 0,
                        "genome_id": genome.genome_id,
                        "parent_id": None,
                        "mutation_seed": mutation_seed,
                    },
                )
            else:
                counters = EvolutionCounters.from_checkpoint_dict(checkpoint["counters"])
                base_elapsed = counters.elapsed_seconds
                rng.bit_generator.state = checkpoint["rng_state"]
                archive = QualityDiversityArchive(
                    config.archive_capacity,
                    [EvolutionElite.from_checkpoint_dict(item) for item in checkpoint["archive"]],
                )
                seen_value = checkpoint["seen_filter"]
                seen = SeenVisualFilter(
                    int(seen_value["size_bytes"]),
                    hashes=int(seen_value["hashes"]),
                    payload=base64.b64decode(seen_value["payload"]),
                )
                history = list(checkpoint["history"])
                genealogy = list(checkpoint["genealogy"])
                screenshots = list(checkpoint["screenshots"])
                tracker = RewardTracker.from_checkpoint_dict(checkpoint["tracker"])
                candidate_action_counts = {
                    str(key): int(value)
                    for key, value in checkpoint.get("candidate_action_counts", {}).items()
                }
                for action in BLIND_ACTIONS:
                    candidate_action_counts.setdefault(action, 0)
                genome = EvolutionGenome.from_checkpoint_dict(checkpoint["current_genome"])
                parent_id = checkpoint.get("parent_id")
                mutation_seed = checkpoint.get("mutation_seed")
                mutation_sigma = float(checkpoint.get("mutation_sigma", 0))
                mutated_parameters = int(checkpoint.get("mutated_parameters", 0))
                previous_action = checkpoint.get("previous_action")
                clean_snapshot = FrozenSnapshot.from_checkpoint_dict(checkpoint["clean_snapshot"])
                current_snapshot = FrozenSnapshot.from_checkpoint_dict(
                    checkpoint["current_snapshot"]
                )
                emulator.load_state(current_snapshot.thaw())
                policy = RecurrentPixelPolicy(
                    genome,
                    np.asarray(checkpoint["policy_hidden"], dtype=np.float32),
                )

            while True:
                now = monotonic()
                counters.elapsed_seconds = base_elapsed + now - start_clock
                if stopper.reason:
                    stop_reason = stopper.reason
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

                pixels = actor.observe()
                key = visual_key(pixels)
                if seen.check_and_add(key):
                    counters.unique_visual_cells += 1
                action_index = policy.select(visual_signature(pixels), previous_action)
                action = BlindAction(
                    BLIND_ACTIONS[action_index], ACTION_HOLD_FRAMES, ACTION_RELEASE_FRAMES
                )
                actor.act(action)
                previous_action = action_index
                counters.total_actions += 1
                counters.candidate_actions += 1
                counters.total_frames += action.total_frames
                candidate_action_counts[action.button] += 1
                referee_state = reader.read()
                tracker.score(visually_novel=False, state=referee_state)

                candidate_finished = counters.candidate_actions >= config.candidate_actions
                if candidate_finished:
                    metrics = _metrics(tracker, referee_state, candidate_action_counts)
                    descriptor = behavior_descriptor(metrics)
                    fitness = fitness_vector(metrics, counters.candidate_actions)
                    elite = EvolutionElite(
                        genome=genome,
                        parent_id=parent_id,
                        generation=counters.generation,
                        descriptor=descriptor,
                        fitness=fitness,
                        metrics=metrics,
                        mutation_seed=mutation_seed,
                        mutation_sigma=mutation_sigma,
                        mutated_parameters=mutated_parameters,
                    )
                    inserted, replaced = archive.consider(elite)
                    counters.evaluations += 1
                    if inserted:
                        counters.archive_insertions += 1
                        counters.archive_replacements += int(replaced is not None)
                    record = {
                        "kind": "candidate_completed",
                        "generation": counters.generation,
                        "candidate_index": counters.candidate_index,
                        "genome_id": genome.genome_id,
                        "parent_id": parent_id,
                        "mutation_seed": mutation_seed,
                        "mutation_sigma": mutation_sigma,
                        "mutated_parameters": mutated_parameters,
                        "descriptor": list(descriptor),
                        "fitness": list(fitness),
                        "metrics": metrics,
                        "actions": counters.candidate_actions,
                        "archive_inserted": inserted,
                        "replaced_genome_id": replaced,
                    }
                    _append_json(trace_path, record)
                    _append_json(genealogy_path, record)
                    genealogy.append(record)
                    genealogy = genealogy[-256:]
                    if inserted and len(screenshots) < config.screenshot_limit:
                        filename = f"elite-{counters.evaluations:06d}-{genome.genome_id}.png"
                        _save_png(actor.observe(), output / "screenshots" / filename)
                        screenshots.append(
                            {
                                "file": f"screenshots/{filename}",
                                "genome_id": genome.genome_id,
                                "generation": counters.generation,
                                "descriptor": list(descriptor),
                            }
                        )

                    counters.candidate_index += 1
                    if counters.candidate_index >= config.population_size:
                        counters.generation += 1
                        counters.candidate_index = 0
                    counters.candidate_actions = 0
                    emulator.load_state(clean_snapshot.thaw())
                    tracker = RewardTracker("observer")
                    candidate_action_counts = {action: 0 for action in BLIND_ACTIONS}
                    referee_state = reader.read()
                    previous_action = None
                    (
                        genome,
                        parent_id,
                        mutation_seed,
                        mutation_sigma,
                        mutated_parameters,
                    ) = _new_candidate(counters, archive, rng, config)
                    policy = RecurrentPixelPolicy(genome)
                    _append_json(
                        trace_path,
                        {
                            "kind": "candidate_started",
                            "generation": counters.generation,
                            "candidate_index": counters.candidate_index,
                            "genome_id": genome.genome_id,
                            "parent_id": parent_id,
                            "mutation_seed": mutation_seed,
                            "mutation_sigma": mutation_sigma,
                            "mutated_parameters": mutated_parameters,
                        },
                    )

                status_due = now - last_status >= config.status_interval_seconds
                checkpoint_due = now - last_checkpoint >= config.checkpoint_interval_seconds
                if status_due or checkpoint_due:
                    pixels = actor.observe()
                    _save_png(pixels, output / "latest.png")
                    run_bytes = _directory_size(output)
                    free_bytes = shutil.disk_usage(output).free
                    if run_bytes >= config.max_output_bytes:
                        stop_reason = "output_limit"
                    elif free_bytes < config.min_free_bytes:
                        stop_reason = "low_disk_space"
                    status = _status_payload(
                        state="running" if stop_reason == "unknown" else "stopping",
                        stop_reason=None if stop_reason == "unknown" else stop_reason,
                        started_at=started_at,
                        counters=counters,
                        config=config,
                        archive=archive,
                        genome=genome,
                        parent_id=parent_id,
                        mutation_seed=mutation_seed,
                        mutation_sigma=mutation_sigma,
                        mutated_parameters=mutated_parameters,
                        tracker=tracker,
                        candidate_action_counts=candidate_action_counts,
                        referee_state=referee_state,
                        run_bytes=run_bytes,
                    )
                    history.append(
                        {
                            "elapsed_seconds": counters.elapsed_seconds,
                            "total_actions": counters.total_actions,
                            "evaluations": counters.evaluations,
                            "generation": counters.generation,
                            "archive_cells": len(archive),
                            "fitness_tier": status["fitness_tier"],
                        }
                    )
                    history = history[-20_000:]
                    _append_json(output / "trace.jsonl", {"kind": "status", **status})
                    _atomic_json(output / "status.json", status)
                    _write_dashboard(output, status, history, genealogy)
                    last_status = now
                    if checkpoint_due or stop_reason != "unknown":
                        current_snapshot = FrozenSnapshot.freeze(emulator.save_state())
                        payload = {
                            "schema_version": EVOLUTION_CHECKPOINT_SCHEMA,
                            "protocol_version": EVOLUTION_PROTOCOL_VERSION,
                            "rom_sha256": rom.sha256,
                            "source": source,
                            "implementation_sha256": implementation,
                            "config": config.public_dict(),
                            "counters": counters.checkpoint_dict(),
                            "rng_state": rng.bit_generator.state,
                            "archive": archive.checkpoint_list(),
                            "seen_filter": {
                                "size_bytes": seen.size_bytes,
                                "hashes": seen.hashes,
                                "payload": base64.b64encode(seen.payload()).decode("ascii"),
                            },
                            "clean_snapshot": clean_snapshot.checkpoint_dict(),
                            "current_snapshot": current_snapshot.checkpoint_dict(),
                            "current_genome": genome.checkpoint_dict(),
                            "policy_hidden": policy.hidden.tolist(),
                            "previous_action": previous_action,
                            "parent_id": parent_id,
                            "mutation_seed": mutation_seed,
                            "mutation_sigma": mutation_sigma,
                            "mutated_parameters": mutated_parameters,
                            "tracker": tracker.checkpoint_dict(),
                            "candidate_action_counts": candidate_action_counts,
                            "history": history,
                            "genealogy": genealogy,
                            "screenshots": screenshots,
                            "trace_offset": trace_path.stat().st_size,
                            "genealogy_offset": genealogy_path.stat().st_size,
                        }
                        _write_checkpoint(checkpoint_path, payload)
                        last_checkpoint = now
                    if stop_reason != "unknown":
                        break

            counters.elapsed_seconds = base_elapsed + monotonic() - start_clock
            current_snapshot = FrozenSnapshot.freeze(emulator.save_state())
            final_payload = {
                "schema_version": EVOLUTION_CHECKPOINT_SCHEMA,
                "protocol_version": EVOLUTION_PROTOCOL_VERSION,
                "rom_sha256": rom.sha256,
                "source": source,
                "implementation_sha256": implementation,
                "config": config.public_dict(),
                "counters": counters.checkpoint_dict(),
                "rng_state": rng.bit_generator.state,
                "archive": archive.checkpoint_list(),
                "seen_filter": {
                    "size_bytes": seen.size_bytes,
                    "hashes": seen.hashes,
                    "payload": base64.b64encode(seen.payload()).decode("ascii"),
                },
                "clean_snapshot": clean_snapshot.checkpoint_dict(),
                "current_snapshot": current_snapshot.checkpoint_dict(),
                "current_genome": genome.checkpoint_dict(),
                "policy_hidden": policy.hidden.tolist(),
                "previous_action": previous_action,
                "parent_id": parent_id,
                "mutation_seed": mutation_seed,
                "mutation_sigma": mutation_sigma,
                "mutated_parameters": mutated_parameters,
                "tracker": tracker.checkpoint_dict(),
                "candidate_action_counts": candidate_action_counts,
                "history": history,
                "genealogy": genealogy,
                "screenshots": screenshots,
                "trace_offset": trace_path.stat().st_size,
                "genealogy_offset": genealogy_path.stat().st_size,
            }
            _write_checkpoint(checkpoint_path, final_payload)
            pixels = actor.observe()
            _save_png(pixels, output / "latest.png")
            status = _status_payload(
                state="finished",
                stop_reason=stop_reason,
                started_at=started_at,
                counters=counters,
                config=config,
                archive=archive,
                genome=genome,
                parent_id=parent_id,
                mutation_seed=mutation_seed,
                mutation_sigma=mutation_sigma,
                mutated_parameters=mutated_parameters,
                tracker=tracker,
                candidate_action_counts=candidate_action_counts,
                referee_state=referee_state,
                run_bytes=_directory_size(output),
            )
            _atomic_json(output / "status.json", status)
            _write_dashboard(output, status, history, genealogy)
            _append_json(trace_path, {"kind": "run_finished", "stop_reason": stop_reason})
    except Exception as error:
        if output.is_dir():
            with contextlib.suppress(Exception):
                _atomic_json(
                    output / "status.json",
                    {
                        "schema_version": 1,
                        "mode": "evolution",
                        "state": "failed",
                        "stop_reason": f"error:{type(error).__name__}",
                        "updated_at": datetime.now(UTC).isoformat(),
                        "process_id": os.getpid(),
                    },
                )
        raise
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)

    return EvolutionRunResult(
        run_directory=output,
        stop_reason=stop_reason,
        total_actions=counters.total_actions,
        evaluations=counters.evaluations,
        archive_cells=len(archive),
    )
