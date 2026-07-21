from __future__ import annotations

# The collector lives with the optional recurrent-PPO implementation.
# ruff: noqa: E402
import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("gymnasium")
pytest.importorskip("stable_baselines3")
pytest.importorskip("sb3_contrib")
pytest.importorskip("torch")

from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    FrozenSnapshot,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import MilestoneProgress, milestone_progress_for_state
from pokemon_red_ai.ppo_training import (
    PPO_V8_PROTOCOL,
    CompositionReplayRejected,
    _atomic_gzip_json,
    _atomic_json,
    _collect_v8_composition_dataset,
    _collect_v8_student_dataset,
    _composition_state_signature,
    _distillation_state_signature,
    _execute_action,
    _sha256_file,
    _validate_curriculum_state,
)
from pokemon_red_ai.rom import ROM_ENVIRONMENT_VARIABLE, verify_rom
from pokemon_red_ai.state import PokemonRedStateReader

# A self-generated power-on lineage from the project's stable curriculum. The first
# 230 actions reach ``game_started`` and the remaining 59 reach ``left_bedroom``.
# Keeping the trace here makes the real-ROM regression require no private run artifact.
_TWO_SKILL_LINEAGE = bytes.fromhex(
    "030301070205000600020501010004040000030307060006030105060002070206000007"
    "060006070303040703010302010101000605010505010100040402070206010407070400"
    "010704050304070307050706010706070607070102050203070101060500010000070305"
    "030004060506000501050003030101040006060007040707040401040001040006050400"
    "050500070603010306010105000705020306010500030303000000050303030101040701"
    "070703040004010607010002050205030003040505000202060304070604000506060401"
    "040404070107040404040404040506060604030300020006050001010304050205030406"
    "05030404010105030400030500000703000103030604060700050001060500040706050000"
)
_FIRST_SKILL_ACTIONS = 230


def _entry_payload(
    entry_id: str,
    snapshot: FrozenSnapshot,
    progress: MilestoneProgress,
    lineage: list[int],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "entry_id": entry_id,
        "source_cell_id": None,
        "progress": progress.public_dict(),
        "snapshot": snapshot.checkpoint_dict(),
        "lineage_actions": [
            BlindAction(
                BLIND_ACTIONS[action], ACTION_HOLD_FRAMES, ACTION_RELEASE_FRAMES
            ).public_dict()
            for action in lineage
        ],
    }


def _write_curriculum_entry(
    curriculum: Path,
    payload: dict[str, object],
    *,
    progress: MilestoneProgress,
) -> dict[str, object]:
    entry_id = str(payload["entry_id"])
    relative = Path("entries") / f"{entry_id}.json.gz"
    path = curriculum / relative
    _atomic_gzip_json(path, payload)
    return {
        "entry_id": entry_id,
        "file": relative.as_posix(),
        "file_sha256": _sha256_file(path),
        "milestone_id": progress.key,
        "milestone_index": progress.index,
        "milestone_label": progress.label,
        "map_id": None,
        "depth_actions": len(payload["lineage_actions"]),
        "source": "real_rom_composition_test",
    }


