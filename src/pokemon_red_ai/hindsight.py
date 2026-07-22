from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

HINDSIGHT_PROTOCOL = "self-generated-visual-hindsight-v1"


@dataclass(frozen=True, slots=True)
class HindsightConfig:
    """Bounded, pixels-only relabeling settings for one PPO rollout."""

    max_lessons: int = 16
    min_actions: int = 8
    max_actions: int = 128
    min_changed_fraction: float = 0.03
    min_mean_absolute_error: float = 3.0

    def __post_init__(self) -> None:
        if self.max_lessons < 1:
            raise ValueError("Hindsight requires at least one lesson")
        if self.min_actions < 1 or self.max_actions < self.min_actions:
            raise ValueError("Hindsight action horizons are invalid")
        if not 0 <= self.min_changed_fraction <= 1:
            raise ValueError("Hindsight changed-pixel threshold is invalid")
        if self.min_mean_absolute_error < 0:
            raise ValueError("Hindsight visual-error threshold is invalid")


@dataclass(frozen=True, slots=True)
class HindsightLesson:
    """One action excerpt relabeled with a future frame the same policy reached."""

    environment_rank: int
    start_step: int
    target_step: int
    pixels: np.ndarray
    action_history: np.ndarray
    target_pixels: np.ndarray
    actions: np.ndarray
    changed_fraction: float
    mean_absolute_error: float

    @property
    def action_count(self) -> int:
        return int(len(self.actions))

    @property
    def target_sha256(self) -> str:
        return hashlib.sha256(self.target_pixels.tobytes()).hexdigest()

    def dataset(self) -> dict[str, np.ndarray]:
        return {
            "pixels": self.pixels,
            "action_history": self.action_history,
            "target_pixels": self.target_pixels,
            "actions": self.actions,
            "hindsight_protocol": np.asarray(HINDSIGHT_PROTOCOL),
            "environment_rank": np.asarray(self.environment_rank, dtype=np.int64),
            "start_step": np.asarray(self.start_step, dtype=np.int64),
            "target_step": np.asarray(self.target_step, dtype=np.int64),
        }

    def public_dict(self) -> dict[str, Any]:
        return {
            "protocol": HINDSIGHT_PROTOCOL,
            "environment_rank": self.environment_rank,
            "start_step": self.start_step,
            "target_step": self.target_step,
            "action_count": self.action_count,
            "changed_fraction": self.changed_fraction,
            "mean_absolute_error": self.mean_absolute_error,
            "target_sha256": self.target_sha256,
        }


def _segments(starts: np.ndarray) -> list[tuple[int, int]]:
    boundaries = [0]
    boundaries.extend(int(index) for index in np.flatnonzero(starts[1:]) + 1)
    boundaries.append(len(starts))
    return [
        (begin, end)
        for begin, end in zip(boundaries, boundaries[1:], strict=False)
        if end > begin
    ]


def _candidate_endpoints(begin: int, end: int, minimum: int) -> tuple[int, ...]:
    available = end - begin
    if available <= minimum:
        return ()
    first = begin + minimum
    last = end - 1
    if first >= last:
        return (last,)
    values = np.linspace(first, last, num=min(4, last - first + 1), dtype=int)
    return tuple(sorted(set(int(value) for value in values)))


