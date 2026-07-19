from __future__ import annotations

import contextlib
import functools
import json
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from time import monotonic, sleep
from typing import Any
from urllib.parse import unquote, urlsplit

from pokemon_red_ai.arena_report import MODE_ORDER, render_arena_dashboard
from pokemon_red_ai.rom import ROM_ENVIRONMENT_VARIABLE, RomFingerprint

FINAL_ARENA_MAX_ACTIONS = 150_000_000
FINAL_ARENA_Q_POLICY_BUCKETS = 1_048_576


@dataclass(frozen=True, slots=True)
class ArenaConfig:
    duration_seconds: float
    max_actions: int
    seed: int
    port: int = 8_765
    status_interval_seconds: float = 10
    checkpoint_interval_seconds: float = 300
    max_output_mib_per_agent: int = 2_048
    min_free_gib: float = 50
    seen_filter_mib: int = 64
    q_policy_buckets: int = FINAL_ARENA_Q_POLICY_BUCKETS
    q_n_step: int = 128
    replay_capacity: int = 100_000
    replay_batch_size: int = 16
    replay_interval: int = 4
    important_replay_capacity: int = 10_000
    timelapse_minutes: float = 10
    evolution_population_size: int = 16
    evolution_candidate_actions: int = 12_000
    evolution_archive_capacity: int = 512

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0 or self.max_actions < 1:
            raise ValueError("Arena duration and action budget must be positive")
        if not 1 <= self.port <= 65_535:
            raise ValueError("Arena port must be between 1 and 65535")
        if self.status_interval_seconds <= 0 or self.checkpoint_interval_seconds <= 0:
            raise ValueError("Arena status and checkpoint intervals must be positive")
        if self.max_output_mib_per_agent < 64 or self.min_free_gib < 0:
            raise ValueError("Arena disk limits are invalid")
        if self.seen_filter_mib < 1 or self.q_policy_buckets < 1_024:
            raise ValueError("Arena learner memory settings are invalid")
        if self.q_n_step < 1 or self.replay_capacity < 1:
            raise ValueError("Arena replay settings are invalid")
        if not 1 <= self.replay_batch_size <= self.replay_capacity:
            raise ValueError("Arena replay batch must fit inside replay capacity")
        if self.replay_interval < 1:
            raise ValueError("Arena replay interval must be positive")
        if self.important_replay_capacity < 1:
            raise ValueError("Arena important replay capacity must be positive")
        if self.timelapse_minutes <= 0:
            raise ValueError("Arena timelapse interval must be positive")
        if self.evolution_population_size < 2 or self.evolution_candidate_actions < 1:
            raise ValueError("Arena evolution population and lifetime must be positive")
        if self.evolution_archive_capacity < 1:
            raise ValueError("Arena evolution archive capacity must be positive")

    def public_dict(self) -> dict[str, int | float]:
        return {
            "duration_seconds": self.duration_seconds,
            "max_actions": self.max_actions,
            "seed": self.seed,
            "port": self.port,
            "status_interval_seconds": self.status_interval_seconds,
            "checkpoint_interval_seconds": self.checkpoint_interval_seconds,
            "max_output_mib_per_agent": self.max_output_mib_per_agent,
            "min_free_gib": self.min_free_gib,
            "seen_filter_mib": self.seen_filter_mib,
            "q_policy_buckets": self.q_policy_buckets,
            "q_n_step": self.q_n_step,
            "replay_capacity": self.replay_capacity,
            "replay_batch_size": self.replay_batch_size,
            "replay_interval": self.replay_interval,
            "important_replay_capacity": self.important_replay_capacity,
            "timelapse_minutes": self.timelapse_minutes,
            "evolution_population_size": self.evolution_population_size,
            "evolution_candidate_actions": self.evolution_candidate_actions,
            "evolution_archive_capacity": self.evolution_archive_capacity,
        }


