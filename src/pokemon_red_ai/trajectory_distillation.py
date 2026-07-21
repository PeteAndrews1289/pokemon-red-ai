from __future__ import annotations

import math
from collections.abc import Callable, Hashable, Sequence
from dataclasses import asdict, dataclass
from typing import Generic, TypeVar

SELF_GENERATED_REPLAY_PROTOCOL = "agent-self-generated-replay-v1"

ActionT = TypeVar("ActionT")
ReplayOracle = Callable[[tuple[ActionT, ...]], bool]


class ReplayVerificationError(RuntimeError):
    """Raised when the replay oracle cannot verify a trajectory as successful."""


@dataclass(frozen=True, slots=True)
class ReplayEvidence:
    """Fail-closed provenance for a trajectory the agent discovered itself."""

    verification_id: str
    successful_replays: int
    protocol: str = SELF_GENERATED_REPLAY_PROTOCOL

    def __post_init__(self) -> None:
        if self.protocol != SELF_GENERATED_REPLAY_PROTOCOL:
            raise ValueError("Trajectory distillation accepts only agent-generated replays")
        if not self.verification_id.strip():
            raise ValueError("Replay evidence requires a verification identifier")
        if self.successful_replays < 1:
            raise ValueError("A self-generated trajectory must already have a successful replay")


@dataclass(frozen=True, slots=True)
class SelfDiscoveredMilestone:
    """An ordered action boundary observed and replay-verified by the agent."""

    milestone_id: str
    action_offset: int
    verification_id: str
    protocol: str = SELF_GENERATED_REPLAY_PROTOCOL

    def __post_init__(self) -> None:
        if self.protocol != SELF_GENERATED_REPLAY_PROTOCOL:
            raise ValueError("Milestone boundaries must be self-discovered")
        if not self.milestone_id.strip() or not self.verification_id.strip():
            raise ValueError("Milestone boundaries require identifiers and replay evidence")
        if self.action_offset < 0:
            raise ValueError("Milestone action offsets cannot be negative")


@dataclass(frozen=True, slots=True)
class VerifiedSelfTrajectory(Generic[ActionT]):
    """An agent-generated action trace plus its observed state signatures."""

    actions: tuple[ActionT, ...]
    state_signatures: tuple[Hashable, ...]
    evidence: ReplayEvidence

    def __post_init__(self) -> None:
        if not self.actions:
            raise ValueError("Trajectory distillation requires at least one action")
        if len(self.state_signatures) != len(self.actions) + 1:
            raise ValueError("A trajectory needs one state signature before and after every action")
        for signature in self.state_signatures:
            try:
                hash(signature)
            except TypeError as error:
                raise ValueError("State signatures must be hashable") from error


@dataclass(frozen=True, slots=True)
class DistillationConfig:
    """Conservative budgets for replay-backed trajectory reduction."""

    max_loop_attempts: int = 128
    max_chunk_attempts: int = 256
    minimum_actions: int = 1

    def __post_init__(self) -> None:
        if self.max_loop_attempts < 0 or self.max_chunk_attempts < 0:
            raise ValueError("Distillation attempt budgets cannot be negative")
        if self.minimum_actions < 0:
            raise ValueError("The minimum action count cannot be negative")


@dataclass(frozen=True, slots=True)
class DistillationAudit:
    """Complete accounting of proposed, accepted, and rejected edits."""

    protocol: str
    verification_id: str
    original_action_count: int
    compressed_action_count: int
    actions_removed: int
    compression_ratio: float
    baseline_oracle_calls: int
    final_oracle_calls: int
    loop_candidates_considered: int
    loop_oracle_attempts: int
    loop_deletions_accepted: int
    loop_deletions_rejected: int
    loop_actions_removed: int
    loop_budget_exhausted: bool
    chunk_candidates_considered: int
    chunk_oracle_attempts: int
    chunk_deletions_accepted: int
    chunk_deletions_rejected: int
    chunk_actions_removed: int
    chunk_budget_exhausted: bool
    total_oracle_calls: int
    oracle_actions_replayed: int
    final_replay_verified: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DistillationResult(Generic[ActionT]):
    """A replay-verified reduction with bidirectional action provenance."""

    actions: tuple[ActionT, ...]
    compressed_to_original: tuple[int, ...]
    original_to_compressed: tuple[int | None, ...]
    audit: DistillationAudit

    def map_original_boundary(self, action_offset: int) -> int:
        """Map an original between-action boundary into the compressed trace."""

        if not 0 <= action_offset <= len(self.original_to_compressed):
            raise ValueError("Original action boundary is outside the trajectory")
        return sum(index < action_offset for index in self.compressed_to_original)


