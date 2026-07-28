from __future__ import annotations

import gzip
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from pokemon_red_ai.cli import build_parser
from pokemon_red_ai.evolution_lab import (
    DEFAULT_EVOLUTION_LAB_ACTIONS,
    EvolutionLabConfig,
    EvolutionLabLane,
    _capture_visual_frame,
    _comparison_complete,
    _seed_archive_identity,
    _start_http_server,
    _validate_lanes,
    comparison_snapshot,
    evolution_lab_agent_command,
    six_lane_matrix,
)
from pokemon_red_ai.evolution_lab_report import render_evolution_lab_dashboard


def test_six_lane_matrix_is_selection_by_mutation_in_dashboard_order() -> None:
    lanes = six_lane_matrix()

    assert [lane.lane_id for lane in lanes] == [
        "uniform-broad",
        "uniform-gentle",
        "uniform-multiscale",
        "frontier-broad",
        "frontier-gentle",
        "frontier-multiscale",
    ]
    assert {(lane.row, lane.column) for lane in lanes} == {
        (row, column) for row in range(2) for column in range(3)
    }
    assert len({lane.lane_id for lane in lanes}) == 6


def test_cli_exposes_evolution_treatments_and_lab_controls() -> None:
    parser = build_parser()
    lane = parser.parse_args(
        [
            "evolution-run",
            "--output",
            "/safe/lane",
            "--selection-strategy",
            "frontier",
            "--mutation-profile",
            "gentle",
            "--seed-archive",
            "/safe/archive",
        ]
    )
    lab = parser.parse_args(
        [
            "evolution-lab-run",
            "--output",
            "/safe/lab",
            "--seed-archive",
            "/safe/archive",
        ]
    )

    assert lane.selection_strategy == "frontier"
    assert lane.mutation_profile == "gentle"
    assert lane.seed_archive == Path("/safe/archive")
    assert lab.max_actions_per_lane == DEFAULT_EVOLUTION_LAB_ACTIONS
    assert lab.unpaired_seeds is False
    assert lab.resume is False
    assert parser.parse_args(["evolution-lab-status", "/safe/lab"]).command == (
        "evolution-lab-status"
    )
    assert parser.parse_args(["evolution-lab-stop", "/safe/lab"]).command == (
        "evolution-lab-stop"
    )


def test_paired_commands_change_treatment_but_not_seed_or_budget() -> None:
    config = EvolutionLabConfig(duration_seconds=3_600, seed=77)
    commands = [
        evolution_lab_agent_command(
            lane,
            Path("/safe/lab") / lane.lane_id,
            Path("/safe/seed-run"),
            config,
            lane_index=index,
        )
        for index, lane in enumerate(six_lane_matrix())
    ]

    assert config.paired_seed is True
    assert config.max_actions_per_lane == DEFAULT_EVOLUTION_LAB_ACTIONS == 1_536_000
    assert {command[command.index("--seed") + 1] for command in commands} == {"77"}
    assert {command[command.index("--max-actions") + 1] for command in commands} == {"1536000"}
    assert {command[command.index("--selection-strategy") + 1] for command in commands} == {
        "uniform",
        "frontier",
    }
    assert {command[command.index("--mutation-profile") + 1] for command in commands} == {
        "broad",
        "gentle",
        "multiscale",
    }
    assert all("--seed-archive" in command and "--rom" not in command for command in commands)
    resumed = evolution_lab_agent_command(
        six_lane_matrix()[0],
        Path("/safe/lab/uniform-broad"),
        Path("/safe/seed-run"),
        config,
        lane_index=0,
        resume=True,
    )
    assert resumed[-1] == "--resume"


