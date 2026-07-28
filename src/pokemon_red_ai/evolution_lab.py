from __future__ import annotations

import contextlib
import functools
import gzip
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from time import monotonic, sleep
from typing import Any, BinaryIO
from urllib.parse import unquote, urlsplit

from pokemon_red_ai.evolution_lab_report import render_evolution_lab_dashboard
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import ROM_ENVIRONMENT_VARIABLE, RomFingerprint

DEFAULT_EVOLUTION_LAB_ACTIONS = 1_536_000
_LANE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@dataclass(frozen=True, slots=True)
class EvolutionLabLane:
    lane_id: str
    label: str
    selection_strategy: str
    mutation_profile: str
    row: int
    column: int

    def __post_init__(self) -> None:
        if not _LANE_ID.fullmatch(self.lane_id):
            raise ValueError("Evolution lab lane IDs must be safe lowercase URL slugs")
        if self.selection_strategy not in {"uniform", "frontier"}:
            raise ValueError("Evolution lab selection must be uniform or frontier")
        if self.mutation_profile not in {"broad", "gentle", "multiscale"}:
            raise ValueError("Evolution lab mutation profile is invalid")
        if self.row < 0 or self.column < 0:
            raise ValueError("Evolution lab matrix coordinates cannot be negative")

    def public_dict(self) -> dict[str, str | int]:
        return asdict(self)


def six_lane_matrix() -> tuple[EvolutionLabLane, ...]:
    """The paired 2x3 selection-by-mutation experiment, in dashboard order."""

    labels = {
        ("uniform", "broad"): "U-B · Uniform / Broad",
        ("uniform", "gentle"): "U-G · Uniform / Gentle",
        ("uniform", "multiscale"): "U-M · Uniform / Multiscale",
        ("frontier", "broad"): "F-B · Frontier / Broad",
        ("frontier", "gentle"): "F-G · Frontier / Gentle",
        ("frontier", "multiscale"): "F-M · Frontier / Multiscale",
    }
    lanes: list[EvolutionLabLane] = []
    for row, selection in enumerate(("uniform", "frontier")):
        for column, mutation in enumerate(("broad", "gentle", "multiscale")):
            lanes.append(
                EvolutionLabLane(
                    lane_id=f"{selection}-{mutation}",
                    label=labels[(selection, mutation)],
                    selection_strategy=selection,
                    mutation_profile=mutation,
                    row=row,
                    column=column,
                )
            )
    return tuple(lanes)


@dataclass(frozen=True, slots=True)
class EvolutionLabConfig:
    duration_seconds: float
    max_actions_per_lane: int = DEFAULT_EVOLUTION_LAB_ACTIONS
    seed: int = 20_260_725
    paired_seed: bool = True
    port: int = 8_765
    population_size: int = 16
    candidate_actions: int = 12_000
    archive_capacity: int = 512
    frontier_probability: float = 0.80
    frontier_tournament_size: int = 3
    seen_filter_mib: int = 64
    screenshot_limit: int = 128
    status_interval_seconds: float = 10
    checkpoint_interval_seconds: float = 300
    narrative_interval_seconds: float = 3_600
    visual_interval_seconds: float = 600
    poll_interval_seconds: float = 2
    max_output_mib_per_lane: int = 2_048
    min_free_gib: float = 50
    fail_fast: bool = True

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0 or self.max_actions_per_lane < 1:
            raise ValueError("Evolution lab duration and action budget must be positive")
        if self.seed < 0:
            raise ValueError("Evolution lab seed cannot be negative")
        if not 1 <= self.port <= 65_535:
            raise ValueError("Evolution lab port must be between 1 and 65535")
        if self.population_size < 2 or self.candidate_actions < 1:
            raise ValueError("Evolution lab population settings are invalid")
        if self.archive_capacity < 1:
            raise ValueError("Evolution lab archive capacity must be positive")
        if not 0 <= self.frontier_probability <= 1:
            raise ValueError("Evolution lab frontier probability must be between zero and one")
        if self.frontier_tournament_size < 1:
            raise ValueError("Evolution lab tournament size must be positive")
        if self.seen_filter_mib < 1 or self.screenshot_limit < 1:
            raise ValueError("Evolution lab observation limits must be positive")
        if (
            self.status_interval_seconds <= 0
            or self.checkpoint_interval_seconds <= 0
            or self.narrative_interval_seconds <= 0
            or self.visual_interval_seconds <= 0
            or self.poll_interval_seconds <= 0
        ):
            raise ValueError("Evolution lab intervals must be positive")
        if self.max_output_mib_per_lane < 64 or self.min_free_gib < 0:
            raise ValueError("Evolution lab disk limits are invalid")

    def public_dict(self) -> dict[str, int | float | bool]:
        return asdict(self)


