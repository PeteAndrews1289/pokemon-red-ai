from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

APPRENTICE_BUNDLE_PROTOCOL = "apprentice-integrity-bundle-v1"


class ApprenticeBundleError(ValueError):
    """Raised when a Stage-0 result bundle is incomplete or has changed."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def strict_json(payload: bytes, *, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ApprenticeBundleError(f"{label} contains duplicate JSON keys")
            value[key] = item
        return value

    try:
        return json.loads(payload, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApprenticeBundleError(f"{label} is not valid JSON") from error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_records(directory: Path) -> dict[str, dict[str, int | str]]:
    records: dict[str, dict[str, int | str]] = {}
    for item in sorted(directory.rglob("*")):
        if item.is_symlink():
            raise ApprenticeBundleError("Apprentice bundles cannot contain symbolic links")
        if not item.is_file() or item.name == "SUCCESS":
            continue
        relative = item.relative_to(directory).as_posix()
        records[relative] = {
            "sha256": sha256_file(item),
            "bytes": item.stat().st_size,
        }
    if not records:
        raise ApprenticeBundleError("Apprentice bundle has no evidence files")
    return records


def _identity_payload(
    *,
    kind: str,
    subject_protocol: str,
    identities: Mapping[str, Any],
    files: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "subject_protocol": subject_protocol,
        "identities": dict(identities),
        "files": dict(files),
    }


def seal_apprentice_bundle(
    directory: Path,
    *,
    kind: str,
    subject_protocol: str,
    identities: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Close a successful bundle over every durable file in the directory."""

    directory = directory.expanduser().resolve()
    if not directory.is_dir() or directory.is_symlink():
        raise ApprenticeBundleError("Apprentice bundle path must be a real directory")
    marker = directory / "SUCCESS"
    if marker.exists():
        raise ApprenticeBundleError("Apprentice bundle is already sealed")
    if not kind or not subject_protocol:
        raise ApprenticeBundleError("Apprentice bundle identity is incomplete")
    files = _file_records(directory)
    identity = _identity_payload(
        kind=kind,
        subject_protocol=subject_protocol,
        identities=identities,
        files=files,
    )
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "protocol": APPRENTICE_BUNDLE_PROTOCOL,
        **identity,
        "bundle_sha256": hashlib.sha256(canonical_json(identity)).hexdigest(),
    }
    payload = canonical_json(receipt) + b"\n"
    temporary = directory / "SUCCESS.tmp"
    with temporary.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, marker)
    return verify_apprentice_bundle(
        directory,
        expected_kind=kind,
        expected_subject_protocol=subject_protocol,
    )


def verify_apprentice_bundle(
    directory: Path,
    *,
    expected_kind: str,
    expected_subject_protocol: str,
) -> Mapping[str, Any]:
    """Recompute one bundle's exact file set, hashes, sizes, and logical identity."""

    directory = directory.expanduser().resolve()
    if not directory.is_dir() or directory.is_symlink():
        raise ApprenticeBundleError("Apprentice bundle path must be a real directory")
    marker = directory / "SUCCESS"
    if not marker.is_file() or marker.is_symlink():
        raise ApprenticeBundleError("Apprentice bundle has no valid SUCCESS receipt")
    payload = marker.read_bytes()
    receipt = strict_json(payload, label="Apprentice SUCCESS receipt")
    if not isinstance(receipt, dict) or payload != canonical_json(receipt) + b"\n":
        raise ApprenticeBundleError("Apprentice SUCCESS receipt is not canonical")
    expected_fields = {
        "schema_version",
        "protocol",
        "kind",
        "subject_protocol",
        "identities",
        "files",
        "bundle_sha256",
    }
    if set(receipt) != expected_fields:
        raise ApprenticeBundleError("Apprentice SUCCESS receipt fields are invalid")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("protocol") != APPRENTICE_BUNDLE_PROTOCOL
        or receipt.get("kind") != expected_kind
        or receipt.get("subject_protocol") != expected_subject_protocol
    ):
        raise ApprenticeBundleError("Apprentice SUCCESS receipt identity is invalid")
    identities = receipt.get("identities")
    files = receipt.get("files")
    if not isinstance(identities, dict) or not isinstance(files, dict):
        raise ApprenticeBundleError("Apprentice SUCCESS receipt payload is invalid")
    actual_files = _file_records(directory)
    if actual_files != files:
        raise ApprenticeBundleError("Apprentice bundle file set or hash has changed")
    identity = _identity_payload(
        kind=expected_kind,
        subject_protocol=expected_subject_protocol,
        identities=identities,
        files=files,
    )
    expected_sha256 = hashlib.sha256(canonical_json(identity)).hexdigest()
    if receipt.get("bundle_sha256") != expected_sha256:
        raise ApprenticeBundleError("Apprentice bundle identity hash is invalid")
    return MappingProxyType(receipt)

