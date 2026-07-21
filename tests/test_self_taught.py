from __future__ import annotations

import random

from pokemon_red_ai.self_taught import (
    SelfTaughtSkillLibrary,
    choose_self_taught_episode,
    choose_v8_self_taught_episode,
)


def entries(*indices: int) -> list[dict[str, int | str]]:
    return [{"entry_id": f"entry-{index}", "milestone_index": index} for index in indices]


def add_skill(library: SelfTaughtSkillLibrary, source: int, target: int) -> None:
    assert library.add_verified_skill(
        skill_id=f"skill-{source}-{target}",
        source_entry_id=f"entry-{source}",
        source_index=source,
        target_entry_id=f"entry-{target}",
        target_index=target,
        target_label=f"Target {target}",
        target_frame_file=f"self-skills/skill-{source}-{target}.png",
        target_frame_sha256="a" * 64,
        dataset_file=f"self-skills/skill-{source}-{target}.npz",
        dataset_sha256="b" * 64,
        action_count=12,
    )


def test_empty_library_can_only_explore_from_its_own_frontier() -> None:
    curriculum = entries(0)
    library = SelfTaughtSkillLibrary.initialize(curriculum, window_size=10, threshold=0.8)

    entry, mode, target, skill_id, frame = choose_self_taught_episode(
        curriculum, library, random.Random(1), frontier_probability=0
    )

    assert entry["entry_id"] == "entry-0"
    assert mode == "self_frontier"
    assert target == 0
    assert skill_id is frame is None


def test_verified_self_generated_skill_is_rehearsed_and_gated() -> None:
    curriculum = entries(0, 1)
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=5, threshold=0.8)
    add_skill(library, 0, 1)

    entry, mode, target, skill_id, frame = choose_self_taught_episode(
        curriculum, library, random.Random(2), frontier_probability=0
    )

    assert entry["entry_id"] == "entry-0"
    assert mode == "self_rehearsal"
    assert target == 1
    assert skill_id == "skill-0-1"
    assert frame == "self-skills/skill-0-1.png"

    for best in (1, 1, 1, 0):
        assert not library.record_episode(mode=mode, skill_id=skill_id, best_reached_index=best)
    assert library.record_episode(mode=mode, skill_id=skill_id, best_reached_index=1)
    assert library.skill(skill_id)["competent"] is True


def test_weakest_unlearned_skill_receives_rehearsal_priority() -> None:
    curriculum = entries(0, 1, 2)
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    add_skill(library, 0, 1)
    add_skill(library, 1, 2)
    first = library.skill("skill-0-1")
    first["attempts"] = 2
    first["successes"] = 2
    first["window"] = [True, True]
    first["competent"] = True

    entry, mode, target, skill_id, _frame = choose_self_taught_episode(
        curriculum, library, random.Random(3), frontier_probability=0
    )

    assert entry["entry_id"] == "entry-1"
    assert mode == "self_rehearsal"
    assert target == 2
    assert skill_id == "skill-1-2"


def test_library_round_trip_and_imitation_accounting() -> None:
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=10, threshold=0.8)
    add_skill(library, 0, 1)
    assert library.imitation_pending is True
    library.record_imitation(updates=3, examples=24, mean_loss=0.75)

    restored = SelfTaughtSkillLibrary.from_dict(library.public_dict())

    assert restored.skills == library.skills
    assert restored.imitation_updates == 3
    assert restored.imitation_examples == 24
    assert restored.last_imitation_loss == 0.75
    assert restored.imitation_pending is False


def test_pending_self_imitation_survives_restart() -> None:
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=10, threshold=0.8)
    add_skill(library, 0, 1)

    restored = SelfTaughtSkillLibrary.from_dict(library.public_dict())

    assert restored.imitation_pending is True


