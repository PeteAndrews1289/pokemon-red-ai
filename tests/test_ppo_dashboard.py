from __future__ import annotations

from pokemon_red_ai.ppo_dashboard import render_ppo_dashboard


def test_version_7_dashboard_retains_legacy_story_and_metrics() -> None:
    page = render_ppo_dashboard(
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
            "best_milestone": {"index": 1, "label": "Reached Route 1"},
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
    assert "One agent explores" not in page
    assert "How deep is the learning?" not in page
    assert "Self-imitation examples" in page
    assert "Consolidation start" in page
    assert "Navigation-recovery credit" in page
    assert "Battle successes" in page
    assert ">3<" in page
    assert "No-progress battle exits" in page
    assert ">7<" in page
    assert "pixels + three recent actions; trainer-only RAM rewards" in page
    assert page.count("Environment ") == 8


def test_version_8_dashboard_separates_explorer_student_and_exams() -> None:
    page = render_ppo_dashboard(
        {
            "state": "running",
            "mode": "self_taught_v8",
            "protocol": "parallel-recurrent-ppo-v8",
            "reward_protocol": "distilled-self-generated-skills-v1",
            "environments": 4,
            "total_actions": 1_250_000,
            "actions_per_second": 518.4,
            "elapsed_seconds": 3_661,
            "best_milestone": {"index": 14, "label": "Reached Cerulean City"},
            "checkpoints": {
                "explorer_sha256": "0123456789abcdef0123456789abcdef",
                "student_sha256": "fedcba9876543210fedcba9876543210",
            },
            "v7_denominator": {
                "locked": True,
                "run_id": "parallel-ppo-v7-24h",
                "total_actions": 6_000_000,
                "best_index": 3,
                "best_label": "Reached Viridian City",
                "checkpoint_sha256": "aabbccddeeff00112233445566778899",
                "source_state_at_lock": "running",
            },
            "information_boundary": (
                "Explorer sees pixels; Student sees pixels, recent actions, and a self-observed "
                "three-frame target clip"
            ),
            "self_taught": {
                "skills_discovered": 5,
                "skills_competent": 3,
                "distillation": {
                    "original_actions": 1_000,
                    "distilled_actions": 400,
                    "skills_distilled": 5,
                    "best_index": 12,
                    "best_label": "Defeated Brock",
                    "total_oracle_calls": 87,
                    "oracle_actions_replayed": 12_345,
                    "edits_accepted": 11,
                    "edits_rejected": 74,
                },
                "student": {
                    "state": "training between PPO rollouts",
                    "training_rounds": 7,
                    "optimizer_updates": 35,
                    "examples": 4_096,
                    "diagnostics": {
                        "action_nll": 0.725,
                        "action_accuracy": 0.625,
                        "policy_entropy": 1.401,
                        "demonstration_entropy": 1.233,
                    },
                    "replay_memory": {
                        "skill_shards_total": 23,
                        "skill_shards_loaded": 5,
                        "shard_train_examples_loaded": 2_048,
                        "shard_context_examples_loaded": 256,
                        "shard_bytes_read": 3_145_728,
                        "full_skill_artifacts_opened": 0,
                        "minimum_completed_coverage_cycles": 2,
                        "sampling_cycle_size": 10,
                        "retained_bytes": 12_582_912,
                    },
                },
                "frozen_exams": {
                    "rounds": 4,
                    "attempts": 40,
                    "successes": 29,
                    "next_at_action": 1_500_000,
                    "current_skill": "Reach Viridian City",
                    "competence_losses": 1,
                    "best_competent_index": 8,
                    "best_competent_label": "Delivered Oak's Parcel",
                },
                "composition": {
                    "attempts": 10,
                    "successes": 3,
                    "window_attempts": 10,
                    "window_successes": 3,
                    "best_index": 6,
                    "best_label": "Received Pokédex",
                    "hall_of_fame_completions": 0,
                },
            },
        }
    )

    assert "One agent explores" in page
    assert "Explorer actions" in page
    assert "Combined actions" not in page
    assert "EXPLORER · LIVE PPO" in page
    assert "STUDENT · SEPARATE NETWORK" in page
    assert "The Student never receives authored demonstrations" in page
    assert "How deep is the learning?" in page
    assert "Discovery depth" in page
    assert "milestone 14 of 66" in page
    assert "Distilled library depth" in page
    assert "milestone 12 of 66" in page
    assert "Frozen local competence" in page
    assert "milestone 8 of 66" in page
    assert "Restore-free composition" in page
    assert "milestone 6 of 66" in page
    assert "Discovery distillation" in page
    assert "1,000" in page
    assert "400" in page
    assert "600" in page
    assert "2.50× shorter" in page
    assert ">40.0%<" in page
    assert "Replay-oracle calls" in page and ">87<" in page
    assert "Actions replayed by oracle" in page and ">12,345<" in page
    assert "Proposed edits accepted" in page and ">11<" in page
    assert "Proposed edits rejected" in page and ">74<" in page
    assert "Student updates" in page
    assert ">35<" in page
    assert "Action accuracy" in page
    assert "62.5%" in page
    assert "Action NLL" in page
    assert "0.725" in page
    assert "Bounded skill shards" in page and "5/23 loaded" in page
    assert "Owned / context examples" in page and "2,048 / 256" in page
    assert "Shard bytes read this round" in page and "3.0 MiB" in page
    assert "Full skill files opened" in page and ">0<" in page
    assert "Minimum full-coverage cycles" in page and ">2<" in page
    assert "Weighted replay cycle" in page and "10 tickets" in page
    assert "Retained replay memory" in page and "12.0 MiB" in page
    assert "Frozen exams: can it reproduce the lesson?" in page
    assert "self-generated goal clips at declared RAM milestone endpoints" in page
    assert "29/40" in page
    assert "72%" in page
    assert "at action 1,500,000" in page
    assert "Composition exam record" in page
    assert "3/10" in page
    assert 'id="frame-heartbeat"' in page
    assert 'data-updated-at=""' in page
    assert "Explorer frames are temporarily paused" in page
    assert "synchronous Student" in page
    assert "replay, practice, or an exam" in page
    assert "Best restore-free depth" in page
    assert "Received Pokédex" in page
    assert "Hall-of-Fame completions" in page
    assert "continuous frozen-Student runs from power-on" in page
    assert "Explorer checkpoint" in page and "0123456789ab" in page
    assert "Student checkpoint" in page and "fedcba987654" in page
    assert "LOCKED V7 SNAPSHOT" in page
    assert "parallel-ppo-v7-24h" in page
    assert "6,000,000 actions" in page
    assert "aabbccddeeff" in page
    assert "source was running at lock" in page
    assert page.count("Explorer environment ") == 8


def test_version_8_dashboard_accepts_flat_status_counters() -> None:
    page = render_ppo_dashboard(
        {
            "state": "running",
            "mode": "self_taught_v8",
            "distillation_original_actions": 50,
            "distilled_actions_total": 10,
            "student_training_rounds": 2,
            "student_updates": 8,
            "student_examples": 64,
            "student_action_accuracy": 0.5,
            "frozen_exam_attempts": 6,
            "frozen_exam_successes": 3,
            "skills_discovered": 2,
            "skills_competent": 1,
            "composition_attempts": 1,
            "composition_successes": 1,
        }
    )

    assert "5.00× shorter" in page
    assert "80.0%" in page
    assert "Student updates" in page and ">8<" in page
    assert "3/6" in page
    assert "1/2" in page
    assert "1/1" in page


def test_version_9_dashboard_explains_closed_loop_reverse_practice() -> None:
    page = render_ppo_dashboard(
        {
            "state": "running",
            "mode": "self_taught_v9",
            "protocol": "parallel-recurrent-ppo-v9",
            "reward_protocol": "self-correcting-student-v1",
            "student_practice": {
                "enabled": True,
                "skills_with_ladders": 3,
                "skills_completed": 1,
                "promotion_window": 30,
                "promotion_required_successes": 27,
                "promotion_confirmations": 2,
                "attempts": 20,
                "successes": 16,
                "terminal_reasons": {
                    "exact_target": 16,
                    "timeout": 2,
                    "emulator_stopped": 1,
                    "milestone_wrong_state": 1,
                },
                "retained_success_rollouts": 11,
                "emulator_actions": 2_400,
                "verification_actions": 310,
                "training_updates": 16,
                "active_rung_index": 2,
                "active_remaining_actions": 32,
                "success_only_gradient": True,
                "recurrent_state_reset_each_attempt": True,
                "recovery_ppo": "gated_future_escalation_not_active",
            },
        }
    )

    assert "Closed-loop practice: can it recover from its own mistakes?" in page
    assert "Practice ladders completed" in page and "1/3" in page
    assert "Practice promotion gate" in page and "27/30 × 2" in page
    assert "Verified practice record" in page and "16/20" in page
    assert "80%" in page
    assert "Exact-target attempts" in page and ">16<" in page
    assert "Wrong-state milestone hits" in page and ">1<" in page
    assert "Practice timeouts" in page and ">2<" in page
    assert "Practice emulator stops" in page and ">1<" in page
    assert "rung 3 · last 32 actions" in page
    assert "Successful rollouts retained" in page and ">11<" in page
    assert "Closed-loop practice actions" in page and ">2,400<" in page
    assert "Replay-verification actions" in page and ">310<" in page
    assert "Failed attempts enter gradient" in page and ">no<" in page
    assert "Recovery PPO escalation" in page and ">not active<" in page


def test_version_10_dashboard_exposes_policy_controlled_recovery_denominators() -> None:
    page = render_ppo_dashboard(
        {
            "state": "running",
            "mode": "self_taught_v10",
            "protocol": "parallel-recurrent-ppo-v10",
            "reward_protocol": "recovery-before-reset-v1",
            "explorer_loop_recovery": {
                "enabled": True,
                "protocol": "pixels-only-loop-recovery-v1",
                "windows_started": 12,
                "blocked_repeat_triggers": 7,
                "visual_cycle_triggers": 3,
                "progress_stagnation_triggers": 2,
                "escapes": 4,
                "context_changes": 2,
                "expirations": 3,
                "completed_windows": 9,
                "abandoned_windows": 1,
                "abandoned_on_resume": 1,
                "abandoned_on_episode_end": 0,
                "abandoned_on_campaign_end": 0,
                "unresolved_windows": 0,
                "actions": 321,
                "blocked_direction_attempts": 99,
                "repeated_blocked_attempts": 44,
                "active_environments": 2,
                "actor_action_overrides": 0,
            },
        }
    )

    assert "Explorer loop recovery: did it escape without a reset?" in page
    assert "Recovery windows opened" in page and ">12<" in page
    assert "Credited policy escapes" in page and ">4<" in page
    assert "Recovery escape rate" in page and ">44%<" in page
    assert "Completed recovery windows" in page and ">9<" in page
    assert "Context changes (no credit)" in page and ">2<" in page
    assert "Expired and reset" in page and ">3<" in page
    assert "Abandoned windows" in page and ">1<" in page
    assert "Abandoned on resume" in page and ">1<" in page
    assert "Abandoned at episode end" in page and ">0<" in page
    assert "Abandoned at campaign end" in page and ">0<" in page
    assert "Unresolved inactive windows" in page and ">0<" in page
    assert "Recovery actions" in page and ">321<" in page
    assert "Active recovery environments" in page and ">2<" in page
    assert "Blocked-repeat triggers" in page and ">7<" in page
    assert "Visual-cycle triggers" in page and ">3<" in page
    assert "Long-stagnation triggers" in page and ">2<" in page
    assert "Blocked direction attempts" in page and ">99<" in page
    assert "Repeated blocked attempts" in page and ">44<" in page
    assert "Trainer-selected buttons" in page and ">0<" in page
    assert "dialogue or menu changes" in page
    assert "no-credit context changes" in page
    assert "visual-cycle or long-stagnation lesson" in page
    assert "No route, coordinate, preferred direction, mask, or forced action" in page


def test_version_12_dashboard_explains_hindsight_and_terminal_evidence() -> None:
    page = render_ppo_dashboard(
        {
            "state": "running",
            "mode": "self_taught_v12",
            "protocol": "parallel-recurrent-ppo-v12",
            "reward_protocol": "self-generated-hindsight-goals-v1",
            "hindsight_learning": {
                "enabled": True,
                "rollouts_observed": 20,
                "rollouts_with_lessons": 18,
                "lessons_generated": 288,
                "lessons_trained": 272,
                "examples_trained": 21_760,
                "optimizer_updates": 272,
                "pending_lessons": 16,
                "last_mean_loss": 1.2345,
                "online_decision_model_calls": 0,
                "terminal_evaluation": None,
            },
            "explorer_loop_recovery": {"enabled": True},
            "self_taught": {
                "skills_discovered": 2,
                "skills_competent": 1,
                "frozen_exams": {"rounds": 3, "attempts": 3, "successes": 1},
                "composition": {"attempts": 1, "successes": 0},
            },
        }
    )

    assert "Every journey creates" in page
    assert "Hindsight: is ordinary experience becoming a lesson?" in page
    assert "Hindsight goals created" in page and ">288<" in page
    assert "Self-generated action examples" in page and ">21,760<" in page
    assert "Online LLM decisions" in page and ">0<" in page
    assert "Terminal clean-start exam" in page and "not run yet" in page
    assert "One agent explores" not in page


def test_dashboard_escapes_public_labels_and_survives_missing_v8_metrics() -> None:
    page = render_ppo_dashboard(
        {
            "state": '<script id="bad">alert(1)</script>',
            "mode": "self_taught_v8",
            "updated_at": '"><script>alert(2)</script>',
            "environments": 1,
            "best_milestone": {"label": "<b>fake milestone</b>"},
            "self_taught": {
                "student": {"state": "<img src=x onerror=alert(3)>"},
                "frozen_exams": {"current_skill": "<em>fake skill</em>"},
            },
        }
    )

    assert '<script id="bad">' not in page
    assert "<script>alert(2)</script>" not in page
    assert "<img src=x onerror=alert(3)>" not in page
    assert "<img src=x" not in page
    assert "<em>fake skill" not in page
    assert "&lt;script id=&quot;bad&quot;&gt;" in page
    assert "&lt;b&gt;fake milestone&lt;/b&gt;" in page
    assert "waiting for first verified discovery" in page
    assert "awaiting schedule" in page
    assert page.count("not recorded yet") >= 8