def extract_hindsight_lessons(
    pixels: np.ndarray,
    action_history: np.ndarray,
    actions: np.ndarray,
    episode_starts: np.ndarray,
    config: HindsightConfig,
) -> list[HindsightLesson]:
    """Relabel on-policy excerpts with future visual states, never crossing an episode reset.

    ``pixels[t, env]`` is the observation before ``actions[t, env]``. Therefore the actions in
    ``[start, target)`` genuinely lead to the future frame observed at ``target``. Candidate
    excerpts are admitted only when their endpoints differ visibly, which prevents static title
    screens and repeated no-ops from becoming most of the auxiliary training set.
    """

    observed = np.asarray(pixels)
    histories = np.asarray(action_history)
    selected_actions = np.asarray(actions)
    starts = np.asarray(episode_starts, dtype=np.bool_)
    if observed.ndim != 5 or observed.shape[2:] != (2, 72, 80):
        raise ValueError("Hindsight pixels must have rollout × environment × 2 × 72 × 80 shape")
    steps, environments = observed.shape[:2]
    if histories.shape[:2] != (steps, environments):
        raise ValueError("Hindsight action histories do not match pixels")
    if selected_actions.shape[:2] != (steps, environments):
        raise ValueError("Hindsight actions do not match pixels")
    if starts.shape != (steps, environments):
        raise ValueError("Hindsight episode starts do not match pixels")

    flat_actions = selected_actions.reshape(steps, environments, -1)
    if flat_actions.shape[2] != 1:
        raise ValueError("Hindsight requires one discrete action per rollout step")

    candidates: list[HindsightLesson] = []
    horizon_values = sorted(
        {
            config.min_actions,
            min(config.max_actions, config.min_actions * 2),
            min(config.max_actions, config.min_actions * 4),
            config.max_actions,
        }
    )
    for environment_rank in range(environments):
        for segment_begin, segment_end in _segments(starts[:, environment_rank]):
            for target_step in _candidate_endpoints(
                segment_begin,
                segment_end,
                config.min_actions,
            ):
                for horizon in horizon_values:
                    start_step = max(segment_begin, target_step - horizon)
                    if target_step - start_step < config.min_actions:
                        continue
                    initial = observed[start_step, environment_rank, 1].astype(np.int16)
                    target = observed[target_step, environment_rank, 1].astype(np.int16)
                    absolute = np.abs(target - initial)
                    changed_fraction = float(np.count_nonzero(absolute >= 8) / absolute.size)
                    mean_absolute_error = float(absolute.mean())
                    if (
                        changed_fraction < config.min_changed_fraction
                        and mean_absolute_error < config.min_mean_absolute_error
                    ):
                        continue
                    candidates.append(
                        HindsightLesson(
                            environment_rank=environment_rank,
                            start_step=start_step,
                            target_step=target_step,
                            pixels=observed[
                                start_step:target_step,
                                environment_rank,
                            ].astype(np.uint8, copy=True),
                            action_history=histories[
                                start_step:target_step,
                                environment_rank,
                            ].astype(np.float32, copy=True),
                            target_pixels=observed[
                                target_step,
                                environment_rank,
                                1:2,
                            ].astype(np.uint8, copy=True),
                            actions=flat_actions[
                                start_step:target_step,
                                environment_rank,
                                0,
                            ].astype(np.int64, copy=True),
                            changed_fraction=changed_fraction,
                            mean_absolute_error=mean_absolute_error,
                        )
                    )

    # Prefer visually meaningful, longer excerpts, then round-robin environments so a single
    # unusually animated worker cannot consume the entire auxiliary-learning budget.
    by_environment: dict[int, list[HindsightLesson]] = {}
    for lesson in candidates:
        by_environment.setdefault(lesson.environment_rank, []).append(lesson)
    for lessons in by_environment.values():
        lessons.sort(
            key=lambda lesson: (
                lesson.changed_fraction,
                lesson.mean_absolute_error,
                lesson.action_count,
                lesson.target_step,
            ),
            reverse=True,
        )
    result: list[HindsightLesson] = []
    ranks = sorted(by_environment)
    cursor = 0
    while ranks and len(result) < config.max_lessons:
        rank = ranks[cursor % len(ranks)]
        lessons = by_environment[rank]
        if lessons:
            result.append(lessons.pop(0))
        if not lessons:
            ranks.remove(rank)
            cursor = 0
        else:
            cursor += 1
    return result


__all__ = [
    "HINDSIGHT_PROTOCOL",
    "HindsightConfig",
    "HindsightLesson",
    "extract_hindsight_lessons",
]
