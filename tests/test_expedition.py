from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
from pathlib import Path

import numpy as np
import pytest

import pokemon_red_ai.expedition as expedition_module
from pokemon_red_ai.blind import BlindAction, FrozenSnapshot, visual_key
from pokemon_red_ai.emulator import EmulatorSnapshot, PokemonRedEmulator
from pokemon_red_ai.expedition import (
    ExpeditionStore,
    FrontierArchive,
    FrontierDescriptor,
    descriptor_from_state,
    milestone_progress_for_state,
    referee_summary_for_state,
    replay_frontier_cell,
)
from pokemon_red_ai.milestones import MILESTONE_BY_KEY, PokemonRedEvent, PokemonRedMap
from pokemon_red_ai.rom import ROM_ENVIRONMENT_VARIABLE, verify_rom
from pokemon_red_ai.state import PokemonRedState

ROM_HASH = "ab" * 32


def _snapshot(payload: bytes, *, frame: int = 0) -> FrozenSnapshot:
    import hashlib

    sha256 = hashlib.sha256(payload).hexdigest()
    return FrozenSnapshot.freeze(
        EmulatorSnapshot(
            logical_frame=frame,
            sha256=sha256,
            rom_sha256=ROM_HASH,
            pyboy_version="2.7.0",
            payload=payload,
        )
    )


def _descriptor(index: int, *, visual_class: int = 1) -> FrontierDescriptor:
    key = {
        0: "power_on",
        1: "game_started",
        2: "left_bedroom",
        3: "left_home",
    }[index]
    power_on = index == 0
    return FrontierDescriptor(
        milestone_id=key,
        milestone_index=index,
        map_id=None if power_on else index,
        x_bucket=None if power_on else 1,
        y_bucket=None if power_on else 2,
        battle_kind="unavailable" if power_on else "none",
        visual_class=visual_class,
    )


def _store(tmp_path: Path) -> ExpeditionStore:
    return ExpeditionStore.create(
        tmp_path / "frontier",
        rom_sha256=ROM_HASH,
        pyboy_version="2.7.0",
        metadata={"purpose": "test"},
    )


def _record_required_replays(store: ExpeditionStore, cell_id: str) -> None:
    cell = store.cells[cell_id]
    for _ in range(store.required_replay_count(cell_id)):
        store.audit(
            "power_on_replay",
            cell_id=cell_id,
            passed=True,
            mismatch_reasons=[],
            expected_milestone_id=cell.descriptor.milestone_id,
            expected_milestone_index=cell.descriptor.milestone_index,
            actual_milestone_id=cell.descriptor.milestone_id,
            actual_milestone_index=cell.descriptor.milestone_index,
        )


def test_content_addressed_frontier_round_trip_and_complete_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0, visual_class=0),
        screen_sha256="a" * 64,
        referee_summary={"badge_count": 0},
    )
    first_actions = (BlindAction("start", 8, 12), BlindAction("a", 8, 12))
    first = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"first", frame=40),
        actions_from_parent=first_actions,
        descriptor=_descriptor(1),
        screen_sha256="b" * 64,
        discovered_global_action=2,
        referee_summary={"badge_count": 0, "required_events": 1},
        policy_id="policy-a",
    )
    second_action = (BlindAction("down", 8, 12),)
    second = store.add_cell(
        parent_id=first.cell_id,
        snapshot=_snapshot(b"second", frame=60),
        actions_from_parent=second_action,
        descriptor=_descriptor(2),
        screen_sha256="c" * 64,
        discovered_global_action=3,
        referee_summary={"badge_count": 0, "required_events": 2},
    )

    restored = ExpeditionStore.open(store.path)

    assert tuple(cell.cell_id for cell in restored.lineage(second.cell_id)) == (
        root.cell_id,
        first.cell_id,
        second.cell_id,
    )
    assert restored.lineage_actions(second.cell_id) == first_actions + second_action
    assert second.depth_actions == 3
    assert restored.read_snapshot(second.snapshot_sha256).thaw().payload == b"second"
    events = [json.loads(line) for line in (store.path / "events.jsonl").read_text().splitlines()]
    assert [event["kind"] for event in events] == ["frontier_cell_added"] * 3

    index_path = store.path / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["cell_ids"].reverse()
    index_path.write_text(json.dumps(index), encoding="utf-8")
    read_snapshot = ExpeditionStore.read_snapshot
    validated_snapshots: list[str] = []

    def tracked_read_snapshot(self: ExpeditionStore, sha256: str) -> FrozenSnapshot:
        validated_snapshots.append(sha256)
        return read_snapshot(self, sha256)

    monkeypatch.setattr(ExpeditionStore, "read_snapshot", tracked_read_snapshot)
    reordered = ExpeditionStore.open(store.path)

    assert tuple(cell.cell_id for cell in reordered.lineage(second.cell_id)) == (
        root.cell_id,
        first.cell_id,
        second.cell_id,
    )
    assert len(validated_snapshots) == len(reordered.cells)


