from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_ai.self_taught import (
    SELF_GENERATED_COMPOSITION_PROTOCOL,
    SELF_GENERATED_REPLAY_SHARD_PROTOCOL,
)
from pokemon_red_ai.student_training import (
    BalancedSkillReplay,
    SelfGeneratedSkillDataset,
    SequenceAwareStudentTrainer,
    SequenceTrainingConfig,
    load_self_generated_datasets,
    make_recurrent_sequences,
    train_recurrent_student,
)

PIXEL_SHAPE = (2, 4, 5)
TARGET_SHAPE = (1, 4, 5)
HISTORY_SHAPE = (6,)


def _write_dataset(
    path: Path,
    *,
    length: int,
    action: int = 0,
) -> Path:
    np.savez_compressed(
        path,
        pixels=np.zeros((length, *PIXEL_SHAPE), dtype=np.uint8),
        action_history=np.zeros((length, *HISTORY_SHAPE), dtype=np.float32),
        target_pixels=np.zeros(TARGET_SHAPE, dtype=np.uint8),
        actions=np.full(length, action, dtype=np.int64),
    )
    return path


def _write_composition_dataset(path: Path, *, offsets: tuple[int, ...]) -> Path:
    source_count = len(offsets) - 1
    targets = np.stack(
        [np.full(TARGET_SHAPE, goal + 1, dtype=np.uint8) for goal in range(source_count)]
    )
    full_actions = np.arange(offsets[-1], dtype=np.int64) % 4
    full_goals = np.concatenate(
        [
            np.full(stop - begin, goal, dtype=np.int64)
            for goal, (begin, stop) in enumerate(zip(offsets, offsets[1:], strict=False))
        ]
    )
    excerpt_ranges = [
        (
            max(offsets[index - 1], boundary - 5),
            min(offsets[index + 1], boundary + 2),
        )
        for index, boundary in enumerate(offsets[1:-1], start=1)
    ]
    excerpt_offsets = [0]
    switch_offsets: list[int] = []
    action_parts: list[np.ndarray] = []
    goal_parts: list[np.ndarray] = []
    for start, stop in excerpt_ranges:
        boundary = offsets[len(excerpt_offsets)]
        switch_offsets.append(excerpt_offsets[-1] + boundary - start)
        action_parts.append(full_actions[start:stop])
        goal_parts.append(full_goals[start:stop])
        excerpt_offsets.append(excerpt_offsets[-1] + stop - start)
    actions = np.concatenate(action_parts)
    goal_indices = np.concatenate(goal_parts)
    length = len(actions)
    histories = np.arange(length * int(np.prod(HISTORY_SHAPE)), dtype=np.float32).reshape(
        length, *HISTORY_SHAPE
    )
    episode_starts = np.zeros(length, dtype=np.bool_)
    episode_starts[np.asarray(excerpt_offsets[:-1], dtype=np.int64)] = True
    np.savez_compressed(
        path,
        pixels=np.zeros((length, *PIXEL_SHAPE), dtype=np.uint8),
        action_history=histories,
        target_pixels=targets,
        actions=actions,
        episode_starts=episode_starts,
        goal_indices=goal_indices,
        excerpt_offsets=np.asarray(excerpt_offsets, dtype=np.int64),
        dataset_kind=np.asarray("composition"),
        replay_protocol=np.asarray(SELF_GENERATED_COMPOSITION_PROTOCOL),
        successful_replays=np.asarray(1, dtype=np.int64),
        source_skill_ids=np.asarray([f"skill-{index}" for index in range(source_count)]),
        goal_switch_offsets=np.asarray(switch_offsets, dtype=np.int64),
    )
    return path


def test_dataset_loading_and_sequence_windows_preserve_burn_in_boundary(
    tmp_path: Path,
) -> None:
    dataset = SelfGeneratedSkillDataset.load(
        _write_dataset(tmp_path / "route-one.npz", length=11),
        skill_id="route-one",
    )

    windows = make_recurrent_sequences(
        dataset,
        burn_in=3,
        train_length=5,
        stride=2,
    )

    assert [(item.burn_start, item.train_start, item.train_stop) for item in windows] == [
        (0, 0, 5),
        (0, 2, 7),
        (1, 4, 9),
        (3, 6, 11),
        (5, 8, 11),
        (7, 10, 11),
    ]
    assert windows[2].burn_length == 3
    assert windows[2].train_examples == 5
    assert np.array_equal(dataset.weights, np.ones(11, dtype=np.float32))
    observations = dataset.observations(2, 7)
    assert observations["target_pixels"].shape == (5, *TARGET_SHAPE)


