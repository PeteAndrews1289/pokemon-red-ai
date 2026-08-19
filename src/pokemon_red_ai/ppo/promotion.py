"""Candidate verification, admission, and warm-start weight transfer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    FrozenSnapshot,
)
from pokemon_red_ai.expedition import (
    MilestoneProgress,
)
from pokemon_red_ai.ppo.artifacts import (
    _atomic_gzip_json,
    _atomic_json,
    _read_gzip_json,
    _sha256_file,
)
from pokemon_red_ai.ppo.constants import ACTION_HISTORY_LENGTH, torch
from pokemon_red_ai.ppo.curriculum import (
    _load_curriculum_entry,
    _load_curriculum_manifest,
    _progress_from_value,
)
from pokemon_red_ai.ppo.distillation import _load_action, _replay_sequence


def verify_promotion_candidate(
    rom_path: Path,
    curriculum_directory: Path,
    candidate_path: Path,
    *,
    replay_passes: int,
    cancellation_check: Callable[[], str | None] | None = None,
) -> dict[str, Any]:
    candidate = _read_gzip_json(candidate_path)
    manifest = _load_curriculum_manifest(curriculum_directory)
    parent_metadata = next(
        (
            value
            for value in manifest["entries"]
            if value["entry_id"] == candidate["parent_entry_id"]
        ),
        None,
    )
    if parent_metadata is None:
        raise ValueError("PPO candidate parent is not in the curriculum")
    parent = _load_curriculum_entry(curriculum_directory, parent_metadata)
    parent_progress = _progress_from_value(parent["progress"])
    expected_progress = _progress_from_value(candidate["progress"])
    actions = [int(value) for value in candidate["actions"]]
    if not actions or any(not 0 <= value < len(BLIND_ACTIONS) for value in actions):
        raise ValueError("PPO promotion candidate actions are invalid")

    def matches(result: tuple[FrozenSnapshot, MilestoneProgress, dict[str, Any], str]) -> bool:
        snapshot, progress, summary, screen_sha256 = result
        return (
            snapshot.sha256 == candidate["terminal_snapshot_sha256"]
            and screen_sha256 == candidate["terminal_screen_sha256"]
            and progress == expected_progress
            and summary == candidate["terminal_referee_summary"]
        )

    parent_snapshot = FrozenSnapshot.from_checkpoint_dict(parent["snapshot"])
    if not matches(
        _replay_sequence(
            rom_path,
            parent_snapshot,
            actions,
            parent_progress,
            cancellation_check=cancellation_check,
        )
    ):
        raise ValueError("PPO candidate failed exact parent-edge replay")
    roots = [item for item in manifest["entries"] if int(item["milestone_index"]) == 0]
    if len(roots) != 1:
        raise ValueError("PPO curriculum has no unique power-on root")
    root = _load_curriculum_entry(curriculum_directory, roots[0])
    root_snapshot = FrozenSnapshot.from_checkpoint_dict(root["snapshot"])
    lineage: list[BlindAction] = [_load_action(value) for value in parent["lineage_actions"]]
    if any(
        action.hold_frames != ACTION_HOLD_FRAMES or action.release_frames != ACTION_RELEASE_FRAMES
        for action in lineage
    ):
        raise ValueError("PPO curriculum lineage uses a non-canonical action cadence")
    lineage_indices = [BLIND_ACTIONS.index(action.button) for action in lineage]
    full_actions = [*lineage_indices, *actions]
    root_progress = _progress_from_value(root["progress"])
    for _ in range(replay_passes):
        if not matches(
            _replay_sequence(
                rom_path,
                root_snapshot,
                full_actions,
                root_progress,
                cancellation_check=cancellation_check,
            )
        ):
            raise ValueError("PPO candidate failed fresh power-on replay")
    return {
        "candidate": candidate,
        "parent": parent,
        "full_actions": full_actions,
        "edge_replays": 1,
        "power_on_replays": replay_passes,
    }


def admit_verified_candidate(
    curriculum_directory: Path,
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = verification["candidate"]
    progress = _progress_from_value(candidate["progress"])
    manifest = _load_curriculum_manifest(curriculum_directory)
    if progress.index <= int(manifest["best_milestone"]["index"]):
        return manifest
    entry_id = str(candidate["candidate_id"])
    payload = {
        "schema_version": 1,
        "entry_id": entry_id,
        "source_cell_id": None,
        "progress": progress.public_dict(),
        "snapshot": candidate["terminal_snapshot"],
        "lineage_actions": [
            BlindAction(
                BLIND_ACTIONS[index], ACTION_HOLD_FRAMES, ACTION_RELEASE_FRAMES
            ).public_dict()
            for index in verification["full_actions"]
        ],
    }
    path = curriculum_directory / "entries" / f"{entry_id}.json.gz"
    _atomic_gzip_json(path, payload)
    manifest["entries"].append(
        {
            "entry_id": entry_id,
            "file": f"entries/{path.name}",
            "file_sha256": _sha256_file(path),
            "milestone_id": progress.key,
            "milestone_index": progress.index,
            "milestone_label": progress.label,
            "map_id": candidate["terminal_referee_summary"].get("map_id"),
            "depth_actions": len(verification["full_actions"]),
            "source": "ppo_verified_promotion",
        }
    )
    manifest["best_milestone"] = progress.public_dict()
    manifest["verified_promotions"] = int(manifest.get("verified_promotions", 0)) + 1
    manifest["updated_at"] = datetime.now(UTC).isoformat()
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _remap_warm_start_lstm_input(destination: Any, source: Any) -> None:
    """Put the one-action seed weights in Version 4's newest-action history slot."""

    pixel_features = 256
    action_features = len(BLIND_ACTIONS)
    expected_source = pixel_features + action_features
    expected_destination = pixel_features + ACTION_HISTORY_LENGTH * action_features
    if source.shape[1] != expected_source or destination.shape[1] < expected_destination:
        raise ValueError("Frontier learner LSTM input is incompatible with PPO Version 4")
    destination.zero_()
    destination[:, :pixel_features].copy_(source[:, :pixel_features])
    newest_action_start = pixel_features + (ACTION_HISTORY_LENGTH - 1) * action_features
    destination[:, newest_action_start : newest_action_start + action_features].copy_(
        source[:, pixel_features:]
    )


