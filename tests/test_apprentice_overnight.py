from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

from pokemon_red_ai.apprentice_data import ApprenticeDataset
from pokemon_red_ai.apprentice_overnight import (
    DEFAULT_RUNG_HORIZONS,
    OvernightApprenticeConfig,
    OvernightApprenticeRunner,
    PromotionGate,
    _RunState,
    build_curriculum_rungs,
    build_suffix_arrays,
)


def test_default_gate_requires_27_of_30_twice() -> None:
    config = OvernightApprenticeConfig()
    assert config.max_seconds == 8 * 60 * 60
    assert config.max_emulator_actions == 15_000_000
    assert config.max_actions_without_promotion == 2_000_000
    assert config.max_rss_mib == 1_536
    assert config.minimum_free_gib == 50
    assert config.checkpoint_interval_episodes == 10
    assert config.promotion_window == 30
    assert config.promotion_required == 27
    assert config.promotion_confirmations == 2

    gate = PromotionGate(30, 27, 2)
    first_results = [True] * 27 + [False] * 3
    for result in first_results[:-1]:
        promoted, evidence = gate.record(result)
        assert not promoted
        assert evidence is None
    promoted, evidence = gate.record(first_results[-1])
    assert not promoted
    assert evidence == {
        "window": 1,
        "attempts": 30,
        "successes": 27,
        "required_successes": 27,
        "passed": True,
        "consecutive_confirmations": 1,
    }

    for result in first_results[:-1]:
        promoted, evidence = gate.record(result)
        assert not promoted
        assert evidence is None
    promoted, evidence = gate.record(first_results[-1])
    assert promoted
    assert evidence is not None
    assert evidence["consecutive_confirmations"] == 2


def test_failed_window_resets_promotion_confirmation() -> None:
    gate = PromotionGate(3, 2, 2)
    for result in (True, True, False):
        promoted, _ = gate.record(result)
    assert not promoted
    assert gate.consecutive_confirmations == 1

    for result in (True, False, False):
        promoted, _ = gate.record(result)
    assert not promoted
    assert gate.consecutive_confirmations == 0

    restored = PromotionGate.from_dict(gate.public_dict())
    assert restored.public_dict() == gate.public_dict()


def test_curriculum_is_nearest_goal_first_and_bounded() -> None:
    config = OvernightApprenticeConfig()
    rungs = build_curriculum_rungs(419, config)
    assert tuple(rung.remaining_actions for rung in rungs) == DEFAULT_RUNG_HORIZONS
    assert tuple(rung.start_action for rung in rungs) == (411, 403, 387, 355, 291, 163, 0)
    assert all(rung.rollout_limit >= rung.remaining_actions for rung in rungs)
    assert rungs[0].rollout_limit == 32
    with pytest.raises(ValueError, match="Dataset length"):
        build_curriculum_rungs(418, config)


def test_suffix_restarts_visual_and_action_history() -> None:
    action_count = 6
    frames = np.arange((action_count + 1) * 2 * 3, dtype=np.uint8).reshape(
        action_count + 1, 2, 3
    )
    actions = np.asarray([0, 1, 2, 3, 4, 5], dtype=np.uint8)
    previous = np.asarray([-1, 0, 1, 2, 3, 4], dtype=np.int16)
    starts = np.asarray([True, False, False, False, False, False], dtype=np.bool_)
    dataset = ApprenticeDataset(
        frames,
        actions,
        previous,
        starts,
        MappingProxyType({"dataset_sha256": "d" * 64}),
    )

    pairs, suffix_previous, targets = build_suffix_arrays(dataset, 3)

    assert pairs.shape == (3, 2, 2, 3)
    assert np.array_equal(pairs[0, 0], frames[3])
    assert np.array_equal(pairs[0, 1], frames[3])
    assert np.array_equal(pairs[1, 0], frames[3])
    assert np.array_equal(pairs[1, 1], frames[4])
    assert suffix_previous.tolist() == [-1, 3, 4]
    assert targets.tolist() == [3, 4, 5]


def test_canary_is_short_and_explicitly_relaxed() -> None:
    canary = OvernightApprenticeConfig.canary(dashboard_port=8771)
    assert canary.max_seconds == 180
    assert canary.demo_bootstrap_updates == 2
    assert (canary.promotion_required, canary.promotion_window) == (2, 3)
    assert canary.promotion_confirmations == 1
    assert canary.checkpoint_interval_episodes == 1
    assert canary.dashboard_port == 8771
    assert canary.public_dict()["rung_horizons"] == list(DEFAULT_RUNG_HORIZONS)


def test_checkpoint_round_trip_and_hash_refusal(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    output = tmp_path / "run"
    output.mkdir()
    runner = OvernightApprenticeRunner(
        tmp_path / "rom.gb",
        tmp_path / "dataset",
        tmp_path / "model",
        output,
        config=OvernightApprenticeConfig.canary(),
    )
    runner.model = torch.nn.Linear(2, 2)
    runner.optimizer = torch.optim.Adam(runner.model.parameters(), lr=1e-3)
    runner.state = _RunState(
        created_epoch=123.0,
        rung_index=2,
        episodes=11,
        successes=7,
        updates=5,
        demo_updates=3,
        self_imitation_updates=2,
        emulator_actions=321,
        checkpoint_replay_actions=20,
        evaluation_actions=12,
        actions_at_last_promotion=250,
        bootstrapped_rungs=[0, 1],
        gate=PromotionGate(3, 2, 1, current=[True]),
    )
    expected = {
        key: value.detach().clone() for key, value in runner.model.state_dict().items()
    }

    runner._save_checkpoint()
    receipt = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
    assert receipt["episode"] == 11
    with torch.no_grad():
        for parameter in runner.model.parameters():
            parameter.add_(10)
    runner.state.episodes = 99

    runner._load_checkpoint()
    assert runner.state.episodes == 11
    assert runner.state.demo_updates == 3
    assert runner.state.self_imitation_updates == 2
    assert runner.state.actions_at_last_promotion == 250
    assert runner.state.gate is not None
    assert runner.state.gate.current == [True]
    for key, value in runner.model.state_dict().items():
        assert torch.equal(value, expected[key])

    checkpoint = output / "checkpoint.pt"
    checkpoint.write_bytes(checkpoint.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="receipt"):
        runner._load_checkpoint()