def test_lineage_action_iterator_loads_one_segment_at_a_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0, visual_class=0),
        screen_sha256="a" * 64,
        referee_summary={},
    )
    first_actions = (BlindAction("start", 8, 12), BlindAction("a", 8, 12))
    first = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"first", frame=40),
        actions_from_parent=first_actions,
        descriptor=_descriptor(1),
        screen_sha256="b" * 64,
        discovered_global_action=2,
        referee_summary={},
    )
    final_action = BlindAction("down", 8, 12)
    final = store.add_cell(
        parent_id=first.cell_id,
        snapshot=_snapshot(b"final", frame=60),
        actions_from_parent=(final_action,),
        descriptor=_descriptor(2),
        screen_sha256="c" * 64,
        discovered_global_action=3,
        referee_summary={},
    )
    read_segment = store.read_segment
    read_hashes: list[str] = []

    def tracked_read_segment(sha256: str) -> tuple[BlindAction, ...]:
        read_hashes.append(sha256)
        return read_segment(sha256)

    monkeypatch.setattr(store, "read_segment", tracked_read_segment)
    actions = store.iter_lineage_actions(final.cell_id)

    assert read_hashes == []
    assert next(actions) == first_actions[0]
    assert read_hashes == [root.segment_sha256, first.segment_sha256]
    assert tuple(actions) == (first_actions[1], final_action)
    assert read_hashes == [
        root.segment_sha256,
        first.segment_sha256,
        final.segment_sha256,
    ]


def test_successful_replay_index_updates_and_rebuilds_without_rescanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0),
        screen_sha256="a" * 64,
        referee_summary={},
    )
    child = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"child", frame=20),
        actions_from_parent=(BlindAction("a", 8, 12),),
        descriptor=_descriptor(1),
        screen_sha256="b" * 64,
        discovered_global_action=1,
        referee_summary={},
    )
    _record_required_replays(store, child.cell_id)
    store.audit(
        "power_on_replay",
        cell_id=child.cell_id,
        passed=False,
        mismatch_reasons=[],
        expected_milestone_id=child.descriptor.milestone_id,
        expected_milestone_index=child.descriptor.milestone_index,
        actual_milestone_id=child.descriptor.milestone_id,
        actual_milestone_index=child.descriptor.milestone_index,
    )
    store.audit(
        "power_on_replay",
        cell_id=child.cell_id,
        passed=True,
        mismatch_reasons=[],
        expected_milestone_id="power_on",
        expected_milestone_index=0,
        actual_milestone_id=child.descriptor.milestone_id,
        actual_milestone_index=child.descriptor.milestone_index,
    )

    restored = ExpeditionStore.open(store.path)
    assert restored.successful_replay_count(child.cell_id) == 3

    events_path = restored.path / "events.jsonl"
    path_open = Path.open

    def reject_event_log_reads(path: Path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if path == events_path and "r" in mode:
            raise AssertionError("successful_replay_count rescanned the event log")
        return path_open(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "open", reject_event_log_reads)
        assert restored.successful_replay_count(child.cell_id) == 3
        _record_required_replays(restored, child.cell_id)
        assert restored.successful_replay_count(child.cell_id) == 6

    resumed = ExpeditionStore.open(store.path)
    assert resumed.successful_replay_count(child.cell_id) == 6


def test_power_on_replay_streams_actions_and_preserves_planned_action_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    state = PokemonRedState(False, None, None, None, None, None)
    pixels = np.zeros((144, 160, 3), dtype=np.uint8)
    descriptor = descriptor_from_state(
        state,
        milestone_id="power_on",
        milestone_index=0,
        visual_key=visual_key(pixels),
    )
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=descriptor,
        screen_sha256=hashlib.sha256(pixels.tobytes()).hexdigest(),
        referee_summary={},
    )
    planned_actions = (
        BlindAction("a", 8, 12),
        BlindAction("down", 8, 12),
        BlindAction("start", 8, 12),
    )
    target = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"target", frame=60),
        actions_from_parent=planned_actions,
        descriptor=descriptor,
        screen_sha256=hashlib.sha256(pixels.tobytes()).hexdigest(),
        discovered_global_action=3,
        referee_summary={},
    )
    target_snapshot = store.read_snapshot(target.snapshot_sha256).thaw()
    streamed_actions: list[BlindAction] = []
    iter_lineage_actions = store.iter_lineage_actions

    def tracked_actions(cell_id: str):
        for action in iter_lineage_actions(cell_id):
            streamed_actions.append(action)
            yield action

    def reject_materialized_lineage(_cell_id: str):
        raise AssertionError("replay_frontier_cell materialized the complete lineage")

    class FakeEmulator:
        def __init__(self, _rom_path: Path) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def tick(self, _frames: int, *, render_last: bool) -> bool:
            assert render_last
            return False

        def press(self, _button: str, *, hold_frames: int, release_frames: int) -> bool:
            assert hold_frames > 0 and release_frames > 0
            return False

        def screen_rgb(self) -> np.ndarray:
            return pixels

        def save_state(self):
            return target_snapshot

    class FakeStateReader:
        def __init__(self, _emulator: FakeEmulator) -> None:
            pass

        def read(self) -> PokemonRedState:
            return state

    monkeypatch.setattr(store, "iter_lineage_actions", tracked_actions)
    monkeypatch.setattr(store, "lineage_actions", reject_materialized_lineage)
    monkeypatch.setattr(expedition_module, "PokemonRedEmulator", FakeEmulator)
    monkeypatch.setattr(expedition_module, "PokemonRedStateReader", FakeStateReader)

    result = replay_frontier_cell(Path("unused.gb"), store, target.cell_id)

    assert result.action_count == len(planned_actions)
    assert streamed_actions == [planned_actions[0]]
    assert "emulator_stopped" in result.mismatch_reasons


