from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

SKILL_GRAPH_PROTOCOL = "self-generated-consecutive-skill-graph-v1"

ActionT = TypeVar("ActionT")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _require_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class StableStateIdentity:
    """Public, payload-free identity for one exact replay state.

    ``stable_state_sha256`` identifies the save/load-stable visual and semantic
    state projection. ``snapshot_sha256`` binds the private restorable snapshot
    without putting its bytes in the graph or its public audit.
    """

    stable_state_sha256: str
    snapshot_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.stable_state_sha256, "Stable-state identity")
        _require_sha256(self.snapshot_sha256, "Snapshot identity")

    def public_dict(self) -> dict[str, str]:
        return {
            "stable_state_sha256": self.stable_state_sha256,
            "snapshot_sha256": self.snapshot_sha256,
        }


@dataclass(frozen=True, slots=True)
class ObservedMilestoneFirstHit:
    """The first concrete state at which one replay reached a milestone."""

    milestone_id: str
    milestone_index: int
    action_offset: int
    state_identity: StableStateIdentity
    verification_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.milestone_id, "Milestone identifier")
        _require_identifier(self.verification_id, "First-hit verification identifier")
        if self.milestone_index < 0:
            raise ValueError("Milestone indices cannot be negative")
        if self.action_offset < 0:
            raise ValueError("First-hit action offsets cannot be negative")
        if not isinstance(self.state_identity, StableStateIdentity):
            raise ValueError("A first hit requires a concrete stable-state identity")


@dataclass(frozen=True, slots=True)
class ConsecutiveSkillNode:
    """One replay-local milestone node, keyed by concrete state rather than ordinal."""

    node_id: str
    milestone_id: str
    milestone_index: int
    action_offset: int
    state_identity: StableStateIdentity
    verification_id: str

    def public_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "milestone_id": self.milestone_id,
            "milestone_index": self.milestone_index,
            "action_offset": self.action_offset,
            "state_identity": self.state_identity.public_dict(),
            "verification_id": self.verification_id,
        }


@dataclass(frozen=True, slots=True)
class ConsecutiveSkillEdge(Generic[ActionT]):
    """A strictly adjacent milestone edge sliced at exact first-hit boundaries."""

    edge_id: str
    source: ConsecutiveSkillNode
    target: ConsecutiveSkillNode
    start_action_offset: int
    end_action_offset: int
    actions: tuple[ActionT, ...]

    def __post_init__(self) -> None:
        if self.target.milestone_index != self.source.milestone_index + 1:
            raise ValueError("Skill edges must connect consecutive milestone indices")
        if self.start_action_offset != self.source.action_offset:
            raise ValueError("Skill edge start does not preserve its source first hit")
        if self.end_action_offset != self.target.action_offset:
            raise ValueError("Skill edge end does not preserve its target first hit")
        if self.end_action_offset <= self.start_action_offset:
            raise ValueError("Skill edges require a positive action span")
        if len(self.actions) != self.end_action_offset - self.start_action_offset:
            raise ValueError("Skill edge actions do not cover their declared action span")

    def public_dict(self) -> dict[str, object]:
        """Return provenance and counts, deliberately excluding controller actions."""

        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source.node_id,
            "target_node_id": self.target.node_id,
            "source_milestone_index": self.source.milestone_index,
            "target_milestone_index": self.target.milestone_index,
            "start_action_offset": self.start_action_offset,
            "end_action_offset": self.end_action_offset,
            "action_count": len(self.actions),
        }


@dataclass(frozen=True, slots=True)
class SkillGraphAudit:
    """Payload-free accounting for one normalized self-generated replay."""

    protocol: str
    replay_id: str
    replay_action_count: int
    first_hit_count: int
    edge_count: int
    inserted_split_boundaries: int
    source_milestone_index: int
    target_milestone_index: int
    nodes: tuple[ConsecutiveSkillNode, ...]
    edges: tuple[ConsecutiveSkillEdge[object], ...]

    def as_public_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "replay_id": self.replay_id,
            "replay_action_count": self.replay_action_count,
            "first_hit_count": self.first_hit_count,
            "edge_count": self.edge_count,
            "inserted_split_boundaries": self.inserted_split_boundaries,
            "source_milestone_index": self.source_milestone_index,
            "target_milestone_index": self.target_milestone_index,
            "nodes": [node.public_dict() for node in self.nodes],
            "edges": [edge.public_dict() for edge in self.edges],
        }


@dataclass(frozen=True, slots=True)
class NormalizedSkillGraph(Generic[ActionT]):
    """Replay-local nodes and strictly consecutive, action-bearing skill edges."""

    replay_id: str
    nodes: tuple[ConsecutiveSkillNode, ...]
    edges: tuple[ConsecutiveSkillEdge[ActionT], ...]
    audit: SkillGraphAudit

    def public_audit(self) -> dict[str, object]:
        return self.audit.as_public_dict()


