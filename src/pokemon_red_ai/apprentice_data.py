from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np

import pokemon_red_ai.expedition as expedition_module
from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    visual_key,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    ExpeditionStore,
    MilestoneProgress,
    descriptor_from_state,
    milestone_progress_for_state,
    referee_summary_for_state,
)
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import verify_rom
from pokemon_red_ai.state import PokemonRedStateReader

APPRENTICE_DATASET_SCHEMA = 1
APPRENTICE_DATASET_PROTOCOL = "visual-apprentice-demonstration-v1"
APPRENTICE_OBSERVATION_PROTOCOL = "pixels-72x80-gray-v1"
APPRENTICE_FRAME_SHAPE = (72, 80)
APPRENTICE_RGB_SHAPE = (144, 160, 3)
PREVIOUS_ACTION_SENTINEL = -1
STAGE0_Q1_TARGET_CELL_ID = "4618cb56f99c95b594534474"
STAGE0_Q1_LINEAGE_SHA256 = (
    "84aa0179b01df7a8c9d5220d5bd5ba042f639489e2918459570b5c4e42d0c25c"
)
STAGE0_Q1_ACTION_COUNT = 419
STAGE0_Q1_MILESTONE_ID = "left_home"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_ARRAY_FILENAMES = {
    "frames": "frames.npy",
    "actions": "actions.npy",
    "previous_actions": "previous_actions.npy",
    "episode_starts": "episode_starts.npy",
}
_EXPECTED_FILES = {
    ".gitignore",
    "SUCCESS",
    "manifest.json",
    *_ARRAY_FILENAMES.values(),
}


class ApprenticeDatasetError(ValueError):
    """Raised when a demonstration cannot be proven or its payload is not intact."""


@dataclass(frozen=True, slots=True)
class ApprenticeDataset:
    """One verified, immutable sequence for pixels-only behavioral cloning.

    ``frames`` contains every decision boundary, including the terminal boundary. Therefore an
    episode with ``N`` target actions has ``N + 1`` frames. A trainer can construct the two-frame
    observation for action ``i`` as ``(frames[max(i - 1, 0)], frames[i])`` without copying frame
    pairs into the private dataset.
    """

    frames: np.ndarray
    actions: np.ndarray
    previous_actions: np.ndarray
    episode_starts: np.ndarray
    manifest: Mapping[str, Any]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _strict_json(payload: bytes, *, label: str) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ApprenticeDatasetError(f"{label} contains duplicate JSON keys")
            value[key] = item
        return value

    try:
        return json.loads(payload, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApprenticeDatasetError(f"{label} JSON is invalid") from error


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes(path: Path, payload: bytes) -> None:
    with path.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _write_npy(path: Path, value: np.ndarray) -> None:
    with path.open("xb") as output:
        np.save(output, value, allow_pickle=False)
        output.flush()
        os.fsync(output.fileno())


def _require_private_output_location(path: Path) -> None:
    """Reject derived ROM pixels inside Git unless the destination is ignored."""

    repository = next(
        (candidate for candidate in (path, *path.parents) if (candidate / ".git").exists()),
        None,
    )
    if repository is None:
        return
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", str(path)],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ApprenticeDatasetError(
            "Apprentice datasets contain ROM-derived pixels and must be outside Git or below "
            "an ignored path such as runs/"
        )


def _read_source_view(
    store_path: Path,
) -> tuple[ExpeditionStore, dict[str, bytes]]:
    """Open exactly the raw index/event prefix without invoking mutable store recovery."""

    raw = {
        "manifest": (store_path / "manifest.json").read_bytes(),
        "index": (store_path / "index.json").read_bytes(),
        "events": (store_path / "events.jsonl").read_bytes(),
    }
    index = _strict_json(raw["index"], label="Expedition index")
    if not isinstance(index, dict) or index.get("schema_version") != 1:
        raise ApprenticeDatasetError("Expedition index schema is not supported")
    cell_ids = index.get("cell_ids")
    if not isinstance(cell_ids, list) or any(not isinstance(item, str) for item in cell_ids):
        raise ApprenticeDatasetError("Expedition index cell IDs are invalid")
    try:
        store = ExpeditionStore.open_checkpoint_view(
            store_path,
            event_payload=raw["events"],
            cell_ids=cell_ids,
        )
    except (OSError, ValueError) as error:
        raise ApprenticeDatasetError(
            "The immutable expedition source prefix failed validation"
        ) from error
    if (store_path / "manifest.json").read_bytes() != raw["manifest"]:
        raise ApprenticeDatasetError("Expedition manifest changed while opening the source view")
    if (store_path / "index.json").read_bytes() != raw["index"]:
        raise ApprenticeDatasetError("Expedition index changed while opening the source view")
    if (store_path / "events.jsonl").read_bytes() != raw["events"]:
        raise ApprenticeDatasetError("Expedition events changed while opening the source view")
    return store, raw


