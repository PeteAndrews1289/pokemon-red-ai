"""The training callback that drives evaluation, checkpointing, and promotion."""

from __future__ import annotations

import json
import random
import shutil
import time
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from pokemon_red_ai.consolidation import (
    BackwardConsolidation,
)
from pokemon_red_ai.ppo.artifacts import (
    _random_state_from_json,
    _read_gzip_json,
    _sha256_file,
)
from pokemon_red_ai.ppo.callback_persistence import RunPersistenceMixin
from pokemon_red_ai.ppo.callback_recovery import ExplorerRecoveryMixin
from pokemon_red_ai.ppo.callback_status import StatusReportingMixin
from pokemon_red_ai.ppo.callback_v8 import V8DistillationMixin
from pokemon_red_ai.ppo.callback_v9 import V9PracticeMixin
from pokemon_red_ai.ppo.callback_v12 import V12EvaluationMixin
from pokemon_red_ai.ppo.config import ParallelPpoConfig
from pokemon_red_ai.ppo.constants import (
    BaseCallback,
)
from pokemon_red_ai.ppo.curriculum import (
    _load_curriculum_manifest,
    _progress_from_value,
)
from pokemon_red_ai.ppo.distillation import (
    _PreparedV9Skills,
    _train_self_imitation_policy,
)
from pokemon_red_ai.ppo.modes import (
    _hall_of_fame_stop_is_verified,
    _is_distilled_student_mode,
    _is_self_taught_mode,
    _is_v12_mode,
    _narrative_telemetry_protocol,
    _uses_frozen_exam,
    _uses_pixel_recovery,
    _uses_v9_practice,
)
from pokemon_red_ai.ppo.promotion import admit_verified_candidate, verify_promotion_candidate
from pokemon_red_ai.ppo.telemetry import (
    V9PracticeCancelled,
    _check_v9_practice_cancellation,
    _v9_practice_terminal_reason_counts,
    _v10_narrative_telemetry,
    _validate_v12_learning_state,
)
from pokemon_red_ai.self_taught import (
    SelfTaughtSkillLibrary,
)
from pokemon_red_ai.student_practice import (
    StudentPracticeLedger,
)
from pokemon_red_ai.student_training import (
    SequenceAwareStudentTrainer,
)