def _node_id(replay_id: str, first_hit: ObservedMilestoneFirstHit) -> str:
    identity = {
        "protocol": SKILL_GRAPH_PROTOCOL,
        "replay_id": replay_id,
        "milestone_id": first_hit.milestone_id,
        "milestone_index": first_hit.milestone_index,
        "action_offset": first_hit.action_offset,
        "state_identity": first_hit.state_identity.public_dict(),
        "verification_id": first_hit.verification_id,
    }
    return hashlib.sha256(_canonical_json(identity)).hexdigest()


def _edge_id(
    replay_id: str,
    source: ConsecutiveSkillNode,
    target: ConsecutiveSkillNode,
) -> str:
    identity = {
        "protocol": SKILL_GRAPH_PROTOCOL,
        "replay_id": replay_id,
        "source_node_id": source.node_id,
        "target_node_id": target.node_id,
        "start_action_offset": source.action_offset,
        "end_action_offset": target.action_offset,
    }
    return hashlib.sha256(_canonical_json(identity)).hexdigest()


def normalize_first_hit_replay(
    actions: Sequence[ActionT],
    first_hits: Sequence[ObservedMilestoneFirstHit],
    *,
    replay_id: str,
) -> NormalizedSkillGraph[ActionT]:
    """Split a verified replay into exact, strictly consecutive skill edges.

    The caller must provide every milestone first hit from the replay itself.
    Missing intermediate first hits are rejected rather than filled with a node
    from another worker that merely shares the same milestone ordinal.
    """

    _require_identifier(replay_id, "Replay identifier")
    replay_actions = tuple(actions)
    observed_first_hits = tuple(first_hits)
    if not replay_actions:
        raise ValueError("Skill-graph normalization requires replay actions")
    if len(observed_first_hits) < 2:
        raise ValueError("Skill-graph normalization requires at least two first hits")
    if any(not isinstance(hit, ObservedMilestoneFirstHit) for hit in observed_first_hits):
        raise ValueError("Skill-graph nodes require observed first hits with state identities")

    offsets = [hit.action_offset for hit in observed_first_hits]
    indices = [hit.milestone_index for hit in observed_first_hits]
    if offsets[0] != 0 or offsets[-1] != len(replay_actions):
        raise ValueError("First-hit boundaries must cover the complete replay")
    if any(current >= following for current, following in zip(offsets, offsets[1:], strict=False)):
        raise ValueError("First-hit action offsets must be strictly increasing")
    if any(current >= following for current, following in zip(indices, indices[1:], strict=False)):
        raise ValueError("First-hit milestone indices must be strictly increasing")
    index_pairs = zip(indices, indices[1:], strict=False)
    if any(following != current + 1 for current, following in index_pairs):
        raise ValueError("Every intermediate milestone needs its own replay-local first hit")
    milestone_ids = [hit.milestone_id for hit in observed_first_hits]
    if len(set(milestone_ids)) != len(milestone_ids):
        raise ValueError("Replay-local milestone identifiers must be unique")
    concrete_states = [hit.state_identity for hit in observed_first_hits]
    if len(set(concrete_states)) != len(concrete_states):
        raise ValueError("Distinct milestones cannot reuse one concrete stable-state identity")

    nodes = tuple(
        ConsecutiveSkillNode(
            node_id=_node_id(replay_id, hit),
            milestone_id=hit.milestone_id,
            milestone_index=hit.milestone_index,
            action_offset=hit.action_offset,
            state_identity=hit.state_identity,
            verification_id=hit.verification_id,
        )
        for hit in observed_first_hits
    )
    edges = tuple(
        ConsecutiveSkillEdge(
            edge_id=_edge_id(replay_id, source, target),
            source=source,
            target=target,
            start_action_offset=source.action_offset,
            end_action_offset=target.action_offset,
            actions=replay_actions[source.action_offset : target.action_offset],
        )
        for source, target in zip(nodes, nodes[1:], strict=False)
    )
    audit = SkillGraphAudit(
        protocol=SKILL_GRAPH_PROTOCOL,
        replay_id=replay_id,
        replay_action_count=len(replay_actions),
        first_hit_count=len(observed_first_hits),
        edge_count=len(edges),
        inserted_split_boundaries=max(0, len(observed_first_hits) - 2),
        source_milestone_index=observed_first_hits[0].milestone_index,
        target_milestone_index=observed_first_hits[-1].milestone_index,
        nodes=nodes,
        edges=tuple(edges),
    )
    return NormalizedSkillGraph(replay_id=replay_id, nodes=nodes, edges=edges, audit=audit)
