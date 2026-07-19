from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from pokemon_red_ai.arena import (
    ArenaConfig,
    request_arena_stop,
    run_arena,
    show_arena_status,
)
from pokemon_red_ai.blind import RUN_MODES, BlindRunConfig, run_blind_experiment
from pokemon_red_ai.bootstrap import run_bootstrap_test
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.report import generate_run_report
from pokemon_red_ai.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_ai.smoke import run_smoke_test


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokemon-red-ai",
        description="Reproducible emulator harness for the Pokemon Red AI project.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Verify the ROM and emulator installation.")
    doctor.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")

    smoke = subparsers.add_parser("smoke-test", help="Run the Phase 0 emulator smoke test.")
    smoke.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    smoke.add_argument("--output", type=Path, help="New directory for the generated trace")
    smoke.add_argument("--boot-frames", type=int, default=1_800)

    bootstrap = subparsers.add_parser(
        "bootstrap-test",
        help="Reproducibly start a new game and reach RED's bedroom.",
    )
    bootstrap.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    bootstrap.add_argument("--output", type=Path, help="New directory for the generated trace")

    report = subparsers.add_parser(
        "report",
        help="Turn a sanitized JSONL trace into a local visual HTML report.",
    )
    report.add_argument("source", type=Path, help="A trace.jsonl file or its run directory")
    report.add_argument("--output", type=Path, help="HTML destination; defaults beside the trace")

    blind = subparsers.add_parser(
        "blind-run",
        help="Run a bounded game-naive pixels-only exploration from power-on.",
    )
    blind.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    blind.add_argument(
        "--output",
        type=Path,
        help="New run directory, or an existing one to resume",
    )
    blind.add_argument(
        "--mode",
        choices=tuple(sorted(RUN_MODES)),
        default="curious",
        help="Declared agent and information-boundary configuration",
    )
    blind.add_argument("--hours", type=float, default=8, help="Hard wall-clock limit")
    blind.add_argument("--max-actions", type=int, default=5_000_000)
    blind.add_argument("--seed", type=int, default=20_260_719)
    blind.add_argument("--branch-actions", type=int, default=32)
    blind.add_argument("--max-archive-cells", type=int, default=10_000)
    blind.add_argument("--seen-filter-mib", type=int, default=8)
    blind.add_argument("--q-policy-buckets", type=int, default=16_384)
    blind.add_argument("--screenshot-limit", type=int, default=96)
    blind.add_argument("--timelapse-minutes", type=float, default=15)
    blind.add_argument("--timelapse-limit", type=int, default=256)
    blind.add_argument("--status-seconds", type=float, default=30)
    blind.add_argument("--checkpoint-seconds", type=float, default=300)
    blind.add_argument("--max-output-mib", type=int, default=512)
    blind.add_argument("--min-free-gib", type=float, default=10)
    blind.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the checkpoint in --output using exactly the same configuration",
    )

    blind_status = subparsers.add_parser(
        "blind-status",
        help="Show the latest status for a pixels-only run.",
    )
    blind_status.add_argument("run_directory", type=Path)

    blind_stop = subparsers.add_parser(
        "blind-stop",
        help="Request a graceful checkpoint and stop for a pixels-only run.",
    )
    blind_stop.add_argument("run_directory", type=Path)

    arena = subparsers.add_parser(
        "arena-run",
        help="Run the four declared agents together with a live local dashboard.",
    )
    arena.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    arena.add_argument("--output", type=Path, required=True, help="New arena directory")
    arena.add_argument("--hours", type=float, default=8)
    arena.add_argument("--max-actions", type=int, default=50_000_000)
    arena.add_argument("--seed", type=int, default=20_260_719)
    arena.add_argument("--port", type=int, default=8_765)
    arena.add_argument("--status-seconds", type=float, default=10)
    arena.add_argument("--checkpoint-seconds", type=float, default=300)
    arena.add_argument("--seen-filter-mib", type=int, default=64)
    arena.add_argument("--q-policy-buckets", type=int, default=16_384)
    arena.add_argument("--timelapse-minutes", type=float, default=10)
    arena.add_argument("--max-output-mib-per-agent", type=int, default=2_048)
    arena.add_argument("--min-free-gib", type=float, default=50)

    arena_status = subparsers.add_parser("arena-status", help="Show four-agent arena status.")
    arena_status.add_argument("arena_directory", type=Path)
    arena_stop = subparsers.add_parser("arena-stop", help="Gracefully stop a four-agent arena.")
    arena_stop.add_argument("arena_directory", type=Path)

    return parser