def test_v8_distillation_student_and_exam_evidence_survive_restart() -> None:
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    assert library.add_verified_skill(
        skill_id="skill-0-1",
        source_entry_id="entry-0",
        source_index=0,
        target_entry_id="entry-1",
        target_index=1,
        target_label="Target 1",
        target_frame_file="self-skills/skill-0-1.png",
        target_frame_sha256="a" * 64,
        dataset_file="self-skills/skill-0-1.npz",
        dataset_sha256="b" * 64,
        action_count=7,
        original_action_count=21,
        distillation_audit_file="self-skills/skill-0-1.distillation.json",
        distillation_audit_sha256="c" * 64,
        target_clip_channels=3,
    )
    library.record_student_training(
        {
            "updates": 2,
            "train_examples": 14,
            "diagnostics": {"action_accuracy": 0.75},
        }
    )
    library.last_student_replay_rollout = 42
    library.exam_rng_state = [3, [1, 2, 3], None]
    library.record_frozen_exam_round(actions=28)
    library.last_frozen_exam_actions = 250_000
    library.record_composition_exam(
        success=True,
        actions=12,
        target_index=1,
        hall_of_fame_target=False,
    )

    restored = SelfTaughtSkillLibrary.from_dict(library.public_dict())

    skill = restored.skill("skill-0-1")
    assert skill["action_count"] == 7
    assert skill["original_action_count"] == 21
    assert skill["compression_ratio"] == 1 / 3
    assert skill["target_clip_channels"] == 3
    assert restored.student_updates == 2
    assert restored.student_examples == 14
    assert restored.last_student_report == library.last_student_report
    assert restored.last_student_replay_rollout == 42
    assert restored.exam_rng_state == [3, [1, 2, 3], None]
    assert restored.frozen_exam_rounds == 1
    assert restored.frozen_exam_actions == 28
    assert restored.last_frozen_exam_actions == 250_000
    assert restored.composition_window == [True]
    assert restored.best_composition_index == 1
    assert restored.hall_of_fame_completions == 0


def test_verified_composition_is_persisted_but_exam_failure_is_evaluation_only() -> None:
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    add_skill(library, 0, 1)
    add_skill(library, 1, 2)
    for skill_id in ("skill-0-1", "skill-1-2"):
        skill = library.skill(skill_id)
        skill["competent"] = True
        skill["window"] = [True, True]
    fingerprint = "c" * 64

    assert library.add_verified_composition(
        composition_id="composition-c",
        fingerprint=fingerprint,
        skill_ids=("skill-0-1", "skill-1-2"),
        target_index=2,
        dataset_file="self-skills/composition-c.npz",
        dataset_sha256="d" * 64,
        audit_file="self-skills/composition-c.audit.json",
        audit_sha256="e" * 64,
        action_count=24,
        goal_switch_offsets=(12,),
        full_action_count=24,
        full_goal_switch_offsets=(12,),
        excerpt_offsets=(0, 24),
        successful_replays=1,
    )
    before_replays = list(library.composition_replays)
    before_pending = library.imitation_pending
    library.record_composition_exam(success=False, actions=24, target_index=2)

    assert library.composition_replays == before_replays
    assert library.imitation_pending is before_pending
    restored = SelfTaughtSkillLibrary.from_dict(library.public_dict())
    assert restored.composition_replays == library.composition_replays
    assert restored.composition_build_outcomes == {fingerprint: "verified"}


def test_composition_admission_rejects_disconnected_or_unverified_data() -> None:
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    add_skill(library, 0, 1)
    add_skill(library, 1, 2)
    for skill in library.skills:
        skill["competent"] = True

    kwargs = {
        "composition_id": "composition-a",
        "fingerprint": "a" * 64,
        "skill_ids": ("skill-0-1", "skill-1-2"),
        "target_index": 2,
        "dataset_file": "self-skills/composition-a.npz",
        "dataset_sha256": "b" * 64,
        "audit_file": "self-skills/composition-a.audit.json",
        "audit_sha256": "c" * 64,
        "action_count": 24,
        "goal_switch_offsets": (12,),
        "full_action_count": 24,
        "full_goal_switch_offsets": (12,),
        "excerpt_offsets": (0, 24),
        "successful_replays": 0,
    }
    import pytest

    with pytest.raises(ValueError, match="successful continuous replay"):
        library.add_verified_composition(**kwargs)

    library.skill("skill-1-2")["source_entry_id"] = "entry-disconnected"
    kwargs["successful_replays"] = 1
    with pytest.raises(ValueError, match="continuous chain from power-on"):
        library.add_verified_composition(**kwargs)


