from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

import numpy as np
from pyboy import PyBoy

from pokemon_red_ai.constants import SUPPORTED_BUTTONS
from pokemon_red_ai.rom import RomFingerprint, verify_rom


class EmulatorError(RuntimeError):
    """Raised when the emulator cannot perform a requested operation safely."""


@dataclass(frozen=True, slots=True)
class EmulatorSnapshot:
    logical_frame: int
    sha256: str
    rom_sha256: str
    pyboy_version: str
    payload: bytes = field(repr=False)


class PokemonRedEmulator:
    """A small, deterministic, no-save wrapper around PyBoy.

    The ROM is passed as an open binary stream so PyBoy cannot create sibling save files. The
    wrapper intentionally exposes read-only memory helpers but no memory-writing API.
    """

    def __init__(self, rom_path: Path, *, window: str = "null", speed: int = 0) -> None:
        self.rom_path = rom_path
        self.window = window
        self.speed = speed
        self.frame_count = 0
        self._pyboy: PyBoy | None = None
        self._rom_file: BinaryIO | None = None
        self._rom_fingerprint: RomFingerprint | None = None

    @property
    def pyboy(self) -> PyBoy:
        if self._pyboy is None:
            raise EmulatorError("Emulator has not been started.")
        return self._pyboy

    def start(self) -> PokemonRedEmulator:
        if self._pyboy is not None:
            raise EmulatorError("Emulator is already running.")

        self._rom_fingerprint = verify_rom(self.rom_path)
        self._rom_file = self.rom_path.open("rb")
        try:
            self._pyboy = PyBoy(
                self._rom_file,
                window=self.window,
                no_input=True,
                sound_volume=0,
                log_level="ERROR",
            )
        except Exception:
            self._rom_file.close()
            self._rom_file = None
            self._rom_fingerprint = None
            raise
        self._pyboy.set_emulation_speed(self.speed)
        return self

    def close(self) -> None:
        if self._pyboy is not None:
            self._pyboy.stop(False)
        self._pyboy = None
        if self._rom_file is not None:
            self._rom_file.close()
        self._rom_file = None
        self._rom_fingerprint = None

    def __enter__(self) -> PokemonRedEmulator:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def tick(self, frames: int, *, render_last: bool = True) -> bool:
        if frames < 1:
            raise ValueError("frames must be at least 1")
        alive = bool(self.pyboy.tick(frames, render=render_last, sound=False))
        self.frame_count += frames
        return alive

    def press(self, button: str, *, hold_frames: int = 8, release_frames: int = 16) -> bool:
        normalized = button.lower()
        if normalized not in SUPPORTED_BUTTONS:
            raise ValueError(f"Unsupported button: {button}")
        if hold_frames < 1 or release_frames < 1:
            raise ValueError("hold_frames and release_frames must be at least 1")

        self.pyboy.button_press(normalized)
        alive = self.tick(hold_frames, render_last=False)
        self.pyboy.button_release(normalized)
        return self.tick(release_frames, render_last=True) and alive

    def screen_rgb(self) -> np.ndarray:
        return self.pyboy.screen.ndarray[:, :, :3].copy()

    def screen_sha256(self) -> str:
        return hashlib.sha256(self.screen_rgb().tobytes()).hexdigest()

    def game_area_sha256(self) -> str:
        return hashlib.sha256(self.pyboy.game_area().tobytes()).hexdigest()

    def save_state(self) -> EmulatorSnapshot:
        if self._rom_fingerprint is None:
            raise EmulatorError("Emulator ROM metadata is unavailable.")
        state = io.BytesIO()
        self.pyboy.save_state(state)
        payload = state.getvalue()
        return EmulatorSnapshot(
            logical_frame=self.frame_count,
            sha256=hashlib.sha256(payload).hexdigest(),
            rom_sha256=self._rom_fingerprint.sha256,
            pyboy_version=version("pyboy"),
            payload=payload,
        )

    def load_state(self, snapshot: EmulatorSnapshot) -> None:
        actual_hash = hashlib.sha256(snapshot.payload).hexdigest()
        if actual_hash != snapshot.sha256:
            raise EmulatorError("Snapshot payload hash does not match its metadata.")
        if self._rom_fingerprint is None:
            raise EmulatorError("Emulator ROM metadata is unavailable.")
        if snapshot.rom_sha256 != self._rom_fingerprint.sha256:
            raise EmulatorError("Snapshot was created from a different ROM revision.")
        if snapshot.pyboy_version != version("pyboy"):
            raise EmulatorError("Snapshot was created by a different PyBoy version.")
        self.pyboy.load_state(io.BytesIO(snapshot.payload))
        self.frame_count = snapshot.logical_frame

    def read_u8(self, address: int) -> int:
        """Read one byte without exposing a corresponding write operation."""
        if not 0 <= address <= 0xFFFF:
            raise ValueError("Game Boy address must be between 0x0000 and 0xFFFF")
        return int(self.pyboy.memory[address])
