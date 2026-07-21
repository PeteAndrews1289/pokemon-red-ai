from __future__ import annotations

# Optional RL dependencies must be checked before importing the PPO module.
# ruff: noqa: E402
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

gym = pytest.importorskip("gymnasium")
pytest.importorskip("stable_baselines3")
pytest.importorskip("sb3_contrib")
torch = pytest.importorskip("torch")

import pokemon_red_ai.ppo_training as ppo_training_module
from pokemon_red_ai.blind import BLIND_ACTIONS
from pokemon_red_ai.milestones import MILESTONES
from pokemon_red_ai.ppo_training import (
    ACTION_HISTORY_LENGTH,
    GOAL_COUNT,
    MAP_CONTEXT_SIZE,
    MAP_MEMORY_FEATURES,
    MAP_MEMORY_SIZE,
    PPO_V8_PROTOCOL,
    PRIVILEGED_STATE_SIZE,
    SKILL_COUNT,
    EpisodeMapMemory,
    ParallelPpoConfig,
    PokemonPpoFeatures,
    PpoRunCallback,
    VisualStagnationTracker,
    _atomic_gzip_json,
    _checkpoint_curriculum_state,
    _checkpoint_self_skill_state,
    _copy_retained_ppo_policy,
    _ensure_run_manifest_identity,
    _hall_of_fame_stop_is_verified,
    _remaining_action_budget,
    _remap_warm_start_lstm_input,
    _render_dashboard,
    _resolve_checkpoint_artifact,
    _restore_curriculum_state,
    _restore_self_skill_state,
    _sha256_file,
    _snapshot_v7_denominator,
    _state_vector,
    _train_self_imitation_policy,
    _v8_composition_fingerprint,
    _v8_composition_training_weights,
    _validate_checkpoint_identity,
    _write_v8_replay_shards,
)
from pokemon_red_ai.self_taught import SelfTaughtSkillLibrary
from pokemon_red_ai.state import PokemonRedState
from pokemon_red_ai.student_training import (
    SelfGeneratedSkillDataset,
    SequenceTrainingConfig,
    make_recurrent_sequences,
)


def test_parallel_config_enforces_vector_batch_boundary() -> None:
    config = ParallelPpoConfig(environments=4, rollout_steps=64, batch_size=128)
    assert config.environments * config.rollout_steps == 256

    with pytest.raises(ValueError, match="must divide"):
        ParallelPpoConfig(environments=3, rollout_steps=64, batch_size=128)

    with pytest.raises(ValueError, match="competence"):
        ParallelPpoConfig(competence_window=1)

    with pytest.raises(ValueError, match="Self-taught"):
        ParallelPpoConfig(mode="self_taught")
    self_taught = ParallelPpoConfig(
        mode="self_taught", random_initialization=True, power_on_only=True
    )
    assert self_taught.consolidation is False
    v8 = ParallelPpoConfig(mode="self_taught_v8", random_initialization=True, power_on_only=True)
    assert v8.distillation_attempts == 32
    assert v8.frozen_exam_attempts == 1
    assert len(MILESTONES) * v8.competence_window * v8.frozen_exam_interval_actions < v8.max_actions
    with pytest.raises(ValueError, match="one deterministic frozen attempt"):
        ParallelPpoConfig(
            mode="self_taught_v8",
            random_initialization=True,
            power_on_only=True,
            frozen_exam_attempts=2,
        )


