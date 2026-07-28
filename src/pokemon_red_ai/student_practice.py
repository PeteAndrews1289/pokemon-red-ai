from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STUDENT_PRACTICE_SCHEMA = 1
STUDENT_PRACTICE_PROTOCOL = "v9-student-closed-loop-reverse-practice-v1"
SUCCESSFUL_ROLLOUT_PROTOCOL = "v9-student-successful-rollout-v1"
ZERO_STATE_PROTOCOL = "zero-recurrent-sentinel-history-duplicate-frame-v1"
ACTOR_OBSERVATION_KEYS = ("pixels", "action_history", "target_pixels")
PRACTICE_MODES = frozenset({"current", "retention"})


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _safe_relative_file(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and bool(path.name)


def _deterministic_number(seed: int, namespace: str, counter: int) -> int:
    payload = f"{seed}:{namespace}:{counter}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def actor_practice_contract(*, action_history_length: int = 3) -> dict[str, object]:
    """Return the complete actor-visible reset contract.

    Skill identity, checkpoint identity, rung index, and remaining horizon are deliberately
    absent. They remain trainer-only scheduling data.
    """

    if action_history_length < 1:
        raise ValueError("Student practice action history must be positive")
    return {
        "observation_keys": list(ACTOR_OBSERVATION_KEYS),
        "episode_start": True,
        "recurrent_state": "zeros",
        "action_history": [-1] * action_history_length,
        "initial_frame_history": "duplicate_current",
        "reset_protocol": ZERO_STATE_PROTOCOL,
    }


@dataclass(frozen=True, slots=True)
class ReversePracticeConfig:
    """Fixed development rules for one skill's reverse closed-loop curriculum."""

    first_rung_actions: int = 8
    promotion_window: int = 30
    promotion_required_successes: int = 27
    promotion_confirmations: int = 2
    retention_fraction: float = 0.25
    success_reservoir_capacity: int = 32
    action_history_length: int = 3

    def __post_init__(self) -> None:
        if self.first_rung_actions != 8:
            raise ValueError("V9 reverse practice is frozen to an eight-action first rung")
        if self.promotion_window < 1:
            raise ValueError("Reverse practice promotion window must be positive")
        if not 1 <= self.promotion_required_successes <= self.promotion_window:
            raise ValueError("Reverse practice success threshold is outside its window")
        if self.promotion_confirmations < 1:
            raise ValueError("Reverse practice confirmations must be positive")
        if not 0.20 <= self.retention_fraction <= 0.25:
            raise ValueError("Reverse practice retention must remain between 20% and 25%")
        if self.success_reservoir_capacity < 1:
            raise ValueError("Successful rollout reservoir capacity must be positive")
        if self.action_history_length < 1:
            raise ValueError("Student practice action history must be positive")

    @property
    def promotion_threshold(self) -> float:
        return self.promotion_required_successes / self.promotion_window

    def public_dict(self) -> dict[str, int | float]:
        return {
            "first_rung_actions": self.first_rung_actions,
            "promotion_window": self.promotion_window,
            "promotion_required_successes": self.promotion_required_successes,
            "promotion_confirmations": self.promotion_confirmations,
            "promotion_threshold": self.promotion_threshold,
            "retention_fraction": self.retention_fraction,
            "success_reservoir_capacity": self.success_reservoir_capacity,
            "action_history_length": self.action_history_length,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReversePracticeConfig:
        config = cls(
            first_rung_actions=int(value["first_rung_actions"]),
            promotion_window=int(value["promotion_window"]),
            promotion_required_successes=int(value["promotion_required_successes"]),
            promotion_confirmations=int(value["promotion_confirmations"]),
            retention_fraction=float(value["retention_fraction"]),
            success_reservoir_capacity=int(value["success_reservoir_capacity"]),
            action_history_length=int(value["action_history_length"]),
        )
        recorded_threshold = float(value.get("promotion_threshold", config.promotion_threshold))
        if not math.isclose(recorded_threshold, config.promotion_threshold):
            raise ValueError("Serialized Student practice threshold is inconsistent")
        return config


@dataclass(frozen=True, slots=True)
class ReversePracticeRung:
    index: int
    remaining_actions: int
    start_action: int

    def public_dict(self) -> dict[str, int]:
        return {
            "index": self.index,
            "remaining_actions": self.remaining_actions,
            "start_action": self.start_action,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReversePracticeRung:
        return cls(
            index=int(value["index"]),
            remaining_actions=int(value["remaining_actions"]),
            start_action=int(value["start_action"]),
        )


def build_reverse_practice_rungs(
    action_count: int,
    *,
    first_rung_actions: int = 8,
) -> tuple[ReversePracticeRung, ...]:
    """Build 8/16/32/64/.../full suffixes without duplicating an exact full rung."""

    if action_count < 1:
        raise ValueError("Reverse practice needs a positive action count")
    if first_rung_actions != 8:
        raise ValueError("V9 reverse practice is frozen to an eight-action first rung")
    horizons: list[int] = []
    horizon = min(first_rung_actions, action_count)
    while horizon < action_count:
        horizons.append(horizon)
        horizon = min(action_count, horizon * 2)
    horizons.append(action_count)
    return tuple(
        ReversePracticeRung(
            index=index,
            remaining_actions=remaining,
            start_action=action_count - remaining,
        )
        for index, remaining in enumerate(horizons)
    )


@dataclass(frozen=True, slots=True)
class SuccessfulRolloutMetadata:
    """Bounded provenance for one Student-generated rollout that reached the target."""

    rollout_id: str
    skill_id: str
    rung_index: int
    remaining_actions: int
    attempt_seed: int
    action_count: int
    dataset_file: str
    dataset_sha256: str
    verification_id: str
    successful_replays: int = 1
    replay_shards: tuple[dict[str, object], ...] = ()
    protocol: str = SUCCESSFUL_ROLLOUT_PROTOCOL

    def __post_init__(self) -> None:
        if self.protocol != SUCCESSFUL_ROLLOUT_PROTOCOL:
            raise ValueError("Unsupported successful Student rollout protocol")
        if not self.rollout_id.strip() or not self.skill_id.strip():
            raise ValueError("Successful Student rollout requires identifiers")
        if self.rung_index < 0 or self.remaining_actions < 1:
            raise ValueError("Successful Student rollout has an invalid rung")
        if not 0 <= self.attempt_seed < 2**31 or self.action_count < 1:
            raise ValueError("Successful Student rollout has invalid action metadata")
        if not _safe_relative_file(self.dataset_file) or not _is_sha256(self.dataset_sha256):
            raise ValueError("Successful Student rollout artifact identity is invalid")
        if not self.verification_id.strip() or self.successful_replays < 1:
            raise ValueError("Successful Student rollout lacks replay verification")
        for shard in self.replay_shards:
            if (
                not isinstance(shard, dict)
                or not _safe_relative_file(str(shard.get("file", "")))
                or not _is_sha256(str(shard.get("sha256", "")))
                or int(shard.get("stored_bytes", 0)) < 1
                or int(shard.get("shard_count", 0)) < 1
                or not 0 <= int(shard.get("shard_index", -1)) < int(shard.get("shard_count", 0))
            ):
                raise ValueError("Successful Student rollout replay shard is invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "rollout_id": self.rollout_id,
            "skill_id": self.skill_id,
            "rung_index": self.rung_index,
            "remaining_actions": self.remaining_actions,
            "attempt_seed": self.attempt_seed,
            "action_count": self.action_count,
            "dataset_file": self.dataset_file,
            "dataset_sha256": self.dataset_sha256,
            "verification_id": self.verification_id,
            "successful_replays": self.successful_replays,
            "replay_shards": [dict(shard) for shard in self.replay_shards],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SuccessfulRolloutMetadata:
        return cls(
            protocol=str(value["protocol"]),
            rollout_id=str(value["rollout_id"]),
            skill_id=str(value["skill_id"]),
            rung_index=int(value["rung_index"]),
            remaining_actions=int(value["remaining_actions"]),
            attempt_seed=int(value["attempt_seed"]),
            action_count=int(value["action_count"]),
            dataset_file=str(value["dataset_file"]),
            dataset_sha256=str(value["dataset_sha256"]),
            verification_id=str(value["verification_id"]),
            successful_replays=int(value["successful_replays"]),
            replay_shards=tuple(dict(item) for item in value.get("replay_shards", [])),
        )


@dataclass(frozen=True, slots=True)
class PracticeChoice:
    """One trainer decision. Only :meth:`actor_reset` crosses the actor boundary."""

    decision: int
    mode: str
    rung_index: int
    remaining_actions: int
    start_action: int
    attempt_seed: int
    action_history_length: int

    def __post_init__(self) -> None:
        if self.decision < 0 or self.mode not in PRACTICE_MODES or self.rung_index < 0:
            raise ValueError("Student practice choice is invalid")
        if self.remaining_actions < 1 or self.start_action < 0:
            raise ValueError("Student practice choice has an invalid suffix")
        if not 0 <= self.attempt_seed < 2**31 or self.action_history_length < 1:
            raise ValueError("Student practice choice has invalid actor reset metadata")

    def actor_reset(self) -> dict[str, object]:
        """Return reset data with no skill, checkpoint, rung, or horizon disclosure."""

        return actor_practice_contract(action_history_length=self.action_history_length)

    def public_dict(self) -> dict[str, int | str]:
        return {
            "decision": self.decision,
            "mode": self.mode,
            "rung_index": self.rung_index,
            "remaining_actions": self.remaining_actions,
            "start_action": self.start_action,
            "attempt_seed": self.attempt_seed,
            "action_history_length": self.action_history_length,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PracticeChoice:
        return cls(
            decision=int(value["decision"]),
            mode=str(value["mode"]),
            rung_index=int(value["rung_index"]),
            remaining_actions=int(value["remaining_actions"]),
            start_action=int(value["start_action"]),
            attempt_seed=int(value["attempt_seed"]),
            action_history_length=int(value["action_history_length"]),
        )


@dataclass(frozen=True, slots=True)
class PromotionWindowEvidence:
    window: int
    attempts: int
    successes: int
    required_successes: int
    passed: bool
    consecutive_confirmations: int

    def public_dict(self) -> dict[str, int | bool]:
        return {
            "window": self.window,
            "attempts": self.attempts,
            "successes": self.successes,
            "required_successes": self.required_successes,
            "passed": self.passed,
            "consecutive_confirmations": self.consecutive_confirmations,
        }


@dataclass(frozen=True, slots=True)
class PracticeOutcome:
    promoted: bool
    curriculum_complete: bool
    window: PromotionWindowEvidence | None
    rollout_retained: bool
    evicted_rollout_id: str | None


@dataclass(slots=True)
class RungPracticeState:
    rung: ReversePracticeRung
    promoted: bool = False
    attempts: int = 0
    successes: int = 0
    retention_attempts: int = 0
    retention_successes: int = 0
    promotion_window: list[bool] = field(default_factory=list)
    consecutive_confirmations: int = 0
    completed_windows: int = 0
    successful_rollouts_seen: int = 0
    successful_rollouts: list[SuccessfulRolloutMetadata] = field(default_factory=list)

    def public_dict(self) -> dict[str, object]:
        return {
            "rung": self.rung.public_dict(),
            "promoted": self.promoted,
            "attempts": self.attempts,
            "successes": self.successes,
            "retention_attempts": self.retention_attempts,
            "retention_successes": self.retention_successes,
            "promotion_window": list(self.promotion_window),
            "consecutive_confirmations": self.consecutive_confirmations,
            "completed_windows": self.completed_windows,
            "successful_rollouts_seen": self.successful_rollouts_seen,
            "successful_rollouts": [item.public_dict() for item in self.successful_rollouts],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RungPracticeState:
        return cls(
            rung=ReversePracticeRung.from_dict(value["rung"]),
            promoted=bool(value["promoted"]),
            attempts=int(value["attempts"]),
            successes=int(value["successes"]),
            retention_attempts=int(value["retention_attempts"]),
            retention_successes=int(value["retention_successes"]),
            promotion_window=[bool(item) for item in value["promotion_window"]],
            consecutive_confirmations=int(value["consecutive_confirmations"]),
            completed_windows=int(value["completed_windows"]),
            successful_rollouts_seen=int(value["successful_rollouts_seen"]),
            successful_rollouts=[
                SuccessfulRolloutMetadata.from_dict(item) for item in value["successful_rollouts"]
            ],
        )


@dataclass(slots=True)
class StudentPracticeLedger:
    """Crash-stable scheduling and success aggregation for one self-generated skill."""

    skill_id: str
    source_action_count: int
    seed: int
    config: ReversePracticeConfig
    rungs: list[RungPracticeState]
    active_rung_index: int = 0
    schedule_decisions: int = 0
    retention_eligible_decisions: int = 0
    retention_decisions: int = 0
    attempts: int = 0
    successes: int = 0
    pending_choice: PracticeChoice | None = None

    def __post_init__(self) -> None:
        self._validate()

    @classmethod
    def initialize(
        cls,
        *,
        skill_id: str,
        source_action_count: int,
        seed: int,
        config: ReversePracticeConfig | None = None,
    ) -> StudentPracticeLedger:
        settings = config or ReversePracticeConfig()
        rungs = build_reverse_practice_rungs(
            source_action_count,
            first_rung_actions=settings.first_rung_actions,
        )
        return cls(
            skill_id=skill_id,
            source_action_count=source_action_count,
            seed=seed,
            config=settings,
            rungs=[RungPracticeState(rung=rung) for rung in rungs],
        )

    @property
    def curriculum_complete(self) -> bool:
        return self.active_rung_index == len(self.rungs)

    @property
    def active_rung(self) -> ReversePracticeRung | None:
        if self.curriculum_complete:
            return None
        return self.rungs[self.active_rung_index].rung

    def _attempt_seed(self, decision: int) -> int:
        return _deterministic_number(self.seed, "student-practice-attempt", decision) % (2**31)

    def _retention_rung_index(self, decision: int, eligible: list[int]) -> int:
        selection = _deterministic_number(self.seed, "student-practice-retention", decision)
        return eligible[selection % len(eligible)]

    def next_choice(self) -> PracticeChoice:
        """Return the next choice, replaying an unconsumed choice exactly after resume."""

        if self.pending_choice is not None:
            return self.pending_choice
        decision = self.schedule_decisions
        promoted = [index for index, state in enumerate(self.rungs) if state.promoted]
        if self.curriculum_complete:
            mode = "retention"
            rung_index = self._retention_rung_index(decision, promoted)
        else:
            use_retention = False
            if promoted:
                self.retention_eligible_decisions += 1
                target = math.floor(
                    self.retention_eligible_decisions * self.config.retention_fraction + 1e-12
                )
                use_retention = self.retention_decisions < target
            if use_retention:
                mode = "retention"
                rung_index = self._retention_rung_index(decision, promoted)
            else:
                mode = "current"
                rung_index = self.active_rung_index
        if mode == "retention":
            self.retention_decisions += 1
        rung = self.rungs[rung_index].rung
        choice = PracticeChoice(
            decision=decision,
            mode=mode,
            rung_index=rung.index,
            remaining_actions=rung.remaining_actions,
            start_action=rung.start_action,
            attempt_seed=self._attempt_seed(decision),
            action_history_length=self.config.action_history_length,
        )
        self.schedule_decisions += 1
        self.pending_choice = choice
        return choice

    def _validate_rollout(
        self,
        choice: PracticeChoice,
        rollout: SuccessfulRolloutMetadata,
    ) -> None:
        if (
            rollout.skill_id != self.skill_id
            or rollout.rung_index != choice.rung_index
            or rollout.remaining_actions != choice.remaining_actions
            or rollout.attempt_seed != choice.attempt_seed
        ):
            raise ValueError("Successful rollout does not match its Student practice attempt")
        retained_ids = {
            item.rollout_id for state in self.rungs for item in state.successful_rollouts
        }
        if rollout.rollout_id in retained_ids:
            raise ValueError("Successful rollout identifier is already retained")

    def _retain_success(
        self,
        state: RungPracticeState,
        rollout: SuccessfulRolloutMetadata,
    ) -> tuple[bool, str | None]:
        state.successful_rollouts_seen += 1
        capacity = self.config.success_reservoir_capacity
        if len(state.successful_rollouts) < capacity:
            state.successful_rollouts.append(rollout)
            return True, None
        slot = (
            _deterministic_number(
                self.seed,
                f"student-practice-reservoir:{state.rung.index}",
                state.successful_rollouts_seen,
            )
            % state.successful_rollouts_seen
        )
        if slot >= capacity:
            return False, None
        evicted = state.successful_rollouts[slot].rollout_id
        state.successful_rollouts[slot] = rollout
        return True, evicted

    def _record_promotion_window(
        self,
        state: RungPracticeState,
        success: bool,
    ) -> tuple[bool, PromotionWindowEvidence | None]:
        state.promotion_window.append(bool(success))
        if len(state.promotion_window) < self.config.promotion_window:
            return False, None
        successes = sum(state.promotion_window)
        passed = successes >= self.config.promotion_required_successes
        state.consecutive_confirmations = state.consecutive_confirmations + 1 if passed else 0
        state.completed_windows += 1
        evidence = PromotionWindowEvidence(
            window=state.completed_windows,
            attempts=self.config.promotion_window,
            successes=successes,
            required_successes=self.config.promotion_required_successes,
            passed=passed,
            consecutive_confirmations=state.consecutive_confirmations,
        )
        state.promotion_window.clear()
        promoted = state.consecutive_confirmations >= self.config.promotion_confirmations
        return promoted, evidence

    def record_attempt(
        self,
        choice: PracticeChoice,
        *,
        success: bool,
        rollout: SuccessfulRolloutMetadata | None = None,
    ) -> PracticeOutcome:
        """Record one closed-loop attempt and aggregate only verified successes."""

        if self.pending_choice is None or choice != self.pending_choice:
            raise ValueError("Student practice result does not match the pending choice")
        if success and rollout is None:
            raise ValueError("A successful Student attempt requires replay-verified metadata")
        if not success and rollout is not None:
            raise ValueError("A failed Student attempt cannot enter the success reservoir")
        if rollout is not None:
            self._validate_rollout(choice, rollout)

        state = self.rungs[choice.rung_index]
        state.attempts += 1
        state.successes += int(success)
        self.attempts += 1
        self.successes += int(success)
        retained = False
        evicted: str | None = None
        if rollout is not None:
            retained, evicted = self._retain_success(state, rollout)

        promoted = False
        window: PromotionWindowEvidence | None = None
        if choice.mode == "current":
            promoted, window = self._record_promotion_window(state, success)
            if promoted:
                state.promoted = True
                self.active_rung_index += 1
        else:
            state.retention_attempts += 1
            state.retention_successes += int(success)
        self.pending_choice = None
        self._validate()
        return PracticeOutcome(
            promoted=promoted,
            curriculum_complete=self.curriculum_complete,
            window=window,
            rollout_retained=retained,
            evicted_rollout_id=evicted,
        )

    def _validate(self) -> None:
        if not self.skill_id.strip() or self.source_action_count < 1:
            raise ValueError("Student practice ledger requires a skill and source actions")
        if not 0 <= self.seed < 2**63:
            raise ValueError("Student practice seed is invalid")
        expected = build_reverse_practice_rungs(
            self.source_action_count,
            first_rung_actions=self.config.first_rung_actions,
        )
        if tuple(state.rung for state in self.rungs) != expected:
            raise ValueError("Student practice rung ladder is inconsistent")
        if not 0 <= self.active_rung_index <= len(self.rungs):
            raise ValueError("Student practice active rung is invalid")
        if any(
            state.promoted != (index < self.active_rung_index)
            for index, state in enumerate(self.rungs)
        ):
            raise ValueError("Student practice promotion prefix is inconsistent")
        counters = (
            self.schedule_decisions,
            self.retention_eligible_decisions,
            self.retention_decisions,
            self.attempts,
            self.successes,
        )
        if any(value < 0 for value in counters) or self.successes > self.attempts:
            raise ValueError("Student practice counters are invalid")
        if self.retention_decisions > self.schedule_decisions:
            raise ValueError("Student practice retention accounting is invalid")

        rollout_ids: set[str] = set()
        for index, state in enumerate(self.rungs):
            values = (
                state.attempts,
                state.successes,
                state.retention_attempts,
                state.retention_successes,
                state.consecutive_confirmations,
                state.completed_windows,
                state.successful_rollouts_seen,
            )
            if any(value < 0 for value in values):
                raise ValueError("Student practice rung counters cannot be negative")
            if (
                state.successes > state.attempts
                or state.retention_attempts > state.attempts
                or state.retention_successes > state.retention_attempts
                or state.successful_rollouts_seen != state.successes
                or len(state.successful_rollouts) > self.config.success_reservoir_capacity
                or len(state.successful_rollouts) > state.successful_rollouts_seen
                or len(state.promotion_window) >= self.config.promotion_window
                or state.consecutive_confirmations > self.config.promotion_confirmations
                or state.consecutive_confirmations > state.completed_windows
            ):
                raise ValueError("Student practice rung accounting is inconsistent")
            if state.promoted and (
                state.consecutive_confirmations < self.config.promotion_confirmations
            ):
                raise ValueError("Student practice rung lacks promotion evidence")
            current_attempts = state.attempts - state.retention_attempts
            if current_attempts != (
                state.completed_windows * self.config.promotion_window + len(state.promotion_window)
            ):
                raise ValueError("Student practice promotion-window accounting is inconsistent")
            if (
                not state.promoted
                and state.consecutive_confirmations >= self.config.promotion_confirmations
            ):
                raise ValueError("Student practice promotion evidence was not applied")
            if (
                not state.promoted
                and index != self.active_rung_index
                and (state.attempts or state.successful_rollouts)
            ):
                raise ValueError("Student practice touched a future rung")
            for rollout in state.successful_rollouts:
                if (
                    rollout.skill_id != self.skill_id
                    or rollout.rung_index != state.rung.index
                    or rollout.remaining_actions != state.rung.remaining_actions
                    or rollout.rollout_id in rollout_ids
                ):
                    raise ValueError("Student practice rollout reservoir is inconsistent")
                rollout_ids.add(rollout.rollout_id)

        if self.attempts != sum(state.attempts for state in self.rungs):
            raise ValueError("Student practice attempt total disagrees with its rungs")
        if self.successes != sum(state.successes for state in self.rungs):
            raise ValueError("Student practice success total disagrees with its rungs")
        pending_count = int(self.pending_choice is not None)
        if self.schedule_decisions != self.attempts + pending_count:
            raise ValueError("Student practice pending decision accounting is inconsistent")
        recorded_retention = sum(state.retention_attempts for state in self.rungs)
        pending_retention = int(
            self.pending_choice is not None and self.pending_choice.mode == "retention"
        )
        if self.retention_decisions != recorded_retention + pending_retention:
            raise ValueError("Student practice retention decisions disagree with attempts")
        if self.pending_choice is not None:
            choice = self.pending_choice
            if (
                choice.decision != self.schedule_decisions - 1
                or choice.attempt_seed != self._attempt_seed(choice.decision)
                or choice.action_history_length != self.config.action_history_length
            ):
                raise ValueError("Pending Student practice choice is not reproducible")
            rung = self.rungs[choice.rung_index].rung
            if (
                choice.remaining_actions != rung.remaining_actions
                or choice.start_action != rung.start_action
                or (choice.mode == "current" and choice.rung_index != self.active_rung_index)
                or (choice.mode == "retention" and not self.rungs[choice.rung_index].promoted)
            ):
                raise ValueError("Pending Student practice choice is inconsistent")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": STUDENT_PRACTICE_SCHEMA,
            "protocol": STUDENT_PRACTICE_PROTOCOL,
            "skill_id": self.skill_id,
            "source_action_count": self.source_action_count,
            "seed": self.seed,
            "config": self.config.public_dict(),
            "active_rung_index": self.active_rung_index,
            "schedule_decisions": self.schedule_decisions,
            "retention_eligible_decisions": self.retention_eligible_decisions,
            "retention_decisions": self.retention_decisions,
            "attempts": self.attempts,
            "successes": self.successes,
            "pending_choice": (
                None if self.pending_choice is None else self.pending_choice.public_dict()
            ),
            "rungs": [state.public_dict() for state in self.rungs],
            "actor_contract": actor_practice_contract(
                action_history_length=self.config.action_history_length
            ),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> StudentPracticeLedger:
        if int(value.get("schema_version", -1)) != STUDENT_PRACTICE_SCHEMA:
            raise ValueError("Unsupported Student practice ledger schema")
        if value.get("protocol") != STUDENT_PRACTICE_PROTOCOL:
            raise ValueError("Unsupported Student practice ledger protocol")
        config = ReversePracticeConfig.from_dict(value["config"])
        expected_contract = actor_practice_contract(
            action_history_length=config.action_history_length
        )
        if value.get("actor_contract") != expected_contract:
            raise ValueError("Serialized Student actor contract changed")
        pending = value.get("pending_choice")
        return cls(
            skill_id=str(value["skill_id"]),
            source_action_count=int(value["source_action_count"]),
            seed=int(value["seed"]),
            config=config,
            rungs=[RungPracticeState.from_dict(item) for item in value["rungs"]],
            active_rung_index=int(value["active_rung_index"]),
            schedule_decisions=int(value["schedule_decisions"]),
            retention_eligible_decisions=int(value["retention_eligible_decisions"]),
            retention_decisions=int(value["retention_decisions"]),
            attempts=int(value["attempts"]),
            successes=int(value["successes"]),
            pending_choice=(None if pending is None else PracticeChoice.from_dict(pending)),
        )
