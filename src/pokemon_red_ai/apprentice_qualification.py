from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_red_ai.apprentice_artifacts import (
    canonical_json,
    seal_apprentice_bundle,
    sha256_file,
    verify_apprentice_bundle,
)
from pokemon_red_ai.apprentice_data import (
    STAGE0_Q1_ACTION_COUNT,
    STAGE0_Q1_LINEAGE_SHA256,
    STAGE0_Q1_TARGET_CELL_ID,
    verify_apprentice_dataset,
)
from pokemon_red_ai.apprentice_stage0 import (
    verify_stage0_evaluation_bundle,
    verify_stage0_training_bundle,
)
from pokemon_red_ai.provenance import detect_source_provenance

STAGE0_DATA_QUALIFICATION_PROTOCOL = "visual-apprentice-stage0-data-qualification-v1"
STAGE0_COMPOSITE_PROTOCOL = "visual-apprentice-stage0-composite-qualification-v1"
DATA_BUNDLE_KIND = "visual-apprentice-stage0-data-qualification"
COMPOSITE_BUNDLE_KIND = "visual-apprentice-stage0-composite-qualification"


def _private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repository = next(
        (candidate for candidate in (resolved, *resolved.parents) if (candidate / ".git").exists()),
        None,
    )
    if repository is not None:
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(resolved)],
            cwd=repository,
            check=False,
            capture_output=True,
        )
        if ignored.returncode != 0:
            raise ValueError("Stage-0 qualification artifacts must be outside Git or ignored")
    return resolved


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as output:
        output.write(canonical_json(value) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _create_output(path: Path) -> Path:
    output = _private_output(path)
    if output.exists():
        raise ValueError("Stage-0 qualification output already exists")
    output.mkdir(parents=True)
    (output / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    return output


def _clean_source() -> dict[str, str | bool]:
    source = detect_source_provenance()
    if source.git_commit is None or source.worktree_dirty is not False:
        raise ValueError("Official Stage-0 qualification requires committed, clean source")
    return source.public_dict()


def qualify_stage0_data(
    first_dataset: Path,
    second_dataset: Path,
    output_path: Path,
) -> Mapping[str, Any]:
    """Prove that two distinct captures yield the same logical Q1 dataset."""

    first_path = first_dataset.expanduser().resolve()
    second_path = second_dataset.expanduser().resolve()
    if first_path == second_path:
        raise ValueError("Stage-0 data qualification requires two different dataset directories")
    first = verify_apprentice_dataset(first_path)
    second = verify_apprentice_dataset(second_path)
    if first["capture_id"] == second["capture_id"]:
        raise ValueError("Stage-0 data qualification requires two independent capture identities")
    if first["dataset_sha256"] != second["dataset_sha256"]:
        raise ValueError("Stage-0 independent captures produced different logical datasets")
    if first["implementation"] != second["implementation"]:
        raise ValueError("Stage-0 captures use different implementations")
    source = _clean_source()
    if source != first["implementation"]:
        raise ValueError("Stage-0 data qualification source differs from its captures")

    output = _create_output(output_path)
    first_manifest_sha256 = sha256_file(first_path / "manifest.json")
    second_manifest_sha256 = sha256_file(second_path / "manifest.json")
    manifest = {
        "schema_version": 1,
        "protocol": STAGE0_DATA_QUALIFICATION_PROTOCOL,
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "canonical_target": {
            "cell_id": STAGE0_Q1_TARGET_CELL_ID,
            "lineage_sha256": STAGE0_Q1_LINEAGE_SHA256,
            "action_count": STAGE0_Q1_ACTION_COUNT,
            "decision_boundary_frame_count": STAGE0_Q1_ACTION_COUNT + 1,
        },
        "captures": [
            {
                "ordinal": 1,
                "capture_id": first["capture_id"],
                "manifest_sha256": first_manifest_sha256,
                "dataset_sha256": first["dataset_sha256"],
            },
            {
                "ordinal": 2,
                "capture_id": second["capture_id"],
                "manifest_sha256": second_manifest_sha256,
                "dataset_sha256": second["dataset_sha256"],
            },
        ],
    }
    summary = {
        "schema_version": 1,
        "protocol": STAGE0_DATA_QUALIFICATION_PROTOCOL,
        "passed": True,
        "independent_capture_count": 2,
        "logical_hashes_match": True,
        "dataset_sha256": first["dataset_sha256"],
        "action_count": STAGE0_Q1_ACTION_COUNT,
        "decision_boundary_frame_count": STAGE0_Q1_ACTION_COUNT + 1,
        "terminal_replays_exact": True,
    }
    _atomic_json(output / "manifest.json", manifest)
    _atomic_json(output / "summary.json", summary)
    receipt = seal_apprentice_bundle(
        output,
        kind=DATA_BUNDLE_KIND,
        subject_protocol=STAGE0_DATA_QUALIFICATION_PROTOCOL,
        identities={
            "dataset_sha256": first["dataset_sha256"],
            "first_manifest_sha256": first_manifest_sha256,
            "second_manifest_sha256": second_manifest_sha256,
            "source_commit": source["git_commit"],
        },
    )
    verify_stage0_data_qualification(output)
    return receipt


def verify_stage0_data_qualification(path: Path) -> Mapping[str, Any]:
    directory = path.expanduser().resolve()
    receipt = verify_apprentice_bundle(
        directory,
        expected_kind=DATA_BUNDLE_KIND,
        expected_subject_protocol=STAGE0_DATA_QUALIFICATION_PROTOCOL,
    )
    if set(receipt["files"]) != {".gitignore", "manifest.json", "summary.json"}:
        raise ValueError("Stage-0 data qualification file set is not canonical")
    import json

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    captures = manifest.get("captures", [])
    if (
        manifest.get("protocol") != STAGE0_DATA_QUALIFICATION_PROTOCOL
        or manifest.get("canonical_target")
        != {
            "cell_id": STAGE0_Q1_TARGET_CELL_ID,
            "lineage_sha256": STAGE0_Q1_LINEAGE_SHA256,
            "action_count": STAGE0_Q1_ACTION_COUNT,
            "decision_boundary_frame_count": STAGE0_Q1_ACTION_COUNT + 1,
        }
        or not isinstance(captures, list)
        or len(captures) != 2
        or [capture.get("ordinal") for capture in captures] != [1, 2]
        or captures[0].get("capture_id") == captures[1].get("capture_id")
        or any(
            not isinstance(capture.get("capture_id"), str)
            or len(capture["capture_id"]) != 32
            or not isinstance(capture.get("manifest_sha256"), str)
            or len(capture["manifest_sha256"]) != 64
            for capture in captures
        )
    ):
        raise ValueError("Stage-0 data qualification manifest is invalid")
    dataset_sha256 = receipt["identities"].get("dataset_sha256")
    if (
        summary
        != {
            "schema_version": 1,
            "protocol": STAGE0_DATA_QUALIFICATION_PROTOCOL,
            "passed": True,
            "independent_capture_count": 2,
            "logical_hashes_match": True,
            "dataset_sha256": dataset_sha256,
            "action_count": STAGE0_Q1_ACTION_COUNT,
            "decision_boundary_frame_count": STAGE0_Q1_ACTION_COUNT + 1,
            "terminal_replays_exact": True,
        }
        or any(
            capture.get("dataset_sha256") != dataset_sha256
            for capture in captures
        )
        or captures[0]["manifest_sha256"]
        != receipt["identities"].get("first_manifest_sha256")
        or captures[1]["manifest_sha256"]
        != receipt["identities"].get("second_manifest_sha256")
        or manifest.get("source", {}).get("worktree_dirty") is not False
        or receipt["identities"].get("source_commit")
        != manifest.get("source", {}).get("git_commit")
    ):
        raise ValueError("Stage-0 data qualification identities disagree")
    return receipt


def qualify_stage0_composite(
    data_qualification: Path,
    training_bundle: Path,
    evaluation_bundle: Path,
    output_path: Path,
) -> Mapping[str, Any]:
    """Issue the only Stage-0 PASS after data, offline, and live gates agree."""

    data = verify_stage0_data_qualification(data_qualification)
    training = verify_stage0_training_bundle(training_bundle)
    evaluation = verify_stage0_evaluation_bundle(evaluation_bundle)
    source = _clean_source()
    dataset_sha256 = data["identities"]["dataset_sha256"]
    model_sha256 = training["identities"]["model_sha256"]
    source_commit = source["git_commit"]
    if (
        training["identities"]["dataset_sha256"] != dataset_sha256
        or evaluation["identities"]["dataset_sha256"] != dataset_sha256
        or evaluation["identities"]["model_sha256"] != model_sha256
        or evaluation["identities"]["training_bundle_sha256"]
        != training["bundle_sha256"]
        or any(
            receipt["identities"]["source_commit"] != source_commit
            for receipt in (data, training, evaluation)
        )
    ):
        raise ValueError("Stage-0 data, model, evaluation, or source identities disagree")

    output = _create_output(output_path)
    manifest = {
        "schema_version": 1,
        "protocol": STAGE0_COMPOSITE_PROTOCOL,
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "data_qualification_bundle_sha256": data["bundle_sha256"],
        "training_bundle_sha256": training["bundle_sha256"],
        "evaluation_bundle_sha256": evaluation["bundle_sha256"],
        "dataset_sha256": dataset_sha256,
        "model_sha256": model_sha256,
    }
    summary = {
        "schema_version": 1,
        "protocol": STAGE0_COMPOSITE_PROTOCOL,
        "passed": True,
        "data_gate": "passed",
        "offline_gate": "passed",
        "closed_loop_gate": "passed",
        "dataset_sha256": dataset_sha256,
        "model_sha256": model_sha256,
        "claim_boundary": (
            "one frozen model exactly fit its single trajectory offline and reached "
            "left_home once in closed loop"
        ),
        "not_claimed": ["recovery", "generalization", "H2", "general Pokemon play"],
    }
    _atomic_json(output / "manifest.json", manifest)
    _atomic_json(output / "summary.json", summary)
    receipt = seal_apprentice_bundle(
        output,
        kind=COMPOSITE_BUNDLE_KIND,
        subject_protocol=STAGE0_COMPOSITE_PROTOCOL,
        identities={
            "dataset_sha256": dataset_sha256,
            "model_sha256": model_sha256,
            "source_commit": source_commit,
            "data_qualification_bundle_sha256": data["bundle_sha256"],
            "training_bundle_sha256": training["bundle_sha256"],
            "evaluation_bundle_sha256": evaluation["bundle_sha256"],
        },
    )
    verify_stage0_composite(output)
    return receipt


def verify_stage0_composite(path: Path) -> Mapping[str, Any]:
    directory = path.expanduser().resolve()
    receipt = verify_apprentice_bundle(
        directory,
        expected_kind=COMPOSITE_BUNDLE_KIND,
        expected_subject_protocol=STAGE0_COMPOSITE_PROTOCOL,
    )
    if set(receipt["files"]) != {".gitignore", "manifest.json", "summary.json"}:
        raise ValueError("Stage-0 composite file set is not canonical")
    import json

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    identities = receipt["identities"]
    if (
        manifest.get("protocol") != STAGE0_COMPOSITE_PROTOCOL
        or summary.get("protocol") != STAGE0_COMPOSITE_PROTOCOL
        or summary.get("passed") is not True
        or [summary.get(name) for name in ("data_gate", "offline_gate", "closed_loop_gate")]
        != ["passed", "passed", "passed"]
        or manifest.get("dataset_sha256") != identities.get("dataset_sha256")
        or manifest.get("model_sha256") != identities.get("model_sha256")
        or summary.get("dataset_sha256") != identities.get("dataset_sha256")
        or summary.get("model_sha256") != identities.get("model_sha256")
        or manifest.get("source", {}).get("git_commit") != identities.get("source_commit")
        or manifest.get("source", {}).get("worktree_dirty") is not False
    ):
        raise ValueError("Stage-0 composite identities or gates disagree")
    for name in (
        "data_qualification_bundle_sha256",
        "training_bundle_sha256",
        "evaluation_bundle_sha256",
    ):
        if manifest.get(name) != identities.get(name):
            raise ValueError("Stage-0 composite component identity disagrees")
    return receipt
