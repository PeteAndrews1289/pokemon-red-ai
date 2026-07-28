from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import RomFingerprint
from pokemon_red_ai.smoke import save_screen
from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader, ReadOnlyMemory
from pokemon_red_ai.trace import JsonlTrace

BEDROOM_MAP_ID = 0x26
BEDROOM_START_Y = 6
BEDROOM_START_X = 3
JOY_IGNORE_ADDRESS = 0xCD6B
REDS_HOUSE_2F_SCRIPT_ADDRESS = 0xD60C
BEDROOM_NOOP_SCRIPT = 1


class Controller(Protocol):
    frame_count: int

    def tick(self, frames: int, *, render_last: bool = True) -> bool: ...

    def press(self, button: str, *, hold_frames: int = 8, release_frames: int = 16) -> bool: ...


@dataclass(frozen=True, slots=True)
class NewGameTiming:
    boot_frames: int = 1_800
    normal_wait_frames: int = 240
    menu_move_wait_frames: int = 120
    final_wait_frames: int = 300


DEFAULT_NEW_GAME_TIMING = NewGameTiming()


@dataclass(frozen=True, slots=True)
class BootstrapAttempt:
    label: str
    state: PokemonRedState
    screen_sha256: str
    game_area_sha256: str
    snapshot_sha256: str
    final_frame: int
    input_ready: bool
    one_tile_down_verified: bool

    @property
    def reached_bedroom(self) -> bool:
        return is_clean_bedroom_start(self.state) and self.input_ready


@dataclass(frozen=True, slots=True)
class BootstrapTestResult:
    run_directory: Path
    first: BootstrapAttempt
    second: BootstrapAttempt

    @property
    def deterministic(self) -> bool:
        return (
            self.first.state == self.second.state
            and self.first.screen_sha256 == self.second.screen_sha256
            and self.first.game_area_sha256 == self.second.game_area_sha256
            and self.first.snapshot_sha256 == self.second.snapshot_sha256
            and self.first.final_frame == self.second.final_frame
        )

    @property
    def passed(self) -> bool:
        return (
            self.first.reached_bedroom
            and self.second.reached_bedroom
            and self.first.one_tile_down_verified
            and self.second.one_tile_down_verified
            and self.deterministic
        )


def is_clean_bedroom_start(state: PokemonRedState) -> bool:
    """Identify the expected clean bedroom tuple without using a screen hash."""
    return (
        state.game_started
        and state.map_id == BEDROOM_MAP_ID
        and state.player_y == BEDROOM_START_Y
        and state.player_x == BEDROOM_START_X
        and state.party_count == 0
        and state.battle_state == 0
    )


def is_bedroom_input_ready(state: PokemonRedState, memory: ReadOnlyMemory) -> bool:
    """Verify that the bedroom map script reached its input-ready no-op state.

    These two extra reads are bootstrap assertions, not part of the policy observation schema.
    """
    return (
        is_clean_bedroom_start(state)
        and memory.read_u8(REDS_HOUSE_2F_SCRIPT_ADDRESS) == BEDROOM_NOOP_SCRIPT
        and memory.read_u8(JOY_IGNORE_ADDRESS) == 0
    )


def _press_and_wait(controller: Controller, button: str, wait_frames: int) -> None:
    controller.press(button)
    controller.tick(wait_frames, render_last=True)


def play_new_game_intro(
    controller: Controller,
    *,
    timing: NewGameTiming = DEFAULT_NEW_GAME_TIMING,
) -> None:
    """Reach the bedroom from a clean boot using the built-in RED and BLUE names."""
    controller.tick(timing.boot_frames, render_last=True)
    _press_and_wait(controller, "start", timing.normal_wait_frames)

    for _ in range(14):
        _press_and_wait(controller, "a", timing.normal_wait_frames)

    _press_and_wait(controller, "down", timing.menu_move_wait_frames)
    _press_and_wait(controller, "a", timing.normal_wait_frames)

    for _ in range(5):
        _press_and_wait(controller, "a", timing.normal_wait_frames)

    _press_and_wait(controller, "down", timing.menu_move_wait_frames)
    _press_and_wait(controller, "a", timing.normal_wait_frames)

    for _ in range(6):
        _press_and_wait(controller, "a", timing.normal_wait_frames)
    _press_and_wait(controller, "a", timing.final_wait_frames)


