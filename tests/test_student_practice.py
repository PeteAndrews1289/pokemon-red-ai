from __future__ import annotations

from copy import deepcopy

import pytest

from pokemon_red_ai.student_practice import (
    ACTOR_OBSERVATION_KEYS,
    ZERO_STATE_PROTOCOL,
    PracticeChoice,
    PracticeOutcome,
    ReversePracticeConfig,
    StudentPracticeLedger,
    SuccessfulRolloutMetadata,
    actor_practice_contract,
    build_reverse_practice_rungs,
)


def rollout_for(
    choice: PracticeChoice,
    index: int,
    *,
    skill_id: str = "skill-opening",
) -> SuccessfulRolloutMetadata:
    return SuccessfulRolloutMetadata(
        rollout_id=f"rollout-{index}",
        skill_id=skill_id,
        rung_index=choice.rung_index,
        remaining_actions=choice.remaining_actions,
        attempt_seed=choice.attempt_seed,
        action_count=max(1, choice.remaining_actions - index % 3),
        dataset_file=f"student-practice/rollout-{index}.npz",
        dataset_sha256=f"{index % 16:x}" * 64,
        verification_id=f"verification-{index}",
    )


def record_success(ledger: StudentPracticeLedger, index: int) -> PracticeOutcome:
    choice = ledger.next_choice()
    return ledger.record_attempt(
        choice,
        success=True,
        rollout=rollout_for(choice, index, skill_id=ledger.skill_id),
    )


def test_reverse_ladder_doubles_to_full_without_duplicate_terminal_rung() -> None:
    rungs = build_reverse_practice_rungs(300)

    assert [rung.remaining_actions for rung in rungs] == [8, 16, 32, 64, 128, 256, 300]
    assert [rung.start_action for rung in rungs] == [292, 284, 268, 236, 172, 44, 0]
    assert [rung.index for rung in rungs] == list(range(7))
    assert [rung.remaining_actions for rung in build_reverse_practice_rungs(64)] == [
        8,
        16,
        32,
        64,
    ]
    assert [rung.remaining_actions for rung in build_reverse_practice_rungs(5)] == [5]


@pytest.mark.parametrize("fraction", [0.19, 0.26])
def test_retention_fraction_is_bounded(fraction: float) -> None:
    with pytest.raises(ValueError, match="between 20% and 25%"):
        ReversePracticeConfig(retention_fraction=fraction)


def test_first_rung_is_frozen_at_eight_actions() -> None:
    with pytest.raises(ValueError, match="eight-action first rung"):
        ReversePracticeConfig(first_rung_actions=4)
    with pytest.raises(ValueError, match="eight-action first rung"):
        build_reverse_practice_rungs(64, first_rung_actions=4)


def test_two_fixed_passing_windows_promote_one_rung() -> None:
    config = ReversePracticeConfig(
        promotion_window=4,
        promotion_required_successes=3,
        promotion_confirmations=2,
        success_reservoir_capacity=16,
    )
    ledger = StudentPracticeLedger.initialize(
        skill_id="skill-opening",
        source_action_count=16,
        seed=17,
        config=config,
    )

    outcomes = [record_success(ledger, index) for index in range(3)]
    choice = ledger.next_choice()
    first_window = ledger.record_attempt(choice, success=False)

    assert not any(outcome.promoted for outcome in outcomes)
    assert first_window.window is not None
    assert first_window.window.successes == 3
    assert first_window.window.passed is True
    assert first_window.window.consecutive_confirmations == 1
    assert first_window.promoted is False

    for index in range(4, 7):
        record_success(ledger, index)
    choice = ledger.next_choice()
    second_window = ledger.record_attempt(choice, success=False)

    assert second_window.promoted is True
    assert second_window.window is not None
    assert second_window.window.consecutive_confirmations == 2
    assert ledger.active_rung_index == 1
    assert ledger.active_rung is not None
    assert ledger.active_rung.remaining_actions == 16


@pytest.mark.parametrize(
    ("retention_fraction", "expected"),
    [(0.20, 4), (0.25, 5)],
)
def test_retention_scheduler_delivers_declared_share_without_starving_current_rung(
    retention_fraction: float,
    expected: int,
) -> None:
    config = ReversePracticeConfig(
        promotion_window=1,
        promotion_required_successes=1,
        promotion_confirmations=1,
        retention_fraction=retention_fraction,
    )
    ledger = StudentPracticeLedger.initialize(
        skill_id="skill-opening",
        source_action_count=16,
        seed=29,
        config=config,
    )
    assert record_success(ledger, 0).promoted is True

    modes: list[str] = []
    for _ in range(20):
        choice = ledger.next_choice()
        modes.append(choice.mode)
        ledger.record_attempt(choice, success=False)

    assert modes.count("retention") == expected
    assert modes.count("current") == 20 - expected
    assert ledger.active_rung_index == 1
    assert ledger.rungs[0].retention_attempts == expected
    assert ledger.rungs[1].attempts == 20 - expected


