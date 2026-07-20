from __future__ import annotations

import gzip
import hashlib
import json
import random
import urllib.error
import urllib.request
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pytest

import pokemon_red_ai.expedition as expedition_module
import pokemon_red_ai.expedition_runner as runner_module
from pokemon_red_ai.blind import BLIND_ACTIONS
from pokemon_red_ai.emulator import EmulatorSnapshot
from pokemon_red_ai.expedition import ExpeditionStore, FrontierArchive
from pokemon_red_ai.expedition_runner import (
    ExpeditionRunConfig,
    SeededRandomSequenceEmitter,
    VisualLoopDetector,
    _acquire_single_writer,
    _json_tuple,
    _release_single_writer,
    _start_dashboard_server,
    _stop_dashboard_server,
    adaptive_suffix_budget,
    run_expedition,
)
from pokemon_red_ai.milestones import PokemonRedMap
from pokemon_red_ai.rom import RomFingerprint
from pokemon_red_ai.state import PokemonRedState


def test_bounded_config_adaptive_horizon_and_loop_detector() -> None:
    assert [
        adaptive_suffix_budget(
            count,
            minimum=16,
            maximum=128,
            attempts_per_expansion=2,
        )
        for count in (1, 2, 3, 4, 5, 20)
    ] == [16, 16, 32, 32, 64, 128]

    detector = VisualLoopDetector(window=4, repeat_limit=3)
    first = b"a" * 16
    second = b"b" * 16
    assert detector.observe(first) is False
    assert detector.observe(second) is False
    assert detector.observe(first) is False
    assert detector.observe(first) is True

    with pytest.raises(ValueError, match="at least three"):
        ExpeditionRunConfig(promotion_replay_passes=2)
    with pytest.raises(ValueError, match="capture interval"):
        ExpeditionRunConfig(frontier_capture_interval_actions=0)


def test_seeded_random_emitter_is_reproducible_and_has_no_state_input() -> None:
    first = SeededRandomSequenceEmitter(random.Random(91))
    second = SeededRandomSequenceEmitter(random.Random(91))

    first_actions = [first.emit() for _ in range(32)]
    second_actions = [second.emit() for _ in range(32)]

    assert first_actions == second_actions
    assert {action.button for action in first_actions}.issubset(BLIND_ACTIONS)
    assert all(action.total_frames == 20 for action in first_actions)


def test_single_writer_lock_rejects_a_live_second_coordinator(tmp_path: Path) -> None:
    lock = _acquire_single_writer(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="live coordinator"):
            _acquire_single_writer(tmp_path)
    finally:
        _release_single_writer(lock)
    assert not lock.exists()


def test_loopback_dashboard_serves_only_sanitized_artifacts(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("expedition", encoding="utf-8")
    (tmp_path / "latest.png").write_bytes(b"png")
    (tmp_path / "status.json").write_text("{}", encoding="utf-8")
    (tmp_path / "frontier").mkdir()
    (tmp_path / "frontier" / "manifest.json").write_text("private", encoding="utf-8")

    server, thread = _start_dashboard_server(tmp_path, 0)
    port = int(server.server_address[1])
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html") as response:
            assert response.read() == b"expedition"
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/frontier/manifest.json")
        assert denied.value.code == 404
    finally:
        _stop_dashboard_server(server, thread)

    assert not thread.is_alive()


class _FakeEmulator:
    rom_sha256 = "a" * 64
    stop_path: Path | None = None
    stop_after_step: int | None = None

    def __init__(self, _rom_path: Path, **_kwargs: object) -> None:
        self.frame_count = 0
        self.step = 0

    def __enter__(self) -> _FakeEmulator:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def _advance(self, frames: int) -> bool:
        self.frame_count += frames
        self.step += 1
        if (
            type(self).stop_path is not None
            and type(self).stop_after_step is not None
            and self.step >= type(self).stop_after_step
        ):
            type(self).stop_path.touch()
            type(self).stop_after_step = None
        return True

    def tick(self, frames: int, *, render_last: bool = True) -> bool:
        del render_last
        return self._advance(frames)

    def press(self, _button: str, *, hold_frames: int, release_frames: int) -> bool:
        return self._advance(hold_frames + release_frames)

    def screen_rgb(self) -> np.ndarray:
        return np.full((144, 160, 3), self.step % 256, dtype=np.uint8)

    def save_state(self) -> EmulatorSnapshot:
        payload = f"{self.frame_count}:{self.step}".encode("ascii")
        return EmulatorSnapshot(
            logical_frame=self.frame_count,
            sha256=hashlib.sha256(payload).hexdigest(),
            rom_sha256=self.rom_sha256,
            pyboy_version=version("pyboy"),
            payload=payload,
        )

    def load_state(self, snapshot: EmulatorSnapshot) -> None:
        self.frame_count, self.step = (
            int(value) for value in snapshot.payload.decode("ascii").split(":")
        )


class _FakeReader:
    def __init__(self, emulator: _FakeEmulator) -> None:
        self.emulator = emulator

    def read(self) -> PokemonRedState:
        if self.emulator.step == 0:
            return PokemonRedState(False, None, None, None, None, None)
        return PokemonRedState(
            game_started=True,
            map_id=int(PokemonRedMap.REDS_HOUSE_1F),
            player_y=6,
            player_x=self.emulator.step,
            party_count=0,
            battle_state=0,
            badge_bits=0,
            pokedex_owned=bytes(19),
            pokedex_seen=bytes(19),
            event_flags=bytes(319),
            bag_item_ids=(),
            got_pokedex=False,
        )


def _patch_fake_emulator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "PokemonRedEmulator", _FakeEmulator)
    monkeypatch.setattr(runner_module, "PokemonRedStateReader", _FakeReader)
    monkeypatch.setattr(expedition_module, "PokemonRedEmulator", _FakeEmulator)
    monkeypatch.setattr(expedition_module, "PokemonRedStateReader", _FakeReader)


