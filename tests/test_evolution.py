from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_ai.blind import BLIND_ACTIONS, visual_signature
from pokemon_red_ai.evolution import (
    HIDDEN_UNITS,
    PARAMETER_COUNT,
    EvolutionConfig,
    EvolutionElite,
    EvolutionGenome,
    QualityDiversityArchive,
    RecurrentPixelPolicy,
    behavior_descriptor,
    fitness_vector,
    run_evolution_experiment,
)
from pokemon_red_ai.rom import ROM_ENVIRONMENT_VARIABLE, verify_rom


def test_genome_round_trip_mutation_and_inference_are_deterministic() -> None:
    parent = EvolutionGenome.random(7)
    restored = EvolutionGenome.from_checkpoint_dict(parent.checkpoint_dict())
    child_a, changed_a = restored.mutate(seed=9, probability=0.1, sigma=0.05)
    child_b, changed_b = restored.mutate(seed=9, probability=0.1, sigma=0.05)
    pixels = np.zeros((144, 160, 3), dtype=np.uint8)
    first_policy = RecurrentPixelPolicy(child_a)
    second_policy = RecurrentPixelPolicy(child_b)

    first_actions = []
    second_actions = []
    previous_first = None
    previous_second = None
    for _ in range(12):
        previous_first = first_policy.select(visual_signature(pixels), previous_first)
        previous_second = second_policy.select(visual_signature(pixels), previous_second)
        first_actions.append(previous_first)
        second_actions.append(previous_second)

    assert PARAMETER_COUNT == 13_096
    assert HIDDEN_UNITS == 32
    assert parent.genome_id == restored.genome_id
    assert child_a.genome_id == child_b.genome_id != parent.genome_id
    assert changed_a == changed_b > 0
    assert first_actions == second_actions
    assert all(0 <= action < len(BLIND_ACTIONS) for action in first_actions)


def test_quality_diversity_archive_preserves_cells_and_replaces_only_improvements() -> None:
    archive = QualityDiversityArchive(2)

    def elite(seed: int, descriptor: tuple[int, int, int, int], score: int) -> EvolutionElite:
        return EvolutionElite(
            genome=EvolutionGenome.random(seed),
            parent_id=None,
            generation=0,
            descriptor=descriptor,
            fitness=(score,),
            metrics={"maps_seen": score},
            mutation_seed=None,
            mutation_sigma=0,
            mutated_parameters=0,
        )

    first = elite(1, (1, 1, 0, 0), 5)
    worse = elite(2, (1, 1, 0, 0), 4)
    better = elite(3, (1, 1, 0, 0), 6)
    different = elite(4, (2, 2, 0, 0), 1)
    overflow = elite(5, (3, 3, 0, 0), 10)

    assert archive.consider(first) == (True, None)
    assert archive.consider(worse) == (False, first.genome.genome_id)
    assert archive.consider(better) == (True, first.genome.genome_id)
    assert archive.consider(different) == (True, None)
    assert archive.consider(overflow) == (False, None)
    assert len(archive) == 2


def test_fitness_is_milestone_first_and_descriptors_are_bounded() -> None:
    local = {
        "game_started": 1,
        "maps_seen": 7,
        "positions_seen": 2_000,
        "warps_seen": 8,
        "max_party_count": 0,
        "max_party_level": 0,
        "pokedex_seen": 0,
        "pokedex_owned": 0,
        "got_pokedex": 0,
        "event_flags_seen": 10,
        "bag_items_seen": 0,
        "moves_seen": 0,
        "battle_kinds_seen": 0,
        "badges": 0,
        "blackouts": 0,
    }
    starter = dict(local, maps_seen=3, positions_seen=50, max_party_count=1)

    assert fitness_vector(starter, 12_000) > fitness_vector(local, 12_000)
    assert behavior_descriptor(dict(starter, maps_seen=99, battle_kinds_seen=99)) == (3, 7, 0, 2, 0)
    assert behavior_descriptor(dict(starter, action_profile=4)) != behavior_descriptor(
        dict(starter, action_profile=17)
    )


def test_evolution_config_rejects_invalid_lifetimes() -> None:
    with pytest.raises(ValueError, match="population"):
        EvolutionConfig(population_size=1)
    with pytest.raises(ValueError, match="sigmas"):
        EvolutionConfig(mutation_sigma=0)


@pytest.mark.integration
def test_evolution_runner_completes_two_clean_start_lifetimes(tmp_path: Path) -> None:
    raw_path = os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        pytest.skip(f"Set {ROM_ENVIRONMENT_VARIABLE} to run ROM integration tests")
    rom_path = Path(raw_path).expanduser().resolve()
    fingerprint = verify_rom(rom_path)
    output = tmp_path / "evolution"
    result = run_evolution_experiment(
        rom_path,
        fingerprint,
        config=EvolutionConfig(
            duration_seconds=60,
            max_actions=16,
            seed=11,
            population_size=2,
            candidate_actions=8,
            archive_capacity=8,
            seen_filter_bytes=1_024,
            screenshot_limit=4,
            status_interval_seconds=0.01,
            checkpoint_interval_seconds=0.01,
            max_output_bytes=32 * 1024 * 1024,
            min_free_bytes=0,
        ),
        run_directory=output,
    )

    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    genealogy = [json.loads(line) for line in (output / "genealogy.jsonl").read_text().splitlines()]
    assert result.stop_reason == "action_limit"
    assert result.evaluations == 2
    assert status["generation"] == 1
    assert status["ram_used_by_actor"] is False
    assert status["ram_used_by_selection"] is True
    assert status["snapshot_assisted"] is False
    assert manifest["network"]["parameter_count"] == PARAMETER_COUNT
    assert len(genealogy) == 2
    assert all(record["parent_id"] is None for record in genealogy)
    assert (output / "checkpoint.json.gz").is_file()
    assert "Useful accidents" in (output / "index.html").read_text(encoding="utf-8")