def test_only_deepest_verified_composition_is_active_after_round_trip() -> None:
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    for source, target in ((0, 1), (1, 2), (2, 3)):
        add_skill(library, source, target)
        library.skill(f"skill-{source}-{target}")["competent"] = True

    def add_composition(identifier: str, skill_ids: tuple[str, ...]) -> None:
        count = len(skill_ids) * 8
        switches = tuple(range(8, count, 8))
        assert library.add_verified_composition(
            composition_id=identifier,
            fingerprint=("a" if len(skill_ids) == 2 else "b") * 64,
            skill_ids=skill_ids,
            target_index=len(skill_ids),
            dataset_file=f"self-skills/{identifier}.npz",
            dataset_sha256="c" * 64,
            audit_file=f"self-skills/{identifier}.audit.json",
            audit_sha256="d" * 64,
            action_count=count,
            goal_switch_offsets=switches,
            full_action_count=count,
            full_goal_switch_offsets=switches,
            excerpt_offsets=tuple(index * count // len(switches) for index in range(len(switches)))
            + (count,),
            successful_replays=1,
        )

    add_composition("two", ("skill-0-1", "skill-1-2"))
    add_composition("three", ("skill-0-1", "skill-1-2", "skill-2-3"))

    assert [item["composition_id"] for item in library.active_composition_replays()] == ["three"]
    restored = SelfTaughtSkillLibrary.from_dict(library.public_dict())
    assert len(restored.composition_replays) == 2
    assert [item["composition_id"] for item in restored.active_composition_replays()] == ["three"]


def test_v8_scheduler_blocks_downstream_until_prerequisite_is_competent() -> None:
    curriculum = entries(0, 1, 2)
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    add_skill(library, 0, 1)
    add_skill(library, 1, 2)

    first = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(1),
        frontier_probability=0,
        minimum_evaluation_attempts=2,
    )
    assert first.mode == "self_evaluation"
    assert first.skill_id == "skill-0-1"
    assert first.reason == "minimum_evaluation_quota"
    assert first.prerequisite_skill_ids == ()
    assert (
        library.record_episode(mode=first.mode, skill_id=first.skill_id, best_reached_index=1)
        is False
    )

    second = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(2),
        frontier_probability=0,
        minimum_evaluation_attempts=2,
    )
    assert second.skill_id == "skill-0-1"
    assert (
        library.record_episode(mode=second.mode, skill_id=second.skill_id, best_reached_index=1)
        is True
    )

    downstream = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(3),
        frontier_probability=0,
        minimum_evaluation_attempts=2,
    )
    assert downstream.mode == "self_evaluation"
    assert downstream.skill_id == "skill-1-2"
    assert downstream.prerequisite_skill_ids == ("skill-0-1",)
    assert downstream.entry["entry_id"] == "entry-1"


def test_v8_evaluation_quota_rotates_between_eligible_skills() -> None:
    curriculum = entries(0, 1, 2)
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=3, threshold=1)
    add_skill(library, 0, 1)
    add_skill(library, 0, 2)

    first = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(4),
        frontier_probability=0,
        minimum_evaluation_attempts=2,
    )
    assert first.skill_id is not None
    library.record_episode(mode=first.mode, skill_id=first.skill_id, best_reached_index=0)
    second = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(5),
        frontier_probability=0,
        minimum_evaluation_attempts=2,
    )

    assert second.mode == "self_evaluation"
    assert second.reason == "minimum_evaluation_quota"
    assert second.skill_id in {"skill-0-1", "skill-0-2"} - {first.skill_id}


