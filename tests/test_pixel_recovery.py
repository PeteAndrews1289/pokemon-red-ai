from __future__ import annotations

import numpy as np

from pokemon_red_ai.pixel_recovery import (
    PIXEL_LOOP_RECOVERY_PROTOCOL,
    PixelLoopRecovery,
    PixelLoopRecoveryConfig,
)


def frame(value: int = 0, *, shape: tuple[int, int] = (72, 80)) -> np.ndarray:
    return np.full(shape, value, dtype=np.uint8)


def config(**overrides: object) -> PixelLoopRecoveryConfig:
    values: dict[str, object] = {
        "action_count": 8,
        "cycle_window": 16,
        "cycle_unique_limit": 2,
        "recovery_actions": 3,
        "blocked_repeat_threshold": 3,
        "escape_confirmations": 1,
        "ineffective_change_fraction": 0.02,
        "ineffective_mean_absolute_error": 2.0,
        "escape_change_fraction": 0.05,
        "escape_mean_absolute_error": 5.0,
    }
    values.update(overrides)
    return PixelLoopRecoveryConfig(**values)  # type: ignore[arg-type]


def start_blocked_recovery(
    tracker: PixelLoopRecovery,
    *,
    action: int = 0,
    pixels: np.ndarray | None = None,
) -> None:
    current = frame() if pixels is None else pixels
    tracker.reset(current)
    first = tracker.observe(action, current)
    second = tracker.observe(action, current)
    started = tracker.observe(action, current)

    assert first.recovery_event is None
    assert second.recovery_event is None
    assert started.recovery_event == "started"
    assert started.recovery_trigger == "blocked_repeat"


def test_repeated_block_starts_on_exactly_the_third_attempt_and_preserves_action() -> None:
    tracker = PixelLoopRecovery(config())
    pixels = frame()
    tracker.reset(pixels)

    steps = [tracker.observe(2, pixels) for _ in range(3)]

    assert [step.repeated_blocked_attempt for step in steps] == [False, False, True]
    assert [step.recovery_event for step in steps] == [None, None, "started"]
    assert steps[-1].recovery_trigger == "blocked_repeat"
    assert steps[-1].recovery_action is False
    assert tracker.active is True
    assert tracker.remaining_actions == 3
    assert all(step.submitted_action == step.executed_action == 2 for step in steps)


def test_cardinal_directions_have_identical_recovery_semantics() -> None:
    outcomes: list[tuple[object, ...]] = []
    pixels = frame()
    for action in range(4):
        tracker = PixelLoopRecovery(config())
        tracker.reset(pixels)
        steps = [tracker.observe(action, pixels) for _ in range(3)]
        final = steps[-1]
        outcomes.append(
            (
                tuple(step.blocked_direction_attempt for step in steps),
                tuple(step.repeated_blocked_attempt for step in steps),
                tuple(step.recovery_event for step in steps),
                final.recovery_trigger,
                final.recovery_active,
                tracker.remaining_actions,
            )
        )
        assert all(step.submitted_action == step.executed_action == action for step in steps)

    assert len(set(outcomes)) == 1


def test_recovery_expires_after_exactly_the_declared_number_of_actions() -> None:
    tracker = PixelLoopRecovery(config(recovery_actions=3))
    pixels = frame()
    start_blocked_recovery(tracker, pixels=pixels)

    steps = [tracker.observe(0, pixels) for _ in range(3)]

    assert [step.recovery_action for step in steps] == [True, True, True]
    assert [step.recovery_event for step in steps] == [None, None, "expired"]
    assert [step.recovery_active for step in steps] == [True, True, False]
    assert all(step.submitted_action == step.executed_action == 0 for step in steps)
    assert tracker.active is False
    assert tracker.remaining_actions == 0


def test_blocked_recovery_separates_context_change_from_directional_escape() -> None:
    tracker = PixelLoopRecovery(config())
    start_blocked_recovery(tracker)

    context_changed = tracker.observe(6, frame(255))

    assert context_changed.recovery_action is True
    assert context_changed.recovery_event == "context_changed"
    assert context_changed.recovery_trigger == "blocked_repeat"
    assert context_changed.perceptually_changed is True
    assert context_changed.blocked_direction_attempt is False
    assert context_changed.submitted_action == context_changed.executed_action == 6
    assert tracker.active is False
    assert tracker.remaining_actions == 0

    start_blocked_recovery(tracker, pixels=frame())
    escaped = tracker.observe(1, frame(255))
    assert escaped.recovery_event == "escaped"
    assert escaped.recovery_trigger == "blocked_repeat"
    assert escaped.submitted_action == escaped.executed_action == 1