def test_v8_can_lock_a_path_free_hash_bound_v7_denominator(tmp_path: Path) -> None:
    run = tmp_path / "parallel-ppo-v7-denominator"
    run.mkdir()
    model = run / "ppo-latest.zip"
    model.write_bytes(b"frozen V7 model generation")
    model_hash = _sha256_file(model)
    (run / "manifest.json").write_text(
        json.dumps({"protocol": "parallel-recurrent-ppo-v7", "actor_mode": "self_taught"}),
        encoding="utf-8",
    )
    checkpoint = {
        "protocol": "parallel-recurrent-ppo-v7",
        "config": {"mode": "self_taught"},
        "model_file_sha256": model_hash,
        "total_actions": 7_000_000,
        "best_milestone": {"index": 8, "label": "Reached Viridian City"},
    }
    (run / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    (run / "status.json").write_text(
        json.dumps({"state": "running", "updated_at": "2026-07-21T18:00:00+00:00"}),
        encoding="utf-8",
    )

    snapshot = _snapshot_v7_denominator(run)

    assert snapshot["locked"] is True
    assert snapshot["run_id"] == run.name
    assert snapshot["total_actions"] == 7_000_000
    assert snapshot["best_index"] == 8
    assert snapshot["checkpoint_sha256"] == model_hash
    assert snapshot["source_state_at_lock"] == "running"
    assert snapshot["source_path_recorded"] is False
    assert str(tmp_path) not in json.dumps(snapshot)

    (run / "ppo-previous.zip").write_bytes(model.read_bytes())
    model.write_bytes(b"uncommitted next generation")
    assert _snapshot_v7_denominator(run)["checkpoint_sha256"] == model_hash

    (run / "ppo-previous.zip").write_bytes(b"also wrong")
    with pytest.raises(ValueError, match="rotated"):
        _snapshot_v7_denominator(run)


def test_denominator_rejects_non_v7_self_taught_run(tmp_path: Path) -> None:
    run = tmp_path / "wrong-denominator"
    run.mkdir()
    (run / "manifest.json").write_text(
        json.dumps({"protocol": PPO_V8_PROTOCOL, "actor_mode": "self_taught_v8"}),
        encoding="utf-8",
    )
    (run / "checkpoint.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Version-7 self-taught"):
        _snapshot_v7_denominator(run)


def test_v8_composition_fingerprint_binds_order_and_source_artifacts() -> None:
    first = {
        "skill_id": "first",
        "source_entry_id": "power-on",
        "target_entry_id": "outside",
        "dataset_sha256": "a" * 64,
        "distillation_audit_sha256": "b" * 64,
    }
    second = {
        "skill_id": "second",
        "source_entry_id": "outside",
        "target_entry_id": "route-one",
        "dataset_sha256": "c" * 64,
        "distillation_audit_sha256": "d" * 64,
    }

    fingerprint = _v8_composition_fingerprint([first, second])

    assert fingerprint == _v8_composition_fingerprint([dict(first), dict(second)])
    assert fingerprint != _v8_composition_fingerprint([second, first])
    changed = dict(second, dataset_sha256="e" * 64)
    assert fingerprint != _v8_composition_fingerprint([first, changed])


def test_v8_composition_weights_do_not_hide_actions_after_a_long_goal_switch() -> None:
    weights = _v8_composition_training_weights(20_000)

    assert weights.dtype == np.float32
    assert np.all(weights == 1)
    assert weights[10_000] == weights[9_999]


def test_v7_public_config_remains_compatible_with_pre_v8_checkpoint() -> None:
    config = ParallelPpoConfig(
        mode="self_taught",
        random_initialization=True,
        power_on_only=True,
    ).public_dict()

    assert not set(config).intersection(
        {
            "distillation_attempts",
            "student_replay_interval",
            "student_replay_epochs",
            "student_burn_in",
            "student_train_horizon",
            "student_learning_rate",
            "frozen_exam_interval_actions",
            "frozen_exam_attempts",
            "frozen_exam_action_multiplier",
        }
    )


def test_v8_checkpoint_identity_binds_source_and_rom() -> None:
    source = {"git_commit": "a" * 40, "worktree_dirty": False}
    rom = {"sha256": "b" * 64, "sha1": "c" * 40}
    checkpoint = {"source": source, "rom": rom}

    _validate_checkpoint_identity(checkpoint, source=source, rom=rom, required=True)
    with pytest.raises(ValueError, match="source identity"):
        _validate_checkpoint_identity(
            checkpoint,
            source={"git_commit": "d" * 40, "worktree_dirty": False},
            rom=rom,
            required=True,
        )
    with pytest.raises(ValueError, match="ROM identity"):
        _validate_checkpoint_identity(
            checkpoint,
            source=source,
            rom={"sha256": "e" * 64, "sha1": "c" * 40},
            required=True,
        )
    with pytest.raises(ValueError, match="no bound source"):
        _validate_checkpoint_identity({}, source=source, rom=rom, required=True)


def test_legacy_v7_manifest_backfills_rom_without_rewriting_source(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    original_source = {"git_commit": "a" * 40, "worktree_dirty": False}
    path.write_text(
        json.dumps({"protocol": "parallel-recurrent-ppo-v7", "source": original_source}),
        encoding="utf-8",
    )
    rom = {"sha256": "b" * 64, "sha1": "c" * 40}

    value = _ensure_run_manifest_identity(
        path,
        source={"git_commit": "d" * 40, "worktree_dirty": False},
        rom=rom,
    )

    assert value["source"] == original_source
    assert value["rom"] == rom


def test_retained_policy_copy_requires_clean_compatible_terminal_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    model = source / "ppo-latest.zip"
    model.write_bytes(b"verified policy")
    config = ParallelPpoConfig(mode="assisted")
    checkpoint = {
        "protocol": "parallel-recurrent-ppo-v5.2",
        "total_actions": 1234,
        "model_file_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "config": config.public_dict(),
    }
    (source / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    (source / "status.json").write_text(
        json.dumps(
            {
                "state": "finished",
                "stop_reason": "stop_requested",
                "total_actions": 1234,
                "best_milestone": {"index": 17, "key": "route", "label": "Route"},
            }
        ),
        encoding="utf-8",
    )
    (source / "manifest.json").write_text(json.dumps({"actor_mode": "assisted"}), encoding="utf-8")
    destination = tmp_path / "retained.zip"

    metadata = _copy_retained_ppo_policy(source, destination, config)

    assert destination.read_bytes() == model.read_bytes()
    assert metadata["optimizer_state_retained"] is True
    assert metadata["source_total_actions"] == 1234

    failed_status = json.loads((source / "status.json").read_text(encoding="utf-8"))
    failed_status["state"] = "running"
    (source / "status.json").write_text(json.dumps(failed_status), encoding="utf-8")
    with pytest.raises(ValueError, match="cleanly finished"):
        _copy_retained_ppo_policy(source, tmp_path / "rejected.zip", config)


def test_retained_policy_gets_a_fresh_budget_but_resume_does_not() -> None:
    assert _remaining_action_budget(8_192, 8_192, resume=False) == 8_192
    assert _remaining_action_budget(8_192, 4_096, resume=True) == 4_096


def test_self_taught_resume_rolls_live_ledger_back_to_model_checkpoint(
    tmp_path: Path,
) -> None:
    initial = SelfTaughtSkillLibrary.initialize(
        [{"entry_id": "root", "milestone_index": 0}],
        window_size=10,
        threshold=0.8,
    )
    (tmp_path / "self-skills.json").write_text(json.dumps(initial.public_dict()), encoding="utf-8")
    checkpoint = _checkpoint_self_skill_state(tmp_path)
    changed = initial.public_dict()
    changed["imitation_updates"] = 99
    (tmp_path / "self-skills.json").write_text(json.dumps(changed), encoding="utf-8")

    restored = _restore_self_skill_state(tmp_path, checkpoint)

    assert restored.imitation_updates == 0
    live = json.loads((tmp_path / "self-skills.json").read_text(encoding="utf-8"))
    assert live["imitation_updates"] == 0


def test_self_taught_resume_can_recover_previous_atomic_generation(
    tmp_path: Path,
) -> None:
    library = SelfTaughtSkillLibrary.initialize(
        [{"entry_id": "root", "milestone_index": 0}],
        window_size=10,
        threshold=0.8,
    )
    (tmp_path / "self-skills.json").write_text(json.dumps(library.public_dict()), encoding="utf-8")
    first_checkpoint = _checkpoint_self_skill_state(tmp_path)
    library.imitation_updates = 5
    (tmp_path / "self-skills.json").write_text(json.dumps(library.public_dict()), encoding="utf-8")
    _checkpoint_self_skill_state(tmp_path)

    restored = _restore_self_skill_state(tmp_path, first_checkpoint)

    assert restored.imitation_updates == 0
    assert (tmp_path / "self-skills.checkpoint.previous.json").is_file()


def test_recovered_previous_artifact_survives_a_second_interrupted_rotation(
    tmp_path: Path,
) -> None:
    latest = tmp_path / "student-latest.zip"
    previous = tmp_path / "student-previous.zip"
    latest.write_bytes(b"interrupted-new-generation")
    previous.write_bytes(b"checkpoint-generation")
    expected = hashlib.sha256(previous.read_bytes()).hexdigest()

    first = _resolve_checkpoint_artifact(
        tmp_path,
        latest_name=latest.name,
        previous_name=previous.name,
        expected_sha256=expected,
    )
    assert first == latest
    assert latest.read_bytes() == b"checkpoint-generation"
    assert previous.read_bytes() == b"checkpoint-generation"

    # The next checkpoint rotates the recovered latest, then crashes before
    # publishing its replacement. The still-current JSON checkpoint remains recoverable.
    os.replace(latest, previous)
    second = _resolve_checkpoint_artifact(
        tmp_path,
        latest_name=latest.name,
        previous_name=previous.name,
        expected_sha256=expected,
    )
    assert second == latest
    assert latest.read_bytes() == b"checkpoint-generation"
    assert previous.read_bytes() == b"checkpoint-generation"


def test_composition_artifacts_are_hash_bound_before_ledger_checkpoint(
    tmp_path: Path,
) -> None:
    library = SelfTaughtSkillLibrary.initialize(
        [{"entry_id": "root", "milestone_index": 0}],
        window_size=2,
        threshold=1,
    )
    artifacts = tmp_path / "self-skills"
    artifacts.mkdir()
    for skill_id, source, target, source_index, target_index in (
        ("first", "root", "middle", 0, 1),
        ("second", "middle", "end", 1, 2),
    ):
        target_path = artifacts / f"{skill_id}.png"
        dataset_path = artifacts / f"{skill_id}.npz"
        target_path.write_bytes(f"{skill_id} target".encode())
        dataset_path.write_bytes(f"{skill_id} dataset".encode())
        assert library.add_verified_skill(
            skill_id=skill_id,
            source_entry_id=source,
            source_index=source_index,
            target_entry_id=target,
            target_index=target_index,
            target_label=target,
            target_frame_file=f"self-skills/{skill_id}.png",
            target_frame_sha256=_sha256_file(target_path),
            dataset_file=f"self-skills/{skill_id}.npz",
            dataset_sha256=_sha256_file(dataset_path),
            action_count=2,
        )
        library.skill(skill_id)["competent"] = True
    dataset = artifacts / "composition.npz"
    audit = artifacts / "composition.audit.json"
    dataset.write_bytes(b"continuous verified observations")
    audit.write_bytes(b"continuous replay audit")
    library.add_verified_composition(
        composition_id="composition",
        fingerprint="f" * 64,
        skill_ids=("first", "second"),
        target_index=2,
        dataset_file="self-skills/composition.npz",
        dataset_sha256=_sha256_file(dataset),
        audit_file="self-skills/composition.audit.json",
        audit_sha256=_sha256_file(audit),
        action_count=4,
        goal_switch_offsets=(2,),
        full_action_count=4,
        full_goal_switch_offsets=(2,),
        excerpt_offsets=(0, 4),
        successful_replays=1,
    )
    (tmp_path / "self-skills.json").write_text(
        json.dumps(library.public_dict()),
        encoding="utf-8",
    )

    checkpoint = _checkpoint_self_skill_state(tmp_path)
    assert checkpoint["self_skills_file_sha256"] == _sha256_file(
        tmp_path / "self-skills.checkpoint.json"
    )
    audit.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="before checkpoint"):
        _checkpoint_self_skill_state(tmp_path)


def test_individual_skill_artifacts_are_hash_bound_before_ledger_checkpoint(
    tmp_path: Path,
) -> None:
    library = SelfTaughtSkillLibrary.initialize(
        [{"entry_id": "root", "milestone_index": 0}],
        window_size=2,
        threshold=1,
    )
    artifacts = tmp_path / "self-skills"
    artifacts.mkdir()
    target = artifacts / "first.png"
    dataset = artifacts / "first.npz"
    audit = artifacts / "first.distillation.json"
    target.write_bytes(b"target")
    dataset.write_bytes(b"dataset")
    audit.write_bytes(b"audit")
    assert library.add_verified_skill(
        skill_id="first",
        source_entry_id="root",
        source_index=0,
        target_entry_id="middle",
        target_index=1,
        target_label="middle",
        target_frame_file="self-skills/first.png",
        target_frame_sha256=_sha256_file(target),
        dataset_file="self-skills/first.npz",
        dataset_sha256=_sha256_file(dataset),
        action_count=2,
        distillation_audit_file="self-skills/first.distillation.json",
        distillation_audit_sha256=_sha256_file(audit),
        distillation_oracle_calls=3,
        distillation_oracle_actions_replayed=6,
        distillation_edits_accepted=1,
        distillation_edits_rejected=1,
    )
    (tmp_path / "self-skills.json").write_text(
        json.dumps(library.public_dict()),
        encoding="utf-8",
    )

    _checkpoint_self_skill_state(tmp_path)
    dataset.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="Self-taught skill artifact before checkpoint"):
        _checkpoint_self_skill_state(tmp_path)


def test_skill_checkpoint_rejects_artifact_path_outside_run(tmp_path: Path) -> None:
    library = SelfTaughtSkillLibrary.initialize(
        [{"entry_id": "root", "milestone_index": 0}],
        window_size=2,
        threshold=1,
    )
    outside = tmp_path.parent / f"{tmp_path.name}-outside.png"
    outside.write_bytes(b"outside")
    with pytest.raises(ValueError, match="path is invalid"):
        library.add_verified_skill(
            skill_id="escape",
            source_entry_id="root",
            source_index=0,
            target_entry_id="middle",
            target_index=1,
            target_label="middle",
            target_frame_file=f"../{outside.name}",
            target_frame_sha256=_sha256_file(outside),
            dataset_file="missing.npz",
            dataset_sha256="a" * 64,
            action_count=1,
        )
    assert library.skills == []


def _admit_sharded_v8_skill(
    tmp_path: Path,
    *,
    action_count: int = 9,
    cap: int = 4,
) -> tuple[SelfTaughtSkillLibrary, Path, list[dict[str, object]]]:
    artifacts = tmp_path / "self-skills"
    artifacts.mkdir(exist_ok=True)
    skill_id = "bounded-skill"
    target = artifacts / f"{skill_id}.png"
    source = artifacts / f"{skill_id}.npz"
    audit = artifacts / f"{skill_id}.distillation.json"
    target.write_bytes(b"sealed target")
    audit.write_bytes(b"sealed audit")
    dataset = {
        "pixels": np.zeros((action_count, 2, 72, 80), dtype=np.uint8),
        "action_history": np.zeros((action_count, ACTION_HISTORY_LENGTH), dtype=np.float32),
        "target_pixels": np.zeros((3, 72, 80), dtype=np.uint8),
        "actions": np.arange(action_count, dtype=np.int64) % len(BLIND_ACTIONS),
        "weights": np.ones(action_count, dtype=np.float32),
        "episode_starts": np.asarray(
            [True, *([False] * (action_count - 1))],
            dtype=np.bool_,
        ),
        "compressed_to_original": np.arange(action_count, dtype=np.int64),
    }
    with source.open("wb") as output:
        np.savez_compressed(output, **dataset)
    source_sha256 = _sha256_file(source)
    shards = _write_v8_replay_shards(
        tmp_path,
        skill_id=skill_id,
        dataset=dataset,
        source_dataset_sha256=source_sha256,
        max_examples=cap,
        burn_in=2,
    )
    library = SelfTaughtSkillLibrary.initialize(
        [{"entry_id": "root", "milestone_index": 0}],
        window_size=2,
        threshold=1,
    )
    assert library.add_verified_skill(
        skill_id=skill_id,
        source_entry_id="root",
        source_index=0,
        target_entry_id="middle",
        target_index=1,
        target_label="middle",
        target_frame_file=f"self-skills/{target.name}",
        target_frame_sha256=_sha256_file(target),
        dataset_file=f"self-skills/{source.name}",
        dataset_sha256=source_sha256,
        action_count=action_count,
        distillation_audit_file=f"self-skills/{audit.name}",
        distillation_audit_sha256=_sha256_file(audit),
        target_clip_channels=3,
        replay_shards=shards,
        replay_shard_example_cap=cap,
        replay_shard_burn_in=2,
    )
    return library, source, shards


def test_v8_training_opens_only_one_bounded_hash_bound_shard_per_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library, full_source, shards = _admit_sharded_v8_skill(tmp_path)
    callback = object.__new__(PpoRunCallback)
    callback.run_directory = tmp_path
    callback.self_skills = library
    callback.student_trainer = SimpleNamespace(
        config=SequenceTrainingConfig(burn_in=2, max_examples_per_dataset=4)
    )

    hashed: list[Path] = []
    opened: list[Path] = []
    real_hash = ppo_training_module._sha256_file
    real_load = np.load

    def recording_hash(path: Path) -> str:
        hashed.append(Path(path))
        return real_hash(path)

    def recording_load(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        opened.append(Path(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(ppo_training_module, "_sha256_file", recording_hash)
    monkeypatch.setattr(ppo_training_module.np, "load", recording_load)

    datasets, selections = PpoRunCallback._load_v8_student_datasets(callback)

    selected_path = tmp_path / str(shards[0]["file"])
    assert len(datasets) == 1
    assert len(datasets[0]) == 4
    assert datasets[0].source_action_count == 9
    assert selections[0]["shard_index"] == 0
    assert hashed == [selected_path]
    assert opened == [selected_path]
    assert full_source not in hashed
    assert full_source not in opened

    second = SelfGeneratedSkillDataset.load(
        tmp_path / str(shards[1]["file"]),
        skill_id="bounded-skill",
    )
    windows = make_recurrent_sequences(second, burn_in=2, train_length=4, stride=4)
    assert len(second) == 6
    assert second.train_offset == 2
    assert second.trainable_examples == 4
    assert (windows[0].burn_start, windows[0].train_start) == (0, 2)
    assert all(window.train_start >= second.train_offset for window in windows)


def test_v8_replay_cursor_rotates_all_shards_and_survives_round_trip(tmp_path: Path) -> None:
    library, _full_source, shards = _admit_sharded_v8_skill(tmp_path)
    observed: list[int] = []
    for _ in range(len(shards) + 1):
        observed.append(int(library.replay_shard("bounded-skill")["shard_index"]))
        library.advance_replay_cursors(["bounded-skill"])
        library = SelfTaughtSkillLibrary.from_dict(library.public_dict())

    assert observed == [0, 1, 2, 0]
    assert library.skill("bounded-skill")["replay_cursor"] == 4
    assert library.public_dict()["schema_version"] == 2

    corrupted = library.public_dict()
    corrupted["skills"][0]["replay_shards"][0]["source_start"] = 1
    with pytest.raises(ValueError, match="shard coverage"):
        SelfTaughtSkillLibrary.from_dict(corrupted)


def test_routine_checkpoint_skips_committed_inactive_composition_but_checks_active(
    tmp_path: Path,
) -> None:
    library = SelfTaughtSkillLibrary.initialize(
        [{"entry_id": "root", "milestone_index": 0}],
        window_size=2,
        threshold=1,
    )
    artifacts = tmp_path / "self-skills"
    artifacts.mkdir()
    for skill_id, source_id, target_id, source_index, target_index in (
        ("first", "root", "middle", 0, 1),
        ("second", "middle", "end", 1, 2),
    ):
        target = artifacts / f"{skill_id}.png"
        dataset = artifacts / f"{skill_id}.npz"
        target.write_bytes(b"target")
        dataset.write_bytes(b"dataset")
        assert library.add_verified_skill(
            skill_id=skill_id,
            source_entry_id=source_id,
            source_index=source_index,
            target_entry_id=target_id,
            target_index=target_index,
            target_label=target_id,
            target_frame_file=f"self-skills/{target.name}",
            target_frame_sha256=_sha256_file(target),
            dataset_file=f"self-skills/{dataset.name}",
            dataset_sha256=_sha256_file(dataset),
            action_count=2,
        )
        library.skill(skill_id)["competent"] = True
    composition = artifacts / "composition.npz"
    audit = artifacts / "composition.audit.json"
    composition.write_bytes(b"composition")
    audit.write_bytes(b"audit")
    assert library.add_verified_composition(
        composition_id="composition",
        fingerprint="f" * 64,
        skill_ids=("first", "second"),
        target_index=2,
        dataset_file="self-skills/composition.npz",
        dataset_sha256=_sha256_file(composition),
        audit_file="self-skills/composition.audit.json",
        audit_sha256=_sha256_file(audit),
        action_count=4,
        goal_switch_offsets=(2,),
        full_action_count=4,
        full_goal_switch_offsets=(2,),
        excerpt_offsets=(0, 4),
        successful_replays=1,
    )
    (tmp_path / "self-skills.json").write_text(
        json.dumps(library.public_dict()), encoding="utf-8"
    )
    committed = _checkpoint_self_skill_state(tmp_path)
    (tmp_path / "checkpoint.json").write_text(json.dumps(committed), encoding="utf-8")

    library.activate_verified_composition(None)
    (tmp_path / "self-skills.json").write_text(
        json.dumps(library.public_dict()), encoding="utf-8"
    )
    audit.write_bytes(b"tampered archived audit")
    _checkpoint_self_skill_state(tmp_path)

    library.activate_verified_composition("f" * 64)
    (tmp_path / "self-skills.json").write_text(
        json.dumps(library.public_dict()), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="composition replay artifact before checkpoint"):
        _checkpoint_self_skill_state(tmp_path)


def test_curriculum_resume_rolls_back_an_uncommitted_promotion(
    tmp_path: Path,
) -> None:
    curriculum = tmp_path / "curriculum"
    entries_directory = curriculum / "entries"
    entries_directory.mkdir(parents=True)

    def entry(entry_id: str, index: int, key: str, label: str) -> dict[str, object]:
        path = entries_directory / f"{entry_id}.json.gz"
        _atomic_gzip_json(
            path,
            {
                "entry_id": entry_id,
                "progress": {"key": key, "index": index, "label": label},
            },
        )
        return {
            "entry_id": entry_id,
            "file": f"entries/{path.name}",
            "file_sha256": _sha256_file(path),
            "milestone_id": key,
            "milestone_index": index,
            "milestone_label": label,
        }

    root = entry("root", 0, "power_on", "Power-on")
    manifest = {
        "protocol": PPO_V8_PROTOCOL,
        "entries": [root],
        "best_milestone": {"key": "power_on", "index": 0, "label": "Power-on"},
    }
    (curriculum / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    committed = _checkpoint_curriculum_state(
        tmp_path,
        curriculum,
        protocol=PPO_V8_PROTOCOL,
    )

    promoted = entry("started", 1, "game_started", "The adventure begins")
    manifest["entries"] = [root, promoted]
    manifest["best_milestone"] = {
        "key": "game_started",
        "index": 1,
        "label": "The adventure begins",
    }
    (curriculum / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _checkpoint_curriculum_state(
        tmp_path,
        curriculum,
        protocol=PPO_V8_PROTOCOL,
    )

    restored = _restore_curriculum_state(
        tmp_path,
        curriculum,
        committed,
        protocol=PPO_V8_PROTOCOL,
    )

    assert [item["entry_id"] for item in restored["entries"]] == ["root"]
    assert json.loads((curriculum / "manifest.json").read_text())["best_milestone"]["index"] == 0


def test_v8_hall_of_fame_stop_requires_frozen_student_composition() -> None:
    status = {"best_milestone": {"key": "hall_of_fame"}}
    library = SelfTaughtSkillLibrary.initialize(
        [{"entry_id": "root", "milestone_index": 0}],
        window_size=2,
        threshold=1,
    )

    assert _hall_of_fame_stop_is_verified("pixels", status, None) is True
    assert _hall_of_fame_stop_is_verified("self_taught_v8", status, library) is False

    library.record_composition_exam(
        success=True,
        actions=10,
        target_index=66,
        hall_of_fame_target=True,
    )

    assert _hall_of_fame_stop_is_verified("self_taught_v8", status, library) is True
    assert library.best_composition_index == 66


def test_self_imitation_updates_recurrent_policy_from_its_own_dataset(
    tmp_path: Path,
) -> None:
    from sb3_contrib import RecurrentPPO
    from stable_baselines3.common.vec_env import DummyVecEnv

    class TinySelfTaughtEnv(gym.Env):
        def __init__(self) -> None:
            self.action_space = gym.spaces.Discrete(len(BLIND_ACTIONS))
            self.observation_space = gym.spaces.Dict(
                {
                    "pixels": gym.spaces.Box(0, 255, shape=(2, 72, 80), dtype=np.uint8),
                    "action_history": gym.spaces.Box(
                        0,
                        1,
                        shape=(ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS),),
                        dtype=np.float32,
                    ),
                    "target_pixels": gym.spaces.Box(0, 255, shape=(1, 72, 80), dtype=np.uint8),
                }
            )

        def observation(self) -> dict[str, np.ndarray]:
            return {
                "pixels": np.zeros((2, 72, 80), dtype=np.uint8),
                "action_history": np.zeros(
                    ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS), dtype=np.float32
                ),
                "target_pixels": np.zeros((1, 72, 80), dtype=np.uint8),
            }

        def reset(self, *, seed=None, options=None):  # type: ignore[no-untyped-def]
            super().reset(seed=seed)
            return self.observation(), {}

        def step(self, action):  # type: ignore[no-untyped-def]
            return self.observation(), 0.0, False, False, {}

    vector = DummyVecEnv([TinySelfTaughtEnv])
    model = RecurrentPPO(
        "MultiInputLstmPolicy",
        vector,
        n_steps=8,
        batch_size=8,
        n_epochs=1,
        policy_kwargs={
            "features_extractor_class": PokemonPpoFeatures,
            "net_arch": [],
            "lstm_hidden_size": 32,
        },
        device="cpu",
    )
    dataset = tmp_path / "self.npz"
    np.savez_compressed(
        dataset,
        pixels=np.zeros((4, 2, 72, 80), dtype=np.uint8),
        action_history=np.zeros((4, ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS)), dtype=np.float32),
        target_pixels=np.zeros((1, 72, 80), dtype=np.uint8),
        actions=np.asarray([0, 1, 2, 3], dtype=np.int64),
    )

    result = _train_self_imitation_policy(model, [dataset], epochs=1)

    assert result["updates"] == 1
    assert result["examples"] == 4
    assert np.isfinite(result["mean_loss"])
    vector.close()


def test_privileged_state_vector_is_fixed_and_bounded() -> None:
    state = PokemonRedState(
        game_started=True,
        map_id=255,
        player_y=200,
        player_x=100,
        party_count=6,
        battle_state=2,
        badge_bits=0b10101010,
        party_species=(1, 2, 3),
        party_levels=(5, 50, 100),
        party_moves=(1, 2),
        pokedex_owned=bytes([0xFF]) + bytes(18),
        pokedex_seen=bytes([0xFF, 0xFF]) + bytes(17),
        event_flags=bytes([0xFF]) + bytes(318),
        bag_item_ids=(1, 2, 3),
        got_pokedex=True,
    )
    vector = _state_vector(state)
    assert vector.shape == (PRIVILEGED_STATE_SIZE,)
    assert vector.dtype == np.float32
    assert np.all((vector >= 0) & (vector <= 1))


@pytest.mark.parametrize(
    "mode", ["pixels", "assisted", "privileged", "self_taught", "self_taught_v8"]
)
def test_feature_extractor_preserves_declared_information_boundary(mode: str) -> None:
    spaces = {
        "pixels": gym.spaces.Box(0, 255, shape=(2, 72, 80), dtype=np.uint8),
        "action_history": gym.spaces.Box(
            0,
            1,
            shape=(ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS),),
            dtype=np.float32,
        ),
    }
    if mode == "privileged":
        spaces["state"] = gym.spaces.Box(0, 1, shape=(PRIVILEGED_STATE_SIZE,), dtype=np.float32)
    if mode == "assisted":
        spaces.update(
            {
                "map_memory": gym.spaces.Box(
                    0, 255, shape=(2, MAP_MEMORY_SIZE, MAP_MEMORY_SIZE), dtype=np.uint8
                ),
                "goal": gym.spaces.Box(0, 1, shape=(GOAL_COUNT,), dtype=np.float32),
                "skill": gym.spaces.Box(0, 1, shape=(SKILL_COUNT,), dtype=np.float32),
                "map_context": gym.spaces.Box(0, 1, shape=(MAP_CONTEXT_SIZE,), dtype=np.float32),
            }
        )
    if mode in {"self_taught", "self_taught_v8"}:
        spaces["target_pixels"] = gym.spaces.Box(
            0,
            255,
            shape=(3 if mode == "self_taught_v8" else 1, 72, 80),
            dtype=np.uint8,
        )
    extractor = PokemonPpoFeatures(gym.spaces.Dict(spaces))
    observations = {
        "pixels": torch.zeros((2, 2, 72, 80)),
        "action_history": torch.zeros((2, ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS))),
    }
    if mode == "privileged":
        observations["state"] = torch.zeros((2, PRIVILEGED_STATE_SIZE))
    if mode == "assisted":
        observations.update(
            {
                "map_memory": torch.zeros((2, 2, MAP_MEMORY_SIZE, MAP_MEMORY_SIZE)),
                "goal": torch.zeros((2, GOAL_COUNT)),
                "skill": torch.zeros((2, SKILL_COUNT)),
                "map_context": torch.zeros((2, MAP_CONTEXT_SIZE)),
            }
        )
    if mode in {"self_taught", "self_taught_v8"}:
        observations["target_pixels"] = torch.zeros(
            (2, 3 if mode == "self_taught_v8" else 1, 72, 80)
        )

    features = extractor(observations)
    expected = (
        256
        + ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS)
        + (
            MAP_MEMORY_FEATURES + GOAL_COUNT + SKILL_COUNT + MAP_CONTEXT_SIZE
            if mode == "assisted"
            else 0
        )
        + (128 if mode in {"self_taught", "self_taught_v8"} else 0)
        + (PRIVILEGED_STATE_SIZE if mode == "privileged" else 0)
    )
    assert features.shape == (2, expected)


