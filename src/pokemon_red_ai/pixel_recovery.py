from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

PIXEL_LOOP_RECOVERY_PROTOCOL = "pixels-only-loop-recovery-v1"
RECOVERY_TRIGGERS = frozenset({"blocked_repeat", "visual_cycle", "progress_stagnation"})


@dataclass(frozen=True, slots=True)
class PixelLoopRecoveryConfig:
    """Route-agnostic recovery settings derived only from rendered frames and actions."""

    action_count: int
    directional_action_count: int = 4
    cycle_window: int = 128
    cycle_unique_limit: int = 8
    recovery_actions: int = 32
    blocked_repeat_threshold: int = 3
    stagnation_threshold: int = 1_024
    escape_confirmations: int = 1
    ineffective_change_fraction: float = 0.02
    ineffective_mean_absolute_error: float = 2.0
    escape_change_fraction: float = 0.05
    escape_mean_absolute_error: float = 5.0

    def __post_init__(self) -> None:
        if self.action_count < 2:
            raise ValueError("Pixel loop recovery requires at least two actions")
        if not 1 <= self.directional_action_count <= self.action_count:
            raise ValueError("Pixel loop recovery directional action count is invalid")
        if self.cycle_window < 4 or not 1 <= self.cycle_unique_limit < self.cycle_window:
            raise ValueError("Pixel loop recovery cycle settings are invalid")
        if (
            self.recovery_actions < 1
            or self.blocked_repeat_threshold < 1
            or self.stagnation_threshold < self.cycle_window
        ):
            raise ValueError("Pixel loop recovery action settings must be positive")
        if not 1 <= self.escape_confirmations <= self.recovery_actions:
            raise ValueError("Pixel loop recovery escape confirmations are invalid")
        if not 0 < self.ineffective_change_fraction <= self.escape_change_fraction <= 1:
            raise ValueError("Pixel loop recovery change fractions are invalid")
        if not 0 <= self.ineffective_mean_absolute_error <= self.escape_mean_absolute_error:
            raise ValueError("Pixel loop recovery mean-error thresholds are invalid")


@dataclass(frozen=True, slots=True)
class PixelLoopRecoveryStep:
    """One auditable pixels-only transition; the submitted action is never replaced."""

    submitted_action: int
    executed_action: int
    changed_fraction: float
    mean_absolute_error: float
    perceptually_changed: bool
    blocked_direction_attempt: bool
    repeated_blocked_attempt: bool
    recovery_action: bool
    recovery_event: str | None
    recovery_trigger: str | None
    recovery_active: bool