@pytest.mark.integration
def test_real_rom_multi_skill_composition_accepts_exact_chain_and_rejects_wrong_endpoint(
    tmp_path: Path,
) -> None:
    raw_path = os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        pytest.skip(f"Set {ROM_ENVIRONMENT_VARIABLE} to run ROM integration tests")
    rom_path = Path(raw_path).expanduser().resolve()
    verify_rom(rom_path)

    full_actions = list(_TWO_SKILL_LINEAGE)
    first_actions = full_actions[:_FIRST_SKILL_ACTIONS]
    second_actions = full_actions[_FIRST_SKILL_ACTIONS:]
    curriculum = tmp_path / "curriculum"
    (curriculum / "entries").mkdir(parents=True)

    with PokemonRedEmulator(rom_path) as emulator:
        reader = PokemonRedStateReader(emulator)
        root_snapshot = FrozenSnapshot.freeze(emulator.save_state())
        root_progress = milestone_progress_for_state(reader.read())
        for action in first_actions:
            assert _execute_action(emulator, action)
        started_snapshot = FrozenSnapshot.freeze(emulator.save_state())
        started_progress = milestone_progress_for_state(reader.read())
        for action in second_actions:
            assert _execute_action(emulator, action)
        bedroom_snapshot = FrozenSnapshot.freeze(emulator.save_state())
        bedroom_progress = milestone_progress_for_state(reader.read())

    assert (root_progress.key, started_progress.key, bedroom_progress.key) == (
        "power_on",
        "game_started",
        "left_bedroom",
    )
    payloads = {
        "power-on": _entry_payload("power-on", root_snapshot, root_progress, []),
        "game-started": _entry_payload(
            "game-started", started_snapshot, started_progress, first_actions
        ),
        "left-bedroom": _entry_payload(
            "left-bedroom", bedroom_snapshot, bedroom_progress, full_actions
        ),
    }
    entries = [
        _write_curriculum_entry(
            curriculum,
            payloads[entry_id],
            progress=progress,
        )
        for entry_id, progress in (
            ("power-on", root_progress),
            ("game-started", started_progress),
            ("left-bedroom", bedroom_progress),
        )
    ]
    manifest = {
        "schema_version": 1,
        "protocol": PPO_V8_PROTOCOL,
        "source_run": "real-rom-composition-test",
        "entries": entries,
        "best_milestone": bedroom_progress.public_dict(),
        "verified_promotions": 2,
    }
    _atomic_json(curriculum / "manifest.json", manifest)
    _validate_curriculum_state(curriculum, manifest, expected_protocol=PPO_V8_PROTOCOL)

    first_dataset, first_goal = _collect_v8_student_dataset(
        rom_path,
        root_snapshot,
        first_actions,
        compressed_to_original=tuple(range(len(first_actions))),
    )
    second_dataset, second_goal = _collect_v8_student_dataset(
        rom_path,
        started_snapshot,
        second_actions,
        compressed_to_original=tuple(range(len(second_actions))),
    )
    chain = [
        {
            "skill_id": "power-on-to-started",
            "source_entry_id": "power-on",
            "target_entry_id": "game-started",
            "target_index": started_progress.index,
            "action_count": len(first_actions),
            "dataset_sha256": "a" * 64,
            "distillation_audit_sha256": "b" * 64,
        },
        {
            "skill_id": "started-to-bedroom",
            "source_entry_id": "game-started",
            "target_entry_id": "left-bedroom",
            "target_index": bedroom_progress.index,
            "action_count": len(second_actions),
            "dataset_sha256": "c" * 64,
            "distillation_audit_sha256": "d" * 64,
        },
    ]
    sources = {
        "power-on-to-started": (first_dataset["actions"], first_goal),
        "started-to-bedroom": (second_dataset["actions"], second_goal),
    }

    dataset, boundaries = _collect_v8_composition_dataset(
        rom_path,
        curriculum,
        chain,
        sources,
        burn_in=8,
        train_length=32,
    )

    assert [boundary["observed_index"] for boundary in boundaries] == [1, 2]
    assert int(dataset["full_action_count"]) == len(full_actions)
    assert dataset["goal_switch_offsets"].tolist() == [24]

    # Keep the artifact structurally valid but bind the second milestone to the
    # first milestone's snapshot. Exact semantic endpoint verification must fail.
    payloads["left-bedroom"]["snapshot"] = started_snapshot.checkpoint_dict()
    final_path = curriculum / "entries" / "left-bedroom.json.gz"
    _atomic_gzip_json(final_path, payloads["left-bedroom"])
    entries[-1]["file_sha256"] = _sha256_file(final_path)
    _atomic_json(curriculum / "manifest.json", manifest)

    with pytest.raises(CompositionReplayRejected, match="protected target state"):
        _collect_v8_composition_dataset(
            rom_path,
            curriculum,
            chain,
            sources,
            burn_in=8,
            train_length=32,
        )


