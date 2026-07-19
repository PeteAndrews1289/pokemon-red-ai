from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from pokemon_red_ai.arena import (
    FINAL_ARENA_MAX_ACTIONS,
    FINAL_ARENA_Q_POLICY_BUCKETS,
    ArenaConfig,
    _agent_command,
    _start_http_server,
)
from pokemon_red_ai.arena_report import MODE_ORDER, render_arena_dashboard
from pokemon_red_ai.cli import build_parser


def test_arena_commands_declare_each_mode_without_a_private_rom_path() -> None:
    config = ArenaConfig(duration_seconds=60, max_actions=100, seed=7)
    for mode in MODE_ORDER:
        command = _agent_command(mode, Path("/safe/output") / mode, config, resume=False)
        assert command[command.index("--mode") + 1] == mode
        assert command[command.index("--q-policy-buckets") + 1] == str(
            FINAL_ARENA_Q_POLICY_BUCKETS
        )
        assert "--rom" not in command


def test_final_arena_defaults_leave_wall_clock_in_control() -> None:
    args = build_parser().parse_args(["arena-run", "--output", "/safe/output"])

    assert args.max_actions == FINAL_ARENA_MAX_ACTIONS == 150_000_000
    assert args.q_policy_buckets == FINAL_ARENA_Q_POLICY_BUCKETS == 1_048_576


def test_arena_dashboard_is_local_static_html() -> None:
    status = {
        "state": "running",
        "updated_at": "now",
    }
    agent_status = {
        "state": "running",
        "elapsed_seconds": 10,
        "duration_seconds": 100,
        "total_actions": 20,
        "unique_visual_cells": 4,
        "reward_total": 2,
        "actions_per_second": 2,
        "maps_seen": 1,
        "max_party_count": 0,
        "badge_count": 0,
    }
    rendered = render_arena_dashboard(
        status,
        {mode: dict(agent_status) for mode in MODE_ORDER},
        {
            mode: [
                {"elapsed_seconds": 1, "unique_visual_cells": 1},
                {"elapsed_seconds": 10, "unique_visual_cells": 4},
            ]
            for mode in MODE_ORDER
        },
    )

    assert "Four ways to play Pokémon Red" in rendered
    assert all(
        label in rendered for label in ("Pure Monkey", "Visually Curious", "Outcome-Rewarded")
    )
    assert "http://" not in rendered and "https://" not in rendered
    assert "<script" not in rendered.lower()


def test_arena_config_rejects_unsafe_budgets() -> None:
    with pytest.raises(ValueError, match="duration"):
        ArenaConfig(duration_seconds=0, max_actions=100, seed=1)
    with pytest.raises(ValueError, match="port"):
        ArenaConfig(duration_seconds=1, max_actions=1, seed=1, port=0)


def test_arena_http_server_refuses_checkpoints_and_traces(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("public", encoding="utf-8")
    agent = tmp_path / "monkey"
    agent.mkdir()
    (agent / "checkpoint.json.gz").write_bytes(b"private snapshot")
    (agent / "trace.jsonl").write_text("private trace", encoding="utf-8")
    server, _thread = _start_http_server(tmp_path, 0)
    port = server.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/index.html") as response:
            assert response.read() == b"public"
        for private_name in ("checkpoint.json.gz", "trace.jsonl"):
            with pytest.raises(HTTPError) as error:
                urlopen(f"http://127.0.0.1:{port}/monkey/{private_name}")
            assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