def test_store_rejects_corrupt_snapshot_and_segment_payloads(tmp_path: Path) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0, visual_class=0),
        screen_sha256="a" * 64,
        referee_summary={},
    )
    segment = store._segment_path(root.segment_sha256)  # noqa: SLF001 - integrity test
    segment.write_text("[] \n", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        ExpeditionStore.open(store.path)

    segment.write_text("[]\n", encoding="utf-8")
    snapshot_path = store._snapshot_path(root.snapshot_sha256)  # noqa: SLF001
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as source:
        payload = json.load(source)
    payload["sha256"] = "0" * 64
    with gzip.open(snapshot_path, "wt", encoding="utf-8") as output:
        json.dump(payload, output)
    with pytest.raises(ValueError, match="integrity"):
        ExpeditionStore.open(store.path)


def test_store_rejects_tampered_cell_metadata_and_recovers_orphan_index(tmp_path: Path) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0),
        screen_sha256="a" * 64,
        referee_summary={"milestone_id": "power_on", "milestone_index": 0},
    )
    index_path = store.path / "index.json"
    index_path.write_text('{"schema_version":1,"cell_ids":[]}\n', encoding="utf-8")

    recovered = ExpeditionStore.open(store.path)

    assert list(recovered.cells) == [root.cell_id]
    recovery_events = [
        json.loads(line)
        for line in (store.path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert recovery_events[-1]["kind"] == "orphan_cells_recovered"

    cell_path = store.path / "cells" / f"{root.cell_id}.json"
    cell_payload = json.loads(cell_path.read_text(encoding="utf-8"))
    cell_payload["descriptor"]["milestone_id"] = "hall_of_fame"
    cell_payload["descriptor"]["milestone_index"] = 46
    cell_path.write_text(json.dumps(cell_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="bind|canonical|root"):
        ExpeditionStore.open(store.path)


def test_store_recovers_only_a_torn_final_audit_event(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0),
        screen_sha256="a" * 64,
        referee_summary={},
    )
    events_path = store.path / "events.jsonl"
    with events_path.open("ab") as output:
        output.write(b'{"kind":"archive_dec')

    recovered = ExpeditionStore.open(store.path)
    events = [json.loads(line) for line in events_path.read_text().splitlines()]

    assert recovered.cells
    assert events[-1]["kind"] == "audit_log_tail_recovered"
    assert events[-1]["recovery_kind"] == "discarded_incomplete_final_event"
    recovery_file = store.path / "recovery" / events[-1]["private_recovery_file"]
    assert recovery_file.read_bytes() == b'{"kind":"archive_dec'

    with events_path.open("ab") as output:
        output.write(b'{"kind":}\n')
    with pytest.raises(ValueError, match="audit event JSON"):
        ExpeditionStore.open(store.path)


def test_store_refuses_changed_milestone_semantics(tmp_path: Path) -> None:
    store = _store(tmp_path)
    manifest_path = store.path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["milestone_catalog_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="different milestone semantics"):
        ExpeditionStore.open(store.path)


def test_archive_protects_root_and_advanced_frontier_while_auditing_rejections(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0, visual_class=0),
        screen_sha256="a" * 64,
        referee_summary={},
    )

    def child(parent: str, number: int, stage: int, *, events: int = 0):
        parent_frame = store.read_snapshot(store.cells[parent].snapshot_sha256).logical_frame
        return store.add_cell(
            parent_id=parent,
            snapshot=_snapshot(f"child-{number}".encode(), frame=parent_frame + 20),
            actions_from_parent=(BlindAction("a", 8, 12),),
            descriptor=_descriptor(stage, visual_class=number),
            screen_sha256=f"{number:064x}",
            discovered_global_action=number,
            referee_summary={"required_events": events},
        )

    local = child(root.cell_id, 1, 0)
    frontier = child(local.cell_id, 2, 2)
    weak = child(root.cell_id, 3, 0)
    stronger = child(frontier.cell_id, 4, 3)
    archive = FrontierArchive(store, capacity=3)

    for cell in (local, frontier, weak, stronger):
        _record_required_replays(store, cell.cell_id)

    assert archive.consider(root).admitted
    assert archive.consider(local).admitted
    assert archive.consider(frontier).admitted
    rejected = archive.consider(weak)
    promoted = archive.consider(stronger)

    assert not rejected.admitted
    assert rejected.reason == "capacity_not_competitive"
    assert promoted.admitted
    assert root.cell_id in {cell.cell_id for cell in archive.active_cells}
    assert stronger.cell_id in {cell.cell_id for cell in archive.active_cells}
    assert weak.cell_id in store.cells  # evidence is retained even when selection rejects it
    audit_kinds = [
        json.loads(line)["kind"]
        for line in (store.path / "events.jsonl").read_text().splitlines()
    ]
    assert audit_kinds.count("archive_decision") == 5


def test_frontier_selection_is_deterministic_and_keeps_rehearsal_channel(tmp_path: Path) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0),
        screen_sha256="a" * 64,
        referee_summary={},
    )
    frontier = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"frontier", frame=20),
        actions_from_parent=(BlindAction("a", 8, 12),),
        descriptor=_descriptor(2),
        screen_sha256="b" * 64,
        discovered_global_action=1,
        referee_summary={},
    )
    archive = FrontierArchive(store, capacity=4)
    _record_required_replays(store, frontier.cell_id)
    archive.consider(root)
    archive.consider(frontier)

    selected, channel = archive.select(
        random.Random(1), frontier_probability=1, rehearsal_probability=0
    )
    rehearsed, rehearsal_channel = archive.select(
        random.Random(1), frontier_probability=0, rehearsal_probability=1
    )

    assert (selected.cell_id, channel) == (frontier.cell_id, "frontier")
    assert (rehearsed.cell_id, rehearsal_channel) == (root.cell_id, "rehearsal")

    restored = FrontierArchive.from_checkpoint_dict(store, archive.checkpoint_dict())
    assert restored.checkpoint_dict() == archive.checkpoint_dict()


