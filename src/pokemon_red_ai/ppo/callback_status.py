"""Status, narrative, and dashboard payload construction for a run.

Split out of the single ``PpoRunCallback`` class. These methods were moved
verbatim; ``self`` resolution and attribute access are unchanged.
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import UTC, datetime
from typing import Any

from pokemon_red_ai.hindsight import (
    HINDSIGHT_PROTOCOL,
)
from pokemon_red_ai.milestones import HALL_OF_FAME_KEY, MILESTONES
from pokemon_red_ai.pixel_recovery import (
    PIXEL_LOOP_RECOVERY_PROTOCOL,
)
from pokemon_red_ai.ppo.artifacts import (
    _atomic_json,
)
from pokemon_red_ai.ppo.constants import (
    V10_RECOVERY_CYCLE_UNIQUE_LIMIT,
    V10_RECOVERY_CYCLE_WINDOW,
    V10_RECOVERY_STAGNATION_ACTIONS,
)
from pokemon_red_ai.ppo.curriculum import (
    _load_curriculum_manifest,
    _milestone_label,
)
from pokemon_red_ai.ppo.dashboard import _render_dashboard
from pokemon_red_ai.ppo.modes import (
    _is_distilled_student_mode,
    _is_self_taught_mode,
    _is_v12_mode,
    _ppo_protocol,
    _ppo_reward_protocol,
    _uses_pixel_recovery,
    _uses_v9_practice,
)


class StatusReportingMixin:
    """Status, narrative, and dashboard payload construction for a run."""


    def _consolidation_status(self) -> dict[str, Any]:
        if self.consolidation is None:
            return {"enabled": False}
        window = self.consolidation.active_window
        return {
            "enabled": True,
            "active_start_index": self.consolidation.active_start_index,
            "active_start_label": _milestone_label(self.consolidation.active_start_index),
            "target_index": self.consolidation.target_index,
            "target_label": _milestone_label(self.consolidation.target_index),
            "active_window_successes": sum(window),
            "active_window_attempts": len(window),
            "active_window_rate": self.consolidation.active_window_rate,
            "required_window": self.consolidation.window_size,
            "required_rate": self.consolidation.threshold,
            "gates_passed_count": len(self.consolidation.gates_passed),
            "power_on_training_gate_passed": (self.consolidation.power_on_training_gate_passed),
        }

    def _explorer_loop_recovery_status(self) -> dict[str, Any]:
        if not _uses_pixel_recovery(self.config.mode):
            return {"enabled": False}
        started = self.explorer_loop_recovery_events["windows_started"]
        escaped = self.explorer_loop_recovery_events["escapes"]
        context_changes = self.explorer_loop_recovery_events["context_changes"]
        expirations = self.explorer_loop_recovery_events["expirations"]
        completed = escaped + context_changes + expirations
        abandoned_on_resume = self.explorer_loop_recovery_events["abandoned_on_resume"]
        abandoned_on_episode_end = self.explorer_loop_recovery_events["abandoned_on_episode_end"]
        abandoned_on_campaign_end = self.explorer_loop_recovery_events["abandoned_on_campaign_end"]
        abandoned = abandoned_on_resume + abandoned_on_episode_end + abandoned_on_campaign_end
        active = sum(self.explorer_loop_recovery_active.values())
        return {
            "enabled": True,
            "protocol": PIXEL_LOOP_RECOVERY_PROTOCOL,
            "window_actions": self.config.explorer_recovery_window_actions,
            "blocked_repeat_threshold": self.config.explorer_recovery_blocked_threshold,
            "cycle_window_actions": V10_RECOVERY_CYCLE_WINDOW,
            "cycle_unique_limit": V10_RECOVERY_CYCLE_UNIQUE_LIMIT,
            "long_stagnation_actions": V10_RECOVERY_STAGNATION_ACTIONS,
            "escape_confirmations": self.config.explorer_recovery_escape_confirmations,
            "ineffective_change_fraction": (
                self.config.explorer_recovery_ineffective_change_fraction
            ),
            "ineffective_mean_absolute_error": (
                self.config.explorer_recovery_ineffective_mean_absolute_error
            ),
            "escape_change_fraction": self.config.explorer_recovery_escape_change_fraction,
            "escape_mean_absolute_error": (
                self.config.explorer_recovery_escape_mean_absolute_error
            ),
            "blocked_penalty": self.config.explorer_recovery_blocked_penalty,
            "escape_credit": self.config.explorer_recovery_escape_reward,
            "context_change_credit": 0.0,
            "expiration_penalty": self.config.explorer_recovery_expiration_penalty,
            "windows_started": started,
            "blocked_repeat_triggers": self.explorer_loop_recovery_events[
                "blocked_repeat_triggers"
            ],
            "visual_cycle_triggers": self.explorer_loop_recovery_events["visual_cycle_triggers"],
            "progress_stagnation_triggers": self.explorer_loop_recovery_events[
                "progress_stagnation_triggers"
            ],
            "escapes": escaped,
            "context_changes": context_changes,
            "expirations": expirations,
            "completed_windows": completed,
            "escape_rate": 0.0 if completed == 0 else escaped / completed,
            "abandoned_on_resume": abandoned_on_resume,
            "abandoned_on_episode_end": abandoned_on_episode_end,
            "abandoned_on_campaign_end": abandoned_on_campaign_end,
            "abandoned_windows": abandoned,
            "unresolved_windows": max(0, started - completed - abandoned - active),
            "actions": self.explorer_loop_recovery_events["actions"],
            "blocked_direction_attempts": self.explorer_loop_recovery_events[
                "blocked_direction_attempts"
            ],
            "repeated_blocked_attempts": self.explorer_loop_recovery_events[
                "repeated_blocked_attempts"
            ],
            "active_environments": active,
            "actor_action_overrides": 0,
            "uses_authored_guidance": False,
            "episode_local_state": True,
            "resume_behavior": "fresh_rollout_counts_inflight_windows_abandoned",
        }

    def _v12_learning_status(self) -> dict[str, Any]:
        if self.v12_learning is None:
            return {"enabled": False}
        rollouts = int(self.v12_learning["rollouts_observed"])
        lessons = int(self.v12_learning["lessons_generated"])
        return {
            "enabled": True,
            "protocol": HINDSIGHT_PROTOCOL,
            "rollouts_observed": rollouts,
            "rollouts_with_lessons": int(self.v12_learning["rollouts_with_lessons"]),
            "lessons_generated": lessons,
            "lessons_trained": int(self.v12_learning["lessons_trained"]),
            "examples_trained": int(self.v12_learning["examples_trained"]),
            "optimizer_updates": int(self.v12_learning["optimizer_updates"]),
            "pending_lessons": len(self.v12_learning["pending_lessons"]),
            "last_mean_loss": self.v12_learning["last_mean_loss"],
            "last_contrastive_loss": self.v12_learning.get("last_contrastive_loss"),
            "last_goal_log_probability_advantage": self.v12_learning.get(
                "last_goal_log_probability_advantage"
            ),
            "lessons_per_rollout": lessons / rollouts if rollouts else 0.0,
            "terminal_evaluation": self.v12_learning["terminal_evaluation"],
            "human_demonstration_examples": 0,
            "imported_action_examples": 0,
            "online_decision_model_calls": 0,
        }

    def _self_taught_status(self) -> dict[str, Any]:
        if self.self_skills is None:
            return {"enabled": False}
        competent = sum(bool(skill.get("competent", False)) for skill in self.self_skills.skills)
        weakest = self.self_skills.weakest_skills()
        active = weakest[0] if weakest else None
        window = [] if active is None else [bool(value) for value in active.get("window", [])]
        original_actions = sum(
            int(skill.get("original_action_count", skill["action_count"]))
            for skill in self.self_skills.skills
        )
        distilled_actions = sum(int(skill["action_count"]) for skill in self.self_skills.skills)
        sharded_skills = [skill for skill in self.self_skills.skills if skill.get("replay_shards")]
        replay_cursors = [int(skill.get("replay_cursor", 0)) for skill in sharded_skills]
        coverage_cycles = [
            int(skill.get("replay_cursor", 0)) // len(skill["replay_shards"])
            for skill in sharded_skills
        ]
        report = self.self_skills.last_student_report or {}
        diagnostics = dict(report.get("diagnostics", {}))
        competence_losses = sum(
            int(skill.get("competence_losses", 0)) for skill in self.self_skills.skills
        )
        composition_window = [bool(result) for result in self.self_skills.composition_window]
        deepest_distilled = max(
            self.self_skills.skills,
            key=lambda skill: int(skill["target_index"]),
            default=None,
        )
        deepest_competent = max(
            (skill for skill in self.self_skills.skills if bool(skill.get("competent", False))),
            key=lambda skill: int(skill["target_index"]),
            default=None,
        )
        return {
            "enabled": True,
            "skills_discovered": len(self.self_skills.skills),
            "skills_competent": competent,
            "rehearsal_attempts": self.self_skills.total_rehearsal_attempts,
            "rehearsal_successes": self.self_skills.total_rehearsal_successes,
            "weakest_skill": None if active is None else active.get("target_label"),
            "weakest_window_successes": sum(window),
            "weakest_window_attempts": len(window),
            "imitation_updates": self.self_skills.imitation_updates,
            "imitation_examples": self.self_skills.imitation_examples,
            "last_imitation_loss": self.self_skills.last_imitation_loss,
            "imitation_pending": self.self_skills.imitation_pending,
            "distillation": {
                "original_actions": original_actions,
                "distilled_actions": distilled_actions,
                "skills_distilled": sum(
                    skill.get("distillation_audit_file") is not None
                    for skill in self.self_skills.skills
                ),
                "compression_ratio": (
                    distilled_actions / original_actions if original_actions else 1.0
                ),
                "best_index": (
                    None if deepest_distilled is None else int(deepest_distilled["target_index"])
                ),
                "best_label": (
                    None if deepest_distilled is None else deepest_distilled["target_label"]
                ),
                "total_oracle_calls": sum(
                    int(skill.get("distillation_oracle_calls", 0))
                    for skill in self.self_skills.skills
                ),
                "oracle_actions_replayed": sum(
                    int(skill.get("distillation_oracle_actions_replayed", 0))
                    for skill in self.self_skills.skills
                ),
                "edits_accepted": sum(
                    int(skill.get("distillation_edits_accepted", 0))
                    for skill in self.self_skills.skills
                ),
                "edits_rejected": sum(
                    int(skill.get("distillation_edits_rejected", 0))
                    for skill in self.self_skills.skills
                ),
            },
            "student": {
                "state": (
                    "not_applicable"
                    if not _is_distilled_student_mode(self.config.mode)
                    else (
                        "training_from_self_discoveries"
                        if self.self_skills.skills
                        else "waiting_for_first_discovery"
                    )
                ),
                "training_rounds": self.self_skills.student_training_rounds,
                "optimizer_updates": self.self_skills.student_updates,
                "examples": self.self_skills.student_examples,
                "diagnostics": diagnostics,
                "replay_memory": {
                    "individual_skill_datasets": int(report.get("individual_skill_datasets", 0)),
                    "active_composition_datasets": int(report.get("composition_datasets", 0)),
                    "retained_examples": int(report.get("replay_examples_retained", 0)),
                    "retained_bytes": int(report.get("replay_bytes_retained", 0)),
                    "max_examples_per_individual_skill": int(
                        report.get("max_examples_per_individual_skill", 0)
                    ),
                    "retained_example_ceiling": int(report.get("replay_example_ceiling", 0)),
                    "train_example_ceiling": int(report.get("replay_train_example_ceiling", 0)),
                    "sampling_cycle_size": int(report.get("sampling_cycle_size", 0)),
                    "skill_shards_total": sum(
                        len(skill["replay_shards"]) for skill in sharded_skills
                    ),
                    "skill_shards_loaded": int(report.get("replay_shards_loaded", 0)),
                    "shard_examples_loaded": int(report.get("replay_shard_examples_loaded", 0)),
                    "shard_train_examples_loaded": int(
                        report.get("replay_shard_train_examples_loaded", 0)
                    ),
                    "shard_context_examples_loaded": int(
                        report.get("replay_shard_context_examples_loaded", 0)
                    ),
                    "shard_bytes_read": int(report.get("replay_shard_bytes_read", 0)),
                    "full_skill_artifacts_opened": int(
                        report.get("replay_full_skill_artifacts_opened", 0)
                    ),
                    "cursor_min": min(replay_cursors, default=0),
                    "cursor_max": max(replay_cursors, default=0),
                    "minimum_completed_coverage_cycles": int(min(coverage_cycles, default=0)),
                    "shard_selections": list(report.get("replay_shard_selections", [])),
                },
            },
            "frozen_exams": {
                "rounds": self.self_skills.frozen_exam_rounds,
                "attempts": self.self_skills.total_rehearsal_attempts,
                "successes": self.self_skills.total_rehearsal_successes,
                "actions": self.self_skills.frozen_exam_actions,
                "next_at_action": (
                    self.self_skills.last_frozen_exam_actions
                    + self.config.frozen_exam_interval_actions
                ),
                "current_skill": self.last_exam_skill_label,
                "competence_losses": competence_losses,
                "best_competent_index": (
                    None if deepest_competent is None else int(deepest_competent["target_index"])
                ),
                "best_competent_label": (
                    None if deepest_competent is None else deepest_competent["target_label"]
                ),
            },
            "composition": {
                "attempts": self.self_skills.composition_attempts,
                "successes": self.self_skills.composition_successes,
                "window_attempts": len(composition_window),
                "window_successes": sum(composition_window),
                "best_index": self.self_skills.best_composition_index,
                "best_label": _milestone_label(self.self_skills.best_composition_index),
                "hall_of_fame_completions": (self.self_skills.hall_of_fame_completions),
                "training_datasets": len(self.self_skills.active_composition_replays()),
                "archived_training_datasets": len(self.self_skills.composition_replays)
                - len(self.self_skills.active_composition_replays()),
                "training_actions": sum(
                    int(item["action_count"])
                    for item in self.self_skills.active_composition_replays()
                ),
                "build_failures": sum(
                    outcome == "replay_failed"
                    for outcome in self.self_skills.composition_build_outcomes.values()
                ),
            },
        }

    def _student_practice_status(self) -> dict[str, Any]:
        if not _uses_v9_practice(self.config.mode):
            return {"enabled": False}
        ledgers = list(self.student_practice_ledgers.values())
        active = next((ledger for ledger in ledgers if not ledger.curriculum_complete), None)
        attempts = sum(ledger.attempts for ledger in ledgers)
        successes = sum(ledger.successes for ledger in ledgers)
        retained = sum(len(rung.successful_rollouts) for ledger in ledgers for rung in ledger.rungs)
        completed = sum(ledger.curriculum_complete for ledger in ledgers)
        report = (
            {}
            if self.self_skills is None or self.self_skills.last_student_report is None
            else self.self_skills.last_student_report
        )
        return {
            "enabled": True,
            "protocol": "v9-student-closed-loop-practice-state-v1",
            "skills_with_ladders": len(ledgers),
            "skills_completed": completed,
            "attempts": attempts,
            "successes": successes,
            "success_rate": successes / attempts if attempts else 0.0,
            "emulator_actions": self.student_practice_actions,
            "verification_actions": self.student_practice_verification_actions,
            "training_updates": self.student_practice_training_updates,
            "terminal_reasons": dict(sorted(self.student_practice_terminal_reasons.items())),
            "promotion_window": self.config.student_practice_window,
            "promotion_required_successes": self.config.student_practice_required,
            "promotion_confirmations": self.config.student_practice_confirmations,
            "retention_fraction": self.config.student_practice_retention,
            "retained_success_rollouts": retained,
            "aggregated_datasets_loaded_last_round": int(
                report.get("practice_replay_datasets_loaded", 0)
            ),
            "aggregated_train_examples_last_round": int(
                report.get("practice_replay_train_examples_loaded", 0)
            ),
            "aggregated_bytes_read_last_round": int(report.get("practice_replay_bytes_read", 0)),
            "active_skill_id": None if active is None else active.skill_id,
            "active_rung_index": None if active is None else active.active_rung_index,
            "active_remaining_actions": (
                None
                if active is None or active.active_rung is None
                else active.active_rung.remaining_actions
            ),
            "closed_loop": True,
            "success_only_gradient": True,
            "recurrent_state_reset_each_attempt": True,
            "recovery_ppo": "gated_future_escalation_not_active",
        }

    def elapsed(self) -> float:
        return self.base_elapsed + time.monotonic() - self.clock_started

    def _status(
        self,
        state: str,
        reason: str | None = None,
        *,
        refresh_disk: bool = True,
    ) -> dict[str, Any]:
        manifest = _load_curriculum_manifest(self.curriculum_directory)
        best_index = int(manifest["best_milestone"]["index"])
        next_milestone = MILESTONES[best_index] if best_index < len(MILESTONES) else None
        elapsed = self.elapsed()
        rollout_size = self.config.rollout_steps * self.config.environments
        if refresh_disk:
            self.cached_run_bytes = sum(
                path.stat().st_size for path in self.run_directory.rglob("*") if path.is_file()
            )
            self.cached_free_bytes = shutil.disk_usage(self.run_directory).free
        checkpoint_hashes: dict[str, str] = {}
        checkpoint_path = self.run_directory / "checkpoint.json"
        if checkpoint_path.is_file():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            explorer_hash = checkpoint.get("model_file_sha256")
            student_hash = checkpoint.get("student_model_file_sha256")
            if isinstance(explorer_hash, str):
                checkpoint_hashes["explorer_sha256"] = explorer_hash
            if isinstance(student_hash, str):
                checkpoint_hashes["student_sha256"] = student_hash
        status = {
            "schema_version": 1,
            "protocol": _ppo_protocol(self.config.mode),
            "state": state,
            "stop_reason": reason,
            "mode": self.config.mode,
            "environments": self.config.environments,
            "started_at": self.started_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(elapsed, 3),
            "duration_seconds": self.config.duration_seconds,
            "total_actions": self.model.num_timesteps,
            "max_actions": self.config.max_actions,
            "actions_per_second": self.model.num_timesteps / max(elapsed, 0.001),
            "ppo_updates": self.model.num_timesteps // max(1, rollout_size),
            "episodes": self.episodes,
            "best_milestone": manifest["best_milestone"],
            "milestone_count": len(MILESTONES),
            "training_focus": (
                {
                    "key": next_milestone.key,
                    "label": next_milestone.label,
                    "chapter": next_milestone.chapter,
                    "kind": next_milestone.kind,
                }
                if next_milestone is not None
                else {"key": HALL_OF_FAME_KEY, "label": "Hall of Fame complete"}
            ),
            "curriculum_entries": len(manifest["entries"]),
            "verified_promotions": manifest.get("verified_promotions", 0),
            "promotion_failures": self.promotion_failures,
            "unique_positions": len(self.positions),
            "reward_components": dict(sorted(self.reward_components.items())),
            "battle_events": dict(sorted(self.battle_events.items())),
            "loop_events": dict(sorted(self.loop_events.items())),
            "episode_end_reasons": dict(sorted(self.episode_end_reasons.items())),
            "explorer_loop_recovery": self._explorer_loop_recovery_status(),
            "hindsight_learning": self._v12_learning_status(),
            "consolidation": self._consolidation_status(),
            "self_taught": self._self_taught_status(),
            "student_practice": self._student_practice_status(),
            "checkpoints": checkpoint_hashes,
            **({"v7_denominator": self.v7_denominator} if self.v7_denominator is not None else {}),
            "policy_roles": (
                {
                    "explorer": "online PPO discovery",
                    "student": "offline distilled self-replay",
                    "shared_parameters": False,
                    "competence_source": "frozen Student exams",
                }
                if _is_distilled_student_mode(self.config.mode)
                else (
                    {
                        "actor": "one recurrent goal-conditioned policy",
                        "online_ppo": "learns from every sampled consequence",
                        "hindsight": "relabels its own future visual states as local goals",
                        "verified_skills": "rehearses replay-verified rare discoveries",
                        "shared_parameters": True,
                        "competence_source": "deterministic no-update checkpoint exams",
                    }
                    if _is_v12_mode(self.config.mode)
                    else {"explorer_and_student": "one shared policy"}
                )
            ),
            "reward_protocol": _ppo_reward_protocol(self.config.mode),
            "novelty_scope": "persistent per worker across episodes and resumes",
            "information_boundary": (
                "pixels + three recent actions; trainer-only RAM rewards and loop termination"
                if self.config.mode == "pixels"
                else (
                    "Explorer: pixels + three recent actions. Separate Student: the same input "
                    "plus a three-frame self-observed goal clip. Trainer-only RAM grades rewards, "
                    "replays, and exams and switches among self-generated goal clips at declared "
                    "milestone endpoints during composition; no imported actions, route graph, "
                    "coordinates, or authored quest plan"
                    + (
                        ". Explorer loop recovery reads only rendered pixels and the exact "
                        "policy-selected action; it supplies no direction and never replaces, "
                        "masks, or chooses a button"
                        if _uses_pixel_recovery(self.config.mode)
                        else ""
                    )
                    if _is_distilled_student_mode(self.config.mode)
                    else (
                        "One recurrent actor: current/previous pixels + three recent actions + "
                        "a self-observed goal frame. During open exploration the goal is blank; "
                        "afterward, future frames from the actor's own rollout become hindsight "
                        "goals. Trainer-only RAM grades durable consequences and verifies rare "
                        "promotions, but no RAM, maps, coordinates, route, walkthrough, LLM "
                        "output, or imported action reaches the actor. Pixel recovery never "
                        "chooses or replaces a button"
                        if _is_v12_mode(self.config.mode)
                        else (
                        "pixels + three recent actions + a self-discovered target screen; "
                        "trainer-only RAM retains V7's historical route/Mart/milestone watchdog "
                        "shaping; no imported actions, actor-visible route graph, or target "
                        "coordinates"
                        if _is_self_taught_mode(self.config.mode)
                        else (
                            "pixels + three recent actions + trainer-built visited map + "
                            "active goal/skill "
                            "+ next certified route map; assisted teacher lane"
                            if self.config.mode == "assisted"
                            else "pixels + three recent actions + disclosed RAM state comparator"
                        )
                        )
                    )
                )
            ),
            "resume_semantics": (
                "exact Explorer PPO and separate Student optimizer; fresh environment rollouts"
                if _is_distilled_student_mode(self.config.mode)
                else "exact model/optimizer; fresh environment rollouts"
            ),
            "dashboard_url": f"http://127.0.0.1:{self.config.dashboard_port}/index.html",
            "run_bytes": self.cached_run_bytes,
            "free_bytes": self.cached_free_bytes,
        }
        _atomic_json(self.run_directory / "status.json", status)
        (self.run_directory / "index.html").write_text(_render_dashboard(status), encoding="utf-8")
        return status

    def _narrative(
        self,
        event: str,
        *,
        state: str = "running",
        reason: str | None = None,
    ) -> None:
        status = self._status(state, reason, refresh_disk=False)
        student_accuracy = float(
            status["self_taught"]
            .get("student", {})
            .get("diagnostics", {})
            .get("action_accuracy", 0)
        )
        path = self.run_directory / "NARRATIVE.md"
        first = not path.exists()
        action_label = (
            "Explorer actions"
            if _is_distilled_student_mode(self.config.mode)
            else "Combined actions"
        )
        exam_actor_label = "V12 checkpoint" if _is_v12_mode(self.config.mode) else "Student"
        hindsight = status.get("hindsight_learning", {})
        recovery = status.get("explorer_loop_recovery", {})
        if _uses_pixel_recovery(self.config.mode):
            loop_lines = (
                f"- Visual-loop detections: {status['loop_events'].get('visual_cycle', 0):,}\n"
                "- Long-stagnation detections: "
                f"{status['loop_events'].get('progress_stagnation', 0):,}\n\n"
            )
            recovery_lines = (
                f"- Recovery windows opened: {recovery.get('windows_started', 0):,}\n"
                f"- Blocked-repeat triggers: {recovery.get('blocked_repeat_triggers', 0):,}\n"
                f"- Visual-cycle triggers: {recovery.get('visual_cycle_triggers', 0):,}\n"
                "- Long-stagnation triggers: "
                f"{recovery.get('progress_stagnation_triggers', 0):,}\n"
                f"- Credited policy escapes: {recovery.get('escapes', 0):,}\n"
                f"- No-credit context changes: {recovery.get('context_changes', 0):,}\n"
                f"- Recovery expirations: {recovery.get('expirations', 0):,}\n"
                f"- Completed recovery windows: {recovery.get('completed_windows', 0):,}\n"
                f"- Active recovery environments: {recovery.get('active_environments', 0):,}\n"
                f"- Abandoned recovery windows: {recovery.get('abandoned_windows', 0):,}\n"
                f"- Abandoned on resume: {recovery.get('abandoned_on_resume', 0):,}\n"
                "- Abandoned at episode end: "
                f"{recovery.get('abandoned_on_episode_end', 0):,}\n"
                "- Abandoned at campaign end: "
                f"{recovery.get('abandoned_on_campaign_end', 0):,}\n"
                f"- Unresolved inactive windows: {recovery.get('unresolved_windows', 0):,}\n"
                f"- Recovery actions: {recovery.get('actions', 0):,}\n"
                f"- Trainer-selected buttons: {recovery.get('actor_action_overrides', 0):,}\n\n"
            )
        else:
            loop_lines = (
                f"- Visual loops terminated: {status['loop_events'].get('visual_cycle', 0):,}\n"
                "- Long stagnations terminated: "
                f"{status['loop_events'].get('progress_stagnation', 0):,}\n\n"
            )
            recovery_lines = ""
        with path.open("a", encoding="utf-8") as output:
            if first:
                output.write("# Parallel PPO learning chronicle\n\n")
            output.write(
                f"## {datetime.now(UTC).isoformat()} — {event}\n\n"
                f"- Best verified milestone: **{status['best_milestone']['label']}**\n"
                f"- Current lesson: **{status['training_focus']['label']}**\n"
                f"- {action_label}: {status['total_actions']:,}\n"
                f"- PPO updates: {status['ppo_updates']:,}\n"
                f"- Verified promotions: {status['verified_promotions']:,}\n"
                f"- Episodes: {status['episodes']:,}\n"
                f"- Unique map positions: {status['unique_positions']:,}\n\n"
                f"- Consolidation start: "
                f"**{status['consolidation'].get('active_start_label', 'disabled')}**\n"
                f"- Consolidation target: "
                f"**{status['consolidation'].get('target_label', 'disabled')}**\n"
                f"- Rolling training competence: "
                f"{status['consolidation'].get('active_window_successes', 0)}/"
                f"{status['consolidation'].get('active_window_attempts', 0)}\n"
                f"- Backward gates passed: "
                f"{status['consolidation'].get('gates_passed_count', 0)}\n\n"
                f"- Self-discovered skills: "
                f"{status['self_taught'].get('skills_discovered', 0)}\n"
                f"- Competent self-discovered skills: "
                f"{status['self_taught'].get('skills_competent', 0)}\n"
                f"- Self-imitation examples: "
                f"{status['self_taught'].get('imitation_examples', 0):,}\n\n"
                f"- Hindsight lessons generated: "
                f"{hindsight.get('lessons_generated', 0):,}\n"
                f"- Hindsight lessons trained: "
                f"{hindsight.get('lessons_trained', 0):,}\n"
                f"- Hindsight action examples: "
                f"{hindsight.get('examples_trained', 0):,}\n"
                f"- Latest correct-goal log-probability advantage: "
                f"{float(hindsight.get('last_goal_log_probability_advantage') or 0):.5f}\n"
                f"- Latest correct-goal contrast loss: "
                f"{float(hindsight.get('last_contrastive_loss') or 0):.5f}\n"
                f"- Online decision-model calls: "
                f"{hindsight.get('online_decision_model_calls', 0):,}\n\n"
                f"- Distilled self-generated actions: "
                f"{status['self_taught'].get('distillation', {}).get('distilled_actions', 0):,}/"
                f"{status['self_taught'].get('distillation', {}).get('original_actions', 0):,}\n"
                f"- Separate Student updates: "
                f"{status['self_taught'].get('student', {}).get('optimizer_updates', 0):,}\n"
                f"- Separate Student action accuracy: "
                f"{student_accuracy:.1%}\n"
                f"- Frozen {exam_actor_label} exams: "
                f"{status['self_taught'].get('frozen_exams', {}).get('successes', 0)}/"
                f"{status['self_taught'].get('frozen_exams', {}).get('attempts', 0)}\n"
                f"- Power-on composition exams: "
                f"{status['self_taught'].get('composition', {}).get('successes', 0)}/"
                f"{status['self_taught'].get('composition', {}).get('attempts', 0)}\n\n"
                f"- Battle successes: {status['battle_events'].get('success', 0):,}\n"
                "- Battle exits without durable progress: "
                f"{status['battle_events'].get('ended_without_progress', 0):,}\n\n"
                f"- Opponent-damage credit: "
                f"{status['reward_components'].get('opponent_damage', 0):,.2f}\n"
                f"- Net active-route credit: "
                f"{status['reward_components'].get('goal_route_progress', 0):,.2f}\n"
                f"- Navigation-recovery credit: "
                f"{status['reward_components'].get('navigation_recovery', 0):,.2f}\n"
                f"- New-best Mart approach credit: "
                f"{status['reward_components'].get('mart_approach', 0):,.2f}\n"
                f"- Mart dialogue-stage credit: "
                f"{status['reward_components'].get('mart_dialogue_progress', 0):,.2f}\n"
                f"{loop_lines}"
                f"{recovery_lines}"
            )
