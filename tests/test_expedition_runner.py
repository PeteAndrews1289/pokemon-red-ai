from __future__ import annotations

import gzip
import hashlib
import json
import random
import urllib.error
import urllib.request
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import pokemon_red_ai.expedition as expedition_module
import pokemon_red_ai.expedition_runner as runner_module
from pokemon_red_ai.blind import BLIND_ACTIONS, FrozenSnapshot
from pokemon_red_ai.emulator import EmulatorSnapshot
from pokemon_red_ai.expedition import ExpeditionStore, FrontierArchive
from pokemon_red_ai.expedition_runner import (
    ExpeditionRunConfig,
    SeededRandomSequenceEmitter,
    VisualLoopDetector,
    _acquire_single_writer,
    _json_tuple,
    _read_checkpoint,
    _release_single_writer,
    _RunDiskMonitor,
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
    with pytest.raises(ValueError, match="reconciliation interval"):
        ExpeditionRunConfig(disk_reconcile_interval_actions=0)
    with pytest.raises(ValueError, match="free-space check interval"):
        ExpeditionRunConfig(disk_free_check_interval_seconds=0)


def test_disk_monitor_does_not_walk_the_tree_for_each_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_snapshot = runner_module._directory_file_sizes
    scans = 0

    def counted_snapshot(path: Path) -> dict[Path, int]:
        nonlocal scans
        scans += 1
        return original_snapshot(path)

    monkeypatch.setattr(runner_module, "_directory_file_sizes", counted_snapshot)
    monitor = _RunDiskMonitor(
        tmp_path,
        max_output_bytes=1_000_000,
        min_free_bytes=0,
        reconcile_interval_actions=64,
        free_check_interval_seconds=1_000,
        now=0,
    )

    assert scans == 1
    for action_count in range(1, 64):
        assert monitor.reason(action_count, now=0) is None
    assert scans == 1

    assert monitor.reason(64, now=0) is None
    assert scans == 2
    assert monitor.exact_reconciliations == 2


def test_disk_monitor_enforces_incremental_size_and_timed_free_space_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"123456789")
    free_values = iter((200, 99))
    free_checks = 0

    def fake_disk_usage(_path: Path) -> SimpleNamespace:
        nonlocal free_checks
        free_checks += 1
        return SimpleNamespace(free=next(free_values))

    monkeypatch.setattr(runner_module.shutil, "disk_usage", fake_disk_usage)
    monitor = _RunDiskMonitor(
        tmp_path,
        max_output_bytes=10,
        min_free_bytes=100,
        reconcile_interval_actions=1_000,
        free_check_interval_seconds=5,
        now=0,
    )

    assert monitor.reason(1, now=4.9) is None
    assert free_checks == 1

    growth = tmp_path / "growth.bin"
    growth.write_bytes(b"xx")
    monitor.observe_files(growth)
    assert monitor.reason(2, now=4.9) == "output_limit"
    assert monitor.output_limit_observed is True

    assert monitor.reason(3, now=5) == "low_disk_space"
    assert free_checks == 2


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


def test_archive_v2_explicitly_refuses_a_v1_runner_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json.gz"
    with gzip.open(checkpoint, "wt", encoding="utf-8") as output:
        json.dump(
            {
                "schema_version": 1,
                "protocol_version": "checkpoint-expedition-runner-v1",
            },
            output,
        )

    with pytest.raises(ValueError, match="cannot resume under Archive v2"):
        _read_checkpoint(checkpoint)


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


class _PowerOnReader:
    def __init__(self, emulator: _FakeEmulator) -> None:
        self.emulator = emulator

    def read(self) -> PokemonRedState:
        return PokemonRedState(False, None, None, None, None, None)


class _PatternFakeEmulator(_FakeEmulator):
    def screen_rgb(self) -> np.ndarray:
        pixels = np.zeros((144, 160, 3), dtype=np.uint8)
        column = (self.step % 20) * 8
        pixels[:, column : column + 8] = 255
        return pixels


