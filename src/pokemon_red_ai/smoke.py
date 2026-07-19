from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from PIL import Image

from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import RomFingerprint
from pokemon_red_ai.trace import JsonlTrace


@dataclass(frozen=True, slots=True)
class SmokeTestResult:
    run_directory: Path
    input_changed_screen: bool
    save_state_is_deterministic: bool
    cartridge_title: str
    frames_executed: int

    @property
    def passed(self) -> bool:
        return self.input_changed_screen and self.save_state_is_deterministic


def default_run_directory(base: Path = Path("runs")) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = base / f"smoke-{timestamp}"
    counter = 1
    while candidate.exists():
        candidate = base / f"smoke-{timestamp}-{counter}"
        counter += 1
    return candidate


def save_screen(emulator: PokemonRedEmulator, path: Path) -> None:
    Image.fromarray(emulator.screen_rgb()).save(path)


def run_smoke_test(
    rom_path: Path,
    rom: RomFingerprint,
    *,
    run_directory: Path | None = None,
    boot_frames: int = 1_800,
) -> SmokeTestResult:
    output = run_directory or default_run_directory()
    output.mkdir(parents=True, exist_ok=False)
    provenance = detect_source_provenance()

    with JsonlTrace(output / "trace.jsonl") as trace:
        trace.write(
            "manifest",
            created_at=datetime.now(UTC).isoformat(),
            run_type="calibration",
            run_name="Emulator smoke calibration",
            actor="scripted_harness",
            start_condition="emulator_power_on",
            instrumentation_schema="none",
            action_schema="controller-v1",
            intervention_count=0,
            rom=rom.public_dict(),
            source=provenance.public_dict(),
            software={
                "python": platform.python_version(),
                "pyboy": version("pyboy"),
                "project": version("pokemon-red-ai"),
            },
            config={"boot_frames": boot_frames, "hold_frames": 8, "release_frames": 16},
        )

        with PokemonRedEmulator(rom_path) as emulator:
            emulator.tick(boot_frames, render_last=True)
            title_hash = emulator.screen_sha256()
            save_screen(emulator, output / "01-title.png")
            trace.write(
                "observation",
                label="title",
                frame=emulator.frame_count,
                screen_sha256=title_hash,
                game_area_sha256=emulator.game_area_sha256(),
            )

            saved_state = emulator.save_state()
            emulator.press("start")
            emulator.tick(120, render_last=True)
            after_input_hash = emulator.screen_sha256()
            save_screen(emulator, output / "02-after-start.png")
            trace.write(
                "action_result",
                action="start",
                frame=emulator.frame_count,
                hold_frames=8,
                release_frames=16,
                screen_sha256=after_input_hash,
                changed_screen=after_input_hash != title_hash,
            )

            emulator.load_state(saved_state)
            emulator.tick(1, render_last=True)
            restored_once = emulator.screen_sha256()
            emulator.load_state(saved_state)
            emulator.tick(1, render_last=True)
            restored_twice = emulator.screen_sha256()
            save_screen(emulator, output / "03-restored.png")
            trace.write(
                "save_state_check",
                frame=emulator.frame_count,
                state_bytes=len(saved_state.payload),
                state_sha256=saved_state.sha256,
                logical_frame=saved_state.logical_frame,
                restored_screen_sha256=restored_once,
                deterministic=restored_once == restored_twice,
            )

            result = SmokeTestResult(
                run_directory=output,
                input_changed_screen=after_input_hash != title_hash,
                save_state_is_deterministic=restored_once == restored_twice,
                cartridge_title=emulator.pyboy.cartridge_title,
                frames_executed=emulator.frame_count,
            )
            trace.write(
                "result",
                passed=result.passed,
                input_changed_screen=result.input_changed_screen,
                save_state_is_deterministic=result.save_state_is_deterministic,
                cartridge_title=result.cartridge_title,
                frames_executed=result.frames_executed,
            )
            return result
