from __future__ import annotations

import copy
import gzip
import json
import os
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_ai.blind import BLIND_ACTIONS, visual_signature
from pokemon_red_ai.evolution import (
    EVOLUTION_CHECKPOINT_SCHEMA,
    EVOLUTION_PROTOCOL_VERSION,
    HIDDEN_UNITS,
    PARAMETER_COUNT,
    EvolutionConfig,
    EvolutionCounters,
    EvolutionElite,
    EvolutionGenome,
    QualityDiversityArchive,
    RecurrentPixelPolicy,
    _best_metrics,
    _mutation_spec,
    _new_candidate,
    behavior_descriptor,
    fitness_vector,
    load_seed_archive,
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
    with pytest.raises(ValueError, match="selection strategy"):
        EvolutionConfig(selection_strategy="roulette")
    with pytest.raises(ValueError, match="frontier probability"):
        EvolutionConfig(frontier_probability=1.1)
    with pytest.raises(ValueError, match="tournament"):
        EvolutionConfig(tournament_size=0)
    with pytest.raises(ValueError, match="mutation profile"):
        EvolutionConfig(mutation_profile="unknown")


def _elite(
    seed: int,
    descriptor: tuple[int, ...],
    fitness: tuple[int, ...],
    *,
    lineage_depth: int = 0,
    metrics: dict[str, int] | None = None,
) -> EvolutionElite:
    return EvolutionElite(
        genome=EvolutionGenome.random(seed),
        parent_id=None,
        generation=0,
        descriptor=descriptor,
        fitness=fitness,
        metrics=metrics or {"maps_seen": fitness[0]},
        mutation_seed=None,
        mutation_sigma=0,
        mutated_parameters=0,
        lineage_depth=lineage_depth,
    )


def test_parent_selection_and_mutation_profiles_are_deterministic() -> None:
    archive = QualityDiversityArchive(
        8,
        [
            _elite(1, (0,), (0, 9)),
            _elite(2, (1,), (2, 3)),
            _elite(3, (2,), (2, 8)),
        ],
    )
    first_rng = np.random.default_rng(91)
    second_rng = np.random.default_rng(91)
    first = [
        archive.select_parent(
            first_rng, strategy="frontier", frontier_probability=1, tournament_size=3
        )
        for _ in range(12)
    ]
    second = [
        archive.select_parent(
            second_rng, strategy="frontier", frontier_probability=1, tournament_size=3
        )
        for _ in range(12)
    ]
    assert [(elite.genome.genome_id, channel) for elite, channel in first] == [
        (elite.genome.genome_id, channel) for elite, channel in second
    ]
    assert all(elite.fitness[0] == 2 and channel == "frontier" for elite, channel in first)

    wildcard, channel = archive.select_parent(
        np.random.default_rng(3),
        strategy="frontier",
        frontier_probability=0,
        tournament_size=3,
    )
    assert wildcard in archive.elites
    assert channel == "wildcard"

    assert _mutation_spec(np.random.default_rng(1), EvolutionConfig()) == (
        "broad",
        0.10,
        0.05,
    )
    assert _mutation_spec(
        np.random.default_rng(1),
        EvolutionConfig(large_mutation_probability=1),
    ) == ("macro", 0.10, 0.20)
    assert _mutation_spec(
        np.random.default_rng(1), EvolutionConfig(mutation_profile="gentle")
    ) == ("gentle", 0.02, 0.01)

    first_rng = np.random.default_rng(44)
    second_rng = np.random.default_rng(44)
    config = EvolutionConfig(mutation_profile="multiscale")
    first_specs = [_mutation_spec(first_rng, config) for _ in range(200)]
    second_specs = [_mutation_spec(second_rng, config) for _ in range(200)]
    assert first_specs == second_specs
    assert {channel for channel, _, _ in first_specs} == {"micro", "broad", "macro"}
    assert set(first_specs) == {
        ("micro", 0.01, 0.02),
        ("broad", 0.10, 0.05),
        ("macro", 0.10, 0.20),
    }


def test_seeded_generation_zero_reproduces_immediately() -> None:
    parent = _elite(5, (1,), (2, 8), lineage_depth=7, metrics={"maps_seen": 4})
    archive = QualityDiversityArchive(8, [parent])
    candidate = _new_candidate(
        EvolutionCounters(),
        archive,
        np.random.default_rng(12),
        EvolutionConfig(large_mutation_probability=0),
        seeded=True,
    )

    assert candidate.parent_id == parent.genome.genome_id
    assert candidate.parent_fitness == parent.fitness
    assert candidate.parent_metrics == parent.metrics
    assert candidate.lineage_depth == 8
    assert candidate.selection_channel == "uniform"
    assert candidate.mutation_channel == "broad"
    assert candidate.genome.genome_id != parent.genome.genome_id

    founder = _new_candidate(
        EvolutionCounters(),
        archive,
        np.random.default_rng(12),
        EvolutionConfig(),
    )
    assert founder.parent_id is None
    assert founder.selection_channel == founder.mutation_channel == "founder"


def _write_seed_run(path: Path, *, rom_sha256: str, corrupt_genome: bool = False) -> None:
    path.mkdir()
    elite = _elite(8, (1,), (1, 2), lineage_depth=2)
    raw_elite = elite.checkpoint_dict()
    if corrupt_genome:
        raw_elite = copy.deepcopy(raw_elite)
        raw_elite["genome"]["genome_id"] = "not-the-real-hash"
    checkpoint = {
        "schema_version": EVOLUTION_CHECKPOINT_SCHEMA,
        "protocol_version": EVOLUTION_PROTOCOL_VERSION,
        "rom_sha256": rom_sha256,
        "source": {"git_commit": "a" * 40, "worktree_dirty": False},
        "counters": {"evaluations": 23},
        "archive": [raw_elite],
    }
    with gzip.open(path / "checkpoint.json.gz", "wt", encoding="utf-8") as output:
        json.dump(checkpoint, output)
    (path / "status.json").write_text(
        json.dumps({"state": "finished", "stop_reason": "duration_limit"}),
        encoding="utf-8",
    )
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "protocol_version": EVOLUTION_PROTOCOL_VERSION,
                "rom": {"sha256": rom_sha256},
                "network": {"parameter_count": PARAMETER_COUNT},
            }
        ),
        encoding="utf-8",
    )
    (path / "genealogy.jsonl").write_text(
        json.dumps(
            {
                "kind": "candidate_completed",
                "genome_id": elite.genome.genome_id,
                "parent_id": "retired-parent",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_seed_archive_import_validates_and_records_no_private_path(tmp_path: Path) -> None:
    source = tmp_path / "private-predecessor-name"
    _write_seed_run(source, rom_sha256="rom-hash")
    imported = load_seed_archive(source, rom_sha256="rom-hash", capacity=4)

    assert len(imported.archive) == 1
    assert imported.archive.elites[0].lineage_depth == 1
    assert imported.metadata["archive_cells"] == 1
    assert imported.metadata["predecessor_evaluations"] == 23
    assert imported.metadata["checkpoint_sha256"]
    assert str(source) not in json.dumps(imported.metadata)
    config = EvolutionConfig(seed_archive=source)
    assert config.public_dict()["seed_archive_enabled"] is True
    assert str(source) not in json.dumps(config.public_dict())

    with pytest.raises(ValueError, match="different ROM"):
        load_seed_archive(source, rom_sha256="other-rom", capacity=4)
    with pytest.raises(ValueError, match="capacity"):
        load_seed_archive(source, rom_sha256="rom-hash", capacity=0)

    corrupt = tmp_path / "corrupt"
    _write_seed_run(corrupt, rom_sha256="rom-hash", corrupt_genome=True)
    with pytest.raises(ValueError, match="hash"):
        load_seed_archive(corrupt, rom_sha256="rom-hash", capacity=4)


def test_best_metrics_uses_one_real_trajectory() -> None:
    archive = QualityDiversityArchive(
        4,
        [
            _elite(1, (1,), (1, 8), metrics={"maps_seen": 2, "positions_seen": 100}),
            _elite(2, (2,), (2, 1), metrics={"maps_seen": 4, "positions_seen": 3}),
        ],
    )
    current = {"maps_seen": 1, "positions_seen": 1}
    # Supply the full fitness metric vocabulary used by fitness_vector.
    current = {
        **{
            "game_started": 0,
            "warps_seen": 0,
            "max_party_count": 0,
            "max_party_level": 0,
            "pokedex_seen": 0,
            "pokedex_owned": 0,
            "got_pokedex": 0,
            "event_flags_seen": 0,
            "battle_kinds_seen": 0,
            "badges": 0,
            "blackouts": 0,
        },
        **current,
    }
    assert _best_metrics(archive, current, 1_000) == {
        "maps_seen": 4,
        "positions_seen": 3,
    }


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
    trace = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
    assert result.stop_reason == "action_limit"
    assert result.evaluations == 2
    assert status["generation"] == 1
    assert status["ram_used_by_actor"] is False
    assert status["ram_used_by_selection"] is True
    assert status["snapshot_assisted"] is False
    assert manifest["network"]["parameter_count"] == PARAMETER_COUNT
    assert len(genealogy) == 2
    assert all(record["parent_id"] is None for record in genealogy)
    assert all(
        "action_telemetry" in record and "milestone_actions" in record
        for record in genealogy
    )
    assert sum(record.get("kind") == "candidate_started" for record in trace) == 2
    assert (output / "checkpoint.json.gz").is_file()
    assert "Useful accidents" in (output / "index.html").read_text(encoding="utf-8")
