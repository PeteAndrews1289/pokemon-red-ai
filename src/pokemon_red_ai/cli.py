from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path

from pokemon_red_ai.apprentice_data import (
    capture_apprentice_dataset,
    verify_apprentice_dataset,
)
from pokemon_red_ai.apprentice_overnight import (
    OvernightApprenticeConfig,
    run_overnight_apprentice,
)
from pokemon_red_ai.apprentice_qualification import (
    qualify_stage0_composite,
    qualify_stage0_data,
)
from pokemon_red_ai.apprentice_stage0 import (
    Stage0TrainingConfig,
    evaluate_stage0_policy,
    train_stage0_overfit,
)
from pokemon_red_ai.arena import (
    FINAL_ARENA_MAX_ACTIONS,
    FINAL_ARENA_Q_POLICY_BUCKETS,
    ArenaConfig,
    request_arena_stop,
    run_arena,
    show_arena_status,
)
from pokemon_red_ai.blind import RUN_MODES, BlindRunConfig, run_blind_experiment
from pokemon_red_ai.bootstrap import run_bootstrap_test
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.evolution import EvolutionConfig, run_evolution_experiment
from pokemon_red_ai.evolution_lab import (
    DEFAULT_EVOLUTION_LAB_ACTIONS,
    EvolutionLabConfig,
    request_evolution_lab_stop,
    run_evolution_lab,
    show_evolution_lab_status,
)
from pokemon_red_ai.expedition_runner import (
    APPRENTICE_HYBRID_EMITTER,
    FRONTIER_LEARNING_EMITTER,
    RANDOM_EXPEDITION_EMITTER,
    ExpeditionRunConfig,
    request_expedition_stop,
    run_expedition,
    show_expedition_status,
)
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
    blind.add_argument("--q-n-step", type=int, default=128)
    blind.add_argument("--replay-capacity", type=int, default=100_000)
    blind.add_argument("--replay-batch-size", type=int, default=16)
    blind.add_argument("--replay-interval", type=int, default=4)
    blind.add_argument("--important-replay-capacity", type=int, default=10_000)
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

    evolution = subparsers.add_parser(
        "evolution-run",
        help="Run clean-start recurrent policy neuroevolution with a live dashboard.",
    )
    evolution.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    evolution.add_argument("--output", type=Path, required=True)
    evolution.add_argument("--hours", type=float, default=2)
    evolution.add_argument("--max-actions", type=int, default=20_000_000)
    evolution.add_argument("--seed", type=int, default=20_260_723)
    evolution.add_argument("--population-size", type=int, default=16)
    evolution.add_argument("--candidate-actions", type=int, default=12_000)
    evolution.add_argument("--archive-capacity", type=int, default=512)
    evolution.add_argument("--mutation-probability", type=float, default=0.10)
    evolution.add_argument("--mutation-sigma", type=float, default=0.05)
    evolution.add_argument("--large-mutation-probability", type=float, default=0.05)
    evolution.add_argument("--large-mutation-sigma", type=float, default=0.20)
    evolution.add_argument(
        "--selection-strategy",
        choices=("uniform", "frontier"),
        default="uniform",
    )
    evolution.add_argument("--frontier-probability", type=float, default=0.80)
    evolution.add_argument("--frontier-tournament-size", type=int, default=3)
    evolution.add_argument(
        "--mutation-profile",
        choices=("broad", "gentle", "multiscale"),
        default="broad",
    )
    evolution.add_argument(
        "--seed-archive",
        type=Path,
        help=(
            "Completed evolution run or checkpoint whose neural archive starts this run; "
            "pass the same archive again with --resume"
        ),
    )
    evolution.add_argument("--seen-filter-mib", type=int, default=8)
    evolution.add_argument("--screenshot-limit", type=int, default=128)
    evolution.add_argument("--status-seconds", type=float, default=10)
    evolution.add_argument("--checkpoint-seconds", type=float, default=300)
    evolution.add_argument("--max-output-mib", type=int, default=2_048)
    evolution.add_argument("--min-free-gib", type=float, default=50)
    evolution.add_argument("--resume", action="store_true")

    evolution_lab = subparsers.add_parser(
        "evolution-lab-run",
        help="Run the paired 2x3 selection-by-mutation experiment and live dashboard.",
    )
    evolution_lab.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    evolution_lab.add_argument("--output", type=Path, required=True)
    evolution_lab.add_argument(
        "--seed-archive",
        type=Path,
        required=True,
        help="Completed evolution run or checkpoint containing the sealed starting archive",
    )
    evolution_lab.add_argument("--hours", type=float, default=4)
    evolution_lab.add_argument(
        "--max-actions-per-lane",
        type=int,
        default=DEFAULT_EVOLUTION_LAB_ACTIONS,
    )
    evolution_lab.add_argument("--seed", type=int, default=20_260_725)
    evolution_lab.add_argument("--unpaired-seeds", action="store_true")
    evolution_lab.add_argument("--port", type=int, default=8_765)
    evolution_lab.add_argument("--population-size", type=int, default=16)
    evolution_lab.add_argument("--candidate-actions", type=int, default=12_000)
    evolution_lab.add_argument("--archive-capacity", type=int, default=512)
    evolution_lab.add_argument("--frontier-probability", type=float, default=0.80)
    evolution_lab.add_argument("--frontier-tournament-size", type=int, default=3)
    evolution_lab.add_argument("--seen-filter-mib", type=int, default=64)
    evolution_lab.add_argument("--screenshot-limit", type=int, default=128)
    evolution_lab.add_argument("--status-seconds", type=float, default=10)
    evolution_lab.add_argument("--checkpoint-seconds", type=float, default=300)
    evolution_lab.add_argument("--narrative-minutes", type=float, default=60)
    evolution_lab.add_argument("--visual-minutes", type=float, default=10)
    evolution_lab.add_argument("--poll-seconds", type=float, default=2)
    evolution_lab.add_argument("--max-output-mib-per-lane", type=int, default=2_048)
    evolution_lab.add_argument("--min-free-gib", type=float, default=50)
    evolution_lab.add_argument(
        "--resume",
        action="store_true",
        help="Recover all six lanes from an existing lab with the identical configuration",
    )

    evolution_lab_status = subparsers.add_parser(
        "evolution-lab-status",
        help="Show the latest six-lane evolution lab status.",
    )
    evolution_lab_status.add_argument("lab_directory", type=Path)
    evolution_lab_stop = subparsers.add_parser(
        "evolution-lab-stop",
        help="Gracefully checkpoint and stop every evolution lab lane.",
    )
    evolution_lab_stop.add_argument("lab_directory", type=Path)

    expedition = subparsers.add_parser(
        "expedition-run",
        help="Run bounded checkpoint-assisted exploration with a privileged referee.",
    )
    expedition.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    expedition.add_argument("--output", type=Path, required=True)
    expedition.add_argument("--hours", type=float, default=2)
    expedition.add_argument("--max-actions", type=int, default=1_000_000)
    expedition.add_argument("--seed", type=int, default=20_260_719)
    expedition.add_argument("--archive-capacity", type=int, default=4_096)
    expedition.add_argument("--min-suffix-actions", type=int, default=32)
    expedition.add_argument("--max-suffix-actions", type=int, default=1_024)
    expedition.add_argument("--attempts-per-expansion", type=int, default=8)
    expedition.add_argument("--frontier-capture-actions", type=int, default=8)
    expedition.add_argument("--loop-window-actions", type=int, default=64)
    expedition.add_argument("--loop-repeat-limit", type=int, default=12)
    expedition.add_argument("--frontier-probability", type=float, default=0.75)
    expedition.add_argument("--rehearsal-probability", type=float, default=0.10)
    expedition.add_argument("--promotion-replay-passes", type=int, default=3)
    expedition.add_argument(
        "--port",
        type=int,
        default=8_765,
        help="127.0.0.1 dashboard port; pass 0 to disable serving",
    )
    expedition.add_argument("--status-seconds", type=float, default=10)
    expedition.add_argument("--max-output-mib", type=int, default=4_096)
    expedition.add_argument("--min-free-gib", type=float, default=50)
    expedition.add_argument(
        "--apprentice-model",
        type=Path,
        help="Completed private curriculum run whose frozen learner guides the expedition",
    )
    expedition.add_argument("--apprentice-pre-frontier-epsilon", type=float, default=0.02)
    expedition.add_argument("--apprentice-post-frontier-epsilon", type=float, default=0.35)
    expedition.add_argument(
        "--frontier-learning",
        action="store_true",
        help=(
            "Update the pixel policy only from replay-verified milestone suffixes and target "
            "the complete milestone catalogue"
        ),
    )
    expedition.add_argument("--frontier-learning-rate", type=float, default=0.0001)
    expedition.add_argument("--frontier-training-epochs", type=int, default=2)
    expedition.add_argument("--frontier-max-epsilon", type=float, default=1.0)
    expedition.add_argument("--frontier-epsilon-ramp-actions", type=int, default=250_000)
    expedition.add_argument("--frontier-loop-escape-actions", type=int, default=64)
    expedition.add_argument("--frontier-loop-escape-attempts", type=int, default=2)
    expedition.add_argument("--resume", action="store_true")

    expedition_status = subparsers.add_parser(
        "expedition-status",
        help="Show the latest checkpoint expedition status.",
    )
    expedition_status.add_argument("run_directory", type=Path)
    expedition_stop = subparsers.add_parser(
        "expedition-stop",
        help="Gracefully stop a checkpoint expedition at a short-suffix boundary.",
    )
    expedition_stop.add_argument("run_directory", type=Path)

    ppo = subparsers.add_parser(
        "ppo-run",
        help="Train one recurrent PPO policy across several verified Pokémon Red environments.",
    )
    ppo.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    ppo.add_argument("--output", type=Path, required=True)
    ppo.add_argument(
        "--curriculum-source",
        type=Path,
        required=True,
        help="Verified checkpoint expedition that seeds the private curriculum",
    )
    ppo.add_argument(
        "--learner",
        type=Path,
        required=True,
        help="Frontier learner checkpoint used to warm-start the visual policy",
    )
    ppo.add_argument("--mode", choices=("pixels", "privileged"), default="pixels")
    ppo.add_argument("--hours", type=float, default=8)
    ppo.add_argument("--max-actions", type=int, default=20_000_000)
    ppo.add_argument("--seed", type=int, default=20_260_752)
    ppo.add_argument("--environments", type=int, default=4)
    ppo.add_argument("--episode-actions", type=int, default=16_384)
    ppo.add_argument("--rollout-steps", type=int, default=256)
    ppo.add_argument("--batch-size", type=int, default=256)
    ppo.add_argument("--epochs", type=int, default=4)
    ppo.add_argument("--learning-rate", type=float, default=0.00025)
    ppo.add_argument("--gamma", type=float, default=0.997)
    ppo.add_argument("--entropy", type=float, default=0.01)
    ppo.add_argument("--reward-scale", type=float, default=0.01)
    ppo.add_argument("--promotion-replays", type=int, default=3)
    ppo.add_argument("--checkpoint-actions", type=int, default=16_384)
    ppo.add_argument("--status-seconds", type=float, default=2)
    ppo.add_argument("--narrative-minutes", type=float, default=60)
    ppo.add_argument("--port", type=int, default=8_773)
    ppo.add_argument("--max-output-mib", type=int, default=102_400)
    ppo.add_argument("--min-free-gib", type=float, default=50)
    ppo.add_argument("--resume", action="store_true")

    ppo_status = subparsers.add_parser(
        "ppo-status", help="Show the current parallel PPO learning status."
    )
    ppo_status.add_argument("run_directory", type=Path)
    ppo_stop = subparsers.add_parser(
        "ppo-stop", help="Request a checkpoint and graceful stop for parallel PPO."
    )
    ppo_stop.add_argument("run_directory", type=Path)

    arena = subparsers.add_parser(
        "arena-run",
        help="Run the four declared agents together with a live local dashboard.",
    )
    arena.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    arena.add_argument("--output", type=Path, required=True, help="New arena directory")
    arena.add_argument("--hours", type=float, default=8)
    arena.add_argument("--max-actions", type=int, default=FINAL_ARENA_MAX_ACTIONS)
    arena.add_argument("--seed", type=int, default=20_260_719)
    arena.add_argument("--port", type=int, default=8_765)
    arena.add_argument("--status-seconds", type=float, default=10)
    arena.add_argument("--checkpoint-seconds", type=float, default=300)
    arena.add_argument("--seen-filter-mib", type=int, default=64)
    arena.add_argument("--q-policy-buckets", type=int, default=FINAL_ARENA_Q_POLICY_BUCKETS)
    arena.add_argument("--q-n-step", type=int, default=128)
    arena.add_argument("--replay-capacity", type=int, default=100_000)
    arena.add_argument("--replay-batch-size", type=int, default=16)
    arena.add_argument("--replay-interval", type=int, default=4)
    arena.add_argument("--important-replay-capacity", type=int, default=10_000)
    arena.add_argument("--timelapse-minutes", type=float, default=10)
    arena.add_argument("--max-output-mib-per-agent", type=int, default=2_048)
    arena.add_argument("--min-free-gib", type=float, default=50)
    arena.add_argument("--evolution-population-size", type=int, default=16)
    arena.add_argument("--evolution-candidate-actions", type=int, default=12_000)
    arena.add_argument("--evolution-archive-capacity", type=int, default=512)

    arena_status = subparsers.add_parser("arena-status", help="Show four-agent arena status.")
    arena_status.add_argument("arena_directory", type=Path)
    arena_stop = subparsers.add_parser("arena-stop", help="Gracefully stop a four-agent arena.")
    arena_stop.add_argument("arena_directory", type=Path)

    apprentice_extract = subparsers.add_parser(
        "apprentice-extract",
        help="Turn one explicitly verified expedition promotion into a private pixel dataset.",
    )
    apprentice_extract.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    apprentice_extract.add_argument(
        "--expedition",
        type=Path,
        required=True,
        help="Expedition run directory or its frontier store",
    )
    apprentice_extract.add_argument("--cell-id", required=True)
    apprentice_extract.add_argument("--expected-lineage-sha256", required=True)
    apprentice_extract.add_argument("--output", type=Path, required=True)

    apprentice_verify = subparsers.add_parser(
        "apprentice-dataset-verify",
        help="Verify every hash and invariant in a private Visual Apprentice dataset.",
    )
    apprentice_verify.add_argument("dataset", type=Path)

    apprentice_data_qualify = subparsers.add_parser(
        "apprentice-data-qualify",
        help="Require two independent captures with one exact logical dataset hash.",
    )
    apprentice_data_qualify.add_argument("--first", type=Path, required=True)
    apprentice_data_qualify.add_argument("--second", type=Path, required=True)
    apprentice_data_qualify.add_argument("--output", type=Path, required=True)

    apprentice_overfit = subparsers.add_parser(
        "apprentice-overfit",
        help="Deliberately overfit the Stage-0 recurrent policy to one verified trajectory.",
    )
    apprentice_overfit.add_argument("--dataset", type=Path, required=True)
    apprentice_overfit.add_argument("--output", type=Path, required=True)
    apprentice_overfit.add_argument(
        "--port",
        type=int,
        default=8_770,
        help="127.0.0.1 live dashboard port; pass 0 to disable serving",
    )

    apprentice_evaluate = subparsers.add_parser(
        "apprentice-evaluate",
        help="Give one frozen Stage-0 policy a clean-power-on emulator exam.",
    )
    apprentice_evaluate.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    apprentice_evaluate.add_argument("--model", type=Path, required=True)
    apprentice_evaluate.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Exact training dataset binding the model to the certified route",
    )
    apprentice_evaluate.add_argument("--output", type=Path, required=True)

    apprentice_qualify = subparsers.add_parser(
        "apprentice-stage0-qualify",
        help="Issue Stage-0 PASS only when data, offline, and live gates agree.",
    )
    apprentice_qualify.add_argument("--data-qualification", type=Path, required=True)
    apprentice_qualify.add_argument("--training", type=Path, required=True)
    apprentice_qualify.add_argument("--evaluation", type=Path, required=True)
    apprentice_qualify.add_argument("--output", type=Path, required=True)

    apprentice_curriculum = subparsers.add_parser(
        "apprentice-curriculum-run",
        help="Run the bounded reverse-curriculum self-imitation development pilot.",
    )
    apprentice_curriculum.add_argument("--rom", type=Path, help="Private path to Pokemon Red.gb")
    apprentice_curriculum.add_argument("--dataset", type=Path, required=True)
    apprentice_curriculum.add_argument("--model", type=Path, required=True)
    apprentice_curriculum.add_argument("--output", type=Path, required=True)
    apprentice_curriculum.add_argument("--hours", type=float, default=8)
    apprentice_curriculum.add_argument("--max-actions", type=int, default=15_000_000)
    apprentice_curriculum.add_argument(
        "--stagnation-actions", type=int, default=2_000_000
    )
    apprentice_curriculum.add_argument("--seed", type=int, default=20_260_743)
    apprentice_curriculum.add_argument("--max-rss-mib", type=float, default=1_536)
    apprentice_curriculum.add_argument("--min-free-gib", type=float, default=50)
    apprentice_curriculum.add_argument("--torch-threads", type=int, default=4)
    apprentice_curriculum.add_argument(
        "--port",
        type=int,
        default=8_771,
        help="127.0.0.1 dashboard port; pass 0 to disable serving",
    )
    apprentice_curriculum.add_argument(
        "--canary",
        action="store_true",
        help="Use a three-minute relaxed plumbing check that cannot qualify a model",
    )
    apprentice_curriculum.add_argument("--resume", action="store_true")

    apprentice_curriculum_status = subparsers.add_parser(
        "apprentice-curriculum-status",
        help="Show the latest reverse-curriculum heartbeat.",
    )
    apprentice_curriculum_status.add_argument("run_directory", type=Path)
    apprentice_curriculum_stop = subparsers.add_parser(
        "apprentice-curriculum-stop",
        help="Request a graceful reverse-curriculum checkpoint and stop.",
    )
    apprentice_curriculum_stop.add_argument("run_directory", type=Path)

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
        q_n_step=args.q_n_step,
        replay_capacity=args.replay_capacity,
        replay_batch_size=args.replay_batch_size,
        replay_interval=args.replay_interval,
        important_replay_capacity=args.important_replay_capacity,
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
        q_n_step=args.q_n_step,
        replay_capacity=args.replay_capacity,
        replay_batch_size=args.replay_batch_size,
        replay_interval=args.replay_interval,
        important_replay_capacity=args.important_replay_capacity,
        timelapse_minutes=args.timelapse_minutes,
        evolution_population_size=args.evolution_population_size,
        evolution_candidate_actions=args.evolution_candidate_actions,
        evolution_archive_capacity=args.evolution_archive_capacity,
    )
    return run_arena(
        rom_path,
        fingerprint,
        output=args.output.expanduser().resolve(),
        config=config,
    )


