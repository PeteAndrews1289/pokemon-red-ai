from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_ai import v11
from pokemon_red_ai.rom import RomFingerprint


def _fingerprint(filename: str = "private.gb") -> RomFingerprint:
    return RomFingerprint(
        filename=filename,
        title="POKEMON RED",
        size_bytes=1_048_576,
        sha1="a" * 40,
        sha256="b" * 64,
    )


def _config(tmp_path: Path) -> v11.V11Config:
    harness = tmp_path / "harness"
    harness.mkdir()
    rom = tmp_path / "private.gb"
    rom.write_bytes(b"fixture")
    directive = tmp_path / "directive.md"
    directive.write_text("Reach the Hall of Fame.\n", encoding="utf-8")
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    return v11.V11Config(
        rom=rom,
        output=tmp_path / "run",
        harness=harness,
        directive=directive,
        python=python,
        min_free_gib=0,
    )


def _prepare_without_external_checks(
    monkeypatch: pytest.MonkeyPatch,
    config: v11.V11Config,
) -> dict[str, object]:
    monkeypatch.setattr(v11, "verify_rom", lambda path: _fingerprint(path.name))
    monkeypatch.setattr(
        v11,
        "_harness_overlay_provenance",
        lambda path: {"sha256": "c" * 64, "files": []},
    )
    return v11.prepare_run(config, token="0123456789abcdef" * 2, skip_doctor=True)


def test_harness_command_is_clean_start_local_expert_and_strict(tmp_path: Path) -> None:
    config = _config(tmp_path)

    command = v11.build_harness_command(config, "v11_test")

    joined = " ".join(command)
    assert "--game red" in joined
    assert "--backend codex" in joined
    assert "--api-gateway login" in joined
    assert "--local-agent" in command
    assert "--expert-mode" in command
    assert "--direct-objectives categorized_full_game" in joined
    assert "--termination-condition hall_of_fame" in joined
    assert "--termination-threshold 1" in joined
    assert "--agent-thinking-effort medium" in joined
    assert "--agent-model gpt-5.6-terra" in joined
    assert "--record" in command
    assert "--load-state" not in command
    assert "--load-checkpoint" not in command


def test_resolved_config_preserves_virtualenv_interpreter_symlink(tmp_path: Path) -> None:
    config = _config(tmp_path)
    target = tmp_path / "base-python"
    target.write_text("", encoding="utf-8")
    config.python.unlink()
    config.python.symlink_to(target)

    resolved = config.resolved()

    assert resolved.python == config.python.absolute()
    assert resolved.python != target.resolve()


def test_prepare_records_public_provenance_and_stages_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    manifest = _prepare_without_external_checks(monkeypatch, config)

    staged = config.harness / "PokemonRed-GBC" / "pokered.gbc"
    assert staged.is_symlink()
    assert staged.resolve() == config.rom.resolve()
    assert manifest["state"] == "prepared"
    assert manifest["rom"] == _fingerprint().public_dict()
    assert "filename" not in manifest["rom"]
    assert str(config.rom.resolve()) not in json.dumps(manifest["rom"])
    assert manifest["experiment"]["clean_power_on"] is True
    assert manifest["experiment"]["termination"] == "strict_hall_of_fame"
    assert manifest["experiment"]["planner_model"] == "gpt-5.6-terra"
    assert manifest["directive"]["path"] == "directive.md"
    assert str(config.directive.resolve()) not in json.dumps(manifest)
    assert str(config.rom.resolve()) not in json.dumps(manifest)
    assert str(Path.home()) not in json.dumps(manifest)
    assert Path.home().name not in json.dumps(manifest)
    assert (config.output / v11.STATUS_FILE).is_file()
    assert (config.output / v11.NARRATIVE_FILE).is_file()
    public_records = "".join(
        (config.output / filename).read_text(encoding="utf-8")
        for filename in (
            v11.CONTROL_MANIFEST,
            v11.STATUS_FILE,
            v11.NARRATIVE_FILE,
            v11.EVENTS_FILE,
        )
    )
    assert str(config.rom.resolve()) not in public_records
    assert str(config.directive.resolve()) not in public_records
    assert str(Path.home()) not in public_records
    assert Path.home().name not in public_records


def test_prepare_records_optional_canary_time_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(_config(tmp_path), max_seconds=900.0)

    manifest = _prepare_without_external_checks(monkeypatch, config)

    assert manifest["supervision"]["max_seconds"] == 900.0


def test_prepare_is_idempotent_only_while_still_prepared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    first = _prepare_without_external_checks(monkeypatch, config)

    second = v11.prepare_run(config, token="different", skip_doctor=True)

    assert second == first
    manifest_path = config.output / v11.CONTROL_MANIFEST
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored["state"] = "finished"
    manifest_path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(v11.V11Error, match="not empty"):
        v11.prepare_run(config, skip_doctor=True)


