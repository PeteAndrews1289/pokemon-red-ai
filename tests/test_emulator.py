from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_ai.emulator import EmulatorError, PokemonRedEmulator
from pokemon_red_ai.rom import ROM_ENVIRONMENT_VARIABLE, verify_rom


def test_emulator_rejects_invalid_button() -> None:
    emulator = PokemonRedEmulator(Path("unused.gb"))
    with pytest.raises(ValueError, match="Unsupported button"):
        emulator.press("turbo")


@pytest.mark.integration
def test_supported_rom_boots_and_restores_state() -> None:
    raw_path = os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        pytest.skip(f"Set {ROM_ENVIRONMENT_VARIABLE} to run ROM integration tests")

    rom_path = Path(raw_path).expanduser().resolve()
    verify_rom(rom_path)
    with PokemonRedEmulator(rom_path) as emulator:
        assert emulator.tick(120)
        saved_state = emulator.save_state()
        with pytest.raises(EmulatorError, match="different ROM revision"):
            emulator.load_state(replace(saved_state, rom_sha256="0" * 64))
        with pytest.raises(EmulatorError, match="different PyBoy version"):
            emulator.load_state(replace(saved_state, pyboy_version="different"))
        emulator.tick(30)
        emulator.load_state(saved_state)
        emulator.tick(1)
        first = emulator.screen_sha256()
        emulator.load_state(saved_state)
        emulator.tick(1)
        second = emulator.screen_sha256()

    assert first == second
