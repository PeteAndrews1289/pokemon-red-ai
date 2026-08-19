"""The v9 practice loop: skill preparation, replay selection, and rounds.

Split out of the single ``PpoRunCallback`` class. These methods were moved
verbatim; ``self`` resolution and attribute access are unchanged.
"""

from __future__ import annotations

import hashlib
import os
import random
import shutil
import time
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

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
)
from pokemon_red_ai.ppo.artifacts import (
    _atomic_gzip_json,
    _atomic_json,
    _canonical_json,
    _sha256_file,
    _validate_hashed_run_artifact,
)
from pokemon_red_ai.ppo.constants import (
    ACTION_HISTORY_LENGTH,
    V9_DISK_BUDGET_REFRESH_SECONDS,
    V9_PRACTICE_CANCELLATION_REASONS,
)
from pokemon_red_ai.ppo.curriculum import (
    _load_curriculum_entry,
    _load_curriculum_manifest,
    _progress_from_value,
)
from pokemon_red_ai.ppo.distillation import (
    _atomic_self_imitation_dataset,
    _collect_self_imitation_dataset,
    _collect_v8_student_dataset,
    _collect_v9_first_hit_graph,
    _composition_state_signature,
    _curriculum_snapshot_signature,
    _distill_verified_actions,
    _nearest_verified_lineage_prefix,
    _PreparedV9Skills,
    _replay_sequence,
    _V9FirstHit,
    _write_v8_replay_shards,
)
from pokemon_red_ai.ppo.modes import (
    _is_distilled_student_mode,
    _ppo_reward_protocol,
    _uses_v9_practice,
)
from pokemon_red_ai.ppo.observations import _action_history, _execute_action
from pokemon_red_ai.ppo.promotion import admit_verified_candidate
from pokemon_red_ai.ppo.telemetry import (
    V9PracticeCancelled,
    _check_v9_practice_cancellation,
    _merge_v9_success_student_report,
    _v9_practice_signature_outcome,
)
from pokemon_red_ai.self_taught import (
    SelfTaughtSkillLibrary,
)
from pokemon_red_ai.state import (
    PokemonRedStateReader,
)
from pokemon_red_ai.student_practice import (
    StudentPracticeLedger,
    SuccessfulRolloutMetadata,
)
from pokemon_red_ai.student_training import (
    BalancedSkillReplay,
    SelfGeneratedSkillDataset,
)