@dataclass(frozen=True, slots=True)
class AdjacentSkillSegment(Generic[ActionT]):
    """One self-discovered milestone-to-milestone training segment."""

    source_milestone_id: str
    target_milestone_id: str
    start_action_offset: int
    end_action_offset: int
    actions: tuple[ActionT, ...]


@dataclass(slots=True)
class _AuditCounter:
    oracle_calls: int = 0
    oracle_actions: int = 0
    loop_candidates: int = 0
    loop_attempts: int = 0
    loop_accepted: int = 0
    loop_rejected: int = 0
    loop_removed: int = 0
    chunk_candidates: int = 0
    chunk_attempts: int = 0
    chunk_accepted: int = 0
    chunk_rejected: int = 0
    chunk_removed: int = 0


def _run_oracle(
    actions: tuple[ActionT, ...],
    oracle: ReplayOracle[ActionT],
    counter: _AuditCounter,
) -> bool:
    counter.oracle_calls += 1
    counter.oracle_actions += len(actions)
    return bool(oracle(actions))


def _next_loop(
    signatures: Sequence[Hashable],
    kept_indices: Sequence[int],
    attempted_removals: set[tuple[int, ...]],
) -> tuple[int, int] | None:
    positions: dict[Hashable, list[int]] = {}
    for end, signature in enumerate(signatures):
        for start in positions.get(signature, []):
            removal = tuple(kept_indices[start:end])
            if removal and removal not in attempted_removals:
                return start, end
        positions.setdefault(signature, []).append(end)
    return None


def _erase_verified_loops(
    original_actions: tuple[ActionT, ...],
    state_signatures: tuple[Hashable, ...],
    kept_indices: list[int],
    oracle: ReplayOracle[ActionT],
    config: DistillationConfig,
    counter: _AuditCounter,
) -> tuple[list[int], list[Hashable], bool]:
    signatures = list(state_signatures)
    attempted_removals: set[tuple[int, ...]] = set()
    exhausted = False
    while True:
        loop = _next_loop(signatures, kept_indices, attempted_removals)
        if loop is None:
            break
        start, end = loop
        removal = tuple(kept_indices[start:end])
        attempted_removals.add(removal)
        counter.loop_candidates += 1
        if len(kept_indices) - len(removal) < config.minimum_actions:
            continue
        if counter.loop_attempts >= config.max_loop_attempts:
            exhausted = True
            break
        candidate_indices = kept_indices[:start] + kept_indices[end:]
        candidate = tuple(original_actions[index] for index in candidate_indices)
        counter.loop_attempts += 1
        if _run_oracle(candidate, oracle, counter):
            kept_indices = candidate_indices
            signatures = signatures[: start + 1] + signatures[end + 1 :]
            counter.loop_accepted += 1
            counter.loop_removed += len(removal)
        else:
            counter.loop_rejected += 1
    return kept_indices, signatures, exhausted


def _delete_verified_chunks(
    original_actions: tuple[ActionT, ...],
    kept_indices: list[int],
    oracle: ReplayOracle[ActionT],
    config: DistillationConfig,
    counter: _AuditCounter,
) -> tuple[list[int], bool]:
    granularity = 2
    attempted_candidates: set[tuple[int, ...]] = set()
    exhausted = False
    while len(kept_indices) > config.minimum_actions:
        if counter.chunk_attempts >= config.max_chunk_attempts:
            exhausted = config.max_chunk_attempts > 0
            break
        granularity = min(granularity, len(kept_indices))
        chunk_size = math.ceil(len(kept_indices) / granularity)
        accepted = False
        considered_at_granularity = False
        for start in range(0, len(kept_indices), chunk_size):
            end = min(start + chunk_size, len(kept_indices))
            candidate_indices = kept_indices[:start] + kept_indices[end:]
            if len(candidate_indices) < config.minimum_actions:
                continue
            candidate_key = tuple(candidate_indices)
            if candidate_key in attempted_candidates:
                continue
            attempted_candidates.add(candidate_key)
            considered_at_granularity = True
            counter.chunk_candidates += 1
            if counter.chunk_attempts >= config.max_chunk_attempts:
                exhausted = True
                break
            candidate = tuple(original_actions[index] for index in candidate_indices)
            counter.chunk_attempts += 1
            if _run_oracle(candidate, oracle, counter):
                counter.chunk_accepted += 1
                counter.chunk_removed += end - start
                kept_indices = candidate_indices
                granularity = max(2, granularity - 1)
                accepted = True
                break
            counter.chunk_rejected += 1
        if exhausted:
            break
        if accepted:
            continue
        if granularity >= len(kept_indices) or not considered_at_granularity:
            break
        granularity = min(len(kept_indices), granularity * 2)
    return kept_indices, exhausted