def _fingerprint() -> RomFingerprint:
    return RomFingerprint(
        filename="private.gb",
        title="POKEMON RED",
        size_bytes=1,
        sha1="b" * 40,
        sha256="a" * 64,
    )


def test_runner_quarantines_replays_resumes_and_writes_live_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fake_emulator(monkeypatch)
    output = tmp_path / "expedition"
    _FakeEmulator.stop_path = output / "STOP"
    _FakeEmulator.stop_after_step = 1
    config = ExpeditionRunConfig(
        duration_seconds=60,
        max_actions=3,
        seed=7,
        archive_capacity=16,
        min_suffix_actions=3,
        max_suffix_actions=3,
        attempts_per_expansion=2,
        frontier_capture_interval_actions=1,
        loop_window_actions=3,
        loop_repeat_limit=3,
        dashboard_port=0,
        status_interval_seconds=0.001,
        max_output_bytes=16 * 1024 * 1024,
        min_free_bytes=0,
    )

    interrupted = run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
    )

    assert interrupted.stop_reason == "stop_requested"
    assert interrupted.counters.total_actions == 1
    assert not (output / "RUNNING.lock").exists()
    assert (output / "latest.png").is_file()
    assert (output / "index.html").is_file()
    assert (output / "checkpoint.json.gz").is_file()

    with gzip.open(output / "checkpoint.json.gz", "rt", encoding="utf-8") as source:
        stopped_checkpoint = json.load(source)
    restored_rng = random.Random()
    restored_rng.setstate(_json_tuple(stopped_checkpoint["rng_state"]))
    expected_next_random = restored_rng.random()
    repeat_rng = random.Random()
    repeat_rng.setstate(_json_tuple(stopped_checkpoint["rng_state"]))
    assert repeat_rng.random() == expected_next_random

    store = ExpeditionStore.open(output / "frontier")
    active = FrontierArchive.from_checkpoint_dict(store, stopped_checkpoint["archive"])
    assert active.active_cells
    assert all(
        store.successful_replay_count(cell.cell_id) >= store.required_replay_count(cell.cell_id)
        for cell in active.active_cells
    )
    advanced = [cell for cell in active.active_cells if cell.descriptor.milestone_index > 0]
    assert advanced
    assert all(store.successful_replay_count(cell.cell_id) >= 3 for cell in advanced)

    resumed = run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
        resume=True,
    )

    assert resumed.stop_reason == "action_limit"
    assert resumed.counters.total_actions == 3
    assert resumed.best_milestone.key == "left_bedroom"
    assert resumed.counters.replay_passes == resumed.counters.replay_attempts
    assert not (output / "STOP").exists()
    assert not (output / "RUNNING.lock").exists()

    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    boundary = status["information_boundary"]
    assert status["state"] == "finished"
    assert status["power_on_replay_gate_passed"] is True
    assert status["best_milestone"]["key"] == "left_bedroom"
    assert boundary["action_emitter_inputs"] == ["seeded_prng"]
    assert boundary["ram_used_by_actor"] is False
    assert boundary["ram_used_by_referee"] is True
    assert boundary["snapshots_visible_to_actor"] is False

    events = [
        json.loads(line)
        for line in (output / "frontier" / "events.jsonl").read_text().splitlines()
    ]
    replay_events = [event for event in events if event["kind"] == "power_on_replay"]
    root_gate_events = [event for event in events if event["kind"] == "power_on_replay_gate"]
    assert replay_events
    assert len(root_gate_events) == 1
    assert root_gate_events[0]["passed"] is True
    assert root_gate_events[0]["mismatch_reasons"] == []
    assert all(event["passed"] is True and not event["mismatch_reasons"] for event in replay_events)

    trace = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
    finished = [event for event in trace if event["kind"] == "run_finished"]
    assert [event["stop_reason"] for event in finished] == ["stop_requested", "action_limit"]
    assert [event["kind"] for event in trace].count("run_resumed") == 1