def test_doctor_requires_the_pinned_local_patch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    for relative in ("run_cli.py", "server/app.py", "server/cli/pokemon_mcp_server.py"):
        path = config.harness / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("plain upstream\n", encoding="utf-8")

    monkeypatch.setattr(v11, "verify_rom", lambda path: _fingerprint(path.name))
    monkeypatch.setattr(v11.shutil, "which", lambda name: "/fake/codex")
    monkeypatch.setattr(v11, "_free_gib", lambda path: 200.0)
    monkeypatch.setattr(v11, "_port_available", lambda port: True)

    def capture(command: list[str], **kwargs: object) -> str:
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return v11.UPSTREAM_COMMIT
        if command[-2:] == ["login", "status"]:
            return "Logged in using ChatGPT"
        return "3.11.9"

    monkeypatch.setattr(v11, "_run_capture", capture)

    report = v11.doctor(config)

    assert report.ok is False
    local_patch = next(check for check in report.checks if check.name == "local_patch")
    assert local_patch.ok is False
    assert "--local-agent" in local_patch.detail


def test_local_codex_command_must_keep_host_sandbox_pins() -> None:
    safe = [
        "codex",
        "exec",
        "--sandbox",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "-c",
        "sandbox_workspace_write.network_access=false",
        "--model",
        "gpt-5.6-terra",
        "-c",
        "model_reasoning_effort=medium",
    ]
    assert "network denied" in v11._validate_local_codex_command(safe)

    unsafe = [*safe, "--dangerously-bypass-approvals-and-sandbox"]
    with pytest.raises(v11.V11Error, match="bypasses host"):
        v11._validate_local_codex_command(unsafe)


def test_local_pokemon_mcp_policy_is_required_preapproved_and_exact() -> None:
    safe = {
        "required": True,
        "default_tools_approval_mode": "approve",
        "enabled_tools": sorted(v11.V11_MCP_TOOLS),
    }
    assert "exact 12-tool" in v11._validate_local_mcp_policy(safe)

    with pytest.raises(v11.V11Error, match="pre-approved"):
        v11._validate_local_mcp_policy(
            {**safe, "default_tools_approval_mode": "prompt"}
        )
    with pytest.raises(v11.V11Error, match="12-tool"):
        v11._validate_local_mcp_policy({**safe, "enabled_tools": ["get_game_state"]})


def test_overlay_provenance_hashes_tracked_and_untracked_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = tmp_path / "harness"
    for index, relative in enumerate(v11.V11_OVERLAY_FILES):
        path = harness / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"overlay {index}\n", encoding="utf-8")
    statuses = {
        relative: "untracked" if relative.endswith(".txt") else ".M"
        for relative in v11.V11_OVERLAY_FILES
    }
    monkeypatch.setattr(v11, "_git_worktree_status", lambda path: statuses)

    first = v11._harness_overlay_provenance(harness)
    (harness / v11.V11_OVERLAY_FILES[0]).write_text("changed\n", encoding="utf-8")
    second = v11._harness_overlay_provenance(harness)

    assert len(first["files"]) == len(v11.V11_OVERLAY_FILES)
    assert first["files"][0]["git_status"] == ".M"
    assert first["sha256"] != second["sha256"]


def test_launch_detaches_a_token_bound_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _prepare_without_external_checks(monkeypatch, config)
    calls: list[tuple[list[str], dict[str, object]]] = []

    class FakeProcess:
        pid = 42_424

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(v11.subprocess, "Popen", fake_popen)

    launched = v11.launch_run(config, skip_doctor=True)

    assert launched["supervisor_pid"] == 42_424
    command, kwargs = calls[0]
    assert command[1:4] == ["-m", "pokemon_red_ai.v11", "_supervise"]
    assert str(config.output.resolve()) in command
    assert "0123456789abcdef" * 2 in command
    assert kwargs["start_new_session"] is True
    pid_data = json.loads((config.output / v11.PID_FILE).read_text(encoding="utf-8"))
    assert pid_data["supervisor_pid"] == 42_424
    assert pid_data["control_token"] == "0123456789abcdef" * 2


def test_supervisor_waits_for_launcher_to_replace_prepared_pid_record() -> None:
    token = "control-token"
    prepared = {"control_token": token}
    launched = {"control_token": token, "supervisor_pid": 42_424}

    assert not v11._supervisor_record_matches(
        prepared,
        control_token=token,
        process_id=42_424,
    )
    assert v11._supervisor_record_matches(
        launched,
        control_token=token,
        process_id=42_424,
    )