def _patch_fake_emulator(
    monkeypatch: pytest.MonkeyPatch,
    reader_type: type[_FakeReader] | type[_PowerOnReader] = _FakeReader,
    emulator_type: type[_FakeEmulator] = _FakeEmulator,
) -> None:
    monkeypatch.setattr(runner_module, "PokemonRedEmulator", emulator_type)
    monkeypatch.setattr(runner_module, "PokemonRedStateReader", reader_type)
    monkeypatch.setattr(expedition_module, "PokemonRedEmulator", emulator_type)
    monkeypatch.setattr(expedition_module, "PokemonRedStateReader", reader_type)


def _fingerprint() -> RomFingerprint:
    return RomFingerprint(
        filename="private.gb",
        title="POKEMON RED",
        size_bytes=1,
        sha1="b" * 40,
        sha256="a" * 64,
    )


@pytest.mark.parametrize("expected_reason", ["output_limit", "low_disk_space"])
def test_runner_enforces_disk_stop_reasons(
    expected_reason: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fake_emulator(monkeypatch)
    _FakeEmulator.stop_path = None
    _FakeEmulator.stop_after_step = None
    output = tmp_path / expected_reason
    max_output_bytes = 1_048_576
    min_free_bytes = 1 if expected_reason == "low_disk_space" else 0

    if expected_reason == "output_limit":
        original_snapshot = runner_module._directory_file_sizes

        def full_snapshot(path: Path) -> dict[Path, int]:
            return {
                **original_snapshot(path),
                path / "virtual-budget-reservation": max_output_bytes,
            }

        monkeypatch.setattr(runner_module, "_directory_file_sizes", full_snapshot)
    else:
        monkeypatch.setattr(
            runner_module.shutil,
            "disk_usage",
            lambda _path: SimpleNamespace(free=0),
        )

    result = run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=ExpeditionRunConfig(
            duration_seconds=60,
            max_actions=10,
            seed=19,
            archive_capacity=16,
            min_suffix_actions=1,
            max_suffix_actions=1,
            attempts_per_expansion=1,
            frontier_capture_interval_actions=1,
            loop_window_actions=2,
            loop_repeat_limit=2,
            status_interval_seconds=10,
            max_output_bytes=max_output_bytes,
            min_free_bytes=min_free_bytes,
        ),
        run_directory=output,
    )

    assert result.stop_reason == expected_reason
    assert result.counters.total_actions == 0
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["stop_reason"] == expected_reason


def test_runner_buffers_many_captures_but_persists_one_ordinary_cell_per_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fake_emulator(monkeypatch, _PowerOnReader, _PatternFakeEmulator)
    _FakeEmulator.stop_path = None
    _FakeEmulator.stop_after_step = None
    output = tmp_path / "one-cell-per-suffix"

    result = run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=ExpeditionRunConfig(
            duration_seconds=60,
            max_actions=4,
            seed=29,
            archive_capacity=16,
            min_suffix_actions=4,
            max_suffix_actions=4,
            attempts_per_expansion=1,
            frontier_capture_interval_actions=1,
            loop_window_actions=4,
            loop_repeat_limit=4,
            status_interval_seconds=10,
            max_output_bytes=16 * 1024 * 1024,
            min_free_bytes=0,
        ),
        run_directory=output,
    )

    assert result.stop_reason == "action_limit"
    assert result.counters.attempts == 1
    assert result.counters.cells_created == 2  # Root plus one buffered candidate.
    assert result.counters.cells_created - 1 == 1
    assert result.counters.cells_admitted - 1 in {0, 1}
    assert result.counters.edge_replay_attempts == 1
    assert result.counters.edge_replay_passes == 1
    assert result.counters.edge_replay_actions <= result.counters.total_actions

    events = [
        json.loads(line) for line in (output / "frontier" / "events.jsonl").read_text().splitlines()
    ]
    assert [event["kind"] for event in events].count("edge_replay") == 1
    assert [event["kind"] for event in events].count("frontier_cell_added") == 2
    suffix = next(
        json.loads(line)
        for line in (output / "trace.jsonl").read_text().splitlines()
        if json.loads(line)["kind"] == "suffix_completed"
    )
    assert suffix["candidate_captures"] == 4
    assert suffix["ordinary_candidates_persisted"] == 1