def run_evolution(args: argparse.Namespace) -> int:
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    config = EvolutionConfig(
        duration_seconds=args.hours * 3_600,
        max_actions=args.max_actions,
        seed=args.seed,
        population_size=args.population_size,
        candidate_actions=args.candidate_actions,
        archive_capacity=args.archive_capacity,
        mutation_probability=args.mutation_probability,
        mutation_sigma=args.mutation_sigma,
        large_mutation_probability=args.large_mutation_probability,
        large_mutation_sigma=args.large_mutation_sigma,
        selection_strategy=args.selection_strategy,
        frontier_probability=args.frontier_probability,
        tournament_size=args.frontier_tournament_size,
        mutation_profile=args.mutation_profile,
        seed_archive=args.seed_archive,
        seen_filter_bytes=args.seen_filter_mib * 1024 * 1024,
        screenshot_limit=args.screenshot_limit,
        status_interval_seconds=args.status_seconds,
        checkpoint_interval_seconds=args.checkpoint_seconds,
        max_output_bytes=args.max_output_mib * 1024 * 1024,
        min_free_bytes=int(args.min_free_gib * 1024 * 1024 * 1024),
    )
    result = run_evolution_experiment(
        rom_path,
        fingerprint,
        config=config,
        run_directory=args.output.expanduser().resolve(),
        resume=args.resume,
    )
    print(f"Evolution run: {result.stop_reason}")
    print(f"Actions: {result.total_actions:,}")
    print(f"Evaluated children: {result.evaluations:,}")
    print(f"Archive cells: {result.archive_cells:,}")
    healthy = {
        "action_limit",
        "duration_limit",
        "low_disk_space",
        "output_limit",
        "sigint",
        "sigterm",
        "stop_requested",
    }
    return 0 if result.stop_reason in healthy else 1