def test_unpaired_mode_produces_distinct_deterministic_seeds() -> None:
    config = EvolutionLabConfig(duration_seconds=60, seed=12, paired_seed=False)
    first = [
        evolution_lab_agent_command(
            lane,
            Path("/output") / lane.lane_id,
            Path("/archive"),
            config,
            lane_index=index,
        )
        for index, lane in enumerate(six_lane_matrix())
    ]
    second = [
        evolution_lab_agent_command(
            lane,
            Path("/output") / lane.lane_id,
            Path("/archive"),
            config,
            lane_index=index,
        )
        for index, lane in enumerate(six_lane_matrix())
    ]
    first_seeds = [command[command.index("--seed") + 1] for command in first]
    second_seeds = [command[command.index("--seed") + 1] for command in second]

    assert first_seeds == second_seeds
    assert len(set(first_seeds)) == 6


def test_lab_validates_matrix_and_resource_limits() -> None:
    with pytest.raises(ValueError, match="duration"):
        EvolutionLabConfig(duration_seconds=0)
    with pytest.raises(ValueError, match="port"):
        EvolutionLabConfig(duration_seconds=1, port=0)
    with pytest.raises(ValueError, match="frontier probability"):
        EvolutionLabConfig(duration_seconds=1, frontier_probability=1.1)
    with pytest.raises(ValueError, match="safe lowercase"):
        EvolutionLabLane("../bad", "Bad", "uniform", "broad", 0, 0)
    lane = EvolutionLabLane("same", "First", "uniform", "broad", 0, 0)
    with pytest.raises(ValueError, match="IDs"):
        _validate_lanes((lane, lane))


def test_seed_archive_is_hashed_and_requires_elites(tmp_path: Path) -> None:
    run = tmp_path / "completed-run"
    run.mkdir()
    checkpoint = run / "checkpoint.json.gz"
    with gzip.open(checkpoint, "wt", encoding="utf-8") as target:
        json.dump({"protocol_version": "test-v1", "archive": [{"genome_id": "abc"}]}, target)

    identity = _seed_archive_identity(run)

    assert identity["label"] == "sealed-evolution-archive"
    assert identity["protocol_version"] == "test-v1"
    assert identity["archive_cells"] == 1
    assert len(identity["checkpoint_sha256"]) == 64
    assert identity["absolute_path_recorded"] is False


def test_equal_budget_completion_requires_fresh_terminal_lane_statuses() -> None:
    lanes = six_lane_matrix()
    config = EvolutionLabConfig(duration_seconds=3_600, max_actions_per_lane=24_000)
    complete = {
        lane.lane_id: {
            "state": "finished",
            "stop_reason": "action_limit",
            "total_actions": 24_000,
            "evaluations": 2,
        }
        for lane in lanes
    }

    assert _comparison_complete(complete, lanes, config)
    stale = {key: dict(value) for key, value in complete.items()}
    stale[lanes[0].lane_id]["total_actions"] = 23_999
    assert not _comparison_complete(stale, lanes, config)
    wrong_stop = {key: dict(value) for key, value in complete.items()}
    wrong_stop[lanes[0].lane_id]["stop_reason"] = "duration_limit"
    assert not _comparison_complete(wrong_stop, lanes, config)