def test_unverified_cells_remain_quarantined_until_required_replays(tmp_path: Path) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0),
        screen_sha256="a" * 64,
        referee_summary={},
    )
    child = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"child", frame=20),
        actions_from_parent=(BlindAction("a", 8, 12),),
        descriptor=_descriptor(1),
        screen_sha256="b" * 64,
        discovered_global_action=1,
        referee_summary={},
    )
    archive = FrontierArchive(store, capacity=4)
    assert archive.consider(root).admitted

    first_decision = archive.consider(child)
    assert not first_decision.admitted
    assert first_decision.reason == "quarantined_replay_0_of_3"

    _record_required_replays(store, child.cell_id)
    assert archive.consider(child).admitted


def test_unverified_ancestor_cannot_be_laundered_through_a_same_stage_child(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0),
        screen_sha256="a" * 64,
        referee_summary={},
    )
    unverified_advance = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"advance", frame=20),
        actions_from_parent=(BlindAction("a", 8, 12),),
        descriptor=_descriptor(1, visual_class=2),
        screen_sha256="b" * 64,
        discovered_global_action=1,
        referee_summary={},
    )
    same_stage_child = store.add_cell(
        parent_id=unverified_advance.cell_id,
        snapshot=_snapshot(b"child", frame=40),
        actions_from_parent=(BlindAction("down", 8, 12),),
        descriptor=_descriptor(1, visual_class=3),
        screen_sha256="c" * 64,
        discovered_global_action=2,
        referee_summary={},
    )
    archive = FrontierArchive(store, capacity=4)
    assert archive.consider(root).admitted
    _record_required_replays(store, same_stage_child.cell_id)

    blocked = archive.consider(same_stage_child)

    assert not blocked.admitted
    assert blocked.reason.startswith("quarantined_ancestor_")
    assert store.replay_deficits(same_stage_child.cell_id)[0][0] == unverified_advance.cell_id

    _record_required_replays(store, unverified_advance.cell_id)
    assert archive.consider(same_stage_child).admitted


