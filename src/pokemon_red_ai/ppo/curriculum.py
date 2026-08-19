"""Verified-curriculum import, freezing, retention, and state round-tripping."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_red_ai.apprentice_data import preprocess_apprentice_frame
from pokemon_red_ai.blind import (
    FrozenSnapshot,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    ExpeditionStore,
    MilestoneProgress,
    referee_summary_for_state,
)
from pokemon_red_ai.milestones import MILESTONE_BY_KEY, MILESTONES
from pokemon_red_ai.ppo.artifacts import (
    _atomic_gzip_json,
    _atomic_json,
    _read_gzip_json,
    _resolve_checkpoint_artifact,
    _sha256_file,
)
from pokemon_red_ai.ppo.config import ParallelPpoConfig
from pokemon_red_ai.ppo.constants import (
    PPO_PROTOCOL,
    PPO_V8_PROTOCOL,
    PPO_V9_PROTOCOL,
    PPO_V10_PROTOCOL,
    PPO_V12_PROTOCOL,
)
from pokemon_red_ai.state import (
    PokemonRedStateReader,
)


def _checkpoint_view(run_directory: Path) -> tuple[ExpeditionStore, dict[str, Any]]:
    checkpoint_path = run_directory / "checkpoint.json.gz"
    previous_path = run_directory / "checkpoint.previous.json.gz"
    error: Exception | None = None
    for path in (checkpoint_path, previous_path):
        try:
            checkpoint = _read_gzip_json(path)
            store_path = run_directory / "frontier"
            event_bytes = (store_path / "events.jsonl").read_bytes()
            offset = int(checkpoint["store_event_byte_offset"])
            if offset < 0 or offset > len(event_bytes):
                raise ValueError("Expedition checkpoint event boundary is invalid")
            store = ExpeditionStore.open_checkpoint_view(
                store_path,
                event_payload=event_bytes[:offset],
                cell_ids=checkpoint["store_cell_ids"],
            )
            return store, checkpoint
        except Exception as caught:  # The previous atomic checkpoint is the fallback.
            error = caught
    raise ValueError("No valid expedition checkpoint can seed PPO") from error


def _canonical_progress(key: str) -> MilestoneProgress:
    if key == "power_on":
        return MilestoneProgress("power_on", 0, "Power-on")
    milestone = MILESTONE_BY_KEY.get(key)
    if milestone is None:
        raise ValueError(f"Curriculum uses unknown milestone {key!r}")
    return MilestoneProgress(milestone.key, milestone.ordinal + 1, milestone.label)


def _milestone_label(index: int) -> str:
    if index == 0:
        return "Power-on"
    if not 0 < index <= len(MILESTONES):
        raise ValueError("Milestone index is outside the canonical catalogue")
    return MILESTONES[index - 1].label


def _import_verified_ppo_curriculum(
    source_run: Path,
    curriculum_directory: Path,
    *,
    target_protocol: str = PPO_PROTOCOL,
) -> dict[str, Any]:
    """Import only replay-admitted curriculum from a cleanly finished PPO run."""

    source_manifest_path = source_run / "curriculum" / "manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_protocol = source_manifest.get("protocol")
    if source_protocol not in {
        "parallel-recurrent-ppo-v4",
        "parallel-recurrent-ppo-v5",
        "parallel-recurrent-ppo-v5.1",
        "parallel-recurrent-ppo-v5.2",
        "parallel-recurrent-ppo-v6",
        "parallel-recurrent-ppo-v7",
        "parallel-recurrent-ppo-v8",
        "parallel-recurrent-ppo-v9",
        "parallel-recurrent-ppo-v10",
        "parallel-recurrent-ppo-v12",
    }:
        raise ValueError("Version 7 can import only a verified Version-4-or-later curriculum")
    source_status = json.loads((source_run / "status.json").read_text(encoding="utf-8"))
    source_checkpoint = json.loads((source_run / "checkpoint.json").read_text(encoding="utf-8"))
    if source_status.get("state") != "finished" or source_status.get("stop_reason") not in {
        "stop_requested",
        "duration_limit",
        "action_limit",
        "hall_of_fame_verified",
    }:
        raise ValueError("PPO curriculum source is not a cleanly finished run")
    if source_checkpoint.get("protocol") != source_protocol:
        raise ValueError("PPO curriculum source checkpoint has the wrong protocol")
    if source_checkpoint.get("best_milestone") != source_manifest.get("best_milestone"):
        raise ValueError("PPO curriculum source best milestone is inconsistent")
    if source_checkpoint.get("total_actions") != source_status.get("total_actions"):
        raise ValueError("PPO curriculum source terminal action counts disagree")
    if _sha256_file(source_run / "ppo-latest.zip") != source_checkpoint.get("model_file_sha256"):
        raise ValueError("PPO curriculum source model failed its checkpoint hash")
    novelty_files = source_checkpoint.get("novelty_files")
    expected_environments = int(source_checkpoint.get("config", {}).get("environments", 0))
    if not isinstance(novelty_files, list) or len(novelty_files) != expected_environments:
        raise ValueError("PPO curriculum source lacks one novelty memory per worker")
    novelty_ranks: set[int] = set()
    for metadata in novelty_files:
        rank = int(metadata.get("rank", -1))
        if rank < 0 or rank >= expected_environments or rank in novelty_ranks:
            raise ValueError("PPO curriculum source novelty ranks are invalid")
        novelty_ranks.add(rank)
        filename = str(metadata.get("file", ""))
        if Path(filename).name != filename:
            raise ValueError("PPO curriculum source novelty filename is unsafe")
        if _sha256_file(source_run / filename) != metadata.get("file_sha256"):
            raise ValueError("PPO curriculum source novelty memory failed its hash")

    source_entries = source_manifest.get("entries")
    if not isinstance(source_entries, list) or not source_entries:
        raise ValueError("PPO curriculum source has no entries")
    validated: list[tuple[dict[str, Any], Path, Path, MilestoneProgress]] = []
    for metadata in source_entries:
        relative = Path(str(metadata.get("file", "")))
        if len(relative.parts) != 2 or relative.parts[0] != "entries":
            raise ValueError("PPO curriculum entry path is unsafe")
        source_path = source_run / "curriculum" / relative
        if _sha256_file(source_path) != metadata.get("file_sha256"):
            raise ValueError("PPO curriculum entry failed its source hash")
        payload = _read_gzip_json(source_path)
        progress = _canonical_progress(str(payload.get("progress", {}).get("key", "")))
        source_progress = _progress_from_value(payload["progress"])
        if progress.key != source_progress.key or progress.index != source_progress.index:
            raise ValueError("PPO curriculum entry changed ordinal across protocols")
        validated.append((dict(metadata), relative, source_path, progress))
    source_best = max(validated, key=lambda item: item[3].index)[3].public_dict()
    if source_best != source_manifest.get("best_milestone"):
        raise ValueError("PPO curriculum source entries disagree with its best milestone")

    curriculum_directory.mkdir(parents=True, exist_ok=False)
    target_entries = curriculum_directory / "entries"
    target_entries.mkdir()
    entries: list[dict[str, Any]] = []
    for metadata, relative, source_path, progress in validated:
        target_path = target_entries / relative.name
        shutil.copy2(source_path, target_path)
        entry = metadata
        entry.update(
            {
                "file": f"entries/{relative.name}",
                "file_sha256": _sha256_file(target_path),
                "milestone_id": progress.key,
                "milestone_index": progress.index,
                "milestone_label": progress.label,
            }
        )
        entries.append(entry)
    if sum(int(item["milestone_index"]) == 0 for item in entries) != 1:
        raise ValueError("PPO curriculum import requires one power-on root")
    best = max(entries, key=lambda item: int(item["milestone_index"]))
    manifest = {
        "schema_version": 1,
        "protocol": target_protocol,
        "source_protocol": source_manifest["protocol"],
        "source_run": source_run.name,
        "entries": entries,
        "best_milestone": {
            "key": best["milestone_id"],
            "index": best["milestone_index"],
            "label": best["milestone_label"],
        },
        "verified_promotions": int(source_manifest.get("verified_promotions", 0)),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _copy_retained_ppo_policy(
    source_run: Path,
    destination: Path,
    config: ParallelPpoConfig,
) -> dict[str, Any]:
    """Copy one clean compatible PPO policy and optimizer into a new campaign."""

    status = json.loads((source_run / "status.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((source_run / "checkpoint.json").read_text(encoding="utf-8"))
    manifest = json.loads((source_run / "manifest.json").read_text(encoding="utf-8"))
    source_protocol = checkpoint.get("protocol")
    if source_protocol not in {
        "parallel-recurrent-ppo-v5.2",
        "parallel-recurrent-ppo-v6",
        "parallel-recurrent-ppo-v7",
    }:
        raise ValueError("Consolidation requires a Version-5.2-or-later PPO policy")
    if status.get("state") != "finished" or status.get("stop_reason") not in {
        "stop_requested",
        "duration_limit",
        "action_limit",
        "hall_of_fame_verified",
    }:
        raise ValueError("Retained PPO policy source is not a cleanly finished run")
    if checkpoint.get("total_actions") != status.get("total_actions"):
        raise ValueError("Retained PPO policy terminal action counts disagree")
    if manifest.get("actor_mode") != config.mode:
        raise ValueError("Retained PPO policy actor mode is incompatible")
    source_config = checkpoint.get("config", {})
    compatible = (
        "mode",
        "rollout_steps",
        "batch_size",
        "epochs",
        "learning_rate",
        "gamma",
        "entropy_coefficient",
    )
    mismatched = [
        name for name in compatible if source_config.get(name) != config.public_dict().get(name)
    ]
    if mismatched:
        raise ValueError(
            "Retained PPO policy training shape changed: " + ", ".join(sorted(mismatched))
        )
    source_model = source_run / "ppo-latest.zip"
    expected_hash = checkpoint.get("model_file_sha256")
    if _sha256_file(source_model) != expected_hash:
        raise ValueError("Retained PPO policy failed its terminal hash")
    shutil.copy2(source_model, destination)
    return {
        "kind": "retained_ppo_policy_and_optimizer",
        "source_run": source_run.name,
        "source_protocol": source_protocol,
        "source_total_actions": int(status["total_actions"]),
        "source_best_milestone": status["best_milestone"],
        "file": destination.name,
        "file_sha256": _sha256_file(destination),
        "optimizer_state_retained": True,
        "new_campaign_timestep_counter": True,
    }


def freeze_verified_curriculum(
    expedition_run: Path,
    curriculum_directory: Path,
    *,
    target_protocol: str = PPO_PROTOCOL,
) -> dict[str, Any]:
    """Copy a verified Archive-v2 or completed PPO curriculum into a private run."""

    expedition_run = expedition_run.expanduser().resolve()
    if (expedition_run / "curriculum" / "manifest.json").is_file():
        return _import_verified_ppo_curriculum(
            expedition_run,
            curriculum_directory,
            target_protocol=target_protocol,
        )

    store, checkpoint = _checkpoint_view(expedition_run)
    curriculum_directory.mkdir(parents=True, exist_ok=False)
    (curriculum_directory / "entries").mkdir()
    active_ids = [str(value) for value in checkpoint["archive"]["active_cell_ids"]]
    candidates = [store.cells[cell_id] for cell_id in active_ids]
    verified = [cell for cell in candidates if not store.verification_deficits(cell.cell_id)]
    if not verified:
        raise ValueError("Source expedition has no verified curriculum cells")

    selected: dict[tuple[int, int | None], Any] = {}
    for cell in verified:
        key = (cell.descriptor.milestone_index, cell.descriptor.map_id)
        current = selected.get(key)
        if current is None or (
            cell.discovered_global_action,
            -cell.depth_actions,
            cell.cell_id,
        ) > (
            current.discovered_global_action,
            -current.depth_actions,
            current.cell_id,
        ):
            selected[key] = cell
    roots = [cell for cell in verified if cell.parent_id is None]
    if len(roots) != 1:
        raise ValueError("PPO curriculum requires one verified power-on root")
    selected[(0, None)] = roots[0]

    entries: list[dict[str, Any]] = []
    for cell in sorted(
        selected.values(),
        key=lambda item: (item.descriptor.milestone_index, item.cell_id),
    ):
        index = cell.descriptor.milestone_index
        canonical_label = "Power-on" if index == 0 else MILESTONES[index - 1].label
        progress = MilestoneProgress(
            cell.descriptor.milestone_id,
            index,
            str(cell.referee_summary.get("milestone_label", canonical_label)),
        )
        payload = {
            "schema_version": 1,
            "entry_id": cell.cell_id,
            "source_cell_id": cell.cell_id,
            "progress": progress.public_dict(),
            "snapshot": store.read_snapshot(cell.snapshot_sha256).checkpoint_dict(),
            "lineage_actions": [
                action.public_dict() for action in store.lineage_actions(cell.cell_id)
            ],
        }
        path = curriculum_directory / "entries" / f"{cell.cell_id}.json.gz"
        _atomic_gzip_json(path, payload)
        entries.append(
            {
                "entry_id": cell.cell_id,
                "file": f"entries/{path.name}",
                "file_sha256": _sha256_file(path),
                "milestone_id": progress.key,
                "milestone_index": progress.index,
                "milestone_label": progress.label,
                "map_id": cell.descriptor.map_id,
                "depth_actions": cell.depth_actions,
                "source": "verified_expedition",
            }
        )
    best = max(entries, key=lambda item: int(item["milestone_index"]))
    manifest = {
        "schema_version": 1,
        "protocol": target_protocol,
        "source_run": expedition_run.name,
        "entries": entries,
        "best_milestone": {
            "key": best["milestone_id"],
            "index": best["milestone_index"],
            "label": best["milestone_label"],
        },
        "verified_promotions": 0,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def create_verified_power_on_curriculum(
    rom_path: Path,
    curriculum_directory: Path,
    *,
    target_protocol: str = PPO_V12_PROTOCOL,
) -> dict[str, Any]:
    """Create V12's sole starting state directly from two clean ROM boots.

    Earlier self-taught versions imported a completed run merely to obtain its power-on snapshot
    and then deleted every later entry. V12 removes that awkward dependency: it creates the root
    itself and proves that a second clean emulator accepts the exact frozen state before training.
    No controller action, predecessor snapshot, or predecessor policy participates.
    """

    if curriculum_directory.exists():
        raise ValueError("Direct power-on curriculum output already exists")
    curriculum_directory.mkdir(parents=True)
    (curriculum_directory / "entries").mkdir()
    progress = MilestoneProgress("power_on", 0, "Power-on")
    with PokemonRedEmulator(rom_path) as emulator:
        state = PokemonRedStateReader(emulator).read()
        screen = preprocess_apprentice_frame(emulator.screen_rgb())
        snapshot = FrozenSnapshot.freeze(emulator.save_state())
        screen_sha256 = hashlib.sha256(screen.tobytes()).hexdigest()
        referee = referee_summary_for_state(state, progress)
    with PokemonRedEmulator(rom_path) as verifier:
        verifier.load_state(snapshot.thaw())
        verified_state = PokemonRedStateReader(verifier).read()
        verified_screen = preprocess_apprentice_frame(verifier.screen_rgb())
        if verified_state != state or hashlib.sha256(verified_screen.tobytes()).hexdigest() != (
            screen_sha256
        ):
            raise RuntimeError("Direct power-on snapshot failed its clean-emulator replay gate")

    entry_id = f"power-on-{snapshot.sha256[:16]}"
    payload = {
        "schema_version": 1,
        "entry_id": entry_id,
        "source_cell_id": None,
        "progress": progress.public_dict(),
        "snapshot": snapshot.checkpoint_dict(),
        "lineage_actions": [],
        "terminal_referee_summary": referee,
        "clean_boot_replay_passes": 1,
        "controller_actions": 0,
    }
    path = curriculum_directory / "entries" / f"{entry_id}.json.gz"
    _atomic_gzip_json(path, payload)
    entry = {
        "entry_id": entry_id,
        "file": f"entries/{path.name}",
        "file_sha256": _sha256_file(path),
        "milestone_id": progress.key,
        "milestone_index": progress.index,
        "milestone_label": progress.label,
        "map_id": None,
        "depth_actions": 0,
        "source": "direct_verified_clean_boot",
    }
    manifest = {
        "schema_version": 1,
        "protocol": target_protocol,
        "source_protocol": "direct-verified-clean-boot-v1",
        "source_run": None,
        "entries": [entry],
        "best_milestone": progress.public_dict(),
        "verified_promotions": 0,
        "power_on_only": True,
        "discarded_inherited_entries": 0,
        "clean_boot_replay_passes": 1,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _retain_power_on_only(curriculum_directory: Path) -> dict[str, Any]:
    """Remove inherited lessons while retaining one verified clean-start snapshot."""

    manifest = _load_curriculum_manifest(curriculum_directory)
    roots = [entry for entry in manifest["entries"] if int(entry["milestone_index"]) == 0]
    if len(roots) != 1:
        raise ValueError("Fresh self-taught curriculum requires one power-on root")
    root = roots[0]
    retained = curriculum_directory / str(root["file"])
    for entry in manifest["entries"]:
        path = curriculum_directory / str(entry["file"])
        if path != retained:
            path.unlink()
    manifest["discarded_inherited_entries"] = len(manifest["entries"]) - 1
    manifest["entries"] = [root]
    manifest["best_milestone"] = {
        "key": "power_on",
        "index": 0,
        "label": "Power-on",
    }
    manifest["verified_promotions"] = 0
    manifest["power_on_only"] = True
    manifest["updated_at"] = datetime.now(UTC).isoformat()
    _atomic_json(curriculum_directory / "manifest.json", manifest)
    return manifest


def _load_curriculum_manifest(directory: Path) -> dict[str, Any]:
    value = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if value.get("protocol") not in {
        PPO_PROTOCOL,
        PPO_V8_PROTOCOL,
        PPO_V9_PROTOCOL,
        PPO_V10_PROTOCOL,
        PPO_V12_PROTOCOL,
    } or not isinstance(value.get("entries"), list):
        raise ValueError("PPO curriculum manifest is invalid")
    return value


def _load_curriculum_entry(directory: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    path = directory / str(metadata["file"])
    if _sha256_file(path) != metadata["file_sha256"]:
        raise ValueError("PPO curriculum entry hash is invalid")
    return _read_gzip_json(path)


def _validate_curriculum_state(
    directory: Path,
    value: Mapping[str, Any],
    *,
    expected_protocol: str,
) -> None:
    if value.get("protocol") != expected_protocol:
        raise ValueError("PPO curriculum checkpoint uses the wrong protocol")
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("PPO curriculum checkpoint has no entries")
    identifiers: set[str] = set()
    roots = 0
    best_entry: Mapping[str, Any] | None = None
    for metadata in entries:
        if not isinstance(metadata, Mapping):
            raise ValueError("PPO curriculum checkpoint entry is invalid")
        entry_id = str(metadata.get("entry_id", ""))
        if not entry_id or entry_id in identifiers:
            raise ValueError("PPO curriculum checkpoint entry IDs are invalid")
        identifiers.add(entry_id)
        relative = Path(str(metadata.get("file", "")))
        if (
            relative.is_absolute()
            or len(relative.parts) != 2
            or relative.parts[0] != "entries"
            or ".." in relative.parts
        ):
            raise ValueError("PPO curriculum checkpoint entry path is unsafe")
        payload = _load_curriculum_entry(directory, metadata)
        if str(payload.get("entry_id")) != entry_id:
            raise ValueError("PPO curriculum checkpoint entry ID changed")
        progress = _progress_from_value(payload["progress"])
        if progress.index != int(metadata["milestone_index"]):
            raise ValueError("PPO curriculum checkpoint milestone index changed")
        roots += int(progress.index == 0)
        if best_entry is None or int(metadata["milestone_index"]) > int(
            best_entry["milestone_index"]
        ):
            best_entry = metadata
    if roots != 1 or best_entry is None:
        raise ValueError("PPO curriculum checkpoint needs one power-on root")
    best = value.get("best_milestone")
    if (
        not isinstance(best, Mapping)
        or int(best.get("index", -1)) != int(best_entry["milestone_index"])
        or str(best.get("key")) != str(best_entry["milestone_id"])
        or str(best.get("label")) != str(best_entry["milestone_label"])
    ):
        raise ValueError("PPO curriculum checkpoint best milestone is inconsistent")


def _checkpoint_curriculum_state(
    run_directory: Path,
    curriculum_directory: Path,
    *,
    protocol: str,
) -> dict[str, str]:
    value = _load_curriculum_manifest(curriculum_directory)
    _validate_curriculum_state(
        curriculum_directory,
        value,
        expected_protocol=protocol,
    )
    snapshot = curriculum_directory / "manifest.checkpoint.json"
    previous = curriculum_directory / "manifest.checkpoint.previous.json"
    if snapshot.exists():
        os.replace(snapshot, previous)
    _atomic_json(snapshot, value)
    return {
        "curriculum_checkpoint_file": "curriculum/manifest.checkpoint.json",
        "curriculum_file_sha256": _sha256_file(snapshot),
    }


def _restore_curriculum_state(
    run_directory: Path,
    curriculum_directory: Path,
    checkpoint: Mapping[str, Any],
    *,
    protocol: str,
) -> dict[str, Any]:
    filename = checkpoint.get("curriculum_checkpoint_file")
    if filename != "curriculum/manifest.checkpoint.json":
        raise ValueError("PPO checkpoint has no valid curriculum snapshot")
    try:
        snapshot = _resolve_checkpoint_artifact(
            run_directory,
            latest_name=filename,
            previous_name="curriculum/manifest.checkpoint.previous.json",
            expected_sha256=checkpoint.get("curriculum_file_sha256"),
        )
    except ValueError as error:
        raise ValueError("PPO curriculum snapshot does not match its checkpoint") from error
    value = json.loads(snapshot.read_text(encoding="utf-8"))
    _validate_curriculum_state(
        curriculum_directory,
        value,
        expected_protocol=protocol,
    )
    _atomic_json(curriculum_directory / "manifest.json", value)
    return value


def _progress_from_value(value: Mapping[str, Any]) -> MilestoneProgress:
    return MilestoneProgress(str(value["key"]), int(value["index"]), str(value["label"]))
