from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import pokemon_red_ai.apprentice_data as apprentice_module
import pokemon_red_ai.expedition as expedition_module
from pokemon_red_ai.apprentice_data import (
    APPRENTICE_FRAME_SHAPE,
    ApprenticeDatasetError,
    capture_apprentice_dataset,
    load_apprentice_dataset,
    preprocess_apprentice_frame,
    verify_apprentice_dataset,
)
from pokemon_red_ai.blind import BLIND_ACTIONS, BlindAction, FrozenSnapshot
from pokemon_red_ai.emulator import EmulatorSnapshot
from pokemon_red_ai.expedition import (
    ExpeditionStore,
    FrontierDescriptor,
    MilestoneProgress,
)
from pokemon_red_ai.rom import RomFingerprint

ROM_HASH = "ab" * 32
PYBOY_VERSION = "2.7.0"


def _snapshot(payload: bytes, *, logical_frame: int) -> FrozenSnapshot:
    return FrozenSnapshot.freeze(
        EmulatorSnapshot(
            logical_frame=logical_frame,
            sha256=hashlib.sha256(payload).hexdigest(),
            rom_sha256=ROM_HASH,
            pyboy_version=PYBOY_VERSION,
            payload=payload,
        )
    )


def _screen(step: int) -> np.ndarray:
    y, x = np.indices((144, 160), dtype=np.uint16)
    return np.stack(
        (
            (x + step) % 256,
            (2 * y + 3 * step) % 256,
            (x + y + 5 * step) % 256,
        ),
        axis=2,
    ).astype(np.uint8)


def _root_descriptor() -> FrontierDescriptor:
    return FrontierDescriptor(
        milestone_id="power_on",
        milestone_index=0,
        map_id=None,
        x_bucket=None,
        y_bucket=None,
        battle_kind="unavailable",
        visual_class=0,
    )


def _target_descriptor() -> FrontierDescriptor:
    return FrontierDescriptor(
        milestone_id="game_started",
        milestone_index=1,
        map_id=1,
        x_bucket=1,
        y_bucket=2,
        battle_kind="none",
        visual_class=123,
    )


def _target_summary() -> dict[str, int | str | bool | None]:
    return {
        "milestone_id": "game_started",
        "milestone_index": 1,
        "milestone_label": "The adventure begins",
        "map_id": 1,
        "badge_count": 0,
        "required_events": 1,
        "party_count": 0,
        "pokedex_seen": 0,
        "pokedex_owned": 0,
        "got_pokedex": False,
        "hall_of_fame": False,
    }


def _record_power_on_replay(store: ExpeditionStore, cell_id: str) -> None:
    cell = store.cells[cell_id]
    store.audit(
        "power_on_replay",
        cell_id=cell.cell_id,
        action_count=cell.depth_actions,
        executed_action_count=cell.depth_actions,
        passed=True,
        mismatch_reasons=[],
        failure_reason=None,
        expected_snapshot_sha256=cell.snapshot_sha256,
        actual_snapshot_sha256=cell.snapshot_sha256,
        expected_screen_sha256=cell.screen_sha256,
        actual_screen_sha256=cell.screen_sha256,
        expected_milestone_id=cell.descriptor.milestone_id,
        expected_milestone_index=cell.descriptor.milestone_index,
        actual_milestone_id=cell.descriptor.milestone_id,
        actual_milestone_index=cell.descriptor.milestone_index,
        expected_descriptor=cell.descriptor.public_dict(),
        actual_descriptor=cell.descriptor.public_dict(),
        expected_referee_summary=dict(cell.referee_summary),
        actual_referee_summary=expedition_module._replay_referee_projection(
            cell.referee_summary
        ),
    )


def _record_edge_replay(store: ExpeditionStore, cell_id: str) -> None:
    cell = store.cells[cell_id]
    assert cell.parent_id is not None
    parent = store.cells[cell.parent_id]
    store.audit(
        "edge_replay",
        cell_id=cell.cell_id,
        parent_id=parent.cell_id,
        expected_parent_snapshot_sha256=parent.snapshot_sha256,
        expected_segment_sha256=cell.segment_sha256,
        action_count=cell.depth_actions - parent.depth_actions,
        executed_action_count=cell.depth_actions - parent.depth_actions,
        passed=True,
        mismatch_reasons=[],
        failure_reason=None,
        expected_snapshot_sha256=cell.snapshot_sha256,
        actual_snapshot_sha256=cell.snapshot_sha256,
        expected_screen_sha256=cell.screen_sha256,
        actual_screen_sha256=cell.screen_sha256,
        expected_milestone_id=cell.descriptor.milestone_id,
        expected_milestone_index=cell.descriptor.milestone_index,
        actual_milestone_id=cell.descriptor.milestone_id,
        actual_milestone_index=cell.descriptor.milestone_index,
        expected_descriptor=cell.descriptor.public_dict(),
        actual_descriptor=cell.descriptor.public_dict(),
        expected_referee_summary=dict(cell.referee_summary),
        actual_referee_summary=expedition_module._replay_referee_projection(
            cell.referee_summary
        ),
    )