def test_archive_checkpoint_drops_selection_counts_for_replaced_cells(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    root = store.add_root(
        snapshot=_snapshot(b"root"),
        descriptor=_descriptor(0),
        screen_sha256="a" * 64,
        referee_summary={},
    )
    local = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"local", frame=20),
        actions_from_parent=(BlindAction("a", 8, 12),),
        descriptor=_descriptor(0, visual_class=2),
        screen_sha256="b" * 64,
        discovered_global_action=1,
        referee_summary={},
    )
    advanced = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(b"advanced", frame=20),
        actions_from_parent=(BlindAction("down", 8, 12),),
        descriptor=_descriptor(2, visual_class=3),
        screen_sha256="c" * 64,
        discovered_global_action=2,
        referee_summary={},
    )
    for cell in (local, advanced):
        _record_required_replays(store, cell.cell_id)
    archive = FrontierArchive(store, capacity=2)
    assert archive.consider(root).admitted
    assert archive.consider(local).admitted
    archive.selection_counts[local.cell_id] = 7

    assert archive.consider(advanced).admitted
    checkpoint = archive.checkpoint_dict()

    assert local.cell_id not in checkpoint["selection_counts"]
    assert FrontierArchive.from_checkpoint_dict(store, checkpoint).checkpoint_dict() == checkpoint


def test_descriptor_uses_bounded_semantic_and_visual_buckets() -> None:
    state = PokemonRedState(True, 0x26, 11, 19, 0, 0)
    descriptor = descriptor_from_state(
        state,
        milestone_id="left_bedroom",
        milestone_index=2,
        visual_key=bytes.fromhex("1234" + "00" * 14),
    )

    assert descriptor.map_id == 0x26
    assert descriptor.x_bucket == 4
    assert descriptor.y_bucket == 2
    assert descriptor.visual_class == 0x1234
    assert descriptor.battle_kind == "none"


def _event_flags(*bits: int) -> bytes:
    value = bytearray(319)
    for bit_index in bits:
        byte_index, bit = divmod(bit_index, 8)
        value[byte_index] |= 1 << bit
    return bytes(value)


def test_named_progress_is_ordered_inherited_and_strict_about_hall_of_fame() -> None:
    power_on = PokemonRedState(False, None, None, None, None, None)
    started = PokemonRedState(True, 0x26, 6, 3, 0, 0)
    champion_only = PokemonRedState(
        True,
        int(PokemonRedMap.CHAMPIONS_ROOM),
        0,
        0,
        6,
        0,
        event_flags=_event_flags(int(PokemonRedEvent.BEAT_CHAMPION_RIVAL)),
    )
    hall_of_fame = PokemonRedState(
        True,
        int(PokemonRedMap.HALL_OF_FAME),
        0,
        0,
        6,
        0,
        event_flags=_event_flags(int(PokemonRedEvent.BEAT_CHAMPION_RIVAL)),
    )

    root_progress = milestone_progress_for_state(power_on)
    started_progress = milestone_progress_for_state(started)
    champion_progress = milestone_progress_for_state(champion_only)
    complete_progress = milestone_progress_for_state(hall_of_fame)

    assert (root_progress.key, root_progress.index) == ("power_on", 0)
    assert started_progress.key == "game_started"
    assert champion_progress.key == "defeated_champion"
    assert complete_progress.key == "hall_of_fame"
    assert milestone_progress_for_state(power_on, inherited=champion_progress) == champion_progress
    assert referee_summary_for_state(hall_of_fame, complete_progress)["hall_of_fame"] is True
    assert referee_summary_for_state(power_on, complete_progress)["hall_of_fame"] is False