def run_evolution_lab_command(args: argparse.Namespace) -> int:
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    config = EvolutionLabConfig(
        duration_seconds=args.hours * 3_600,
        max_actions_per_lane=args.max_actions_per_lane,
        seed=args.seed,
        paired_seed=not args.unpaired_seeds,
        port=args.port,
        population_size=args.population_size,
        candidate_actions=args.candidate_actions,
        archive_capacity=args.archive_capacity,
        frontier_probability=args.frontier_probability,
        frontier_tournament_size=args.frontier_tournament_size,
        seen_filter_mib=args.seen_filter_mib,
        screenshot_limit=args.screenshot_limit,
        status_interval_seconds=args.status_seconds,
        checkpoint_interval_seconds=args.checkpoint_seconds,
        narrative_interval_seconds=args.narrative_minutes * 60,
        visual_interval_seconds=args.visual_minutes * 60,
        poll_interval_seconds=args.poll_seconds,
        max_output_mib_per_lane=args.max_output_mib_per_lane,
        min_free_gib=args.min_free_gib,
    )
    return run_evolution_lab(
        rom_path,
        fingerprint,
        output=args.output.expanduser().resolve(),
        seed_archive=args.seed_archive.expanduser().resolve(),
        config=config,
        resume=args.resume,
    )


