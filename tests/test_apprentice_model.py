from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_ai.apprentice_model import (
    APPRENTICE_ARCHITECTURE,
    EXPECTED_PARAMETER_COUNT,
    ApprenticeModelConfig,
)
from pokemon_red_ai.apprentice_stage0 import Stage0TrainingConfig, build_frame_pairs


def test_frozen_model_and_training_configuration() -> None:
    model = ApprenticeModelConfig()
    assert model.public_dict()["architecture"] == APPRENTICE_ARCHITECTURE
    assert len(model.sha256) == 64
    assert Stage0TrainingConfig().torch_threads <= 4
    with pytest.raises(ValueError, match="architecture is frozen"):
        ApprenticeModelConfig(recurrent_units=256)
    with pytest.raises(ValueError, match="between one and four"):
        Stage0TrainingConfig(torch_threads=5)


def test_frame_pair_alignment_duplicates_only_the_initial_frame() -> None:
    frames = np.stack(
        [np.full((72, 80), value, dtype=np.uint8) for value in range(4)]
    )
    dataset = SimpleNamespace(
        frames=frames,
        actions=np.asarray([1, 2, 3], dtype=np.uint8),
    )
    pairs = build_frame_pairs(dataset)
    assert pairs.shape == (3, 2, 72, 80)
    assert pairs.dtype == np.uint8
    assert np.all(pairs[0, 0] == 0)
    assert np.all(pairs[0, 1] == 0)
    assert np.all(pairs[1, 0] == 0)
    assert np.all(pairs[1, 1] == 1)
    assert np.all(pairs[2, 0] == 1)
    assert np.all(pairs[2, 1] == 2)


def test_cnn_lstm_shape_parameter_count_and_reset_determinism() -> None:
    torch = pytest.importorskip("torch")
    from pokemon_red_ai.apprentice_model import build_apprentice_policy

    torch.manual_seed(123)
    model = build_apprentice_policy()
    assert sum(parameter.numel() for parameter in model.parameters()) == EXPECTED_PARAMETER_COUNT
    frames = (
        torch.arange(3 * 2 * 72 * 80, dtype=torch.int64)
        .remainder(256)
        .to(torch.uint8)
        .reshape(1, 3, 2, 72, 80)
    )
    previous = torch.tensor([[-1, 0, 3]], dtype=torch.long)
    first, first_state = model(frames, previous)
    second, second_state = model(frames, previous)
    assert first.shape == (1, 3, 8)
    assert torch.equal(first, second)
    assert torch.equal(first_state[0], second_state[0])
    assert torch.equal(first_state[1], second_state[1])

    step_logits, step_state = model.step(frames[:, 0], previous[:, 0])
    assert step_logits.shape == (1, 8)
    assert step_state[0].shape == (1, 1, 128)


def test_model_rejects_malformed_observation_shapes() -> None:
    torch = pytest.importorskip("torch")
    from pokemon_red_ai.apprentice_model import build_apprentice_policy

    model = build_apprentice_policy()
    with pytest.raises(ValueError, match="frame_pairs"):
        model(torch.zeros(1, 2, 72, 80), torch.zeros(1, 2, dtype=torch.long))
    with pytest.raises(ValueError, match="previous_actions"):
        model(torch.zeros(1, 2, 2, 72, 80), torch.zeros(1, 3, dtype=torch.long))