@pytest.mark.integration
def test_power_on_replay_requires_exact_hashes_and_canonical_milestone(tmp_path: Path) -> None:
    raw_path = os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        pytest.skip(f"Set {ROM_ENVIRONMENT_VARIABLE} to run ROM integration tests")
    rom_path = Path(raw_path).expanduser().resolve()
    rom = verify_rom(rom_path)
    store = ExpeditionStore.create(
        tmp_path / "real-frontier",
        rom_sha256=rom.sha256,
        pyboy_version="2.7.0",
    )

    with PokemonRedEmulator(rom_path) as emulator:
        state = PokemonRedState(False, None, None, None, None, None)
        pixels = emulator.screen_rgb()
        snapshot = FrozenSnapshot.freeze(emulator.save_state())
        progress = milestone_progress_for_state(state)
        root = store.add_root(
            snapshot=snapshot,
            descriptor=descriptor_from_state(
                state,
                milestone_id=progress.key,
                milestone_index=progress.index,
                visual_key=visual_key(pixels),
            ),
            screen_sha256=hashlib.sha256(pixels.tobytes()).hexdigest(),
            referee_summary=referee_summary_for_state(state, progress),
        )
        action = BlindAction("noop", 1, 1)
        emulator.tick(action.total_frames, render_last=True)
        next_state = PokemonRedState(False, None, None, None, None, None)
        next_pixels = emulator.screen_rgb()
        next_snapshot = FrozenSnapshot.freeze(emulator.save_state())
        hall = MILESTONE_BY_KEY["hall_of_fame"]
        false_completion = store.add_cell(
            parent_id=root.cell_id,
            snapshot=next_snapshot,
            actions_from_parent=(action,),
            descriptor=descriptor_from_state(
                next_state,
                milestone_id=hall.key,
                milestone_index=hall.ordinal + 1,
                visual_key=visual_key(next_pixels),
            ),
            screen_sha256=hashlib.sha256(next_pixels.tobytes()).hexdigest(),
            discovered_global_action=1,
            referee_summary={
                "milestone_id": hall.key,
                "milestone_index": hall.ordinal + 1,
                "hall_of_fame": True,
            },
        )
        forged_summary = referee_summary_for_state(next_state, progress)
        forged_summary.update(
            {
                "map_id": 0xFF,
                "badge_count": 999,
                "required_events": 999,
                "pokedex_owned": 999,
            }
        )
        forged_niche = store.add_cell(
            parent_id=root.cell_id,
            snapshot=next_snapshot,
            actions_from_parent=(action,),
            descriptor=FrontierDescriptor(
                milestone_id="power_on",
                milestone_index=0,
                map_id=0xFF,
                x_bucket=1,
                y_bucket=1,
                battle_kind="none",
                visual_class=123,
            ),
            screen_sha256=hashlib.sha256(next_pixels.tobytes()).hexdigest(),
            discovered_global_action=2,
            referee_summary=forged_summary,
        )

    root_result = replay_frontier_cell(rom_path, store, root.cell_id)
    false_result = replay_frontier_cell(rom_path, store, false_completion.cell_id)
    forged_result = replay_frontier_cell(rom_path, store, forged_niche.cell_id)

    assert root_result.passed
    assert not false_result.passed
    assert "canonical_milestone_mismatch" in false_result.mismatch_reasons
    assert false_result.actual_milestone_id == "power_on"
    assert not forged_result.passed
    assert "full_descriptor_mismatch" in forged_result.mismatch_reasons
    assert "canonical_referee_summary_mismatch" in forged_result.mismatch_reasons
    replay_events = [
        json.loads(line)
        for line in (store.path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["kind"] == "power_on_replay"
    ]
    assert [event["passed"] for event in replay_events[-3:]] == [True, False, False]
