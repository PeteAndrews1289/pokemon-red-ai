from __future__ import annotations

import json

import pytest

from pokemon_red_ai.skill_graph import (
    SKILL_GRAPH_PROTOCOL,
    ObservedMilestoneFirstHit,
    StableStateIdentity,
    normalize_first_hit_replay,
)


def digest(value: int) -> str:
    return f"{value:064x}"


def first_hit(index: int, offset: int, *, state: int | None = None) -> ObservedMilestoneFirstHit:
    identity = index if state is None else state
    return ObservedMilestoneFirstHit(
        milestone_id=f"milestone-{index}",
        milestone_index=index,
        action_offset=offset,
        state_identity=StableStateIdentity(
            stable_state_sha256=digest(identity),
            snapshot_sha256=digest(identity + 100),
        ),
        verification_id=f"replay-proof-{index}-{offset}",
    )


def test_async_skip_replay_is_split_at_every_concrete_first_hit() -> None:
    actions = tuple("abcdefgh")
    hits = (
        first_hit(1, 0),
        first_hit(2, 2),
        first_hit(3, 5),
        first_hit(4, 8),
    )

    graph = normalize_first_hit_replay(actions, hits, replay_id="worker-1-depth-1-to-4")

    assert [(edge.source.milestone_index, edge.target.milestone_index) for edge in graph.edges] == [
        (1, 2),
        (2, 3),
        (3, 4),
    ]
    assert [edge.actions for edge in graph.edges] == [
        ("a", "b"),
        ("c", "d", "e"),
        ("f", "g", "h"),
    ]
    assert graph.audit.inserted_split_boundaries == 2
    assert graph.audit.replay_action_count == len(actions)


def test_nodes_and_edges_preserve_the_exact_first_hit_state_objects() -> None:
    source = first_hit(2, 0, state=20)
    target = first_hit(3, 2, state=30)

    graph = normalize_first_hit_replay((0, 1), (source, target), replay_id="exact-state")

    assert graph.nodes[0].state_identity is source.state_identity
    assert graph.nodes[1].state_identity is target.state_identity
    assert graph.edges[0].source is graph.nodes[0]
    assert graph.edges[0].target is graph.nodes[1]


def test_mutable_input_sequences_are_copied_into_immutable_edges() -> None:
    actions = ["up", "a"]
    hits = [first_hit(1, 0), first_hit(2, 2)]

    graph = normalize_first_hit_replay(actions, hits, replay_id="copied-input")
    actions[0] = "down"
    hits.clear()

    assert graph.edges[0].actions == ("up", "a")
    assert len(graph.nodes) == 2


def test_same_ordinal_in_another_replay_does_not_reuse_a_node() -> None:
    first = normalize_first_hit_replay(
        (0,),
        (first_hit(3, 0, state=30), first_hit(4, 1, state=40)),
        replay_id="branch-a",
    )
    second = normalize_first_hit_replay(
        (0,),
        (first_hit(3, 0, state=31), first_hit(4, 1, state=41)),
        replay_id="branch-b",
    )

    assert first.nodes[0].milestone_index == second.nodes[0].milestone_index
    assert first.nodes[0].node_id != second.nodes[0].node_id
    assert first.nodes[0].state_identity != second.nodes[0].state_identity


def test_missing_intermediate_first_hit_is_not_filled_by_ordinal() -> None:
    with pytest.raises(ValueError, match="intermediate milestone"):
        normalize_first_hit_replay(
            (0, 1),
            (first_hit(1, 0), first_hit(4, 2)),
            replay_id="unsafe-skip",
        )


@pytest.mark.parametrize(
    ("hits", "message"),
    [
        ((first_hit(1, 1), first_hit(2, 2)), "cover the complete replay"),
        ((first_hit(1, 0), first_hit(2, 1)), "cover the complete replay"),
        (
            (first_hit(1, 0), first_hit(2, 0), first_hit(3, 2)),
            "action offsets must be strictly increasing",
        ),
        (
            (first_hit(2, 0), first_hit(1, 1), first_hit(3, 2)),
            "milestone indices must be strictly increasing",
        ),
    ],
)
def test_replay_boundaries_and_indices_are_fail_closed(
    hits: tuple[ObservedMilestoneFirstHit, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_first_hit_replay((0, 1), hits, replay_id="invalid-order")


def test_two_milestones_cannot_claim_one_concrete_state() -> None:
    shared = StableStateIdentity(digest(88), digest(188))
    hits = (
        ObservedMilestoneFirstHit("one", 1, 0, shared, "proof-one"),
        ObservedMilestoneFirstHit("two", 2, 1, shared, "proof-two"),
    )

    with pytest.raises(ValueError, match="cannot reuse one concrete stable-state identity"):
        normalize_first_hit_replay((0,), hits, replay_id="state-alias")


def test_state_identity_requires_payload_free_cryptographic_digests() -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        StableStateIdentity("ordinal-4", digest(104))
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        StableStateIdentity(digest(4), "raw-snapshot-bytes")


def test_public_audit_is_json_serializable_and_omits_actions_and_payloads() -> None:
    graph = normalize_first_hit_replay(
        ("up", "a", "down"),
        (first_hit(5, 0), first_hit(6, 3)),
        replay_id="public-audit",
    )

    public = graph.public_audit()
    encoded = json.dumps(public, sort_keys=True)

    assert public["protocol"] == SKILL_GRAPH_PROTOCOL
    assert public["edges"][0]["action_count"] == 3
    assert public["nodes"][0]["state_identity"] == {
        "stable_state_sha256": digest(5),
        "snapshot_sha256": digest(105),
    }
    assert "actions" not in encoded
    assert "up" not in encoded
    assert "raw_snapshot" not in encoded
