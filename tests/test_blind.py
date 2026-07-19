from __future__ import annotations

import json
import os
import random
from pathlib import Path

import numpy as np
import pytest

import pokemon_red_ai.blind as blind_module
from pokemon_red_ai.blind import (
    ArchiveCell,
    BlindAction,
    BlindRunConfig,
    DiscoveryArchive,
    FrozenSnapshot,
    PixelsOnlyActor,
    SeenVisualFilter,
    _read_checkpoint,
    run_blind_experiment,
    visual_key,
    visual_signature,
)
from pokemon_red_ai.blind_report import render_blind_dashboard
from pokemon_red_ai.emulator import EmulatorSnapshot, PokemonRedEmulator
from pokemon_red_ai.rom import ROM_ENVIRONMENT_VARIABLE, verify_rom


class RecordingPixelController:
    def __init__(self, pixels: np.ndarray) -> None:
        self.pixels = pixels
        self.events: list[tuple[str, object]] = []

    def screen_rgb(self) -> np.ndarray:
        self.events.append(("screen", None))
        return self.pixels

    def tick(self, frames: int, *, render_last: bool = True) -> bool:
        self.events.append(("tick", (frames, render_last)))
        return True

    def press(self, button: str, *, hold_frames: int = 8, release_frames: int = 16) -> bool:
        self.events.append(("press", (button, hold_frames, release_frames)))
        return True

    def read_u8(self, _address: int) -> int:
        raise AssertionError("The pixels-only actor touched RAM")


def test_pixels_only_actor_exposes_pixels_and_buttons_but_no_privileged_capabilities() -> None:
    source = np.zeros((144, 160, 3), dtype=np.uint8)
    controller = RecordingPixelController(source)
    actor = PixelsOnlyActor(controller)

    observed = actor.observe()
    observed[0, 0] = 255
    actor.act(BlindAction("a", 4, 8))
    actor.act(BlindAction("noop", 4, 8))

    assert np.all(source == 0)
    assert controller.events == [
        ("screen", None),
        ("press", ("a", 4, 8)),
        ("tick", (12, True)),
    ]
    for forbidden in ("read_u8", "game_area", "save_state", "load_state", "pyboy"):
        assert not hasattr(actor, forbidden)


def test_visual_signature_is_deterministic_and_uses_only_pixels() -> None:
    black = np.zeros((144, 160, 3), dtype=np.uint8)
    split = black.copy()
    split[:, 80:] = 255

    assert len(visual_signature(black)) == 18 * 20
    assert visual_key(black) == visual_key(black.copy())
    assert visual_key(black) != visual_key(split)


def test_seen_visual_filter_has_bounded_round_trip_state() -> None:
    first = bytes.fromhex("00" * 16)
    second = bytes.fromhex("11" * 16)
    seen = SeenVisualFilter(1_024)

    assert seen.check_and_add(first)
    assert not seen.check_and_add(first)
    assert seen.check_and_add(second)

    restored = SeenVisualFilter(1_024, payload=seen.payload())
    assert not restored.check_and_add(first)
    assert not restored.check_and_add(second)


def test_frozen_snapshot_and_archive_checkpoint_round_trip() -> None:
    raw = EmulatorSnapshot(12, "a" * 64, "b" * 64, "2.7.0", b"state" * 10_000)
    frozen = FrozenSnapshot.freeze(raw)
    archive = DiscoveryArchive()
    root = archive.add(
        key=bytes.fromhex("01" * 16),
        snapshot=frozen,
        parent_id=None,
        actions_from_parent=(),
        discovered_action=0,
    )
    child = archive.add(
        key=bytes.fromhex("02" * 16),
        snapshot=frozen,
        parent_id=root.cell_id,
        actions_from_parent=(BlindAction("up", 4, 8),),
        discovered_action=1,
    )

    restored = DiscoveryArchive(
        [ArchiveCell.from_checkpoint_dict(value) for value in archive.checkpoint_list()]
    )

    assert frozen.thaw() == raw
    assert child.depth == 1
    assert len(restored) == 2
    assert restored.find(bytes.fromhex("02" * 16)).depth == 1  # type: ignore[union-attr]
    assert restored.select(random.Random(7)).cell_id in {0, 1}


