from __future__ import annotations

import argparse
import platform
import sys
from importlib.metadata import version
from pathlib import Path

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
    except (OSError, RomValidationError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2