def test_runner_preflight_drops_uncompetitive_candidates_before_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fake_emulator(monkeypatch, _PowerOnReader, _PatternFakeEmulator)
    _FakeEmulator.stop_path = None
    _FakeEmulator.stop_after_step = None
    output = tmp_path / "preflight-drops"

    result = run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=ExpeditionRunConfig(
            duration_seconds=60,
            max_actions=4,
            seed=37,
            archive_capacity=2,
            min_suffix_actions=1,
            max_suffix_actions=1,
            attempts_per_expansion=1,
            frontier_capture_interval_actions=1,
            loop_window_actions=2,
            loop_repeat_limit=2,
            status_interval_seconds=10,
            max_output_bytes=16 * 1024 * 1024,
            min_free_bytes=0,
        ),
        run_directory=output,
    )

    assert result.stop_reason == "action_limit"
    assert result.counters.attempts == 4
    assert result.counters.cells_created == 2
    assert result.counters.edge_replay_attempts == 1
    assert result.counters.ordinary_preflight_rejections == 3
    store = ExpeditionStore.open(output / "frontier")
    assert len(store.cells) == 2

    suffixes = [
        json.loads(line)
        for line in (output / "trace.jsonl").read_text().splitlines()
        if json.loads(line)["kind"] == "suffix_completed"
    ]
    assert sum(event["ordinary_candidates_persisted"] for event in suffixes) == 1
    assert sum(
        event["ordinary_candidate_preflight"] is not None
        and not event["ordinary_candidate_preflight"]["admitted"]
        for event in suffixes
    ) == 3
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["ordinary_preflight_rejections"] == 3
    assert status["stored_evidence_cells"] == 2


