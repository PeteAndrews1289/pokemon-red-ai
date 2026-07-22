"""Lifecycle supervisor for the V11 hierarchical Pokemon Red agent.

V11 intentionally delegates gameplay to a pinned copy of Continual Harness while
keeping launch safety, provenance, process control, and story-friendly status
snapshots in this repository.  Runtime files are private and belong on the T7,
never in Git.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_red_ai.rom import RomFingerprint, resolve_rom_path, verify_rom

UPSTREAM_COMMIT = "bbab97ad73e460b7cd7c08527d10ced30cc03fbe"
DEFAULT_HARNESS = Path("/Volumes/T7 Developer/PokemonRedAI/v11/continual-harness-bbab97ad73e4")
DEFAULT_RUN_ROOT = Path("/Volumes/T7 Developer/PokemonRedAI/v11/runs")
DEFAULT_PORT = 8_775
DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_MIN_FREE_GIB = 50.0
DEFAULT_NARRATIVE_SECONDS = 3_600.0
DEFAULT_POLL_SECONDS = 30.0
CONTROL_MANIFEST = "manifest.json"
PID_FILE = "pid.json"
STATUS_FILE = "status.json"
NARRATIVE_FILE = "narrative.md"
EVENTS_FILE = "events.jsonl"
KEYFRAMES_DIRECTORY = "keyframes"
SUPERVISOR_LOG = "supervisor.log"
HARNESS_LOG = "harness.log"
TRUSTED_HALL_OF_FAME_LOG_LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} - (?:__main__|run_cli) - INFO - "
    r"Termination condition met: hall_of_fame=1 >= 1$"
)
V11_OVERLAY_FILES = (
    ".gitignore",
    "agents/__init__.py",
    "agents/objectives/all_obj_categorized_red.py",
    "agents/prompts/cli-agent-directives/pokemon_expert_directive.md",
    "pokemon_red_env/red_emulator.py",
    "pokemon_red_env/red_memory_reader.py",
    "pokemon_env/__init__.py",
    "requirements-red-codex.txt",
    "run_cli.py",
    "server/app.py",
    "server/cli/pokemon_mcp_server.py",
    "server/frame_server.py",
    "server/game_tools.py",
    "server/stream.html",
    "tests/test_cli_expert_mcp_proxy.py",
    "tests/test_opening_referee.py",
    "tests/test_red_state_truth.py",
    "tests/test_red_completion_safety.py",
    "tests/test_v11_local_codex.py",
    "tests/test_v11_security.py",
    "utils/agent_infrastructure/cli_agent_backends.py",
    "utils/data_persistence/backup_manager.py",
    "utils/state_formatter.py",
)
V11_MCP_TOOLS = frozenset(
    {
        "get_game_state",
        "press_buttons",
        "navigate_to",
        "process_memory",
        "add_memory",
        "search_memory",
        "get_memory_summary",
        "get_memory_overview",
        "complete_direct_objective",
        "get_progress_summary",
        "replan_objectives",
        "reflect",
    }
)
PUBLIC_SNAPSHOT_FIELDS = (
    "server_reachable",
    "server_step_count",
    "agent_step_count",
    "total_actions",
    "total_llm_calls",
    "location",
    "map_id",
    "map_name",
    "position",
    "context",
    "in_battle",
    "badges",
    "party_size",
    "pokedex_seen",
    "pokedex_caught",
    "milestones_completed",
    "milestones_total",
    "objective_index",
    "objectives_total",
    "current_objective",
    "hall_of_fame_verified",
)
MEANINGFUL_EVENT_FIELDS = (
    "server_reachable",
    "location",
    "map_id",
    "map_name",
    "objective_index",
    "current_objective",
    "milestones_completed",
    "badges",
    "party_size",
    "hall_of_fame_verified",
)
CLEAN_START_ENV_BLOCKLIST = (
    "BACKUP_STATE",
    "CHECKPOINT_STATE",
    "LOAD_BACKUP",
    "LOAD_STATE",
    "POKEMON_RED_ROM",
    "ROM_PATH",
    "RUN_DATA_ID",
    "SAVE_STATE",
)


class V11Error(RuntimeError):
    """Raised when a V11 lifecycle operation is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class V11Config:
    """Immutable launch settings for one clean-start V11 run."""

    rom: Path
    output: Path
    harness: Path = DEFAULT_HARNESS
    directive: Path | None = None
    python: Path | None = None
    port: int = DEFAULT_PORT
    min_free_gib: float = DEFAULT_MIN_FREE_GIB
    narrative_seconds: float = DEFAULT_NARRATIVE_SECONDS
    poll_seconds: float = DEFAULT_POLL_SECONDS
    max_seconds: float | None = None
    model: str = DEFAULT_MODEL
    record: bool = True

    def resolved(self) -> V11Config:
        project_root = Path(__file__).resolve().parents[2]
        harness = self.harness.expanduser().resolve()
        directive = self.directive or project_root / "configs" / "v11-codex-directive.md"
        python = self.python or harness / ".venv-red-codex" / "bin" / "python"
        # Do not resolve the final interpreter symlink: Python uses that venv path
        # to discover pyvenv.cfg and its installed site-packages.
        python = Path(os.path.abspath(str(python.expanduser())))
        return V11Config(
            rom=self.rom.expanduser().resolve(),
            output=self.output.expanduser().resolve(),
            harness=harness,
            directive=directive.expanduser().resolve(),
            python=python,
            port=self.port,
            min_free_gib=self.min_free_gib,
            narrative_seconds=self.narrative_seconds,
            poll_seconds=self.poll_seconds,
            max_seconds=self.max_seconds,
            model=self.model,
            record=self.record,
        )


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def public_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "checks": [asdict(check) for check in self.checks]}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise V11Error(f"V11 control file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise V11Error(f"V11 control file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise V11Error(f"V11 control file must contain an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_capture(command: list[str], *, cwd: Path | None = None, timeout: float = 15) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise V11Error(f"Command failed ({result.returncode}): {message or command[0]}")
    return (result.stdout or result.stderr).strip()


def _free_gib(path: Path) -> float:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    if not candidate.exists():
        raise V11Error(f"Cannot find an existing parent for output path: {path}")
    return shutil.disk_usage(candidate).free / (1024**3)


def _port_available(port: int) -> bool:
    if not 1 <= port <= 65_535:
        return False
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def _find_codex() -> Path:
    discovered = shutil.which("codex")
    if discovered:
        return Path(discovered).resolve()
    bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if bundled.is_file():
        return bundled.resolve()
    raise V11Error("Codex CLI is not available")


def _check(name: str, action: Any) -> DoctorCheck:
    try:
        detail = action()
    except Exception as exc:  # Each doctor result should be actionable, not abort the list.
        return DoctorCheck(name=name, ok=False, detail=str(exc))
    return DoctorCheck(name=name, ok=True, detail=str(detail))


def _validate_local_codex_command(command: list[str]) -> str:
    joined = " ".join(command)
    required = (
        "--sandbox workspace-write",
        'approval_policy="never"',
        "sandbox_workspace_write.network_access=false",
        "--model gpt-5.6-terra",
        "model_reasoning_effort=medium",
    )
    missing = [fragment for fragment in required if fragment not in joined]
    if missing:
        raise V11Error("local Codex command lacks safety pins: " + ", ".join(missing))
    if "--dangerously-bypass-approvals-and-sandbox" in joined:
        raise V11Error("local Codex command bypasses host approvals and sandbox")
    return "workspace-write sandbox, no approvals, network denied, Terra medium"


def _validate_local_mcp_policy(policy: dict[str, Any]) -> str:
    """Require unattended access only to the audited private gameplay surface."""

    if policy.get("required") is not True:
        raise V11Error("Pokémon MCP server is not required at planner startup")
    if policy.get("default_tools_approval_mode") != "approve":
        raise V11Error("Pokémon MCP tools are not pre-approved for unattended play")
    enabled = policy.get("enabled_tools")
    if not isinstance(enabled, list) or set(enabled) != V11_MCP_TOOLS:
        raise V11Error("Pokémon MCP enabled-tools list does not match the audited 12-tool surface")
    return "required, pre-approved, exact 12-tool allowlist"


def doctor(config: V11Config, *, require_open_port: bool = True) -> DoctorReport:
    """Validate every local prerequisite without mutating or starting a run."""

    config = config.resolved()

    def check_rom() -> str:
        fingerprint = verify_rom(resolve_rom_path(config.rom))
        return f"supported ROM ({fingerprint.sha1})"

    def check_harness() -> str:
        required = ("run_cli.py", "server/app.py", "server/cli/pokemon_mcp_server.py")
        missing = [relative for relative in required if not (config.harness / relative).is_file()]
        if missing:
            raise V11Error(f"missing harness files: {', '.join(missing)}")
        return str(config.harness)

    def check_commit() -> str:
        actual = _run_capture(["git", "rev-parse", "HEAD"], cwd=config.harness)
        if actual != UPSTREAM_COMMIT:
            raise V11Error(f"harness commit {actual} != pinned {UPSTREAM_COMMIT}")
        return actual

    def check_local_patch() -> str:
        source = (config.harness / "run_cli.py").read_text(encoding="utf-8")
        required = ("--local-agent", "--expert-mode", "--agent-model", "hall_of_fame")
        missing = [flag for flag in required if flag not in source]
        if missing:
            raise V11Error(f"installed harness lacks V11 local patch: {', '.join(missing)}")
        return "local-agent, expert tools, and Hall-of-Fame monitor available"

    def check_overlay_provenance() -> str:
        provenance = _harness_overlay_provenance(config.harness)
        return f"sha256:{provenance['sha256']} ({len(provenance['files'])} files)"

    def check_python() -> str:
        if config.python is None or not config.python.is_file():
            raise V11Error(f"V11 Python environment is missing: {config.python}")
        reported = _run_capture(
            [
                str(config.python),
                "-c",
                "import sys; print('.'.join(map(str, sys.version_info[:3])))",
            ]
        )
        major, minor, *_ = (int(part) for part in reported.split("."))
        if (major, minor) not in {(3, 10), (3, 11)}:
            raise V11Error(f"Continual Harness requires Python 3.10 or 3.11, found {reported}")
        return reported

    def check_lean_imports() -> str:
        if config.python is None:
            raise V11Error("resolved V11 config lacks Python path")
        probe = _run_capture(
            [
                str(config.python),
                "-c",
                (
                    "from agents.objectives import DirectObjectiveManager; "
                    "from utils.state_formatter import format_state_for_llm; "
                    "print('lean-imports-ok')"
                ),
            ],
            cwd=config.harness,
            timeout=30,
        )
        if probe != "lean-imports-ok":
            raise V11Error(f"lean import probe returned unexpected output: {probe}")
        return probe

    def check_local_codex_security() -> str:
        if config.python is None:
            raise V11Error("resolved V11 config lacks Python path")
        script = (
            "import json,os,tempfile,tomllib; from pathlib import Path; "
            "from utils.agent_infrastructure.cli_agent_backends import CodexCliBackend; "
            "os.environ['POKEAGENT_CLI_EXPERT']='1'; os.environ['GAME_TYPE']='red'; "
            "tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name); "
            "directive=root/'directive.md'; directive.write_text('doctor'); "
            "backend=CodexCliBackend(); "
            "cmd,_,_,_=backend.build_launch_cmd(str(directive),'http://127.0.0.1:8775',"
            "str(root/'work'),project_root=str(Path.cwd()),containerized=False,"
            "thinking_effort='medium',agent_memory_dir=str(root/'codex'),"
            "agent_model='gpt-5.6-terra'); "
            "parsed=tomllib.loads((root/'codex'/'config.toml').read_text()); "
            "print(json.dumps({'command':cmd,'mcp_policy':"
            "parsed['mcp_servers']['pokemon-emerald']}))"
        )
        raw = _run_capture([str(config.python), "-c", script], cwd=config.harness, timeout=30)
        try:
            probe = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise V11Error(
                "local Codex dry-run did not return command and MCP policy data"
            ) from exc
        if not isinstance(probe, dict):
            raise V11Error("local Codex dry-run returned invalid policy data")
        command = probe.get("command")
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise V11Error("local Codex dry-run returned an invalid command")
        policy = probe.get("mcp_policy")
        if not isinstance(policy, dict):
            raise V11Error("local Codex dry-run returned an invalid MCP policy")
        command_result = _validate_local_codex_command(command)
        policy_result = _validate_local_mcp_policy(policy)
        return f"{command_result}; Pokémon MCP {policy_result}"

    def check_directive() -> str:
        if config.directive is None or not config.directive.is_file():
            raise V11Error(f"V11 Codex directive is missing: {config.directive}")
        return f"sha256:{_sha256_file(config.directive)}"

    def check_codex() -> str:
        codex = _find_codex()
        status = _run_capture([str(codex), "login", "status"])
        if "logged in" not in status.lower():
            raise V11Error(f"Codex is not logged in: {status}")
        return status

    def check_disk() -> str:
        available = _free_gib(config.output)
        if available < config.min_free_gib:
            raise V11Error(
                f"only {available:.1f} GiB free; V11 requires {config.min_free_gib:.1f} GiB"
            )
        return f"{available:.1f} GiB free"

    def check_supervision() -> str:
        if config.poll_seconds <= 0:
            raise V11Error("poll interval must be positive")
        if config.narrative_seconds <= 0:
            raise V11Error("narrative interval must be positive")
        if config.max_seconds is not None and config.max_seconds <= 0:
            raise V11Error("maximum runtime must be positive when supplied")
        if not config.model.strip():
            raise V11Error("planner model must not be empty")
        limit = "unbounded" if config.max_seconds is None else f"{config.max_seconds:.0f}s"
        return (
            f"poll={config.poll_seconds:.0f}s narrative={config.narrative_seconds:.0f}s max={limit}"
        )

    def check_private_storage() -> str:
        home = Path.home().resolve()
        for label, path in (("output", config.output), ("harness", config.harness)):
            if path == home or path.is_relative_to(home):
                raise V11Error(f"{label} must be outside the home directory; use the T7")
        return "runtime and public records are outside the home directory"

    checks = [
        _check("rom", check_rom),
        _check("harness", check_harness),
        _check("pinned_commit", check_commit),
        _check("local_patch", check_local_patch),
        _check("overlay_provenance", check_overlay_provenance),
        _check("python", check_python),
        _check("lean_imports", check_lean_imports),
        _check("local_codex_security", check_local_codex_security),
        _check("directive", check_directive),
        _check("codex_auth", check_codex),
        _check("disk", check_disk),
        _check("supervision", check_supervision),
        _check("private_storage", check_private_storage),
    ]
    if require_open_port:
        port_is_available = _port_available(config.port)
        checks.append(
            DoctorCheck(
                name="port",
                ok=port_is_available,
                detail=(
                    f"127.0.0.1:{config.port} is available"
                    if port_is_available
                    else f"127.0.0.1:{config.port} is already in use or invalid"
                ),
            )
        )
    return DoctorReport(checks=tuple(checks))


def _stage_rom(config: V11Config) -> tuple[Path, str]:
    """Expose the verified private ROM at the fixed upstream path without copying it."""

    source = resolve_rom_path(config.rom)
    verify_rom(source)
    destination = config.harness / "PokemonRed-GBC" / "pokered.gbc"
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_symlink():
        if destination.resolve() != source:
            raise V11Error(
                "Harness ROM symlink points to a different file; refusing to replace it: "
                f"{destination}"
            )
        return destination, "existing_symlink"
    if destination.exists():
        verify_rom(destination)
        return destination, "existing_verified_file"

    destination.symlink_to(source)
    return destination, "created_symlink"


def _safe_run_name(output: Path, token: str) -> str:
    clean = "".join(character if character.isalnum() else "_" for character in output.name)
    clean = clean.strip("_")[:40] or "v11"
    return f"{clean}_{token[:8]}"


def build_harness_command(
    config: V11Config,
    run_name: str,
    *,
    directive: Path | None = None,
) -> list[str]:
    """Build the exact clean-start upstream command used by the supervisor."""

    config = config.resolved()
    directive = directive or config.directive
    if config.python is None or directive is None:
        raise V11Error("resolved V11 config lacks Python or directive path")
    command = [
        str(config.python),
        str(config.harness / "run_cli.py"),
        "--game",
        "red",
        "--backend",
        "codex",
        "--api-gateway",
        "login",
        "--local-agent",
        "--expert-mode",
        "--directive",
        str(directive),
        "--port",
        str(config.port),
        "--run-name",
        run_name,
        "--direct-objectives",
        "categorized_full_game",
        "--termination-condition",
        "hall_of_fame",
        "--termination-threshold",
        "1",
        "--agent-thinking-effort",
        "medium",
        "--agent-model",
        config.model,
    ]
    if config.record:
        command.append("--record")
    return command


def _public_harness_command(command: list[str], config: V11Config) -> list[str]:
    staged_directive = config.output / "directive.md"
    replacements = {
        str(config.python): "<HARNESS>/.venv-red-codex/bin/python",
        str(config.harness / "run_cli.py"): "<HARNESS>/run_cli.py",
        str(staged_directive): "<RUN>/directive.md",
    }
    return [replacements.get(part, part) for part in command]


def _git_worktree_status(harness: Path) -> dict[str, str]:
    output = _run_capture(
        ["git", "status", "--porcelain=v2", "--untracked-files=all"],
        cwd=harness,
    )
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        if line.startswith("? "):
            statuses[line[2:]] = "untracked"
        elif line.startswith("1 "):
            parts = line.split(" ", 8)
            if len(parts) == 9:
                statuses[parts[8]] = parts[1]
        elif line.startswith("2 "):
            parts = line.split(" ", 9)
            if len(parts) == 10:
                statuses[parts[9].split("\t", 1)[0]] = parts[1]
    return statuses


def _harness_overlay_provenance(harness: Path) -> dict[str, Any]:
    """Hash every expected overlay file, including untracked additions and status."""

    statuses = _git_worktree_status(harness)
    unexpected = sorted(set(statuses) - set(V11_OVERLAY_FILES))
    if unexpected:
        raise V11Error(
            "Harness has changed files outside the declared V11 overlay: " + ", ".join(unexpected)
        )

    files: list[dict[str, Any]] = []
    for relative in V11_OVERLAY_FILES:
        path = harness / relative
        if not path.is_file():
            raise V11Error(f"V11 overlay file is missing: {relative}")
        files.append(
            {
                "path": relative,
                "git_status": statuses.get(relative, "clean"),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "files": files}


def _assert_public_manifest_is_sanitized(manifest: dict[str, Any], config: V11Config) -> None:
    serialized = json.dumps(manifest, sort_keys=True)
    forbidden = {
        "source ROM path": str(config.rom),
        "home directory": str(Path.home().resolve()),
        "home username": Path.home().name,
    }
    leaked = [label for label, value in forbidden.items() if value and value in serialized]
    if leaked:
        raise V11Error("Public V11 manifest contains " + ", ".join(leaked))


def _prepared_manifest_matches(config: V11Config, manifest: dict[str, Any]) -> bool:
    if config.directive is None:
        return False
    try:
        fingerprint = verify_rom(resolve_rom_path(config.rom))
        run_name = str(manifest["run_name"])
        staged_directive = config.output / "directive.md"
        expected_command = build_harness_command(config, run_name, directive=staged_directive)
        private = _read_json(config.output / PID_FILE)
        overlay = _harness_overlay_provenance(config.harness)
        expected_supervision = {
            "poll_seconds": config.poll_seconds,
            "narrative_seconds": config.narrative_seconds,
            "minimum_free_gib": config.min_free_gib,
            "max_seconds": config.max_seconds,
        }
        return (
            manifest.get("state") == "prepared"
            and manifest.get("output_directory") == "."
            and manifest.get("harness", {}).get("installation") == config.harness.name
            and manifest.get("harness", {}).get("local_overlay") == overlay
            and manifest.get("rom") == fingerprint.public_dict()
            and manifest.get("directive", {}).get("path") == "directive.md"
            and manifest.get("directive", {}).get("sha256") == _sha256_file(config.directive)
            and _sha256_file(staged_directive) == _sha256_file(config.directive)
            and manifest.get("harness_command") == _public_harness_command(expected_command, config)
            and private.get("harness_path") == str(config.harness)
            and private.get("harness_command") == expected_command
            and manifest.get("supervision") == expected_supervision
        )
    except (KeyError, OSError, TypeError, V11Error):
        return False


def prepare_run(
    config: V11Config,
    *,
    token: str | None = None,
    skip_doctor: bool = False,
) -> dict[str, Any]:
    """Create a private, provenance-complete control directory for a clean run."""

    config = config.resolved()
    if config.output.exists() and any(config.output.iterdir()):
        existing_manifest = config.output / CONTROL_MANIFEST
        if existing_manifest.is_file():
            existing = _read_json(existing_manifest)
            if _prepared_manifest_matches(config, existing):
                _stage_rom(config)
                return existing
            if existing.get("state") == "prepared":
                raise V11Error(
                    "Prepared output belongs to different V11 settings; choose a new directory"
                )
        raise V11Error(f"Output directory is not empty: {config.output}")

    if not skip_doctor:
        report = doctor(config)
        if not report.ok:
            failures = "; ".join(
                f"{check.name}: {check.detail}" for check in report.checks if not check.ok
            )
            raise V11Error(f"V11 doctor failed: {failures}")

    fingerprint: RomFingerprint = verify_rom(resolve_rom_path(config.rom))
    staged_rom, staging_method = _stage_rom(config)
    config.output.mkdir(parents=True, exist_ok=True)
    if config.directive is None:
        raise V11Error("resolved V11 config lacks directive path")
    staged_directive = config.output / "directive.md"
    staged_directive.write_bytes(config.directive.read_bytes())
    token = token or secrets.token_hex(16)
    run_name = _safe_run_name(config.output, token)
    command = build_harness_command(config, run_name, directive=staged_directive)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "state": "prepared",
        "prepared_at": _utc_now(),
        "run_name": run_name,
        "output_directory": ".",
        "harness": {
            "installation": config.harness.name,
            "upstream_commit": UPSTREAM_COMMIT,
            "local_overlay": _harness_overlay_provenance(config.harness),
        },
        "rom": fingerprint.public_dict(),
        "rom_staging": {
            "method": staging_method,
            "fixed_harness_path": str(staged_rom.relative_to(config.harness)),
        },
        "experiment": {
            "game": "red",
            "backend": "codex",
            "auth": "ChatGPT login",
            "local_agent": True,
            "expert_mode": True,
            "objective_sequence": "categorized_full_game",
            "termination": "strict_hall_of_fame",
            "clean_power_on": True,
            "load_state": False,
            "load_checkpoint": False,
            "reasoning_effort": "medium",
            "planner_model": config.model,
            "port": config.port,
            "dashboard_url": f"http://127.0.0.1:{config.port}/stream",
        },
        "supervision": {
            "poll_seconds": config.poll_seconds,
            "narrative_seconds": config.narrative_seconds,
            "minimum_free_gib": config.min_free_gib,
            "max_seconds": config.max_seconds,
        },
        "directive": {
            "path": "directive.md",
            "sha256": _sha256_file(staged_directive),
        },
        "harness_command": _public_harness_command(command, config),
    }
    _assert_public_manifest_is_sanitized(manifest, config)
    _atomic_json(config.output / CONTROL_MANIFEST, manifest)
    _atomic_json(
        config.output / PID_FILE,
        {
            "schema_version": 1,
            "control_token": token,
            "harness_path": str(config.harness),
            "harness_command": command,
        },
    )
    _atomic_json(
        config.output / STATUS_FILE,
        {
            "state": "prepared",
            "updated_at": _utc_now(),
            "run_name": run_name,
            "planner_model": config.model,
            "dashboard_url": f"http://127.0.0.1:{config.port}/stream",
        },
    )
    narrative = config.output / NARRATIVE_FILE
    narrative.write_text(
        "# V11 run narrative\n\n"
        "This file is appended from measured emulator and harness state. "
        "It does not invent progress.\n\n",
        encoding="utf-8",
    )
    (config.output / EVENTS_FILE).touch(exist_ok=True)
    (config.output / KEYFRAMES_DIRECTORY).mkdir(exist_ok=True)
    return manifest


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _process_command(pid: int) -> str:
    try:
        return _run_capture(["ps", "-p", str(pid), "-o", "command="], timeout=5)
    except V11Error:
        return ""


def _supervisor_identity_matches(pid_data: dict[str, Any], run_directory: Path) -> bool:
    pid = int(pid_data.get("supervisor_pid", 0))
    token = str(pid_data.get("control_token", ""))
    command = _process_command(pid)
    return (
        _pid_alive(pid)
        and "pokemon_red_ai.v11" in command
        and "_supervise" in command
        and str(run_directory) in command
        and token in command
    )


def _supervisor_record_matches(
    pid_data: dict[str, Any],
    *,
    control_token: str,
    process_id: int,
) -> bool:
    return (
        pid_data.get("control_token") == control_token
        and int(pid_data.get("supervisor_pid", 0)) == process_id
    )


def launch_run(config: V11Config, *, skip_doctor: bool = False) -> dict[str, Any]:
    """Prepare and detach a supervisor, returning only after its PID is recorded."""

    config = config.resolved()
    if not skip_doctor:
        report = doctor(config)
        if not report.ok:
            failures = "; ".join(
                f"{check.name}: {check.detail}" for check in report.checks if not check.ok
            )
            raise V11Error(f"V11 doctor failed: {failures}")
    manifest = prepare_run(config, skip_doctor=True)
    if (config.output / PID_FILE).exists():
        pid_data = _read_json(config.output / PID_FILE)
        if int(pid_data.get("supervisor_pid", 0)) > 1 and _supervisor_identity_matches(
            pid_data, config.output
        ):
            raise V11Error(f"V11 is already running with PID {pid_data['supervisor_pid']}")

    pid_data = _read_json(config.output / PID_FILE)
    token = str(pid_data["control_token"])
    supervisor_command = [
        sys.executable,
        "-m",
        "pokemon_red_ai.v11",
        "_supervise",
        str(config.output),
        token,
    ]
    manifest["state"] = "launching"
    manifest["launched_at"] = _utc_now()
    _atomic_json(config.output / CONTROL_MANIFEST, manifest)
    _atomic_json(
        config.output / STATUS_FILE,
        {
            "state": "launching",
            "updated_at": _utc_now(),
            "run_name": manifest["run_name"],
            "planner_model": manifest["experiment"]["planner_model"],
            "dashboard_url": manifest["experiment"]["dashboard_url"],
        },
    )
    supervisor_log = (config.output / SUPERVISOR_LOG).open("a", encoding="utf-8")
    try:
        try:
            process = subprocess.Popen(
                supervisor_command,
                cwd=Path(__file__).resolve().parents[2],
                stdin=subprocess.DEVNULL,
                stdout=supervisor_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            manifest["state"] = "launch_failed"
            manifest["launch_error"] = "supervisor_start_failed"
            _atomic_json(config.output / CONTROL_MANIFEST, manifest)
            _atomic_json(
                config.output / STATUS_FILE,
                {
                    "state": "launch_failed",
                    "updated_at": _utc_now(),
                    "error": "supervisor_start_failed; see private launch output",
                },
            )
            raise V11Error(f"Could not start V11 supervisor: {exc}") from exc
    finally:
        supervisor_log.close()

    pid_data.update(
        {
            "supervisor_pid": process.pid,
            "started_at": _utc_now(),
            "supervisor_command": supervisor_command,
        }
    )
    _atomic_json(config.output / PID_FILE, pid_data)
    _atomic_json(
        config.output / STATUS_FILE,
        {
            "state": "launching",
            "updated_at": _utc_now(),
            "run_name": manifest["run_name"],
            "supervisor_pid": process.pid,
            "planner_model": manifest["experiment"]["planner_model"],
            "dashboard_url": manifest["experiment"]["dashboard_url"],
        },
    )
    return {
        "state": "launching",
        "run_directory": str(config.output),
        "supervisor_pid": process.pid,
        "planner_model": manifest["experiment"]["planner_model"],
        "dashboard_url": manifest["experiment"]["dashboard_url"],
    }


def _http_json(url: str, *, timeout: float = 5) -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _sanitize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Allowlist measured story fields before they reach status or event artifacts."""

    public = {field: snapshot.get(field) for field in PUBLIC_SNAPSHOT_FIELDS}
    position = public.get("position")
    public["position"] = (
        {"x": position.get("x"), "y": position.get("y")}
        if isinstance(position, dict)
        else {"x": None, "y": None}
    )
    badges = public.get("badges")
    public["badges"] = list(badges) if isinstance(badges, list) else []
    return public


def _progress_snapshot(port: int) -> dict[str, Any]:
    """Fetch a compact, screenshot-free status snapshot from the live harness."""

    root = f"http://127.0.0.1:{port}"
    server = _http_json(f"{root}/status") or {}
    state = _http_json(f"{root}/state") or {}
    milestones = _http_json(f"{root}/milestones") or {}
    metrics = _http_json(f"{root}/metrics") or {}
    completion = (
        _http_json(f"{root}/termination_condition?condition_type=hall_of_fame&threshold=1") or {}
    )
    player = state.get("player") if isinstance(state.get("player"), dict) else {}
    game = state.get("game") if isinstance(state.get("game"), dict) else {}
    map_data = state.get("map") if isinstance(state.get("map"), dict) else {}
    objective_data = (
        milestones.get("objectives") if isinstance(milestones.get("objectives"), dict) else {}
    )
    if objective_data.get("mode") == "categorized":
        categorized_status = (
            objective_data.get("categorized_status")
            if isinstance(objective_data.get("categorized_status"), dict)
            else {}
        )
        objective_indices: dict[str, Any] = {}
        objective_totals: dict[str, Any] = {}
        objective_text: list[str] = []
        for category in ("story", "battling", "dynamics"):
            category_status = (
                categorized_status.get(category)
                if isinstance(categorized_status.get(category), dict)
                else {}
            )
            objective_indices[category] = category_status.get("current_index")
            objective_totals[category] = category_status.get("total")
            rows = objective_data.get(category)
            if isinstance(rows, list):
                current = next(
                    (row for row in rows if isinstance(row, dict) and row.get("current") is True),
                    None,
                )
                if current:
                    description = current.get("description") or current.get("id")
                    if description:
                        objective_text.append(f"{category}: {description}")
        current_objective: Any = "; ".join(objective_text) or None
        objective_index: Any = objective_indices
        objectives_total: Any = objective_totals
    else:
        current_objective = objective_data.get("current")
        if isinstance(current_objective, dict):
            current_objective = (
                current_objective.get("description")
                or current_objective.get("title")
                or current_objective.get("id")
            )
        objective_index = objective_data.get("current_index")
        objectives_total = objective_data.get("total_in_sequence")
    position = player.get("position") if isinstance(player.get("position"), dict) else {}
    badge_value = game.get("badges")
    badges = badge_value if isinstance(badge_value, list) else []
    completed_milestones = milestones.get("completed")
    if completed_milestones is None and isinstance(milestones.get("milestones"), list):
        completed_milestones = sum(
            1
            for item in milestones["milestones"]
            if isinstance(item, dict) and item.get("completed")
        )
    return _sanitize_snapshot(
        {
            "server_reachable": bool(server),
            "server_step_count": server.get("step_count"),
            "agent_step_count": metrics.get("agent_step_count"),
            "total_actions": metrics.get("total_actions"),
            "total_llm_calls": metrics.get("total_llm_calls"),
            "location": player.get("location"),
            "map_id": map_data.get("id") or map_data.get("map_id"),
            "map_name": map_data.get("name") or map_data.get("map_name") or player.get("location"),
            "position": {"x": position.get("x"), "y": position.get("y")},
            "context": game.get("game_state"),
            "in_battle": game.get("is_in_battle"),
            "badges": badges,
            "party_size": len(player.get("party") or []),
            "pokedex_seen": game.get("pokedex_seen"),
            "pokedex_caught": game.get("pokedex_caught"),
            "milestones_completed": completed_milestones,
            "milestones_total": milestones.get("total"),
            "objective_index": objective_index,
            "objectives_total": objectives_total,
            "current_objective": current_objective,
            "hall_of_fame_verified": bool(completion.get("condition_met")),
        }
    )


def _event_value(field: str, value: Any) -> Any:
    if field == "badges" and isinstance(value, list):
        return sorted(str(badge) for badge in value)
    return value


def _meaningful_changes(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return only story changes worthy of a keyframe and event row."""

    current = _sanitize_snapshot(current)
    if not current.get("server_reachable"):
        return {}
    previous_public = _sanitize_snapshot(previous or {})
    first_reachable = not previous_public.get("server_reachable")
    changes: dict[str, dict[str, Any]] = {}
    for field in MEANINGFUL_EVENT_FIELDS:
        old = _event_value(field, previous_public.get(field))
        new = _event_value(field, current.get(field))
        if field == "server_reachable" and first_reachable:
            changes[field] = {"from": False, "to": True}
        elif first_reachable:
            if new not in (None, "", [], {}):
                changes[field] = {"from": None, "to": new}
        elif old != new:
            changes[field] = {"from": old, "to": new}
    return changes


def _capture_keyframe(
    port: int,
    run_directory: Path,
    *,
    sequence: int,
    changed_fields: list[str],
) -> dict[str, Any] | None:
    payload = _http_json(f"http://127.0.0.1:{port}/screenshot") or {}
    encoded = payload.get("screenshot_base64")
    if not isinstance(encoded, str) or not encoded:
        return None
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        image = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not image.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    label = "-".join(changed_fields[:3]) or "state"
    label = "".join(
        character if character.isalnum() or character == "-" else "_" for character in label
    )
    relative = Path(KEYFRAMES_DIRECTORY) / f"{sequence:06d}-{label[:60]}.png"
    destination = run_directory / relative
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_bytes(image)
    os.replace(temporary, destination)
    return {
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(image).hexdigest(),
        "size_bytes": len(image),
    }


def _append_event(
    run_directory: Path,
    snapshot: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    elapsed_seconds: float,
    sequence: int,
    port: int,
) -> dict[str, Any] | None:
    public_snapshot = _sanitize_snapshot(snapshot)
    changes = _meaningful_changes(previous, public_snapshot)
    if not changes:
        return None
    keyframe = _capture_keyframe(
        port,
        run_directory,
        sequence=sequence,
        changed_fields=list(changes),
    )
    event: dict[str, Any] = {
        "schema_version": 1,
        "sequence": sequence,
        "timestamp_utc": _utc_now(),
        "elapsed_seconds": elapsed_seconds,
        "changed_fields": changes,
        "snapshot": public_snapshot,
    }
    if keyframe is not None:
        event["keyframe"] = keyframe
    with (run_directory / EVENTS_FILE).open("a", encoding="utf-8") as destination:
        destination.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        destination.flush()
        os.fsync(destination.fileno())
    return event


def _discover_upstream_run(harness: Path, run_name: str) -> str | None:
    candidates = sorted(
        (path for path in (harness / "run_data").glob(f"*_{run_name}") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0].relative_to(harness).as_posix() if candidates else None


def _append_narrative(path: Path, snapshot: dict[str, Any], *, elapsed_seconds: float) -> None:
    timestamp = _utc_now()
    location = snapshot.get("location") or "not yet observable"
    position = snapshot.get("position") or {}
    coords = f"({position.get('x')}, {position.get('y')})"
    objective = snapshot.get("current_objective") or "not yet reported"
    badges = snapshot.get("badges") or []
    milestone_count = snapshot.get("milestones_completed")
    milestone_total = snapshot.get("milestones_total")
    lines = [
        f"## {timestamp}",
        "",
        f"- Elapsed: {elapsed_seconds / 3600:.2f} hours",
        f"- Location: {location} {coords}",
        f"- Current objective: {objective}",
        f"- Agent steps / controller actions: {snapshot.get('agent_step_count')} / "
        f"{snapshot.get('total_actions')}",
        f"- Milestones: {milestone_count} / {milestone_total}",
        f"- Badges: {', '.join(str(badge) for badge in badges) if badges else 'none'}",
        f"- Party size: {snapshot.get('party_size')}",
        f"- Hall of Fame verified: {snapshot.get('hall_of_fame_verified', False)}",
        "",
    ]
    with path.open("a", encoding="utf-8") as destination:
        destination.write("\n".join(lines) + "\n")


def _wait_for_process(process: subprocess.Popen[Any], timeout: float) -> bool:
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


def _stop_child(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    for signum, timeout in ((signal.SIGINT, 30.0), (signal.SIGTERM, 10.0)):
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            return
        if _wait_for_process(process, timeout):
            return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    _wait_for_process(process, 5.0)


def _harness_reports_completion(log_path: Path) -> bool:
    """Recognize the upstream monitor's strict-success message without trusting exit code."""

    try:
        with log_path.open("rb") as source:
            source.seek(0, os.SEEK_END)
            source.seek(max(0, source.tell() - 128 * 1024))
            tail = source.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    return any(TRUSTED_HALL_OF_FAME_LOG_LINE.fullmatch(line) for line in tail.splitlines())


def _terminal_reason(
    *,
    completed: bool,
    disk_guard: bool,
    time_limit: bool,
    operator_requested: bool,
    harness_return_code: int = 0,
) -> str:
    if completed:
        return "strict_hall_of_fame"
    if disk_guard:
        return "disk_guard"
    if time_limit:
        return "time_limit"
    if operator_requested:
        return "operator_request"
    if harness_return_code != 0:
        return "harness_error"
    # An unbounded run has no healthy reason to end here: strict completion,
    # runtime guards, and an operator stop are all handled above.  Treat even
    # a zero exit as a failure so an upstream fallthrough cannot masquerade as
    # a successful experiment (the first V11 canary exposed exactly this).
    return "unexpected_harness_exit"


def _terminal_state(stop_reason: str) -> str:
    if stop_reason == "strict_hall_of_fame":
        return "completed"
    if stop_reason in {"disk_guard", "time_limit", "operator_request"}:
        return "stopped"
    if stop_reason in {"harness_error", "unexpected_harness_exit"}:
        return "failed"
    return "finished"


def _runtime_guard_reason(
    run_directory: Path,
    *,
    minimum_free_gib: float,
    elapsed_seconds: float,
    max_seconds: float | None,
) -> str | None:
    if _free_gib(run_directory) < minimum_free_gib:
        return "disk_guard"
    if max_seconds is not None and elapsed_seconds >= max_seconds:
        return "time_limit"
    return None


def _latch_hall_of_fame(latched: bool, snapshot: dict[str, Any]) -> bool:
    return latched or bool(snapshot.get("hall_of_fame_verified"))


def _clean_start_environment(source: dict[str, str]) -> dict[str, str]:
    environment = source.copy()
    for name in CLEAN_START_ENV_BLOCKLIST:
        environment.pop(name, None)
    environment["LOAD_CHECKPOINT_MODE"] = "false"
    return environment


def supervise(run_directory: Path, control_token: str) -> int:
    """Run the harness, checkpoint its story state, and own graceful shutdown."""

    run_directory = run_directory.expanduser().resolve()
    manifest_path = run_directory / CONTROL_MANIFEST
    manifest = _read_json(manifest_path)
    pid_path = run_directory / PID_FILE
    pid_deadline = time.monotonic() + 10.0
    recorded_pid: dict[str, Any] = {}
    while time.monotonic() < pid_deadline:
        if pid_path.is_file():
            recorded_pid = _read_json(pid_path)
            if _supervisor_record_matches(
                recorded_pid,
                control_token=control_token,
                process_id=os.getpid(),
            ):
                break
        time.sleep(0.05)
    else:
        raise V11Error("Launcher did not publish this supervisor's PID record")
    if not _supervisor_record_matches(  # Defensive recheck after the polling hand-off.
        recorded_pid,
        control_token=control_token,
        process_id=os.getpid(),
    ):
        raise V11Error("Supervisor PID record does not match this process")
    harness = Path(recorded_pid["harness_path"])
    command = [str(part) for part in recorded_pid["harness_command"]]
    port = int(manifest["experiment"]["port"])
    poll_seconds = max(1.0, float(manifest["supervision"]["poll_seconds"]))
    narrative_seconds = max(poll_seconds, float(manifest["supervision"]["narrative_seconds"]))
    minimum_free_gib = float(manifest["supervision"]["minimum_free_gib"])
    raw_max_seconds = manifest["supervision"].get("max_seconds")
    max_seconds = float(raw_max_seconds) if raw_max_seconds is not None else None

    stop_requested = threading.Event()
    operator_requested = threading.Event()

    def handle_stop(signum: int, frame: Any) -> None:
        del signum, frame
        operator_requested.set()
        stop_requested.set()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    launch_command = command
    caffeinate = shutil.which("caffeinate")
    if caffeinate:
        launch_command = [caffeinate, "-is", *command]
    environment = _clean_start_environment(dict(os.environ))
    environment["POKEAGENT_CLI_EXPERT"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"
    path_parts = [str(Path(command[0]).parent), str(_find_codex().parent)]
    if environment.get("PATH"):
        path_parts.append(environment["PATH"])
    environment["PATH"] = os.pathsep.join(path_parts)
    log_handle = (run_directory / HARNESS_LOG).open("a", encoding="utf-8")
    started = time.monotonic()
    process: subprocess.Popen[Any] | None = None
    return_code = 1
    last_snapshot: dict[str, Any] = {}
    last_event_snapshot: dict[str, Any] | None = None
    event_sequence = sum(1 for _ in (run_directory / EVENTS_FILE).open("r", encoding="utf-8"))
    disk_guard_reached = False
    time_limit_reached = False
    completion_latched = False
    try:
        process = subprocess.Popen(
            launch_command,
            cwd=harness,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        pid_data = _read_json(pid_path)
        pid_data["harness_pid"] = process.pid
        pid_data["harness_command"] = launch_command
        _atomic_json(run_directory / PID_FILE, pid_data)
        manifest["state"] = "running"
        manifest["harness_started_at"] = _utc_now()
        _atomic_json(manifest_path, manifest)

        last_narrative = -narrative_seconds
        while process.poll() is None and not stop_requested.is_set():
            elapsed = time.monotonic() - started
            guard_reason = _runtime_guard_reason(
                run_directory,
                minimum_free_gib=minimum_free_gib,
                elapsed_seconds=elapsed,
                max_seconds=max_seconds,
            )
            if guard_reason == "disk_guard":
                disk_guard_reached = True
                stop_requested.set()
                break
            if guard_reason == "time_limit":
                time_limit_reached = True
                stop_requested.set()
                break
            snapshot = _progress_snapshot(port)
            completion_latched = _latch_hall_of_fame(completion_latched, snapshot)
            if snapshot.get("server_reachable"):
                last_snapshot = snapshot
                event = _append_event(
                    run_directory,
                    snapshot,
                    last_event_snapshot,
                    elapsed_seconds=elapsed,
                    sequence=event_sequence,
                    port=port,
                )
                if event is not None:
                    event_sequence += 1
                last_event_snapshot = snapshot
            if completion_latched:
                stop_requested.set()
            upstream_run = _discover_upstream_run(harness, str(manifest["run_name"]))
            status = {
                "state": "running",
                "updated_at": _utc_now(),
                "elapsed_seconds": elapsed,
                "supervisor_pid": os.getpid(),
                "harness_pid": process.pid,
                "run_name": manifest["run_name"],
                "planner_model": manifest["experiment"]["planner_model"],
                "upstream_run_directory": upstream_run,
                "dashboard_url": manifest["experiment"]["dashboard_url"],
                "progress": snapshot,
            }
            _atomic_json(run_directory / STATUS_FILE, status)
            if elapsed - last_narrative >= narrative_seconds:
                _append_narrative(
                    run_directory / NARRATIVE_FILE,
                    snapshot,
                    elapsed_seconds=elapsed,
                )
                last_narrative = elapsed
            wait_seconds = poll_seconds
            if max_seconds is not None:
                wait_seconds = min(wait_seconds, max(0.05, max_seconds - elapsed))
            stop_requested.wait(wait_seconds)

        if stop_requested.is_set() and process.poll() is None:
            _stop_child(process)
        return_code = process.wait() if process.poll() is None else int(process.returncode or 0)
        final_snapshot = _progress_snapshot(port)
        if not final_snapshot.get("server_reachable") and last_snapshot:
            final_snapshot = last_snapshot
        elapsed = time.monotonic() - started
        completion = _latch_hall_of_fame(
            completion_latched, final_snapshot
        ) or _harness_reports_completion(run_directory / HARNESS_LOG)
        final_snapshot["hall_of_fame_verified"] = completion
        final_event = _append_event(
            run_directory,
            final_snapshot,
            last_event_snapshot,
            elapsed_seconds=elapsed,
            sequence=event_sequence,
            port=port,
        )
        if final_event is not None:
            event_sequence += 1
        stop_reason = _terminal_reason(
            completed=completion,
            disk_guard=disk_guard_reached,
            time_limit=time_limit_reached,
            operator_requested=operator_requested.is_set(),
            harness_return_code=return_code,
        )
        state = _terminal_state(stop_reason)
        error_summary = {
            "harness_error": "harness exited nonzero; see harness.log",
            "unexpected_harness_exit": (
                "harness exited without Hall of Fame, a runtime guard, or an operator stop; "
                "see harness.log"
            ),
        }.get(stop_reason)
        _atomic_json(
            run_directory / STATUS_FILE,
            {
                "state": state,
                "updated_at": _utc_now(),
                "elapsed_seconds": elapsed,
                "supervisor_pid": os.getpid(),
                "harness_pid": process.pid,
                "harness_return_code": return_code,
                "run_name": manifest["run_name"],
                "planner_model": manifest["experiment"]["planner_model"],
                "upstream_run_directory": _discover_upstream_run(
                    harness, str(manifest["run_name"])
                ),
                "dashboard_url": manifest["experiment"]["dashboard_url"],
                "stop_reason": stop_reason,
                "error": error_summary,
                "progress": final_snapshot,
            },
        )
        manifest["state"] = state
        manifest["finished_at"] = _utc_now()
        manifest["harness_return_code"] = return_code
        manifest["stop_reason"] = stop_reason
        if error_summary is not None:
            manifest["error"] = error_summary
        _atomic_json(manifest_path, manifest)
        _append_narrative(
            run_directory / NARRATIVE_FILE,
            final_snapshot,
            elapsed_seconds=elapsed,
        )
    except Exception as exc:
        elapsed = time.monotonic() - started
        _atomic_json(
            run_directory / STATUS_FILE,
            {
                "state": "failed",
                "updated_at": _utc_now(),
                "elapsed_seconds": elapsed,
                "supervisor_pid": os.getpid(),
                "harness_pid": process.pid if process is not None else None,
                "error_type": type(exc).__name__,
                "error": "supervisor_failed; see supervisor.log",
            },
        )
        manifest["state"] = "failed"
        manifest["finished_at"] = _utc_now()
        manifest["supervisor_error"] = "supervisor_failed; see supervisor.log"
        _atomic_json(manifest_path, manifest)
        raise
    finally:
        if process is not None and process.poll() is None:
            _stop_child(process)
        log_handle.close()
    return return_code


def run_status(run_directory: Path, *, poll_live: bool = True) -> dict[str, Any]:
    """Return persisted status plus a conservative live-process assessment."""

    run_directory = run_directory.expanduser().resolve()
    status = _read_json(run_directory / STATUS_FILE)
    pid_path = run_directory / PID_FILE
    if pid_path.is_file():
        pid_data = _read_json(pid_path)
        status["supervisor_alive"] = _supervisor_identity_matches(pid_data, run_directory)
    else:
        status["supervisor_alive"] = False
    if poll_live and status.get("supervisor_alive"):
        manifest = _read_json(run_directory / CONTROL_MANIFEST)
        status["live_progress"] = _progress_snapshot(int(manifest["experiment"]["port"]))
    return status


def stop_run(run_directory: Path, *, timeout: float = 45.0) -> dict[str, Any]:
    """Request graceful shutdown after verifying the exact supervisor identity."""

    run_directory = run_directory.expanduser().resolve()
    pid_data = _read_json(run_directory / PID_FILE)
    pid = int(pid_data.get("supervisor_pid", 0))
    if not _pid_alive(pid):
        return {"state": "not_running", "supervisor_pid": pid}
    if not _supervisor_identity_matches(pid_data, run_directory):
        raise V11Error("PID identity check failed; refusing to signal an unrelated process")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + max(0.0, timeout)
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    if _pid_alive(pid):
        raise V11Error(
            f"Supervisor PID {pid} did not stop within {timeout:.0f}s; inspect logs before forcing"
        )
    return run_status(run_directory, poll_live=False)


def _default_output() -> Path:
    stamp = datetime.now().strftime("v11-%Y%m%d-%H%M%S")
    return DEFAULT_RUN_ROOT / stamp


def _add_config_arguments(
    parser: argparse.ArgumentParser,
    *,
    output_required: bool = False,
) -> None:
    parser.add_argument("--rom", type=Path, required=True, help="Private Pokemon Red ROM path")
    parser.add_argument(
        "--output",
        type=Path,
        required=output_required,
        default=None if output_required else _default_output(),
        help="Private V11 control directory (defaults to the T7)",
    )
    parser.add_argument("--harness", type=Path, default=DEFAULT_HARNESS)
    parser.add_argument("--directive", type=Path)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--min-free-gib", type=float, default=DEFAULT_MIN_FREE_GIB)
    parser.add_argument("--narrative-seconds", type=float, default=DEFAULT_NARRATIVE_SECONDS)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument(
        "--max-seconds",
        type=float,
        help="Optional hard runtime guard; omit for an unlimited Hall-of-Fame run",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Pinned Codex planner model")
    parser.add_argument("--no-record", action="store_true")


def _config_from_args(args: argparse.Namespace) -> V11Config:
    return V11Config(
        rom=args.rom,
        output=args.output,
        harness=args.harness,
        directive=args.directive,
        python=args.python,
        port=args.port,
        min_free_gib=args.min_free_gib,
        narrative_seconds=args.narrative_seconds,
        poll_seconds=args.poll_seconds,
        max_seconds=args.max_seconds,
        model=args.model,
        record=not args.no_record,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokemon-red-ai-v11",
        description="Prepare, launch, observe, and stop the V11 Hall-of-Fame agent.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    doctor_parser = commands.add_parser("doctor", help="Check V11 without changing anything")
    _add_config_arguments(doctor_parser)
    prepare_parser = commands.add_parser("prepare", help="Prepare a private clean-start run")
    _add_config_arguments(prepare_parser)
    launch_parser = commands.add_parser("launch", help="Launch V11 detached under supervision")
    _add_config_arguments(launch_parser)
    status_parser = commands.add_parser("status", help="Show measured V11 progress")
    status_parser.add_argument("run_directory", type=Path)
    status_parser.add_argument("--no-live", action="store_true")
    stop_parser = commands.add_parser("stop", help="Gracefully stop an exact V11 run")
    stop_parser.add_argument("run_directory", type=Path)
    stop_parser.add_argument("--timeout", type=float, default=45.0)
    supervise_parser = commands.add_parser("_supervise", help="internal detached worker")
    supervise_parser.add_argument("run_directory", type=Path)
    supervise_parser.add_argument("control_token")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            report = doctor(_config_from_args(args))
            print(json.dumps(report.public_dict(), indent=2))
            return 0 if report.ok else 1
        if args.command == "prepare":
            payload = prepare_run(_config_from_args(args))
        elif args.command == "launch":
            payload = launch_run(_config_from_args(args))
        elif args.command == "status":
            payload = run_status(args.run_directory, poll_live=not args.no_live)
        elif args.command == "stop":
            payload = stop_run(args.run_directory, timeout=args.timeout)
        elif args.command == "_supervise":
            return supervise(args.run_directory, args.control_token)
        else:  # pragma: no cover - argparse enforces the choices.
            raise V11Error(f"Unknown command: {args.command}")
    except V11Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