def test_supervisor_scrubs_inherited_restore_state() -> None:
    inherited = {
        "PATH": "/bin",
        "LOAD_STATE": "/sensitive/old.state",
        "LOAD_CHECKPOINT_MODE": "true",
        "RUN_DATA_ID": "old-run",
        "ROM_PATH": "/sensitive/other.gb",
        "BACKUP_STATE": "/sensitive/backup.zip",
        "SAVE_STATE": "/sensitive/save.state",
        "POKEMON_RED_ROM": "/sensitive/source.gb",
    }

    clean = v11._clean_start_environment(inherited)

    assert clean["PATH"] == "/bin"
    assert clean["LOAD_CHECKPOINT_MODE"] == "false"
    for name in v11.CLEAN_START_ENV_BLOCKLIST:
        assert name not in clean


def test_progress_snapshot_is_compact_and_never_persists_pixels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {
        "/status": {"step_count": 12},
        "/state": {
            "visual": {"screenshot": "base64-secret-pixels"},
            "player": {
                "location": "Route1",
                "position": {"x": 8, "y": 4},
                "party": [{"species": "Bulbasaur"}],
            },
            "game": {
                "game_state": "overworld",
                "is_in_battle": False,
                "badges": [],
                "pokedex_seen": 3,
                "pokedex_caught": 1,
            },
        },
        "/milestones": {
            "completed": 4,
            "total": 32,
            "objectives": {
                "mode": "categorized",
                "story": [
                    {
                        "description": "Reach Viridian City",
                        "current": True,
                    }
                ],
                "battling": [],
                "dynamics": [],
                "categorized_status": {
                    "story": {"current_index": 2, "total": 120},
                    "battling": {"current_index": 0, "total": 20},
                    "dynamics": {"current_index": 0, "total": 10},
                },
            },
        },
        "/metrics": {"agent_step_count": 7, "total_actions": 90, "total_llm_calls": 2},
        "/termination_condition": {"condition_met": False},
    }

    def fake_http(url: str, **kwargs: object) -> dict[str, object]:
        for suffix, response in responses.items():
            if suffix in url:
                return response
        raise AssertionError(url)

    monkeypatch.setattr(v11, "_http_json", fake_http)

    snapshot = v11._progress_snapshot(8_775)

    assert snapshot["server_reachable"] is True
    assert snapshot["location"] == "Route1"
    assert snapshot["position"] == {"x": 8, "y": 4}
    assert snapshot["current_objective"] == "story: Reach Viridian City"
    assert snapshot["objective_index"] == {"story": 2, "battling": 0, "dynamics": 0}
    assert snapshot["party_size"] == 1
    assert "base64-secret-pixels" not in json.dumps(snapshot)
    assert "visual" not in snapshot


def test_narrative_is_derived_from_the_compact_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "narrative.md"
    path.write_text("# Narrative\n\n", encoding="utf-8")
    snapshot = {
        "location": "ViridianCity",
        "position": {"x": 17, "y": 9},
        "current_objective": "Visit the Poké Mart",
        "agent_step_count": 14,
        "total_actions": 230,
        "milestones_completed": 6,
        "milestones_total": 32,
        "badges": [],
        "party_size": 1,
        "hall_of_fame_verified": False,
    }

    v11._append_narrative(path, snapshot, elapsed_seconds=3_600)

    text = path.read_text(encoding="utf-8")
    assert "Elapsed: 1.00 hours" in text
    assert "ViridianCity (17, 9)" in text
    assert "Visit the Poké Mart" in text
    assert "Hall of Fame verified: False" in text


