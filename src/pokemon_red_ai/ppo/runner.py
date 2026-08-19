"""Entry points that launch, stop, and inspect a parallel PPO run."""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from pokemon_red_ai.consolidation import (
    BackwardConsolidation,
)
from pokemon_red_ai.pixel_recovery import (
    PIXEL_LOOP_RECOVERY_PROTOCOL,
)
from pokemon_red_ai.ppo.artifacts import (
    _atomic_json,
    _ensure_run_manifest_identity,
    _require_reproducible_v8_source,
    _resolve_checkpoint_artifact,
    _sha256_file,
    _snapshot_v7_denominator,
    _validate_checkpoint_identity,
    _validate_hashed_run_artifact,
)
from pokemon_red_ai.ppo.callback import PpoRunCallback
from pokemon_red_ai.ppo.config import ParallelPpoConfig, PpoEnvironmentConfig
from pokemon_red_ai.ppo.constants import (
    V10_RECOVERY_CYCLE_UNIQUE_LIMIT,
    V10_RECOVERY_CYCLE_WINDOW,
    V10_RECOVERY_STAGNATION_ACTIONS,
    RecurrentPPO,
    SubprocVecEnv,
    torch,
)
from pokemon_red_ai.ppo.curriculum import (
    _copy_retained_ppo_policy,
    _load_curriculum_manifest,
    _restore_curriculum_state,
    _retain_power_on_only,
    create_verified_power_on_curriculum,
    freeze_verified_curriculum,
)
from pokemon_red_ai.ppo.environment import PokemonPpoFeatures, make_ppo_environment
from pokemon_red_ai.ppo.modes import (
    _is_distilled_student_mode,
    _is_self_taught_mode,
    _is_v8_mode,
    _is_v9_mode,
    _is_v10_mode,
    _is_v12_mode,
    _ppo_protocol,
    _ppo_reward_protocol,
    _requires_reproducible_source,
    _uses_v9_practice,
)
from pokemon_red_ai.ppo.promotion import _warm_start
from pokemon_red_ai.ppo.state_io import _restore_self_skill_state, _restore_student_practice_state
from pokemon_red_ai.ppo.telemetry import _new_v12_learning_state, _validate_v12_learning_state
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import verify_rom
from pokemon_red_ai.self_taught import (
    SelfTaughtSkillLibrary,
)
from pokemon_red_ai.student_training import (
    SequenceAwareStudentTrainer,
    SequenceTrainingConfig,
)


def _start_server(directory: Path, port: int) -> ThreadingHTTPServer | None:
    if port == 0:
        return None
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="ppo-dashboard").start()
    return server


def _remaining_action_budget(max_actions: int, current_actions: int, *, resume: bool) -> int:
    """Give a retained fresh campaign a new counter while continuing a true resume counter."""

    return max(1, max_actions - current_actions) if resume else max_actions