class QuietHandler(SimpleHTTPRequestHandler):
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
        if not parts or parts == ("index.html",):
            return True
        if parts[0] not in MODE_ORDER:
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


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_status(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _agent_command(mode: str, output: Path, config: ArenaConfig, *, resume: bool) -> list[str]:
    if mode == "evolution":
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
            str(config.max_actions),
            "--seed",
            str(config.seed),
            "--population-size",
            str(config.evolution_population_size),
            "--candidate-actions",
            str(config.evolution_candidate_actions),
            "--archive-capacity",
            str(config.evolution_archive_capacity),
            "--seen-filter-mib",
            str(config.seen_filter_mib),
            "--screenshot-limit",
            "128",
            "--status-seconds",
            str(config.status_interval_seconds),
            "--checkpoint-seconds",
            str(config.checkpoint_interval_seconds),
            "--max-output-mib",
            str(config.max_output_mib_per_agent),
            "--min-free-gib",
            str(config.min_free_gib),
        ]
        if resume:
            command.append("--resume")
        return command
    command = [
        sys.executable,
        "-m",
        "pokemon_red_ai",
        "blind-run",
        "--output",
        str(output),
        "--mode",
        mode,
        "--hours",
        str(config.duration_seconds / 3_600),
        "--max-actions",
        str(config.max_actions),
        "--seed",
        str(config.seed),
        "--seen-filter-mib",
        str(config.seen_filter_mib),
        "--q-policy-buckets",
        str(config.q_policy_buckets),
        "--q-n-step",
        str(config.q_n_step),
        "--replay-capacity",
        str(config.replay_capacity),
        "--replay-batch-size",
        str(config.replay_batch_size),
        "--replay-interval",
        str(config.replay_interval),
        "--important-replay-capacity",
        str(config.important_replay_capacity),
        "--screenshot-limit",
        "128",
        "--timelapse-minutes",
        str(config.timelapse_minutes),
        "--timelapse-limit",
        "512",
        "--status-seconds",
        str(config.status_interval_seconds),
        "--checkpoint-seconds",
        str(config.checkpoint_interval_seconds),
        "--max-output-mib",
        str(config.max_output_mib_per_agent),
        "--min-free-gib",
        str(config.min_free_gib),
    ]
    if resume:
        command.append("--resume")
    return command


def _start_agent(
    mode: str,
    output: Path,
    config: ArenaConfig,
    environment: dict[str, str],
    *,
    resume: bool,
) -> tuple[subprocess.Popen[bytes], Any]:
    log_path = output.parent / f"{mode}.console.log"
    log = log_path.open("ab" if resume else "xb")
    process = subprocess.Popen(
        _agent_command(mode, output, config, resume=resume),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=environment,
        start_new_session=True,
    )
    return process, log


def _start_http_server(output: Path, port: int) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = functools.partial(QuietHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, name="arena-dashboard", daemon=True)
    thread.start()
    return server, thread