@dataclass(slots=True)
class _SourceFixture:
    store: ExpeditionStore
    target_id: str
    lineage_sha256: str
    actions: tuple[BlindAction, ...]
    terminal_payload: bytes


def _make_source(
    tmp_path: Path,
    *,
    action_count: int = 3,
    replay_count: int = 3,
    promotion: bool = True,
) -> _SourceFixture:
    store = ExpeditionStore.create(
        tmp_path / "frontier",
        rom_sha256=ROM_HASH,
        pyboy_version=PYBOY_VERSION,
    )
    root = store.add_root(
        snapshot=_snapshot(b"power-on", logical_frame=0),
        descriptor=_root_descriptor(),
        screen_sha256=hashlib.sha256(_screen(0).tobytes()).hexdigest(),
        referee_summary={},
    )
    actions = tuple(
        BlindAction(BLIND_ACTIONS[index % len(BLIND_ACTIONS)], 8, 12)
        for index in range(action_count)
    )
    terminal_payload = b"terminal-state"
    descriptor = _target_descriptor() if promotion else _root_descriptor()
    summary = _target_summary() if promotion else {}
    target = store.add_cell(
        parent_id=root.cell_id,
        snapshot=_snapshot(terminal_payload, logical_frame=20 * action_count),
        actions_from_parent=actions,
        descriptor=descriptor,
        screen_sha256=hashlib.sha256(_screen(action_count).tobytes()).hexdigest(),
        discovered_global_action=action_count,
        referee_summary=summary,
    )
    _record_edge_replay(store, target.cell_id)
    for _ in range(replay_count):
        _record_power_on_replay(store, target.cell_id)
    return _SourceFixture(
        store=store,
        target_id=target.cell_id,
        lineage_sha256=target.lineage_sha256,
        actions=actions,
        terminal_payload=terminal_payload,
    )


@dataclass(frozen=True, slots=True)
class _FakeState:
    step: int
    terminal_step: int

    def public_dict(self) -> dict[str, int]:
        return {"step": self.step}


def _install_capture_fakes(
    monkeypatch: pytest.MonkeyPatch,
    source: _SourceFixture,
    *,
    terminal_snapshot_matches: bool = True,
) -> None:
    monkeypatch.setattr(apprentice_module, "STAGE0_Q1_TARGET_CELL_ID", source.target_id)
    monkeypatch.setattr(
        apprentice_module,
        "STAGE0_Q1_LINEAGE_SHA256",
        source.lineage_sha256,
    )
    monkeypatch.setattr(
        apprentice_module,
        "STAGE0_Q1_ACTION_COUNT",
        len(source.actions),
    )
    monkeypatch.setattr(apprentice_module, "STAGE0_Q1_MILESTONE_ID", "game_started")
    monkeypatch.setattr(
        apprentice_module,
        "detect_source_provenance",
        lambda: SimpleNamespace(
            git_commit="a" * 40,
            worktree_dirty=False,
            public_dict=lambda: {
                "git_commit": "a" * 40,
                "worktree_dirty": False,
            },
        ),
    )
    class FakeEmulator:
        def __init__(self, _rom_path: Path) -> None:
            self.step = 0

        def __enter__(self) -> FakeEmulator:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def screen_rgb(self) -> np.ndarray:
            return _screen(self.step)

        def press(
            self,
            button: str,
            *,
            hold_frames: int,
            release_frames: int,
        ) -> bool:
            expected = source.actions[self.step]
            assert (button, hold_frames, release_frames) == (
                expected.button,
                expected.hold_frames,
                expected.release_frames,
            )
            self.step += 1
            return True

        def tick(self, frames: int, *, render_last: bool) -> bool:
            expected = source.actions[self.step]
            assert expected.button == "noop"
            assert frames == expected.total_frames
            assert render_last is True
            self.step += 1
            return True

        def save_state(self) -> SimpleNamespace:
            payload = source.terminal_payload if terminal_snapshot_matches else b"wrong"
            return SimpleNamespace(sha256=hashlib.sha256(payload).hexdigest())

    class FakeReader:
        def __init__(self, emulator: FakeEmulator) -> None:
            self.emulator = emulator

        def read(self) -> _FakeState:
            return _FakeState(self.emulator.step, len(source.actions))

    def fake_progress(
        state: _FakeState,
        *,
        inherited: MilestoneProgress | None = None,
    ) -> MilestoneProgress:
        if state.step == state.terminal_step:
            return MilestoneProgress("game_started", 1, "The adventure begins")
        return inherited or MilestoneProgress("power_on", 0, "Power-on")

    fingerprint = RomFingerprint(
        filename="private.gb",
        title="POKEMON RED",
        size_bytes=1,
        sha1="cd" * 20,
        sha256=ROM_HASH,
    )
    monkeypatch.setattr(apprentice_module, "PokemonRedEmulator", FakeEmulator)
    monkeypatch.setattr(apprentice_module, "PokemonRedStateReader", FakeReader)
    monkeypatch.setattr(apprentice_module, "milestone_progress_for_state", fake_progress)
    monkeypatch.setattr(
        apprentice_module,
        "descriptor_from_state",
        lambda *_args, **_kwargs: _target_descriptor(),
    )
    monkeypatch.setattr(
        apprentice_module,
        "referee_summary_for_state",
        lambda *_args, **_kwargs: _target_summary(),
    )
    monkeypatch.setattr(apprentice_module, "verify_rom", lambda _path: fingerprint)