def run_parallel_ppo(
    rom_path: Path,
    run_directory: Path,
    curriculum_source: Path | None,
    learner_path: Path | None,
    config: ParallelPpoConfig,
    *,
    resume: bool = False,
    policy_source: Path | None = None,
    v7_denominator: Path | None = None,
) -> dict[str, Any]:
    rom = verify_rom(rom_path).public_dict()
    source = detect_source_provenance(
        include_untracked=_requires_reproducible_source(config.mode)
    ).public_dict()
    if _requires_reproducible_source(config.mode):
        _require_reproducible_v8_source(source)
    if _is_v12_mode(config.mode) and curriculum_source is not None:
        raise ValueError("V12 creates its own clean power-on root and rejects curriculum imports")
    if not _is_v12_mode(config.mode) and curriculum_source is None:
        raise ValueError("This PPO mode requires a verified curriculum source")
    if v7_denominator is not None and (not _is_v8_mode(config.mode) or resume):
        raise ValueError("A V7 denominator may be locked only when a fresh V8 run begins")
    denominator_snapshot = (
        _snapshot_v7_denominator(v7_denominator) if v7_denominator is not None else None
    )
    if policy_source is not None and not config.consolidation:
        raise ValueError("A retained policy source requires consolidation mode")
    if _is_self_taught_mode(config.mode) and policy_source is not None:
        raise ValueError("Self-taught PPO cannot import a predecessor policy")
    run_directory = run_directory.expanduser().resolve()
    if run_directory.exists() and not resume:
        raise ValueError("PPO output directory already exists")
    run_directory.mkdir(parents=True, exist_ok=resume)
    for name in (
        "candidate-spool",
        "milestones",
        "self-skills",
        "student-practice",
        "hindsight",
    ):
        (run_directory / name).mkdir(exist_ok=True)
    curriculum_directory = run_directory / "curriculum"
    if not curriculum_directory.exists():
        if _is_v12_mode(config.mode):
            create_verified_power_on_curriculum(
                rom_path,
                curriculum_directory,
                target_protocol=_ppo_protocol(config.mode),
            )
        else:
            if curriculum_source is None:
                raise ValueError("This PPO mode requires a verified curriculum source")
            freeze_verified_curriculum(
                curriculum_source,
                curriculum_directory,
                target_protocol=_ppo_protocol(config.mode),
            )
            if config.power_on_only:
                _retain_power_on_only(curriculum_directory)
    consolidation_path = run_directory / "consolidation.json"
    if config.consolidation and not consolidation_path.exists() and not resume:
        curriculum_manifest = _load_curriculum_manifest(curriculum_directory)
        consolidation = BackwardConsolidation.initialize(
            curriculum_manifest["entries"],
            window_size=config.competence_window,
            threshold=config.competence_threshold,
        )
        _atomic_json(consolidation_path, consolidation.public_dict())
    self_skills_path = run_directory / "self-skills.json"
    if _is_self_taught_mode(config.mode) and not self_skills_path.exists() and not resume:
        curriculum_manifest = _load_curriculum_manifest(curriculum_directory)
        library = SelfTaughtSkillLibrary.initialize(
            curriculum_manifest["entries"],
            window_size=config.competence_window,
            threshold=config.competence_threshold,
        )
        _atomic_json(self_skills_path, library.public_dict())
    v12_learning_path = run_directory / "v12-learning.json"
    if _is_v12_mode(config.mode) and not v12_learning_path.exists() and not resume:
        _atomic_json(v12_learning_path, _new_v12_learning_state())
    started_at = datetime.now(UTC).isoformat()
    base_elapsed = 0.0
    checkpoint_path = run_directory / "checkpoint.json"
    model_path = run_directory / "ppo-latest.zip"
    student_model_path = run_directory / "student-latest.zip"
    student_optimizer_path = run_directory / "student-optimizer.pt"
    retained_policy_path: Path | None = None
    retained_policy_info: dict[str, Any] | None = None
    novelty_by_rank: dict[int, str] = {}
    if resume:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("protocol") != _ppo_protocol(config.mode):
            raise ValueError("PPO checkpoint uses a different protocol")
        if checkpoint.get("config") != config.public_dict():
            raise ValueError("PPO resume configuration does not match")
        _validate_checkpoint_identity(
            checkpoint,
            source=source,
            rom=rom,
            required=_requires_reproducible_source(config.mode),
        )
        run_manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
        if _is_v8_mode(config.mode) and checkpoint.get("v7_denominator") != (
            run_manifest.get("v7_denominator")
        ):
            raise ValueError("V8 denominator identity does not match its checkpoint")
        if checkpoint.get("curriculum_checkpoint_file") is not None:
            _restore_curriculum_state(
                run_directory,
                curriculum_directory,
                checkpoint,
                protocol=_ppo_protocol(config.mode),
            )
        elif _requires_reproducible_source(config.mode):
            raise ValueError("Modern self-taught checkpoint has no bound curriculum snapshot")
        else:
            legacy_curriculum = _load_curriculum_manifest(curriculum_directory)
            if legacy_curriculum.get("best_milestone") != checkpoint.get("best_milestone"):
                raise ValueError("Legacy PPO curriculum moved beyond its checkpoint")
        try:
            model_path = _resolve_checkpoint_artifact(
                run_directory,
                latest_name="ppo-latest.zip",
                previous_name="ppo-previous.zip",
                expected_sha256=checkpoint.get("model_file_sha256"),
            )
        except ValueError as error:
            raise ValueError("PPO model does not match its checkpoint") from error
        if config.consolidation:
            expected_consolidation_hash = checkpoint.get("consolidation_file_sha256")
            if (
                not consolidation_path.is_file()
                or _sha256_file(consolidation_path) != expected_consolidation_hash
            ):
                raise ValueError("PPO consolidation state does not match its checkpoint")
        if _is_self_taught_mode(config.mode):
            library = _restore_self_skill_state(run_directory, checkpoint)
            for skill in library.skills:
                for file_key, hash_key in (
                    ("target_frame_file", "target_frame_sha256"),
                    ("dataset_file", "dataset_sha256"),
                    ("distillation_audit_file", "distillation_audit_sha256"),
                    ("skill_graph_audit_file", "skill_graph_audit_sha256"),
                ):
                    if skill.get(file_key) is None:
                        continue
                    _validate_hashed_run_artifact(
                        run_directory,
                        skill[file_key],
                        skill.get(hash_key),
                        label="PPO self-taught skill artifact",
                    )
                for shard in skill.get("replay_shards", []):
                    shard_path = _validate_hashed_run_artifact(
                        run_directory,
                        shard["file"],
                        shard["sha256"],
                        label="PPO bounded replay shard",
                    )
                    if shard_path.stat().st_size != int(shard["stored_bytes"]):
                        raise ValueError("PPO bounded replay shard size disagrees with ledger")
            for composition in library.composition_replays:
                for file_key, hash_key in (
                    ("dataset_file", "dataset_sha256"),
                    ("audit_file", "audit_sha256"),
                ):
                    _validate_hashed_run_artifact(
                        run_directory,
                        composition[file_key],
                        composition.get(hash_key),
                        label="PPO composition replay artifact",
                    )
        if _is_distilled_student_mode(config.mode):
            if checkpoint.get("student_model_file") != "student-latest.zip":
                raise ValueError("Checkpoint has no separate Student model")
            try:
                student_model_path = _resolve_checkpoint_artifact(
                    run_directory,
                    latest_name="student-latest.zip",
                    previous_name="student-previous.zip",
                    expected_sha256=checkpoint.get("student_model_file_sha256"),
                )
            except ValueError as error:
                raise ValueError("Student model does not match its checkpoint") from error
            if checkpoint.get("student_optimizer_file") != "student-optimizer.pt":
                raise ValueError("Checkpoint has no separate Student optimizer")
            try:
                student_optimizer_path = _resolve_checkpoint_artifact(
                    run_directory,
                    latest_name="student-optimizer.pt",
                    previous_name="student-optimizer.previous.pt",
                    expected_sha256=checkpoint.get("student_optimizer_file_sha256"),
                )
            except ValueError as error:
                raise ValueError("Student optimizer does not match its checkpoint") from error
        if _uses_v9_practice(config.mode):
            _restore_student_practice_state(run_directory, checkpoint)
        if _is_v12_mode(config.mode):
            if checkpoint.get("v12_learning_file") != "v12-learning.json":
                raise ValueError("V12 checkpoint has no hindsight learning state")
            if (
                not v12_learning_path.is_file()
                or _sha256_file(v12_learning_path)
                != checkpoint.get("v12_learning_file_sha256")
            ):
                raise ValueError("V12 hindsight learning state does not match its checkpoint")
            _validate_v12_learning_state(
                json.loads(v12_learning_path.read_text(encoding="utf-8"))
            )
        novelty_files = checkpoint.get("novelty_files")
        if not isinstance(novelty_files, list):
            raise ValueError("PPO checkpoint has no persistent novelty memory")
        for metadata in novelty_files:
            rank = int(metadata["rank"])
            filename = str(metadata["file"])
            if Path(filename).name != filename or rank in novelty_by_rank:
                raise ValueError("PPO novelty checkpoint metadata is invalid")
            path = run_directory / filename
            if _sha256_file(path) != metadata.get("file_sha256"):
                raise ValueError("PPO novelty memory does not match its checkpoint")
            novelty_by_rank[rank] = filename
        if set(novelty_by_rank) != set(range(config.environments)):
            raise ValueError("PPO novelty checkpoint does not cover every environment")
        previous_status = json.loads((run_directory / "status.json").read_text(encoding="utf-8"))
        if previous_status.get("stop_reason") in {
            "duration_limit",
            "action_limit",
            "hall_of_fame_verified",
        }:
            raise ValueError("PPO campaign already reached a terminal boundary")
        started_at = str(previous_status["started_at"])
        base_elapsed = float(checkpoint["elapsed_seconds"])
        (run_directory / "STOP").unlink(missing_ok=True)
    else:
        learner_copy = run_directory / "seed-frontier-learner.pt"
        if config.consolidation:
            if policy_source is None:
                raise ValueError("Consolidation requires a finished PPO policy source")
            retained_policy_path = run_directory / "seed-ppo-policy.zip"
            retained_policy_info = _copy_retained_ppo_policy(
                policy_source.expanduser().resolve(),
                retained_policy_path,
                config,
            )
        elif not config.random_initialization:
            if learner_path is None:
                raise ValueError("Warm-start PPO requires a frontier learner checkpoint")
            shutil.copy2(learner_path, learner_copy)
        _atomic_json(
            run_directory / "manifest.json",
            {
                "schema_version": 1,
                "protocol": _ppo_protocol(config.mode),
                "config": config.public_dict(),
                "source": source,
                "rom": rom,
                "actor_mode": config.mode,
                "human_demonstrations": [],
                "self_generated_verified_curriculum": True,
                "curriculum_source": (
                    "direct_verified_clean_boot"
                    if curriculum_source is None
                    else curriculum_source.name
                ),
                "novelty_scope": "persistent per worker across episodes and resumes",
                "reward_protocol": _ppo_reward_protocol(config.mode),
                "rom_path_recorded": False,
                "resume_semantics": "model_optimizer_exact_environment_rollout_restarts",
                **(
                    {"v7_denominator": denominator_snapshot}
                    if denominator_snapshot is not None
                    else {}
                ),
                "policy_initialization": (
                    {
                        "kind": "random_untrained_policy",
                        "imported_actions": 0,
                        "imported_parameters": 0,
                    }
                    if config.random_initialization
                    else retained_policy_info
                ),
                **(
                    {
                        "v12_architecture": {
                            "actor": "one recurrent goal-conditioned visual PPO policy",
                            "online_decision_model_calls": 0,
                            "network_gameplay_calls": 0,
                            "pretrained_components": [],
                            "imported_actions": 0,
                            "imported_parameters": 0,
                            "starting_state": "direct replay-verified clean ROM power-on",
                            "ordinary_learning": (
                                "on-policy PPO plus future-frame hindsight imitation from the "
                                "same policy's own rollouts, with a correct-goal-versus-blank "
                                "counterfactual margin"
                            ),
                            "rare_discovery_learning": (
                                "replay-verified self-generated visual skills and rehearsal"
                            ),
                            "competence_authority": (
                                "deterministic no-update checkpoint exams and terminal "
                                "power-on composition evaluation"
                            ),
                            "recovery": PIXEL_LOOP_RECOVERY_PROTOCOL,
                            "trainer_selected_buttons": 0,
                            "actor_visible_ram": False,
                            "actor_visible_maps_or_coordinates": False,
                            "authored_route_or_quest_plan": False,
                        },
                        "fixed_experiment_contract": {
                            "duration_seconds": config.duration_seconds,
                            "maximum_actions": config.max_actions,
                            "configuration_sha256": hashlib.sha256(
                                json.dumps(
                                    config.public_dict(),
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ).encode("utf-8")
                            ).hexdigest(),
                            "mid_run_rule_changes_allowed": False,
                            "human_controller_actions_after_launch": 0,
                        },
                    }
                    if _is_v12_mode(config.mode)
                    else {}
                ),
            },
        )
        if retained_policy_path is None and not config.random_initialization:
            learner_path = learner_copy

    _ensure_run_manifest_identity(
        run_directory / "manifest.json",
        source=source,
        rom=rom,
    )

    env_fns = [
        partial(
            make_ppo_environment,
            PpoEnvironmentConfig(
                rom_path=str(rom_path),
                run_directory=str(run_directory),
                curriculum_directory=str(curriculum_directory),
                mode=config.mode,
                episode_actions=config.episode_actions,
                reward_scale=config.reward_scale,
                seed=config.seed,
                rank=rank,
                frontier_probability=config.frontier_probability,
                consolidation=config.consolidation,
                self_taught=_is_self_taught_mode(config.mode),
                novelty_checkpoint_file=novelty_by_rank.get(rank),
                explorer_recovery_window_actions=config.explorer_recovery_window_actions,
                explorer_recovery_blocked_threshold=(config.explorer_recovery_blocked_threshold),
                explorer_recovery_escape_confirmations=(
                    config.explorer_recovery_escape_confirmations
                ),
                explorer_recovery_ineffective_change_fraction=(
                    config.explorer_recovery_ineffective_change_fraction
                ),
                explorer_recovery_ineffective_mean_absolute_error=(
                    config.explorer_recovery_ineffective_mean_absolute_error
                ),
                explorer_recovery_escape_change_fraction=(
                    config.explorer_recovery_escape_change_fraction
                ),
                explorer_recovery_escape_mean_absolute_error=(
                    config.explorer_recovery_escape_mean_absolute_error
                ),
                explorer_recovery_blocked_penalty=config.explorer_recovery_blocked_penalty,
                explorer_recovery_escape_reward=config.explorer_recovery_escape_reward,
                explorer_recovery_expiration_penalty=(config.explorer_recovery_expiration_penalty),
            ),
        )
        for rank in range(config.environments)
    ]
    torch.set_num_threads(max(1, 4 // config.environments))
    vector = SubprocVecEnv(env_fns, start_method="forkserver")
    policy_kwargs = {
        "features_extractor_class": PokemonPpoFeatures,
        "features_extractor_kwargs": {},
        "lstm_hidden_size": 128,
        "n_lstm_layers": 1,
        "net_arch": [],
        "normalize_images": True,
    }
    if resume:
        model = RecurrentPPO.load(model_path, env=vector, device="cpu")
    elif retained_policy_path is not None:
        model = RecurrentPPO.load(retained_policy_path, env=vector, device="cpu")
        model.tensorboard_log = str(run_directory / "tensorboard")
    else:
        model = RecurrentPPO(
            "MultiInputLstmPolicy",
            vector,
            learning_rate=config.learning_rate,
            n_steps=config.rollout_steps,
            batch_size=config.batch_size,
            n_epochs=config.epochs,
            gamma=config.gamma,
            ent_coef=config.entropy_coefficient,
            policy_kwargs=policy_kwargs,
            seed=config.seed,
            device="cpu",
            verbose=0,
            tensorboard_log=str(run_directory / "tensorboard"),
        )
        if not config.random_initialization:
            if learner_path is None:
                raise ValueError("Warm-start PPO requires a frontier learner checkpoint")
            seed_info = _warm_start(
                model,
                learner_path,
                privileged=config.mode == "privileged",
                assisted=config.mode == "assisted",
            )
            manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
            manifest["warm_start"] = seed_info
            _atomic_json(run_directory / "manifest.json", manifest)
    student_model: Any | None = None
    student_trainer: SequenceAwareStudentTrainer | None = None
    if _is_distilled_student_mode(config.mode):
        if resume:
            student_model = RecurrentPPO.load(student_model_path, device="cpu")
        else:
            temporary_seed = run_directory / "student-seed.tmp.zip"
            model.save(temporary_seed)
            try:
                student_model = RecurrentPPO.load(temporary_seed, device="cpu")
            finally:
                temporary_seed.unlink(missing_ok=True)
        student_config = SequenceTrainingConfig(
            burn_in=config.student_burn_in,
            train_length=config.student_train_horizon,
            stride=max(1, config.student_train_horizon // 2),
            learning_rate=config.student_learning_rate,
            diagnostic_chunk_length=max(128, config.student_train_horizon * 4),
        )
        student_trainer = SequenceAwareStudentTrainer(
            student_model,
            student_config,
        )
        if resume:
            optimizer_state = torch.load(
                student_optimizer_path,
                map_location="cpu",
                weights_only=True,
            )
            student_trainer.load_optimizer_state_dict(optimizer_state)
        else:
            manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
            architecture_key = (
                "v10_architecture"
                if _is_v10_mode(config.mode)
                else "v9_architecture"
                if _is_v9_mode(config.mode)
                else "v8_architecture"
            )
            manifest[architecture_key] = {
                "explorer": "PPO policy updated only from online blind exploration",
                "student": (
                    "independent recurrent policy updated from distilled replay and closed-loop "
                    "success-only self-practice"
                    if _uses_v9_practice(config.mode)
                    else "independent recurrent policy updated only from self-generated replay"
                ),
                "initial_parameters_identical": True,
                "shared_parameters_after_initialization": False,
                "human_demonstrations": [],
                "goal_observation": "three self-observed terminal frames",
                "competence_authority": "frozen deterministic Student exams",
                "closed_loop_practice": _uses_v9_practice(config.mode),
                "recovery_ppo": (
                    "gated_future_escalation" if _uses_v9_practice(config.mode) else None
                ),
                **(
                    {
                        "explorer_loop_recovery": {
                            "protocol": PIXEL_LOOP_RECOVERY_PROTOCOL,
                            "inputs": ["preprocessed_rendered_pixels", "policy_selected_action"],
                            "actor_action_overrides": 0,
                            "uses_authored_guidance": False,
                            "episode_local_state": True,
                            "cycle_window_actions": V10_RECOVERY_CYCLE_WINDOW,
                            "cycle_unique_limit": V10_RECOVERY_CYCLE_UNIQUE_LIMIT,
                            "long_stagnation_actions": V10_RECOVERY_STAGNATION_ACTIONS,
                            "resume_behavior": ("fresh_rollout_counts_inflight_windows_abandoned"),
                        }
                    }
                    if _is_v10_mode(config.mode)
                    else {}
                ),
            }
            _atomic_json(run_directory / "manifest.json", manifest)
    callback = PpoRunCallback(
        run_directory,
        rom_path,
        curriculum_directory,
        config,
        base_elapsed=base_elapsed,
        started_at=started_at,
        student_model=student_model,
        student_trainer=student_trainer,
    )
    server = _start_server(run_directory, config.dashboard_port)
    reason = "completed"
    try:
        remaining = _remaining_action_budget(
            config.max_actions,
            model.num_timesteps,
            resume=resume,
        )
        model.learn(
            total_timesteps=remaining,
            callback=callback,
            reset_num_timesteps=not resume,
            progress_bar=False,
        )
        reason = callback.stop_reason or "action_limit"
    except KeyboardInterrupt:
        reason = "sigint"
    finally:
        callback.stop_reason = reason
        callback._abandon_active_recoveries("campaign_end")
        if _is_v12_mode(config.mode):
            callback._train_pending_v12_hindsight()
            callback._checkpoint()
            terminal = callback._run_v12_terminal_evaluation()
            if terminal is not None and terminal["hall_of_fame_verified"]:
                reason = "hall_of_fame_verified"
                callback.stop_reason = reason
        callback._checkpoint()
        status = callback._status("finished", reason)
        callback._narrative(f"campaign stopped: {reason}", state="finished", reason=reason)
        vector.close()
        if server is not None:
            server.shutdown()
            server.server_close()
    return status


def request_parallel_ppo_stop(run_directory: Path) -> None:
    run_directory = run_directory.expanduser().resolve()
    if not (run_directory / "status.json").is_file():
        raise ValueError("PPO status.json does not exist")
    (run_directory / "STOP").touch(exist_ok=True)


def show_parallel_ppo_status(run_directory: Path) -> dict[str, Any]:
    return json.loads(
        (run_directory.expanduser().resolve() / "status.json").read_text(encoding="utf-8")
    )