def test_episode_map_memory_marks_visited_and_current_cells() -> None:
    memory = EpisodeMapMemory()
    first = PokemonRedState(True, 1, 4, 3, 1, 0)
    second = PokemonRedState(True, 1, 4, 4, 1, 0)
    memory.reset(first)
    memory.observe(second)
    value = memory.observation(second)
    assert value[0, 4, 3] == 255
    assert value[0, 4, 4] == 255
    assert value[1, 4, 4] == 255
    assert value[1].sum() == 255


def test_visual_stagnation_tracker_finds_cycles_and_resets_on_progress() -> None:
    tracker = VisualStagnationTracker(cycle_window=4, cycle_unique_limit=2, hard_limit=20)
    progress = pytest.importorskip("pokemon_red_ai.expedition").MilestoneProgress(
        "power_on", 0, "Power-on"
    )
    state = PokemonRedState(True, 0, 1, 1, 1, 0, party_experience=(1,))
    tracker.reset(state, progress)
    frame = np.zeros((72, 80), dtype=np.uint8)
    assert tracker.observe(frame, state, progress) is None
    assert tracker.observe(frame, state, progress) is None
    assert tracker.observe(frame, state, progress) is None
    assert tracker.observe(frame, state, progress) == "visual_cycle"

    moved = PokemonRedState(True, 0, 1, 2, 1, 0, party_experience=(1,))
    assert tracker.observe(frame, moved, progress) is None