def run_expedition_command(args: argparse.Namespace) -> int:
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    apprentice_model = None
    apprentice_model_sha256 = ""
    emitter_kind = RANDOM_EXPEDITION_EMITTER
    if args.frontier_learning and args.apprentice_model is None:
        raise ValueError("--frontier-learning requires --apprentice-model")
    if args.apprentice_model is not None:
        apprentice_model = args.apprentice_model.expanduser().resolve()
        learner_metadata_path = apprentice_model / "learner.json"
        if not learner_metadata_path.is_file():
            raise ValueError("Apprentice model directory does not contain learner.json")
        learner_metadata = json.loads(learner_metadata_path.read_text(encoding="utf-8"))
        apprentice_model_sha256 = str(learner_metadata.get("file_sha256", ""))
        emitter_kind = (
            FRONTIER_LEARNING_EMITTER if args.frontier_learning else APPRENTICE_HYBRID_EMITTER
        )
    config = ExpeditionRunConfig(
        duration_seconds=args.hours * 3_600,
        max_actions=args.max_actions,
        seed=args.seed,
        archive_capacity=args.archive_capacity,
        min_suffix_actions=args.min_suffix_actions,
        max_suffix_actions=args.max_suffix_actions,
        attempts_per_expansion=args.attempts_per_expansion,
        frontier_capture_interval_actions=args.frontier_capture_actions,
        loop_window_actions=args.loop_window_actions,
        loop_repeat_limit=args.loop_repeat_limit,
        frontier_probability=args.frontier_probability,
        rehearsal_probability=args.rehearsal_probability,
        promotion_replay_passes=args.promotion_replay_passes,
        dashboard_port=args.port,
        status_interval_seconds=args.status_seconds,
        max_output_bytes=args.max_output_mib * 1024 * 1024,
        min_free_bytes=int(args.min_free_gib * 1024 * 1024 * 1024),
        emitter_kind=emitter_kind,
        apprentice_model_sha256=apprentice_model_sha256,
        apprentice_pre_frontier_epsilon=args.apprentice_pre_frontier_epsilon,
        apprentice_post_frontier_epsilon=args.apprentice_post_frontier_epsilon,
        frontier_learning_rate=args.frontier_learning_rate,
        frontier_training_epochs=args.frontier_training_epochs,
        frontier_max_epsilon=args.frontier_max_epsilon,
        frontier_epsilon_ramp_actions=args.frontier_epsilon_ramp_actions,
        frontier_loop_escape_actions=args.frontier_loop_escape_actions,
        frontier_loop_escape_attempts=args.frontier_loop_escape_attempts,
    )
    if args.port:
        print(
            f"Live dashboard while the expedition is running: "
            f"http://127.0.0.1:{args.port}/index.html",
            flush=True,
        )
    result = run_expedition(
        rom_path,
        fingerprint,
        config=config,
        run_directory=args.output,
        resume=args.resume,
        apprentice_model_directory=apprentice_model,
    )
    print(f"Checkpoint expedition: {result.stop_reason}")
    print(f"Actions: {result.counters.total_actions:,}")
    print(f"Attempts: {result.counters.attempts:,}")
    print(f"Active frontier cells: {result.archive_cells:,}")
    print(f"Best milestone: {result.best_milestone.label}")
    print(f"Finished dashboard: {(result.run_directory / 'index.html').resolve()}")
    healthy = {
        "action_limit",
        "duration_limit",
        "low_disk_space",
        "output_limit",
        "sigint",
        "sigterm",
        "stop_requested",
        "hall_of_fame_verified",
    }
    return 0 if result.stop_reason in healthy else 1