def run_arena(
    rom_path: Path,
    rom: RomFingerprint,
    *,
    output: Path,
    config: ArenaConfig,
) -> int:
    if output.exists():
        raise ValueError("Arena output directory already exists")
    output.mkdir(parents=True)
    stop_marker = output / "STOP"
    started_at = datetime.now(UTC).isoformat()
    manifest = {
        "schema_version": 1,
        "kind": "four_agent_successor_arena",
        "created_at": started_at,
        "modes": list(MODE_ORDER),
        "rom": rom.public_dict(),
        "config": config.public_dict(),
        "private_rom_path_recorded": False,
    }
    _atomic_json(output / "manifest.json", manifest)

    environment = os.environ.copy()
    environment[ROM_ENVIRONMENT_VARIABLE] = str(rom_path)
    processes: dict[str, subprocess.Popen[bytes]] = {}
    logs: dict[str, Any] = {}
    restarts = {mode: 0 for mode in MODE_ORDER}
    histories: dict[str, list[dict[str, Any]]] = {mode: [] for mode in MODE_ORDER}
    stopping = False

    def request_stop(_event: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    previous_sigterm = signal.signal(signal.SIGTERM, request_stop)
    server: ThreadingHTTPServer | None = None
    try:
        server, _server_thread = _start_http_server(output, config.port)
        for mode in MODE_ORDER:
            process, log = _start_agent(
                mode,
                output / mode,
                config,
                environment,
                resume=False,
            )
            processes[mode] = process
            logs[mode] = log

        start_clock = monotonic()
        while True:
            if stop_marker.exists():
                stopping = True
            statuses = {mode: _read_status(output / mode / "status.json") for mode in MODE_ORDER}
            for mode, status in statuses.items():
                if status is None:
                    continue
                history = histories[mode]
                if not history or history[-1].get("total_actions") != status.get("total_actions"):
                    history.append(
                        {
                            "elapsed_seconds": status.get("elapsed_seconds", 0),
                            "total_actions": status.get("total_actions", 0),
                            "unique_visual_cells": status.get("unique_visual_cells", 0),
                            "reward_total": status.get("reward_total", 0),
                            "maps_seen": status.get("maps_seen", 0),
                            "positions_seen": status.get("positions_seen", 0),
                            "pokedex_seen": status.get("pokedex_seen", 0),
                            "pokedex_owned": status.get("pokedex_owned", 0),
                            "max_party_level": status.get("max_party_level", 0),
                            "badge_count": status.get("badge_count", 0),
                            "fitness_tier": status.get("fitness_tier", 0),
                            "evaluations": status.get("evaluations", 0),
                            "archive_cells": status.get("archive_cells", 0),
                        }
                    )
                    histories[mode] = history[-20_000:]

            if stopping:
                for mode in MODE_ORDER:
                    run_status = statuses.get(mode)
                    if run_status and run_status.get("state") == "running":
                        (output / mode / "STOP").touch(exist_ok=True)

            for mode, process in list(processes.items()):
                return_code = process.poll()
                if return_code is None:
                    continue
                logs[mode].close()
                status = statuses.get(mode)
                terminal = status and status.get("state") == "finished"
                checkpoint = output / mode / "checkpoint.json.gz"
                if not stopping and not terminal and checkpoint.is_file() and restarts[mode] < 3:
                    restarts[mode] += 1
                    replacement, log = _start_agent(
                        mode,
                        output / mode,
                        config,
                        environment,
                        resume=True,
                    )
                    processes[mode] = replacement
                    logs[mode] = log

            all_exited = all(process.poll() is not None for process in processes.values())
            state = "stopping" if stopping and not all_exited else "running"
            if all_exited:
                state = "finished"
            arena_status = {
                "schema_version": 1,
                "state": state,
                "started_at": started_at,
                "updated_at": datetime.now(UTC).isoformat(),
                "elapsed_seconds": round(monotonic() - start_clock, 3),
                "dashboard_url": f"http://127.0.0.1:{config.port}/index.html",
                "process_id": os.getpid(),
                "agents": {
                    mode: {
                        "process_id": processes[mode].pid,
                        "process_alive": processes[mode].poll() is None,
                        "return_code": processes[mode].poll(),
                        "restarts": restarts[mode],
                        "state": None if statuses[mode] is None else statuses[mode].get("state"),
                        "stop_reason": (
                            None if statuses[mode] is None else statuses[mode].get("stop_reason")
                        ),
                    }
                    for mode in MODE_ORDER
                },
            }
            _atomic_json(output / "status.json", arena_status)
            _atomic_json(output / "history.json", {"agents": histories})
            _atomic_text(
                output / "index.html",
                render_arena_dashboard(arena_status, statuses, histories),
            )
            if all_exited:
                return 0 if all(process.returncode == 0 for process in processes.values()) else 1
            sleep(2)
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        if server is not None:
            server.shutdown()
            server.server_close()
        for mode, process in processes.items():
            if process.poll() is None:
                with contextlib.suppress(OSError):
                    (output / mode / "STOP").touch(exist_ok=True)
        deadline = monotonic() + 30
        for process in processes.values():
            if process.poll() is None:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=max(0, deadline - monotonic()))
        for process in processes.values():
            if process.poll() is None:
                with contextlib.suppress(OSError):
                    os.killpg(process.pid, signal.SIGTERM)
        for log in logs.values():
            with contextlib.suppress(Exception):
                log.close()


def show_arena_status(output: Path) -> int:
    status = _read_status(output / "status.json")
    if status is None:
        raise ValueError("Arena status.json does not exist or is invalid")
    print(f"Arena: {status['state']}")
    print(f"Dashboard: {status['dashboard_url']}")
    for mode in MODE_ORDER:
        agent = status["agents"][mode]
        print(
            f"{mode}: {agent['state'] or 'starting'} · alive={agent['process_alive']} · "
            f"restarts={agent['restarts']} · stop={agent['stop_reason'] or 'active'}"
        )
    return 0 if status["state"] != "failed" else 1


def request_arena_stop(output: Path) -> int:
    if not (output / "status.json").is_file():
        raise ValueError("Arena status.json does not exist")
    (output / "STOP").touch(exist_ok=True)
    print("Graceful arena stop requested; all four agents will checkpoint before exiting.")
    return 0