def test_v8_finishes_evaluation_quota_even_after_early_competence() -> None:
    curriculum = entries(0, 1)
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    add_skill(library, 0, 1)

    for seed in (12, 13):
        choice = choose_v8_self_taught_episode(
            curriculum,
            library,
            random.Random(seed),
            frontier_probability=0,
            minimum_evaluation_attempts=3,
        )
        library.record_episode(mode=choice.mode, skill_id=choice.skill_id, best_reached_index=1)
    assert library.skill("skill-0-1")["competent"] is True

    final_evaluation = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(14),
        frontier_probability=0,
        minimum_evaluation_attempts=3,
    )
    assert final_evaluation.mode == "self_evaluation"
    assert final_evaluation.skill_id == "skill-0-1"


def test_v8_retention_is_periodic_and_can_revoke_competence() -> None:
    curriculum = entries(0, 1)
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    add_skill(library, 0, 1)
    skill_id = "skill-0-1"

    for seed in (6, 7):
        choice = choose_v8_self_taught_episode(
            curriculum,
            library,
            random.Random(seed),
            frontier_probability=0,
            retention_interval=2,
        )
        library.record_episode(mode=choice.mode, skill_id=choice.skill_id, best_reached_index=1)
    assert library.skill(skill_id)["competent"] is True

    waiting = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(8),
        frontier_probability=0,
        retention_interval=2,
    )
    assert waiting.mode == "self_frontier"
    assert waiting.reason == "all_available_skills_qualified"

    retention = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(9),
        frontier_probability=0,
        retention_interval=2,
    )
    assert retention.mode == "self_retention"
    assert retention.reason == "periodic_retention_due"
    library.record_episode(
        mode=retention.mode,
        skill_id=retention.skill_id,
        best_reached_index=0,
    )

    skill = library.skill(skill_id)
    assert skill["competent"] is False
    assert skill["competence_losses"] == 1
    assert skill["last_retention_decision"] == library.v8_schedule_decisions


def test_v8_frontier_allocation_and_scheduler_state_are_explicit() -> None:
    curriculum = entries(0, 1)
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    add_skill(library, 0, 1)

    choice = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(10),
        frontier_probability=1,
    )

    assert choice.mode == "self_frontier"
    assert choice.reason == "configured_frontier_allocation"
    assert choice.legacy_tuple() == (
        choice.entry,
        choice.mode,
        choice.target_index,
        choice.skill_id,
        choice.target_frame_file,
    )
    restored = SelfTaughtSkillLibrary.from_dict(library.public_dict())
    assert restored.v8_schedule_decisions == 1
    assert restored.skill("skill-0-1")["last_retention_decision"] == 0


def test_v8_disconnected_skill_is_not_rehearsed() -> None:
    curriculum = entries(0, 1, 2)
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    add_skill(library, 1, 2)

    choice = choose_v8_self_taught_episode(
        curriculum,
        library,
        random.Random(11),
        frontier_probability=0,
    )

    assert choice.mode == "self_frontier"
    assert choice.reason == "all_rehearsals_blocked_by_prerequisites"


def test_v8_retention_quota_cannot_starve_a_late_unqualified_skill() -> None:
    curriculum = entries(*range(53))
    library = SelfTaughtSkillLibrary.initialize(entries(0), window_size=2, threshold=1)
    for target in range(1, 52):
        add_skill(library, 0, target)
        skill = library.skill(f"skill-0-{target}")
        skill["attempts"] = 2
        skill["successes"] = 2
        skill["window"] = [True, True]
        skill["competent"] = True
    add_skill(library, 0, 52)

    choices = [
        choose_v8_self_taught_episode(
            curriculum,
            library,
            random.Random(seed),
            frontier_probability=0,
            retention_interval=5,
        )
        for seed in range(20)
    ]

    assert sum(choice.mode == "self_retention" for choice in choices) == 4
    assert sum(choice.skill_id == "skill-0-52" for choice in choices) == 16