def test_dashboard_marks_the_information_boundary_and_escapes_labels() -> None:
    status = {
        "run_name": "Pixels-only <test>",
        "run_class": "development",
        "mode": "archivist",
        "state": "running",
        "stop_reason": None,
        "elapsed_seconds": 10,
        "total_actions": 20,
        "unique_visual_cells": 5,
        "archive_cells": 5,
        "archive_restores": 3,
        "snapshot_assisted": True,
        "continuous_playthrough": False,
        "actions_per_second": 2,
        "novelty_rate": 0.25,
        "action_counts": {"a": 10, "noop": 10},
    }
    rendered = render_blind_dashboard(
        status,
        [
            {"elapsed_seconds": 1, "total_actions": 1, "unique_visual_cells": 1},
            {"elapsed_seconds": 10, "total_actions": 20, "unique_visual_cells": 5},
        ],
        [{"file": "safe.png", "label": "<unsafe>", "action": 1}],
    )

    assert "Seeded uniform random" in rendered
    assert "DEVELOPMENT" in rendered
    assert "Semantic RAM used" in rendered
    assert "Continuous playthrough: <strong>no</strong>" in rendered
    assert "&lt;test&gt;" in rendered
    assert "&lt;unsafe&gt;" in rendered
    assert "<script" not in rendered.lower()
    assert "http://" not in rendered and "https://" not in rendered


def test_blind_config_rejects_unbounded_or_invalid_values() -> None:
    with pytest.raises(ValueError, match="duration_seconds"):
        BlindRunConfig(duration_seconds=0)
    with pytest.raises(ValueError, match="max_actions"):
        BlindRunConfig(max_actions=0)
    with pytest.raises(ValueError, match="mode"):
        BlindRunConfig(mode="guided")


@pytest.mark.integration
def test_pixels_only_archivist_completes_a_bounded_private_rom_run(tmp_path: Path) -> None:
    raw_path = os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        pytest.skip(f"Set {ROM_ENVIRONMENT_VARIABLE} to run ROM integration tests")
    rom_path = Path(raw_path).expanduser().resolve()
    fingerprint = verify_rom(rom_path)
    output = tmp_path / "blind"
    config = BlindRunConfig(
        duration_seconds=60,
        max_actions=50,
        max_archive_cells=100,
        seen_filter_bytes=1_024,
        screenshot_limit=8,
        status_interval_seconds=0.01,
        checkpoint_interval_seconds=0.01,
        max_output_bytes=32 * 1024 * 1024,
        min_free_bytes=0,
    )

    result = run_blind_experiment(
        rom_path,
        fingerprint,
        config=config,
        run_directory=output,
    )

    assert result.stop_reason == "action_limit"
    assert result.counters.total_actions == 50
    assert result.counters.unique_visual_cells >= 1
    assert (output / "checkpoint.json.gz").is_file()
    assert (output / "status.json").is_file()
    assert (output / "index.html").is_file()
    trace = (output / "trace.jsonl").read_text(encoding="utf-8")
    assert str(rom_path) not in trace
    assert '"ram_used_by_actor_or_reward":false' in trace
    milestones = [
        json.loads(line)
        for line in trace.splitlines()
        if json.loads(line)["kind"] == "visual_milestone"
    ]
    assert len({record["file"] for record in milestones}) == len(milestones)

    checkpoint = _read_checkpoint(output / "checkpoint.json.gz")
    archive = DiscoveryArchive(
        [ArchiveCell.from_checkpoint_dict(value) for value in checkpoint["archive"]]
    )
    with PokemonRedEmulator(rom_path) as emulator:
        actor = PixelsOnlyActor(emulator)
        for cell in archive.cells[1:]:
            assert cell.parent_id is not None
            parent = archive.cells[cell.parent_id]
            emulator.load_state(parent.snapshot.thaw())
            for action in cell.actions_from_parent:
                actor.act(action)
            assert visual_key(actor.observe()) == cell.pixel_key


@pytest.mark.integration
def test_unexpected_runner_error_marks_status_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        pytest.skip(f"Set {ROM_ENVIRONMENT_VARIABLE} to run ROM integration tests")
    rom_path = Path(raw_path).expanduser().resolve()
    fingerprint = verify_rom(rom_path)

    def fail_dashboard(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected dashboard failure")

    monkeypatch.setattr(blind_module, "_write_dashboard", fail_dashboard)
    output = tmp_path / "failed-blind-run"
    config = BlindRunConfig(
        duration_seconds=60,
        max_actions=10,
        seen_filter_bytes=1_024,
        status_interval_seconds=0.01,
        checkpoint_interval_seconds=30,
        min_free_bytes=0,
    )

    with pytest.raises(RuntimeError, match="injected dashboard failure"):
        run_blind_experiment(
            rom_path,
            fingerprint,
            config=config,
            run_directory=output,
        )

    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed"
    assert status["stop_reason"] == "error:RuntimeError"
    assert '"kind":"failure"' in (output / "trace.jsonl").read_text(encoding="utf-8")
