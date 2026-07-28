from __future__ import annotations

import pytest

from pokemon_red_ai.trajectory_distillation import (
    SELF_GENERATED_REPLAY_PROTOCOL,
    DistillationConfig,
    ReplayEvidence,
    ReplayVerificationError,
    SelfDiscoveredMilestone,
    VerifiedSelfTrajectory,
    distill_self_generated_trajectory,
    split_at_self_discovered_milestones,
)


def trajectory(
    actions: tuple[str, ...],
    signatures: tuple[str, ...] | None = None,
) -> VerifiedSelfTrajectory[str]:
    return VerifiedSelfTrajectory(
        actions=actions,
        state_signatures=signatures or tuple(f"state-{index}" for index in range(len(actions) + 1)),
        evidence=ReplayEvidence(verification_id="replay-17", successful_replays=3),
    )


def contains_in_order(actions: tuple[str, ...], required: tuple[str, ...]) -> bool:
    position = 0
    for action in actions:
        if position < len(required) and action == required[position]:
            position += 1
    return position == len(required)


def test_provenance_rejects_imported_or_unverified_trajectories() -> None:
    with pytest.raises(ValueError, match="agent-generated"):
        ReplayEvidence(
            verification_id="human-demo",
            successful_replays=1,
            protocol="imported-human-demonstration",
        )
    with pytest.raises(ValueError, match="successful replay"):
        ReplayEvidence(verification_id="unverified", successful_replays=0)


def test_repeated_state_loop_is_erased_only_after_successful_replay() -> None:
    source = trajectory(
        ("start", "left", "right", "up", "select"),
        ("boot", "menu", "detour", "menu", "hall", "goal"),
    )
    result = distill_self_generated_trajectory(
        source,
        lambda actions: contains_in_order(actions, ("start", "up", "select")),
        config=DistillationConfig(max_loop_attempts=8, max_chunk_attempts=0),
    )

    assert result.actions == ("start", "up", "select")
    assert result.compressed_to_original == (0, 3, 4)
    assert result.original_to_compressed == (0, None, None, 1, 2)
    assert result.map_original_boundary(4) == 2
    assert result.audit.loop_deletions_accepted == 1
    assert result.audit.loop_actions_removed == 2
    assert result.audit.final_replay_verified is True


def test_state_signature_collision_cannot_override_replay_oracle() -> None:
    source = trajectory(
        ("start", "key", "door"),
        ("boot", "same", "same", "goal"),
    )
    result = distill_self_generated_trajectory(
        source,
        lambda actions: actions == source.actions,
        config=DistillationConfig(max_loop_attempts=4, max_chunk_attempts=0),
    )

    assert result.actions == source.actions
    assert result.audit.loop_deletions_accepted == 0
    assert result.audit.loop_deletions_rejected == 1


def test_delta_debug_chunk_deletion_keeps_only_replay_required_actions() -> None:
    source = trajectory(("start", "noise", "left", "up", "noise", "select", "noise"))
    result = distill_self_generated_trajectory(
        source,
        lambda actions: contains_in_order(actions, ("start", "up", "select")),
        config=DistillationConfig(max_loop_attempts=0, max_chunk_attempts=40),
    )

    assert result.actions == ("start", "up", "select")
    assert result.compressed_to_original == (0, 3, 5)
    assert result.audit.chunk_deletions_accepted >= 1
    assert result.audit.chunk_actions_removed == 4
    assert result.audit.total_oracle_calls == result.audit.chunk_oracle_attempts + 2
    assert result.audit.as_dict()["compressed_action_count"] == 3


def test_chunk_deletion_honors_attempt_budget() -> None:
    source = trajectory(("a", "b", "c", "d"))
    result = distill_self_generated_trajectory(
        source,
        lambda actions: actions == source.actions,
        config=DistillationConfig(max_loop_attempts=0, max_chunk_attempts=1),
    )

    assert result.actions == source.actions
    assert result.audit.chunk_oracle_attempts == 1
    assert result.audit.chunk_budget_exhausted is True
    assert result.audit.total_oracle_calls == 3
    assert result.audit.oracle_actions_replayed == 10


def test_original_and_final_replay_must_both_succeed() -> None:
    source = trajectory(("start", "select"))
    outcomes = iter((True, False))

    with pytest.raises(ReplayVerificationError, match="final replay"):
        distill_self_generated_trajectory(
            source,
            lambda _actions: next(outcomes),
            config=DistillationConfig(max_loop_attempts=0, max_chunk_attempts=0),
        )


def test_self_discovered_boundaries_form_adjacent_skill_segments() -> None:
    actions = ("a", "b", "c", "d", "e")
    boundaries = (
        SelfDiscoveredMilestone("power-on", 0, "root-replay"),
        SelfDiscoveredMilestone("outside", 2, "outside-replay"),
        SelfDiscoveredMilestone("route-one", 5, "route-replay"),
    )

    segments = split_at_self_discovered_milestones(actions, boundaries)

    assert [(segment.source_milestone_id, segment.target_milestone_id) for segment in segments] == [
        ("power-on", "outside"),
        ("outside", "route-one"),
    ]
    assert segments[0].actions == ("a", "b")
    assert segments[1].actions == ("c", "d", "e")


def test_milestone_split_rejects_authored_or_incomplete_boundaries() -> None:
    with pytest.raises(ValueError, match="self-discovered"):
        SelfDiscoveredMilestone(
            "walkthrough-step",
            1,
            "human-note",
            protocol="authored-route-plan",
        )
    boundaries = (
        SelfDiscoveredMilestone("power-on", 0, "root-replay"),
        SelfDiscoveredMilestone("outside", 1, "outside-replay"),
    )
    with pytest.raises(ValueError, match="complete action trajectory"):
        split_at_self_discovered_milestones(("a", "b"), boundaries)


def test_public_protocol_is_stable_for_audit_artifacts() -> None:
    assert SELF_GENERATED_REPLAY_PROTOCOL == "agent-self-generated-replay-v1"
