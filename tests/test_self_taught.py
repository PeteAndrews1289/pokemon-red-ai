from __future__ import annotations

import random

from pokemon_red_ai.self_taught import (
    SelfTaughtSkillLibrary,
    choose_self_taught_episode,
)


def entries(*indices: int) -> list[dict[str, int | str]]:
    return [
        {"entry_id": f"entry-{index}", "milestone_index": index} for index in indices
    ]


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
    library = SelfTaughtSkillLibrary.initialize(
        curriculum, window_size=10, threshold=0.8
    )

    entry, mode, target, skill_id, frame = choose_self_taught_episode(
        curriculum, library, random.Random(1), frontier_probability=0
    )

    assert entry["entry_id"] == "entry-0"
    assert mode == "self_frontier"
    assert target == 0
    assert skill_id is frame is None


def test_verified_self_generated_skill_is_rehearsed_and_gated() -> None:
    curriculum = entries(0, 1)
    library = SelfTaughtSkillLibrary.initialize(
        entries(0), window_size=5, threshold=0.8
    )
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
        assert not library.record_episode(
            mode=mode, skill_id=skill_id, best_reached_index=best
        )
    assert library.record_episode(mode=mode, skill_id=skill_id, best_reached_index=1)
    assert library.skill(skill_id)["competent"] is True


def test_weakest_unlearned_skill_receives_rehearsal_priority() -> None:
    curriculum = entries(0, 1, 2)
    library = SelfTaughtSkillLibrary.initialize(
        entries(0), window_size=2, threshold=1
    )
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
    library = SelfTaughtSkillLibrary.initialize(
        entries(0), window_size=10, threshold=0.8
    )
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
    library = SelfTaughtSkillLibrary.initialize(
        entries(0), window_size=10, threshold=0.8
    )
    add_skill(library, 0, 1)

    restored = SelfTaughtSkillLibrary.from_dict(library.public_dict())

    assert restored.imitation_pending is True