def test_v8_stagnation_ignores_authored_route_and_mart_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_route_guidance(*_args: object, **_kwargs: object) -> object:
        pytest.fail("blind stagnation tracking consulted authored route guidance")

    monkeypatch.setattr("pokemon_red_ai.ppo_training.route_guidance", forbidden_route_guidance)
    tracker = VisualStagnationTracker(
        cycle_window=16,
        cycle_unique_limit=1,
        hard_limit=3,
        use_authored_guidance=False,
    )
    power_on = pytest.importorskip("pokemon_red_ai.expedition").MilestoneProgress(
        "power_on", 0, "Power-on"
    )
    authored_advance = pytest.importorskip("pokemon_red_ai.expedition").MilestoneProgress(
        "game_started", 1, "The adventure begins"
    )
    state = PokemonRedState(
        True,
        1,
        1,
        1,
        1,
        0,
        party_experience=(1,),
        viridian_mart_script=0,
    )
    authored_only_change = PokemonRedState(
        True,
        1,
        1,
        1,
        1,
        0,
        party_experience=(1,),
        viridian_mart_script=255,
    )
    tracker.reset(state, power_on)
    frame = np.zeros((72, 80), dtype=np.uint8)
    assert tracker.observe(frame, authored_only_change, authored_advance) is None
    assert tracker.observe(frame, authored_only_change, authored_advance) is None
    assert tracker.observe(frame, authored_only_change, authored_advance) == "progress_stagnation"


