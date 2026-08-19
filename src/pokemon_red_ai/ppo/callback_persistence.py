"""Writing run state to disk: checkpoints, ledgers, and status artifacts.

Split out of the single ``PpoRunCallback`` class. These methods were moved
verbatim; ``self`` resolution and attribute access are unchanged.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pokemon_red_ai.ppo.artifacts import (
    _atomic_json,
    _atomic_torch_checkpoint,
    _sha256_file,
)
from pokemon_red_ai.ppo.constants import (
    ACTION_HISTORY_LENGTH,
)
from pokemon_red_ai.ppo.curriculum import (
    _checkpoint_curriculum_state,
    _load_curriculum_manifest,
)
from pokemon_red_ai.ppo.modes import (
    _narrative_telemetry_protocol,
    _ppo_protocol,
    _ppo_reward_protocol,
    _uses_pixel_recovery,
    _uses_v9_practice,
)
from pokemon_red_ai.ppo.state_io import (
    _checkpoint_self_skill_state,
    _checkpoint_student_practice_state,
)
from pokemon_red_ai.ppo.telemetry import (
    _validate_v12_learning_state,
)
from pokemon_red_ai.student_practice import (
    ReversePracticeConfig,
    StudentPracticeLedger,
)


class RunPersistenceMixin:
    """Writing run state to disk: checkpoints, ledgers, and status artifacts."""


    def _write_v12_learning(self) -> None:
        if self.v12_learning is None:
            return
        self.v12_learning["updated_at"] = datetime.now(UTC).isoformat()
        validated = _validate_v12_learning_state(self.v12_learning)
        _atomic_json(self.run_directory / "v12-learning.json", validated)

    def _write_consolidation(self) -> None:
        if self.consolidation is not None:
            _atomic_json(
                self.run_directory / "consolidation.json",
                self.consolidation.public_dict(),
            )

    def _write_self_skills(self) -> None:
        if self.self_skills is not None:
            _atomic_json(
                self.run_directory / "self-skills.json",
                self.self_skills.public_dict(),
            )

    def _write_student_practice(self) -> None:
        if not _uses_v9_practice(self.config.mode):
            return
        _atomic_json(
            self.run_directory / "student-practice.json",
            {
                "schema_version": 1,
                "protocol": "v9-student-closed-loop-practice-state-v1",
                "updated_at": datetime.now(UTC).isoformat(),
                "last_explorer_rollout": self.last_student_practice_rollout,
                "emulator_actions": self.student_practice_actions,
                "verification_actions": self.student_practice_verification_actions,
                "training_updates": self.student_practice_training_updates,
                "terminal_reasons": dict(sorted(self.student_practice_terminal_reasons.items())),
                "ledgers": [
                    ledger.public_dict()
                    for _skill_id, ledger in sorted(self.student_practice_ledgers.items())
                ],
            },
        )

    def _checkpoint(self) -> None:
        latest = self.run_directory / "ppo-latest.zip"
        previous = self.run_directory / "ppo-previous.zip"
        temporary = self.run_directory / "ppo-checkpoint.tmp.zip"
        novelty_files = self.training_env.env_method(
            "save_novelty_checkpoint", self.model.num_timesteps
        )
        self.model.save(temporary)
        if latest.exists():
            os.replace(latest, previous)
        os.replace(temporary, latest)
        run_manifest = json.loads(
            (self.run_directory / "manifest.json").read_text(encoding="utf-8")
        )
        checkpoint: dict[str, Any] = {
            "schema_version": 1,
            "protocol": _ppo_protocol(self.config.mode),
            "reward_protocol": _ppo_reward_protocol(self.config.mode),
            "model_file_sha256": _sha256_file(latest),
            "total_actions": self.model.num_timesteps,
            "elapsed_seconds": self.elapsed(),
            "config": self.config.public_dict(),
            "source": run_manifest["source"],
            "rom": run_manifest["rom"],
            "best_milestone": _load_curriculum_manifest(self.curriculum_directory)[
                "best_milestone"
            ],
            "novelty_files": novelty_files,
            "resume_semantics": "model_optimizer_exact_environment_rollout_restarts",
        }
        if _uses_pixel_recovery(self.config.mode):
            checkpoint["narrative_telemetry"] = {
                "protocol": _narrative_telemetry_protocol(self.config.mode),
                "episodes": self.episodes,
                "promotion_failures": self.promotion_failures,
                "reward_components": dict(sorted(self.reward_components.items())),
                "battle_events": dict(sorted(self.battle_events.items())),
                "loop_events": dict(sorted(self.loop_events.items())),
                "episode_end_reasons": dict(sorted(self.episode_end_reasons.items())),
                "explorer_loop_recovery_events": dict(
                    sorted(self.explorer_loop_recovery_events.items())
                ),
                "positions": [list(item) for item in sorted(self.positions)],
                "active_environment_ranks": sorted(
                    rank for rank, active in self.explorer_loop_recovery_active.items() if active
                ),
                "episode_local_recovery_state_persisted": False,
            }
        if self.v12_learning is not None:
            self._write_v12_learning()
            learning_path = self.run_directory / "v12-learning.json"
            checkpoint.update(
                {
                    "v12_learning_file": learning_path.name,
                    "v12_learning_file_sha256": _sha256_file(learning_path),
                    "hindsight_pending_lessons": len(
                        self.v12_learning["pending_lessons"]
                    ),
                    "online_decision_model_calls": 0,
                    "network_gameplay_calls": 0,
                }
            )
        if isinstance(run_manifest.get("v7_denominator"), Mapping):
            checkpoint["v7_denominator"] = dict(run_manifest["v7_denominator"])
        if self.student_model is not None and self.student_trainer is not None:
            student_latest = self.run_directory / "student-latest.zip"
            student_previous = self.run_directory / "student-previous.zip"
            student_temporary = self.run_directory / "student-checkpoint.tmp.zip"
            self.student_model.save(student_temporary)
            if student_latest.exists():
                os.replace(student_latest, student_previous)
            os.replace(student_temporary, student_latest)
            optimizer_path = self.run_directory / "student-optimizer.pt"
            optimizer_previous = self.run_directory / "student-optimizer.previous.pt"
            if optimizer_path.exists():
                os.replace(optimizer_path, optimizer_previous)
            _atomic_torch_checkpoint(
                optimizer_path,
                self.student_trainer.optimizer_state_dict(),
            )
            checkpoint.update(
                {
                    "student_model_file": student_latest.name,
                    "student_model_file_sha256": _sha256_file(student_latest),
                    "student_optimizer_file": optimizer_path.name,
                    "student_optimizer_file_sha256": _sha256_file(optimizer_path),
                    "student_training_isolated_from_ppo": True,
                }
            )
        if self.consolidation is not None:
            self._write_consolidation()
            checkpoint["consolidation_file_sha256"] = _sha256_file(
                self.run_directory / "consolidation.json"
            )
        if self.self_skills is not None:
            self._write_self_skills()
            checkpoint.update(_checkpoint_self_skill_state(self.run_directory))
        if _uses_v9_practice(self.config.mode):
            self._write_student_practice()
            checkpoint.update(_checkpoint_student_practice_state(self.run_directory))
        checkpoint.update(
            _checkpoint_curriculum_state(
                self.run_directory,
                self.curriculum_directory,
                protocol=_ppo_protocol(self.config.mode),
            )
        )
        _atomic_json(
            self.run_directory / "checkpoint.json",
            checkpoint,
        )
        self.last_checkpoint_step = self.model.num_timesteps

    def _refresh_v9_written_artifact_budget(self) -> None:
        """Refresh output accounting after a synchronous V9 artifact batch."""

        self.cached_run_bytes = sum(
            path.stat().st_size for path in self.run_directory.rglob("*") if path.is_file()
        )
        self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
        self.last_v9_disk_budget_refresh = time.monotonic()

    def _sync_v9_practice_ledgers(self) -> None:
        if not _uses_v9_practice(self.config.mode) or self.self_skills is None:
            return
        settings = ReversePracticeConfig(
            first_rung_actions=8,
            promotion_window=self.config.student_practice_window,
            promotion_required_successes=self.config.student_practice_required,
            promotion_confirmations=self.config.student_practice_confirmations,
            retention_fraction=self.config.student_practice_retention,
            success_reservoir_capacity=self.config.student_practice_reservoir,
            action_history_length=ACTION_HISTORY_LENGTH,
        )
        changed = False
        for skill in self.self_skills.skills:
            skill_id = str(skill["skill_id"])
            if skill_id in self.student_practice_ledgers:
                continue
            self.student_practice_ledgers[skill_id] = StudentPracticeLedger.initialize(
                skill_id=skill_id,
                source_action_count=int(skill["action_count"]),
                seed=self.config.seed + int(skill["target_index"]) * 10_007,
                config=settings,
            )
            changed = True
        if changed:
            self._write_student_practice()