def test_success_reservoir_is_capped_success_only_and_seed_deterministic() -> None:
    config = ReversePracticeConfig(
        promotion_window=100,
        promotion_required_successes=100,
        success_reservoir_capacity=3,
    )
    ledgers = [
        StudentPracticeLedger.initialize(
            skill_id="skill-opening",
            source_action_count=32,
            seed=41,
            config=config,
        )
        for _ in range(2)
    ]

    for index in range(12):
        for ledger in ledgers:
            record_success(ledger, index)

    retained = [item.rollout_id for item in ledgers[0].rungs[0].successful_rollouts]
    assert retained == [item.rollout_id for item in ledgers[1].rungs[0].successful_rollouts]
    assert len(retained) == 3
    assert ledgers[0].rungs[0].successful_rollouts_seen == 12
    round_trip = StudentPracticeLedger.from_dict(ledgers[0].public_dict())
    assert round_trip.public_dict() == ledgers[0].public_dict()

    choice = ledgers[0].next_choice()
    with pytest.raises(ValueError, match="failed Student attempt"):
        ledgers[0].record_attempt(
            choice,
            success=False,
            rollout=rollout_for(choice, 99),
        )
    assert ledgers[0].next_choice() == choice
    ledgers[0].record_attempt(choice, success=False)


def test_pending_choice_and_future_seeds_resume_exactly() -> None:
    ledger = StudentPracticeLedger.initialize(
        skill_id="skill-opening",
        source_action_count=80,
        seed=73,
    )
    first = ledger.next_choice()
    restored = StudentPracticeLedger.from_dict(ledger.public_dict())

    assert restored.next_choice() == first
    ledger.record_attempt(first, success=False)
    restored.record_attempt(first, success=False)
    assert restored.next_choice() == ledger.next_choice()
    assert restored.public_dict() == ledger.public_dict()


def test_completed_curriculum_continues_as_retention_and_resumes() -> None:
    config = ReversePracticeConfig(
        promotion_window=1,
        promotion_required_successes=1,
        promotion_confirmations=1,
    )
    ledger = StudentPracticeLedger.initialize(
        skill_id="skill-short",
        source_action_count=5,
        seed=79,
        config=config,
    )
    assert record_success(ledger, 0).curriculum_complete is True

    choice = ledger.next_choice()
    assert choice.mode == "retention"
    assert choice.remaining_actions == 5
    restored = StudentPracticeLedger.from_dict(ledger.public_dict())
    assert restored.next_choice() == choice
    restored.record_attempt(choice, success=False)
    assert restored.curriculum_complete is True
    assert restored.rungs[0].retention_attempts == 1


def test_resume_rejects_tampered_ladder_pending_seed_and_actor_contract() -> None:
    ledger = StudentPracticeLedger.initialize(
        skill_id="skill-opening",
        source_action_count=65,
        seed=91,
    )
    ledger.next_choice()

    ladder_tamper = deepcopy(ledger.public_dict())
    ladder_tamper["rungs"][1]["rung"]["remaining_actions"] = 17
    with pytest.raises(ValueError, match="rung ladder"):
        StudentPracticeLedger.from_dict(ladder_tamper)

    seed_tamper = deepcopy(ledger.public_dict())
    seed_tamper["pending_choice"]["attempt_seed"] += 1
    with pytest.raises(ValueError, match="not reproducible"):
        StudentPracticeLedger.from_dict(seed_tamper)

    disclosure_tamper = deepcopy(ledger.public_dict())
    disclosure_tamper["actor_contract"]["rung_index"] = 0
    with pytest.raises(ValueError, match="actor contract"):
        StudentPracticeLedger.from_dict(disclosure_tamper)


def test_actor_reset_is_zero_state_and_contains_no_trainer_scheduling_fields() -> None:
    ledger = StudentPracticeLedger.initialize(
        skill_id="secret-skill-id",
        source_action_count=128,
        seed=103,
    )
    choice = ledger.next_choice()
    actor = choice.actor_reset()

    assert actor == actor_practice_contract()
    assert actor["observation_keys"] == list(ACTOR_OBSERVATION_KEYS)
    assert actor["recurrent_state"] == "zeros"
    assert actor["action_history"] == [-1, -1, -1]
    assert actor["initial_frame_history"] == "duplicate_current"
    assert actor["reset_protocol"] == ZERO_STATE_PROTOCOL
    serialized = repr(actor).lower()
    for private_value in (
        ledger.skill_id.lower(),
        "rung_index",
        "remaining_actions",
        "start_action",
        "checkpoint",
    ):
        assert private_value not in serialized


def test_success_metadata_must_match_pending_choice_and_replay_provenance() -> None:
    ledger = StudentPracticeLedger.initialize(
        skill_id="skill-opening",
        source_action_count=32,
        seed=113,
    )
    choice = ledger.next_choice()
    wrong_skill = rollout_for(choice, 0, skill_id="some-other-skill")

    with pytest.raises(ValueError, match="does not match"):
        ledger.record_attempt(choice, success=True, rollout=wrong_skill)
    assert ledger.attempts == 0
    assert ledger.next_choice() == choice

    with pytest.raises(ValueError, match="artifact identity"):
        SuccessfulRolloutMetadata(
            rollout_id="bad-artifact",
            skill_id=ledger.skill_id,
            rung_index=choice.rung_index,
            remaining_actions=choice.remaining_actions,
            attempt_seed=choice.attempt_seed,
            action_count=4,
            dataset_file="../escape.npz",
            dataset_sha256="not-a-hash",
            verification_id="verification",
        )
