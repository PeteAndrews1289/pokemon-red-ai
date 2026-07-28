from __future__ import annotations

import numpy as np
import pytest

from pokemon_red_ai.hindsight import HindsightConfig, extract_hindsight_lessons


def rollout(steps: int = 24, environments: int = 2) -> tuple[np.ndarray, ...]:
    pixels = np.zeros((steps, environments, 2, 72, 80), dtype=np.uint8)
    histories = np.zeros((steps, environments, 21), dtype=np.float32)
    actions = np.zeros((steps, environments, 1), dtype=np.int64)
    starts = np.zeros((steps, environments), dtype=np.bool_)
    starts[0] = True
    for step in range(steps):
        pixels[step, :, 1, :, : step + 1] = 255
    pixels[:, :, 0] = np.concatenate((pixels[:1, :, 1], pixels[:-1, :, 1]), axis=0)
    return pixels, histories, actions, starts


def test_hindsight_relabels_only_real_future_states() -> None:
    pixels, histories, actions, starts = rollout()
    lessons = extract_hindsight_lessons(
        pixels,
        histories,
        actions,
        starts,
        HindsightConfig(max_lessons=4, min_actions=4, max_actions=12),
    )

    assert len(lessons) == 4
    assert {lesson.environment_rank for lesson in lessons} == {0, 1}
    for lesson in lessons:
        assert lesson.target_step > lesson.start_step
        assert lesson.action_count == lesson.target_step - lesson.start_step
        assert np.array_equal(
            lesson.target_pixels,
            pixels[lesson.target_step, lesson.environment_rank, 1:2],
        )
        assert lesson.dataset()["hindsight_protocol"].item().endswith("-v1")


def test_hindsight_never_crosses_episode_boundaries() -> None:
    pixels, histories, actions, starts = rollout(steps=28, environments=1)
    starts[12, 0] = True
    lessons = extract_hindsight_lessons(
        pixels,
        histories,
        actions,
        starts,
        HindsightConfig(max_lessons=20, min_actions=3, max_actions=10),
    )

    assert lessons
    assert all(
        lesson.target_step <= 11 or lesson.start_step >= 12
        for lesson in lessons
    )


def test_hindsight_rejects_static_rollouts() -> None:
    pixels, histories, actions, starts = rollout()
    pixels[:] = 0
    lessons = extract_hindsight_lessons(
        pixels,
        histories,
        actions,
        starts,
        HindsightConfig(max_lessons=4, min_actions=4, max_actions=12),
    )
    assert lessons == []


def test_hindsight_configuration_and_shapes_fail_closed() -> None:
    with pytest.raises(ValueError, match="horizons"):
        HindsightConfig(min_actions=9, max_actions=8)
    pixels, histories, actions, starts = rollout()
    with pytest.raises(ValueError, match="pixels"):
        extract_hindsight_lessons(
            pixels[:, :, :, :10, :10],
            histories,
            actions,
            starts,
            HindsightConfig(),
        )