def preprocess_apprentice_frame(pixels: np.ndarray) -> np.ndarray:
    """Convert one rendered RGB frame to the frozen 72x80 grayscale observation.

    Version 1 uses integer BT.601-style luma (77R + 150G + 29B, rounded before division by
    256), followed by an integer mean over each non-overlapping 2x2 block. No crop, interpolation,
    palette lookup, RAM, or emulator tile data enters the observation.
    """

    if not isinstance(pixels, np.ndarray):
        raise TypeError("Rendered pixels must be a NumPy array")
    if pixels.shape != APPRENTICE_RGB_SHAPE:
        raise ValueError(f"Expected rendered RGB shape {APPRENTICE_RGB_SHAPE}")
    if pixels.dtype != np.uint8:
        raise ValueError("Rendered RGB pixels must use uint8")
    rgb = pixels.astype(np.uint32, copy=False)
    gray = (
        77 * rgb[:, :, 0] + 150 * rgb[:, :, 1] + 29 * rgb[:, :, 2] + 128
    ) >> 8
    pooled = gray.reshape(72, 2, 80, 2).sum(axis=(1, 3)) // 4
    return np.ascontiguousarray(pooled, dtype=np.uint8)


def _validate_target(
    store: ExpeditionStore,
    target_cell_id: str,
    expected_lineage_sha256: str,
) -> tuple[Any, tuple[BlindAction, ...]]:
    if target_cell_id != STAGE0_Q1_TARGET_CELL_ID:
        raise ApprenticeDatasetError("Stage-0 requires the canonical Q1 promotion cell")
    if expected_lineage_sha256 != STAGE0_Q1_LINEAGE_SHA256:
        raise ApprenticeDatasetError("The explicit target cell has a different lineage hash")
    if _SHA256_PATTERN.fullmatch(expected_lineage_sha256) is None:
        raise ApprenticeDatasetError("Expected lineage hash must be lowercase SHA-256")
    if target_cell_id not in store.cells:
        raise ApprenticeDatasetError("The explicit target cell is absent from the source prefix")
    target = store.cells[target_cell_id]
    if target.lineage_sha256 != expected_lineage_sha256:
        raise ApprenticeDatasetError("The explicit target cell has a different lineage hash")
    if (
        target.depth_actions != STAGE0_Q1_ACTION_COUNT
        or target.descriptor.milestone_id != STAGE0_Q1_MILESTONE_ID
    ):
        raise ApprenticeDatasetError("Stage-0 target does not match the frozen Q1 task boundary")
    if target.parent_id is None:
        raise ApprenticeDatasetError("The apprentice target must be a named milestone promotion")
    parent = store.cells[target.parent_id]
    if target.descriptor.milestone_index <= parent.descriptor.milestone_index:
        raise ApprenticeDatasetError("The apprentice target is not a named milestone promotion")
    power_on_replays = store.successful_replay_count(target_cell_id)
    if power_on_replays < 3:
        raise ApprenticeDatasetError(
            "The apprentice target lacks three validated fresh power-on replays"
        )
    deficits = store.verification_deficits(target_cell_id)
    if deficits:
        raise ApprenticeDatasetError(
            "The apprentice target lineage has unresolved replay-verification deficits"
        )
    actions = tuple(store.iter_lineage_actions(target_cell_id))
    if len(actions) != target.depth_actions or not actions:
        raise ApprenticeDatasetError("The apprentice target action lineage is incomplete")
    if any(
        action.hold_frames != ACTION_HOLD_FRAMES
        or action.release_frames != ACTION_RELEASE_FRAMES
        for action in actions
    ):
        raise ApprenticeDatasetError(
            "Stage-0 accepts only the frozen eight-held/twelve-released action timing"
        )
    return target, actions


