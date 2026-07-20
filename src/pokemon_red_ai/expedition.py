from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import re
import subprocess
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

import numpy as np

from pokemon_red_ai.blind import BlindAction, FrozenSnapshot, visual_key
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.milestones import MILESTONE_BY_KEY, MILESTONES
from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader

LEGACY_EXPEDITION_PROTOCOL_VERSION = "checkpoint-expedition-v1"
EXPEDITION_PROTOCOL_VERSION = "checkpoint-expedition-v2"
EXPEDITION_STORE_SCHEMA = 2
SUPPORTED_EXPEDITION_STORE_SCHEMAS = frozenset({1, EXPEDITION_STORE_SCHEMA})
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_CELL_ID_PATTERN = re.compile(r"[0-9a-f]{24}")
_REPLAY_REFEREE_KEYS = (
    "milestone_id",
    "milestone_index",
    "milestone_label",
    "map_id",
    "badge_count",
    "required_events",
    "party_count",
    "pokedex_seen",
    "pokedex_owned",
    "got_pokedex",
    "hall_of_fame",
)
_CANONICAL_PROGRESS = {
    "power_on": (0, "Power-on"),
    **{
        milestone.key: (milestone.ordinal + 1, milestone.label)
        for milestone in MILESTONES
    },
}


@dataclass(frozen=True, slots=True)
class MilestoneProgress:
    key: str
    index: int
    label: str

    def __post_init__(self) -> None:
        expected = _CANONICAL_PROGRESS.get(self.key)
        if expected is None or expected != (self.index, self.label):
            raise ValueError("Milestone progress does not match the canonical catalog")

    def public_dict(self) -> dict[str, int | str]:
        return asdict(self)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


MILESTONE_CATALOG_SHA256 = _sha256(
    _canonical_json([asdict(milestone) for milestone in MILESTONES])
)


def _is_sha256(value: str) -> bool:
    return _SHA256_PATTERN.fullmatch(value) is not None


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _freeze_summary(
    value: Mapping[str, int | str | bool | None],
) -> Mapping[str, int | str | bool | None]:
    summary = {str(key): item for key, item in value.items()}
    if len(summary) > 64:
        raise ValueError("Frontier referee summary is unexpectedly large")
    if any(len(key) > 80 for key in summary):
        raise ValueError("Frontier referee summary key is too long")
    if any(isinstance(item, str) and len(item) > 256 for item in summary.values()):
        raise ValueError("Frontier referee summary value is too long")
    return MappingProxyType(summary)


def _replay_referee_projection(
    value: Mapping[str, int | str | bool | None],
) -> dict[str, int | str | bool | None]:
    """Select the deterministic state-derived fields that a replay can reproduce.

    Stored summaries may also contain narrative fields accumulated by the coordinator. Those are
    useful evidence, but a replay should neither fabricate nor erase them while proving the exact
    state-derived projection.
    """

    return {key: value[key] for key in _REPLAY_REFEREE_KEYS if key in value}


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _atomic_json(path: Path, value: object) -> None:
    _atomic_bytes(path, _canonical_json(value) + b"\n")


def _append_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as output:
        output.write(_canonical_json(value) + b"\n")
        output.flush()
        os.fsync(output.fileno())


def _require_private_output_location(path: Path) -> None:
    """Reject a store inside Git unless an existing repository rule ignores it."""

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
        raise ValueError(
            "Expedition stores contain private emulator states and must be outside Git "
            "or below an ignored path such as runs/"
        )


@dataclass(frozen=True, slots=True)
class FrontierDescriptor:
    """A bounded, declared niche used by the privileged training referee.

    The actor never receives this value. ``visual_class`` is deliberately small; it
    distinguishes broad screen modes without turning every animation frame into a new niche.
    """

    milestone_id: str
    milestone_index: int
    map_id: int | None
    x_bucket: int | None
    y_bucket: int | None
    battle_kind: str
    visual_class: int

    def __post_init__(self) -> None:
        if not self.milestone_id:
            raise ValueError("A frontier descriptor requires a milestone ID")
        if self.milestone_index < 0:
            raise ValueError("A frontier milestone index cannot be negative")
        if not 0 <= self.visual_class <= 0xFFFF:
            raise ValueError("A frontier visual class must fit in 16 bits")
        if self.map_id is not None and not 0 <= self.map_id <= 0xFF:
            raise ValueError("A frontier map ID must fit in one byte")
        if any(
            bucket is not None and not 0 <= bucket <= 0x3F
            for bucket in (self.x_bucket, self.y_bucket)
        ):
            raise ValueError("A frontier coordinate bucket must be between zero and 63")
        if self.battle_kind not in {
            "none",
            "wild",
            "trainer",
            "lost",
            "unknown",
            "unavailable",
        }:
            raise ValueError("A frontier battle kind is not canonical")

    @property
    def primary_key(self) -> tuple[str, int | None, int | None, int | None, str]:
        """The semantic/spatial niche, independent of transient screen appearance."""

        return (
            self.milestone_id,
            self.map_id,
            self.x_bucket,
            self.y_bucket,
            self.battle_kind,
        )

    @property
    def variant_key(self) -> tuple[str, int | None, int | None, int | None, str, int]:
        """The exact bounded visual variant within :attr:`primary_key`."""

        return (
            *self.primary_key,
            self.visual_class,
        )

    @property
    def key(self) -> tuple[str, int | None, int | None, int | None, str, int]:
        """Compatibility alias for v1 callers and checkpoints."""

        return self.variant_key

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FrontierDescriptor:
        return cls(
            milestone_id=str(value["milestone_id"]),
            milestone_index=int(value["milestone_index"]),
            map_id=None if value.get("map_id") is None else int(value["map_id"]),
            x_bucket=None if value.get("x_bucket") is None else int(value["x_bucket"]),
            y_bucket=None if value.get("y_bucket") is None else int(value["y_bucket"]),
            battle_kind=str(value["battle_kind"]),
            visual_class=int(value["visual_class"]),
        )