def test_visual_frame_freezes_each_lane_with_hash_and_action_count(tmp_path: Path) -> None:
    lanes = six_lane_matrix()
    (tmp_path / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
    statuses = {}
    for index, lane in enumerate(lanes):
        lane_directory = tmp_path / lane.lane_id
        lane_directory.mkdir()
        (lane_directory / "latest.png").write_bytes(b"png" + bytes([index]))
        statuses[lane.lane_id] = {"total_actions": index + 1, "evaluations": 1}

    record = _capture_visual_frame(
        tmp_path,
        statuses,
        lanes,
        frame_index=0,
        kind="periodic",
        elapsed_seconds=10,
    )

    assert record is not None
    assert len(record["images"]) == 6
    assert record["images"][lanes[-1].lane_id]["total_actions"] == 6
    assert len(record["images"][lanes[0].lane_id]["sha256"]) == 64
    assert (tmp_path / "visuals" / "frame-00000" / "metadata.json").is_file()


def test_comparison_snapshot_keeps_narrative_fields_small_and_explicit() -> None:
    lanes = six_lane_matrix()
    statuses = {
        lane.lane_id: {
            "state": "running",
            "total_actions": 12_000,
            "evaluations": 1,
            "fitness_tier": int(lane.selection_strategy == "frontier"),
            "maps_seen": 2,
            "positions_seen": 7,
            "best_fitness": [1, 0, 0],
            "current_genome_id": "must-not-be-copied",
        }
        for lane in lanes
    }

    snapshot = comparison_snapshot("hourly", statuses, lanes, elapsed_seconds=3_600)

    assert snapshot["kind"] == "hourly"
    assert snapshot["elapsed_seconds"] == 3_600
    assert len(snapshot["lanes"]) == 6
    assert snapshot["lanes"]["frontier-gentle"]["fitness_tier"] == 1
    assert "current_genome_id" not in snapshot["lanes"]["frontier-gentle"]


def test_lab_dashboard_is_static_and_explains_the_paired_2x3_contract() -> None:
    lanes = six_lane_matrix()
    statuses = {
        lane.lane_id: {
            "state": "running",
            "elapsed_seconds": 10,
            "total_actions": 1_000,
            "evaluations": 2,
            "fitness_tier": 1,
            "best_fitness": [1, 0, 2],
            "maps_seen": 2,
            "positions_seen": 9,
            "candidate_action_budget": 12_000,
            "current_genome_id": "child",
            "current_parent_id": "parent",
            "selection_channel": "frontier",
            "mutation_channel": "micro",
            "lineage_depth": 3,
        }
        for lane in lanes
    }
    lab_status = {
        "state": "running",
        "updated_at": "now",
        "config": {
            "duration_seconds": 100,
            "max_actions_per_lane": 10_000,
            "paired_seed": True,
        },
        "seed_archive": {"label": "sealed-pretrial"},
        "lanes": {lane.lane_id: {"process_alive": True, "state": "running"} for lane in lanes},
    }

    rendered = render_evolution_lab_dashboard(
        lab_status,
        [lane.public_dict() for lane in lanes],
        statuses,
        {lane.lane_id: [{"total_actions": 0}, statuses[lane.lane_id]] for lane in lanes},
    )

    assert "Which descendants" in rendered
    assert "TWO SELECTION RULES × THREE MUTATION SCALES" in rendered
    assert "same paired RNG seed" in rendered
    assert all(lane.label in rendered for lane in lanes)
    assert "Parent channel" in rendered and "Mutation channel" in rendered
    assert "<script" not in rendered.lower()
    assert "http://" not in rendered and "https://" not in rendered


def test_lab_http_server_exposes_only_dashboards_status_and_pngs(tmp_path: Path) -> None:
    lane = "uniform-broad"
    (tmp_path / lane / "screenshots").mkdir(parents=True)
    (tmp_path / "index.html").write_text("public lab", encoding="utf-8")
    (tmp_path / "status.json").write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text("private metadata", encoding="utf-8")
    (tmp_path / "lab-events.jsonl").write_text("private events", encoding="utf-8")
    (tmp_path / lane / "index.html").write_text("public lane", encoding="utf-8")
    (tmp_path / lane / "latest.png").write_bytes(b"png")
    (tmp_path / lane / "screenshots" / "elite.png").write_bytes(b"png")
    (tmp_path / lane / "checkpoint.json.gz").write_bytes(b"private snapshot")
    (tmp_path / lane / "trace.jsonl").write_text("private trace", encoding="utf-8")
    server, _thread = _start_http_server(tmp_path, 0, [lane])
    port = server.server_address[1]
    try:
        for public_name in (
            "index.html",
            "status.json",
            f"{lane}/index.html",
            f"{lane}/latest.png",
            f"{lane}/screenshots/elite.png",
        ):
            with urlopen(f"http://127.0.0.1:{port}/{public_name}") as response:
                assert response.status == 200
        for private_name in (
            "manifest.json",
            "lab-events.jsonl",
            f"{lane}/checkpoint.json.gz",
            f"{lane}/trace.jsonl",
            f"{lane}/../manifest.json",
        ):
            with pytest.raises(HTTPError) as error:
                urlopen(f"http://127.0.0.1:{port}/{private_name}")
            assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