@pytest.mark.integration
def test_real_rom_composition_ignores_only_the_save_load_volatile_game_area_hash(
    tmp_path: Path,
) -> None:
    """Regress the exact PyBoy endpoint mismatch that blocked every composition."""

    raw_path = os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        pytest.skip(f"Set {ROM_ENVIRONMENT_VARIABLE} to run ROM integration tests")
    rom_path = Path(raw_path).expanduser().resolve()
    verify_rom(rom_path)
    noop = BLIND_ACTIONS.index("noop")
    progress = MilestoneProgress("power_on", 0, "Power-on")

    snapshots: list[FrozenSnapshot] = []
    with PokemonRedEmulator(rom_path) as emulator:
        reader = PokemonRedStateReader(emulator)
        snapshots.append(FrozenSnapshot.freeze(emulator.save_state()))
        for index in range(4):
            assert _execute_action(emulator, noop)
            snapshots.append(FrozenSnapshot.freeze(emulator.save_state()))
            if index == 0:
                live_state = reader.read()
                live_progress = milestone_progress_for_state(live_state, inherited=progress)
                live_strict = _distillation_state_signature(emulator, live_state, live_progress)
                live_composable = _composition_state_signature(emulator, live_state, live_progress)

    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(snapshots[1].thaw())
        loaded_state = PokemonRedStateReader(emulator).read()
        loaded_progress = milestone_progress_for_state(loaded_state, inherited=progress)
        loaded_strict = _distillation_state_signature(emulator, loaded_state, loaded_progress)
        loaded_composable = _composition_state_signature(emulator, loaded_state, loaded_progress)

    # The complete emulator game-area hash is the sole unstable element. The
    # processed visual and every enumerated gameplay RAM field are still exact.
    assert [
        index
        for index, (live, loaded) in enumerate(zip(live_strict, loaded_strict, strict=True))
        if live != loaded
    ] == [26]
    assert live_composable == loaded_composable

    curriculum = tmp_path / "volatile-hash-curriculum"
    (curriculum / "entries").mkdir(parents=True)
    entry_ids = ["root", "edge-1", "edge-2", "edge-3", "edge-4"]
    payloads = {
        entry_id: _entry_payload(
            entry_id,
            snapshot,
            progress,
            [noop] * index,
        )
        for index, (entry_id, snapshot) in enumerate(zip(entry_ids, snapshots, strict=True))
    }
    entries = [
        _write_curriculum_entry(curriculum, payloads[entry_id], progress=progress)
        for entry_id in entry_ids
    ]
    manifest = {
        "schema_version": 1,
        "protocol": PPO_V8_PROTOCOL,
        "source_run": "real-rom-volatile-hash-test",
        "entries": entries,
        "best_milestone": progress.public_dict(),
        "verified_promotions": 0,
    }
    _atomic_json(curriculum / "manifest.json", manifest)
    chain = [
        {
            "skill_id": f"skill-{index}",
            "source_entry_id": entry_ids[index],
            "target_entry_id": entry_ids[index + 1],
            "target_index": 0,
            "action_count": 1,
            "dataset_sha256": f"{index + 1:x}" * 64,
            "distillation_audit_sha256": f"{index + 5:x}" * 64,
        }
        for index in range(4)
    ]
    goal = np.zeros((3, 72, 80), dtype=np.uint8)
    sources = {
        str(skill["skill_id"]): (np.asarray([noop], dtype=np.int64), goal) for skill in chain
    }

    dataset, boundaries = _collect_v8_composition_dataset(
        rom_path,
        curriculum,
        chain,
        sources,
        burn_in=32,
        train_length=64,
    )

    assert len(boundaries) == 4
    assert len(dataset["actions"]) == 6
    assert dataset["excerpt_offsets"].tolist() == [0, 2, 4, 6]
    assert dataset["goal_switch_offsets"].tolist() == [1, 3, 5]

    # A validly encoded but wrong final target must still fail closed.
    payloads["edge-4"]["snapshot"] = snapshots[1].checkpoint_dict()
    final_path = curriculum / "entries" / "edge-4.json.gz"
    _atomic_gzip_json(final_path, payloads["edge-4"])
    entries[-1]["file_sha256"] = _sha256_file(final_path)
    _atomic_json(curriculum / "manifest.json", manifest)
    with pytest.raises(CompositionReplayRejected, match="protected target state"):
        _collect_v8_composition_dataset(
            rom_path,
            curriculum,
            chain,
            sources,
            burn_in=32,
            train_length=64,
        )