def test_warm_start_maps_previous_action_to_newest_history_slot() -> None:
    source = torch.arange(2 * (256 + len(BLIND_ACTIONS)), dtype=torch.float32).reshape(2, -1)
    destination = torch.full(
        (2, 256 + ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS) + PRIVILEGED_STATE_SIZE),
        -1.0,
    )
    _remap_warm_start_lstm_input(destination, source)

    newest = 256 + (ACTION_HISTORY_LENGTH - 1) * len(BLIND_ACTIONS)
    assert torch.equal(destination[:, :256], source[:, :256])
    assert torch.count_nonzero(destination[:, 256:newest]) == 0
    assert torch.equal(destination[:, newest : newest + len(BLIND_ACTIONS)], source[:, 256:])
    assert torch.count_nonzero(destination[:, newest + len(BLIND_ACTIONS) :]) == 0


def test_dashboard_names_actor_boundary_and_finished_state() -> None:
    page = _render_dashboard(
        {
            "state": "finished",
            "mode": "pixels",
            "environments": 4,
            "total_actions": 10,
            "actions_per_second": 2,
            "ppo_updates": 1,
            "verified_promotions": 0,
            "unique_positions": 3,
            "episodes": 2,
            "best_milestone": {"label": "Reached Route 1"},
            "information_boundary": (
                "pixels + three recent actions; trainer-only RAM rewards and loop termination"
            ),
            "novelty_scope": "persistent per worker across episodes and resumes",
            "reward_protocol": "retained-policy-backward-consolidation-v1",
            "battle_events": {"success": 3, "ended_without_progress": 7},
            "self_taught": {
                "skills_discovered": 2,
                "skills_competent": 1,
                "imitation_examples": 12,
            },
        }
    )
    assert "Failures now" in page
    assert "pixels + three recent actions; trainer-only RAM rewards" in page
    assert "persistent per worker across episodes and resumes" in page
    assert "retained-policy-backward-consolidation-v1" in page
    assert "Consolidation start" in page
    assert "Self-discovered skills" in page
    assert "Self-imitation examples" in page
    assert "Navigation-recovery credit" in page
    assert "Battle successes" in page
    assert ">3<" in page
    assert "No-progress battle exits" in page
    assert ">7<" in page
    assert "finished" in page
    assert page.count("Environment ") == 8


def test_v8_narrative_labels_online_counter_as_explorer_actions(tmp_path: Path) -> None:
    callback = object.__new__(PpoRunCallback)
    callback.run_directory = tmp_path
    callback.config = SimpleNamespace(mode="self_taught_v8")
    status = {
        "best_milestone": {"label": "Power-on"},
        "training_focus": {"label": "Begin"},
        "total_actions": 123,
        "ppo_updates": 1,
        "verified_promotions": 0,
        "episodes": 1,
        "unique_positions": 1,
        "consolidation": {},
        "self_taught": {
            "skills_discovered": 0,
            "skills_competent": 0,
            "distillation": {},
            "student": {"diagnostics": {}},
            "frozen_exams": {},
            "composition": {},
        },
        "battle_events": {},
        "reward_components": {},
        "loop_events": {},
    }
    callback._status = lambda *_args, **_kwargs: status

    PpoRunCallback._narrative(callback, "terminology test")

    narrative = (tmp_path / "NARRATIVE.md").read_text(encoding="utf-8")
    assert "Explorer actions: 123" in narrative
    assert "Combined actions" not in narrative
