"""Replay signatures, distillation datasets, and self-imitation training."""

from __future__ import annotations

import hashlib
import os
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pokemon_red_ai.apprentice_data import preprocess_apprentice_frame
from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    FrozenSnapshot,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    MilestoneProgress,
    milestone_progress_for_state,
    referee_summary_for_state,
)
from pokemon_red_ai.ppo.artifacts import _canonical_json, _sha256_file
from pokemon_red_ai.ppo.constants import ACTION_HISTORY_LENGTH, torch
from pokemon_red_ai.ppo.curriculum import (
    _load_curriculum_entry,
    _load_curriculum_manifest,
    _progress_from_value,
)
from pokemon_red_ai.ppo.observations import _action_history, _execute_action
from pokemon_red_ai.ppo.telemetry import (
    CompositionReplayRejected,
    V9PracticeCancelled,
    _check_v9_practice_cancellation,
)
from pokemon_red_ai.self_taught import (
    SELF_GENERATED_COMPOSITION_PROTOCOL,
    SELF_GENERATED_REPLAY_SHARD_PROTOCOL,
)
from pokemon_red_ai.skill_graph import (
    ObservedMilestoneFirstHit,
    StableStateIdentity,
    normalize_first_hit_replay,
)
from pokemon_red_ai.state import (
    MAX_BAG_ITEMS,
    PARTY_LENGTH,
    PARTY_MON_STRUCT_LENGTH,
    PokemonRedState,
    PokemonRedStateReader,
    RamAddress,
)
from pokemon_red_ai.trajectory_distillation import (
    DistillationConfig,
    ReplayEvidence,
    VerifiedSelfTrajectory,
    distill_self_generated_trajectory,
)


def _load_action(value: Mapping[str, Any]) -> BlindAction:
    return BlindAction(
        str(value["button"]), int(value["hold_frames"]), int(value["release_frames"])
    )