def test_resume_locks_before_mutation_checks_event_head_and_updates_immediate_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fake_emulator(monkeypatch, _PowerOnReader)
    output = tmp_path / "resume-safety"
    _FakeEmulator.stop_path = output / "STOP"
    _FakeEmulator.stop_after_step = 1
    config = ExpeditionRunConfig(
        duration_seconds=60,
        max_actions=3,
        seed=31,
        archive_capacity=16,
        min_suffix_actions=3,
        max_suffix_actions=3,
        attempts_per_expansion=1,
        frontier_capture_interval_actions=1,
        loop_window_actions=3,
        loop_repeat_limit=3,
        dashboard_port=0,
        status_interval_seconds=10,
        max_output_bytes=16 * 1024 * 1024,
        min_free_bytes=1,
    )
    stopped = run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
    )
    assert stopped.stop_reason == "stop_requested"
    trace_before = (output / "trace.jsonl").read_bytes()

    checkpoint_path = output / "checkpoint.json.gz"
    checkpoint_bytes = checkpoint_path.read_bytes()
    with gzip.open(checkpoint_path, "rt", encoding="utf-8") as source:
        frame_checkpoint = json.load(source)
    frame_payload = frame_checkpoint["latest_frame"]["payload_base64"]
    frame_checkpoint["latest_frame"]["payload_base64"] = (
        ("A" if frame_payload[0] != "A" else "B") + frame_payload[1:]
    )
    with gzip.open(checkpoint_path, "wt", encoding="utf-8") as target:
        json.dump(frame_checkpoint, target)
    events_before_frame_failure = (output / "frontier" / "events.jsonl").read_bytes()
    index_before_frame_failure = (output / "frontier" / "index.json").read_bytes()
    with pytest.raises(ValueError, match="checkpoint frame"):
        run_expedition(
            Path("unused.gb"),
            _fingerprint(),
            config=config,
            run_directory=output,
            resume=True,
        )
    assert (output / "trace.jsonl").read_bytes() == trace_before
    assert (output / "frontier" / "events.jsonl").read_bytes() == events_before_frame_failure
    assert (output / "frontier" / "index.json").read_bytes() == index_before_frame_failure
    assert (output / "STOP").is_file()
    checkpoint_path.write_bytes(checkpoint_bytes)

    # The dashboard frame is intentionally mutable between checkpoints and must not be resume
    # state. Simulate a heartbeat that rendered a later screen before the process died.
    divergent_live_frame = np.full((144, 160, 3), 255, dtype=np.uint8)
    runner_module._save_png(divergent_live_frame, output / "latest.png")
    assert hashlib.sha256(divergent_live_frame.tobytes()).hexdigest() != (
        frame_checkpoint["latest_frame_sha256"]
    )

    live_lock = _acquire_single_writer(output)
    try:
        with pytest.raises(RuntimeError, match="live coordinator"):
            run_expedition(
                Path("unused.gb"),
                _fingerprint(),
                config=config,
                run_directory=output,
                resume=True,
            )
        assert (output / "trace.jsonl").read_bytes() == trace_before
        assert (output / "STOP").is_file()
    finally:
        _release_single_writer(live_lock)

    monkeypatch.setattr(
        runner_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=0),
    )
    immediate = run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
        resume=True,
    )
    assert immediate.stop_reason == "low_disk_space"
    assert immediate.counters.total_actions == stopped.counters.total_actions
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "finished"
    assert status["stop_reason"] == "low_disk_space"

    with gzip.open(output / "checkpoint.json.gz", "rt", encoding="utf-8") as source:
        checkpoint_before_recovery = json.load(source)
    (output / "STOP").touch()
    store = ExpeditionStore.open(output / "frontier")
    root = next(cell for cell in store.cells.values() if cell.parent_id is None)
    store.audit(
        "frontier_selected",
        cell_id=root.cell_id,
        channel="frontier",
        selection_count=1,
        selection_total=1,
        promotion_warmup=False,
    )
    recovered_selection = run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
        resume=True,
    )
    assert recovered_selection.stop_reason == "low_disk_space"
    recovery_directories = sorted((output / "frontier" / "recovery").glob("runner-crash-*"))
    assert len(recovery_directories) == 1
    assert b'"kind":"frontier_selected"' in (
        recovery_directories[0] / "events.tail.jsonl"
    ).read_bytes()
    trace = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
    assert any(event["kind"] == "runner_post_checkpoint_store_recovered" for event in trace)
    with gzip.open(output / "checkpoint.json.gz", "rt", encoding="utf-8") as source:
        checkpoint_after_selection = json.load(source)
    assert checkpoint_after_selection["rng_state"] == checkpoint_before_recovery["rng_state"]
    assert checkpoint_after_selection["archive"] == checkpoint_before_recovery["archive"]
    assert checkpoint_after_selection["attempts_by_parent"] == (
        checkpoint_before_recovery["attempts_by_parent"]
    )

    def add_extra_cell(discovered_global_action: int) -> object:
        store = ExpeditionStore.open(output / "frontier")
        root = next(cell for cell in store.cells.values() if cell.parent_id is None)
        extra_emulator = _FakeEmulator(Path("unused.gb"))
        extra_action = SeededRandomSequenceEmitter(random.Random(97)).emit()
        extra_emulator.press(
            extra_action.button,
            hold_frames=extra_action.hold_frames,
            release_frames=extra_action.release_frames,
        )
        return store.add_cell(
            parent_id=root.cell_id,
            snapshot=FrozenSnapshot.freeze(extra_emulator.save_state()),
            actions_from_parent=(extra_action,),
            descriptor=root.descriptor,
            screen_sha256=hashlib.sha256(extra_emulator.screen_rgb().tobytes()).hexdigest(),
            discovered_global_action=discovered_global_action,
            referee_summary=root.referee_summary,
            policy_id=SeededRandomSequenceEmitter.policy_id,
        )

    extra = add_extra_cell(999)
    original_apply_recovery = runner_module._apply_recovery_bundle

    def crash_after_events(
        store_path: Path,
        recovery_directory: Path,
        _pending_path: Path,
    ) -> object:
        runner_module._atomic_binary(
            store_path / "events.jsonl",
            (recovery_directory / "events.checkpoint.jsonl").read_bytes(),
        )
        raise RuntimeError("simulated crash after event restoration")

    monkeypatch.setattr(runner_module, "_apply_recovery_bundle", crash_after_events)
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_expedition(
            Path("unused.gb"),
            _fingerprint(),
            config=config,
            run_directory=output,
            resume=True,
        )
    assert (output / "frontier" / "recovery" / "PENDING.json").is_file()
    assert extra.cell_id in json.loads(
        (output / "frontier" / "index.json").read_text(encoding="utf-8")
    )["cell_ids"]

    # Even a syntactically valid PENDING marker cannot authorize rollback until the complete
    # checkpoint has been revalidated on this invocation.
    pending_path = output / "frontier" / "recovery" / "PENDING.json"
    pending_bytes = pending_path.read_bytes()
    checkpoint_bytes = (output / "checkpoint.json.gz").read_bytes()
    with gzip.open(output / "checkpoint.json.gz", "rt", encoding="utf-8") as source:
        invalid_pending_checkpoint = json.load(source)
    invalid_pending_checkpoint["counters"]["attempts"] += 1
    with gzip.open(output / "checkpoint.json.gz", "wt", encoding="utf-8") as target:
        json.dump(invalid_pending_checkpoint, target)
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    pending["checkpoint_sha256"] = runner_module._checkpoint_identity_sha256(
        invalid_pending_checkpoint
    )
    pending_path.write_text(json.dumps(pending), encoding="utf-8")
    invalid_pending_bytes = pending_path.read_bytes()
    events_before_invalid_pending = (output / "frontier" / "events.jsonl").read_bytes()
    index_before_invalid_pending = (output / "frontier" / "index.json").read_bytes()
    cells_before_invalid_pending = {
        path.name: path.read_bytes() for path in (output / "frontier" / "cells").glob("*.json")
    }
    trace_before_invalid_pending = (output / "trace.jsonl").read_bytes()
    stop_before_invalid_pending = (output / "STOP").exists()
    with pytest.raises(ValueError, match="attempt totals"):
        run_expedition(
            Path("unused.gb"),
            _fingerprint(),
            config=config,
            run_directory=output,
            resume=True,
        )
    assert pending_path.read_bytes() == invalid_pending_bytes
    assert (output / "frontier" / "events.jsonl").read_bytes() == events_before_invalid_pending
    assert (output / "frontier" / "index.json").read_bytes() == index_before_invalid_pending
    assert {
        path.name: path.read_bytes() for path in (output / "frontier" / "cells").glob("*.json")
    } == cells_before_invalid_pending
    assert (output / "trace.jsonl").read_bytes() == trace_before_invalid_pending
    assert (output / "STOP").exists() is stop_before_invalid_pending
    (output / "checkpoint.json.gz").write_bytes(checkpoint_bytes)
    pending_path.write_bytes(pending_bytes)

    monkeypatch.setattr(runner_module, "_apply_recovery_bundle", original_apply_recovery)
    run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
        resume=True,
    )
    recovery_directories = sorted((output / "frontier" / "recovery").glob("runner-crash-*"))
    assert len(recovery_directories) == 2
    cell_recovery = next(
        directory
        for directory in recovery_directories
        if (directory / "cells" / f"{extra.cell_id}.json").is_file()
    )
    recovery_manifest = json.loads(
        (cell_recovery / "manifest.json").read_text(encoding="utf-8")
    )
    assert extra.cell_id in recovery_manifest["observed_cell_ids"]
    restored_store = ExpeditionStore.open(output / "frontier")
    assert extra.cell_id not in restored_store.cells
    assert not (output / "frontier" / "cells" / f"{extra.cell_id}.json").exists()
    assert not (output / "frontier" / "recovery" / "PENDING.json").exists()

    extra_after_index = add_extra_cell(1_000)

    def crash_after_index(
        store_path: Path,
        recovery_directory: Path,
        _pending_path: Path,
    ) -> object:
        runner_module._atomic_binary(
            store_path / "events.jsonl",
            (recovery_directory / "events.checkpoint.jsonl").read_bytes(),
        )
        manifest = json.loads(
            (recovery_directory / "manifest.json").read_text(encoding="utf-8")
        )
        runner_module._atomic_binary(
            store_path / "index.json",
            (json.dumps(
                {"schema_version": 1, "cell_ids": manifest["checkpoint_cell_ids"]},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n").encode("utf-8"),
        )
        raise RuntimeError("simulated crash after index restoration")

    monkeypatch.setattr(runner_module, "_apply_recovery_bundle", crash_after_index)
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_expedition(
            Path("unused.gb"),
            _fingerprint(),
            config=config,
            run_directory=output,
            resume=True,
        )
    assert extra_after_index.cell_id not in json.loads(
        (output / "frontier" / "index.json").read_text(encoding="utf-8")
    )["cell_ids"]
    assert (output / "frontier" / "cells" / f"{extra_after_index.cell_id}.json").is_file()
    monkeypatch.setattr(runner_module, "_apply_recovery_bundle", original_apply_recovery)
    run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
        resume=True,
    )
    assert not (output / "frontier" / "cells" / f"{extra_after_index.cell_id}.json").exists()
    assert not (output / "frontier" / "recovery" / "PENDING.json").exists()

    original_audit = ExpeditionStore.audit

    def crash_after_cell_metadata(
        self: ExpeditionStore,
        kind: str,
        **payload: object,
    ) -> None:
        if kind == "frontier_cell_added":
            raise RuntimeError("simulated crash after cell metadata")
        original_audit(self, kind, **payload)

    indexed_before_orphan = set(
        json.loads((output / "frontier" / "index.json").read_text(encoding="utf-8"))[
            "cell_ids"
        ]
    )
    monkeypatch.setattr(ExpeditionStore, "audit", crash_after_cell_metadata)
    with pytest.raises(RuntimeError, match="after cell metadata"):
        add_extra_cell(1_001)
    monkeypatch.setattr(ExpeditionStore, "audit", original_audit)
    orphan_ids = {
        path.stem for path in (output / "frontier" / "cells").glob("*.json")
    } - indexed_before_orphan
    assert len(orphan_ids) == 1
    orphan_id = orphan_ids.pop()
    run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
        resume=True,
    )
    orphan_recovery = next(
        directory
        for directory in (output / "frontier" / "recovery").glob("runner-crash-*")
        if (directory / "cells" / f"{orphan_id}.json").is_file()
    )
    assert (orphan_recovery / "events.tail.jsonl").read_bytes() == b""
    assert not (output / "frontier" / "cells" / f"{orphan_id}.json").exists()

    original_atomic_json = expedition_module._atomic_json
    live_index_path = (output / "frontier" / "index.json").resolve()

    def crash_before_index(path: Path, value: object) -> None:
        if path.resolve() == live_index_path:
            raise RuntimeError("simulated crash before cell index")
        original_atomic_json(path, value)

    monkeypatch.setattr(expedition_module, "_atomic_json", crash_before_index)
    with pytest.raises(RuntimeError, match="before cell index"):
        add_extra_cell(1_002)
    monkeypatch.setattr(expedition_module, "_atomic_json", original_atomic_json)
    event_without_index = (output / "frontier" / "events.jsonl").read_bytes()
    run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
        resume=True,
    )
    assert any(
        b'"kind":"frontier_cell_added"' in (directory / "events.tail.jsonl").read_bytes()
        for directory in (output / "frontier" / "recovery").glob("runner-crash-*")
    )
    assert (output / "frontier" / "events.jsonl").read_bytes() != event_without_index

    original_append_json = expedition_module._append_json
    live_events_path = (output / "frontier" / "events.jsonl").resolve()

    def crash_during_event_append(path: Path, value: object) -> None:
        if (
            path.resolve() == live_events_path
            and isinstance(value, dict)
            and value.get("kind") == "frontier_cell_added"
        ):
            encoded = expedition_module._canonical_json(value) + b"\n"
            with path.open("ab") as target:
                target.write(encoded[: len(encoded) // 2])
                target.flush()
            raise RuntimeError("simulated crash during event append")
        original_append_json(path, value)

    checkpoint_event_bytes = (output / "frontier" / "events.jsonl").read_bytes()
    monkeypatch.setattr(expedition_module, "_append_json", crash_during_event_append)
    with pytest.raises(RuntimeError, match="during event append"):
        add_extra_cell(1_003)
    monkeypatch.setattr(expedition_module, "_append_json", original_append_json)
    torn_event_bytes = (output / "frontier" / "events.jsonl").read_bytes()[
        len(checkpoint_event_bytes) :
    ]
    assert torn_event_bytes and not torn_event_bytes.endswith(b"\n")
    run_expedition(
        Path("unused.gb"),
        _fingerprint(),
        config=config,
        run_directory=output,
        resume=True,
    )
    assert any(
        (directory / "events.tail.jsonl").read_bytes() == torn_event_bytes
        for directory in (output / "frontier" / "recovery").glob("runner-crash-*")
    )

    events_path = output / "frontier" / "events.jsonl"
    valid_events = events_path.read_bytes()
    tampered_events = valid_events.replace(
        b'"kind":"frontier_cell_added"',
        b'"kind":"frontier_cell_addeX"',
        1,
    )
    assert tampered_events != valid_events
    events_path.write_bytes(tampered_events)
    (output / "STOP").touch()
    trace_before_tamper = (output / "trace.jsonl").read_bytes()
    with pytest.raises(ValueError, match="event hash"):
        run_expedition(
            Path("unused.gb"),
            _fingerprint(),
            config=config,
            run_directory=output,
            resume=True,
        )
    assert events_path.read_bytes() == tampered_events
    assert (output / "trace.jsonl").read_bytes() == trace_before_tamper
    assert (output / "STOP").is_file()
    events_path.write_bytes(valid_events)

    with gzip.open(output / "checkpoint.json.gz", "rt", encoding="utf-8") as source:
        exact_checkpoint = json.load(source)
    behind_events = valid_events[: int(exact_checkpoint["store_event_byte_offset"]) - 1]
    events_path.write_bytes(behind_events)
    trace_before_behind = (output / "trace.jsonl").read_bytes()
    with pytest.raises(ValueError, match="behind"):
        run_expedition(
            Path("unused.gb"),
            _fingerprint(),
            config=config,
            run_directory=output,
            resume=True,
        )
    assert events_path.read_bytes() == behind_events
    assert (output / "trace.jsonl").read_bytes() == trace_before_behind
    assert (output / "STOP").is_file()
    events_path.write_bytes(valid_events)

    with gzip.open(output / "checkpoint.json.gz", "rt", encoding="utf-8") as source:
        invalid_checkpoint = json.load(source)
    invalid_checkpoint["counters"]["attempts"] += 1
    with gzip.open(output / "checkpoint.json.gz", "wt", encoding="utf-8") as target:
        json.dump(invalid_checkpoint, target)
    (output / "STOP").touch()
    trace_before_invalid = (output / "trace.jsonl").read_bytes()
    events_before_invalid = (output / "frontier" / "events.jsonl").read_bytes()
    index_before_invalid = (output / "frontier" / "index.json").read_bytes()
    cells_before_invalid = sorted((output / "frontier" / "cells").glob("*.json"))
    with pytest.raises(ValueError, match="attempt totals"):
        run_expedition(
            Path("unused.gb"),
            _fingerprint(),
            config=config,
            run_directory=output,
            resume=True,
        )
    assert (output / "trace.jsonl").read_bytes() == trace_before_invalid
    assert (output / "frontier" / "events.jsonl").read_bytes() == events_before_invalid
    assert (output / "frontier" / "index.json").read_bytes() == index_before_invalid
    assert sorted((output / "frontier" / "cells").glob("*.json")) == cells_before_invalid
    assert (output / "STOP").is_file()
    assert not (output / "RUNNING.lock").exists()


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
    assert interrupted.counters.attempts == 1
    assert interrupted.counters.cells_created == 2
    assert interrupted.counters.edge_replay_attempts == 1
    assert interrupted.counters.edge_replay_actions == 1
    assert interrupted.counters.edge_replay_passes == 1
    assert interrupted.counters.promotion_power_on_replay_attempts == 1
    assert interrupted.counters.promotion_power_on_replay_actions == 0
    assert interrupted.counters.promotion_power_on_replay_passes == 0
    assert interrupted.counters.replay_attempts == 3  # Root + edge + cancelled promotion.
    assert interrupted.counters.replay_actions == 1
    assert interrupted.counters.replay_passes == 2
    assert not (output / "RUNNING.lock").exists()
    assert (output / "latest.png").is_file()
    assert (output / "index.html").is_file()
    assert (output / "checkpoint.json.gz").is_file()

    with gzip.open(output / "checkpoint.json.gz", "rt", encoding="utf-8") as source:
        stopped_checkpoint = json.load(source)
    assert stopped_checkpoint["schema_version"] == 2
    assert stopped_checkpoint["counters"]["edge_replay_attempts"] == 1
    assert stopped_checkpoint["counters"]["promotion_power_on_replay_attempts"] == 1
    assert stopped_checkpoint["store_event_sequence"] > 0
    assert len(stopped_checkpoint["store_event_head_sha256"]) == 64
    interrupted_trace = [
        json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()
    ]
    first_suffix = next(event for event in interrupted_trace if event["kind"] == "suffix_completed")
    assert first_suffix["suffix_budget"] == 3
    assert first_suffix["actions_executed"] == 1
    assert first_suffix["stop_reason"] == "named_milestone_rejected"
    interrupted_events = [
        json.loads(line) for line in (output / "frontier" / "events.jsonl").read_text().splitlines()
    ]
    assert [event["kind"] for event in interrupted_events].count("edge_replay") == 1
    assert [event["kind"] for event in interrupted_events].count("power_on_replay") == 2
    cancelled_replay = next(
        event
        for event in interrupted_events
        if event["kind"] == "power_on_replay" and not event["passed"]
    )
    assert cancelled_replay["executed_action_count"] == 0
    assert "replay_cancelled" in cancelled_replay["mismatch_reasons"]
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
    assert not [cell for cell in active.active_cells if cell.descriptor.milestone_index > 0]

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
    assert resumed.counters.replay_passes == resumed.counters.replay_attempts - 1
    assert resumed.counters.edge_replay_actions <= resumed.counters.total_actions
    assert resumed.counters.replay_attempts == (
        1
        + resumed.counters.edge_replay_attempts
        + resumed.counters.promotion_power_on_replay_attempts
    )
    assert not (output / "STOP").exists()
    assert not (output / "RUNNING.lock").exists()

    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    boundary = status["information_boundary"]
    assert status["state"] == "finished"
    assert status["power_on_replay_gate_passed"] is True
    assert status["best_milestone"]["key"] == "left_bedroom"
    assert status["edge_replay_actions"] <= status["total_actions"]
    assert status["edge_replay_action_ratio"] <= 1
    assert status["edge_replay_attempts"] == resumed.counters.edge_replay_attempts
    assert status["promotion_power_on_replay_attempts"] == (
        resumed.counters.promotion_power_on_replay_attempts
    )
    disk_metrics = status["disk_monitor"]
    assert disk_metrics["run_bytes"] == status["run_bytes"]
    assert runner_module._directory_size(output) == status["run_bytes"]
    assert disk_metrics["exact_size_reconciliations"] >= 1
    assert disk_metrics["incremental_file_checks"] >= 1
    assert disk_metrics["free_space_checks"] >= 1
    assert disk_metrics["output_limit_observed"] is False
    assert boundary["action_emitter_inputs"] == ["seeded_prng"]
    assert boundary["ram_used_by_actor"] is False
    assert boundary["ram_used_by_referee"] is True
    assert boundary["snapshots_visible_to_actor"] is False

    events = [
        json.loads(line) for line in (output / "frontier" / "events.jsonl").read_text().splitlines()
    ]
    replay_events = [event for event in events if event["kind"] == "power_on_replay"]
    edge_events = [event for event in events if event["kind"] == "edge_replay"]
    root_gate_events = [event for event in events if event["kind"] == "power_on_replay_gate"]
    assert replay_events
    assert edge_events
    assert len(root_gate_events) == 1
    assert root_gate_events[0]["passed"] is True
    assert root_gate_events[0]["mismatch_reasons"] == []
    failed_replays = [event for event in replay_events if not event["passed"]]
    assert len(failed_replays) == 1
    assert "replay_cancelled" in failed_replays[0]["mismatch_reasons"]
    assert all(not event["mismatch_reasons"] for event in replay_events if event["passed"])

    trace = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
    finished = [event for event in trace if event["kind"] == "run_finished"]
    assert [event["stop_reason"] for event in finished] == ["stop_requested", "action_limit"]
    assert [event["kind"] for event in trace].count("run_resumed") == 1