def default_bootstrap_run_directory(base: Path = Path("runs")) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = base / f"bootstrap-{timestamp}"
    counter = 1
    while candidate.exists():
        candidate = base / f"bootstrap-{timestamp}-{counter}"
        counter += 1
    return candidate


def _run_attempt(
    rom_path: Path,
    *,
    label: str,
    screenshot_path: Path,
    timing: NewGameTiming,
    trace: JsonlTrace,
) -> BootstrapAttempt:
    with PokemonRedEmulator(rom_path) as emulator:
        trace.write("bootstrap_attempt_started", label=label)
        play_new_game_intro(emulator, timing=timing)
        state = PokemonRedStateReader(emulator).read()
        input_ready = is_bedroom_input_ready(state, emulator)
        snapshot = emulator.save_state()
        save_screen(emulator, screenshot_path)
        screen_sha256 = emulator.screen_sha256()
        game_area_sha256 = emulator.game_area_sha256()

        emulator.press("down")
        moved_state = PokemonRedStateReader(emulator).read()
        one_tile_down_verified = (
            state.player_y is not None
            and moved_state.map_id == state.map_id
            and moved_state.player_y == state.player_y + 1
            and moved_state.player_x == state.player_x
        )
        emulator.load_state(snapshot)
        one_tile_down_verified = (
            one_tile_down_verified and PokemonRedStateReader(emulator).read() == state
        )

        attempt = BootstrapAttempt(
            label=label,
            state=state,
            screen_sha256=screen_sha256,
            game_area_sha256=game_area_sha256,
            snapshot_sha256=snapshot.sha256,
            final_frame=emulator.frame_count,
            input_ready=input_ready,
            one_tile_down_verified=one_tile_down_verified,
        )
        trace.write(
            "bootstrap_attempt_finished",
            label=label,
            frame=attempt.final_frame,
            reached_bedroom=attempt.reached_bedroom,
            input_ready=attempt.input_ready,
            one_tile_down_verified=attempt.one_tile_down_verified,
            state=state.public_dict(),
            screen_sha256=attempt.screen_sha256,
            game_area_sha256=attempt.game_area_sha256,
            snapshot_sha256=attempt.snapshot_sha256,
            screenshot=screenshot_path.name,
        )
        return attempt


def run_bootstrap_test(
    rom_path: Path,
    rom: RomFingerprint,
    *,
    run_directory: Path | None = None,
    timing: NewGameTiming = DEFAULT_NEW_GAME_TIMING,
) -> BootstrapTestResult:
    output = run_directory or default_bootstrap_run_directory()
    output.mkdir(parents=True, exist_ok=False)
    provenance = detect_source_provenance()

    with JsonlTrace(output / "trace.jsonl") as trace:
        trace.write(
            "manifest",
            created_at=datetime.now(UTC).isoformat(),
            run_type="calibration",
            run_name="Clean-game bootstrap calibration",
            actor="scripted_harness",
            start_condition="clean_boot",
            instrumentation_schema="state-instrumentation-v1",
            action_schema="controller-v1",
            intervention_count=0,
            rom=rom.public_dict(),
            source=provenance.public_dict(),
            software={
                "python": platform.python_version(),
                "pyboy": version("pyboy"),
                "project": version("pokemon-red-ai"),
            },
            config={
                "sequence": "clean_boot_to_bedroom_red_blue",
                "boot_frames": timing.boot_frames,
                "normal_wait_frames": timing.normal_wait_frames,
                "menu_move_wait_frames": timing.menu_move_wait_frames,
                "final_wait_frames": timing.final_wait_frames,
                "hold_frames": 8,
                "release_frames": 16,
            },
        )
        first = _run_attempt(
            rom_path,
            label="a",
            screenshot_path=output / "01-bedroom-a.png",
            timing=timing,
            trace=trace,
        )
        second = _run_attempt(
            rom_path,
            label="b",
            screenshot_path=output / "02-bedroom-b.png",
            timing=timing,
            trace=trace,
        )
        result = BootstrapTestResult(output, first, second)
        trace.write(
            "result",
            passed=result.passed,
            deterministic=result.deterministic,
            both_reached_bedroom=first.reached_bedroom and second.reached_bedroom,
            one_tile_down_verified=(
                first.one_tile_down_verified and second.one_tile_down_verified
            ),
        )
        return result