def _warm_start(
    model: Any, learner_path: Path, *, privileged: bool, assisted: bool
) -> dict[str, Any]:
    payload = torch.load(learner_path, map_location="cpu", weights_only=True)
    source = payload.get("model", payload)
    encoder_state = {
        key.removeprefix("encoder."): value
        for key, value in source.items()
        if key.startswith("encoder.")
    }
    extractors = {
        id(value): value
        for value in (
            model.policy.features_extractor,
            model.policy.pi_features_extractor,
            model.policy.vf_features_extractor,
        )
        if hasattr(value, "pixel_encoder")
    }
    for extractor in extractors.values():
        extractor.pixel_encoder.load_state_dict(encoder_state, strict=True)
    actor = model.policy.lstm_actor
    actor_state = actor.state_dict()
    source_recurrent = {
        key.removeprefix("recurrent."): value
        for key, value in source.items()
        if key.startswith("recurrent.")
    }
    for key, value in source_recurrent.items():
        if key == "weight_ih_l0" and actor_state[key].shape != value.shape:
            _remap_warm_start_lstm_input(actor_state[key], value)
        else:
            actor_state[key].copy_(value)
    actor.load_state_dict(actor_state)
    model.policy.action_net.load_state_dict(
        {
            "weight": source["policy_head.weight"],
            "bias": source["policy_head.bias"],
        }
    )
    return {
        "seed_file_sha256": _sha256_file(learner_path),
        "seed_updates": int(payload.get("updates", 0)),
        "seed_promotions": int(payload.get("promotions_learned", 0)),
        "privileged_actor": privileged,
        "privileged_lstm_columns_initialized_to_zero": privileged,
        "older_action_history_lstm_columns_initialized_to_zero": True,
        "seed_previous_action_mapped_to_newest_history_slot": True,
        "assisted_memory_and_goal_columns_initialized_to_zero": assisted,
    }