def _lane_seed(config: EvolutionLabConfig, lane_index: int) -> int:
    if config.paired_seed:
        return config.seed
    # Retained for exploratory N-lane runs. The 2x3 preset defaults to paired conditions.
    return (config.seed + (lane_index + 1) * 1_000_003) % (2**63 - 1)


def evolution_lab_agent_command(
    lane: EvolutionLabLane,
    output: Path,
    seed_archive: Path,
    config: EvolutionLabConfig,
    *,
    lane_index: int,
    resume: bool = False,
) -> list[str]:
    """Build one child command without recording or exposing the private ROM path."""

    command = [
        sys.executable,
        "-m",
        "pokemon_red_ai",
        "evolution-run",
        "--output",
        str(output),
        "--hours",
        str(config.duration_seconds / 3_600),
        "--max-actions",
        str(config.max_actions_per_lane),
        "--seed",
        str(_lane_seed(config, lane_index)),
        "--population-size",
        str(config.population_size),
        "--candidate-actions",
        str(config.candidate_actions),
        "--archive-capacity",
        str(config.archive_capacity),
        "--selection-strategy",
        lane.selection_strategy,
        "--frontier-probability",
        str(config.frontier_probability),
        "--frontier-tournament-size",
        str(config.frontier_tournament_size),
        "--mutation-profile",
        lane.mutation_profile,
        "--seed-archive",
        str(seed_archive),
        "--seen-filter-mib",
        str(config.seen_filter_mib),
        "--screenshot-limit",
        str(config.screenshot_limit),
        "--status-seconds",
        str(config.status_interval_seconds),
        "--checkpoint-seconds",
        str(config.checkpoint_interval_seconds),
        "--max-output-mib",
        str(config.max_output_mib_per_lane),
        "--min-free-gib",
        str(config.min_free_gib),
    ]
    if resume:
        command.append("--resume")
    return command


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _atomic_bytes(path: Path, value: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def _append_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as target:
        target.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        target.flush()
        os.fsync(target.fileno())


def _read_status(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _archive_checkpoint(seed_archive: Path) -> Path:
    if seed_archive.is_file():
        return seed_archive
    if seed_archive.is_dir():
        checkpoint = seed_archive / "checkpoint.json.gz"
        if checkpoint.is_file():
            return checkpoint
    raise ValueError(
        "Seed archive must be an evolution checkpoint or a run with checkpoint.json.gz"
    )


def _seed_archive_identity(seed_archive: Path) -> dict[str, Any]:
    checkpoint = _archive_checkpoint(seed_archive)
    digest = hashlib.sha256()
    with checkpoint.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    try:
        if checkpoint.suffix == ".gz":
            with gzip.open(checkpoint, "rt", encoding="utf-8") as source:
                payload = json.load(source)
        else:
            payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Seed archive checkpoint is unreadable") from error
    archive = payload.get("archive")
    if not isinstance(archive, list) or not archive:
        raise ValueError("Seed archive checkpoint contains no surviving elites")
    return {
        "label": "sealed-evolution-archive",
        "checkpoint_file": checkpoint.name,
        "checkpoint_sha256": digest.hexdigest(),
        "checkpoint_bytes": checkpoint.stat().st_size,
        "protocol_version": payload.get("protocol_version"),
        "archive_cells": len(archive),
        "absolute_path_recorded": False,
    }


class EvolutionLabHandler(SimpleHTTPRequestHandler):
    """A narrow static server that cannot expose checkpoints, traces, logs, or manifests."""

    def __init__(
        self,
        *args: Any,
        lane_ids: Sequence[str],
        directory: str,
        **kwargs: Any,
    ) -> None:
        self.lane_ids = frozenset(lane_ids)
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self'; style-src 'unsafe-inline'; object-src 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _public_path(self) -> bool:
        decoded = unquote(urlsplit(self.path).path)
        path = PurePosixPath(decoded)
        parts = tuple(part for part in path.parts if part != "/")
        if any(part in {"", ".", ".."} for part in parts):
            return False
        if not parts or parts in {("index.html",), ("status.json",)}:
            return True
        if parts[0] not in self.lane_ids:
            return False
        if len(parts) == 2 and parts[1] in {"index.html", "latest.png"}:
            return True
        return (
            len(parts) == 3
            and parts[1] == "screenshots"
            and parts[2].endswith(".png")
            and "/" not in parts[2]
        )

    def do_GET(self) -> None:
        if not self._public_path():
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if not self._public_path():
            self.send_error(404)
            return
        super().do_HEAD()


def _start_http_server(
    output: Path, port: int, lane_ids: Sequence[str]
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = functools.partial(
        EvolutionLabHandler,
        directory=str(output),
        lane_ids=tuple(lane_ids),
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="evolution-lab-dashboard",
        daemon=True,
    )
    thread.start()
    return server, thread


def _start_lane(
    lane: EvolutionLabLane,
    *,
    lane_index: int,
    output: Path,
    seed_archive: Path,
    config: EvolutionLabConfig,
    environment: Mapping[str, str],
    resume: bool,
) -> tuple[subprocess.Popen[bytes], BinaryIO]:
    log_path = output.parent / f"{lane.lane_id}.console.log"
    log = log_path.open("ab" if resume else "xb")
    try:
        process = subprocess.Popen(
            evolution_lab_agent_command(
                lane,
                output,
                seed_archive,
                config,
                lane_index=lane_index,
                resume=resume,
            ),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=dict(environment),
            start_new_session=True,
        )
    except Exception:
        log.close()
        raise
    return process, log


def _history_point(status: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "updated_at": status.get("updated_at"),
        "elapsed_seconds": status.get("elapsed_seconds", 0),
        "total_actions": status.get("total_actions", 0),
        "evaluations": status.get("evaluations", 0),
        "generation": status.get("generation", 0),
        "archive_cells": status.get("archive_cells", 0),
        "fitness_tier": status.get("fitness_tier", 0),
        "maps_seen": status.get("maps_seen", 0),
        "positions_seen": status.get("positions_seen", 0),
        "max_party_count": status.get("max_party_count", 0),
        "max_party_level": status.get("max_party_level", 0),
        "pokedex_seen": status.get("pokedex_seen", 0),
        "pokedex_owned": status.get("pokedex_owned", 0),
        "archive_insertions": status.get("archive_insertions", 0),
        "lineage_depth": status.get("lineage_depth", status.get("current_lineage_depth", 0)),
    }


def comparison_snapshot(
    kind: str,
    statuses: Mapping[str, Mapping[str, Any] | None],
    lanes: Sequence[EvolutionLabLane],
    *,
    elapsed_seconds: float,
) -> dict[str, Any]:
    """Create the small, stable narrative record used by JSONL and Markdown."""

    lane_values: dict[str, dict[str, Any]] = {}
    for lane in lanes:
        status = statuses.get(lane.lane_id) or {}
        best_fitness = status.get("best_fitness")
        lane_values[lane.lane_id] = {
            "selection_strategy": lane.selection_strategy,
            "mutation_profile": lane.mutation_profile,
            "state": status.get("state", "waiting"),
            "total_actions": int(status.get("total_actions", 0) or 0),
            "evaluations": int(status.get("evaluations", 0) or 0),
            "fitness_tier": int(status.get("fitness_tier", 0) or 0),
            "maps_seen": int(status.get("maps_seen", 0) or 0),
            "positions_seen": int(status.get("positions_seen", 0) or 0),
            "max_party_count": int(status.get("max_party_count", 0) or 0),
            "max_party_level": int(status.get("max_party_level", 0) or 0),
            "pokedex_seen": int(status.get("pokedex_seen", 0) or 0),
            "pokedex_owned": int(status.get("pokedex_owned", 0) or 0),
            "archive_cells": int(status.get("archive_cells", 0) or 0),
            "archive_insertions": int(status.get("archive_insertions", 0) or 0),
            "lineage_depth": int(
                status.get("lineage_depth", status.get("current_lineage_depth", 0)) or 0
            ),
            "best_fitness": list(best_fitness) if isinstance(best_fitness, (list, tuple)) else [],
        }
    return {
        "schema_version": 1,
        "kind": kind,
        "recorded_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "lanes": lane_values,
    }


def _capture_visual_frame(
    output: Path,
    statuses: Mapping[str, Mapping[str, Any] | None],
    lanes: Sequence[EvolutionLabLane],
    *,
    frame_index: int,
    kind: str,
    elapsed_seconds: float,
) -> dict[str, Any] | None:
    """Freeze one synchronized six-lane visual set for analysis and video editing."""

    sources = {lane.lane_id: output / lane.lane_id / "latest.png" for lane in lanes}
    if any(not path.is_file() for path in sources.values()):
        return None
    frame_name = f"frame-{frame_index:05d}"
    frame_directory = output / "visuals" / frame_name
    frame_directory.mkdir(parents=True, exist_ok=False)
    images: dict[str, dict[str, Any]] = {}
    for lane in lanes:
        payload = sources[lane.lane_id].read_bytes()
        destination = frame_directory / f"{lane.lane_id}.png"
        _atomic_bytes(destination, payload)
        status = statuses.get(lane.lane_id) or {}
        images[lane.lane_id] = {
            "file": f"visuals/{frame_name}/{destination.name}",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "total_actions": int(status.get("total_actions", 0) or 0),
            "evaluations": int(status.get("evaluations", 0) or 0),
            "fitness_tier": int(status.get("fitness_tier", 0) or 0),
        }
    dashboard_payload = (output / "index.html").read_bytes()
    _atomic_bytes(frame_directory / "dashboard.html", dashboard_payload)
    record = {
        "schema_version": 1,
        "kind": "visual_frame",
        "frame_kind": kind,
        "frame_index": frame_index,
        "recorded_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "dashboard_sha256": hashlib.sha256(dashboard_payload).hexdigest(),
        "images": images,
    }
    _atomic_json(frame_directory / "metadata.json", record)
    return record


def _comparison_complete(
    statuses: Mapping[str, Mapping[str, Any] | None],
    lanes: Sequence[EvolutionLabLane],
    config: EvolutionLabConfig,
) -> bool:
    expected_evaluations = config.max_actions_per_lane // config.candidate_actions
    return config.max_actions_per_lane % config.candidate_actions == 0 and all(
        status is not None
        and status.get("state") == "finished"
        and status.get("stop_reason") == "action_limit"
        and int(status.get("total_actions", -1)) == config.max_actions_per_lane
        and int(status.get("evaluations", -1)) == expected_evaluations
        for status in (statuses.get(lane.lane_id) for lane in lanes)
    )


def _worker_heartbeat_is_live(status: Mapping[str, Any] | None) -> bool:
    if not status or status.get("state") not in {"running", "stopping"}:
        return False
    try:
        updated = datetime.fromisoformat(str(status["updated_at"]))
        age = max(0.0, (datetime.now(UTC) - updated).total_seconds())
        heartbeat_limit = max(
            90.0,
            float(status.get("heartbeat_interval_seconds", 30) or 30) * 3,
        )
        process_id = int(status.get("process_id", 0) or 0)
        if age > heartbeat_limit or process_id < 1:
            return False
        os.kill(process_id, 0)
    except (KeyError, OSError, TypeError, ValueError):
        return False
    return True


def _append_chronicle_snapshot(path: Path, snapshot: Mapping[str, Any]) -> None:
    lanes = snapshot["lanes"]
    lines = [
        "",
        f"## {_duration(float(snapshot['elapsed_seconds']))} · {snapshot['kind']}",
        "",
        f"Recorded `{snapshot['recorded_at']}`.",
        "",
        "| Lane | Actions | Children | Tier | Maps / positions | Party / level | Archive | Depth |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for lane_id, value in lanes.items():
        lines.append(
            f"| {lane_id} | {value['total_actions']:,} | {value['evaluations']:,} | "
            f"{value['fitness_tier']} | {value['maps_seen']} / {value['positions_seen']} | "
            f"{value['max_party_count']} / {value['max_party_level']} | "
            f"{value['archive_cells']} | {value['lineage_depth']} |"
        )
    lines.extend(
        [
            "",
            "> Interpretation boundary: this is a synchronized observation, not a causal verdict. "
            "Compare final lanes by equal action budget and confirm any apparent winner from fresh "
            "archives and seeds.",
            "",
        ]
    )
    with path.open("a", encoding="utf-8") as target:
        target.write("\n".join(lines))
        target.flush()
        os.fsync(target.fileno())


def _initialize_chronicle(
    path: Path,
    lanes: Sequence[EvolutionLabLane],
    seed_identity: Mapping[str, Any],
    config: EvolutionLabConfig,
) -> None:
    rows = "\n".join(
        f"| {lane.lane_id} | {lane.selection_strategy} | {lane.mutation_profile} |"
        for lane in lanes
    )
    _atomic_text(
        path,
        "# Evolution 2×3 Lab Chronicle\n\n"
        "## The branch point\n\n"
        "The first neuroevolution pretrial showed evidence that useful behavior can become "
        "heritable, but "
        "also showed two losses: uniform parent choice spent many lives revisiting weak ancestors, "
        "and one broad mutation scale often destroyed rare progress. This engineering fork asks "
        "which combination best preserves and extends those useful accidents.\n\n"
        "All lanes inherit the same sealed neural archive. They do **not** inherit game RAM or a "
        "save state: every child starts Pokémon Red from clean power-on. The paired setup uses the "
        f"same base RNG seed (`{config.seed}`) in every lane so the intended rule change is the "
        "selection/mutation treatment. Once their archive populations diverge, their random draws "
        "naturally lead to different genomes.\n\n"
        f"Seed checkpoint SHA-256: `{seed_identity['checkpoint_sha256']}`  \n"
        f"Seed archive cells: {seed_identity['archive_cells']}  \n"
        f"Per-lane ceiling: {config.max_actions_per_lane:,} actions  \n"
        f"Child lifetime: {config.candidate_actions:,} actions\n\n"
        "| Lane | Parent selection | Mutation profile |\n"
        "|---|---|---|\n"
        f"{rows}\n\n"
        "## Live comparison log\n",
    )


def _lab_status(
    *,
    state: str,
    started_at: str,
    elapsed_seconds: float,
    config: EvolutionLabConfig,
    seed_identity: Mapping[str, Any],
    lanes: Sequence[EvolutionLabLane],
    processes: Mapping[str, subprocess.Popen[bytes]],
    statuses: Mapping[str, Mapping[str, Any] | None],
    stop_reason: str | None,
    comparison_complete: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "evolution_selection_mutation_lab",
        "state": state,
        "stop_reason": stop_reason,
        "comparison_complete": comparison_complete,
        "started_at": started_at,
        "updated_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "process_id": os.getpid(),
        "dashboard_url": f"http://127.0.0.1:{config.port}/index.html",
        "config": config.public_dict(),
        "seed_archive": dict(seed_identity),
        "lanes": {
            lane.lane_id: {
                **lane.public_dict(),
                "seed": _lane_seed(config, index),
                "process_id": processes[lane.lane_id].pid,
                "process_alive": processes[lane.lane_id].poll() is None,
                "return_code": processes[lane.lane_id].poll(),
                "state": None
                if statuses.get(lane.lane_id) is None
                else statuses[lane.lane_id].get("state"),
                "stop_reason": None
                if statuses.get(lane.lane_id) is None
                else statuses[lane.lane_id].get("stop_reason"),
            }
            for index, lane in enumerate(lanes)
        },
    }


def _validate_lanes(lanes: Sequence[EvolutionLabLane]) -> tuple[EvolutionLabLane, ...]:
    result = tuple(lanes)
    if not result:
        raise ValueError("Evolution lab requires at least one lane")
    ids = [lane.lane_id for lane in result]
    if len(set(ids)) != len(ids):
        raise ValueError("Evolution lab lane IDs must be unique")
    coordinates = [(lane.row, lane.column) for lane in result]
    if len(set(coordinates)) != len(coordinates):
        raise ValueError("Evolution lab matrix coordinates must be unique")
    return result


def run_evolution_lab(
    rom_path: Path,
    rom: RomFingerprint,
    *,
    output: Path,
    seed_archive: Path,
    config: EvolutionLabConfig,
    lanes: Sequence[EvolutionLabLane] | None = None,
    resume: bool = False,
) -> int:
    """Run an N-lane paired evolution comparison and serve its local dashboard."""

    selected_lanes = _validate_lanes(six_lane_matrix() if lanes is None else lanes)
    seed_archive = seed_archive.resolve()
    seed_identity = _seed_archive_identity(seed_archive)
    source = detect_source_provenance().public_dict()
    lane_manifest = [lane.public_dict() for lane in selected_lanes]
    stop_marker = output / "STOP"
    events_path = output / "lab-events.jsonl"
    chronicle_path = output / "chronicle.md"
    histories: dict[str, list[dict[str, Any]]] = {
        lane.lane_id: [] for lane in selected_lanes
    }
    base_elapsed = 0.0
    if resume:
        if not output.is_dir() or not (output / "manifest.json").is_file():
            raise ValueError("Evolution lab resume requires an existing lab manifest")
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            "kind": "evolution_selection_mutation_lab",
            "rom": rom.public_dict(),
            "config": config.public_dict(),
            "paired_seed": config.paired_seed,
            "lanes": lane_manifest,
            "seed_archive": seed_identity,
            "source": source,
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise ValueError(f"Evolution lab resume {key} does not match")
        for lane in selected_lanes:
            lane_output = output / lane.lane_id
            lane_status = _read_status(lane_output / "status.json")
            if _worker_heartbeat_is_live(lane_status):
                raise ValueError(
                    f"Evolution lab lane {lane.lane_id} still has a live worker"
                )
            if not (lane_output / "checkpoint.json.gz").is_file():
                raise ValueError(
                    f"Evolution lab lane {lane.lane_id} has no recovery checkpoint"
                )
        previous_status = _read_status(output / "status.json") or {}
        base_elapsed = float(previous_status.get("elapsed_seconds", 0) or 0)
        history_payload = _read_status(output / "history.json") or {}
        raw_histories = history_payload.get("lanes", {})
        if isinstance(raw_histories, dict):
            for lane in selected_lanes:
                value = raw_histories.get(lane.lane_id)
                if isinstance(value, list):
                    histories[lane.lane_id] = [
                        dict(item) for item in value if isinstance(item, dict)
                    ][-20_000:]
        started_at = str(manifest["created_at"])
        stop_marker.unlink(missing_ok=True)
    else:
        if output.exists():
            raise ValueError("Evolution lab output directory already exists")
        output.mkdir(parents=True)
        started_at = datetime.now(UTC).isoformat()
        manifest = {
            "schema_version": 1,
            "kind": "evolution_selection_mutation_lab",
            "created_at": started_at,
            "rom": rom.public_dict(),
            "config": config.public_dict(),
            "paired_seed": config.paired_seed,
            "lanes": lane_manifest,
            "seed_archive": seed_identity,
            "source": source,
            "runtime": {
                "python": platform.python_version(),
                "numpy": version("numpy"),
                "pillow": version("pillow"),
                "pyboy": version("pyboy"),
                "platform": platform.platform(),
            },
            "private_rom_path_recorded": False,
            "private_seed_archive_path_recorded": False,
        }
        _atomic_json(output / "manifest.json", manifest)
        events_path.touch()
        _initialize_chronicle(chronicle_path, selected_lanes, seed_identity, config)
    (output / "visuals").mkdir(exist_ok=True)

    environment = os.environ.copy()
    environment[ROM_ENVIRONMENT_VARIABLE] = str(rom_path)
    processes: dict[str, subprocess.Popen[bytes]] = {}
    logs: dict[str, BinaryIO] = {}
    stopping = False
    requested_reason: str | None = None

    def request_stop(event: int, _frame: object) -> None:
        nonlocal stopping, requested_reason
        stopping = True
        requested_reason = "sigint" if event == signal.SIGINT else "sigterm"

    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    previous_sigterm = signal.signal(signal.SIGTERM, request_stop)
    server: ThreadingHTTPServer | None = None
    start_clock = monotonic()
    last_narrative = start_clock
    last_visual = start_clock - config.visual_interval_seconds
    visual_frame_index = len(tuple((output / "visuals").glob("frame-*")))
    final_snapshot_written = False
    try:
        server, _thread = _start_http_server(
            output,
            config.port,
            [lane.lane_id for lane in selected_lanes],
        )
        for index, lane in enumerate(selected_lanes):
            process, log = _start_lane(
                lane,
                lane_index=index,
                output=output / lane.lane_id,
                seed_archive=seed_archive,
                config=config,
                environment=environment,
                resume=resume,
            )
            processes[lane.lane_id] = process
            logs[lane.lane_id] = log

        initial_statuses: dict[str, dict[str, Any] | None] = {
            lane.lane_id: _read_status(output / lane.lane_id / "status.json")
            if resume
            else None
            for lane in selected_lanes
        }
        startup = comparison_snapshot(
            "orchestrator_resume" if resume else "startup",
            initial_statuses,
            selected_lanes,
            elapsed_seconds=base_elapsed,
        )
        _append_json(events_path, startup)
        _append_chronicle_snapshot(chronicle_path, startup)

        while True:
            elapsed = base_elapsed + monotonic() - start_clock
            if stop_marker.exists() and not stopping:
                stopping = True
                requested_reason = "stop_requested"
            statuses: dict[str, dict[str, Any] | None] = {
                lane.lane_id: _read_status(output / lane.lane_id / "status.json")
                for lane in selected_lanes
            }
            for lane in selected_lanes:
                status = statuses[lane.lane_id]
                if status is None:
                    continue
                history = histories[lane.lane_id]
                if not history or history[-1].get("total_actions") != status.get("total_actions"):
                    history.append(_history_point(status))
                    histories[lane.lane_id] = history[-20_000:]

            failed = [
                lane.lane_id
                for lane in selected_lanes
                if processes[lane.lane_id].poll() not in {None, 0}
            ]
            if failed and config.fail_fast and not stopping:
                stopping = True
                requested_reason = "lane_failed:" + ",".join(failed)
            if stopping:
                for lane in selected_lanes:
                    process = processes[lane.lane_id]
                    if process.poll() is None:
                        # A child creates its run directory after process start. On an unusually
                        # early stop, retry on the next poll instead of crashing the orchestrator.
                        with contextlib.suppress(OSError):
                            (output / lane.lane_id / "STOP").touch(exist_ok=True)

            all_exited = all(process.poll() is not None for process in processes.values())
            if all_exited:
                # A worker can publish its terminal status after the read at the
                # top of this loop. Re-read only after every process has exited.
                statuses = {
                    lane.lane_id: _read_status(output / lane.lane_id / "status.json")
                    for lane in selected_lanes
                }
                for lane in selected_lanes:
                    terminal = statuses[lane.lane_id]
                    history = histories[lane.lane_id]
                    if terminal is not None and (
                        not history
                        or history[-1].get("total_actions")
                        != terminal.get("total_actions")
                    ):
                        history.append(_history_point(terminal))
                        histories[lane.lane_id] = history[-20_000:]
                comparison_complete = _comparison_complete(
                    statuses, selected_lanes, config
                )
                all_successful = all(
                    process.returncode == 0 for process in processes.values()
                )
                if not all_successful:
                    state = "failed"
                elif stopping or comparison_complete:
                    state = "finished"
                else:
                    state = "incomplete"
            else:
                state = "stopping" if stopping else "running"
                comparison_complete = False
            lab_stop_reason = requested_reason
            if all_exited and lab_stop_reason is None:
                lab_stop_reason = (
                    "all_lanes_action_limit"
                    if comparison_complete
                    else "incomplete_equal_budget_comparison"
                )
            lab_status = _lab_status(
                state=state,
                started_at=started_at,
                elapsed_seconds=elapsed,
                config=config,
                seed_identity=seed_identity,
                lanes=selected_lanes,
                processes=processes,
                statuses=statuses,
                stop_reason=lab_stop_reason,
                comparison_complete=comparison_complete,
            )
            _atomic_json(output / "status.json", lab_status)
            _atomic_json(output / "history.json", {"lanes": histories})
            _atomic_text(
                output / "index.html",
                render_evolution_lab_dashboard(
                    lab_status,
                    [lane.public_dict() for lane in selected_lanes],
                    statuses,
                    histories,
                ),
            )

            if monotonic() - last_narrative >= config.narrative_interval_seconds:
                snapshot = comparison_snapshot(
                    "periodic_comparison",
                    statuses,
                    selected_lanes,
                    elapsed_seconds=elapsed,
                )
                _append_json(events_path, snapshot)
                _append_chronicle_snapshot(chronicle_path, snapshot)
                last_narrative = monotonic()

            if (
                not all_exited
                and monotonic() - last_visual >= config.visual_interval_seconds
            ):
                visual = _capture_visual_frame(
                    output,
                    statuses,
                    selected_lanes,
                    frame_index=visual_frame_index,
                    kind="periodic",
                    elapsed_seconds=elapsed,
                )
                if visual is not None:
                    _append_json(events_path, visual)
                    visual_frame_index += 1
                    last_visual = monotonic()

            if all_exited:
                visual = _capture_visual_frame(
                    output,
                    statuses,
                    selected_lanes,
                    frame_index=visual_frame_index,
                    kind="final",
                    elapsed_seconds=elapsed,
                )
                if visual is not None:
                    _append_json(events_path, visual)
                final = comparison_snapshot(
                    "final_comparison",
                    statuses,
                    selected_lanes,
                    elapsed_seconds=elapsed,
                )
                final["comparison_complete"] = comparison_complete
                _append_json(events_path, final)
                _append_chronicle_snapshot(chronicle_path, final)
                _atomic_json(output / "final-snapshot.json", final)
                final_snapshot_written = True
                return 0 if state == "finished" else 1
            sleep(config.poll_interval_seconds)
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        if server is not None:
            server.shutdown()
            server.server_close()
        for lane in selected_lanes:
            process = processes.get(lane.lane_id)
            if process is not None and process.poll() is None:
                with contextlib.suppress(OSError):
                    (output / lane.lane_id / "STOP").touch(exist_ok=True)
        deadline = monotonic() + 30
        for process in processes.values():
            if process.poll() is None:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=max(0, deadline - monotonic()))
        for process in processes.values():
            if process.poll() is None:
                with contextlib.suppress(OSError):
                    os.killpg(process.pid, signal.SIGTERM)
        term_deadline = monotonic() + 5
        for process in processes.values():
            if process.poll() is None:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=max(0, term_deadline - monotonic()))
        for process in processes.values():
            if process.poll() is None:
                with contextlib.suppress(OSError):
                    os.killpg(process.pid, signal.SIGKILL)
        for process in processes.values():
            if process.poll() is None:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=2)
        for log in logs.values():
            with contextlib.suppress(Exception):
                log.close()
        if processes and not final_snapshot_written:
            statuses = {
                lane.lane_id: _read_status(output / lane.lane_id / "status.json")
                for lane in selected_lanes
            }
            emergency = comparison_snapshot(
                "orchestrator_exit",
                statuses,
                selected_lanes,
                elapsed_seconds=base_elapsed + monotonic() - start_clock,
            )
            with contextlib.suppress(OSError):
                _append_json(events_path, emergency)
                _append_chronicle_snapshot(chronicle_path, emergency)


def show_evolution_lab_status(output: Path) -> int:
    status = _read_status(output / "status.json")
    if status is None:
        raise ValueError("Evolution lab status.json does not exist or is invalid")
    print(f"Evolution lab: {status['state']}")
    print(f"Dashboard: {status['dashboard_url']}")
    for lane_id, lane in status["lanes"].items():
        print(
            f"{lane_id}: {lane['state'] or 'starting'} · alive={lane['process_alive']} · "
            f"return={lane['return_code']} · stop={lane['stop_reason'] or 'active'}"
        )
    return 1 if status["state"] in {"failed", "incomplete"} else 0


def request_evolution_lab_stop(output: Path) -> int:
    if not (output / "status.json").is_file():
        raise ValueError("Evolution lab status.json does not exist")
    (output / "STOP").touch(exist_ok=True)
    print("Graceful evolution-lab stop requested; all lanes will checkpoint before exiting.")
    return 0