def test_generic_visual_cycle_can_open_a_window_without_overriding_noop() -> None:
    tracker = PixelLoopRecovery(
        config(cycle_window=4, cycle_unique_limit=1, blocked_repeat_threshold=10)
    )
    pixels = frame()
    tracker.reset(pixels)

    steps = [tracker.observe(7, pixels) for _ in range(3)]

    assert [step.recovery_event for step in steps] == [None, None, "started"]
    assert steps[-1].recovery_trigger == "visual_cycle"
    assert steps[-1].blocked_direction_attempt is False
    assert all(step.submitted_action == step.executed_action == 7 for step in steps)

    escaped = tracker.observe(6, frame(255))
    assert escaped.recovery_event == "escaped"
    assert escaped.recovery_trigger == "visual_cycle"
    assert escaped.submitted_action == escaped.executed_action == 6


def test_pixels_only_long_stagnation_opens_the_same_bounded_window() -> None:
    tracker = PixelLoopRecovery(
        config(
            cycle_window=4,
            cycle_unique_limit=1,
            blocked_repeat_threshold=10,
            stagnation_threshold=5,
        )
    )
    pixels = frame(shape=(10, 10))
    tracker.reset(pixels)

    steps = []
    for value in (32, 64, 96, 128, 160):
        current = pixels.copy()
        current[0, 0] = value
        steps.append(tracker.observe(7, current))

    assert [step.recovery_event for step in steps] == [None, None, None, None, "started"]
    assert tracker.active is True
    assert tracker.trigger == "progress_stagnation"
    assert tracker.remaining_actions == 3
    step = tracker.observe(4, frame(255, shape=(10, 10)))
    assert step.recovery_event == "escaped"
    assert step.recovery_trigger == "progress_stagnation"


def test_ineffective_thresholds_are_exact_and_uint8_difference_does_not_wrap() -> None:
    base = frame(shape=(10, 10))

    below_both = base.copy()
    below_both[0, 0] = 199  # 1% changed and MAE 1.99: below both strict thresholds.
    tracker = PixelLoopRecovery(config(blocked_repeat_threshold=10))
    tracker.reset(base)
    ineffective = tracker.observe(0, below_both)
    assert ineffective.changed_fraction == 0.01
    assert ineffective.mean_absolute_error == 1.99
    assert ineffective.perceptually_changed is False
    assert ineffective.blocked_direction_attempt is True

    fraction_boundary = base.copy()
    fraction_boundary[0, :2] = 1  # Exactly 2% changed: equality is effective.
    tracker.reset(base)
    fraction_effective = tracker.observe(0, fraction_boundary)
    assert fraction_effective.changed_fraction == 0.02
    assert fraction_effective.perceptually_changed is True

    error_boundary = base.copy()
    error_boundary[0, 0] = 200  # Exactly MAE 2.0: equality is effective.
    tracker.reset(base)
    error_effective = tracker.observe(0, error_boundary)
    assert error_effective.mean_absolute_error == 2.0
    assert error_effective.perceptually_changed is True

    high = frame(255, shape=(10, 10))
    tracker.reset(base)
    rising = tracker.observe(0, high)
    tracker.reset(high)
    falling = tracker.observe(0, base)
    assert rising.mean_absolute_error == 255.0
    assert falling.mean_absolute_error == 255.0
    assert rising.changed_fraction == falling.changed_fraction == 1.0


def test_reset_is_episode_local_and_trackers_do_not_share_state() -> None:
    first = PixelLoopRecovery(config())
    second = PixelLoopRecovery(config())
    pixels = frame()
    first.reset(pixels)
    second.reset(pixels)

    for _ in range(3):
        first.observe(0, pixels)
    second_first = second.observe(1, pixels)
    assert first.active is True
    assert second_first.repeated_blocked_attempt is False
    assert second.active is False

    first.reset(frame(64))
    assert first.active is False
    assert first.remaining_actions == 0
    after_reset = first.observe(0, frame(64))
    assert after_reset.repeated_blocked_attempt is False

    second.observe(1, pixels)
    second_started = second.observe(1, pixels)
    assert second_started.recovery_event == "started"
    assert second.active is True
    assert PIXEL_LOOP_RECOVERY_PROTOCOL == "pixels-only-loop-recovery-v1"