def distill_self_generated_trajectory(
    trajectory: VerifiedSelfTrajectory[ActionT],
    replay_oracle: ReplayOracle[ActionT],
    *,
    config: DistillationConfig | None = None,
) -> DistillationResult[ActionT]:
    """Remove only edits whose self-generated replay still satisfies the oracle.

    The oracle should restore the trajectory's own source state, replay the supplied
    actions, and return true only when the same protected outcome is reached. Human
    demonstrations and imported action sequences are intentionally not accepted by
    the input type or provenance protocol.
    """

    settings = config or DistillationConfig()
    if settings.minimum_actions > len(trajectory.actions):
        raise ValueError("The minimum action count exceeds the original trajectory")
    counter = _AuditCounter()
    if not _run_oracle(trajectory.actions, replay_oracle, counter):
        raise ReplayVerificationError("The original self-generated trajectory failed replay")

    kept_indices = list(range(len(trajectory.actions)))
    kept_indices, _signatures, loop_exhausted = _erase_verified_loops(
        trajectory.actions,
        trajectory.state_signatures,
        kept_indices,
        replay_oracle,
        settings,
        counter,
    )
    kept_indices, chunk_exhausted = _delete_verified_chunks(
        trajectory.actions,
        kept_indices,
        replay_oracle,
        settings,
        counter,
    )
    compressed = tuple(trajectory.actions[index] for index in kept_indices)
    final_success = _run_oracle(compressed, replay_oracle, counter)
    if not final_success:
        raise ReplayVerificationError("The compressed trajectory failed its final replay")

    original_to_compressed: list[int | None] = [None] * len(trajectory.actions)
    for compressed_index, original_index in enumerate(kept_indices):
        original_to_compressed[original_index] = compressed_index
    action_count = len(trajectory.actions)
    audit = DistillationAudit(
        protocol=SELF_GENERATED_REPLAY_PROTOCOL,
        verification_id=trajectory.evidence.verification_id,
        original_action_count=action_count,
        compressed_action_count=len(compressed),
        actions_removed=action_count - len(compressed),
        compression_ratio=len(compressed) / action_count,
        baseline_oracle_calls=1,
        final_oracle_calls=1,
        loop_candidates_considered=counter.loop_candidates,
        loop_oracle_attempts=counter.loop_attempts,
        loop_deletions_accepted=counter.loop_accepted,
        loop_deletions_rejected=counter.loop_rejected,
        loop_actions_removed=counter.loop_removed,
        loop_budget_exhausted=loop_exhausted,
        chunk_candidates_considered=counter.chunk_candidates,
        chunk_oracle_attempts=counter.chunk_attempts,
        chunk_deletions_accepted=counter.chunk_accepted,
        chunk_deletions_rejected=counter.chunk_rejected,
        chunk_actions_removed=counter.chunk_removed,
        chunk_budget_exhausted=chunk_exhausted,
        total_oracle_calls=counter.oracle_calls,
        oracle_actions_replayed=counter.oracle_actions,
        final_replay_verified=final_success,
    )
    return DistillationResult(
        actions=compressed,
        compressed_to_original=tuple(kept_indices),
        original_to_compressed=tuple(original_to_compressed),
        audit=audit,
    )


def split_at_self_discovered_milestones(
    actions: Sequence[ActionT],
    boundaries: Sequence[SelfDiscoveredMilestone],
) -> tuple[AdjacentSkillSegment[ActionT], ...]:
    """Split one trace into adjacent skills without adding authored game knowledge."""

    if len(boundaries) < 2:
        raise ValueError("Adjacent skill splitting requires at least two milestones")
    offsets = [boundary.action_offset for boundary in boundaries]
    if offsets[0] != 0 or offsets[-1] != len(actions):
        raise ValueError("Milestone boundaries must cover the complete action trajectory")
    if any(current >= following for current, following in zip(offsets, offsets[1:], strict=False)):
        raise ValueError("Self-discovered milestones must be in strict action order")
    return tuple(
        AdjacentSkillSegment(
            source_milestone_id=source.milestone_id,
            target_milestone_id=target.milestone_id,
            start_action_offset=source.action_offset,
            end_action_offset=target.action_offset,
            actions=tuple(actions[source.action_offset : target.action_offset]),
        )
        for source, target in zip(boundaries, boundaries[1:], strict=False)
    )