def _terminal_mismatches(
    *,
    target: Any,
    actual_snapshot_sha256: str,
    actual_screen_sha256: str,
    actual_progress: MilestoneProgress,
    actual_descriptor: Any,
    actual_referee_summary: Mapping[str, int | str | bool | None],
) -> list[str]:
    mismatches: list[str] = []
    if actual_snapshot_sha256 != target.snapshot_sha256:
        mismatches.append("snapshot_hash_mismatch")
    if actual_screen_sha256 != target.screen_sha256:
        mismatches.append("screen_hash_mismatch")
    if (
        actual_progress.key != target.descriptor.milestone_id
        or actual_progress.index != target.descriptor.milestone_index
    ):
        mismatches.append("canonical_milestone_mismatch")
    if actual_descriptor != target.descriptor:
        mismatches.append("full_descriptor_mismatch")
    if expedition_module._replay_referee_projection(  # noqa: SLF001
        actual_referee_summary
    ) != expedition_module._replay_referee_projection(target.referee_summary):  # noqa: SLF001
        mismatches.append("canonical_referee_summary_mismatch")
    return mismatches


def _array_record(path: Path, value: np.ndarray) -> dict[str, Any]:
    return {
        "filename": path.name,
        "sha256": _sha256_file(path),
        "dtype": value.dtype.str,
        "shape": list(value.shape),
        "nbytes": int(value.nbytes),
        "file_bytes": path.stat().st_size,
    }


def _dataset_identity(manifest: Mapping[str, Any]) -> str:
    arrays = manifest["arrays"]
    return _sha256_bytes(
        _canonical_json(
            {
                "protocol": manifest["protocol"],
                "observation_protocol": manifest["observation"]["protocol"],
                "target_cell_id": manifest["source"]["target_cell_id"],
                "lineage_sha256": manifest["source"]["lineage_sha256"],
                "action_sequence_sha256": manifest["action_sequence_sha256"],
                "implementation": manifest["implementation"],
                "arrays": {
                    key: arrays[key]["sha256"] for key in sorted(_ARRAY_FILENAMES)
                },
            }
        )
    )