class PpoRunCallback(
    StatusReportingMixin,
    RunPersistenceMixin,
    ExplorerRecoveryMixin,
    V8DistillationMixin,
    V9PracticeMixin,
    V12EvaluationMixin,
    BaseCallback,
):
    """Drives evaluation, checkpointing, promotion, and telemetry during a run.

    The behaviour lives in the mixins above, grouped by responsibility. This
    class holds construction, the Stable-Baselines3 hooks, and candidate
    handling - the parts that define when everything else runs.
    """


    def __init__(
        self,
        run_directory: Path,
        rom_path: Path,
        curriculum_directory: Path,
        config: ParallelPpoConfig,
        *,
        base_elapsed: float,
        started_at: str,
        student_model: Any | None = None,
        student_trainer: SequenceAwareStudentTrainer | None = None,
    ) -> None:
        super().__init__(verbose=0)
        self.run_directory = run_directory
        self.rom_path = rom_path
        self.curriculum_directory = curriculum_directory
        self.config = config
        self.base_elapsed = base_elapsed
        self.started_at = started_at
        self.student_model = student_model
        self.student_trainer = student_trainer
        if _is_distilled_student_mode(config.mode) != (student_model is not None):
            raise ValueError("Distilled-Student mode requires one separate Student model")
        if (student_model is None) != (student_trainer is None):
            raise ValueError("Student model and optimizer must be configured together")
        self.clock_started = time.monotonic()
        self.last_status = 0.0
        self.last_narrative = 0.0
        self.last_checkpoint_step = 0
        self.episodes = 0
        self.reward_components: Counter[str] = Counter()
        self.battle_events: Counter[str] = Counter()
        self.loop_events: Counter[str] = Counter()
        self.episode_end_reasons: Counter[str] = Counter()
        self.explorer_loop_recovery_events: Counter[str] = Counter()
        self.explorer_loop_recovery_active: dict[int, bool] = {}
        self.positions: set[tuple[int, int, int]] = set()
        self.promotion_failures = 0
        self.stop_reason: str | None = None
        self.cached_run_bytes = (
            sum(path.stat().st_size for path in self.run_directory.rglob("*") if path.is_file())
            if _uses_v9_practice(config.mode)
            else 0
        )
        self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
        self.last_v9_disk_budget_refresh = time.monotonic()
        run_manifest = json.loads(
            (self.run_directory / "manifest.json").read_text(encoding="utf-8")
        )
        checkpoint_path = self.run_directory / "checkpoint.json"
        if _uses_pixel_recovery(config.mode) and checkpoint_path.is_file():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            telemetry = _v10_narrative_telemetry(
                checkpoint.get("narrative_telemetry"),
                expected_protocol=_narrative_telemetry_protocol(config.mode),
            )
            self.episodes = telemetry["episodes"]
            self.promotion_failures = telemetry["promotion_failures"]
            self.reward_components = telemetry["reward_components"]
            self.battle_events = telemetry["battle_events"]
            self.loop_events = telemetry["loop_events"]
            self.episode_end_reasons = telemetry["episode_end_reasons"]
            self.explorer_loop_recovery_events = telemetry["explorer_loop_recovery_events"]
            self.positions = telemetry["positions"]
            self.explorer_loop_recovery_active = {
                rank: True for rank in telemetry["active_environment_ranks"]
            }
            self._abandon_active_recoveries("resume")
        self.v7_denominator = (
            dict(run_manifest["v7_denominator"])
            if isinstance(run_manifest.get("v7_denominator"), Mapping)
            else None
        )
        self.consolidation = (
            BackwardConsolidation.from_dict(
                json.loads((self.run_directory / "consolidation.json").read_text(encoding="utf-8"))
            )
            if config.consolidation
            else None
        )
        self.self_skills = (
            SelfTaughtSkillLibrary.from_dict(
                json.loads((self.run_directory / "self-skills.json").read_text(encoding="utf-8"))
            )
            if _is_self_taught_mode(config.mode)
            else None
        )
        self.self_imitation_pending = bool(
            self.self_skills is not None and self.self_skills.imitation_pending
        )
        self.last_student_replay_rollout = (
            -1 if self.self_skills is None else self.self_skills.last_student_replay_rollout
        )
        self.exam_rng = random.Random(config.seed + 80_008)
        if self.self_skills is not None and self.self_skills.exam_rng_state is not None:
            self.exam_rng.setstate(_random_state_from_json(self.self_skills.exam_rng_state))
        self.last_exam_skill_label: str | None = None
        self.student_practice_ledgers: dict[str, StudentPracticeLedger] = {}
        self.student_practice_actions = 0
        self.student_practice_verification_actions = 0
        self.student_practice_training_updates = 0
        self.student_practice_terminal_reasons: Counter[str] = Counter()
        self.last_student_practice_rollout = -1
        practice_path = self.run_directory / "student-practice.json"
        if _uses_v9_practice(config.mode) and practice_path.is_file():
            practice = json.loads(practice_path.read_text(encoding="utf-8"))
            if practice.get("schema_version") != 1 or practice.get("protocol") != (
                "v9-student-closed-loop-practice-state-v1"
            ):
                raise ValueError("V9 Student practice state has the wrong protocol")
            self.student_practice_ledgers = {
                str(item["skill_id"]): StudentPracticeLedger.from_dict(item)
                for item in practice.get("ledgers", [])
            }
            self.student_practice_actions = int(practice.get("emulator_actions", 0))
            self.student_practice_verification_actions = int(
                practice.get("verification_actions", 0)
            )
            self.student_practice_training_updates = int(practice.get("training_updates", 0))
            self.student_practice_terminal_reasons = _v9_practice_terminal_reason_counts(
                practice.get("terminal_reasons")
            )
            self.last_student_practice_rollout = int(practice.get("last_explorer_rollout", -1))
        self.v12_learning: dict[str, Any] | None = None
        v12_learning_path = self.run_directory / "v12-learning.json"
        if _is_v12_mode(config.mode):
            if not v12_learning_path.is_file():
                raise ValueError("V12 run has no hindsight learning state")
            self.v12_learning = _validate_v12_learning_state(
                json.loads(v12_learning_path.read_text(encoding="utf-8"))
            )
            for item in self.v12_learning["pending_lessons"]:
                path = self.run_directory / str(item["file"])
                if not path.is_file() or _sha256_file(path) != item["sha256"]:
                    raise ValueError("V12 pending hindsight lesson failed its recorded hash")

    def _on_rollout_start(self) -> None:
        if _is_v12_mode(self.config.mode):
            self._train_pending_v12_hindsight()
        if _is_distilled_student_mode(self.config.mode):
            if _uses_v9_practice(self.config.mode):
                reason = self._v9_practice_cancellation_reason()
                if reason is not None:
                    self.stop_reason = reason
                    return
            self._train_v8_student()
            if self._run_v9_practice_round():
                self._narrative("closed-loop Student practice expanded one rung backward")
            return
        if self.self_skills is None or not self.self_imitation_pending:
            return
        skills = self.self_skills.skills
        selected = (
            skills
            if len(skills) <= 8
            else [skills[int(index)] for index in np.linspace(0, len(skills) - 1, num=8, dtype=int)]
        )
        datasets: list[Path] = []
        for skill in selected:
            path = self.run_directory / str(skill["dataset_file"])
            if _sha256_file(path) != skill["dataset_sha256"]:
                raise ValueError("Self-imitation dataset failed its recorded hash")
            target = self.run_directory / str(skill["target_frame_file"])
            if _sha256_file(target) != skill["target_frame_sha256"]:
                raise ValueError("Self-generated visual target failed its recorded hash")
            datasets.append(path)
        result = _train_self_imitation_policy(
            self.model,
            datasets,
            epochs=self.config.self_imitation_epochs,
        )
        self.self_skills.record_imitation(
            updates=int(result["updates"]),
            examples=int(result["examples"]),
            mean_loss=float(result["mean_loss"]),
        )
        self.self_imitation_pending = self.self_skills.imitation_pending
        self._write_self_skills()
        self._narrative("rehearsed self-generated verified skills")

    def _on_rollout_end(self) -> None:
        if _is_v12_mode(self.config.mode):
            self._collect_v12_hindsight()

    def _handle_candidate(self, candidate_path: Path) -> None:
        try:
            current = _load_curriculum_manifest(self.curriculum_directory)
            candidate = _read_gzip_json(candidate_path)
            progress = _progress_from_value(candidate["progress"])
            if progress.index <= int(current["best_milestone"]["index"]):
                return
            verification = verify_promotion_candidate(
                self.rom_path,
                self.curriculum_directory,
                candidate_path,
                replay_passes=self.config.promotion_replays,
                cancellation_check=(
                    self._v9_practice_cancellation_reason
                    if _uses_v9_practice(self.config.mode)
                    else None
                ),
            )
            source_png = candidate_path.with_suffix("").with_suffix(".png")
            prepared_skill = self._prepare_self_generated_skill(verification, progress, source_png)
            if _uses_v9_practice(self.config.mode):
                _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            if isinstance(prepared_skill, _PreparedV9Skills):
                self._commit_v9_candidate(verification, prepared_skill)
            else:
                admit_verified_candidate(self.curriculum_directory, verification)
                self._commit_self_generated_skill(prepared_skill)
            if self.consolidation is not None:
                updated_manifest = _load_curriculum_manifest(self.curriculum_directory)
                self.consolidation.sync_curriculum(updated_manifest["entries"])
                self._write_consolidation()
            if source_png.is_file():
                shutil.copy2(
                    source_png,
                    self.run_directory / "milestones" / f"{progress.index:03d}-{progress.key}.png",
                )
            self._checkpoint()
            self._narrative(f"verified {progress.label}")
        except V9PracticeCancelled as cancellation:
            # Candidate preparation is intentionally staged before curriculum
            # admission. A campaign boundary can therefore discard partial private
            # artifacts without admitting a lesson or training from it.
            self.stop_reason = cancellation.reason
        except Exception as error:
            self.promotion_failures += 1
            with (self.run_directory / "verification-failures.jsonl").open(
                "a", encoding="utf-8"
            ) as output:
                output.write(
                    json.dumps(
                        {
                            "recorded_at": datetime.now(UTC).isoformat(),
                            "candidate": candidate_path.name,
                            "error": f"{type(error).__name__}: {error}",
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        competence_gate_passed = False
        self_skill_passed = False
        for info in infos:
            if not isinstance(info, Mapping):
                continue
            if info.get("episode_end"):
                self.episodes += 1
                if self.consolidation is not None:
                    competence_gate_passed |= self.consolidation.record_episode(
                        start_mode=str(info.get("start_mode", "")),
                        start_index=int(info.get("starting_milestone_index", -1)),
                        target_index=int(info.get("consolidation_target_index", -1)),
                        best_reached_index=int(info.get("episode_best_index", -1)),
                    )
                    self._write_consolidation()
                if self.self_skills is not None and not _is_v12_mode(self.config.mode):
                    self_skill_passed |= self.self_skills.record_episode(
                        mode=str(info.get("start_mode", "")),
                        skill_id=(
                            str(info["self_skill_id"])
                            if info.get("self_skill_id") is not None
                            else None
                        ),
                        best_reached_index=int(info.get("episode_best_index", -1)),
                    )
                    self._write_self_skills()
            map_id, x, y = info.get("map_id"), info.get("x"), info.get("y")
            if all(isinstance(value, int) for value in (map_id, x, y)):
                self.positions.add((map_id, x, y))
            self.reward_components.update(info.get("reward_components", {}))
            battle_event = info.get("battle_event")
            if isinstance(battle_event, str):
                self.battle_events[battle_event] += 1
            loop_event = info.get("loop_event")
            if isinstance(loop_event, str):
                self.loop_events[loop_event] += 1
            self._record_explorer_loop_recovery(info)
            end_reason = info.get("episode_end_reason")
            if isinstance(end_reason, str):
                self.episode_end_reasons[end_reason] += 1
            candidate = info.get("promotion_candidate")
            if isinstance(candidate, str):
                self._handle_candidate(Path(candidate))
                if self.stop_reason is not None:
                    break

        if (
            self.stop_reason is None
            and _uses_frozen_exam(self.config.mode)
            and self.self_skills is not None
            and self.model.num_timesteps - self.self_skills.last_frozen_exam_actions
            >= self.config.frozen_exam_interval_actions
        ):
            self_skill_passed |= self._run_frozen_exam_round()

        if competence_gate_passed:
            self._narrative("training competence gate expanded one checkpoint backward")
        if self_skill_passed:
            self._narrative("self-generated skill passed its rolling competence gate")

        elapsed = self.elapsed()
        if (self.run_directory / "STOP").exists():
            self.stop_reason = "stop_requested"
        elif elapsed >= self.config.duration_seconds:
            self.stop_reason = "duration_limit"
        elif self.model.num_timesteps >= self.config.max_actions:
            self.stop_reason = "action_limit"

        now = time.monotonic()
        if now - self.last_status >= self.config.status_seconds:
            status = self._status("running")
            if self.cached_free_bytes < self.config.min_free_bytes:
                self.stop_reason = "low_disk_space"
            elif self.cached_run_bytes >= self.config.max_output_bytes:
                self.stop_reason = "output_limit"
            elif _hall_of_fame_stop_is_verified(self.config.mode, status, self.self_skills):
                self.stop_reason = "hall_of_fame_verified"
            self.last_status = now
        if now - self.last_narrative >= self.config.narrative_seconds:
            self._narrative("scheduled observation")
            self.last_narrative = now
        if self.model.num_timesteps - self.last_checkpoint_step >= self.config.checkpoint_actions:
            self._checkpoint()
        return self.stop_reason is None