def _source_hashes(path: Path) -> dict[str, str]:
    return {
        str(item.relative_to(path)): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_preprocess_apprentice_frame_freezes_integer_grayscale_and_pooling() -> None:
    pixels = np.zeros((144, 160, 3), dtype=np.uint8)
    pixels[0, 0] = (255, 0, 0)
    pixels[0, 1] = (0, 255, 0)
    pixels[1, 0] = (0, 0, 255)
    pixels[1, 1] = (255, 255, 255)

    frame = preprocess_apprentice_frame(pixels)

    assert frame.shape == APPRENTICE_FRAME_SHAPE
    assert frame.dtype == np.uint8
    individual = [
        (77 * 255 + 128) >> 8,
        (150 * 255 + 128) >> 8,
        (29 * 255 + 128) >> 8,
        (256 * 255 + 128) >> 8,
    ]
    assert frame[0, 0] == sum(individual) // 4
    assert np.count_nonzero(frame) == 1


@pytest.mark.parametrize(
    "pixels,exception",
    [
        (np.zeros((72, 80, 3), dtype=np.uint8), ValueError),
        (np.zeros((144, 160, 3), dtype=np.float32), ValueError),
        ([[[0, 0, 0]]], TypeError),
    ],
)
def test_preprocess_rejects_unversioned_inputs(pixels: Any, exception: type[Exception]) -> None:
    with pytest.raises(exception):
        preprocess_apprentice_frame(pixels)


def test_capture_419_actions_produces_420_verified_boundaries_without_mutating_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_source(tmp_path, action_count=419)
    _install_capture_fakes(monkeypatch, source)
    source_before = _source_hashes(source.store.path)
    rom_path = tmp_path / "private.gb"
    rom_path.write_bytes(b"private test placeholder")
    output = tmp_path / "apprentice-dataset"

    manifest = capture_apprentice_dataset(
        rom_path,
        source.store.path,
        source.target_id,
        source.lineage_sha256,
        output,
    )
    dataset = load_apprentice_dataset(output)

    assert manifest["action_count"] == 419
    assert manifest["decision_boundary_frame_count"] == 420
    assert dataset.frames.shape == (420, 72, 80)
    assert dataset.actions.shape == (419,)
    assert dataset.previous_actions[0] == -1
    assert np.array_equal(dataset.previous_actions[1:], dataset.actions[:-1])
    assert dataset.episode_starts.tolist() == [True] + [False] * 418
    assert not dataset.frames.flags.writeable
    assert {item.name for item in output.iterdir()} == {
        ".gitignore",
        "frames.npy",
        "actions.npy",
        "previous_actions.npy",
        "episode_starts.npy",
        "manifest.json",
        "SUCCESS",
    }
    assert _source_hashes(source.store.path) == source_before
    assert not list(tmp_path.glob(".apprentice-dataset.tmp-*"))
    assert not (tmp_path / ".apprentice-dataset.publish.lock").exists()


def test_capture_requires_explicit_promotion_hash_and_three_power_on_replays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_source(tmp_path, replay_count=2)
    _install_capture_fakes(monkeypatch, source)
    rom_path = tmp_path / "private.gb"
    rom_path.write_bytes(b"placeholder")

    with pytest.raises(ApprenticeDatasetError, match="different lineage hash"):
        capture_apprentice_dataset(
            rom_path,
            source.store.path,
            source.target_id,
            "0" * 64,
            tmp_path / "wrong-lineage",
        )
    with pytest.raises(ApprenticeDatasetError, match="three validated fresh power-on"):
        capture_apprentice_dataset(
            rom_path,
            source.store.path,
            source.target_id,
            source.lineage_sha256,
            tmp_path / "unverified",
        )
    ordinary = _make_source(tmp_path / "ordinary", promotion=False)
    monkeypatch.setattr(apprentice_module, "STAGE0_Q1_TARGET_CELL_ID", ordinary.target_id)
    monkeypatch.setattr(
        apprentice_module,
        "STAGE0_Q1_LINEAGE_SHA256",
        ordinary.lineage_sha256,
    )
    monkeypatch.setattr(
        apprentice_module,
        "STAGE0_Q1_ACTION_COUNT",
        len(ordinary.actions),
    )
    monkeypatch.setattr(apprentice_module, "STAGE0_Q1_MILESTONE_ID", "power_on")
    with pytest.raises(ApprenticeDatasetError, match="not a named milestone promotion"):
        capture_apprentice_dataset(
            rom_path,
            ordinary.store.path,
            ordinary.target_id,
            ordinary.lineage_sha256,
            tmp_path / "ordinary-target",
        )
    assert not (tmp_path / "wrong-lineage").exists()
    assert not (tmp_path / "unverified").exists()
    assert not (tmp_path / "ordinary-target").exists()


def test_terminal_mismatch_publishes_nothing_and_leaves_source_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_source(tmp_path)
    _install_capture_fakes(monkeypatch, source, terminal_snapshot_matches=False)
    source_before = _source_hashes(source.store.path)
    rom_path = tmp_path / "private.gb"
    rom_path.write_bytes(b"placeholder")
    output = tmp_path / "failed-capture"

    with pytest.raises(ApprenticeDatasetError, match="snapshot_hash_mismatch"):
        capture_apprentice_dataset(
            rom_path,
            source.store.path,
            source.target_id,
            source.lineage_sha256,
            output,
        )

    assert not output.exists()
    assert _source_hashes(source.store.path) == source_before


def test_immutable_source_view_refuses_torn_event_tail_without_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_source(tmp_path)
    _install_capture_fakes(monkeypatch, source)
    event_path = source.store.path / "events.jsonl"
    with event_path.open("ab") as output:
        output.write(b'{"incomplete":')
    torn_payload = event_path.read_bytes()
    rom_path = tmp_path / "private.gb"
    rom_path.write_bytes(b"placeholder")

    with pytest.raises(ApprenticeDatasetError, match="immutable expedition source prefix"):
        capture_apprentice_dataset(
            rom_path,
            source.store.path,
            source.target_id,
            source.lineage_sha256,
            tmp_path / "torn-source",
        )

    assert event_path.read_bytes() == torn_payload
    assert not (source.store.path / "recovery").exists()
    assert not (tmp_path / "torn-source").exists()


def test_verifier_rejects_array_and_manifest_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_source(tmp_path)
    _install_capture_fakes(monkeypatch, source)
    rom_path = tmp_path / "private.gb"
    rom_path.write_bytes(b"placeholder")
    output = tmp_path / "tamper-dataset"
    capture_apprentice_dataset(
        rom_path,
        source.store.path,
        source.target_id,
        source.lineage_sha256,
        output,
    )

    actions_path = output / "actions.npy"
    original_actions = actions_path.read_bytes()
    tampered = bytearray(original_actions)
    tampered[-1] ^= 1
    actions_path.write_bytes(tampered)
    with pytest.raises(ApprenticeDatasetError, match="actions array hash"):
        verify_apprentice_dataset(output)

    actions_path.write_bytes(original_actions)
    manifest_path = output / "manifest.json"
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["action_count"] += 1
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ApprenticeDatasetError, match="manifest hash"):
        verify_apprentice_dataset(output)

    manifest_path.write_bytes(original_manifest)
    success_path = output / "SUCCESS"
    success = json.loads(success_path.read_text(encoding="utf-8"))
    success_path.write_text(
        "{"
        f'"dataset_sha256":"{success["dataset_sha256"]}",'
        f'"dataset_sha256":"{success["dataset_sha256"]}",'
        f'"manifest_sha256":"{success["manifest_sha256"]}",'
        '"schema_version":1}\n',
        encoding="utf-8",
    )
    with pytest.raises(ApprenticeDatasetError, match="duplicate JSON keys"):
        verify_apprentice_dataset(output)