def run_parallel_ppo_command(args: argparse.Namespace) -> int:
    from pokemon_red_ai.ppo_training import ParallelPpoConfig, run_parallel_ppo

    rom_path = resolve_rom_path(args.rom)
    learner = args.learner.expanduser().resolve()
    if not learner.is_file():
        raise ValueError("PPO learner checkpoint does not exist")
    config = ParallelPpoConfig(
        mode=args.mode,
        duration_seconds=args.hours * 3_600,
        max_actions=args.max_actions,
        seed=args.seed,
        environments=args.environments,
        episode_actions=args.episode_actions,
        rollout_steps=args.rollout_steps,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        gamma=args.gamma,
        entropy_coefficient=args.entropy,
        reward_scale=args.reward_scale,
        promotion_replays=args.promotion_replays,
        checkpoint_actions=args.checkpoint_actions,
        status_seconds=args.status_seconds,
        narrative_seconds=args.narrative_minutes * 60,
        dashboard_port=args.port,
        max_output_bytes=args.max_output_mib * 1024 * 1024,
        min_free_bytes=int(args.min_free_gib * 1024**3),
    )
    if args.port:
        print(
            f"Live parallel PPO dashboard: http://127.0.0.1:{args.port}/index.html",
            flush=True,
        )
    status = run_parallel_ppo(
        rom_path,
        args.output,
        args.curriculum_source.expanduser().resolve(),
        learner,
        config,
        resume=args.resume,
    )
    print(f"Parallel PPO stopped: {status['stop_reason']}")
    print(f"Combined actions: {status['total_actions']:,}")
    print(f"PPO updates: {status['ppo_updates']:,}")
    print(f"Best verified milestone: {status['best_milestone']['label']}")
    print(f"Verified promotions: {status['verified_promotions']:,}")
    return 0 if status["state"] != "failed" else 1