class V9PracticeMixin:
    """The v9 practice loop: skill preparation, replay selection, and rounds."""


    def _admit_v9_split_boundaries(
        self,
        graph: Any,
        hits: tuple[_V9FirstHit, ...],
        *,
        source_entry_id: str,
        final_entry_id: str,
        full_actions: Sequence[int],
        source_prefix_length: int,
    ) -> tuple[str, ...]:
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        existing = {str(item["entry_id"]): item for item in manifest["entries"]}
        if source_entry_id not in existing or final_entry_id not in existing:
            raise ValueError("V9 split commit requires admitted source and final entries")
        entry_ids = [source_entry_id]
        split_metadata: list[dict[str, Any]] = []
        for node, hit in zip(graph.nodes[1:-1], hits[1:-1], strict=True):
            entry_id = node.node_id
            if entry_id in existing:
                raise ValueError("V9 split boundary already exists in the curriculum")
            path = self.curriculum_directory / "entries" / f"{entry_id}.json.gz"
            payload = {
                "schema_version": 1,
                "entry_id": entry_id,
                "source_cell_id": None,
                "progress": hit.progress.public_dict(),
                "snapshot": hit.snapshot.checkpoint_dict(),
                "stable_state_identity": hit.observed.state_identity.public_dict(),
                "lineage_actions": [
                    BlindAction(
                        BLIND_ACTIONS[index], ACTION_HOLD_FRAMES, ACTION_RELEASE_FRAMES
                    ).public_dict()
                    for index in full_actions[: source_prefix_length + hit.observed.action_offset]
                ],
            }
            _atomic_gzip_json(path, payload)
            split_metadata.append(
                {
                    "entry_id": entry_id,
                    "file": f"entries/{path.name}",
                    "file_sha256": _sha256_file(path),
                    "milestone_id": hit.progress.key,
                    "milestone_index": hit.progress.index,
                    "milestone_label": hit.progress.label,
                    "map_id": hit.referee_summary.get("map_id"),
                    "depth_actions": source_prefix_length + hit.observed.action_offset,
                    "source": "v9_replay_local_first_hit",
                    "stable_state_sha256": hit.observed.state_identity.stable_state_sha256,
                    "snapshot_sha256": hit.observed.state_identity.snapshot_sha256,
                }
            )
            entry_ids.append(entry_id)
        entry_ids.append(final_entry_id)
        final_metadata = existing[final_entry_id]
        split_ids = set(entry_ids[1:-1])
        manifest["entries"] = [
            item
            for item in manifest["entries"]
            if str(item["entry_id"]) != final_entry_id and str(item["entry_id"]) not in split_ids
        ]
        manifest["entries"].extend(split_metadata)
        manifest["entries"].append(final_metadata)
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        _atomic_json(self.curriculum_directory / "manifest.json", manifest)
        return tuple(entry_ids)

    def _prepare_v9_normalized_skills(
        self,
        verification: Mapping[str, Any],
        progress: MilestoneProgress,
    ) -> _PreparedV9Skills:
        if self.student_trainer is None:
            raise RuntimeError("V9 edge normalization has no Student trainer")
        candidate = verification["candidate"]
        replay_id = str(candidate["candidate_id"])
        full_actions = [int(value) for value in verification["full_actions"]]
        source_metadata, source_entry, prefix_length = _nearest_verified_lineage_prefix(
            self.curriculum_directory,
            full_actions,
            target_index=progress.index,
        )
        source_actions = full_actions[prefix_length:]
        source_progress = _progress_from_value(source_entry["progress"])
        source_snapshot = FrozenSnapshot.from_checkpoint_dict(source_entry["snapshot"])
        graph, hits = _collect_v9_first_hit_graph(
            self.rom_path,
            source_snapshot,
            source_actions,
            source_progress,
            progress,
            replay_id=replay_id,
            cancellation_check=self._v9_practice_cancellation_reason,
        )
        candidate_snapshot = FrozenSnapshot.from_checkpoint_dict(candidate["terminal_snapshot"])
        if hits[0].progress != source_progress or hits[0].snapshot.sha256 != source_snapshot.sha256:
            raise ValueError("V9 graph source is not the selected concrete curriculum state")
        if (
            hits[-1].progress != progress
            or hits[-1].snapshot.sha256 != candidate_snapshot.sha256
            or candidate_snapshot.sha256 != str(candidate["terminal_snapshot_sha256"])
        ):
            raise ValueError("V9 graph target is not the verified candidate terminal state")
        graph_relative = f"self-skills/{replay_id}.skill-graph.json"
        graph_path = self.run_directory / graph_relative
        _atomic_json(graph_path, graph.public_audit())
        graph_sha256 = _sha256_file(graph_path)
        entry_ids = (
            str(source_metadata["entry_id"]),
            *(node.node_id for node in graph.nodes[1:-1]),
            replay_id,
        )
        prepared: list[dict[str, Any]] = []
        for edge_index, edge in enumerate(graph.edges):
            _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            source_hit = hits[edge_index]
            target_hit = hits[edge_index + 1]
            skill_id = edge.edge_id
            original_actions = [int(value) for value in edge.actions]
            distilled = _distill_verified_actions(
                self.rom_path,
                source_hit.snapshot,
                original_actions,
                source_hit.progress,
                target_hit.progress,
                verification_id=skill_id,
                successful_replays=(
                    int(verification["edge_replays"]) + int(verification["power_on_replays"])
                ),
                max_attempts=self.config.distillation_attempts,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            compressed_actions = [int(value) for value in distilled.actions]
            dataset, target_clip = _collect_v8_student_dataset(
                self.rom_path,
                source_hit.snapshot,
                compressed_actions,
                compressed_to_original=distilled.compressed_to_original,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            target_relative = f"self-skills/{skill_id}.png"
            dataset_relative = f"self-skills/{skill_id}.npz"
            audit_relative = f"self-skills/{skill_id}.distillation.json"
            target_path = self.run_directory / target_relative
            dataset_path = self.run_directory / dataset_relative
            audit_path = self.run_directory / audit_relative
            temporary_target = target_path.with_suffix(".tmp.png")
            Image.fromarray(target_clip[-1]).save(temporary_target, format="PNG")
            os.replace(temporary_target, target_path)
            _atomic_self_imitation_dataset(dataset_path, dataset)
            dataset_sha256 = _sha256_file(dataset_path)
            replay_shards = _write_v8_replay_shards(
                self.run_directory,
                skill_id=skill_id,
                dataset=dataset,
                source_dataset_sha256=dataset_sha256,
                max_examples=self.student_trainer.config.max_examples_per_dataset,
                burn_in=self.student_trainer.config.burn_in,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            self._refresh_v9_written_artifact_budget()
            _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            _atomic_json(
                audit_path,
                {
                    "schema_version": 1,
                    "protocol": _ppo_reward_protocol(self.config.mode),
                    "verification_id": skill_id,
                    "source_entry_id": entry_ids[edge_index],
                    "source_milestone": source_hit.progress.public_dict(),
                    "target_entry_id": entry_ids[edge_index + 1],
                    "target_milestone": target_hit.progress.public_dict(),
                    "expected_target_snapshot_sha256": target_hit.snapshot.sha256,
                    "skill_graph_audit_file": graph_relative,
                    "skill_graph_audit_sha256": graph_sha256,
                    "graph_edge_id": edge.edge_id,
                    "graph_start_action_offset": edge.start_action_offset,
                    "graph_end_action_offset": edge.end_action_offset,
                    "full_self_generated_action_count": len(full_actions),
                    "source_lineage_action_count": (prefix_length + edge.start_action_offset),
                    "compressed_to_original": list(distilled.compressed_to_original),
                    "original_to_compressed": list(distilled.original_to_compressed),
                    "distillation": distilled.audit.as_dict(),
                    "human_actions": [],
                },
            )
            prepared.append(
                {
                    "skill_id": skill_id,
                    "source_entry_id": entry_ids[edge_index],
                    "source_index": source_hit.progress.index,
                    "target_entry_id": entry_ids[edge_index + 1],
                    "target_index": target_hit.progress.index,
                    "target_label": target_hit.progress.label,
                    "target_frame_file": target_relative,
                    "target_frame_sha256": _sha256_file(target_path),
                    "dataset_file": dataset_relative,
                    "dataset_sha256": dataset_sha256,
                    "action_count": len(compressed_actions),
                    "original_action_count": len(original_actions),
                    "distillation_audit_file": audit_relative,
                    "distillation_audit_sha256": _sha256_file(audit_path),
                    "skill_graph_audit_file": graph_relative,
                    "skill_graph_audit_sha256": graph_sha256,
                    "graph_edge_id": edge.edge_id,
                    "distillation_oracle_calls": distilled.audit.total_oracle_calls,
                    "distillation_oracle_actions_replayed": (
                        distilled.audit.oracle_actions_replayed
                    ),
                    "distillation_edits_accepted": (
                        distilled.audit.loop_deletions_accepted
                        + distilled.audit.chunk_deletions_accepted
                    ),
                    "distillation_edits_rejected": (
                        distilled.audit.loop_deletions_rejected
                        + distilled.audit.chunk_deletions_rejected
                    ),
                    "target_clip_channels": int(target_clip.shape[0]),
                    "replay_shards": replay_shards,
                    "replay_shard_example_cap": (
                        self.student_trainer.config.max_examples_per_dataset
                    ),
                    "replay_shard_burn_in": self.student_trainer.config.burn_in,
                }
            )
        return _PreparedV9Skills(
            skills=tuple(prepared),
            graph=graph,
            hits=hits,
            source_entry_id=str(source_metadata["entry_id"]),
            final_entry_id=replay_id,
            full_actions=tuple(full_actions),
            source_prefix_length=prefix_length,
        )

    def _prepare_self_generated_skill(
        self,
        verification: Mapping[str, Any],
        progress: MilestoneProgress,
        source_png: Path,
    ) -> dict[str, Any] | list[dict[str, Any]] | _PreparedV9Skills | None:
        if self.self_skills is None:
            return None
        if not source_png.is_file():
            raise ValueError("Self-generated skill has no terminal visual target")
        candidate = verification["candidate"]
        parent = verification["parent"]
        skill_id = str(candidate["candidate_id"])
        target_relative = f"self-skills/{skill_id}.png"
        dataset_relative = f"self-skills/{skill_id}.npz"
        target_path = self.run_directory / target_relative
        dataset_path = self.run_directory / dataset_relative
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if _uses_v9_practice(self.config.mode):
            return self._prepare_v9_normalized_skills(verification, progress)

        if _is_distilled_student_mode(self.config.mode):
            full_actions = [int(value) for value in verification["full_actions"]]
            source_metadata, source_entry, prefix_length = _nearest_verified_lineage_prefix(
                self.curriculum_directory,
                full_actions,
                target_index=progress.index,
            )
            original_actions = full_actions[prefix_length:]
            if not original_actions:
                raise ValueError("V8 discovery has no actions after its nearest verified state")
            source_progress = _progress_from_value(source_entry["progress"])
            source_snapshot = FrozenSnapshot.from_checkpoint_dict(source_entry["snapshot"])
            distilled = _distill_verified_actions(
                self.rom_path,
                source_snapshot,
                original_actions,
                source_progress,
                progress,
                verification_id=skill_id,
                successful_replays=(
                    int(verification["edge_replays"]) + int(verification["power_on_replays"])
                ),
                max_attempts=self.config.distillation_attempts,
            )
            compressed_actions = [int(value) for value in distilled.actions]
            dataset, target_clip = _collect_v8_student_dataset(
                self.rom_path,
                source_snapshot,
                compressed_actions,
                compressed_to_original=distilled.compressed_to_original,
            )
            temporary_target = target_path.with_suffix(".tmp.png")
            Image.fromarray(target_clip[-1]).save(temporary_target, format="PNG")
            os.replace(temporary_target, target_path)
            _atomic_self_imitation_dataset(dataset_path, dataset)
            dataset_sha256 = _sha256_file(dataset_path)
            if self.student_trainer is None:
                raise RuntimeError("V8 replay shard admission has no Student trainer")
            replay_shards = _write_v8_replay_shards(
                self.run_directory,
                skill_id=skill_id,
                dataset=dataset,
                source_dataset_sha256=dataset_sha256,
                max_examples=self.student_trainer.config.max_examples_per_dataset,
                burn_in=self.student_trainer.config.burn_in,
            )
            audit_relative = f"self-skills/{skill_id}.distillation.json"
            audit_path = self.run_directory / audit_relative
            _atomic_json(
                audit_path,
                {
                    "schema_version": 1,
                    "protocol": _ppo_reward_protocol(self.config.mode),
                    "verification_id": skill_id,
                    "source_entry_id": str(source_entry["entry_id"]),
                    "source_milestone": source_progress.public_dict(),
                    "target_entry_id": skill_id,
                    "target_milestone": progress.public_dict(),
                    "expected_target_snapshot_sha256": str(candidate["terminal_snapshot_sha256"]),
                    "distillation_acceptance": (
                        "same expanded trainer-observed gameplay state, full processed "
                        "terminal visual, and game-area hash; emulator clocks may differ"
                    ),
                    "full_self_generated_action_count": len(full_actions),
                    "source_lineage_action_count": prefix_length,
                    "compressed_to_original": list(distilled.compressed_to_original),
                    "original_to_compressed": list(distilled.original_to_compressed),
                    "distillation": distilled.audit.as_dict(),
                    "human_actions": [],
                },
            )
            return {
                "skill_id": skill_id,
                "source_entry_id": str(source_metadata["entry_id"]),
                "source_index": source_progress.index,
                "target_entry_id": skill_id,
                "target_index": progress.index,
                "target_label": progress.label,
                "target_frame_file": target_relative,
                "target_frame_sha256": _sha256_file(target_path),
                "dataset_file": dataset_relative,
                "dataset_sha256": dataset_sha256,
                "action_count": len(compressed_actions),
                "original_action_count": len(original_actions),
                "distillation_audit_file": audit_relative,
                "distillation_audit_sha256": _sha256_file(audit_path),
                "distillation_oracle_calls": distilled.audit.total_oracle_calls,
                "distillation_oracle_actions_replayed": (distilled.audit.oracle_actions_replayed),
                "distillation_edits_accepted": (
                    distilled.audit.loop_deletions_accepted
                    + distilled.audit.chunk_deletions_accepted
                ),
                "distillation_edits_rejected": (
                    distilled.audit.loop_deletions_rejected
                    + distilled.audit.chunk_deletions_rejected
                ),
                "target_clip_channels": int(target_clip.shape[0]),
                "replay_shards": replay_shards,
                "replay_shard_example_cap": (self.student_trainer.config.max_examples_per_dataset),
                "replay_shard_burn_in": self.student_trainer.config.burn_in,
            }

        target_frame = preprocess_apprentice_frame(
            np.asarray(Image.open(source_png).convert("RGB"))
        )
        temporary_target = target_path.with_suffix(".tmp.png")
        Image.fromarray(target_frame).save(temporary_target, format="PNG")
        os.replace(temporary_target, target_path)
        edge_actions = [int(value) for value in candidate["actions"]]
        dataset = _collect_self_imitation_dataset(
            self.rom_path,
            FrozenSnapshot.from_checkpoint_dict(parent["snapshot"]),
            edge_actions,
            target_frame,
        )
        _atomic_self_imitation_dataset(dataset_path, dataset)
        source_progress = _progress_from_value(parent["progress"])
        return {
            "skill_id": skill_id,
            "source_entry_id": str(parent["entry_id"]),
            "source_index": source_progress.index,
            "target_entry_id": skill_id,
            "target_index": progress.index,
            "target_label": progress.label,
            "target_frame_file": target_relative,
            "target_frame_sha256": _sha256_file(target_path),
            "dataset_file": dataset_relative,
            "dataset_sha256": _sha256_file(dataset_path),
            "action_count": len(edge_actions),
        }

    def _commit_self_generated_skill(
        self,
        prepared: Mapping[str, Any] | list[dict[str, Any]] | None,
    ) -> None:
        if self.self_skills is None or prepared is None:
            return
        skills = prepared if isinstance(prepared, list) else [prepared]
        admitted = False
        for skill in skills:
            admitted = self.self_skills.add_verified_skill(**skill) or admitted
        if admitted:
            self.self_imitation_pending = self.self_skills.imitation_pending
            self._write_self_skills()

    def _commit_v9_candidate(
        self,
        verification: Mapping[str, Any],
        prepared: _PreparedV9Skills,
    ) -> None:
        if self.self_skills is None:
            raise RuntimeError("V9 promotion has no Student skill library")
        previous_manifest = _load_curriculum_manifest(self.curriculum_directory)
        previous_library = self.self_skills.public_dict()
        proposed_library = SelfTaughtSkillLibrary.from_dict(previous_library)
        for skill in prepared.skills:
            if not proposed_library.add_verified_skill(**skill):
                raise ValueError("V9 normalized skill batch contains a duplicate edge")
        try:
            admit_verified_candidate(self.curriculum_directory, verification)
            self._admit_v9_split_boundaries(
                prepared.graph,
                prepared.hits,
                source_entry_id=prepared.source_entry_id,
                final_entry_id=prepared.final_entry_id,
                full_actions=prepared.full_actions,
                source_prefix_length=prepared.source_prefix_length,
            )
            self.self_skills = proposed_library
            self.self_imitation_pending = proposed_library.imitation_pending
            self._write_self_skills()
        except Exception:
            _atomic_json(self.curriculum_directory / "manifest.json", previous_manifest)
            self.self_skills = SelfTaughtSkillLibrary.from_dict(previous_library)
            self.self_imitation_pending = self.self_skills.imitation_pending
            self._write_self_skills()
            raise

    def _selected_v9_practice_replays(
        self,
    ) -> tuple[dict[str, Path], list[dict[str, Any]]]:
        if not _uses_v9_practice(self.config.mode) or self.self_skills is None:
            return {}, []
        paths: dict[str, Path] = {}
        selections: list[dict[str, Any]] = []
        round_index = self.self_skills.student_training_rounds
        for skill_id, ledger in sorted(self.student_practice_ledgers.items()):
            for rung in ledger.rungs:
                rollouts = rung.successful_rollouts
                if not rollouts:
                    continue
                offset = int.from_bytes(
                    hashlib.sha256(f"{skill_id}:{rung.rung.index}".encode()).digest()[:8],
                    "big",
                )
                rollout = rollouts[(round_index + offset) % len(rollouts)]
                if not rollout.replay_shards:
                    raise ValueError("V9 retained success has no bounded replay shards")
                shard = rollout.replay_shards[
                    (round_index // len(rollouts) + offset) % len(rollout.replay_shards)
                ]
                dataset_id = f"practice-{rollout.rollout_id}"
                if dataset_id in paths:
                    raise ValueError("V9 practice replay selection repeats a rollout")
                shard_path = _validate_hashed_run_artifact(
                    self.run_directory,
                    shard["file"],
                    shard["sha256"],
                    label="V9 bounded successful-practice replay shard",
                )
                if shard_path.stat().st_size != int(shard["stored_bytes"]):
                    raise ValueError("V9 practice replay shard size disagrees with its ledger")
                paths[dataset_id] = shard_path
                selections.append(
                    {
                        "dataset_id": dataset_id,
                        "source_skill_id": skill_id,
                        "rung_index": rung.rung.index,
                        "rollout_id": rollout.rollout_id,
                        "rollout_reservoir_size": len(rollouts),
                        "shard_index": int(shard["shard_index"]),
                        "shard_count": int(shard["shard_count"]),
                        "context_examples": int(shard["context_example_count"]),
                        "train_examples": int(shard["train_example_count"]),
                        "stored_examples": int(shard["example_count"]),
                        "stored_bytes": int(shard["stored_bytes"]),
                    }
                )
        return paths, selections

    def _v9_practice_cancellation_reason(self) -> str | None:
        """Expose campaign boundaries to long, synchronous Student practice loops."""

        if self.stop_reason in V9_PRACTICE_CANCELLATION_REASONS:
            return self.stop_reason
        if (self.run_directory / "STOP").exists():
            return "stop_requested"
        if self.elapsed() >= self.config.duration_seconds:
            return "duration_limit"
        if self.model.num_timesteps >= self.config.max_actions:
            return "action_limit"
        now = time.monotonic()
        if now - self.last_v9_disk_budget_refresh >= V9_DISK_BUDGET_REFRESH_SECONDS:
            self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
            self.last_v9_disk_budget_refresh = now
        if self.cached_free_bytes < self.config.min_free_bytes:
            return "low_disk_space"
        if self.cached_run_bytes >= self.config.max_output_bytes:
            return "output_limit"
        return None

    def _v9_practice_skill(self) -> tuple[dict[str, Any], StudentPracticeLedger] | None:
        if self.self_skills is None:
            return None
        self._sync_v9_practice_ledgers()
        skills = sorted(self.self_skills.skills, key=lambda item: int(item["target_index"]))
        choices = [
            (skill, self.student_practice_ledgers[str(skill["skill_id"])]) for skill in skills
        ]
        unfinished = [item for item in choices if not item[1].curriculum_complete]
        if unfinished:
            return min(unfinished, key=lambda item: (item[1].active_rung_index, item[1].attempts))
        if not choices:
            return None
        return min(choices, key=lambda item: item[1].attempts)

    def _train_v9_success_rollout(self, path: Path, rollout_id: str, seed: int) -> None:
        if self.student_trainer is None or self.self_skills is None:
            raise RuntimeError("V9 success replay has no Student trainer")
        dataset = SelfGeneratedSkillDataset.load(path, skill_id=f"practice-{rollout_id}")
        replay = BalancedSkillReplay((dataset,), self.student_trainer.config, seed=seed)
        immediate = self.student_trainer.train(
            replay,
            updates=self.config.student_replay_epochs,
        ).public_dict()
        report = _merge_v9_success_student_report(
            self.self_skills.last_student_report,
            immediate,
        )
        self.self_skills.record_student_training(report)
        self.student_practice_training_updates += int(immediate["updates"])

    def _run_v9_practice_attempt(
        self,
        skill: Mapping[str, Any],
        ledger: StudentPracticeLedger,
    ) -> bool:
        if self.student_model is None:
            raise RuntimeError("V9 closed-loop practice has no Student model")
        choice = ledger.next_choice()
        # Persist the deterministic choice before touching the emulator. If the
        # attempt is interrupted, resume repeats this exact seed and rung.
        self._write_student_practice()
        skill_path = _validate_hashed_run_artifact(
            self.run_directory,
            skill["dataset_file"],
            skill["dataset_sha256"],
            label="V9 practice source skill",
        )
        with np.load(skill_path, allow_pickle=False) as archive:
            demonstrated_actions = np.asarray(archive["actions"], dtype=np.int64)
            target_clip = np.asarray(archive["target_pixels"], dtype=np.uint8)
        if len(demonstrated_actions) != ledger.source_action_count:
            raise ValueError("V9 practice ladder no longer matches its source skill")
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        metadata_by_id = {str(entry["entry_id"]): entry for entry in manifest["entries"]}
        source_metadata = metadata_by_id.get(str(skill["source_entry_id"]))
        if source_metadata is None:
            raise ValueError("V9 practice source curriculum entry is missing")
        target_metadata = metadata_by_id.get(str(skill["target_entry_id"]))
        if target_metadata is None:
            raise ValueError("V9 practice target curriculum entry is missing")
        source = _load_curriculum_entry(self.curriculum_directory, source_metadata)
        source_progress = _progress_from_value(source["progress"])
        target_index = int(skill["target_index"])
        target = _load_curriculum_entry(self.curriculum_directory, target_metadata)
        target_progress = _progress_from_value(target["progress"])
        if target_progress.index != target_index:
            raise ValueError("V9 practice target entry disagrees with its normalized skill")
        target_signature = _curriculum_snapshot_signature(self.rom_path, target)
        target_signature_sha256 = hashlib.sha256(repr(target_signature).encode()).hexdigest()
        pixels: list[np.ndarray] = []
        histories: list[np.ndarray] = []
        student_actions: list[int] = []
        recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
        success = False
        terminal_reason = "timeout"
        practice_snapshot: FrozenSnapshot | None = None
        practice_progress = source_progress
        previous_mode = bool(self.student_model.policy.training)
        python_state = random.getstate()
        numpy_state = np.random.get_state()
        try:
            import torch

            torch_state = torch.random.get_rng_state()
            self.student_model.set_random_seed(choice.attempt_seed)
            self.student_model.policy.set_training_mode(False)
            with PokemonRedEmulator(self.rom_path) as emulator:
                emulator.load_state(FrozenSnapshot.from_checkpoint_dict(source["snapshot"]).thaw())
                reader = PokemonRedStateReader(emulator)
                for action in demonstrated_actions[: choice.start_action]:
                    _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
                    if not _execute_action(emulator, int(action)):
                        raise RuntimeError("V9 practice ladder replay stopped")
                    self.student_practice_actions += 1
                practice_progress = milestone_progress_for_state(
                    reader.read(), inherited=source_progress
                )
                practice_snapshot = FrozenSnapshot.freeze(emulator.save_state())
                current = preprocess_apprentice_frame(emulator.screen_rgb())
                previous = current
                recurrent_state: Any | None = None
                limit = max(
                    1,
                    int(
                        np.ceil(
                            choice.remaining_actions
                            * self.config.student_practice_rollout_multiplier
                        )
                    )
                    + self.config.student_practice_rollout_slack,
                )
                for step in range(limit):
                    _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
                    observation = {
                        "pixels": np.stack((previous, current)),
                        "action_history": _action_history(recent),
                        "target_pixels": target_clip,
                    }
                    action, recurrent_state = self._predict_student_action(
                        observation,
                        recurrent_state,
                        episode_start=step == 0,
                        deterministic=False,
                    )
                    pixels.append(observation["pixels"])
                    histories.append(observation["action_history"])
                    student_actions.append(action)
                    self.student_practice_actions += 1
                    if not _execute_action(emulator, action):
                        terminal_reason = "emulator_stopped"
                        break
                    recent.append(action)
                    previous = current
                    current = preprocess_apprentice_frame(emulator.screen_rgb())
                    state = reader.read()
                    progress = milestone_progress_for_state(state, inherited=practice_progress)
                    signature_outcome = _v9_practice_signature_outcome(
                        progress.index,
                        target_index,
                        _composition_state_signature(emulator, state, progress),
                        target_signature,
                    )
                    if signature_outcome is not None:
                        terminal_reason = signature_outcome
                        success = signature_outcome == "exact_target"
                        break
        finally:
            self.student_model.policy.set_training_mode(previous_mode)
            random.setstate(python_state)
            np.random.set_state(numpy_state)
            if "torch_state" in locals():
                torch.random.set_rng_state(torch_state)

        metadata: SuccessfulRolloutMetadata | None = None
        dataset_path: Path | None = None
        if success:
            if practice_snapshot is None or not student_actions:
                raise RuntimeError("V9 successful practice has no replayable actions")
            replay_snapshot, replay_progress, _summary, _screen = _replay_sequence(
                self.rom_path,
                practice_snapshot,
                student_actions,
                practice_progress,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            self.student_practice_verification_actions += len(student_actions)
            replay_signature = _curriculum_snapshot_signature(
                self.rom_path,
                {
                    "progress": replay_progress.public_dict(),
                    "snapshot": replay_snapshot.checkpoint_dict(),
                },
            )
            replay_outcome = _v9_practice_signature_outcome(
                replay_progress.index,
                target_index,
                replay_signature,
                target_signature,
            )
            if replay_outcome != "exact_target":
                success = False
                terminal_reason = "milestone_wrong_state"
        if success:
            identity = {
                "skill_id": ledger.skill_id,
                "decision": choice.decision,
                "attempt_seed": choice.attempt_seed,
                "actions": student_actions,
                "practice_snapshot_sha256": practice_snapshot.sha256,
                "target_entry_id": str(skill["target_entry_id"]),
                "target_signature_sha256": target_signature_sha256,
            }
            rollout_id = hashlib.sha256(_canonical_json(identity)).hexdigest()
            relative = (
                f"student-practice/{ledger.skill_id}/"
                f"success-{choice.decision:08d}-{rollout_id[:16]}.npz"
            )
            dataset_path = self.run_directory / relative
            rollout_dataset = {
                "pixels": np.stack(pixels).astype(np.uint8, copy=False),
                "action_history": np.stack(histories).astype(np.float32, copy=False),
                "target_pixels": target_clip,
                "actions": np.asarray(student_actions, dtype=np.int64),
                "weights": np.ones(len(student_actions), dtype=np.float32),
                "episode_starts": np.asarray(
                    [True, *([False] * (len(student_actions) - 1))],
                    dtype=np.bool_,
                ),
            }
            _atomic_self_imitation_dataset(dataset_path, rollout_dataset)
            dataset_sha256 = _sha256_file(dataset_path)
            replay_shards = _write_v8_replay_shards(
                self.run_directory,
                skill_id=f"practice-{rollout_id}",
                dataset=rollout_dataset,
                source_dataset_sha256=dataset_sha256,
                max_examples=self.student_trainer.config.max_examples_per_dataset,
                burn_in=self.student_trainer.config.burn_in,
                cancellation_check=self._v9_practice_cancellation_reason,
            )
            self._refresh_v9_written_artifact_budget()
            _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            metadata = SuccessfulRolloutMetadata(
                rollout_id=rollout_id,
                skill_id=ledger.skill_id,
                rung_index=choice.rung_index,
                remaining_actions=choice.remaining_actions,
                attempt_seed=choice.attempt_seed,
                action_count=len(student_actions),
                dataset_file=relative,
                dataset_sha256=dataset_sha256,
                verification_id=hashlib.sha256(
                    _canonical_json(
                        {
                            "rollout_id": rollout_id,
                            "target_entry_id": str(skill["target_entry_id"]),
                            "target_signature_sha256": target_signature_sha256,
                            "replay_snapshot_sha256": replay_snapshot.sha256,
                        }
                    )
                ).hexdigest(),
                replay_shards=tuple(replay_shards),
            )
        outcome = ledger.record_attempt(choice, success=success, rollout=metadata)
        self.student_practice_terminal_reasons[terminal_reason] += 1
        if metadata is not None and dataset_path is not None:
            if outcome.rollout_retained:
                first_shard = self.run_directory / str(metadata.replay_shards[0]["file"])
                self._train_v9_success_rollout(
                    first_shard,
                    metadata.rollout_id,
                    choice.attempt_seed,
                )
            else:
                dataset_path.unlink(missing_ok=True)
                for shard in metadata.replay_shards:
                    (self.run_directory / str(shard["file"])).unlink(missing_ok=True)
        # An evicted rollout may still be referenced by the previous committed
        # checkpoint generation. Its immutable files are therefore left in place
        # for crash rollback; a later storage compactor may remove unreachable data.
        self._write_student_practice()
        self._write_self_skills()
        return outcome.promoted

    def _run_v9_practice_round(self) -> bool:
        if not _uses_v9_practice(self.config.mode):
            return False
        rollout_size = self.config.rollout_steps * self.config.environments
        explorer_rollout = self.model.num_timesteps // max(1, rollout_size)
        if (
            explorer_rollout == self.last_student_practice_rollout
            or explorer_rollout % self.config.student_practice_interval
        ):
            return False
        self.last_student_practice_rollout = explorer_rollout
        promoted = False
        for _ in range(self.config.student_practice_attempts):
            reason = self._v9_practice_cancellation_reason()
            if reason is not None:
                self.stop_reason = reason
                break
            selected = self._v9_practice_skill()
            if selected is None:
                break
            skill, ledger = selected
            try:
                promoted |= self._run_v9_practice_attempt(skill, ledger)
            except V9PracticeCancelled as cancellation:
                self.stop_reason = cancellation.reason
                break
        self._write_student_practice()
        return promoted