def test_balanced_replay_samples_skills_equally_despite_different_lengths(
    tmp_path: Path,
) -> None:
    datasets = load_self_generated_datasets(
        {
            "short": _write_dataset(tmp_path / "short.npz", length=3),
            "long": _write_dataset(tmp_path / "long.npz", length=30),
            "longest": _write_dataset(tmp_path / "longest.npz", length=60),
        }
    )
    replay = BalancedSkillReplay(
        datasets,
        SequenceTrainingConfig(burn_in=2, train_length=4, stride=2),
        seed=9,
    )

    counts = Counter(sequence.skill_id for sequence in replay.sample(31))

    assert max(counts.values()) - min(counts.values()) <= 1
    assert replay.window_counts() == {"short": 2, "long": 15, "longest": 30}

    new_skill = SelfGeneratedSkillDataset.load(
        _write_dataset(tmp_path / "new.npz", length=4),
        skill_id="new",
    )
    replay.register(new_skill)
    assert {sequence.skill_id for sequence in replay.sample(4)} == {
        "short",
        "long",
        "longest",
        "new",
    }


def test_composition_replay_declares_goal_switches_and_trains_across_them(
    tmp_path: Path,
) -> None:
    composition = SelfGeneratedSkillDataset.load(
        _write_composition_dataset(tmp_path / "power-on-chain.npz", offsets=(0, 5, 12)),
        skill_id="composition-12",
    )

    windows = make_recurrent_sequences(
        composition,
        burn_in=3,
        train_length=4,
        stride=4,
    )

    assert composition.dataset_kind == "composition"
    assert composition.source_skill_ids == ("skill-0", "skill-1")
    boundary = composition.goal_switch_offsets[0]
    boundary_windows = [
        window for window in windows if window.train_start < boundary < window.train_stop
    ]
    assert boundary_windows
    assert any(window.burn_start < window.train_start < boundary for window in boundary_windows)
    assert max(window.burn_length for window in boundary_windows) == 3
    observations = composition.observations(boundary - 1, boundary + 2)
    assert np.all(observations["target_pixels"][0] == 1)
    assert np.all(observations["target_pixels"][1:] == 2)
    assert np.array_equal(
        observations["action_history"],
        composition.action_history[boundary - 1 : boundary + 2],
    )


def test_composition_sampling_guarantees_deterministic_boundary_coverage(
    tmp_path: Path,
) -> None:
    composition = SelfGeneratedSkillDataset.load(
        _write_composition_dataset(
            tmp_path / "long-chain.npz",
            offsets=(0, 6, 18, 40, 80),
        ),
        skill_id="composition-long",
    )
    config = SequenceTrainingConfig(burn_in=4, train_length=8, stride=8)
    first = BalancedSkillReplay((composition,), config, seed=71)
    second = BalancedSkillReplay((composition,), config, seed=71)

    first_sample = first.sample(8)
    second_sample = second.sample(8)
    crossed = {boundary for sequence in first_sample for boundary in sequence.crossed_goal_switches}

    assert crossed == set(composition.goal_switch_offsets)
    assert [(item.burn_start, item.train_start, item.train_stop) for item in first_sample] == [
        (item.burn_start, item.train_start, item.train_stop) for item in second_sample
    ]
    assert sum(bool(item.crossed_goal_switches) for item in first_sample) >= 4


def test_weighted_composition_cycle_and_persisted_cursor_cover_rebuilt_rounds(
    tmp_path: Path,
) -> None:
    composition = SelfGeneratedSkillDataset.load(
        _write_composition_dataset(
            tmp_path / "weighted-chain.npz",
            offsets=(0, 6, 18, 40, 80),
        ),
        skill_id="composition-weighted",
    )
    locals_ = tuple(
        SelfGeneratedSkillDataset.load(
            _write_dataset(tmp_path / f"local-{index}.npz", length=8),
            skill_id=f"local-{index}",
        )
        for index in range(4)
    )
    config = SequenceTrainingConfig(burn_in=4, train_length=8, stride=8)
    cursor = 0
    crossed: set[int] = set()
    for round_index in range(2):
        replay = BalancedSkillReplay(
            (*locals_, composition),
            config,
            seed=900 + round_index,
            composition_boundary_cursor=cursor,
        )
        assert replay.sampling_cycle_size == 8
        sample = replay.sample(replay.sampling_cycle_size)
        assert sum(item.skill_id == composition.skill_id for item in sample) == 4
        crossed.update(boundary for item in sample for boundary in item.crossed_goal_switches)
        cursor = replay.next_composition_boundary_cursor

    assert crossed == set(composition.goal_switch_offsets)
    assert cursor >= len(composition.goal_switch_offsets)


