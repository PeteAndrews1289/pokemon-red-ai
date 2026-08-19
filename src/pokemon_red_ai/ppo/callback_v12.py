"""The v12 evaluation path: terminal exams, blank-goal probes, and hindsight.

Split out of the single ``PpoRunCallback`` class. These methods were moved
verbatim; ``self`` resolution and attribute access are unchanged.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from pokemon_red_ai.apprentice_data import preprocess_apprentice_frame
from pokemon_red_ai.blind import (
    FrozenSnapshot,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    milestone_progress_for_state,
)
from pokemon_red_ai.hindsight import (
    HindsightConfig,
    extract_hindsight_lessons,
)
from pokemon_red_ai.milestones import HALL_OF_FAME_KEY, MILESTONES
from pokemon_red_ai.ppo.artifacts import (
    _atomic_json,
    _random_state_to_json,
    _sha256_file,
)
from pokemon_red_ai.ppo.constants import (
    ACTION_HISTORY_LENGTH,
)
from pokemon_red_ai.ppo.curriculum import (
    _load_curriculum_entry,
    _load_curriculum_manifest,
    _milestone_label,
    _progress_from_value,
)
from pokemon_red_ai.ppo.distillation import (
    _atomic_self_imitation_dataset,
    _hindsight_goal_log_probability_advantage,
    _train_self_imitation_policy,
)
from pokemon_red_ai.ppo.modes import (
    _is_v12_mode,
    _uses_frozen_exam,
    _uses_v9_practice,
)
from pokemon_red_ai.ppo.observations import _action_history, _execute_action
from pokemon_red_ai.ppo.telemetry import (
    V9PracticeCancelled,
    _check_v9_practice_cancellation,
)
from pokemon_red_ai.self_taught import (
    choose_v8_self_taught_episode,
)
from pokemon_red_ai.state import (
    PokemonRedStateReader,
)


class V12EvaluationMixin:
    """The v12 evaluation path: terminal exams, blank-goal probes, and hindsight."""


    def _collect_v12_hindsight(self) -> None:
        if self.v12_learning is None:
            return
        if self.v12_learning["pending_lessons"]:
            raise RuntimeError("V12 cannot overwrite untrained hindsight lessons")
        buffer = self.model.rollout_buffer
        observations = buffer.observations
        if not isinstance(observations, Mapping):
            raise RuntimeError("V12 requires a dictionary recurrent rollout buffer")
        lessons = extract_hindsight_lessons(
            np.asarray(observations["pixels"]),
            np.asarray(observations["action_history"]),
            np.asarray(buffer.actions),
            np.asarray(buffer.episode_starts),
            HindsightConfig(
                max_lessons=self.config.hindsight_max_lessons,
                min_actions=self.config.hindsight_min_actions,
                max_actions=self.config.hindsight_max_actions,
                min_changed_fraction=self.config.hindsight_min_changed_fraction,
                min_mean_absolute_error=(self.config.hindsight_min_mean_absolute_error),
            ),
        )
        self.v12_learning["rollouts_observed"] += 1
        if lessons:
            self.v12_learning["rollouts_with_lessons"] += 1
        pending: list[dict[str, Any]] = []
        rollout = int(self.v12_learning["rollouts_observed"])
        for index, lesson in enumerate(lessons):
            relative = Path("hindsight") / (
                f"pending-rollout-{rollout:08d}-lesson-{index:03d}.npz"
            )
            path = self.run_directory / relative
            _atomic_self_imitation_dataset(path, lesson.dataset())
            pending.append(
                {
                    **lesson.public_dict(),
                    "file": relative.as_posix(),
                    "sha256": _sha256_file(path),
                    "stored_bytes": path.stat().st_size,
                }
            )
        self.v12_learning["lessons_generated"] += len(pending)
        self.v12_learning["pending_lessons"] = pending
        self._write_v12_learning()
        with (self.run_directory / "hindsight" / "audit.jsonl").open(
            "a", encoding="utf-8"
        ) as output:
            output.write(
                json.dumps(
                    {
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "rollout": rollout,
                        "total_actions": self.model.num_timesteps,
                        "lessons": pending,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    def _train_pending_v12_hindsight(self) -> bool:
        if self.v12_learning is None or not self.v12_learning["pending_lessons"]:
            return False
        pending = list(self.v12_learning["pending_lessons"])
        paths: list[Path] = []
        for item in pending:
            path = self.run_directory / str(item["file"])
            if not path.is_file() or _sha256_file(path) != item["sha256"]:
                raise ValueError("V12 pending hindsight lesson changed before training")
            paths.append(path)
        result = _train_self_imitation_policy(
            self.model,
            paths,
            epochs=self.config.hindsight_epochs,
            counterfactual_blank_weight=self.config.hindsight_contrastive_weight,
            counterfactual_margin=self.config.hindsight_contrastive_margin,
        )
        self.v12_learning["lessons_trained"] += len(paths)
        self.v12_learning["examples_trained"] += int(result["examples"])
        self.v12_learning["optimizer_updates"] += int(result["updates"])
        self.v12_learning["last_mean_loss"] = float(result["mean_loss"])
        self.v12_learning["last_contrastive_loss"] = float(result["mean_contrastive_loss"])
        self.v12_learning["last_goal_log_probability_advantage"] = (
            _hindsight_goal_log_probability_advantage(self.model, paths)
        )
        self.v12_learning["pending_lessons"] = []
        self._write_v12_learning()
        for path in paths:
            path.unlink(missing_ok=True)
        return True

    def _run_frozen_exam_round(self) -> bool:
        if self.self_skills is None or not _uses_frozen_exam(self.config.mode):
            return False
        if not self.self_skills.skills:
            self.self_skills.last_frozen_exam_actions = self.model.num_timesteps
            self._write_self_skills()
            return False
        evaluation_model = self.model if _is_v12_mode(self.config.mode) else self.student_model
        if evaluation_model is None:
            return False
        previous_mode = bool(evaluation_model.policy.training)
        previous_exam_rng_state = self.exam_rng.getstate()
        evaluation_model.policy.set_training_mode(False)
        actions = 0
        competence_passed = False
        try:
            if _uses_v9_practice(self.config.mode):
                _check_v9_practice_cancellation(self._v9_practice_cancellation_reason)
            manifest = _load_curriculum_manifest(self.curriculum_directory)
            choice = choose_v8_self_taught_episode(
                manifest["entries"],
                self.self_skills,
                self.exam_rng,
                frontier_probability=0,
            )
            if choice.skill_id is not None:
                skill = self.self_skills.skill(choice.skill_id)
                self.last_exam_skill_label = str(skill["target_label"])
                success, best, used = self._run_frozen_skill_attempt(skill)
                actions += used
                competence_passed |= self.self_skills.record_episode(
                    mode=choice.mode,
                    skill_id=choice.skill_id,
                    best_reached_index=(int(skill["target_index"]) if success else best),
                )
            else:
                chain = self._competent_skill_chain()
                self.last_exam_skill_label = "Power-on composition"
                target_index = int(chain[-1]["target_index"]) if chain else 0
                hall_of_fame_target = (
                    target_index > 0 and MILESTONES[target_index - 1].key == HALL_OF_FAME_KEY
                )
                success, used = self._run_frozen_composition_attempt(chain)
                actions += used
                self.self_skills.record_composition_exam(
                    success=success,
                    actions=used,
                    target_index=target_index,
                    hall_of_fame_target=hall_of_fame_target,
                )
        except V9PracticeCancelled as cancellation:
            self.exam_rng.setstate(previous_exam_rng_state)
            self.stop_reason = cancellation.reason
            return False
        finally:
            evaluation_model.policy.set_training_mode(previous_mode)
        self.self_skills.record_frozen_exam_round(actions=actions)
        self.self_skills.last_frozen_exam_actions = self.model.num_timesteps
        self.self_skills.exam_rng_state = _random_state_to_json(self.exam_rng.getstate())
        self._write_self_skills()
        self._checkpoint()
        exam_label = "V12 checkpoint" if _is_v12_mode(self.config.mode) else "Student"
        self._narrative(
            f"frozen {exam_label} exam: {self.last_exam_skill_label or 'unknown skill'}"
        )
        return competence_passed

    def _run_v12_terminal_evaluation(self) -> dict[str, Any] | None:
        """Evaluate the terminal V12 checkpoint once with no learning or restored subskills."""

        if self.v12_learning is None or self.self_skills is None:
            return None
        model_path = self.run_directory / "ppo-latest.zip"
        if not model_path.is_file():
            raise RuntimeError("V12 terminal evaluation has no sealed policy checkpoint")
        chain = self._competent_skill_chain()
        previous_mode = bool(self.model.policy.training)
        self.model.policy.set_training_mode(False)
        try:
            if chain:
                target_index = int(chain[-1]["target_index"])
                target_label = _milestone_label(target_index)
                success, actions = self._run_frozen_composition_attempt(chain)
                best_index = target_index if success else 0
                best_label = _milestone_label(best_index)
                evaluation_mode = "competent_self_generated_goal_chain"
            else:
                target_index = len(MILESTONES)
                target_label = "Hall of Fame"
                success, best_index, actions = self._run_v12_blank_goal_attempt(
                    self.config.terminal_evaluation_actions
                )
                best_label = _milestone_label(best_index)
                evaluation_mode = "unguided_blank_goal_from_power_on"
        finally:
            self.model.policy.set_training_mode(previous_mode)
        hall_of_fame_target = (
            target_index > 0 and MILESTONES[target_index - 1].key == HALL_OF_FAME_KEY
        )
        if chain:
            self.self_skills.record_composition_exam(
                success=success,
                actions=actions,
                target_index=target_index,
                hall_of_fame_target=hall_of_fame_target,
            )
            self._write_self_skills()
        result = {
            "protocol": "v12-terminal-frozen-composition-v1",
            "evaluated_at": datetime.now(UTC).isoformat(),
            "policy_file": model_path.name,
            "policy_sha256": _sha256_file(model_path),
            "policy_actions": actions,
            "policy_updates_during_evaluation": 0,
            "restores_between_skills": 0,
            "trainer_selected_buttons": 0,
            "evaluation_mode": evaluation_mode,
            "competent_skill_count": len(chain),
            "skill_ids": [str(skill["skill_id"]) for skill in chain],
            "target_index": target_index,
            "target_label": target_label,
            "best_index": best_index,
            "best_label": best_label,
            "success": success,
            "hall_of_fame_target": hall_of_fame_target,
            "hall_of_fame_verified": bool(success and hall_of_fame_target),
        }
        self.v12_learning["terminal_evaluation"] = result
        self._write_v12_learning()
        _atomic_json(self.run_directory / "terminal-evaluation.json", result)
        return result

    def _run_v12_blank_goal_attempt(self, limit: int) -> tuple[bool, int, int]:
        """Give the terminal actor one deterministic, blank-goal run from exact power-on."""

        if limit < 1:
            raise ValueError("V12 blank-goal evaluation limit must be positive")
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        roots = [entry for entry in manifest["entries"] if int(entry["milestone_index"]) == 0]
        if len(roots) != 1:
            raise ValueError("V12 terminal evaluation requires one power-on root")
        root = _load_curriculum_entry(self.curriculum_directory, roots[0])
        inherited = _progress_from_value(root["progress"])
        recent: deque[int] = deque([-1] * ACTION_HISTORY_LENGTH, maxlen=ACTION_HISTORY_LENGTH)
        recurrent_state: Any | None = None
        best = inherited.index
        actions = 0
        with PokemonRedEmulator(self.rom_path) as emulator:
            emulator.load_state(FrozenSnapshot.from_checkpoint_dict(root["snapshot"]).thaw())
            reader = PokemonRedStateReader(emulator)
            current = preprocess_apprentice_frame(emulator.screen_rgb())
            previous = current
            for step in range(limit):
                action, recurrent_state = self._predict_student_action(
                    {
                        "pixels": np.stack((previous, current)),
                        "action_history": _action_history(recent),
                        "target_pixels": np.zeros((1, 72, 80), dtype=np.uint8),
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
                best = max(best, progress.index)
                if progress.key == HALL_OF_FAME_KEY:
                    return True, best, actions
        return False, best, actions