def _replay_sequence(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
    *,
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[FrozenSnapshot, MilestoneProgress, dict[str, Any], str]:
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        for action_index in actions:
            _check_v9_practice_cancellation(cancellation_check)
            if not _execute_action(emulator, int(action_index)):
                raise RuntimeError("PPO promotion replay emulator stopped")
        state = PokemonRedStateReader(emulator).read()
        progress = milestone_progress_for_state(state, inherited=inherited)
        snapshot = FrozenSnapshot.freeze(emulator.save_state())
        return (
            snapshot,
            progress,
            referee_summary_for_state(state, progress),
            emulator.screen_sha256(),
        )


def _lineage_action_indices(entry: Mapping[str, Any]) -> list[int]:
    actions = [_load_action(value) for value in entry.get("lineage_actions", [])]
    if any(
        action.hold_frames != ACTION_HOLD_FRAMES or action.release_frames != ACTION_RELEASE_FRAMES
        for action in actions
    ):
        raise ValueError("PPO curriculum lineage uses a non-canonical action cadence")
    return [BLIND_ACTIONS.index(action.button) for action in actions]


def _nearest_verified_lineage_prefix(
    curriculum_directory: Path,
    full_actions: list[int],
    *,
    target_index: int,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Find the deepest admitted state on the exact self-generated action lineage."""

    manifest = _load_curriculum_manifest(curriculum_directory)
    matches: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for metadata in manifest["entries"]:
        index = int(metadata["milestone_index"])
        if index >= target_index:
            continue
        entry = _load_curriculum_entry(curriculum_directory, metadata)
        lineage = _lineage_action_indices(entry)
        if len(lineage) <= len(full_actions) and full_actions[: len(lineage)] == lineage:
            matches.append((len(lineage), index, dict(metadata), entry))
    if not matches:
        raise ValueError("Verified candidate has no admitted lineage prefix")
    length, _index, metadata, entry = max(matches, key=lambda value: (value[0], value[1]))
    return metadata, entry, length


def _stable_semantic_state_signature(
    emulator: PokemonRedEmulator,
    state: PokemonRedState,
) -> tuple[Any, ...]:
    """Return gameplay state that survives an emulator save/load boundary.

    PyBoy's complete game-area hash is a derived emulator view that is not
    guaranteed to be identical immediately across ``load_state``. Keep that stricter hash in the
    distillation oracle, whose candidates all replay from the same snapshot, but
    do not use it to compare a live composition with a separately loaded target
    snapshot.  The processed visual hash and all gameplay RAM fields remain exact.
    """

    frame = preprocess_apprentice_frame(emulator.screen_rgb())
    visual = hashlib.blake2b(frame.tobytes(), digest_size=16).digest()
    party_blob = bytes(
        emulator.read_u8(int(RamAddress.PARTY_COUNT) + offset)
        for offset in range(
            int(RamAddress.PARTY_MONS)
            - int(RamAddress.PARTY_COUNT)
            + PARTY_LENGTH * PARTY_MON_STRUCT_LENGTH
        )
    )
    bag_blob = bytes(
        emulator.read_u8(int(RamAddress.NUM_BAG_ITEMS) + offset)
        for offset in range(1 + MAX_BAG_ITEMS * 2)
    )
    money_blob = bytes(emulator.read_u8(0xD347 + offset) for offset in range(3))
    status_blob = bytes(emulator.read_u8(0xD730 + offset) for offset in range(7))
    return (
        state.game_started,
        state.map_id,
        state.player_x,
        state.player_y,
        state.battle_state,
        state.party_count,
        state.party_species,
        state.party_levels,
        state.party_moves,
        state.party_experience,
        state.party_hp,
        state.party_max_hp,
        state.badge_bits,
        state.pokedex_owned,
        state.pokedex_seen,
        state.event_flags,
        state.bag_item_ids,
        state.got_pokedex,
        state.enemy_hp,
        state.enemy_max_hp,
        state.viridian_mart_script,
        party_blob,
        bag_blob,
        money_blob,
        status_blob,
        visual,
    )


@dataclass(frozen=True, slots=True)
class _V9FirstHit:
    observed: ObservedMilestoneFirstHit
    progress: MilestoneProgress
    snapshot: FrozenSnapshot
    referee_summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _PreparedV9Skills:
    skills: tuple[dict[str, Any], ...]
    graph: Any
    hits: tuple[_V9FirstHit, ...]
    source_entry_id: str
    final_entry_id: str
    full_actions: tuple[int, ...]
    source_prefix_length: int


def _v9_stable_state_sha256(
    emulator: PokemonRedEmulator,
    state: PokemonRedState,
) -> str:
    signature = _stable_semantic_state_signature(emulator, state)
    return hashlib.sha256(repr(signature).encode("utf-8")).hexdigest()


def _collect_v9_first_hit_graph(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
    target: MilestoneProgress,
    *,
    replay_id: str,
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[Any, tuple[_V9FirstHit, ...]]:
    """Replay one verified discovery and capture every concrete adjacent milestone edge."""

    hits: list[_V9FirstHit] = []
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        reader = PokemonRedStateReader(emulator)

        def capture(progress: MilestoneProgress, offset: int) -> None:
            state = reader.read()
            snapshot = FrozenSnapshot.freeze(emulator.save_state())
            stable = _v9_stable_state_sha256(emulator, state)
            verification_id = hashlib.sha256(
                f"{replay_id}:{progress.index}:{offset}:{snapshot.sha256}:{stable}".encode()
            ).hexdigest()
            hits.append(
                _V9FirstHit(
                    observed=ObservedMilestoneFirstHit(
                        milestone_id=progress.key,
                        milestone_index=progress.index,
                        action_offset=offset,
                        state_identity=StableStateIdentity(
                            stable_state_sha256=stable,
                            snapshot_sha256=snapshot.sha256,
                        ),
                        verification_id=verification_id,
                    ),
                    progress=progress,
                    snapshot=snapshot,
                    referee_summary=referee_summary_for_state(state, progress),
                )
            )

        current = milestone_progress_for_state(reader.read(), inherited=inherited)
        capture(current, 0)
        for offset, action in enumerate(actions, start=1):
            _check_v9_practice_cancellation(cancellation_check)
            if not _execute_action(emulator, action):
                raise RuntimeError("V9 first-hit replay emulator stopped")
            progress = milestone_progress_for_state(reader.read(), inherited=current)
            if progress.index > current.index:
                if progress.index != current.index + 1:
                    raise ValueError("V9 replay skipped an unobserved milestone boundary")
                current = progress
                capture(current, offset)
        if current.index != target.index or hits[-1].observed.action_offset != len(actions):
            raise ValueError("V9 verified replay did not terminate on its target first hit")
    graph = normalize_first_hit_replay(
        actions,
        tuple(hit.observed for hit in hits),
        replay_id=replay_id,
    )
    return graph, tuple(hits)


def _distillation_state_signature(
    emulator: PokemonRedEmulator,
    state: PokemonRedState,
    progress: MilestoneProgress,
) -> tuple[Any, ...]:
    return (
        *_stable_semantic_state_signature(emulator, state),
        emulator.game_area_sha256(),
        progress.index,
    )


def _composition_state_signature(
    emulator: PokemonRedEmulator,
    state: PokemonRedState,
    progress: MilestoneProgress,
) -> tuple[Any, ...]:
    """Fail-closed endpoint identity for comparisons across save/load boundaries."""

    return (*_stable_semantic_state_signature(emulator, state), progress.index)


def _collect_distillation_signatures(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
    *,
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[tuple[Any, ...], ...]:
    signatures: list[tuple[Any, ...]] = []
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        reader = PokemonRedStateReader(emulator)
        state = reader.read()
        progress = milestone_progress_for_state(state, inherited=inherited)
        signatures.append(_distillation_state_signature(emulator, state, progress))
        for action in actions:
            _check_v9_practice_cancellation(cancellation_check)
            if not _execute_action(emulator, action):
                raise RuntimeError("Trajectory distillation replay emulator stopped")
            state = reader.read()
            progress = milestone_progress_for_state(state, inherited=inherited)
            signatures.append(_distillation_state_signature(emulator, state, progress))
    return tuple(signatures)


def _replay_distillation_terminal_signature(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: tuple[int, ...],
    inherited: MilestoneProgress,
    *,
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[Any, ...]:
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        for action in actions:
            _check_v9_practice_cancellation(cancellation_check)
            if not _execute_action(emulator, action):
                raise RuntimeError("Trajectory distillation replay emulator stopped")
        state = PokemonRedStateReader(emulator).read()
        progress = milestone_progress_for_state(state, inherited=inherited)
        return _distillation_state_signature(emulator, state, progress)


def _distill_verified_actions(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    inherited: MilestoneProgress,
    target: MilestoneProgress,
    *,
    verification_id: str,
    successful_replays: int,
    max_attempts: int,
    cancellation_check: Callable[[], str | None] | None = None,
) -> Any:
    """Shorten an agent-generated edge using only replayed outcome evidence."""

    signatures = _collect_distillation_signatures(
        rom_path,
        start_snapshot,
        actions,
        inherited,
        cancellation_check=cancellation_check,
    )
    protected_outcome = signatures[-1]

    def oracle(candidate: tuple[int, ...]) -> bool:
        try:
            signature = _replay_distillation_terminal_signature(
                rom_path,
                start_snapshot,
                candidate,
                inherited,
                cancellation_check=cancellation_check,
            )
        except V9PracticeCancelled:
            raise
        except RuntimeError:
            return False
        return signature == protected_outcome and int(signature[-1]) >= target.index

    return distill_self_generated_trajectory(
        VerifiedSelfTrajectory(
            actions=tuple(actions),
            state_signatures=signatures,
            evidence=ReplayEvidence(
                verification_id=verification_id,
                successful_replays=successful_replays,
            ),
        ),
        oracle,
        config=DistillationConfig(
            max_loop_attempts=max_attempts // 2,
            max_chunk_attempts=max_attempts - max_attempts // 2,
        ),
    )


def _collect_v8_student_dataset(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    *,
    compressed_to_original: tuple[int, ...],
    cancellation_check: Callable[[], str | None] | None = None,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Build a recurrent Student sequence and a three-frame self-observed goal clip."""

    if not actions:
        raise ValueError("V8 Student dataset requires a non-empty distilled edge")
    pixels: list[np.ndarray] = []
    histories: list[np.ndarray] = []
    frames: list[np.ndarray] = []
    recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        current = preprocess_apprentice_frame(emulator.screen_rgb())
        previous = current
        frames.append(current)
        for action_index in actions:
            _check_v9_practice_cancellation(cancellation_check)
            pixels.append(np.stack((previous, current)))
            histories.append(_action_history(recent))
            if not _execute_action(emulator, int(action_index)):
                raise RuntimeError("V8 Student replay emulator stopped")
            recent.append(int(action_index))
            previous = current
            current = preprocess_apprentice_frame(emulator.screen_rgb())
            frames.append(current)
    target_frames = frames[-3:]
    while len(target_frames) < 3:
        target_frames.insert(0, target_frames[0])
    target_clip = np.stack(target_frames).astype(np.uint8, copy=False)
    # Distillation already proved that every retained action is necessary to the
    # accepted replay. Give those actions equal authority instead of importing
    # PPO's future-return discount into supervised sequence imitation.
    weights = np.ones(len(actions), dtype=np.float32)
    return (
        {
            "pixels": np.stack(pixels).astype(np.uint8, copy=False),
            "action_history": np.stack(histories).astype(np.float32, copy=False),
            "target_pixels": target_clip,
            "actions": np.asarray(actions, dtype=np.int64),
            "weights": weights,
            "episode_starts": np.asarray([True, *([False] * (len(actions) - 1))], dtype=np.bool_),
            "compressed_to_original": np.asarray(compressed_to_original, dtype=np.int64),
        },
        target_clip,
    )


def _v8_composition_fingerprint(chain: list[Mapping[str, Any]]) -> str:
    """Name one exact ordered chain and every artifact that supplies its actions."""

    if len(chain) < 2:
        raise ValueError("V8 composition replay requires at least two skills")
    identity = {
        "protocol": SELF_GENERATED_COMPOSITION_PROTOCOL,
        "skills": [
            {
                "skill_id": str(skill["skill_id"]),
                "source_entry_id": str(skill["source_entry_id"]),
                "target_entry_id": str(skill["target_entry_id"]),
                "dataset_sha256": str(skill["dataset_sha256"]),
                "distillation_audit_sha256": str(skill["distillation_audit_sha256"]),
            }
            for skill in chain
        ],
    }
    return hashlib.sha256(_canonical_json(identity)).hexdigest()


def _curriculum_snapshot_signature(
    rom_path: Path,
    entry: Mapping[str, Any],
) -> tuple[Any, ...]:
    inherited = _progress_from_value(entry["progress"])
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(FrozenSnapshot.from_checkpoint_dict(entry["snapshot"]).thaw())
        state = PokemonRedStateReader(emulator).read()
        progress = milestone_progress_for_state(state, inherited=inherited)
        return _composition_state_signature(emulator, state, progress)


def _v8_composition_training_weights(action_count: int) -> np.ndarray:
    """Keep both sides of long goal switches visible to normalized BC loss."""

    if action_count < 1:
        raise ValueError("V8 composition weights require at least one action")
    return np.ones(action_count, dtype=np.float32)


def _collect_v8_composition_dataset(
    rom_path: Path,
    curriculum_directory: Path,
    chain: list[Mapping[str, Any]],
    sources: Mapping[str, tuple[np.ndarray, np.ndarray]],
    *,
    burn_in: int,
    train_length: int,
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    """Stream-verify a chain and retain only bounded goal-switch excerpts.

    Every action comes from an individually replay-verified self-generated skill.
    Concatenation is admitted only when one uninterrupted replay from the exact
    power-on snapshot reaches the protected terminal state of every edge. Pixels
    are retained only around internal goal switches; full lineage remains bound by
    the source hashes and replay audit without quadratic prefix materialization.
    """

    if len(chain) < 2:
        raise ValueError("V8 composition replay requires at least two skills")
    if burn_in < 0 or train_length < 2:
        raise ValueError("V8 composition excerpts require valid recurrent context")
    if any(
        str(left["target_entry_id"]) != str(right["source_entry_id"])
        for left, right in zip(chain, chain[1:], strict=False)
    ):
        raise ValueError("V8 composition skills are not a continuous chain")
    manifest = _load_curriculum_manifest(curriculum_directory)
    metadata_by_id = {str(item["entry_id"]): item for item in manifest["entries"]}

    def load_entry(entry_id: str) -> tuple[Mapping[str, Any], dict[str, Any]]:
        metadata = metadata_by_id.get(entry_id)
        if metadata is None:
            raise ValueError("V8 composition curriculum entry is missing")
        return metadata, _load_curriculum_entry(curriculum_directory, metadata)

    root_id = str(chain[0]["source_entry_id"])
    root_metadata, root = load_entry(root_id)
    if int(root_metadata["milestone_index"]) != 0:
        raise ValueError("V8 composition replay must begin at the exact power-on entry")
    inherited = _progress_from_value(root["progress"])
    expected: list[tuple[Mapping[str, Any], dict[str, Any], tuple[Any, ...]]] = []
    ordered_actions: list[np.ndarray] = []
    target_clips: list[np.ndarray] = []
    for skill in chain:
        skill_id = str(skill["skill_id"])
        source = sources.get(skill_id)
        if source is None:
            raise ValueError("V8 composition source dataset is missing")
        actions, target_clip = source
        if actions.ndim != 1 or len(actions) != int(skill["action_count"]):
            raise ValueError("V8 composition source actions disagree with the skill ledger")
        if target_clip.shape != (3, 72, 80):
            raise ValueError("V8 composition source needs one verified three-frame goal clip")
        metadata, entry = load_entry(str(skill["target_entry_id"]))
        expected.append((metadata, entry, _curriculum_snapshot_signature(rom_path, entry)))
        ordered_actions.append(actions.astype(np.int64, copy=False))
        target_clips.append(target_clip.astype(np.uint8, copy=False))

    full_offsets = [0]
    for actions in ordered_actions:
        full_offsets.append(full_offsets[-1] + len(actions))
    left_train = max(1, train_length // 2)
    right_train = max(1, train_length - left_train)
    before = burn_in + left_train
    after = right_train
    excerpt_ranges = [
        (
            max(full_offsets[index - 1], boundary - before),
            min(full_offsets[index + 1], boundary + after),
        )
        for index, boundary in enumerate(full_offsets[1:-1], start=1)
    ]
    excerpt_pixels: list[list[np.ndarray]] = [[] for _ in excerpt_ranges]
    excerpt_histories: list[list[np.ndarray]] = [[] for _ in excerpt_ranges]
    excerpt_actions: list[list[int]] = [[] for _ in excerpt_ranges]
    excerpt_goals: list[list[int]] = [[] for _ in excerpt_ranges]
    boundaries: list[dict[str, Any]] = []
    recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
    global_action = 0
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(FrozenSnapshot.from_checkpoint_dict(root["snapshot"]).thaw())
        reader = PokemonRedStateReader(emulator)
        current = preprocess_apprentice_frame(emulator.screen_rgb())
        previous = current
        for goal_index, (skill, segment_actions, (metadata, target_entry, protected)) in enumerate(
            zip(
                chain,
                ordered_actions,
                expected,
                strict=True,
            )
        ):
            for raw_action in segment_actions:
                action = int(raw_action)
                for excerpt, (start, stop) in enumerate(excerpt_ranges):
                    if start <= global_action < stop:
                        excerpt_pixels[excerpt].append(np.stack((previous, current)))
                        excerpt_histories[excerpt].append(_action_history(recent))
                        excerpt_actions[excerpt].append(action)
                        excerpt_goals[excerpt].append(goal_index)
                if not _execute_action(emulator, action):
                    raise CompositionReplayRejected(
                        "V8 composition emulator stopped during continuous replay"
                    )
                recent.append(action)
                previous = current
                current = preprocess_apprentice_frame(emulator.screen_rgb())
                global_action += 1
            state = reader.read()
            progress = milestone_progress_for_state(state, inherited=inherited)
            observed = _composition_state_signature(emulator, state, progress)
            if observed[:-1] != protected[:-1] or progress.index < int(skill["target_index"]):
                raise CompositionReplayRejected(
                    "V8 compressed skills did not compose to a protected target state"
                )
            boundaries.append(
                {
                    "full_action_offset": global_action,
                    "skill_id": str(skill["skill_id"]),
                    "target_entry_id": str(skill["target_entry_id"]),
                    "target_entry_file_sha256": str(metadata["file_sha256"]),
                    "target_index": int(skill["target_index"]),
                    "observed_index": progress.index,
                    "semantic_signature_sha256": hashlib.sha256(
                        repr(observed[:-1]).encode("utf-8")
                    ).hexdigest(),
                }
            )
            inherited = _progress_from_value(target_entry["progress"])

    pixels = [np.stack(values).astype(np.uint8, copy=False) for values in excerpt_pixels]
    histories = [np.stack(values).astype(np.float32, copy=False) for values in excerpt_histories]
    actions = [np.asarray(values, dtype=np.int64) for values in excerpt_actions]
    goals = [np.asarray(values, dtype=np.int64) for values in excerpt_goals]
    excerpt_offsets = [0]
    training_switches: list[int] = []
    for excerpt, ((start, _stop), full_boundary) in enumerate(
        zip(excerpt_ranges, full_offsets[1:-1], strict=True)
    ):
        training_switches.append(excerpt_offsets[-1] + full_boundary - start)
        excerpt_offsets.append(excerpt_offsets[-1] + len(actions[excerpt]))
    count = excerpt_offsets[-1]
    episode_starts = np.zeros(count, dtype=np.bool_)
    episode_starts[np.asarray(excerpt_offsets[:-1], dtype=np.int64)] = True
    return (
        {
            "pixels": np.concatenate(pixels),
            "action_history": np.concatenate(histories),
            "target_pixels": np.stack(target_clips).astype(np.uint8, copy=False),
            "actions": np.concatenate(actions),
            "weights": _v8_composition_training_weights(count),
            "episode_starts": episode_starts,
            "goal_indices": np.concatenate(goals),
            "excerpt_offsets": np.asarray(excerpt_offsets, dtype=np.int64),
            "dataset_kind": np.asarray("composition"),
            "replay_protocol": np.asarray(SELF_GENERATED_COMPOSITION_PROTOCOL),
            "successful_replays": np.asarray(1, dtype=np.int64),
            "source_skill_ids": np.asarray([str(skill["skill_id"]) for skill in chain]),
            "goal_switch_offsets": np.asarray(training_switches, dtype=np.int64),
            "full_goal_switch_offsets": np.asarray(full_offsets[1:-1], dtype=np.int64),
            "full_action_count": np.asarray(full_offsets[-1], dtype=np.int64),
            "excerpt_full_ranges": np.asarray(excerpt_ranges, dtype=np.int64),
        },
        boundaries,
    )


def _collect_self_imitation_dataset(
    rom_path: Path,
    start_snapshot: FrozenSnapshot,
    actions: list[int],
    target_frame: np.ndarray,
) -> dict[str, np.ndarray]:
    """Replay the agent's own verified edge into exact visual/action training examples."""

    if not actions:
        raise ValueError("Self-imitation requires a non-empty verified edge")
    pixels: list[np.ndarray] = []
    histories: list[np.ndarray] = []
    recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
    with PokemonRedEmulator(rom_path) as emulator:
        emulator.load_state(start_snapshot.thaw())
        current = preprocess_apprentice_frame(emulator.screen_rgb())
        previous = current
        for action_index in actions:
            pixels.append(np.stack((previous, current)))
            histories.append(_action_history(recent))
            if not _execute_action(emulator, int(action_index)):
                raise RuntimeError("Self-imitation replay emulator stopped")
            recent.append(int(action_index))
            previous = current
            current = preprocess_apprentice_frame(emulator.screen_rgb())
    return {
        "pixels": np.stack(pixels).astype(np.uint8, copy=False),
        "action_history": np.stack(histories).astype(np.float32, copy=False),
        "target_pixels": target_frame[None, :, :].astype(np.uint8, copy=False),
        "actions": np.asarray(actions, dtype=np.int64),
    }


def _atomic_self_imitation_dataset(path: Path, dataset: Mapping[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.npz")
    with temporary.open("wb") as output:
        np.savez_compressed(output, **dataset)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _write_v8_replay_shards(
    run_directory: Path,
    *,
    skill_id: str,
    dataset: Mapping[str, np.ndarray],
    source_dataset_sha256: str,
    max_examples: int,
    burn_in: int,
    cancellation_check: Callable[[], str | None] | None = None,
) -> list[dict[str, Any]]:
    """Seal bounded training chunks while the verified full dataset is in memory.

    The full artifact remains the immutable provenance source.  Later replay rounds
    open only one of these small hash-bound derivatives, never the monolithic NPZ.
    """

    skill_component = Path(skill_id)
    if (
        not skill_id
        or skill_component.is_absolute()
        or skill_component.name != skill_id
        or skill_id in {".", ".."}
        or max_examples < 1
        or burn_in < 0
    ):
        raise ValueError("V8 replay shards require a skill and positive example cap")
    if len(source_dataset_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in source_dataset_sha256
    ):
        raise ValueError("V8 replay shards require a sealed source dataset")
    required = {"pixels", "action_history", "target_pixels", "actions", "weights"}
    if missing := sorted(required.difference(dataset)):
        raise ValueError(f"V8 replay shard source is missing: {', '.join(missing)}")
    action_count = len(np.asarray(dataset["actions"]))
    if action_count < 1:
        raise ValueError("V8 replay shards require at least one source action")
    for key in ("pixels", "action_history", "weights"):
        if len(np.asarray(dataset[key])) != action_count:
            raise ValueError("V8 replay shard source arrays disagree on action count")

    shard_count = (action_count + max_examples - 1) // max_examples
    metadata: list[dict[str, Any]] = []
    for shard_index, train_start in enumerate(range(0, action_count, max_examples)):
        _check_v9_practice_cancellation(cancellation_check)
        context_start = max(0, train_start - burn_in)
        stop = min(action_count, train_start + max_examples)
        stored_count = stop - context_start
        train_count = stop - train_start
        relative = (
            Path("self-skills")
            / "replay"
            / skill_id
            / f"shard-{shard_index:06d}-of-{shard_count:06d}.npz"
        )
        path = run_directory / relative
        episode_starts = np.zeros(stored_count, dtype=np.bool_)
        episode_starts[0] = True
        payload: dict[str, np.ndarray] = {
            "pixels": np.asarray(dataset["pixels"])[context_start:stop],
            "action_history": np.asarray(dataset["action_history"])[context_start:stop],
            "target_pixels": np.asarray(dataset["target_pixels"]),
            "actions": np.asarray(dataset["actions"])[context_start:stop],
            "weights": np.asarray(dataset["weights"])[context_start:stop],
            "episode_starts": episode_starts,
            "replay_shard_protocol": np.asarray(SELF_GENERATED_REPLAY_SHARD_PROTOCOL),
            "source_dataset_sha256": np.asarray(source_dataset_sha256),
            "source_skill_id": np.asarray(skill_id),
            "source_action_count": np.asarray(action_count, dtype=np.int64),
            "source_action_offset": np.asarray(context_start, dtype=np.int64),
            "source_context_start": np.asarray(context_start, dtype=np.int64),
            "source_train_start": np.asarray(train_start, dtype=np.int64),
            "source_train_stop": np.asarray(stop, dtype=np.int64),
            "replay_train_offset": np.asarray(
                train_start - context_start,
                dtype=np.int64,
            ),
            "replay_shard_index": np.asarray(shard_index, dtype=np.int64),
            "replay_shard_count": np.asarray(shard_count, dtype=np.int64),
        }
        if "compressed_to_original" in dataset:
            payload["compressed_to_original"] = np.asarray(dataset["compressed_to_original"])[
                context_start:stop
            ]
        _atomic_self_imitation_dataset(path, payload)
        metadata.append(
            {
                "protocol": SELF_GENERATED_REPLAY_SHARD_PROTOCOL,
                "file": relative.as_posix(),
                "sha256": _sha256_file(path),
                "stored_bytes": path.stat().st_size,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "source_dataset_sha256": source_dataset_sha256,
                "source_action_count": action_count,
                "source_start": context_start,
                "source_context_start": context_start,
                "source_train_start": train_start,
                "source_stop": stop,
                "context_example_count": train_start - context_start,
                "train_example_count": train_count,
                "example_count": stored_count,
            }
        )
    if (
        len(metadata) != shard_count
        or metadata[-1]["source_stop"] != action_count
        or sum(int(item["train_example_count"]) for item in metadata) != action_count
    ):
        raise RuntimeError("V8 replay shard admission did not cover the verified source")
    return metadata


def _self_imitation_windows(length: int, width: int = 256) -> list[tuple[int, int]]:
    if length < 1:
        return []
    if length <= width:
        return [(0, length)]
    starts = np.linspace(0, length - width, num=min(8, max(2, length // width)), dtype=int)
    return [(int(start), min(length, int(start) + width)) for start in sorted(set(starts))]


def _train_self_imitation_policy(
    model: Any,
    datasets: list[Path],
    *,
    epochs: int,
    counterfactual_blank_weight: float = 0.0,
    counterfactual_margin: float = 0.0,
) -> dict[str, Any]:
    """Apply direct action likelihood updates on self-generated, replay-verified skills."""

    from sb3_contrib.common.recurrent.type_aliases import RNNStates

    if epochs < 1 or not datasets:
        raise ValueError("Self-imitation training requires data and positive epochs")
    if counterfactual_blank_weight < 0 or counterfactual_margin < 0:
        raise ValueError("Self-imitation counterfactual settings must be non-negative")
    losses: list[float] = []
    contrastive_losses: list[float] = []
    examples = 0
    updates = 0
    policy = model.policy
    policy.set_training_mode(True)
    for _epoch in range(epochs):
        for path in datasets:
            with np.load(path, allow_pickle=False) as data:
                actions = np.asarray(data["actions"], dtype=np.int64)
                pixels = np.asarray(data["pixels"], dtype=np.uint8)
                histories = np.asarray(data["action_history"], dtype=np.float32)
                target = np.asarray(data["target_pixels"], dtype=np.uint8)
            for begin, end in _self_imitation_windows(len(actions)):
                count = end - begin
                observations = {
                    "pixels": torch.as_tensor(pixels[begin:end], device=policy.device),
                    "action_history": torch.as_tensor(histories[begin:end], device=policy.device),
                    "target_pixels": torch.as_tensor(
                        np.repeat(target[None, ...], count, axis=0),
                        device=policy.device,
                    ),
                }
                action_tensor = torch.as_tensor(
                    actions[begin:end], dtype=torch.long, device=policy.device
                )
                episode_starts = torch.zeros(count, device=policy.device)
                episode_starts[0] = 1
                actor_shape = (
                    policy.lstm_actor.num_layers,
                    1,
                    policy.lstm_actor.hidden_size,
                )
                actor_zero = torch.zeros(actor_shape, device=policy.device)
                critic_lstm = policy.lstm_critic or policy.lstm_actor
                critic_shape = (
                    critic_lstm.num_layers,
                    1,
                    critic_lstm.hidden_size,
                )
                critic_zero = torch.zeros(critic_shape, device=policy.device)
                states = RNNStates(
                    pi=(actor_zero, actor_zero.clone()),
                    vf=(critic_zero, critic_zero.clone()),
                )
                _values, log_probability, _entropy = policy.evaluate_actions(
                    observations,
                    action_tensor,
                    states,
                    episode_starts,
                )
                behavior_loss = -log_probability.mean()
                contrastive_loss = torch.zeros((), device=policy.device)
                if counterfactual_blank_weight:
                    blank_observations = {
                        **observations,
                        "target_pixels": torch.zeros_like(observations["target_pixels"]),
                    }
                    blank_states = RNNStates(
                        pi=(torch.zeros_like(actor_zero), torch.zeros_like(actor_zero)),
                        vf=(torch.zeros_like(critic_zero), torch.zeros_like(critic_zero)),
                    )
                    _values, blank_log_probability, _entropy = policy.evaluate_actions(
                        blank_observations,
                        action_tensor,
                        blank_states,
                        episode_starts,
                    )
                    contrastive_loss = torch.relu(
                        counterfactual_margin - (log_probability - blank_log_probability)
                    ).mean()
                loss = behavior_loss + counterfactual_blank_weight * contrastive_loss
                policy.optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(policy.parameters(), model.max_grad_norm)
                policy.optimizer.step()
                losses.append(float(loss.detach().item()))
                contrastive_losses.append(float(contrastive_loss.detach().item()))
                examples += count
                updates += 1
    policy.set_training_mode(False)
    return {
        "updates": updates,
        "examples": examples,
        "mean_loss": sum(losses) / len(losses),
        "mean_contrastive_loss": sum(contrastive_losses) / len(contrastive_losses),
    }


def _hindsight_goal_log_probability_advantage(
    model: Any,
    datasets: Sequence[Path],
    *,
    maximum_datasets: int = 8,
    maximum_actions: int = 64,
) -> float:
    """Measure whether actions fit their future goal better than an all-zero goal."""

    from sb3_contrib.common.recurrent.type_aliases import RNNStates

    if maximum_datasets < 1 or maximum_actions < 1:
        raise ValueError("Hindsight goal diagnostic limits must be positive")
    policy = model.policy
    previous_mode = bool(policy.training)
    policy.set_training_mode(False)
    advantages: list[float] = []
    try:
        for path in list(datasets)[:maximum_datasets]:
            with np.load(path, allow_pickle=False) as data:
                count = min(maximum_actions, len(data["actions"]))
                if count < 1:
                    continue
                pixels = np.asarray(data["pixels"][:count], dtype=np.uint8)
                histories = np.asarray(data["action_history"][:count], dtype=np.float32)
                actions = np.asarray(data["actions"][:count], dtype=np.int64)
                target = np.asarray(data["target_pixels"], dtype=np.uint8)
            action_tensor = torch.as_tensor(actions, dtype=torch.long, device=policy.device)
            episode_starts = torch.zeros(count, device=policy.device)
            episode_starts[0] = 1
            actor_shape = (
                policy.lstm_actor.num_layers,
                1,
                policy.lstm_actor.hidden_size,
            )
            critic_lstm = policy.lstm_critic or policy.lstm_actor
            critic_shape = (
                critic_lstm.num_layers,
                1,
                critic_lstm.hidden_size,
            )

            def states(
                actor_state_shape: tuple[int, ...] = actor_shape,
                critic_state_shape: tuple[int, ...] = critic_shape,
            ) -> RNNStates:
                actor = torch.zeros(actor_state_shape, device=policy.device)
                critic = torch.zeros(critic_state_shape, device=policy.device)
                return RNNStates(
                    pi=(actor, actor.clone()),
                    vf=(critic, critic.clone()),
                )

            base = {
                "pixels": torch.as_tensor(pixels, device=policy.device),
                "action_history": torch.as_tensor(histories, device=policy.device),
            }
            actual = {
                **base,
                "target_pixels": torch.as_tensor(
                    np.repeat(target[None, ...], count, axis=0),
                    device=policy.device,
                ),
            }
            blank = {
                **base,
                "target_pixels": torch.zeros(
                    (count, *target.shape),
                    dtype=torch.uint8,
                    device=policy.device,
                ),
            }
            with torch.no_grad():
                _values, actual_log, _entropy = policy.evaluate_actions(
                    actual,
                    action_tensor,
                    states(),
                    episode_starts,
                )
                _values, blank_log, _entropy = policy.evaluate_actions(
                    blank,
                    action_tensor,
                    states(),
                    episode_starts,
                )
            advantages.append(float((actual_log - blank_log).mean().item()))
    finally:
        policy.set_training_mode(previous_mode)
    return float(np.mean(advantages)) if advantages else 0.0