def test_individual_replay_loading_has_a_deterministic_memory_bound(
    tmp_path: Path,
) -> None:
    path = _write_dataset(tmp_path / "large-skill.npz", length=10_000)
    first = SelfGeneratedSkillDataset.load(
        path,
        skill_id="large",
        max_examples=32,
        sample_seed=17,
    )
    second = SelfGeneratedSkillDataset.load(
        path,
        skill_id="large",
        max_examples=32,
        sample_seed=17,
    )

    assert len(first) == 32
    assert first.source_action_count == 10_000
    assert first.source_action_offset == second.source_action_offset
    assert first.retained_bytes < 10_000


def test_composition_replay_fails_closed_without_verified_provenance(
    tmp_path: Path,
) -> None:
    path = _write_composition_dataset(tmp_path / "unverified.npz", offsets=(0, 2, 4))
    with np.load(path, allow_pickle=False) as archive:
        payload = {name: np.asarray(archive[name]) for name in archive.files}
    payload["successful_replays"] = np.asarray(0, dtype=np.int64)
    np.savez_compressed(path, **payload)

    with pytest.raises(ValueError, match="no successful continuous replay"):
        SelfGeneratedSkillDataset.load(path)


def test_short_adjacent_skills_have_only_declared_in_excerpt_goal_switches(
    tmp_path: Path,
) -> None:
    dataset = SelfGeneratedSkillDataset.load(
        _write_composition_dataset(
            tmp_path / "short-adjacent.npz",
            offsets=(0, 2, 3, 5, 6),
        ),
        skill_id="short-adjacent",
    )
    excerpt_starts = set(dataset.excerpt_offsets[:-1])
    observed = {
        int(value)
        for value in np.flatnonzero(dataset.goal_indices[1:] != dataset.goal_indices[:-1]) + 1
        if int(value) not in excerpt_starts
    }

    assert observed == set(dataset.goal_switch_offsets)


def test_invalid_dataset_is_rejected_before_training(tmp_path: Path) -> None:
    path = tmp_path / "broken.npz"
    np.savez_compressed(
        path,
        pixels=np.zeros((3, *PIXEL_SHAPE), dtype=np.uint8),
        action_history=np.zeros((2, *HISTORY_SHAPE), dtype=np.float32),
        target_pixels=np.zeros(TARGET_SHAPE, dtype=np.uint8),
        actions=np.zeros(3, dtype=np.int64),
    )

    with pytest.raises(ValueError, match="Action histories"):
        SelfGeneratedSkillDataset.load(path)

    negative = tmp_path / "negative.npz"
    np.savez_compressed(
        negative,
        pixels=np.zeros((1, *PIXEL_SHAPE), dtype=np.uint8),
        action_history=np.zeros((1, *HISTORY_SHAPE), dtype=np.float32),
        target_pixels=np.zeros(TARGET_SHAPE, dtype=np.uint8),
        actions=np.asarray([-1], dtype=np.int64),
    )
    with pytest.raises(ValueError, match="cannot be negative"):
        SelfGeneratedSkillDataset.load(negative)

    invalid_weights = tmp_path / "invalid-weights.npz"
    np.savez_compressed(
        invalid_weights,
        pixels=np.zeros((2, *PIXEL_SHAPE), dtype=np.uint8),
        action_history=np.zeros((2, *HISTORY_SHAPE), dtype=np.float32),
        target_pixels=np.zeros(TARGET_SHAPE, dtype=np.uint8),
        actions=np.zeros(2, dtype=np.int64),
        weights=np.asarray([1.0, 0.0], dtype=np.float32),
    )
    with pytest.raises(ValueError, match="weights must be positive"):
        SelfGeneratedSkillDataset.load(invalid_weights)