def capture_apprentice_dataset(
    rom_path: Path,
    store_path: Path,
    target_cell_id: str,
    expected_lineage_sha256: str,
    output_path: Path,
) -> Mapping[str, Any]:
    """Replay one proven promotion into a crash-safe private Stage-0 dataset.

    The source store is opened through :meth:`ExpeditionStore.open_checkpoint_view`; this function
    never calls ``ExpeditionStore.open`` or ``audit`` and refuses a source whose raw manifest,
    index, or event prefix changes during capture.
    """

    rom_path = rom_path.expanduser().resolve()
    store_path = store_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    _require_private_output_location(output_path)
    if output_path == store_path or output_path.is_relative_to(store_path):
        raise ApprenticeDatasetError("The apprentice output cannot be inside its source store")
    if store_path.is_relative_to(output_path):
        raise ApprenticeDatasetError("The apprentice output cannot contain its source store")
    if output_path.exists():
        raise FileExistsError(f"Apprentice dataset output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    store, raw_source = _read_source_view(store_path)
    target, actions = _validate_target(store, target_cell_id, expected_lineage_sha256)
    implementation = detect_source_provenance()
    if implementation.git_commit is None or implementation.worktree_dirty is not False:
        raise ApprenticeDatasetError(
            "Official Stage-0 extraction requires one committed, clean implementation"
        )
    fingerprint = verify_rom(rom_path)
    if fingerprint.sha256 != store.manifest["rom_sha256"]:
        raise ApprenticeDatasetError("ROM identity does not match the expedition source")

    action_by_name = {name: index for index, name in enumerate(BLIND_ACTIONS)}
    action_values = np.fromiter(
        (action_by_name[action.button] for action in actions),
        dtype=np.uint8,
        count=len(actions),
    )
    previous_actions = np.empty(len(actions), dtype=np.int16)
    previous_actions[0] = PREVIOUS_ACTION_SENTINEL
    previous_actions[1:] = action_values[:-1]
    episode_starts = np.zeros(len(actions), dtype=np.bool_)
    episode_starts[0] = True

    frames = np.empty((len(actions) + 1, *APPRENTICE_FRAME_SHAPE), dtype=np.uint8)
    actual_progress = MilestoneProgress("power_on", 0, "Power-on")
    executed_actions = 0
    final_state: Any = None
    final_pixels: np.ndarray | None = None
    with PokemonRedEmulator(rom_path) as emulator:
        reader = PokemonRedStateReader(emulator)
        initial_state = reader.read()
        actual_progress = milestone_progress_for_state(initial_state)
        initial_pixels = emulator.screen_rgb()
        frames[0] = preprocess_apprentice_frame(initial_pixels)
        for index, action in enumerate(actions, start=1):
            alive = (
                emulator.tick(action.total_frames, render_last=True)
                if action.button == "noop"
                else emulator.press(
                    action.button,
                    hold_frames=action.hold_frames,
                    release_frames=action.release_frames,
                )
            )
            executed_actions += 1
            state = reader.read()
            actual_progress = milestone_progress_for_state(
                state,
                inherited=actual_progress,
            )
            pixels = emulator.screen_rgb()
            frames[index] = preprocess_apprentice_frame(pixels)
            if not alive:
                raise ApprenticeDatasetError(
                    f"Emulator stopped after {executed_actions} of {len(actions)} actions"
                )
        final_state = reader.read()
        actual_progress = milestone_progress_for_state(
            final_state,
            inherited=actual_progress,
        )
        final_pixels = emulator.screen_rgb()
        # The final decision boundary was already captured after the last action. Requiring an
        # identical second read catches a capture facade that mutates observation state.
        if not np.array_equal(frames[-1], preprocess_apprentice_frame(final_pixels)):
            raise ApprenticeDatasetError("Terminal rendered pixels changed during verification")
        actual_screen_sha256 = _sha256_bytes(final_pixels.tobytes())
        actual_snapshot_sha256 = emulator.save_state().sha256

    if executed_actions != len(actions) or final_state is None or final_pixels is None:
        raise ApprenticeDatasetError("The complete action lineage was not captured")
    actual_descriptor = descriptor_from_state(
        final_state,
        milestone_id=actual_progress.key,
        milestone_index=actual_progress.index,
        visual_key=visual_key(final_pixels),
    )
    actual_referee_summary = referee_summary_for_state(final_state, actual_progress)
    mismatches = _terminal_mismatches(
        target=target,
        actual_snapshot_sha256=actual_snapshot_sha256,
        actual_screen_sha256=actual_screen_sha256,
        actual_progress=actual_progress,
        actual_descriptor=actual_descriptor,
        actual_referee_summary=actual_referee_summary,
    )
    if mismatches:
        raise ApprenticeDatasetError(
            "Terminal exact replay verification failed: " + ", ".join(mismatches)
        )

    source_files = {
        "manifest": store_path / "manifest.json",
        "index": store_path / "index.json",
        "events": store_path / "events.jsonl",
    }
    for name, payload in raw_source.items():
        if source_files[name].read_bytes() != payload:
            raise ApprenticeDatasetError(
                "Expedition source changed during capture; no dataset was published"
            )

    lock_path = output_path.parent / f".{output_path.name}.publish.lock"
    lock_descriptor: int | None = None
    lock_owned = False
    staging = output_path.parent / f".{output_path.name}.tmp-{uuid.uuid4().hex}"
    try:
        try:
            lock_descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            lock_owned = True
        except FileExistsError as error:
            raise ApprenticeDatasetError(
                f"Another dataset publisher owns the destination lock: {lock_path}"
            ) from error
        os.write(lock_descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(lock_descriptor)
        staging.mkdir(mode=0o700)
        _write_bytes(staging / ".gitignore", b"*\n!.gitignore\n")
        arrays = {
            "frames": frames,
            "actions": action_values,
            "previous_actions": previous_actions,
            "episode_starts": episode_starts,
        }
        for key, filename in _ARRAY_FILENAMES.items():
            _write_npy(staging / filename, arrays[key])
        array_records = {
            key: _array_record(staging / filename, arrays[key])
            for key, filename in _ARRAY_FILENAMES.items()
        }
        action_sequence_sha256 = _sha256_bytes(
            _canonical_json([action.public_dict() for action in actions])
        )
        lineage = store.lineage(target_cell_id)
        lineage_ids = [cell.cell_id for cell in lineage]
        lineage_segments = [
            {
                "ordinal": ordinal,
                "cell_id": cell.cell_id,
                "segment_sha256": cell.segment_sha256,
                "segment_action_count": len(store.read_segment(cell.segment_sha256)),
                "cumulative_depth_actions": cell.depth_actions,
            }
            for ordinal, cell in enumerate(lineage)
        ]
        power_on_certificates = list(
            store.power_on_replay_certificate_ids(target_cell_id)
        )
        manifest: dict[str, Any] = {
            "schema_version": APPRENTICE_DATASET_SCHEMA,
            "protocol": APPRENTICE_DATASET_PROTOCOL,
            "created_at": datetime.now(UTC).isoformat(),
            "capture_id": uuid.uuid4().hex,
            "private_rom_derived_pixels": True,
            "implementation": implementation.public_dict(),
            "actor_inputs": ["rendered_pixels", "previous_action", "episode_boundary"],
            "actor_excluded_inputs": ["ram", "checkpoint_identity", "referee_state"],
            "action_vocabulary": list(BLIND_ACTIONS),
            "action_timing": {
                "hold_frames": ACTION_HOLD_FRAMES,
                "release_frames": ACTION_RELEASE_FRAMES,
            },
            "action_count": len(actions),
            "decision_boundary_frame_count": len(actions) + 1,
            "action_sequence_sha256": action_sequence_sha256,
            "observation": {
                "protocol": APPRENTICE_OBSERVATION_PROTOCOL,
                "source_shape": list(APPRENTICE_RGB_SHAPE),
                "frame_shape": list(APPRENTICE_FRAME_SHAPE),
                "dtype": np.dtype(np.uint8).str,
                "grayscale": "(77R+150G+29B+128)>>8",
                "pooling": "non-overlapping-2x2-integer-mean",
                "frame_pair_for_action_i": "frames[max(i-1,0)],frames[i]",
                "terminal_frame": "frames[action_count]",
            },
            "source": {
                "store_schema_version": store.schema_version,
                "store_protocol_version": store.manifest["protocol_version"],
                "store_manifest_sha256": _sha256_bytes(raw_source["manifest"]),
                "store_index_sha256": _sha256_bytes(raw_source["index"]),
                "store_events_prefix_sha256": _sha256_bytes(raw_source["events"]),
                "store_events_prefix_bytes": len(raw_source["events"]),
                "store_event_sequence": store.event_sequence,
                "store_event_head_sha256": store.event_head_sha256,
                "indexed_cell_count": len(store.cells),
                "lineage_cell_ids_sha256": _sha256_bytes(_canonical_json(lineage_ids)),
                "lineage_segments_sha256": _sha256_bytes(
                    _canonical_json(lineage_segments)
                ),
                "target_cell_id": target.cell_id,
                "lineage_sha256": target.lineage_sha256,
                "target_snapshot_sha256": target.snapshot_sha256,
                "target_screen_sha256": target.screen_sha256,
                "target_milestone_id": target.descriptor.milestone_id,
                "target_milestone_index": target.descriptor.milestone_index,
                "target_depth_actions": target.depth_actions,
                "successful_power_on_replay_count": store.successful_replay_count(
                    target_cell_id
                ),
                "power_on_replay_certificate_ids": power_on_certificates,
                "lineage_verification_deficits": [],
                "rom": fingerprint.public_dict(),
            },
            "terminal_verification": {
                "passed": True,
                "executed_action_count": executed_actions,
                "expected_snapshot_sha256": target.snapshot_sha256,
                "actual_snapshot_sha256": actual_snapshot_sha256,
                "expected_screen_sha256": target.screen_sha256,
                "actual_screen_sha256": actual_screen_sha256,
                "expected_descriptor": target.descriptor.public_dict(),
                "actual_descriptor": actual_descriptor.public_dict(),
                "expected_referee_summary": dict(target.referee_summary),
                "actual_referee_summary": actual_referee_summary,
            },
            "arrays": array_records,
        }
        manifest["dataset_sha256"] = _dataset_identity(manifest)
        manifest_payload = _canonical_json(manifest) + b"\n"
        _write_bytes(staging / "manifest.json", manifest_payload)
        success = {
            "schema_version": 1,
            "dataset_sha256": manifest["dataset_sha256"],
            "manifest_sha256": _sha256_bytes(manifest_payload),
        }
        _write_bytes(staging / "SUCCESS", _canonical_json(success) + b"\n")
        _fsync_directory(staging)
        verify_apprentice_dataset(staging)
        if output_path.exists():
            raise FileExistsError(f"Apprentice dataset output already exists: {output_path}")
        os.rename(staging, output_path)
        _fsync_directory(output_path.parent)
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if staging.exists():
            shutil.rmtree(staging)
        if lock_owned and lock_path.exists():
            lock_path.unlink()
            _fsync_directory(lock_path.parent)

    return verify_apprentice_dataset(output_path)


def _load_manifest_and_success(
    path: Path,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    if not path.is_dir() or path.is_symlink():
        raise ApprenticeDatasetError("Apprentice dataset path must be a real directory")
    actual_files = {item.name for item in path.iterdir()}
    if actual_files != _EXPECTED_FILES:
        raise ApprenticeDatasetError("Apprentice dataset file set is incomplete or unexpected")
    for name in _EXPECTED_FILES:
        item = path / name
        if item.is_symlink() or not item.is_file():
            raise ApprenticeDatasetError("Apprentice dataset payloads must be regular files")
    if (path / ".gitignore").read_bytes() != b"*\n!.gitignore\n":
        raise ApprenticeDatasetError("Apprentice private-data ignore rule is invalid")
    manifest_payload = (path / "manifest.json").read_bytes()
    success_payload = (path / "SUCCESS").read_bytes()
    manifest = _strict_json(manifest_payload, label="Apprentice manifest")
    success = _strict_json(success_payload, label="Apprentice SUCCESS marker")
    if not isinstance(manifest, dict) or not isinstance(success, dict):
        raise ApprenticeDatasetError("Apprentice manifest and SUCCESS must be objects")
    if manifest_payload != _canonical_json(manifest) + b"\n":
        raise ApprenticeDatasetError("Apprentice manifest is not canonical JSON")
    if success_payload != _canonical_json(success) + b"\n":
        raise ApprenticeDatasetError("Apprentice SUCCESS marker is not canonical JSON")
    if set(success) != {"schema_version", "dataset_sha256", "manifest_sha256"}:
        raise ApprenticeDatasetError("Apprentice SUCCESS fields are invalid")
    if success.get("schema_version") != 1:
        raise ApprenticeDatasetError("Apprentice SUCCESS schema is unsupported")
    if success.get("manifest_sha256") != _sha256_bytes(manifest_payload):
        raise ApprenticeDatasetError("Apprentice manifest hash does not match SUCCESS")
    return manifest, success, manifest_payload


def _load_arrays(path: Path, manifest: Mapping[str, Any]) -> dict[str, np.ndarray]:
    records = manifest.get("arrays")
    if not isinstance(records, dict) or set(records) != set(_ARRAY_FILENAMES):
        raise ApprenticeDatasetError("Apprentice array manifest is invalid")
    arrays: dict[str, np.ndarray] = {}
    for key, filename in _ARRAY_FILENAMES.items():
        record = records[key]
        if not isinstance(record, dict) or record.get("filename") != filename:
            raise ApprenticeDatasetError("Apprentice array filename is invalid")
        array_path = path / filename
        if record.get("sha256") != _sha256_file(array_path):
            raise ApprenticeDatasetError(f"Apprentice {key} array hash is invalid")
        if record.get("file_bytes") != array_path.stat().st_size:
            raise ApprenticeDatasetError(f"Apprentice {key} file size is invalid")
        try:
            value = np.load(array_path, mmap_mode="r", allow_pickle=False)
        except (OSError, ValueError) as error:
            raise ApprenticeDatasetError(f"Apprentice {key} array cannot be loaded") from error
        if record.get("dtype") != value.dtype.str:
            raise ApprenticeDatasetError(f"Apprentice {key} dtype is invalid")
        if record.get("shape") != list(value.shape):
            raise ApprenticeDatasetError(f"Apprentice {key} shape is invalid")
        if record.get("nbytes") != value.nbytes:
            raise ApprenticeDatasetError(f"Apprentice {key} byte count is invalid")
        arrays[key] = value
    return arrays


def verify_apprentice_dataset(path: Path) -> Mapping[str, Any]:
    """Verify every file hash, array contract, and cross-field invariant."""

    path = path.expanduser().resolve()
    manifest, success, _ = _load_manifest_and_success(path)
    if (
        manifest.get("schema_version") != APPRENTICE_DATASET_SCHEMA
        or manifest.get("protocol") != APPRENTICE_DATASET_PROTOCOL
    ):
        raise ApprenticeDatasetError("Apprentice dataset protocol is unsupported")
    capture_id = manifest.get("capture_id")
    if (
        not isinstance(capture_id, str)
        or len(capture_id) != 32
        or any(character not in "0123456789abcdef" for character in capture_id)
    ):
        raise ApprenticeDatasetError("Apprentice capture identity is invalid")
    if manifest.get("action_vocabulary") != list(BLIND_ACTIONS):
        raise ApprenticeDatasetError("Apprentice action vocabulary is not canonical")
    if manifest.get("action_timing") != {
        "hold_frames": ACTION_HOLD_FRAMES,
        "release_frames": ACTION_RELEASE_FRAMES,
    }:
        raise ApprenticeDatasetError("Apprentice action timing is not canonical")
    observation = manifest.get("observation")
    if not isinstance(observation, dict) or observation != {
        "protocol": APPRENTICE_OBSERVATION_PROTOCOL,
        "source_shape": list(APPRENTICE_RGB_SHAPE),
        "frame_shape": list(APPRENTICE_FRAME_SHAPE),
        "dtype": np.dtype(np.uint8).str,
        "grayscale": "(77R+150G+29B+128)>>8",
        "pooling": "non-overlapping-2x2-integer-mean",
        "frame_pair_for_action_i": "frames[max(i-1,0)],frames[i]",
        "terminal_frame": "frames[action_count]",
    }:
        raise ApprenticeDatasetError("Apprentice observation contract is invalid")
    source = manifest.get("source")
    terminal = manifest.get("terminal_verification")
    implementation = manifest.get("implementation")
    if (
        not isinstance(source, dict)
        or not isinstance(terminal, dict)
        or not isinstance(implementation, dict)
    ):
        raise ApprenticeDatasetError("Apprentice source or terminal evidence is invalid")
    if set(implementation) != {"git_commit", "worktree_dirty"}:
        raise ApprenticeDatasetError("Apprentice implementation provenance is invalid")
    if source.get("successful_power_on_replay_count", 0) < 3:
        raise ApprenticeDatasetError("Apprentice source lacks three power-on certificates")
    certificate_ids = source.get("power_on_replay_certificate_ids")
    if (
        not isinstance(certificate_ids, list)
        or len(certificate_ids) != source.get("successful_power_on_replay_count")
        or len(certificate_ids) != len(set(certificate_ids))
        or any(
            not isinstance(certificate_id, str)
            or _SHA256_PATTERN.fullmatch(certificate_id) is None
            for certificate_id in certificate_ids
        )
    ):
        raise ApprenticeDatasetError("Apprentice power-on certificate identities are invalid")
    if _SHA256_PATTERN.fullmatch(str(source.get("lineage_segments_sha256", ""))) is None:
        raise ApprenticeDatasetError("Apprentice lineage-segment manifest hash is invalid")
    if (
        source.get("target_cell_id") != STAGE0_Q1_TARGET_CELL_ID
        or source.get("lineage_sha256") != STAGE0_Q1_LINEAGE_SHA256
        or source.get("target_milestone_id") != STAGE0_Q1_MILESTONE_ID
        or source.get("target_depth_actions") != STAGE0_Q1_ACTION_COUNT
    ):
        raise ApprenticeDatasetError("Apprentice source is not the frozen Stage-0 Q1 target")
    if source.get("lineage_verification_deficits") != []:
        raise ApprenticeDatasetError("Apprentice source records verification deficits")
    for key in (
        "store_manifest_sha256",
        "store_index_sha256",
        "store_events_prefix_sha256",
        "store_event_head_sha256",
        "lineage_cell_ids_sha256",
        "lineage_sha256",
        "target_snapshot_sha256",
        "target_screen_sha256",
    ):
        if _SHA256_PATTERN.fullmatch(str(source.get(key, ""))) is None:
            raise ApprenticeDatasetError(f"Apprentice source {key} is invalid")
    if terminal.get("passed") is not True:
        raise ApprenticeDatasetError("Apprentice terminal replay was not exact")
    for kind in ("snapshot", "screen"):
        if terminal.get(f"expected_{kind}_sha256") != terminal.get(
            f"actual_{kind}_sha256"
        ):
            raise ApprenticeDatasetError(f"Apprentice terminal {kind} evidence disagrees")
    if terminal.get("expected_descriptor") != terminal.get("actual_descriptor"):
        raise ApprenticeDatasetError("Apprentice terminal descriptors disagree")
    if terminal.get("expected_snapshot_sha256") != source.get("target_snapshot_sha256"):
        raise ApprenticeDatasetError("Apprentice target snapshot evidence is inconsistent")
    if terminal.get("expected_screen_sha256") != source.get("target_screen_sha256"):
        raise ApprenticeDatasetError("Apprentice target screen evidence is inconsistent")
    descriptor = terminal.get("expected_descriptor")
    if not isinstance(descriptor, dict) or (
        descriptor.get("milestone_id") != source.get("target_milestone_id")
        or descriptor.get("milestone_index") != source.get("target_milestone_index")
    ):
        raise ApprenticeDatasetError("Apprentice target milestone evidence is inconsistent")
    expected_summary = terminal.get("expected_referee_summary")
    actual_summary = terminal.get("actual_referee_summary")
    if not isinstance(expected_summary, dict) or not isinstance(actual_summary, dict):
        raise ApprenticeDatasetError("Apprentice terminal referee summaries are invalid")
    if expedition_module._replay_referee_projection(  # noqa: SLF001
        expected_summary
    ) != expedition_module._replay_referee_projection(actual_summary):  # noqa: SLF001
        raise ApprenticeDatasetError("Apprentice terminal referee summaries disagree")

    arrays = _load_arrays(path, manifest)
    frames = arrays["frames"]
    actions = arrays["actions"]
    previous = arrays["previous_actions"]
    starts = arrays["episode_starts"]
    action_count = manifest.get("action_count")
    if not isinstance(action_count, int) or isinstance(action_count, bool) or action_count < 1:
        raise ApprenticeDatasetError("Apprentice action count is invalid")
    if action_count != STAGE0_Q1_ACTION_COUNT:
        raise ApprenticeDatasetError("Apprentice action count is not the frozen Stage-0 horizon")
    if frames.dtype != np.uint8 or frames.shape != (
        action_count + 1,
        *APPRENTICE_FRAME_SHAPE,
    ):
        raise ApprenticeDatasetError("Apprentice decision-boundary frames are invalid")
    if actions.dtype != np.uint8 or actions.shape != (action_count,):
        raise ApprenticeDatasetError("Apprentice target actions are invalid")
    if previous.dtype != np.int16 or previous.shape != (action_count,):
        raise ApprenticeDatasetError("Apprentice previous actions are invalid")
    if starts.dtype != np.bool_ or starts.shape != (action_count,):
        raise ApprenticeDatasetError("Apprentice episode boundaries are invalid")
    if np.any(actions >= len(BLIND_ACTIONS)):
        raise ApprenticeDatasetError("Apprentice target action index is out of range")
    if previous[0] != PREVIOUS_ACTION_SENTINEL or not np.array_equal(
        previous[1:], actions[:-1]
    ):
        raise ApprenticeDatasetError("Apprentice previous-action sequence is inconsistent")
    if not bool(starts[0]) or bool(np.any(starts[1:])):
        raise ApprenticeDatasetError("Apprentice episode-boundary sequence is inconsistent")
    if manifest.get("decision_boundary_frame_count") != action_count + 1:
        raise ApprenticeDatasetError("Apprentice frame count does not match its manifest")
    if source.get("target_depth_actions") != action_count:
        raise ApprenticeDatasetError("Apprentice target depth does not match its actions")
    if terminal.get("executed_action_count") != action_count:
        raise ApprenticeDatasetError("Apprentice terminal action count is inconsistent")
    reconstructed_actions = [
        BlindAction(
            BLIND_ACTIONS[int(action)],
            ACTION_HOLD_FRAMES,
            ACTION_RELEASE_FRAMES,
        ).public_dict()
        for action in actions
    ]
    if manifest.get("action_sequence_sha256") != _sha256_bytes(
        _canonical_json(reconstructed_actions)
    ):
        raise ApprenticeDatasetError("Apprentice action-sequence hash is inconsistent")
    if manifest.get("dataset_sha256") != _dataset_identity(manifest):
        raise ApprenticeDatasetError("Apprentice dataset identity is inconsistent")
    if success.get("dataset_sha256") != manifest["dataset_sha256"]:
        raise ApprenticeDatasetError("Apprentice dataset identity does not match SUCCESS")
    return MappingProxyType(manifest)


def load_apprentice_dataset(path: Path) -> ApprenticeDataset:
    """Load a fully verified dataset as read-only, memory-mapped arrays."""

    path = path.expanduser().resolve()
    manifest = verify_apprentice_dataset(path)
    arrays = _load_arrays(path, manifest)
    for value in arrays.values():
        value.flags.writeable = False
    return ApprenticeDataset(
        frames=arrays["frames"],
        actions=arrays["actions"],
        previous_actions=arrays["previous_actions"],
        episode_starts=arrays["episode_starts"],
        manifest=manifest,
    )