def show_parallel_ppo_command(run_directory: Path) -> int:
    from pokemon_red_ai.ppo_training import show_parallel_ppo_status

    status = show_parallel_ppo_status(run_directory)
    print(f"State: {status['state']}")
    print(f"Combined actions: {status['total_actions']:,}")
    print(f"Actions/second: {status['actions_per_second']:,.2f}")
    print(f"Best verified milestone: {status['best_milestone']['label']}")
    print(f"Verified promotions: {status['verified_promotions']:,}")
    print(f"Stop reason: {status.get('stop_reason') or 'still running'}")
    return 0 if status["state"] != "failed" else 1


def request_parallel_ppo_stop_command(run_directory: Path) -> int:
    from pokemon_red_ai.ppo_training import request_parallel_ppo_stop

    request_parallel_ppo_stop(run_directory)
    print("Graceful stop requested; PPO will checkpoint after the current vector step.")
    return 0


def run_apprentice_extract(args: argparse.Namespace) -> int:
    rom_path = resolve_rom_path(args.rom)
    expedition = args.expedition.expanduser().resolve()
    nested_store = expedition / "frontier"
    store = nested_store if (nested_store / "manifest.json").is_file() else expedition
    manifest = capture_apprentice_dataset(
        rom_path,
        store,
        args.cell_id,
        args.expected_lineage_sha256,
        args.output,
    )
    print("Visual Apprentice dataset: PASS")
    print(f"Verified actions: {manifest['action_count']:,}")
    print(f"Decision-boundary frames: {manifest['decision_boundary_frame_count']:,}")
    print(f"Dataset SHA-256: {manifest['dataset_sha256']}")
    print(f"Private dataset: {args.output.expanduser().resolve()}")
    return 0