def run_doctor(rom_argument: Path | None) -> int:
    rom_path = resolve_rom_path(rom_argument)
    fingerprint = verify_rom(rom_path)

    with PokemonRedEmulator(rom_path) as emulator:
        emulator.tick(1)
        cartridge_title = emulator.pyboy.cartridge_title
        screen_shape = tuple(int(value) for value in emulator.pyboy.screen.ndarray.shape)
        game_area_shape = tuple(int(value) for value in emulator.pyboy.game_area().shape)

    print("ROM verification: PASS")
    print(f"Cartridge title: {cartridge_title}")
    print(f"ROM SHA-1: {fingerprint.sha1}")
    print(f"ROM size: {fingerprint.size_bytes:,} bytes")
    print(f"Python: {platform.python_version()}")
    print(f"PyBoy: {version('pyboy')}")
    print(f"Screen buffer: {screen_shape}")
    print(f"Game-area buffer: {game_area_shape}")
    print("Private ROM path is not written to project logs.")
    return 0


def run_smoke(args: argparse.Namespace) -> int:
    if args.boot_frames < 1:
        raise ValueError("--boot-frames must be at least 1")
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    result = run_smoke_test(
        rom_path,
        fingerprint,
        run_directory=args.output,
        boot_frames=args.boot_frames,
    )

    print(f"Smoke test: {'PASS' if result.passed else 'FAIL'}")
    print(f"Controller changed screen: {result.input_changed_screen}")
    print(f"Save-state replay deterministic: {result.save_state_is_deterministic}")
    print(f"Trace and screenshots: {result.run_directory.resolve()}")
    return 0 if result.passed else 1


def run_bootstrap(args: argparse.Namespace) -> int:
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    result = run_bootstrap_test(rom_path, fingerprint, run_directory=args.output)

    print(f"New-game bootstrap: {'PASS' if result.passed else 'FAIL'}")
    both_reached_bedroom = result.first.reached_bedroom and result.second.reached_bedroom
    print(f"Reached bedroom twice: {both_reached_bedroom}")
    print(f"Clean boots deterministic: {result.deterministic}")
    print(f"One-tile DOWN calibrated: {result.first.one_tile_down_verified}")
    print(f"Final state: {result.first.state.public_dict()}")
    print(f"Trace and screenshots: {result.run_directory.resolve()}")
    return 0 if result.passed else 1


def run_report(args: argparse.Namespace) -> int:
    source: Path = args.source.expanduser()
    trace_path = source / "trace.jsonl" if source.is_dir() else source
    report_path = generate_run_report(trace_path, args.output)
    print(f"Run report: {report_path.resolve()}")
    return 0


def run_blind(args: argparse.Namespace) -> int:
    if args.resume and args.output is None:
        raise ValueError("--resume requires --output")
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    config = BlindRunConfig(
        mode=args.mode,
        duration_seconds=args.hours * 3_600,
        max_actions=args.max_actions,
        seed=args.seed,
        branch_actions=args.branch_actions,
        max_archive_cells=args.max_archive_cells,
        seen_filter_bytes=args.seen_filter_mib * 1024 * 1024,
        q_policy_buckets=args.q_policy_buckets,
        screenshot_limit=args.screenshot_limit,
        timelapse_interval_seconds=args.timelapse_minutes * 60,
        timelapse_limit=args.timelapse_limit,
        status_interval_seconds=args.status_seconds,
        checkpoint_interval_seconds=args.checkpoint_seconds,
        max_output_bytes=args.max_output_mib * 1024 * 1024,
        min_free_bytes=int(args.min_free_gib * 1024 * 1024 * 1024),
    )
    result = run_blind_experiment(
        rom_path,
        fingerprint,
        config=config,
        run_directory=args.output,
        resume=args.resume,
    )
    print(f"Pixels-only run: {result.stop_reason}")
    print(f"Actions: {result.counters.total_actions:,}")
    print(f"Visual cells: {result.counters.unique_visual_cells:,}")
    print(f"Archive cells: {result.archive_cells:,}")
    print(f"Dashboard: {(result.run_directory / 'index.html').resolve()}")
    healthy_stops = {
        "action_limit",
        "duration_limit",
        "low_disk_space",
        "output_limit",
        "sigint",
        "sigterm",
        "stop_requested",
    }
    return 0 if result.stop_reason in healthy_stops else 1