@dataclass(slots=True)
class PixelLoopRecovery:
    """Detect repeated visual cycles and permit bounded recovery before an episode reset.

    This object receives only preprocessed rendered frames and the action selected by the
    recurrent policy.  It never receives RAM, coordinates, milestones, maps, or route guidance,
    and it never replaces or masks an action.
    """

    config: PixelLoopRecoveryConfig
    _previous_sample: np.ndarray | None = field(default=None, init=False, repr=False)
    _previous_frame: np.ndarray | None = field(default=None, init=False, repr=False)
    _recent_signatures: deque[bytes] = field(init=False, repr=False)
    _blocked_counts: list[int] = field(init=False, repr=False)
    _recovery_active: bool = field(default=False, init=False)
    _recovery_remaining: int = field(default=0, init=False)
    _recovery_trigger: str | None = field(default=None, init=False)
    _ineffective_actions: int = field(default=0, init=False)
    _escape_streak: int = field(default=0, init=False)
    _trapped_signatures: set[bytes] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self._recent_signatures = deque(maxlen=self.config.cycle_window)
        self._blocked_counts = [0] * self.config.directional_action_count

    @staticmethod
    def _sample(frame: np.ndarray) -> np.ndarray:
        if frame.ndim != 2 or frame.size == 0:
            raise ValueError("Pixel loop recovery expects one non-empty grayscale frame")
        value = frame.astype(np.uint8, copy=False)
        return (value[::4, ::4] // 32).astype(np.uint8, copy=False)

    @staticmethod
    def _signature(sample: np.ndarray) -> bytes:
        return sample.tobytes()

    @property
    def active(self) -> bool:
        return self._recovery_active

    @property
    def remaining_actions(self) -> int:
        return self._recovery_remaining

    @property
    def trigger(self) -> str | None:
        return self._recovery_trigger

    def reset(self, frame: np.ndarray) -> None:
        sample = self._sample(frame).copy()
        self._previous_sample = sample
        self._previous_frame = frame.astype(np.uint8, copy=True)
        self._recent_signatures = deque([self._signature(sample)], maxlen=self.config.cycle_window)
        self._blocked_counts = [0] * self.config.directional_action_count
        self._recovery_active = False
        self._recovery_remaining = 0
        self._recovery_trigger = None
        self._ineffective_actions = 0
        self._escape_streak = 0
        self._trapped_signatures = set()

    def _open_recovery(self, trigger: str) -> None:
        if trigger not in RECOVERY_TRIGGERS:
            raise ValueError("Pixel loop recovery trigger is unsupported")
        self._recovery_active = True
        self._recovery_remaining = self.config.recovery_actions
        self._recovery_trigger = trigger
        self._ineffective_actions = 0
        self._escape_streak = 0
        self._trapped_signatures = set(self._recent_signatures)

    def _close_recovery(self, signature: bytes) -> None:
        self._recovery_active = False
        self._recovery_remaining = 0
        self._recovery_trigger = None
        self._ineffective_actions = 0
        self._escape_streak = 0
        self._trapped_signatures = set()
        self._recent_signatures = deque([signature], maxlen=self.config.cycle_window)

    def observe(self, action: int, frame: np.ndarray) -> PixelLoopRecoveryStep:
        """Record the exact submitted action and its visual effect.

        The returned ``executed_action`` deliberately equals ``submitted_action``.  Keeping that
        invariant explicit prevents an environment wrapper from corrupting PPO's on-policy
        action attribution while trying to help the agent escape.
        """

        action_index = int(action)
        if not 0 <= action_index < self.config.action_count:
            raise ValueError("Pixel loop recovery action is outside the declared action space")
        sample = self._sample(frame).copy()
        if self._previous_sample is None:
            self.reset(frame)
            return PixelLoopRecoveryStep(
                submitted_action=action_index,
                executed_action=action_index,
                changed_fraction=0.0,
                mean_absolute_error=0.0,
                perceptually_changed=False,
                blocked_direction_attempt=False,
                repeated_blocked_attempt=False,
                recovery_action=False,
                recovery_event=None,
                recovery_trigger=None,
                recovery_active=False,
            )

        current_frame = frame.astype(np.uint8, copy=False)
        if self._previous_frame is None:
            raise RuntimeError("Pixel loop recovery frame memory is incomplete")
        changed_fraction = float(np.mean(current_frame != self._previous_frame))
        mean_absolute_error = float(
            np.mean(np.abs(current_frame.astype(np.int16) - self._previous_frame.astype(np.int16)))
        )
        ineffective = (
            changed_fraction < self.config.ineffective_change_fraction
            and mean_absolute_error < self.config.ineffective_mean_absolute_error
        )
        changed = not ineffective
        self._ineffective_actions = self._ineffective_actions + 1 if ineffective else 0
        escape_change = (
            changed_fraction >= self.config.escape_change_fraction
            or mean_absolute_error >= self.config.escape_mean_absolute_error
        )
        directional = action_index < self.config.directional_action_count
        blocked = directional and not changed
        repeated_blocked = False
        if changed:
            self._blocked_counts = [0] * self.config.directional_action_count
        elif directional:
            self._blocked_counts[action_index] += 1
            repeated_blocked = (
                self._blocked_counts[action_index] >= self.config.blocked_repeat_threshold
            )

        signature = self._signature(sample)
        recovery_was_active = self._recovery_active
        recovery_event: str | None = None
        recovery_trigger = self._recovery_trigger
        if recovery_was_active:
            self._recovery_remaining -= 1
            novel_escape = escape_change and signature not in self._trapped_signatures
            if recovery_trigger == "blocked_repeat" and novel_escape and not directional:
                recovery_event = "context_changed"
                self._close_recovery(signature)
            elif novel_escape:
                self._escape_streak += 1
            else:
                self._escape_streak = 0
            if recovery_event is None and self._escape_streak >= self.config.escape_confirmations:
                recovery_event = "escaped"
                self._close_recovery(signature)
            elif recovery_event is None and self._recovery_remaining <= 0:
                recovery_event = "expired"
                self._close_recovery(signature)
        else:
            self._recent_signatures.append(signature)
            if repeated_blocked:
                recovery_event = "started"
                recovery_trigger = "blocked_repeat"
                self._open_recovery(recovery_trigger)
            elif (
                len(self._recent_signatures) == self.config.cycle_window
                and len(set(self._recent_signatures)) <= self.config.cycle_unique_limit
            ):
                recovery_event = "started"
                recovery_trigger = "visual_cycle"
                self._open_recovery(recovery_trigger)
            elif self._ineffective_actions >= self.config.stagnation_threshold:
                recovery_event = "started"
                recovery_trigger = "progress_stagnation"
                self._open_recovery(recovery_trigger)

        if self._recovery_active and recovery_was_active:
            self._recent_signatures.append(signature)
        self._previous_sample = sample
        self._previous_frame = current_frame.copy()
        return PixelLoopRecoveryStep(
            submitted_action=action_index,
            executed_action=action_index,
            changed_fraction=changed_fraction,
            mean_absolute_error=mean_absolute_error,
            perceptually_changed=changed,
            blocked_direction_attempt=blocked,
            repeated_blocked_attempt=repeated_blocked,
            recovery_action=recovery_was_active,
            recovery_event=recovery_event,
            recovery_trigger=recovery_trigger,
            recovery_active=self._recovery_active,
        )


__all__ = [
    "PIXEL_LOOP_RECOVERY_PROTOCOL",
    "RECOVERY_TRIGGERS",
    "PixelLoopRecovery",
    "PixelLoopRecoveryConfig",
    "PixelLoopRecoveryStep",
]
