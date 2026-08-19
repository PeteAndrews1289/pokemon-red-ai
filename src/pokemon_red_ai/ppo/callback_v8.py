"""The v8 student: dataset loading, training, and frozen composition replay.

Split out of the single ``PpoRunCallback`` class. These methods were moved
verbatim; ``self`` resolution and attribute access are unchanged.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pokemon_red_ai.apprentice_data import preprocess_apprentice_frame
from pokemon_red_ai.blind import (
    FrozenSnapshot,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    milestone_progress_for_state,
)
from pokemon_red_ai.ppo.artifacts import (
    _atomic_json,
    _sha256_file,
    _validate_hashed_run_artifact,
)
from pokemon_red_ai.ppo.constants import (
    ACTION_HISTORY_LENGTH,
)
from pokemon_red_ai.ppo.curriculum import (
    _load_curriculum_entry,
    _load_curriculum_manifest,
    _progress_from_value,
)
from pokemon_red_ai.ppo.distillation import (
    _atomic_self_imitation_dataset,
    _collect_v8_composition_dataset,
    _v8_composition_fingerprint,
)
from pokemon_red_ai.ppo.modes import (
    _is_v12_mode,
    _uses_v9_practice,
)
from pokemon_red_ai.ppo.observations import _action_history, _execute_action
from pokemon_red_ai.ppo.telemetry import (
    CompositionReplayRejected,
    _check_v9_practice_cancellation,
)
from pokemon_red_ai.self_taught import (
    SELF_GENERATED_COMPOSITION_PROTOCOL,
    SELF_GENERATED_REPLAY_SHARD_PROTOCOL,
)
from pokemon_red_ai.state import (
    PokemonRedStateReader,
)
from pokemon_red_ai.student_training import (
    BalancedSkillReplay,
    load_self_generated_datasets,
)


class V8DistillationMixin:
    """The v8 student: dataset loading, training, and frozen composition replay."""


    def _refresh_v8_composition_replay(self) -> bool:
        """Build one new replay-verified continuous chain when competence advances."""

        if self.self_skills is None:
            return False
        chain = self._competent_skill_chain()
        if len(chain) < 2:
            changed = self.self_skills.activate_verified_composition(None)
            if changed:
                self._write_self_skills()
            return changed
        fingerprint = _v8_composition_fingerprint(chain)
        outcome = self.self_skills.composition_build_outcomes.get(fingerprint)
        if outcome == "verified":
            changed = self.self_skills.activate_verified_composition(fingerprint)
            if changed:
                self._write_self_skills()
            return changed
        if outcome == "replay_failed":
            return False
        sources: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for skill in chain:
            path = self.run_directory / str(skill["dataset_file"])
            if _sha256_file(path) != skill["dataset_sha256"]:
                raise ValueError("V8 composition source dataset failed its hash")
            audit_path = self.run_directory / str(skill["distillation_audit_file"])
            if _sha256_file(audit_path) != skill["distillation_audit_sha256"]:
                raise ValueError("V8 composition source audit failed its hash")
            with np.load(path, allow_pickle=False) as archive:
                actions = np.asarray(archive["actions"], dtype=np.int64)
                target = np.asarray(archive["target_pixels"], dtype=np.uint8)
            sources[str(skill["skill_id"])] = (actions, target)
        try:
            dataset, boundaries = _collect_v8_composition_dataset(
                self.rom_path,
                self.curriculum_directory,
                chain,
                sources,
                burn_in=self.student_trainer.config.burn_in,
                train_length=self.student_trainer.config.train_length,
            )
        except CompositionReplayRejected:
            self.self_skills.record_composition_build_failure(fingerprint)
            self._write_self_skills()
            return False

        composition_id = f"composition-{fingerprint[:24]}"
        dataset_relative = f"self-skills/{composition_id}.npz"
        audit_relative = f"self-skills/{composition_id}.audit.json"
        dataset_path = self.run_directory / dataset_relative
        audit_path = self.run_directory / audit_relative
        _atomic_self_imitation_dataset(dataset_path, dataset)
        dataset_hash = _sha256_file(dataset_path)
        offsets = [int(value) for value in dataset["goal_switch_offsets"]]
        full_offsets = [int(value) for value in dataset["full_goal_switch_offsets"]]
        excerpt_offsets = [int(value) for value in dataset["excerpt_offsets"]]
        _atomic_json(
            audit_path,
            {
                "schema_version": 1,
                "protocol": SELF_GENERATED_COMPOSITION_PROTOCOL,
                "composition_id": composition_id,
                "fingerprint": fingerprint,
                "root_entry_id": self.self_skills.root_entry_id,
                "skill_ids": [str(skill["skill_id"]) for skill in chain],
                "source_artifacts": [
                    {
                        "skill_id": str(skill["skill_id"]),
                        "dataset_sha256": str(skill["dataset_sha256"]),
                        "distillation_audit_sha256": str(skill["distillation_audit_sha256"]),
                        "competent_when_built": bool(skill.get("competent", False)),
                    }
                    for skill in chain
                ],
                "dataset_sha256": dataset_hash,
                "action_count": int(len(dataset["actions"])),
                "goal_switch_offsets": offsets,
                "full_action_count": int(dataset["full_action_count"]),
                "full_goal_switch_offsets": full_offsets,
                "excerpt_offsets": excerpt_offsets,
                "excerpt_full_ranges": np.asarray(dataset["excerpt_full_ranges"]).tolist(),
                "boundaries": boundaries,
                "successful_continuous_replays": 1,
                "episode_starts": excerpt_offsets[:-1],
                "goal_storage": "one clip per declared segment; expanded per sampled window",
                "pixel_storage": "bounded switch excerpts only",
                "hidden_state_resets_at_excerpt_boundaries": True,
                "hidden_state_resets_at_goal_switches": False,
                "frozen_exam_actions_used_for_training": False,
                "human_actions": [],
            },
        )
        admitted = self.self_skills.add_verified_composition(
            composition_id=composition_id,
            fingerprint=fingerprint,
            skill_ids=[str(skill["skill_id"]) for skill in chain],
            target_index=int(chain[-1]["target_index"]),
            dataset_file=dataset_relative,
            dataset_sha256=dataset_hash,
            audit_file=audit_relative,
            audit_sha256=_sha256_file(audit_path),
            action_count=int(len(dataset["actions"])),
            goal_switch_offsets=offsets,
            full_action_count=int(dataset["full_action_count"]),
            full_goal_switch_offsets=full_offsets,
            excerpt_offsets=excerpt_offsets,
            successful_replays=1,
        )
        if admitted:
            self.self_imitation_pending = self.self_skills.imitation_pending
            self._write_self_skills()
        return admitted

    def _load_v8_student_datasets(
        self,
    ) -> tuple[tuple[Any, ...], list[dict[str, Any]], list[dict[str, Any]]]:
        if self.self_skills is None or not self.self_skills.skills:
            return (), [], []
        paths: dict[str, Path] = {}
        selections: list[dict[str, Any]] = []
        for skill in self.self_skills.skills:
            skill_id = str(skill["skill_id"])
            if int(skill.get("replay_shard_example_cap", 0)) != (
                self.student_trainer.config.max_examples_per_dataset
            ):
                raise ValueError("V8 replay shard cap disagrees with the Student configuration")
            if int(skill.get("replay_shard_burn_in", -1)) != self.student_trainer.config.burn_in:
                raise ValueError("V8 replay shard burn-in disagrees with Student configuration")
            shard = self.self_skills.replay_shard(skill_id)
            shard_path = _validate_hashed_run_artifact(
                self.run_directory,
                shard["file"],
                shard["sha256"],
                label="V8 bounded Student replay shard",
            )
            if shard_path.stat().st_size != int(shard["stored_bytes"]):
                raise ValueError("V8 bounded Student replay shard size disagrees with ledger")
            paths[skill_id] = shard_path
            cursor = int(skill.get("replay_cursor", 0))
            shard_count = len(skill["replay_shards"])
            selections.append(
                {
                    "skill_id": skill_id,
                    "cursor": cursor,
                    "shard_index": int(shard["shard_index"]),
                    "shard_count": shard_count,
                    "coverage_cycle": cursor // shard_count,
                    "source_start": int(shard["source_start"]),
                    "source_context_start": int(shard["source_context_start"]),
                    "source_train_start": int(shard["source_train_start"]),
                    "source_stop": int(shard["source_stop"]),
                    "context_examples": int(shard["context_example_count"]),
                    "train_examples": int(shard["train_example_count"]),
                    "stored_examples": int(shard["example_count"]),
                    "stored_bytes": int(shard["stored_bytes"]),
                }
            )
        for composition in self.self_skills.composition_replays:
            if not bool(composition.get("active", False)):
                continue
            dataset_path = _validate_hashed_run_artifact(
                self.run_directory,
                composition["dataset_file"],
                composition["dataset_sha256"],
                label="V8 active composition dataset",
            )
            _validate_hashed_run_artifact(
                self.run_directory,
                composition["audit_file"],
                composition["audit_sha256"],
                label="V8 active composition audit",
            )
            composition_id = str(composition["composition_id"])
            if composition_id in paths:
                raise ValueError("V8 composition identifier collides with an individual skill")
            paths[composition_id] = dataset_path
        practice_paths, practice_selections = self._selected_v9_practice_replays()
        if set(paths).intersection(practice_paths):
            raise ValueError("V9 practice replay identifier collides with a verified lesson")
        paths.update(practice_paths)
        datasets = load_self_generated_datasets(
            paths,
        )
        by_id = {dataset.skill_id: dataset for dataset in datasets}
        for skill in self.self_skills.skills:
            skill_id = str(skill["skill_id"])
            dataset = by_id[skill_id]
            shard = self.self_skills.replay_shard(skill_id)
            if (
                dataset.dataset_kind != "skill"
                or dataset.source_action_count != int(skill["action_count"])
                or dataset.source_action_offset != int(shard["source_start"])
                or len(dataset) != int(shard["example_count"])
                or dataset.train_offset
                != int(shard["source_train_start"]) - int(shard["source_start"])
                or dataset.trainable_examples != int(shard["train_example_count"])
                or dataset.source_train_start != int(shard["source_train_start"])
                or dataset.source_train_stop != int(shard["source_stop"])
                or dataset.replay_shard_protocol != SELF_GENERATED_REPLAY_SHARD_PROTOCOL
                or dataset.source_dataset_sha256 != str(skill["dataset_sha256"])
                or dataset.replay_shard_index != int(shard["shard_index"])
                or dataset.replay_shard_count != int(shard["shard_count"])
                or dataset.target_pixels.shape
                != (int(skill.get("target_clip_channels", 1)), 72, 80)
            ):
                raise ValueError("V8 individual dataset disagrees with its verified ledger")
        for composition in self.self_skills.active_composition_replays():
            dataset = by_id[str(composition["composition_id"])]
            if (
                dataset.dataset_kind != "composition"
                or dataset.source_skill_ids != tuple(composition["skill_ids"])
                or dataset.goal_switch_offsets
                != tuple(int(value) for value in composition["goal_switch_offsets"])
                or dataset.successful_replays != int(composition["successful_replays"])
                or len(dataset) != int(composition["action_count"])
                or dataset.excerpt_offsets != tuple(composition["excerpt_offsets"])
            ):
                raise ValueError("V8 composition dataset disagrees with its verified ledger")
        for selection in practice_selections:
            dataset = by_id[str(selection["dataset_id"])]
            rollout_id = str(selection["rollout_id"])
            rollout = next(
                item
                for ledger in self.student_practice_ledgers.values()
                for rung in ledger.rungs
                for item in rung.successful_rollouts
                if item.rollout_id == rollout_id
            )
            if (
                dataset.dataset_kind != "skill"
                or dataset.source_action_count != rollout.action_count
                or dataset.source_dataset_sha256 != rollout.dataset_sha256
                or dataset.replay_shard_index != int(selection["shard_index"])
                or dataset.replay_shard_count != int(selection["shard_count"])
                or dataset.target_pixels.shape != (3, 72, 80)
            ):
                raise ValueError("V9 practice dataset disagrees with its verified ledger")
        return datasets, selections, practice_selections

    def _train_v8_student(self) -> None:
        if self.self_skills is None or self.student_trainer is None or not self.self_skills.skills:
            return
        rollout_size = self.config.rollout_steps * self.config.environments
        rollout = self.model.num_timesteps // max(1, rollout_size)
        due = rollout % self.config.student_replay_interval == 0
        if not self.self_skills.imitation_pending and (
            not due or rollout == self.last_student_replay_rollout
        ):
            return
        self._refresh_v8_composition_replay()
        datasets, shard_selections, practice_selections = self._load_v8_student_datasets()
        replay = BalancedSkillReplay(
            datasets,
            self.student_trainer.config,
            seed=self.config.seed + self.self_skills.student_training_rounds,
            composition_boundary_cursor=self.self_skills.composition_boundary_cursor,
        )
        updates = self.config.student_replay_epochs * replay.sampling_cycle_size
        report = self.student_trainer.train(replay, updates=updates)
        self.self_skills.composition_boundary_cursor = replay.next_composition_boundary_cursor
        measured = self.student_trainer.diagnose(datasets)
        total = sum(item.examples for item in measured.values())
        diagnostics = {
            "action_nll": sum(item.action_nll * item.examples for item in measured.values())
            / total,
            "action_accuracy": sum(
                item.action_accuracy * item.examples for item in measured.values()
            )
            / total,
            "policy_entropy": sum(item.policy_entropy * item.examples for item in measured.values())
            / total,
            "demonstration_entropy": sum(
                item.demonstration_entropy * item.examples for item in measured.values()
            )
            / total,
        }
        recorded = report.public_dict()
        recorded["diagnostics"] = diagnostics
        recorded["per_skill_diagnostics"] = {
            skill_id: item.public_dict() for skill_id, item in sorted(measured.items())
        }
        recorded["individual_skill_datasets"] = sum(
            dataset.dataset_kind == "skill" for dataset in datasets
        )
        recorded["composition_datasets"] = sum(
            dataset.dataset_kind == "composition" for dataset in datasets
        )
        recorded["replay_examples_retained"] = sum(len(dataset) for dataset in datasets)
        recorded["replay_bytes_retained"] = sum(dataset.retained_bytes for dataset in datasets)
        recorded["max_examples_per_individual_skill"] = (
            self.student_trainer.config.max_examples_per_dataset
        )
        recorded["replay_example_ceiling"] = recorded["individual_skill_datasets"] * (
            self.student_trainer.config.max_examples_per_dataset
            + self.student_trainer.config.burn_in
        ) + sum(len(dataset) for dataset in datasets if dataset.dataset_kind == "composition")
        recorded["replay_train_example_ceiling"] = recorded[
            "individual_skill_datasets"
        ] * self.student_trainer.config.max_examples_per_dataset + sum(
            dataset.trainable_examples
            for dataset in datasets
            if dataset.dataset_kind == "composition"
        )
        recorded["sampling_cycle_size"] = replay.sampling_cycle_size
        recorded["replay_shards_total"] = sum(
            len(skill.get("replay_shards", [])) for skill in self.self_skills.skills
        )
        recorded["replay_shards_loaded"] = len(shard_selections)
        recorded["replay_shard_examples_loaded"] = sum(
            int(item["stored_examples"]) for item in shard_selections
        )
        recorded["replay_shard_train_examples_loaded"] = sum(
            int(item["train_examples"]) for item in shard_selections
        )
        recorded["replay_shard_context_examples_loaded"] = sum(
            int(item["context_examples"]) for item in shard_selections
        )
        recorded["replay_shard_bytes_read"] = sum(
            int(item["stored_bytes"]) for item in shard_selections
        )
        recorded["practice_replay_datasets_loaded"] = len(practice_selections)
        recorded["practice_replay_train_examples_loaded"] = sum(
            int(item["train_examples"]) for item in practice_selections
        )
        recorded["practice_replay_context_examples_loaded"] = sum(
            int(item["context_examples"]) for item in practice_selections
        )
        recorded["practice_replay_bytes_read"] = sum(
            int(item["stored_bytes"]) for item in practice_selections
        )
        recorded["practice_replay_selections"] = practice_selections
        recorded["replay_full_skill_artifacts_opened"] = 0
        recorded["replay_shard_selections"] = shard_selections
        recorded["replay_cursor_min"] = min(
            (int(item["cursor"]) for item in shard_selections),
            default=0,
        )
        recorded["replay_cursor_max"] = max(
            (int(item["cursor"]) for item in shard_selections),
            default=0,
        )
        recorded["replay_coverage_cycle_min"] = min(
            (int(item["coverage_cycle"]) for item in shard_selections),
            default=0,
        )
        self.self_skills.advance_replay_cursors(
            [str(item["skill_id"]) for item in shard_selections]
        )
        self.self_skills.record_student_training(recorded)
        self.self_imitation_pending = self.self_skills.imitation_pending
        self.last_student_replay_rollout = rollout
        self.self_skills.last_student_replay_rollout = rollout
        self._write_self_skills()
        self._checkpoint()
        self._narrative("Student replayed distilled self-discovered skills")

    def _v8_target_clip(self, skill: Mapping[str, Any]) -> np.ndarray:
        if self.self_skills is None:
            raise RuntimeError("Frozen Student exam has no self-generated skill ledger")
        if _is_v12_mode(self.config.mode):
            path = _validate_hashed_run_artifact(
                self.run_directory,
                skill["target_frame_file"],
                skill["target_frame_sha256"],
                label="V12 checkpoint exam target frame",
            )
            target = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)[None, :, :]
            if target.shape != (1, 72, 80):
                raise ValueError("V12 checkpoint exam requires one self-observed goal frame")
            return target
        shard = self.self_skills.replay_shard(str(skill["skill_id"]))
        path = _validate_hashed_run_artifact(
            self.run_directory,
            shard["file"],
            shard["sha256"],
            label="Frozen Student exam target shard",
        )
        with np.load(path, allow_pickle=False) as archive:
            target = np.asarray(archive["target_pixels"], dtype=np.uint8)
        if target.shape != (3, 72, 80):
            raise ValueError("V8 frozen exam requires a three-frame self-observed goal")
        return target

    def _predict_student_action(
        self,
        observation: Mapping[str, np.ndarray],
        recurrent_state: Any | None,
        *,
        episode_start: bool,
        deterministic: bool = True,
    ) -> tuple[int, Any]:
        evaluation_model = self.model if _is_v12_mode(self.config.mode) else self.student_model
        if evaluation_model is None:
            raise RuntimeError("Frozen checkpoint exam has no evaluation model")
        action, next_state = evaluation_model.predict(
            observation,
            state=recurrent_state,
            episode_start=np.asarray([episode_start], dtype=np.bool_),
            deterministic=deterministic,
        )
        return int(np.asarray(action).reshape(-1)[0]), next_state

    def _run_frozen_skill_attempt(
        self,
        skill: Mapping[str, Any],
    ) -> tuple[bool, int, int]:
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        source_metadata = next(
            (
                entry
                for entry in manifest["entries"]
                if str(entry["entry_id"]) == str(skill["source_entry_id"])
            ),
            None,
        )
        if source_metadata is None:
            raise ValueError("Frozen Student exam source is missing")
        source = _load_curriculum_entry(self.curriculum_directory, source_metadata)
        inherited = _progress_from_value(source["progress"])
        target_index = int(skill["target_index"])
        target_clip = self._v8_target_clip(skill)
        limit = max(
            1,
            int(np.ceil(int(skill["action_count"]) * self.config.frozen_exam_action_multiplier)),
        )
        recurrent_state: Any | None = None
        recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
        best = inherited.index
        actions = 0
        cancellation_check = (
            self._v9_practice_cancellation_reason if _uses_v9_practice(self.config.mode) else None
        )
        with PokemonRedEmulator(self.rom_path) as emulator:
            emulator.load_state(FrozenSnapshot.from_checkpoint_dict(source["snapshot"]).thaw())
            reader = PokemonRedStateReader(emulator)
            current = preprocess_apprentice_frame(emulator.screen_rgb())
            previous = current
            for step in range(limit):
                _check_v9_practice_cancellation(cancellation_check)
                action, recurrent_state = self._predict_student_action(
                    {
                        "pixels": np.stack((previous, current)),
                        "action_history": _action_history(recent),
                        "target_pixels": target_clip,
                    },
                    recurrent_state,
                    episode_start=step == 0,
                )
                actions += 1
                if not _execute_action(emulator, action):
                    break
                recent.append(action)
                previous = current
                current = preprocess_apprentice_frame(emulator.screen_rgb())
                state = reader.read()
                progress = milestone_progress_for_state(state, inherited=inherited)
                best = max(best, progress.index)
                if progress.index >= target_index:
                    return True, best, actions
        return False, best, actions

    def _competent_skill_chain(self) -> list[dict[str, Any]]:
        if self.self_skills is None:
            return []
        by_source: dict[str, list[dict[str, Any]]] = {}
        for skill in self.self_skills.skills:
            if bool(skill.get("competent", False)):
                by_source.setdefault(str(skill["source_entry_id"]), []).append(skill)

        def best_path(
            current: str,
            visiting: frozenset[str],
        ) -> list[dict[str, Any]]:
            if current in visiting:
                return []
            candidates = [
                [
                    skill,
                    *best_path(
                        str(skill["target_entry_id"]),
                        visiting | frozenset({current}),
                    ),
                ]
                for skill in by_source.get(current, [])
            ]
            if not candidates:
                return []
            return max(
                candidates,
                key=lambda path: (
                    int(path[-1]["target_index"]),
                    len(path),
                    tuple(str(item["skill_id"]) for item in path),
                ),
            )

        return best_path(self.self_skills.root_entry_id, frozenset())

    def _run_frozen_composition_attempt(
        self,
        chain: list[dict[str, Any]],
    ) -> tuple[bool, int]:
        if not chain:
            return False, 0
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        root_metadata = next(
            entry
            for entry in manifest["entries"]
            if str(entry["entry_id"]) == str(chain[0]["source_entry_id"])
        )
        root = _load_curriculum_entry(self.curriculum_directory, root_metadata)
        inherited = _progress_from_value(root["progress"])
        targets = [self._v8_target_clip(skill) for skill in chain]
        limit = max(
            1,
            int(
                np.ceil(
                    sum(int(skill["action_count"]) for skill in chain)
                    * self.config.frozen_exam_action_multiplier
                )
            ),
        )
        recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
        recurrent_state: Any | None = None
        current_skill = 0
        actions = 0
        cancellation_check = (
            self._v9_practice_cancellation_reason if _uses_v9_practice(self.config.mode) else None
        )
        with PokemonRedEmulator(self.rom_path) as emulator:
            emulator.load_state(FrozenSnapshot.from_checkpoint_dict(root["snapshot"]).thaw())
            reader = PokemonRedStateReader(emulator)
            current = preprocess_apprentice_frame(emulator.screen_rgb())
            previous = current
            for step in range(limit):
                _check_v9_practice_cancellation(cancellation_check)
                action, recurrent_state = self._predict_student_action(
                    {
                        "pixels": np.stack((previous, current)),
                        "action_history": _action_history(recent),
                        "target_pixels": targets[current_skill],
                    },
                    recurrent_state,
                    episode_start=step == 0,
                )
                actions += 1
                if not _execute_action(emulator, action):
                    break
                recent.append(action)
                previous = current
                current = preprocess_apprentice_frame(emulator.screen_rgb())
                progress = milestone_progress_for_state(reader.read(), inherited=inherited)
                while current_skill < len(chain) and progress.index >= int(
                    chain[current_skill]["target_index"]
                ):
                    current_skill += 1
                if current_skill == len(chain):
                    return True, actions
        return False, actions