def run_apprentice_verify(args: argparse.Namespace) -> int:
    manifest = verify_apprentice_dataset(args.dataset)
    print("Visual Apprentice dataset integrity: PASS")
    print(f"Actions: {manifest['action_count']:,}")
    print(f"Dataset SHA-256: {manifest['dataset_sha256']}")
    return 0


def run_apprentice_data_qualify(args: argparse.Namespace) -> int:
    receipt = qualify_stage0_data(args.first, args.second, args.output)
    print("Visual Apprentice two-capture data gate: PASS")
    print(f"Dataset SHA-256: {receipt['identities']['dataset_sha256']}")
    print(f"Qualification bundle: {args.output.expanduser().resolve()}")
    return 0


class _QuietDashboardHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return None


@contextmanager
def _serve_apprentice_dashboard(directory: Path, port: int) -> Iterator[None]:
    if port == 0:
        yield
        return
    if not 1 <= port <= 65_535:
        raise ValueError("--port must be zero or between 1 and 65535")
    handler = partial(_QuietDashboardHandler, directory=str(directory.expanduser().resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print(
            f"Live Visual Apprentice dashboard: http://127.0.0.1:{port}/index.html",
            flush=True,
        )
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_apprentice_overfit(args: argparse.Namespace) -> int:
    config = Stage0TrainingConfig()
    with _serve_apprentice_dashboard(args.output, args.port):
        result = train_stage0_overfit(args.dataset, args.output, config=config)
    print(f"Stage-0 offline gate: {'PASS' if result.passed else 'FAIL'}")
    print(f"Stop reason: {result.stop_reason}")
    print(f"Epochs: {result.epochs:,}")
    print(
        f"Teacher-forced exact labels: "
        f"{result.offline.teacher_correct:,}/{result.action_count:,}"
    )
    print(
        f"Predicted-feedback exact labels: "
        f"{result.offline.feedback_correct:,}/{result.action_count:,}"
    )
    print(f"Frozen model SHA-256: {result.model_sha256}")
    print(f"Dashboard: {(result.output_directory / 'index.html').resolve()}")
    return 0 if result.passed else 1


def run_apprentice_evaluate(args: argparse.Namespace) -> int:
    rom_path = resolve_rom_path(args.rom)
    result = evaluate_stage0_policy(
        rom_path,
        args.model,
        args.output,
        max_actions=1_000,
        dataset_path=args.dataset,
    )
    print(f"Stage-0 clean-power-on gate: {'PASS' if result.passed else 'FAIL'}")
    print(f"Stop reason: {result.stop_reason}")
    print(f"Actions: {result.actions:,}")
    print(f"Final milestone: {result.final_milestone}")
    print(f"Matched teacher prefix: {result.matched_teacher_prefix:,}")
    print(f"Exact teacher route: {result.exact_teacher_actions}")
    print(f"Private evidence: {result.output_directory.resolve()}")
    return 0 if result.passed else 1


def run_apprentice_stage0_qualify(args: argparse.Namespace) -> int:
    receipt = qualify_stage0_composite(
        args.data_qualification,
        args.training,
        args.evaluation,
        args.output,
    )
    print("Visual Apprentice Stage 0: PASS")
    print("Data gate: PASS")
    print("Offline/reload gate: PASS")
    print("Clean-power-on gate: PASS")
    print(f"Composite SHA-256: {receipt['bundle_sha256']}")
    print(f"Qualification bundle: {args.output.expanduser().resolve()}")
    return 0


def run_apprentice_curriculum(args: argparse.Namespace) -> int:
    rom_path = resolve_rom_path(args.rom)
    port = None if args.port == 0 else args.port
    if args.canary:
        config = OvernightApprenticeConfig.canary(dashboard_port=port)
        print("Mode: three-minute development canary; relaxed promotion is not evidence.")
    else:
        config = OvernightApprenticeConfig(
            seed=args.seed,
            max_seconds=args.hours * 60 * 60,
            max_emulator_actions=args.max_actions,
            max_actions_without_promotion=args.stagnation_actions,
            max_rss_mib=args.max_rss_mib,
            minimum_free_gib=args.min_free_gib,
            torch_threads=args.torch_threads,
            dashboard_port=port,
        )
    if port is not None:
        print(f"Live curriculum dashboard: http://127.0.0.1:{port}/index.html", flush=True)
    result = run_overnight_apprentice(
        rom_path,
        args.dataset,
        args.model,
        args.output,
        config=config,
        resume=args.resume,
    )
    print(f"Curriculum state: {result.state}")
    print(f"Stop reason: {result.stop_reason}")
    print(f"Elapsed hours: {result.elapsed_seconds / 3600:.3f}")
    print(f"Episodes: {result.episodes:,}")
    print(f"Successes: {result.successes:,}")
    print(f"Gradient updates: {result.updates:,}")
    print(f"Emulator actions: {result.emulator_actions:,}")
    print(f"Highest completed horizon: {result.highest_completed_horizon:,}")
    print(f"Private evidence: {result.output_directory}")
    return 0 if result.state != "failed" else 1


def show_apprentice_curriculum_status(run_directory: Path) -> int:
    status_path = run_directory.expanduser().resolve() / "status.json"
    if not status_path.is_file():
        raise ValueError("Curriculum status.json does not exist")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    updated = datetime.fromisoformat(status["updated_at"])
    age = max(0.0, (datetime.now(UTC) - updated).total_seconds())
    print(f"State: {status['state']}")
    print(f"Heartbeat age: {age:.1f} seconds")
    print(f"Elapsed hours: {status['elapsed_seconds'] / 3600:.3f}")
    print(f"Current rung: {status.get('current_horizon') or 'complete'} actions remaining")
    print(f"Episodes: {status['episodes']:,}")
    print(f"Successes: {status['successes']:,}")
    print(f"Learner updates: {status.get('self_imitation_updates', 0):,}")
    print(f"Demo priming updates: {status.get('demo_updates', 0):,}")
    print(f"Emulator actions: {status['emulator_actions']:,}")
    print(f"Actions/second: {status.get('actions_per_second', 0):,.2f}")
    print(f"Stop reason: {status.get('stop_reason') or 'still running'}")
    return 0 if status["state"] != "failed" else 1


def request_apprentice_curriculum_stop(run_directory: Path) -> int:
    directory = run_directory.expanduser().resolve()
    if not (directory / "manifest.json").is_file():
        raise ValueError("Curriculum run manifest does not exist")
    (directory / "STOP").touch(exist_ok=True)
    print("Graceful stop requested; the learner will checkpoint before exiting.")
    return 0


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
        if args.command == "evolution-run":
            return run_evolution(args)
        if args.command == "evolution-lab-run":
            return run_evolution_lab_command(args)
        if args.command == "evolution-lab-status":
            return show_evolution_lab_status(args.lab_directory.expanduser().resolve())
        if args.command == "evolution-lab-stop":
            return request_evolution_lab_stop(args.lab_directory.expanduser().resolve())
        if args.command == "expedition-run":
            return run_expedition_command(args)
        if args.command == "expedition-status":
            return show_expedition_status(args.run_directory)
        if args.command == "expedition-stop":
            return request_expedition_stop(args.run_directory)
        if args.command == "ppo-run":
            return run_parallel_ppo_command(args)
        if args.command == "ppo-status":
            return show_parallel_ppo_command(args.run_directory)
        if args.command == "ppo-stop":
            return request_parallel_ppo_stop_command(args.run_directory)
        if args.command == "arena-run":
            return run_agent_arena(args)
        if args.command == "arena-status":
            return show_arena_status(args.arena_directory.expanduser().resolve())
        if args.command == "arena-stop":
            return request_arena_stop(args.arena_directory.expanduser().resolve())
        if args.command == "apprentice-extract":
            return run_apprentice_extract(args)
        if args.command == "apprentice-dataset-verify":
            return run_apprentice_verify(args)
        if args.command == "apprentice-data-qualify":
            return run_apprentice_data_qualify(args)
        if args.command == "apprentice-overfit":
            return run_apprentice_overfit(args)
        if args.command == "apprentice-evaluate":
            return run_apprentice_evaluate(args)
        if args.command == "apprentice-stage0-qualify":
            return run_apprentice_stage0_qualify(args)
        if args.command == "apprentice-curriculum-run":
            return run_apprentice_curriculum(args)
        if args.command == "apprentice-curriculum-status":
            return show_apprentice_curriculum_status(args.run_directory)
        if args.command == "apprentice-curriculum-stop":
            return request_apprentice_curriculum_stop(args.run_directory)
    except (OSError, RomValidationError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2