def run_agent_arena(args: argparse.Namespace) -> int:
    if not 1 <= args.port <= 65_535:
        raise ValueError("--port must be between 1 and 65535")
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    config = ArenaConfig(
        duration_seconds=args.hours * 3_600,
        max_actions=args.max_actions,
        seed=args.seed,
        port=args.port,
        status_interval_seconds=args.status_seconds,
        checkpoint_interval_seconds=args.checkpoint_seconds,
        max_output_mib_per_agent=args.max_output_mib_per_agent,
        min_free_gib=args.min_free_gib,
        seen_filter_mib=args.seen_filter_mib,
        q_policy_buckets=args.q_policy_buckets,
        timelapse_minutes=args.timelapse_minutes,
    )
    return run_arena(
        rom_path,
        fingerprint,
        output=args.output.expanduser().resolve(),
        config=config,
    )


def show_blind_status(run_directory: Path) -> int:
    status_path = run_directory.expanduser() / "status.json"
    if not status_path.is_file():
        raise ValueError("Run status.json does not exist")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    updated_at = datetime.fromisoformat(status["updated_at"])
    heartbeat_age = max(0.0, (datetime.now(UTC) - updated_at).total_seconds())
    process_id = int(status.get("process_id", 0))
    process_alive = False
    if process_id > 0:
        try:
            os.kill(process_id, 0)
            process_alive = True
        except OSError:
            process_alive = False
    heartbeat_limit = max(90.0, float(status.get("heartbeat_interval_seconds", 30)) * 3)
    heartbeat_state = "fresh" if heartbeat_age <= heartbeat_limit else "stale"
    print(f"State: {status['state']}")
    print(f"Mode: {status['mode']}")
    print(f"Elapsed seconds: {status['elapsed_seconds']:,.1f}")
    print(f"Actions: {status['total_actions']:,}")
    print(f"Visual cells: {status['unique_visual_cells']:,}")
    print(f"Archive cells: {status['archive_cells']:,}")
    print(f"Actions/second: {status['actions_per_second']:,.2f}")
    print(f"Heartbeat: {heartbeat_state} ({heartbeat_age:,.1f} seconds old)")
    print(f"Process alive: {process_alive}")
    print(f"Stop reason: {status.get('stop_reason') or 'still running'}")
    if status["state"] == "running" and (not process_alive or heartbeat_state == "stale"):
        return 1
    return 0 if status["state"] != "failed" else 1


def request_blind_stop(run_directory: Path) -> int:
    resolved = run_directory.expanduser()
    if not (resolved / "status.json").is_file():
        raise ValueError("Run status.json does not exist")
    (resolved / "STOP").touch(exist_ok=True)
    print("Graceful stop requested; the runner will checkpoint before exiting.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return run_doctor(args.rom)
        if args.command == "smoke-test":
            return run_smoke(args)
        if args.command == "bootstrap-test":
            return run_bootstrap(args)
        if args.command == "report":
            return run_report(args)
        if args.command == "blind-run":
            return run_blind(args)
        if args.command == "blind-status":
            return show_blind_status(args.run_directory)
        if args.command == "blind-stop":
            return request_blind_stop(args.run_directory)
        if args.command == "arena-run":
            return run_agent_arena(args)
        if args.command == "arena-status":
            return show_arena_status(args.arena_directory.expanduser().resolve())
        if args.command == "arena-stop":
            return request_arena_stop(args.arena_directory.expanduser().resolve())
    except (OSError, RomValidationError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2