def test_recurrent_student_uses_loss_free_burn_in_and_improves_action_nll(
    tmp_path: Path,
) -> None:
    gym = pytest.importorskip("gymnasium")
    torch = pytest.importorskip("torch")
    pytest.importorskip("sb3_contrib")
    from sb3_contrib import RecurrentPPO
    from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
    from stable_baselines3.common.vec_env import DummyVecEnv

    class TinyExtractor(BaseFeaturesExtractor):
        def __init__(self, observation_space: gym.spaces.Dict) -> None:
            super().__init__(observation_space, features_dim=16)
            self.project = torch.nn.Linear(9, 16)

        def forward(self, observations):  # type: ignore[no-untyped-def]
            pixels = observations["pixels"].mean(dim=(2, 3))
            target = observations["target_pixels"].mean(dim=(2, 3))
            combined = torch.cat((pixels, observations["action_history"], target), dim=1)
            return torch.tanh(self.project(combined))

    class TinySkillEnv(gym.Env):
        def __init__(self) -> None:
            self.action_space = gym.spaces.Discrete(4)
            self.observation_space = gym.spaces.Dict(
                {
                    "pixels": gym.spaces.Box(
                        0,
                        255,
                        shape=PIXEL_SHAPE,
                        dtype=np.uint8,
                    ),
                    "action_history": gym.spaces.Box(
                        0,
                        1,
                        shape=HISTORY_SHAPE,
                        dtype=np.float32,
                    ),
                    "target_pixels": gym.spaces.Box(
                        0,
                        255,
                        shape=TARGET_SHAPE,
                        dtype=np.uint8,
                    ),
                }
            )

        def observation(self) -> dict[str, np.ndarray]:
            return {
                "pixels": np.zeros(PIXEL_SHAPE, dtype=np.uint8),
                "action_history": np.zeros(HISTORY_SHAPE, dtype=np.float32),
                "target_pixels": np.zeros(TARGET_SHAPE, dtype=np.uint8),
            }

        def reset(self, *, seed=None, options=None):  # type: ignore[no-untyped-def]
            super().reset(seed=seed)
            return self.observation(), {}

        def step(self, action):  # type: ignore[no-untyped-def]
            return self.observation(), 0.0, False, False, {}

    vector = DummyVecEnv([TinySkillEnv])
    model = RecurrentPPO(
        "MultiInputLstmPolicy",
        vector,
        n_steps=4,
        batch_size=4,
        n_epochs=1,
        policy_kwargs={
            "features_extractor_class": TinyExtractor,
            "net_arch": [],
            "lstm_hidden_size": 16,
        },
        device="cpu",
        seed=4,
    )
    path = _write_dataset(tmp_path / "choose-starter.npz", length=12, action=3)
    datasets = load_self_generated_datasets({"choose-starter": path})
    config = SequenceTrainingConfig(
        burn_in=3,
        train_length=4,
        stride=2,
        learning_rate=3e-3,
        diagnostic_chunk_length=5,
    )
    trainer = SequenceAwareStudentTrainer(model, config)
    assert trainer.optimizer is not model.policy.optimizer
    before = trainer.diagnose(datasets)["choose-starter"]
    sequence = make_recurrent_sequences(
        datasets[0],
        burn_in=3,
        train_length=4,
        stride=2,
    )[2]

    single = trainer.train_sequence(sequence)
    assert single.train_examples == 4
    assert single.burn_in_examples == 3
    report = trainer.train(
        BalancedSkillReplay(datasets, config, seed=4),
        updates=30,
    )
    after = trainer.diagnose(datasets)["choose-starter"]

    assert report.updates == 30
    assert report.per_skill["choose-starter"].examples == report.train_examples
    assert np.isfinite(report.per_skill["choose-starter"].policy_entropy)
    assert after.action_nll < before.action_nll
    assert after.action_accuracy >= before.action_accuracy
    assert after.demonstration_entropy == pytest.approx(0.0)

    _trainer, convenience = train_recurrent_student(
        model,
        {"choose-starter": path},
        updates=1,
        config=config,
        seed=5,
    )
    assert convenience.updates == 1

    # A later admission shard replays its predecessor overlap into recurrent
    # state, but diagnostics and supervised losses count only its owned range.
    shard_path = tmp_path / "context-shard.npz"
    np.savez_compressed(
        shard_path,
        pixels=np.zeros((6, *PIXEL_SHAPE), dtype=np.uint8),
        action_history=np.zeros((6, *HISTORY_SHAPE), dtype=np.float32),
        target_pixels=np.zeros(TARGET_SHAPE, dtype=np.uint8),
        actions=np.full(6, 3, dtype=np.int64),
        weights=np.ones(6, dtype=np.float32),
        episode_starts=np.asarray([True, False, False, False, False, False]),
        replay_shard_protocol=np.asarray(SELF_GENERATED_REPLAY_SHARD_PROTOCOL),
        source_dataset_sha256=np.asarray("a" * 64),
        source_skill_id=np.asarray("context-shard"),
        source_action_count=np.asarray(8, dtype=np.int64),
        source_action_offset=np.asarray(2, dtype=np.int64),
        source_context_start=np.asarray(2, dtype=np.int64),
        source_train_start=np.asarray(4, dtype=np.int64),
        source_train_stop=np.asarray(8, dtype=np.int64),
        replay_train_offset=np.asarray(2, dtype=np.int64),
        replay_shard_index=np.asarray(1, dtype=np.int64),
        replay_shard_count=np.asarray(2, dtype=np.int64),
    )
    context_shard = SelfGeneratedSkillDataset.load(
        shard_path,
        skill_id="context-shard",
    )
    context_windows = make_recurrent_sequences(
        context_shard,
        burn_in=3,
        train_length=4,
        stride=2,
    )
    context_diagnostics = trainer.diagnose((context_shard,))["context-shard"]
    assert context_windows[0].burn_start == 0
    assert context_windows[0].train_start == 2
    assert context_diagnostics.examples == 4
    vector.close()
