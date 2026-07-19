from __future__ import annotations

import os
from pathlib import Path

import pytest

from pokemon_red_ai.bootstrap import NewGameTiming, is_clean_bedroom_start, play_new_game_intro
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.rom import ROM_ENVIRONMENT_VARIABLE, verify_rom
from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader


class RecordingController:
    def __init__(self) -> None:
        self.frame_count = 0
        self.events: list[tuple[str, object]] = []

    def tick(self, frames: int, *, render_last: bool = True) -> bool:
        self.frame_count += frames
        self.events.append(("tick", (frames, render_last)))
        return True

    def press(self, button: str, *, hold_frames: int = 8, release_frames: int = 16) -> bool:
        self.frame_count += hold_frames + release_frames
        self.events.append(("press", button))
        return True


def test_new_game_sequence_has_frozen_inputs_and_timing() -> None:
    controller = RecordingController()

    play_new_game_intro(controller)

    buttons = [value for kind, value in controller.events if kind == "press"]
    assert buttons == [
        "start",
        *(["a"] * 14),
        "down",
        "a",
        *(["a"] * 5),
        "down",
        "a",
        *(["a"] * 7),
    ]
    assert controller.frame_count == 9_804


def test_clean_bedroom_start_requires_started_game() -> None:
    expected = PokemonRedState(True, 0x26, 6, 3, 0, 0)
    preloaded_intro = PokemonRedState(False, None, None, None, None, None)

    assert is_clean_bedroom_start(expected)
    assert not is_clean_bedroom_start(preloaded_intro)


@pytest.mark.integration
def test_supported_rom_reaches_clean_bedroom() -> None:
    raw_path = os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        pytest.skip(f"Set {ROM_ENVIRONMENT_VARIABLE} to run ROM integration tests")

    rom_path = Path(raw_path).expanduser().resolve()
    verify_rom(rom_path)
    with PokemonRedEmulator(rom_path) as emulator:
        play_new_game_intro(emulator, timing=NewGameTiming())
        state = PokemonRedStateReader(emulator).read()
        emulator.press("down")
        moved_state = PokemonRedStateReader(emulator).read()

    assert is_clean_bedroom_start(state)
    assert moved_state.map_id == state.map_id
    assert moved_state.player_y == 7
    assert moved_state.player_x == 3