@dataclass(frozen=True, slots=True)
class FrontierCell:
    """Immutable evidence for one checkpoint-assisted stepping stone."""

    cell_id: str
    parent_id: str | None
    snapshot_sha256: str
    segment_sha256: str
    lineage_sha256: str
    depth_actions: int
    descriptor: FrontierDescriptor
    screen_sha256: str
    discovered_global_action: int
    policy_id: str | None
    referee_summary: Mapping[str, int | str | bool | None]

    def __post_init__(self) -> None:
        object.__setattr__(self, "referee_summary", _freeze_summary(self.referee_summary))
        if self.policy_id is not None and len(self.policy_id) > 256:
            raise ValueError("Frontier policy ID is too long")

    @property
    def quality(self) -> tuple[int, int, int, int, int]:
        summary = self.referee_summary
        return (
            self.descriptor.milestone_index,
            int(summary.get("badge_count", 0) or 0),
            int(summary.get("required_events", 0) or 0),
            int(summary.get("pokedex_owned", 0) or 0),
            -self.depth_actions,
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "parent_id": self.parent_id,
            "snapshot_sha256": self.snapshot_sha256,
            "segment_sha256": self.segment_sha256,
            "lineage_sha256": self.lineage_sha256,
            "depth_actions": self.depth_actions,
            "descriptor": self.descriptor.public_dict(),
            "screen_sha256": self.screen_sha256,
            "discovered_global_action": self.discovered_global_action,
            "policy_id": self.policy_id,
            "referee_summary": dict(self.referee_summary),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FrontierCell:
        summary = value.get("referee_summary", {})
        if not isinstance(summary, dict):
            raise ValueError("Frontier referee summary must be an object")
        return cls(
            cell_id=str(value["cell_id"]),
            parent_id=None if value.get("parent_id") is None else str(value["parent_id"]),
            snapshot_sha256=str(value["snapshot_sha256"]),
            segment_sha256=str(value["segment_sha256"]),
            lineage_sha256=str(value["lineage_sha256"]),
            depth_actions=int(value["depth_actions"]),
            descriptor=FrontierDescriptor.from_dict(value["descriptor"]),
            screen_sha256=str(value["screen_sha256"]),
            discovered_global_action=int(value["discovered_global_action"]),
            policy_id=None if value.get("policy_id") is None else str(value["policy_id"]),
            referee_summary={str(key): item for key, item in summary.items()},
        )


def _cell_identity(cell: FrontierCell) -> dict[str, Any]:
    value = cell.public_dict()
    value.pop("cell_id")
    return value


def _cell_id(cell: FrontierCell) -> str:
    return _sha256(_canonical_json(_cell_identity(cell)))[:24]


@dataclass(frozen=True, slots=True)
class ArchiveDecision:
    admitted: bool
    reason: str
    replaced_cell_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReplayResult:
    cell_id: str
    passed: bool
    action_count: int
    executed_action_count: int
    expected_snapshot_sha256: str
    actual_snapshot_sha256: str
    expected_screen_sha256: str
    actual_screen_sha256: str
    final_state: dict[str, object]
    expected_milestone_id: str
    expected_milestone_index: int
    actual_milestone_id: str
    actual_milestone_index: int
    expected_descriptor: dict[str, Any]
    actual_descriptor: dict[str, Any]
    expected_referee_summary: dict[str, int | str | bool | None]
    actual_referee_summary: dict[str, int | str | bool | None]
    mismatch_reasons: tuple[str, ...] = ()
    failure_reason: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExpeditionStore:
    """Crash-safe, content-addressed private state and complete action lineages.

    Cells and audit events are append-only. Archive eviction only removes a cell from the
    active selection set; it never erases the evidence that the attempted idea existed.
    """

    def __init__(
        self,
        path: Path,
        manifest: Mapping[str, Any],
        cells: Iterable[FrontierCell],
        *,
        event_payload: bytes | None = None,
    ) -> None:
        self.path = path
        self.manifest = MappingProxyType(dict(manifest))
        self.schema_version = int(self.manifest.get("schema_version", -1))
        cell_list = list(cells)
        self.cells = {cell.cell_id: cell for cell in cell_list}
        if len(self.cells) != len(cell_list):
            raise ValueError("Expedition store contains duplicate cell IDs")
        self._event_sequence = 0
        self._last_event_sha256 = "0" * 64
        self._successful_replay_counts: dict[str, int] = {}
        self._power_on_replay_certificate_ids: dict[str, list[str]] = {}
        self._successful_edge_replay_counts: dict[str, int] = {}
        self._edge_replay_certificate_ids: dict[str, list[str]] = {}
        self._event_log_recovery: dict[str, Any] | None = None
        self._load_event_chain(event_payload)
        self._validate_graph()
        if self._event_log_recovery is not None:
            self.audit("audit_log_tail_recovered", **self._event_log_recovery)

    @property
    def event_sequence(self) -> int:
        """Return the number of durable events in the validated audit chain."""

        return self._event_sequence

    @property
    def event_head_sha256(self) -> str:
        """Return the immutable ID of the current durable audit-chain head."""

        return self._last_event_sha256

    def _load_event_chain(self, event_payload: bytes | None = None) -> None:
        path = self.path / "events.jsonl"
        if not path.is_file():
            raise ValueError("Expedition store is missing its audit event log")
        payload = path.read_bytes() if event_payload is None else event_payload
        lines = payload.splitlines(keepends=True)
        valid_bytes = 0
        repair_missing_newline = False
        torn_tail: bytes | None = None
        for line_number, raw_line in enumerate(lines, start=1):
            terminated = raw_line.endswith((b"\n", b"\r"))
            encoded_event = raw_line.rstrip(b"\r\n") if terminated else raw_line
            try:
                event = json.loads(encoded_event)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                if line_number == len(lines) and not terminated:
                    torn_tail = raw_line
                    break
                raise ValueError("Expedition audit event JSON is invalid") from error
            if not isinstance(event, dict):
                raise ValueError("Expedition audit event must be an object")
            event_hash = str(event.pop("event_sha256", ""))
            expected_sequence = self._event_sequence + 1
            if int(event.get("event_sequence", -1)) != expected_sequence:
                raise ValueError("Expedition audit sequence is invalid")
            if event.get("previous_event_sha256") != self._last_event_sha256:
                raise ValueError("Expedition audit hash chain is broken")
            expected_hash = _sha256(_canonical_json(event))
            if event_hash != expected_hash:
                raise ValueError("Expedition audit event hash is invalid")
            replay_evidence = self._successful_replay_evidence(event)
            if replay_evidence is not None:
                self._record_replay_evidence(*replay_evidence, event_hash)
            self._event_sequence = expected_sequence
            self._last_event_sha256 = event_hash
            valid_bytes += len(raw_line)
            repair_missing_newline = not terminated

        if torn_tail is not None:
            if event_payload is not None:
                raise ValueError("Expedition event view has an incomplete final event")
            tail_sha256 = _sha256(torn_tail)
            recovery_directory = self.path / "recovery"
            recovery_directory.mkdir(exist_ok=True)
            recovery_name = f"torn-audit-tail-{tail_sha256}.bin"
            recovery_path = recovery_directory / recovery_name
            if not recovery_path.exists():
                _atomic_bytes(recovery_path, torn_tail)
            _atomic_bytes(path, payload[:valid_bytes])
            self._event_log_recovery = {
                "recovery_kind": "discarded_incomplete_final_event",
                "discarded_bytes": len(torn_tail),
                "discarded_sha256": tail_sha256,
                "private_recovery_file": recovery_name,
            }
        elif repair_missing_newline:
            if event_payload is not None:
                raise ValueError("Expedition event view lacks its final newline")
            _atomic_bytes(path, payload + b"\n")
            self._event_log_recovery = {
                "recovery_kind": "restored_missing_final_newline",
                "discarded_bytes": 0,
                "discarded_sha256": None,
                "private_recovery_file": None,
            }

    def _successful_replay_evidence(
        self,
        event: Mapping[str, Any],
    ) -> tuple[str, str] | None:
        """Validate and classify a replay event for the rebuildable in-memory index."""

        kind = str(event.get("kind", ""))
        if kind not in {"power_on_replay", "edge_replay"}:
            return None
        if kind == "edge_replay" and self.schema_version != EXPEDITION_STORE_SCHEMA:
            raise ValueError("Legacy expedition stores cannot contain v2 edge certificates")
        cell_id = event.get("cell_id")
        if not isinstance(cell_id, str) or cell_id not in self.cells:
            raise ValueError("Expedition replay event references an unknown cell")
        mismatch_reasons = event.get("mismatch_reasons", [])
        if not isinstance(mismatch_reasons, (list, tuple)):
            raise ValueError("Expedition replay event mismatch reasons must be a sequence")
        if event.get("passed") is not True or mismatch_reasons:
            return None
        cell = self.cells[cell_id]
        try:
            expected_index = int(event.get("expected_milestone_index", -1))
            actual_index = int(event.get("actual_milestone_index", -1))
        except (TypeError, ValueError) as error:
            raise ValueError("Expedition successful replay milestone index is invalid") from error
        if (
            event.get("expected_milestone_id") != cell.descriptor.milestone_id
            or expected_index != cell.descriptor.milestone_index
            or event.get("actual_milestone_id") != cell.descriptor.milestone_id
            or actual_index != cell.descriptor.milestone_index
        ):
            return None

        if (
            event.get("expected_snapshot_sha256") != cell.snapshot_sha256
            or event.get("actual_snapshot_sha256") != cell.snapshot_sha256
            or event.get("expected_screen_sha256") != cell.screen_sha256
            or event.get("actual_screen_sha256") != cell.screen_sha256
            or event.get("expected_descriptor") != cell.descriptor.public_dict()
            or event.get("actual_descriptor") != cell.descriptor.public_dict()
            or event.get("failure_reason") is not None
        ):
            return None
        expected_summary = event.get("expected_referee_summary")
        actual_summary = event.get("actual_referee_summary")
        expected_projection = _replay_referee_projection(cell.referee_summary)
        if (
            expected_summary != dict(cell.referee_summary)
            or not isinstance(actual_summary, dict)
            or actual_summary != expected_projection
        ):
            return None

        expected_action_count = cell.depth_actions
        if kind == "edge_replay":
            if cell.parent_id is None:
                raise ValueError("An edge replay cannot target the expedition root")
            parent = self.cells[cell.parent_id]
            expected_action_count = cell.depth_actions - parent.depth_actions
            if (
                event.get("parent_id") != parent.cell_id
                or event.get("expected_parent_snapshot_sha256")
                != parent.snapshot_sha256
                or event.get("expected_segment_sha256") != cell.segment_sha256
            ):
                return None

        action_count = event.get("action_count")
        if not isinstance(action_count, int) or isinstance(action_count, bool):
            raise ValueError("Expedition replay action count is invalid")
        if action_count != expected_action_count:
            return None
        executed_action_count = event.get("executed_action_count")
        if executed_action_count is None and self.schema_version == 1:
            # ReplayResult v1 did not expose this field. A successful mismatch-free v1 event
            # represented the complete planned lineage by definition.
            executed_action_count = action_count
        if not isinstance(executed_action_count, int) or isinstance(
            executed_action_count, bool
        ):
            raise ValueError("Expedition replay executed action count is invalid")
        if executed_action_count != action_count:
            return None
        return kind, cell_id

    def _record_replay_evidence(
        self,
        kind: str,
        cell_id: str,
        certificate_id: str,
    ) -> None:
        if kind == "power_on_replay":
            self._successful_replay_counts[cell_id] = (
                self._successful_replay_counts.get(cell_id, 0) + 1
            )
            self._power_on_replay_certificate_ids.setdefault(cell_id, []).append(
                certificate_id
            )
            return
        self._successful_edge_replay_counts[cell_id] = (
            self._successful_edge_replay_counts.get(cell_id, 0) + 1
        )
        self._edge_replay_certificate_ids.setdefault(cell_id, []).append(certificate_id)

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        rom_sha256: str,
        pyboy_version: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> ExpeditionStore:
        path = path.expanduser().resolve()
        _require_private_output_location(path)
        if not _is_sha256(rom_sha256) or not pyboy_version:
            raise ValueError("Expedition store requires valid ROM and PyBoy identities")
        path.mkdir(parents=True, exist_ok=False)
        (path / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
        for name in ("snapshots", "segments", "cells"):
            (path / name).mkdir()
        manifest: dict[str, Any] = {
            "schema_version": EXPEDITION_STORE_SCHEMA,
            "protocol_version": EXPEDITION_PROTOCOL_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "rom_sha256": rom_sha256,
            "pyboy_version": pyboy_version,
            "milestone_catalog_sha256": MILESTONE_CATALOG_SHA256,
            "private_payloads": True,
            "actor_receives_snapshots": False,
            "writer_model": "single_process_coordinator",
            "metadata": dict(metadata or {}),
        }
        _atomic_json(path / "manifest.json", manifest)
        _atomic_json(path / "index.json", {"schema_version": 1, "cell_ids": []})
        (path / "events.jsonl").touch()
        return cls(path, manifest, [])

    @classmethod
    def open(cls, path: Path) -> ExpeditionStore:
        path = path.expanduser().resolve()
        _require_private_output_location(path)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if int(manifest.get("schema_version", -1)) not in (
            SUPPORTED_EXPEDITION_STORE_SCHEMAS
        ):
            raise ValueError("Unsupported expedition store schema")
        schema_version = int(manifest.get("schema_version", -1))
        expected_protocol = (
            LEGACY_EXPEDITION_PROTOCOL_VERSION
            if schema_version == 1
            else EXPEDITION_PROTOCOL_VERSION
        )
        if manifest.get("protocol_version") != expected_protocol:
            raise ValueError("Expedition store uses a different protocol")
        if not _is_sha256(str(manifest.get("rom_sha256", ""))):
            raise ValueError("Expedition manifest ROM hash is invalid")
        if not str(manifest.get("pyboy_version", "")):
            raise ValueError("Expedition manifest PyBoy version is missing")
        if manifest.get("milestone_catalog_sha256") != MILESTONE_CATALOG_SHA256:
            raise ValueError("Expedition store uses different milestone semantics")
        index = json.loads((path / "index.json").read_text(encoding="utf-8"))
        indexed_ids = [str(cell_id) for cell_id in index.get("cell_ids", [])]
        if len(indexed_ids) != len(set(indexed_ids)):
            raise ValueError("Expedition index contains duplicate cell IDs")
        cell_files = {item.stem: item for item in (path / "cells").glob("*.json")}
        missing = set(indexed_ids) - cell_files.keys()
        if missing:
            raise ValueError("Expedition index references a missing cell file")
        recovered_ids = sorted(cell_files.keys() - set(indexed_ids))
        ordered_ids = [*indexed_ids, *recovered_ids]
        cells = []
        for cell_id in ordered_ids:
            cell = FrontierCell.from_dict(
                json.loads(cell_files[cell_id].read_text(encoding="utf-8"))
            )
            if cell.cell_id != cell_id:
                raise ValueError("Expedition cell filename does not match its identity")
            cells.append(cell)
        store = cls(path, manifest, cells)
        if recovered_ids:
            _atomic_json(
                path / "index.json",
                {"schema_version": 1, "cell_ids": ordered_ids},
            )
            store.audit("orphan_cells_recovered", cell_ids=recovered_ids)
        return store

    @classmethod
    def open_checkpoint_view(
        cls,
        path: Path,
        *,
        event_payload: bytes,
        cell_ids: Iterable[str],
    ) -> ExpeditionStore:
        """Validate a checkpoint prefix without repairing or rewriting the live store."""

        path = path.expanduser().resolve()
        _require_private_output_location(path)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if int(manifest.get("schema_version", -1)) not in (
            SUPPORTED_EXPEDITION_STORE_SCHEMAS
        ):
            raise ValueError("Unsupported expedition store schema")
        schema_version = int(manifest.get("schema_version", -1))
        expected_protocol = (
            LEGACY_EXPEDITION_PROTOCOL_VERSION
            if schema_version == 1
            else EXPEDITION_PROTOCOL_VERSION
        )
        if manifest.get("protocol_version") != expected_protocol:
            raise ValueError("Expedition store uses a different protocol")
        if not _is_sha256(str(manifest.get("rom_sha256", ""))):
            raise ValueError("Expedition manifest ROM hash is invalid")
        if not str(manifest.get("pyboy_version", "")):
            raise ValueError("Expedition manifest PyBoy version is missing")
        if manifest.get("milestone_catalog_sha256") != MILESTONE_CATALOG_SHA256:
            raise ValueError("Expedition store uses different milestone semantics")
        ordered_ids = [str(cell_id) for cell_id in cell_ids]
        if len(ordered_ids) != len(set(ordered_ids)):
            raise ValueError("Expedition checkpoint view contains duplicate cell IDs")
        cells: list[FrontierCell] = []
        for cell_id in ordered_ids:
            cell_path = path / "cells" / f"{cell_id}.json"
            if not cell_path.is_file():
                raise ValueError("Expedition checkpoint view references a missing cell file")
            cell = FrontierCell.from_dict(json.loads(cell_path.read_text(encoding="utf-8")))
            if cell.cell_id != cell_id:
                raise ValueError("Expedition cell filename does not match its identity")
            cells.append(cell)
        return cls(path, manifest, cells, event_payload=event_payload)

    def _validate_graph(self) -> None:
        if not self.cells:
            return
        roots = [cell for cell in self.cells.values() if cell.parent_id is None]
        if len(roots) != 1:
            raise ValueError("Expedition store must contain exactly one root")
        for cell in self.cells.values():
            if _CELL_ID_PATTERN.fullmatch(cell.cell_id) is None:
                raise ValueError("Expedition cell ID is malformed")
            for name, value in (
                ("snapshot", cell.snapshot_sha256),
                ("segment", cell.segment_sha256),
                ("lineage", cell.lineage_sha256),
                ("screen", cell.screen_sha256),
            ):
                if not _is_sha256(value):
                    raise ValueError(f"Expedition {name} hash is malformed")
            self._validate_descriptor(cell.descriptor)
            self._validate_referee_summary(cell)
            if cell.cell_id != _cell_id(cell):
                raise ValueError("Expedition cell ID does not bind its complete metadata")

        ordered_cells = self._topological_cells()
        logical_frames: dict[str, int] = {}
        for cell in ordered_cells:
            segment = self.read_segment(cell.segment_sha256)
            snapshot = self.read_snapshot(cell.snapshot_sha256)
            if cell.parent_id is None:
                if cell.depth_actions != 0 or segment or cell.discovered_global_action != 0:
                    raise ValueError("Expedition root has invalid action metadata")
                if snapshot.logical_frame != 0:
                    raise ValueError("Expedition root is not an exact power-on snapshot")
                if (
                    cell.descriptor.milestone_id != "power_on"
                    or cell.descriptor.milestone_index != 0
                ):
                    raise ValueError("Expedition root requires the canonical power-on descriptor")
                expected_lineage = _sha256(
                    _canonical_json(
                        {
                            "protocol": self.manifest["protocol_version"],
                            "root_snapshot_sha256": snapshot.sha256,
                        }
                    )
                )
            else:
                parent = self.cells[cell.parent_id]
                if not segment:
                    raise ValueError("A non-root expedition cell has an empty action segment")
                if cell.depth_actions != parent.depth_actions + len(segment):
                    raise ValueError("Expedition cell action depth does not match its parent")
                expected_frame = logical_frames[parent.cell_id] + sum(
                    action.total_frames for action in segment
                )
                if snapshot.logical_frame != expected_frame:
                    raise ValueError("Expedition snapshot frame does not match its action segment")
                expected_lineage = _sha256(
                    _canonical_json(
                        {
                            "parent_lineage_sha256": parent.lineage_sha256,
                            "segment_sha256": cell.segment_sha256,
                            "snapshot_sha256": snapshot.sha256,
                        }
                    )
                )
            if cell.lineage_sha256 != expected_lineage:
                raise ValueError("Expedition lineage hash is invalid")
            summary_id = cell.referee_summary.get("milestone_id")
            summary_index = cell.referee_summary.get("milestone_index")
            if summary_id is not None and summary_id != cell.descriptor.milestone_id:
                raise ValueError("Frontier summary milestone ID disagrees with its descriptor")
            if summary_index is not None and summary_index != cell.descriptor.milestone_index:
                raise ValueError("Frontier summary milestone index disagrees with its descriptor")
            if bool(cell.referee_summary.get("hall_of_fame", False)) != (
                cell.descriptor.milestone_id == "hall_of_fame"
            ) and "hall_of_fame" in cell.referee_summary:
                raise ValueError("Frontier Hall-of-Fame summary disagrees with its descriptor")
            logical_frames[cell.cell_id] = snapshot.logical_frame

    def _topological_cells(self) -> tuple[FrontierCell, ...]:
        """Return parents before children with one iterative cycle-detection pass."""

        visitation: dict[str, int] = {}
        ordered: list[FrontierCell] = []
        for starting_id in self.cells:
            if visitation.get(starting_id) == 2:
                continue
            stack = [(starting_id, False)]
            while stack:
                cell_id, expanded = stack.pop()
                state = visitation.get(cell_id, 0)
                if expanded:
                    if state == 1:
                        visitation[cell_id] = 2
                        ordered.append(self.cells[cell_id])
                    continue
                if state == 2:
                    continue
                if state == 1:
                    raise ValueError("Expedition lineage contains a cycle")
                visitation[cell_id] = 1
                stack.append((cell_id, True))
                parent_id = self.cells[cell_id].parent_id
                if parent_id is None:
                    continue
                if parent_id not in self.cells:
                    raise ValueError("Expedition cell references a missing parent")
                parent_state = visitation.get(parent_id, 0)
                if parent_state == 1:
                    raise ValueError("Expedition lineage contains a cycle")
                if parent_state != 2:
                    stack.append((parent_id, False))
        return tuple(ordered)

    @staticmethod
    def _validate_descriptor(descriptor: FrontierDescriptor) -> None:
        expected = _CANONICAL_PROGRESS.get(descriptor.milestone_id)
        if expected is None or descriptor.milestone_index != expected[0]:
            raise ValueError("Frontier descriptor is not in the canonical milestone catalog")

    @staticmethod
    def _validate_referee_summary(cell: FrontierCell) -> None:
        summary = cell.referee_summary
        if summary.get("milestone_id", cell.descriptor.milestone_id) != (
            cell.descriptor.milestone_id
        ):
            raise ValueError("Frontier summary milestone ID disagrees with its descriptor")
        if int(summary.get("milestone_index", cell.descriptor.milestone_index)) != (
            cell.descriptor.milestone_index
        ):
            raise ValueError("Frontier summary milestone index disagrees with its descriptor")
        if "map_id" in summary and summary["map_id"] != cell.descriptor.map_id:
            raise ValueError("Frontier summary map disagrees with its descriptor")
        if "battle_kind" in summary and summary["battle_kind"] != cell.descriptor.battle_kind:
            raise ValueError("Frontier summary battle kind disagrees with its descriptor")
        for key in ("badge_count", "required_events", "pokedex_owned"):
            if int(summary.get(key, 0) or 0) < 0:
                raise ValueError("Frontier quality fields cannot be negative")

    def _snapshot_path(self, sha256: str) -> Path:
        return self.path / "snapshots" / f"{sha256}.json.gz"

    def _segment_path(self, sha256: str) -> Path:
        return self.path / "segments" / f"{sha256}.json"

    def _write_snapshot(self, snapshot: FrozenSnapshot) -> None:
        if snapshot.rom_sha256 != self.manifest["rom_sha256"]:
            raise ValueError("Frontier snapshot belongs to a different ROM")
        if snapshot.pyboy_version != self.manifest["pyboy_version"]:
            raise ValueError("Frontier snapshot uses a different PyBoy version")
        if _sha256(snapshot.thaw().payload) != snapshot.sha256:
            raise ValueError("Frontier snapshot payload hash is invalid")
        path = self._snapshot_path(snapshot.sha256)
        if path.exists():
            existing = self.read_snapshot(snapshot.sha256)
            if existing != snapshot:
                raise ValueError("Existing frontier snapshot metadata does not match")
            return
        temporary = path.with_suffix(path.suffix + ".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=3) as output:
            json.dump(snapshot.checkpoint_dict(), output, sort_keys=True, separators=(",", ":"))
        with temporary.open("rb") as source:
            os.fsync(source.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)

    def read_snapshot(self, sha256: str) -> FrozenSnapshot:
        with gzip.open(self._snapshot_path(sha256), "rt", encoding="utf-8") as source:
            snapshot = FrozenSnapshot.from_checkpoint_dict(json.load(source))
        if snapshot.sha256 != sha256 or _sha256(snapshot.thaw().payload) != sha256:
            raise ValueError("Stored frontier snapshot failed its integrity check")
        if snapshot.rom_sha256 != self.manifest["rom_sha256"]:
            raise ValueError("Stored frontier snapshot belongs to a different ROM")
        if snapshot.pyboy_version != self.manifest["pyboy_version"]:
            raise ValueError("Stored frontier snapshot uses a different PyBoy version")
        return snapshot

    def _write_segment(self, actions: tuple[BlindAction, ...]) -> str:
        payload = [action.public_dict() for action in actions]
        encoded = _canonical_json(payload)
        sha256 = _sha256(encoded)
        path = self._segment_path(sha256)
        if not path.exists():
            _atomic_bytes(path, encoded + b"\n")
        return sha256

    def read_segment(self, sha256: str) -> tuple[BlindAction, ...]:
        path = self._segment_path(sha256)
        payload = path.read_bytes()
        if payload.endswith(b"\n"):
            payload = payload[:-1]
        if _sha256(payload) != sha256:
            raise ValueError("Stored action segment failed its integrity check")
        values = json.loads(payload)
        return tuple(
            BlindAction(
                button=str(value["button"]),
                hold_frames=int(value["hold_frames"]),
                release_frames=int(value["release_frames"]),
            )
            for value in values
        )

    def _commit_cell(self, cell: FrontierCell) -> FrontierCell:
        self._validate_descriptor(cell.descriptor)
        self._validate_referee_summary(cell)
        if cell.cell_id != _cell_id(cell):
            raise ValueError("Frontier cell ID does not bind its complete metadata")
        for value in (
            cell.snapshot_sha256,
            cell.segment_sha256,
            cell.lineage_sha256,
            cell.screen_sha256,
        ):
            if not _is_sha256(value):
                raise ValueError("Frontier cell contains a malformed content hash")
        if cell.cell_id in self.cells:
            existing = self.cells[cell.cell_id]
            if existing != cell:
                raise ValueError("Frontier cell ID collision or metadata mismatch")
            self.audit(
                "frontier_cell_rediscovered",
                cell_id=cell.cell_id,
                discovered_global_action=cell.discovered_global_action,
                policy_id=cell.policy_id,
            )
            return existing
        _atomic_json(self.path / "cells" / f"{cell.cell_id}.json", cell.public_dict())
        self.audit("frontier_cell_added", **cell.public_dict())
        self.cells[cell.cell_id] = cell
        _atomic_json(
            self.path / "index.json",
            {"schema_version": 1, "cell_ids": list(self.cells)},
        )
        return cell

    def add_root(
        self,
        *,
        snapshot: FrozenSnapshot,
        descriptor: FrontierDescriptor,
        screen_sha256: str,
        referee_summary: Mapping[str, int | str | bool | None],
    ) -> FrontierCell:
        if self.cells:
            raise ValueError("An expedition store can contain only one root")
        self._validate_descriptor(descriptor)
        if (
            descriptor.milestone_id != "power_on"
            or descriptor.map_id is not None
            or descriptor.x_bucket is not None
            or descriptor.y_bucket is not None
            or descriptor.battle_kind != "unavailable"
            or snapshot.logical_frame != 0
        ):
            raise ValueError("Expedition root must be the exact canonical power-on state")
        self._write_snapshot(snapshot)
        segment_sha256 = self._write_segment(())
        lineage_sha256 = _sha256(
            _canonical_json(
                {
                    "protocol": self.manifest["protocol_version"],
                    "root_snapshot_sha256": snapshot.sha256,
                }
            )
        )
        provisional = FrontierCell(
            cell_id="0" * 24,
            parent_id=None,
            snapshot_sha256=snapshot.sha256,
            segment_sha256=segment_sha256,
            lineage_sha256=lineage_sha256,
            depth_actions=0,
            descriptor=descriptor,
            screen_sha256=screen_sha256,
            discovered_global_action=0,
            policy_id=None,
            referee_summary=dict(referee_summary),
        )
        cell = replace(provisional, cell_id=_cell_id(provisional))
        return self._commit_cell(cell)

    def add_cell(
        self,
        *,
        parent_id: str,
        snapshot: FrozenSnapshot,
        actions_from_parent: tuple[BlindAction, ...],
        descriptor: FrontierDescriptor,
        screen_sha256: str,
        discovered_global_action: int,
        referee_summary: Mapping[str, int | str | bool | None],
        policy_id: str | None = None,
    ) -> FrontierCell:
        if parent_id not in self.cells:
            raise ValueError("Frontier parent does not exist")
        if not actions_from_parent:
            raise ValueError("A non-root frontier cell requires an action segment")
        if discovered_global_action < 1:
            raise ValueError("A non-root discovery action must be positive")
        self._validate_descriptor(descriptor)
        parent = self.cells[parent_id]
        parent_snapshot = self.read_snapshot(parent.snapshot_sha256)
        expected_frame = parent_snapshot.logical_frame + sum(
            action.total_frames for action in actions_from_parent
        )
        if snapshot.logical_frame != expected_frame:
            raise ValueError("Frontier snapshot frame does not match its action segment")
        self._write_snapshot(snapshot)
        segment_sha256 = self._write_segment(actions_from_parent)
        lineage_sha256 = _sha256(
            _canonical_json(
                {
                    "parent_lineage_sha256": parent.lineage_sha256,
                    "segment_sha256": segment_sha256,
                    "snapshot_sha256": snapshot.sha256,
                }
            )
        )
        provisional = FrontierCell(
            cell_id="0" * 24,
            parent_id=parent_id,
            snapshot_sha256=snapshot.sha256,
            segment_sha256=segment_sha256,
            lineage_sha256=lineage_sha256,
            depth_actions=parent.depth_actions + len(actions_from_parent),
            descriptor=descriptor,
            screen_sha256=screen_sha256,
            discovered_global_action=discovered_global_action,
            policy_id=policy_id,
            referee_summary=dict(referee_summary),
        )
        cell = replace(provisional, cell_id=_cell_id(provisional))
        return self._commit_cell(cell)

    def lineage(self, cell_id: str) -> tuple[FrontierCell, ...]:
        if cell_id not in self.cells:
            raise ValueError("Unknown frontier cell")
        reversed_lineage: list[FrontierCell] = []
        seen: set[str] = set()
        current = self.cells[cell_id]
        while True:
            if current.cell_id in seen:
                raise ValueError("Expedition lineage contains a cycle")
            seen.add(current.cell_id)
            reversed_lineage.append(current)
            if current.parent_id is None:
                break
            current = self.cells[current.parent_id]
        return tuple(reversed(reversed_lineage))

    def iter_lineage_actions(self, cell_id: str) -> Iterator[BlindAction]:
        """Yield a lineage one stored segment at a time without joining all actions."""

        lineage = self.lineage(cell_id)
        expected_actions = self.cells[cell_id].depth_actions

        def iterate() -> Iterator[BlindAction]:
            yielded_actions = 0
            for cell in lineage:
                for action in self.read_segment(cell.segment_sha256):
                    yielded_actions += 1
                    yield action
            if yielded_actions != expected_actions:
                raise ValueError("Frontier lineage depth does not match its action segments")

        return iterate()

    def lineage_actions(self, cell_id: str) -> tuple[BlindAction, ...]:
        return tuple(self.iter_lineage_actions(cell_id))

    def successful_replay_count(self, cell_id: str) -> int:
        if cell_id not in self.cells:
            raise ValueError("Unknown frontier cell")
        return self._successful_replay_counts.get(cell_id, 0)

    def power_on_replay_certificate_ids(self, cell_id: str) -> tuple[str, ...]:
        """Return event-chain hashes for successful complete power-on replays."""

        if cell_id not in self.cells:
            raise ValueError("Unknown frontier cell")
        return tuple(self._power_on_replay_certificate_ids.get(cell_id, ()))

    def successful_edge_replay_count(self, cell_id: str) -> int:
        if cell_id not in self.cells:
            raise ValueError("Unknown frontier cell")
        return self._successful_edge_replay_counts.get(cell_id, 0)

    def edge_replay_certificate_ids(self, cell_id: str) -> tuple[str, ...]:
        """Return event-chain hashes for successful exact-parent edge replays."""

        if cell_id not in self.cells:
            raise ValueError("Unknown frontier cell")
        return tuple(self._edge_replay_certificate_ids.get(cell_id, ()))

    def required_replay_count(self, cell_id: str) -> int:
        """Return the number of full power-on claims required for this boundary."""

        if cell_id not in self.cells:
            raise ValueError("Unknown frontier cell")
        cell = self.cells[cell_id]
        if cell.parent_id is None:
            return 0
        parent = self.cells[cell.parent_id]
        if cell.descriptor.milestone_index > parent.descriptor.milestone_index:
            return 3
        # V1 used one complete power-on replay for every ordinary cell. Preserve that historical
        # reporting rule without converting the evidence into a v2 edge certificate.
        return 1 if self.schema_version == 1 else 0

    def required_edge_replay_count(self, cell_id: str) -> int:
        if cell_id not in self.cells:
            raise ValueError("Unknown frontier cell")
        if self.schema_version == 1 or self.cells[cell_id].parent_id is None:
            return 0
        return 1

    def _effective_edge_replay_count(self, cell_id: str) -> int:
        return self.successful_edge_replay_count(cell_id)

    def verification_deficits(
        self,
        cell_id: str,
    ) -> tuple[tuple[str, str, int, int], ...]:
        """Return typed, lineage-wide verification deficits in causal order."""

        deficits: list[tuple[str, str, int, int]] = []
        for lineage_cell in self.lineage(cell_id):
            boundary_id = lineage_cell.cell_id
            edge_required = self.required_edge_replay_count(boundary_id)
            edge_completed = self._effective_edge_replay_count(boundary_id)
            if edge_completed < edge_required:
                deficits.append((boundary_id, "edge", edge_completed, edge_required))
            full_required = self.required_replay_count(boundary_id)
            full_completed = self.successful_replay_count(boundary_id)
            if full_completed < full_required:
                deficits.append((boundary_id, "power_on", full_completed, full_required))
        return tuple(deficits)

    def replay_deficits(self, cell_id: str) -> tuple[tuple[str, int, int], ...]:
        """Return every unverified lineage boundary from power-on through ``cell_id``.

        A terminal replay cannot silently stand in for an unchecked intermediate snapshot: the
        terminal verifier checks only the target hashes. Requiring each non-root boundary to pass
        its own gate prevents a same-stage descendant from laundering an unverified milestone
        advance into the active archive.
        """

        deficits: list[tuple[str, int, int]] = []
        for lineage_cell in self.lineage(cell_id):
            boundary_id = lineage_cell.cell_id
            edge_required = self.required_edge_replay_count(boundary_id)
            edge_completed = min(
                self._effective_edge_replay_count(boundary_id), edge_required
            )
            full_required = self.required_replay_count(boundary_id)
            full_completed = min(self.successful_replay_count(boundary_id), full_required)
            required = edge_required + full_required
            completed = edge_completed + full_completed
            if completed < required:
                deficits.append((boundary_id, completed, required))
        return tuple(deficits)

    def audit(self, kind: str, **payload: Any) -> None:
        reserved = {
            "kind",
            "recorded_at",
            "event_sequence",
            "previous_event_sha256",
            "event_sha256",
        } & payload.keys()
        if reserved:
            raise ValueError("Expedition audit payload cannot override envelope fields")
        event = {
            "kind": kind,
            "recorded_at": datetime.now(UTC).isoformat(),
            "event_sequence": self._event_sequence + 1,
            "previous_event_sha256": self._last_event_sha256,
            **payload,
        }
        event_hash = _sha256(_canonical_json(event))
        replay_evidence = self._successful_replay_evidence(event)
        _append_json(
            self.path / "events.jsonl",
            {**event, "event_sha256": event_hash},
        )
        self._event_sequence += 1
        self._last_event_sha256 = event_hash
        if replay_evidence is not None:
            self._record_replay_evidence(*replay_evidence, event_hash)


class FrontierArchive:
    """A bounded archive of semantic niches with limited visual diversity."""

    MAX_VISUAL_VARIANTS_PER_PRIMARY = 3
    PROMOTION_WARMUP_CREDITS = 1

    def __init__(self, store: ExpeditionStore, capacity: int) -> None:
        if store.schema_version != EXPEDITION_STORE_SCHEMA:
            raise ValueError(
                "Legacy expedition stores are read-only and cannot enter a mutable v2 archive"
            )
        if capacity < 2:
            raise ValueError("A frontier archive must hold at least two cells")
        self.store = store
        self.capacity = capacity
        self.active_by_key: dict[
            tuple[str, int | None, int | None, int | None, str, int], str
        ] = {}
        self.selection_counts: dict[str, int] = {}
        self.promotion_warmup_credits: dict[str, int] = {}
        self.selection_total = 0

    @property
    def active_cells(self) -> tuple[FrontierCell, ...]:
        return tuple(self.store.cells[cell_id] for cell_id in self.active_by_key.values())

    @staticmethod
    def _cell_sort_key(cell: FrontierCell) -> tuple[Any, ...]:
        descriptor = cell.descriptor
        return (
            descriptor.milestone_index,
            descriptor.milestone_id,
            -1 if descriptor.map_id is None else descriptor.map_id,
            -1 if descriptor.x_bucket is None else descriptor.x_bucket,
            -1 if descriptor.y_bucket is None else descriptor.y_bucket,
            descriptor.battle_kind,
            descriptor.visual_class,
            cell.cell_id,
        )

    def _primary_group(self, descriptor: FrontierDescriptor) -> list[FrontierCell]:
        return [
            cell
            for cell in self.active_cells
            if cell.descriptor.primary_key == descriptor.primary_key
        ]

    def _is_promotion(self, cell: FrontierCell) -> bool:
        if cell.parent_id is None:
            return False
        return (
            cell.descriptor.milestone_index
            > self.store.cells[cell.parent_id].descriptor.milestone_index
        )

    def _protected_ids(self) -> set[str]:
        """Protect the root and the best certificate at the current promotion frontier."""

        protected = {
            cell.cell_id for cell in self.active_cells if cell.parent_id is None
        }
        promotions = [cell for cell in self.active_cells if self._is_promotion(cell)]
        if promotions:
            highest = max(cell.descriptor.milestone_index for cell in promotions)
            representative = max(
                (cell for cell in promotions if cell.descriptor.milestone_index == highest),
                key=lambda item: (item.quality, item.cell_id),
            )
            protected.add(representative.cell_id)
        return protected

    def candidate_priority(
        self,
        descriptor: FrontierDescriptor,
        referee_summary: Mapping[str, int | str | bool | None],
        depth_actions: int,
    ) -> tuple[int, int, int, int, int, int, int]:
        """Rank an unpersisted candidate for a runner-side suffix buffer.

        The first fields reward actual semantic progress, then novel semantic/visual niches;
        the remaining fields match :attr:`FrontierCell.quality`.  No mutation or audit event is
        produced, so runners can discard weak suffixes before writing private payloads.
        """

        if depth_actions < 0:
            raise ValueError("A candidate action depth cannot be negative")
        self.store._validate_descriptor(descriptor)
        primary_present = any(
            cell.descriptor.primary_key == descriptor.primary_key
            for cell in self.active_cells
        )
        variant_present = descriptor.variant_key in self.active_by_key
        return (
            descriptor.milestone_index,
            int(not primary_present),
            int(not variant_present),
            int(referee_summary.get("badge_count", 0) or 0),
            int(referee_summary.get("required_events", 0) or 0),
            int(referee_summary.get("pokedex_owned", 0) or 0),
            -depth_actions,
        )

    @staticmethod
    def _candidate_quality(
        descriptor: FrontierDescriptor,
        referee_summary: Mapping[str, int | str | bool | None],
        depth_actions: int,
    ) -> tuple[int, int, int, int, int]:
        return (
            descriptor.milestone_index,
            int(referee_summary.get("badge_count", 0) or 0),
            int(referee_summary.get("required_events", 0) or 0),
            int(referee_summary.get("pokedex_owned", 0) or 0),
            -depth_actions,
        )

    def _competitiveness_decision(
        self,
        descriptor: FrontierDescriptor,
        quality: tuple[int, int, int, int, int],
    ) -> ArchiveDecision:
        existing_id = self.active_by_key.get(descriptor.variant_key)
        if existing_id is not None:
            existing = self.store.cells[existing_id]
            if existing.parent_id is None:
                return ArchiveDecision(False, "same_niche_root_protected", existing_id)
            if existing_id in self._protected_ids():
                return ArchiveDecision(False, "same_niche_promotion_protected", existing_id)
            if quality <= existing.quality:
                return ArchiveDecision(False, "same_niche_not_better", existing_id)
            return ArchiveDecision(True, "same_niche_improved", existing_id)

        primary_group = self._primary_group(descriptor)
        group_limit = self.MAX_VISUAL_VARIANTS_PER_PRIMARY + 1
        if len(primary_group) >= group_limit:
            representative = max(
                primary_group,
                key=lambda item: (item.quality, item.cell_id),
            )
            protected = self._protected_ids() | {representative.cell_id}
            variants = [item for item in primary_group if item.cell_id not in protected]
            if not variants:
                return ArchiveDecision(False, "primary_variant_cap_protected")
            worst_variant = min(variants, key=lambda item: (item.quality, item.cell_id))
            if quality <= worst_variant.quality:
                return ArchiveDecision(
                    False,
                    "primary_variant_cap_not_competitive",
                    worst_variant.cell_id,
                )
            return ArchiveDecision(
                True,
                "primary_variant_replacement",
                worst_variant.cell_id,
            )

        if len(self.active_by_key) < self.capacity:
            return ArchiveDecision(True, "unused_capacity")

        protected_ids = self._protected_ids()
        highest_tier = max(active.descriptor.milestone_index for active in self.active_cells)
        candidates = [
            active
            for active in self.active_cells
            if active.cell_id not in protected_ids
            and active.descriptor.milestone_index < highest_tier
        ]
        if not candidates:
            candidates = [
                active for active in self.active_cells if active.cell_id not in protected_ids
            ]
        if not candidates and descriptor.milestone_index > highest_tier:
            # A strictly newer milestone must be able to supersede the old frontier even when a
            # tiny archive consists only of the root and its protected promotion anchor.
            candidates = [active for active in self.active_cells if active.parent_id is not None]
        if not candidates:
            return ArchiveDecision(False, "capacity_root_protected")
        worst = min(candidates, key=lambda active: (active.quality, active.cell_id))
        if quality <= worst.quality:
            return ArchiveDecision(False, "capacity_not_competitive", worst.cell_id)
        return ArchiveDecision(True, "milestone_aware_replacement", worst.cell_id)

    def preflight_ordinary_candidate(
        self,
        descriptor: FrontierDescriptor,
        referee_summary: Mapping[str, int | str | bool | None],
        depth_actions: int,
    ) -> ArchiveDecision:
        """Preview deterministic archive competitiveness without writing or mutating state.

        This preflight deliberately says nothing about replay eligibility. The runner may use a
        rejection to avoid persisting a certainly uncompetitive ordinary suffix candidate; an
        admission still requires a durable cell, its exact edge certificate, and the normal
        :meth:`consider` gate.
        """

        if depth_actions < 0:
            raise ValueError("A candidate action depth cannot be negative")
        self.store._validate_descriptor(descriptor)
        quality = self._candidate_quality(descriptor, referee_summary, depth_actions)
        if any(item < 0 for item in quality[1:4]):
            raise ValueError("Frontier quality fields cannot be negative")
        return self._competitiveness_decision(descriptor, quality)

    def checkpoint_dict(self) -> dict[str, Any]:
        active_ids = [
            cell.cell_id for cell in sorted(self.active_cells, key=self._cell_sort_key)
        ]
        return {
            "schema_version": 2,
            "capacity": self.capacity,
            "max_visual_variants_per_primary": self.MAX_VISUAL_VARIANTS_PER_PRIMARY,
            "active_cell_ids": active_ids,
            "selection_counts": {
                cell_id: self.selection_counts.get(cell_id, 0)
                for cell_id in sorted(active_ids)
            },
            "promotion_warmup_credits": {
                cell_id: self.promotion_warmup_credits[cell_id]
                for cell_id in sorted(active_ids)
                if self.promotion_warmup_credits.get(cell_id, 0) > 0
            },
            "selection_total": self.selection_total,
        }

    @classmethod
    def from_checkpoint_dict(
        cls,
        store: ExpeditionStore,
        value: Mapping[str, Any],
    ) -> FrontierArchive:
        schema_version = int(value.get("schema_version", -1))
        if schema_version != 2:
            raise ValueError("Unsupported frontier archive checkpoint schema")
        archive = cls(store, int(value["capacity"]))
        active_ids = [str(cell_id) for cell_id in value.get("active_cell_ids", [])]
        if len(active_ids) != len(set(active_ids)) or len(active_ids) > archive.capacity:
            raise ValueError("Frontier archive checkpoint has invalid active cells")
        checkpoint_cells: list[FrontierCell] = []
        for cell_id in active_ids:
            if cell_id not in store.cells:
                raise ValueError("Frontier archive checkpoint references an unknown cell")
            cell = store.cells[cell_id]
            if any(
                existing.descriptor.variant_key == cell.descriptor.variant_key
                for existing in checkpoint_cells
            ):
                raise ValueError("Frontier archive checkpoint contains duplicate niches")
            if store.replay_deficits(cell_id):
                raise ValueError(
                    "Frontier archive checkpoint contains an unverified cell or ancestor"
                )
            checkpoint_cells.append(cell)
        if int(value.get("max_visual_variants_per_primary", -1)) != (
            archive.MAX_VISUAL_VARIANTS_PER_PRIMARY
        ):
            raise ValueError("Frontier archive checkpoint visual cap is incompatible")
        groups: dict[tuple[str, int | None, int | None, int | None, str], int] = {}
        for cell in checkpoint_cells:
            key = cell.descriptor.primary_key
            groups[key] = groups.get(key, 0) + 1
        if any(
            count > archive.MAX_VISUAL_VARIANTS_PER_PRIMARY + 1
            for count in groups.values()
        ):
            raise ValueError("Frontier archive checkpoint exceeds its visual variant cap")
        for cell in sorted(checkpoint_cells, key=archive._cell_sort_key):
            archive.active_by_key[cell.descriptor.variant_key] = cell.cell_id
        counts = {
            str(cell_id): int(count)
            for cell_id, count in value.get("selection_counts", {}).items()
        }
        retained_ids = set(archive.active_by_key.values())
        if set(counts) - set(active_ids) or any(count < 0 for count in counts.values()):
            raise ValueError("Frontier archive checkpoint has invalid selection counts")
        archive.selection_counts = {
            cell_id: count for cell_id, count in counts.items() if cell_id in retained_ids
        }
        warmup = {
            str(cell_id): int(credits)
            for cell_id, credits in value.get("promotion_warmup_credits", {}).items()
        }
        if (
            set(warmup) - retained_ids
            or any(
                credits < 0 or credits > archive.PROMOTION_WARMUP_CREDITS
                for credits in warmup.values()
            )
            or any(not archive._is_promotion(store.cells[cell_id]) for cell_id in warmup)
        ):
            raise ValueError("Frontier archive checkpoint has invalid warmup credits")
        archive.promotion_warmup_credits = warmup
        archive.selection_total = int(value.get("selection_total", -1))
        if archive.selection_total < sum(archive.selection_counts.values()):
            raise ValueError("Frontier archive checkpoint selection total is invalid")
        return archive

    def _remove(self, cell: FrontierCell) -> None:
        self.active_by_key.pop(cell.descriptor.variant_key)
        self.selection_counts.pop(cell.cell_id, None)
        self.promotion_warmup_credits.pop(cell.cell_id, None)

    def _admit(
        self,
        cell: FrontierCell,
        *,
        highest_tier_before: int,
        replaced: FrontierCell | None = None,
    ) -> None:
        if replaced is not None:
            self._remove(replaced)
        self.active_by_key[cell.descriptor.variant_key] = cell.cell_id
        if self._is_promotion(cell) and cell.descriptor.milestone_index > highest_tier_before:
            self.promotion_warmup_credits[cell.cell_id] = (
                self.PROMOTION_WARMUP_CREDITS
            )

    def consider(self, cell: FrontierCell) -> ArchiveDecision:
        stored = self.store.cells.get(cell.cell_id)
        if stored is None or stored != cell:
            raise ValueError("Frontier archive can consider only cells from its own store")
        deficits = self.store.verification_deficits(cell.cell_id)
        if deficits:
            deficit_id, replay_kind, completed_replays, required_replays = deficits[0]
            reason = (
                f"quarantined_{replay_kind}_{completed_replays}_of_{required_replays}"
                if deficit_id == cell.cell_id
                else (
                    f"quarantined_ancestor_{deficit_id[:12]}_{replay_kind}_"
                    f"{completed_replays}_of_{required_replays}"
                )
            )
            decision = ArchiveDecision(
                False,
                reason,
            )
            self.store.audit("archive_decision", cell_id=cell.cell_id, **asdict(decision))
            return decision
        highest_tier_before = max(
            (active.descriptor.milestone_index for active in self.active_cells),
            default=-1,
        )
        decision = self._competitiveness_decision(cell.descriptor, cell.quality)
        if decision.admitted:
            replaced = (
                None
                if decision.replaced_cell_id is None
                else self.store.cells[decision.replaced_cell_id]
            )
            self._admit(
                cell,
                highest_tier_before=highest_tier_before,
                replaced=replaced,
            )
        self.store.audit("archive_decision", cell_id=cell.cell_id, **asdict(decision))
        return decision

    def select(
        self,
        rng: random.Random,
        *,
        frontier_probability: float = 0.70,
        rehearsal_probability: float = 0.10,
    ) -> tuple[FrontierCell, str]:
        if not self.active_by_key:
            raise RuntimeError("Cannot select from an empty frontier archive")
        if not 0 <= frontier_probability <= 1 or not 0 <= rehearsal_probability <= 1:
            raise ValueError("Frontier selection probabilities must be between zero and one")
        if frontier_probability + rehearsal_probability > 1:
            raise ValueError("Frontier selection probabilities cannot exceed one")
        cells = list(self.active_cells)
        warmup_pool = [
            cell
            for cell in cells
            if self.promotion_warmup_credits.get(cell.cell_id, 0) > 0
        ]
        used_warmup = bool(warmup_pool)
        if warmup_pool:
            highest = max(cell.descriptor.milestone_index for cell in warmup_pool)
            pool = [
                cell for cell in warmup_pool if cell.descriptor.milestone_index == highest
            ]
            channel = "frontier"
        else:
            draw = rng.random()
            if draw < frontier_probability:
                highest = max(cell.descriptor.milestone_index for cell in cells)
                pool = [cell for cell in cells if cell.descriptor.milestone_index == highest]
                channel = "frontier"
            elif draw < frontier_probability + rehearsal_probability:
                lowest = min(cell.descriptor.milestone_index for cell in cells)
                pool = [cell for cell in cells if cell.descriptor.milestone_index == lowest]
                channel = "rehearsal"
            else:
                pool = cells
                channel = "underexplored"
        selected = min(
            pool,
            key=lambda cell: (
                self.selection_counts.get(cell.cell_id, 0),
                cell.discovered_global_action,
                cell.cell_id,
            ),
        )
        self.selection_counts[selected.cell_id] = self.selection_counts.get(selected.cell_id, 0) + 1
        self.selection_total += 1
        if used_warmup:
            credits = self.promotion_warmup_credits[selected.cell_id] - 1
            if credits:
                self.promotion_warmup_credits[selected.cell_id] = credits
            else:
                self.promotion_warmup_credits.pop(selected.cell_id)
        self.store.audit(
            "frontier_selected",
            cell_id=selected.cell_id,
            channel=channel,
            selection_count=self.selection_counts[selected.cell_id],
            selection_total=self.selection_total,
            promotion_warmup=used_warmup,
        )
        return selected, channel


class ReplayEvaluator(Protocol):
    def __call__(self, state: PokemonRedState, pixels: np.ndarray) -> bool: ...


def _replay_actions(
    rom_path: Path,
    store: ExpeditionStore,
    cell_id: str,
    *,
    actions: Iterable[BlindAction],
    action_count: int,
    starting_snapshot: FrozenSnapshot | None,
    starting_progress: MilestoneProgress | None,
    evaluator: ReplayEvaluator | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> ReplayResult:
    if cell_id not in store.cells:
        raise ValueError("Unknown frontier cell")
    target = store.cells[cell_id]
    mismatch_reasons: list[str] = []
    actual_snapshot_sha256 = ""
    actual_screen_sha256 = ""
    final_state_dict: dict[str, object] = {}
    actual_descriptor_dict: dict[str, Any] = {}
    actual_referee_summary: dict[str, int | str | bool | None] = {}
    actual_progress = MilestoneProgress("power_on", 0, "Power-on")
    executed_action_count = 0
    try:
        with PokemonRedEmulator(rom_path) as emulator:
            reader = PokemonRedStateReader(emulator)
            if starting_snapshot is not None:
                emulator.load_state(starting_snapshot.thaw())
            initial_state = reader.read()
            actual_progress = milestone_progress_for_state(
                initial_state,
                inherited=starting_progress,
            )
            for action in actions:
                if cancel_requested is not None and cancel_requested():
                    mismatch_reasons.append("replay_cancelled")
                    break
                alive = (
                    emulator.tick(action.total_frames, render_last=True)
                    if action.button == "noop"
                    else emulator.press(
                        action.button,
                        hold_frames=action.hold_frames,
                        release_frames=action.release_frames,
                    )
                )
                executed_action_count += 1
                state = reader.read()
                actual_progress = milestone_progress_for_state(
                    state,
                    inherited=actual_progress,
                )
                if not alive:
                    mismatch_reasons.append("emulator_stopped")
                    break
            final_state = reader.read()
            actual_progress = milestone_progress_for_state(
                final_state,
                inherited=actual_progress,
            )
            pixels = emulator.screen_rgb()
            actual_screen_sha256 = hashlib.sha256(pixels.tobytes()).hexdigest()
            actual_snapshot_sha256 = emulator.save_state().sha256
            final_state_dict = final_state.public_dict()
            actual_descriptor = descriptor_from_state(
                final_state,
                milestone_id=actual_progress.key,
                milestone_index=actual_progress.index,
                visual_key=visual_key(pixels),
            )
            actual_descriptor_dict = actual_descriptor.public_dict()
            actual_referee_summary = referee_summary_for_state(final_state, actual_progress)
            if evaluator is not None and not evaluator(final_state, pixels):
                mismatch_reasons.append("additional_target_predicate_failed")
            if actual_snapshot_sha256 != target.snapshot_sha256:
                mismatch_reasons.append("snapshot_hash_mismatch")
            if actual_screen_sha256 != target.screen_sha256:
                mismatch_reasons.append("screen_hash_mismatch")
            if (
                actual_progress.key != target.descriptor.milestone_id
                or actual_progress.index != target.descriptor.milestone_index
            ):
                mismatch_reasons.append("canonical_milestone_mismatch")
            if actual_descriptor != target.descriptor:
                mismatch_reasons.append("full_descriptor_mismatch")
            if _replay_referee_projection(
                actual_referee_summary
            ) != _replay_referee_projection(target.referee_summary):
                mismatch_reasons.append("canonical_referee_summary_mismatch")
    except Exception as error:  # Every planned verifier failure belongs in the ledger.
        mismatch_reasons.append(f"verifier_exception:{type(error).__name__}")

    failure_reason = mismatch_reasons[0] if mismatch_reasons else None
    result = ReplayResult(
        cell_id=cell_id,
        passed=not mismatch_reasons,
        action_count=action_count,
        executed_action_count=executed_action_count,
        expected_snapshot_sha256=target.snapshot_sha256,
        actual_snapshot_sha256=actual_snapshot_sha256,
        expected_screen_sha256=target.screen_sha256,
        actual_screen_sha256=actual_screen_sha256,
        final_state=final_state_dict,
        expected_milestone_id=target.descriptor.milestone_id,
        expected_milestone_index=target.descriptor.milestone_index,
        actual_milestone_id=actual_progress.key,
        actual_milestone_index=actual_progress.index,
        expected_descriptor=target.descriptor.public_dict(),
        actual_descriptor=actual_descriptor_dict,
        expected_referee_summary=dict(target.referee_summary),
        actual_referee_summary=actual_referee_summary,
        mismatch_reasons=tuple(mismatch_reasons),
        failure_reason=failure_reason,
    )
    return result


def replay_frontier_cell(
    rom_path: Path,
    store: ExpeditionStore,
    cell_id: str,
    *,
    evaluator: ReplayEvaluator | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> ReplayResult:
    """Replay from fresh power-on and require exact hashes plus canonical semantic progress."""

    if cell_id not in store.cells:
        raise ValueError("Unknown frontier cell")
    target = store.cells[cell_id]
    result = _replay_actions(
        rom_path,
        store,
        cell_id,
        actions=store.iter_lineage_actions(cell_id),
        action_count=target.depth_actions,
        starting_snapshot=None,
        starting_progress=None,
        evaluator=evaluator,
        cancel_requested=cancel_requested,
    )
    store.audit("power_on_replay", **result.public_dict())
    return result


def replay_frontier_edge(
    rom_path: Path,
    store: ExpeditionStore,
    cell_id: str,
    *,
    evaluator: ReplayEvaluator | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> ReplayResult:
    """Verify exactly one parent-to-child edge from the parent's stored snapshot.

    This cheaper certificate establishes local checkpoint integrity. A named milestone advance
    still needs three independent :func:`replay_frontier_cell` claims from power-on before it is
    selectable.
    """

    if cell_id not in store.cells:
        raise ValueError("Unknown frontier cell")
    if store.schema_version != EXPEDITION_STORE_SCHEMA:
        raise ValueError("Legacy expedition stores cannot issue v2 edge certificates")
    target = store.cells[cell_id]
    if target.parent_id is None:
        raise ValueError("The expedition root does not have a replayable edge")
    parent = store.cells[target.parent_id]
    segment = store.read_segment(target.segment_sha256)
    parent_progress = MilestoneProgress(
        parent.descriptor.milestone_id,
        parent.descriptor.milestone_index,
        _CANONICAL_PROGRESS[parent.descriptor.milestone_id][1],
    )
    result = _replay_actions(
        rom_path,
        store,
        cell_id,
        actions=segment,
        action_count=len(segment),
        starting_snapshot=store.read_snapshot(parent.snapshot_sha256),
        starting_progress=parent_progress,
        evaluator=evaluator,
        cancel_requested=cancel_requested,
    )
    store.audit(
        "edge_replay",
        parent_id=parent.cell_id,
        expected_parent_snapshot_sha256=parent.snapshot_sha256,
        expected_segment_sha256=target.segment_sha256,
        **result.public_dict(),
    )
    return result


def descriptor_from_state(
    state: PokemonRedState,
    *,
    milestone_id: str,
    milestone_index: int,
    visual_key: bytes,
    coordinate_bucket_size: int = 4,
) -> FrontierDescriptor:
    if coordinate_bucket_size < 1:
        raise ValueError("Coordinate bucket size must be positive")
    if len(visual_key) < 2:
        raise ValueError("A visual key must contain at least two bytes")
    return FrontierDescriptor(
        milestone_id=milestone_id,
        milestone_index=milestone_index,
        map_id=state.map_id,
        x_bucket=(
            None if state.player_x is None else state.player_x // coordinate_bucket_size
        ),
        y_bucket=(
            None if state.player_y is None else state.player_y // coordinate_bucket_size
        ),
        battle_kind=state.battle_kind,
        visual_class=int.from_bytes(visual_key[:2], "big"),
    )


def milestone_progress_for_state(
    state: PokemonRedState,
    *,
    inherited: MilestoneProgress | None = None,
) -> MilestoneProgress:
    """Return the furthest durable outcome without leaking it to the actor.

    Index zero is reserved for power-on. Catalog ordinals are shifted by one so game start is a
    real advancement. A restored frontier inherits its already-verified progress because some
    landmark conditions describe a location that is no longer present in the current RAM state.
    """

    matching = [milestone for milestone in MILESTONES if milestone.reached_by(state)]
    observed = (
        MilestoneProgress("power_on", 0, "Power-on")
        if not matching
        else MilestoneProgress(
            matching[-1].key,
            matching[-1].ordinal + 1,
            matching[-1].label,
        )
    )
    if inherited is not None and inherited.index > observed.index:
        return inherited
    return observed


def referee_summary_for_state(
    state: PokemonRedState,
    progress: MilestoneProgress,
) -> dict[str, int | str | bool | None]:
    """Small, public-safe training metadata; raw RAM and proprietary payloads stay private."""

    reached_named_outcomes = sum(milestone.reached_by(state) for milestone in MILESTONES)
    return {
        "milestone_id": progress.key,
        "milestone_index": progress.index,
        "milestone_label": progress.label,
        "map_id": state.map_id,
        "badge_count": state.badge_count,
        "required_events": reached_named_outcomes,
        "party_count": state.party_count,
        "pokedex_seen": state.pokedex_seen_count,
        "pokedex_owned": state.pokedex_owned_count,
        "got_pokedex": state.got_pokedex,
        "hall_of_fame": MILESTONE_BY_KEY["hall_of_fame"].reached_by(state),
    }


def replay_predicate_for_milestone(
    classify: Callable[[PokemonRedState], tuple[str, int]],
    expected_id: str,
    expected_index: int,
) -> ReplayEvaluator:
    def evaluate(state: PokemonRedState, _pixels: np.ndarray) -> bool:
        milestone_id, milestone_index = classify(state)
        return milestone_index >= expected_index and (
            milestone_id == expected_id or milestone_index > expected_index
        )

    return evaluate