def test_stop_refuses_a_reused_or_unrelated_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / v11.PID_FILE).write_text(
        json.dumps({"supervisor_pid": 123, "control_token": "token"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(v11, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(v11, "_supervisor_identity_matches", lambda data, directory: False)

    with pytest.raises(v11.V11Error, match="refusing to signal"):
        v11.stop_run(run)


def test_harness_completion_requires_strict_monitor_evidence(tmp_path: Path) -> None:
    log = tmp_path / "harness.log"
    log.write_text("Agent exited normally\n", encoding="utf-8")
    assert v11._harness_reports_completion(log) is False

    log.write_text(
        "2026-07-21 22:30:00,123 - __main__ - INFO - "
        "Termination condition met: hall_of_fame=1 >= 1\n",
        encoding="utf-8",
    )
    assert v11._harness_reports_completion(log) is True

    log.write_text(
        "2026-07-21 22:30:00,123 - cli - INFO - [codex:mcp_tool_call] "
        "termination_condition_met hall_of_fame=1\n",
        encoding="utf-8",
    )
    assert v11._harness_reports_completion(log) is False


def test_hall_of_fame_completion_latches_across_server_shutdown() -> None:
    latched = v11._latch_hall_of_fame(False, {"hall_of_fame_verified": True})

    assert latched is True
    assert v11._latch_hall_of_fame(latched, {"server_reachable": False}) is True
    assert (
        v11._terminal_reason(
            completed=latched,
            disk_guard=False,
            time_limit=False,
            operator_requested=False,
            harness_return_code=130,
        )
        == "strict_hall_of_fame"
    )


def test_meaningful_events_ignore_motion_but_capture_story_changes() -> None:
    before = {
        "server_reachable": True,
        "location": "PalletTown",
        "map_name": "PalletTown",
        "position": {"x": 1, "y": 2},
        "objective_index": {"story": 0},
        "current_objective": "story: Leave home",
        "milestones_completed": 1,
        "badges": [],
        "party_size": 0,
        "hall_of_fame_verified": False,
    }
    moved = {**before, "position": {"x": 1, "y": 3}}
    assert v11._meaningful_changes(before, moved) == {}

    advanced = {
        **moved,
        "location": "Route1",
        "map_name": "Route1",
        "objective_index": {"story": 1},
        "current_objective": "story: Reach Viridian City",
        "milestones_completed": 2,
    }
    changes = v11._meaningful_changes(moved, advanced)
    assert set(changes) == {
        "location",
        "map_name",
        "objective_index",
        "current_objective",
        "milestones_completed",
    }


def test_event_log_redacts_extra_state_and_hashes_private_keyframe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    (run / v11.KEYFRAMES_DIRECTORY).mkdir(parents=True)
    (run / v11.EVENTS_FILE).touch()
    png = b"\x89PNG\r\n\x1a\nprivate-frame-bytes"
    encoded = base64.b64encode(png).decode("ascii")
    monkeypatch.setattr(
        v11,
        "_http_json",
        lambda url: {"screenshot_base64": encoded, "private": "/sensitive/example"},
    )
    snapshot = {
        "server_reachable": True,
        "location": "PalletTown",
        "map_name": "PalletTown",
        "position": {"x": 3, "y": 4},
        "badges": [],
        "party_size": 0,
        "hall_of_fame_verified": False,
        "rom_path": "/sensitive/source/Pokemon Red.gb",
        "visual": {"screenshot": "must-not-persist"},
    }

    event = v11._append_event(
        run,
        snapshot,
        None,
        elapsed_seconds=12.5,
        sequence=0,
        port=8_775,
    )

    assert event is not None
    serialized = (run / v11.EVENTS_FILE).read_text(encoding="utf-8")
    assert "rom_path" not in serialized
    assert "must-not-persist" not in serialized
    assert "/sensitive/source" not in serialized
    assert event["keyframe"]["path"].startswith("keyframes/")
    keyframe = run / event["keyframe"]["path"]
    assert keyframe.read_bytes() == png
    assert event["keyframe"]["sha256"] == hashlib.sha256(png).hexdigest()


def test_runtime_guards_distinguish_disk_and_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(v11, "_free_gib", lambda path: 9.0)
    assert (
        v11._runtime_guard_reason(
            tmp_path,
            minimum_free_gib=10.0,
            elapsed_seconds=1.0,
            max_seconds=100.0,
        )
        == "disk_guard"
    )
    monkeypatch.setattr(v11, "_free_gib", lambda path: 100.0)
    assert (
        v11._runtime_guard_reason(
            tmp_path,
            minimum_free_gib=10.0,
            elapsed_seconds=100.0,
            max_seconds=100.0,
        )
        == "time_limit"
    )
    assert (
        v11._terminal_reason(
            completed=False,
            disk_guard=True,
            time_limit=False,
            operator_requested=False,
        )
        == "disk_guard"
    )


def test_unexpected_nonzero_harness_exit_is_an_error() -> None:
    assert (
        v11._terminal_reason(
            completed=False,
            disk_guard=False,
            time_limit=False,
            operator_requested=False,
            harness_return_code=2,
        )
        == "harness_error"
    )
    assert v11._terminal_state("harness_error") == "failed"
    assert (
        v11._terminal_reason(
            completed=False,
            disk_guard=False,
            time_limit=False,
            operator_requested=False,
            harness_return_code=0,
        )
        == "unexpected_harness_exit"
    )
    assert v11._terminal_state("unexpected_harness_exit") == "failed"
    assert (
        v11._terminal_reason(
            completed=False,
            disk_guard=False,
            time_limit=True,
            operator_requested=False,
            harness_return_code=130,
        )
        == "time_limit"
    )


def test_supervisor_process_timeout_helper_does_not_raise() -> None:
    class TimedOutProcess:
        def wait(self, timeout: float) -> int:
            raise subprocess.TimeoutExpired("v11", timeout)

    assert v11._wait_for_process(TimedOutProcess(), 0.01) is False  # type: ignore[arg-type]
