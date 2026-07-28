from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import os
import platform
import random
import resource
import shutil
import sys
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pokemon_red_ai.apprentice_artifacts import (
    canonical_json,
    seal_apprentice_bundle,
    strict_json,
    verify_apprentice_bundle,
)
from pokemon_red_ai.apprentice_data import (
    STAGE0_Q1_ACTION_COUNT,
    ApprenticeDataset,
    load_apprentice_dataset,
    preprocess_apprentice_frame,
    verify_apprentice_dataset,
)
from pokemon_red_ai.apprentice_model import (
    APPRENTICE_ARCHITECTURE,
    EXPECTED_PARAMETER_COUNT,
    ApprenticeModelConfig,
    build_apprentice_policy,
    require_torch,
)
from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    PixelsOnlyActor,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import MilestoneProgress, milestone_progress_for_state
from pokemon_red_ai.provenance import detect_source_provenance
from pokemon_red_ai.rom import verify_rom
from pokemon_red_ai.state import PokemonRedStateReader

STAGE0_PROTOCOL = "visual-apprentice-stage0-v1"
STAGE0_TRAINING_BUNDLE_KIND = "visual-apprentice-stage0-training"
STAGE0_EVALUATION_BUNDLE_KIND = "visual-apprentice-stage0-evaluation"
MODEL_FILENAME = "model.pt"
MODEL_METADATA_FILENAME = "model.json"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parameter_tensor_sha256(model: Any) -> str:
    """Hash named tensor values independently of PyTorch's checkpoint container."""

    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous().numpy()
        descriptor = {
            "name": name,
            "dtype": value.dtype.str,
            "shape": list(value.shape),
            "nbytes": int(value.nbytes),
        }
        encoded = _canonical_json(descriptor)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(value.tobytes())
    return digest.hexdigest()


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _atomic_json(path: Path, value: object) -> None:
    _atomic_bytes(path, _canonical_json(value) + b"\n")


def _read_canonical_json(path: Path, *, label: str) -> dict[str, Any]:
    payload = path.read_bytes()
    value = strict_json(payload, label=label)
    if not isinstance(value, dict) or payload != canonical_json(value) + b"\n":
        raise ValueError(f"{label} is not a canonical JSON object")
    return value


def _append_event(path: Path, kind: str, **fields: object) -> None:
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "kind": kind,
        **fields,
    }
    with path.open("ab") as output:
        output.write(_canonical_json(event) + b"\n")
        output.flush()
        os.fsync(output.fileno())


def _private_output_directory(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repository = next(
        (candidate for candidate in (resolved, *resolved.parents) if (candidate / ".git").exists()),
        None,
    )
    if repository is not None:
        import subprocess

        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(resolved)],
            cwd=repository,
            check=False,
            capture_output=True,
        )
        if ignored.returncode != 0:
            raise ValueError(
                "Visual Apprentice artifacts must be outside Git or below an ignored path"
            )
    return resolved


def _dataset_identity(manifest: Mapping[str, Any]) -> str:
    for key in ("dataset_sha256", "logical_sha256", "content_sha256"):
        value = manifest.get(key)
        if isinstance(value, str) and len(value) == 64:
            return value
    raise ValueError("Apprentice dataset manifest is missing its logical SHA-256")


def build_frame_pairs(dataset: ApprenticeDataset) -> np.ndarray:
    """Build the frozen two-frame history without exposing a route-position input."""

    action_count = int(dataset.actions.shape[0])
    if tuple(dataset.frames.shape) != (action_count + 1, 72, 80):
        raise ValueError("Apprentice frames must contain N+1 boundary frames")
    current = dataset.frames[:action_count]
    previous = np.concatenate((current[:1], current[:-1]), axis=0)
    return np.stack((previous, current), axis=1).astype(np.uint8, copy=False)


@dataclass(frozen=True, slots=True)
class Stage0TrainingConfig:
    seed: int = 20_260_742
    learning_rate: float = 1e-3
    max_epochs: int = 2_000
    max_seconds: float = 900.0
    torch_threads: int = 4
    gradient_clip: float = 1.0
    required_exact_epochs: int = 3
    status_interval_epochs: int = 5

    def __post_init__(self) -> None:
        if self.seed < 0:
            raise ValueError("Stage-0 seed cannot be negative")
        if not 0 < self.learning_rate <= 0.1:
            raise ValueError("Stage-0 learning rate must be between zero and 0.1")
        if self.max_epochs < 1 or self.max_seconds <= 0:
            raise ValueError("Stage-0 training limits must be positive")
        if not 1 <= self.torch_threads <= 4:
            raise ValueError("Stage-0 uses between one and four CPU threads")
        if self.gradient_clip <= 0 or self.required_exact_epochs < 1:
            raise ValueError("Stage-0 gradient and confirmation gates must be positive")
        if self.status_interval_epochs < 1:
            raise ValueError("Stage-0 status interval must be positive")

    def public_dict(self) -> dict[str, int | float | str]:
        return {"protocol": STAGE0_PROTOCOL, **asdict(self), "device": "cpu"}


CANONICAL_STAGE0_TRAINING_CONFIG = Stage0TrainingConfig()


@dataclass(frozen=True, slots=True)
class OfflineEvaluation:
    teacher_correct: int
    feedback_correct: int
    action_count: int
    teacher_predictions_sha256: str
    feedback_predictions_sha256: str
    minimum_teacher_margin: float

    @property
    def passed(self) -> bool:
        return self.teacher_correct == self.action_count == self.feedback_correct

    def public_dict(self) -> dict[str, int | float | str | bool]:
        return {**asdict(self), "passed": self.passed}


@dataclass(frozen=True, slots=True)
class Stage0TrainingResult:
    output_directory: Path
    passed: bool
    stop_reason: str
    epochs: int
    elapsed_seconds: float
    best_teacher_correct: int
    best_feedback_correct: int
    action_count: int
    model_sha256: str
    offline: OfflineEvaluation
    reload_offline: OfflineEvaluation


def _configure_torch(seed: int, threads: int) -> Any:
    torch = require_torch()
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    with contextlib.suppress(RuntimeError):
        # PyTorch permits this setting only before inter-op work begins in one process.
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    return torch


def _offline_evaluation(
    model: Any,
    frame_pairs: Any,
    previous_actions: Any,
    targets: Any,
) -> OfflineEvaluation:
    torch = require_torch()
    model.eval()
    with torch.no_grad():
        logits, _ = model(frame_pairs.unsqueeze(0), previous_actions.unsqueeze(0))
        teacher_logits = logits[0]
        teacher_predictions = teacher_logits.argmax(dim=-1)
        correct_logits = teacher_logits.gather(1, targets.unsqueeze(1)).squeeze(1)
        alternatives = teacher_logits.clone()
        alternatives.scatter_(1, targets.unsqueeze(1), float("-inf"))
        minimum_margin = float((correct_logits - alternatives.max(dim=1).values).min().item())

        feedback_predictions: list[int] = []
        recurrent_state = None
        prior = torch.tensor([-1], dtype=torch.long)
        for step in range(int(targets.shape[0])):
            step_logits, recurrent_state = model.step(
                frame_pairs[step].unsqueeze(0), prior, recurrent_state
            )
            prediction = int(step_logits.argmax(dim=-1).item())
            feedback_predictions.append(prediction)
            prior = torch.tensor([prediction], dtype=torch.long)

    teacher_array = teacher_predictions.cpu().numpy().astype(np.uint8, copy=False)
    feedback_array = np.asarray(feedback_predictions, dtype=np.uint8)
    target_array = targets.cpu().numpy().astype(np.uint8, copy=False)
    return OfflineEvaluation(
        teacher_correct=int(np.count_nonzero(teacher_array == target_array)),
        feedback_correct=int(np.count_nonzero(feedback_array == target_array)),
        action_count=int(target_array.shape[0]),
        teacher_predictions_sha256=_sha256_bytes(teacher_array.tobytes()),
        feedback_predictions_sha256=_sha256_bytes(feedback_array.tobytes()),
        minimum_teacher_margin=minimum_margin,
    )


def _maximum_rss_mib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        value *= 1024
    return value / (1024 * 1024)


def _dashboard_html(final_status: Mapping[str, Any] | None = None) -> str:
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Visual Apprentice — Stage 0</title><style>
:root{color-scheme:dark;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
body{max-width:980px;margin:32px auto;padding:0 20px;background:#0c1220;color:#e9eef8}
h1{font-family:system-ui,sans-serif}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.card{background:#172238;border:1px solid #30405f;border-radius:12px;padding:16px}
.value{font-size:1.7rem;color:#71e6ba}.wide{grid-column:1/-1}progress{width:100%;height:22px}
small{color:#a7b6d1}@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style></head><body><h1>Visual Apprentice — Stage 0</h1>
<p>Can a small visual memory turn one lucky 419-action route into a frozen behavior?</p>
<div class="grid"><div class="card"><small>STATE</small>
<div id="state" class="value">loading</div></div>
<div class="card"><small>EPOCH</small><div id="epoch" class="value">—</div></div>
<div class="card"><small>ELAPSED</small><div id="elapsed" class="value">—</div></div>
<div class="card"><small>TEACHER-FORCED</small><div id="teacher" class="value">—</div></div>
<div class="card"><small>FEEDBACK MODE</small><div id="feedback" class="value">—</div></div>
<div class="card"><small>LOSS</small><div id="loss" class="value">—</div></div>
<div class="card wide"><small>EXACT LABELS</small>
<progress id="progress" max="419" value="0"></progress>
<p id="note">The model receives pixels, its previous action, and recurrent memory only.</p>
</div></div><script>const embedded=__EMBEDDED_STATUS__;async function refresh(){try{
const s=embedded??await(await fetch('status.json?'+Date.now())).json();
for(const k of ['state','epoch'])document.getElementById(k).textContent=s[k]??'—';
document.getElementById('elapsed').textContent=(s.elapsed_seconds??0).toFixed(1)+' s';
document.getElementById('teacher').textContent=(s.teacher_correct??0)+' / '+(s.action_count??419);
document.getElementById('feedback').textContent=(s.feedback_correct??0)+' / '+(s.action_count??419);
document.getElementById('loss').textContent=(s.loss??0).toFixed(5);
document.getElementById('progress').value=s.teacher_correct??0;
document.getElementById('note').textContent=s.note??document.getElementById('note').textContent;}catch(e){}
}refresh();if(!embedded)setInterval(refresh,2000);</script></body></html>"""
    embedded = "null" if final_status is None else json.dumps(final_status, separators=(",", ":"))
    return template.replace("__EMBEDDED_STATUS__", embedded)


def _write_training_status(
    output: Path,
    *,
    state: str,
    epoch: int,
    elapsed: float,
    loss: float,
    teacher_correct: int,
    feedback_correct: int,
    action_count: int,
    note: str,
) -> None:
    _atomic_json(
        output / "status.json",
        {
            "schema_version": 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "state": state,
            "epoch": epoch,
            "elapsed_seconds": elapsed,
            "loss": loss,
            "teacher_correct": teacher_correct,
            "feedback_correct": feedback_correct,
            "action_count": action_count,
            "note": note,
        },
    )


def _save_model(output: Path, model: Any, metadata: Mapping[str, Any]) -> str:
    torch = require_torch()
    model_path = output / MODEL_FILENAME
    temporary = output / f"{MODEL_FILENAME}.tmp"
    torch.save(model.state_dict(), temporary)
    os.replace(temporary, model_path)
    model_sha256 = _sha256_file(model_path)
    model_metadata = {
        **metadata,
        "model_sha256": model_sha256,
        "parameter_tensor_sha256": _parameter_tensor_sha256(model),
    }
    _atomic_json(output / MODEL_METADATA_FILENAME, model_metadata)
    return model_sha256


def _load_stage0_model_unsealed(model_directory: Path) -> tuple[Any, dict[str, Any]]:
    torch = require_torch()
    directory = model_directory.expanduser().resolve()
    metadata = _read_canonical_json(
        directory / MODEL_METADATA_FILENAME,
        label="Stage-0 model metadata",
    )
    if metadata.get("protocol") != STAGE0_PROTOCOL:
        raise ValueError("Stage-0 model uses a different protocol")
    if metadata.get("architecture") != APPRENTICE_ARCHITECTURE:
        raise ValueError("Stage-0 model uses a different architecture")
    config = ApprenticeModelConfig()
    if metadata.get("architecture_sha256") != config.sha256:
        raise ValueError("Stage-0 architecture hash does not match")
    model_path = directory / MODEL_FILENAME
    if _sha256_file(model_path) != metadata.get("model_sha256"):
        raise ValueError("Stage-0 model file hash does not match its metadata")
    model = build_apprentice_policy(config)
    state_dict = torch.load(model_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict, strict=True)
    if _parameter_tensor_sha256(model) != metadata.get("parameter_tensor_sha256"):
        raise ValueError("Stage-0 parameter tensor hash does not match its metadata")
    model.eval()
    return model, metadata


def _offline_record_passes(value: object, *, action_count: int) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(
        value.get("passed") is True
        and value.get("action_count") == action_count
        and value.get("teacher_correct") == action_count
        and value.get("feedback_correct") == action_count
        and isinstance(value.get("teacher_predictions_sha256"), str)
        and len(value["teacher_predictions_sha256"]) == 64
        and isinstance(value.get("feedback_predictions_sha256"), str)
        and len(value["feedback_predictions_sha256"]) == 64
    )


def verify_stage0_training_bundle(path: Path) -> Mapping[str, Any]:
    """Require the canonical offline gate and every sealed training artifact."""

    directory = path.expanduser().resolve()
    receipt = verify_apprentice_bundle(
        directory,
        expected_kind=STAGE0_TRAINING_BUNDLE_KIND,
        expected_subject_protocol=STAGE0_PROTOCOL,
    )
    required_files = {
        ".gitignore",
        "events.jsonl",
        "index.html",
        "manifest.json",
        "metrics.csv",
        MODEL_FILENAME,
        MODEL_METADATA_FILENAME,
        "status.json",
        "summary.json",
    }
    if set(receipt["files"]) != required_files:
        raise ValueError("Stage-0 training bundle file set is not canonical")
    manifest = _read_canonical_json(directory / "manifest.json", label="Training manifest")
    summary = _read_canonical_json(directory / "summary.json", label="Training summary")
    metadata = _read_canonical_json(
        directory / MODEL_METADATA_FILENAME,
        label="Stage-0 model metadata",
    )
    status = _read_canonical_json(directory / "status.json", label="Training status")
    action_count = STAGE0_Q1_ACTION_COUNT
    if (
        manifest.get("protocol") != STAGE0_PROTOCOL
        or manifest.get("configuration")
        != CANONICAL_STAGE0_TRAINING_CONFIG.public_dict()
        or manifest.get("dataset_action_count") != action_count
        or manifest.get("parameter_count") != EXPECTED_PARAMETER_COUNT
        or not isinstance(manifest.get("dataset_sha256"), str)
    ):
        raise ValueError("Stage-0 training manifest is outside the frozen protocol")
    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("worktree_dirty") is not False:
        raise ValueError("Stage-0 training source provenance is not clean")
    if (
        summary.get("state") != "passed"
        or summary.get("stop_reason") != "offline_overfit_passed"
        or summary.get("action_count") != action_count
        or summary.get("reload_identical") is not True
        or status.get("state") != "passed"
        or not _offline_record_passes(summary.get("offline"), action_count=action_count)
        or not _offline_record_passes(
            summary.get("reload_offline"), action_count=action_count
        )
    ):
        raise ValueError("Stage-0 offline or frozen-reload gate did not pass")
    if (
        metadata.get("dataset_sha256") != manifest["dataset_sha256"]
        or metadata.get("model_sha256") != summary.get("model_sha256")
        or metadata.get("offline_evaluation") != summary.get("offline")
    ):
        raise ValueError("Stage-0 model, dataset, and summary identities disagree")
    _, loaded_metadata = _load_stage0_model_unsealed(directory)
    if loaded_metadata != metadata:
        raise ValueError("Stage-0 reloaded model metadata changed")
    identities = receipt["identities"]
    expected_identities = {
        "action_count": action_count,
        "dataset_sha256": manifest["dataset_sha256"],
        "model_sha256": metadata["model_sha256"],
        "parameter_tensor_sha256": metadata["parameter_tensor_sha256"],
        "source_commit": source.get("git_commit"),
    }
    if identities != expected_identities:
        raise ValueError("Stage-0 training receipt identities disagree")
    return receipt


def load_stage0_model(model_directory: Path) -> tuple[Any, dict[str, Any]]:
    """Load only a sealed model whose complete offline and reload gates passed."""

    verify_stage0_training_bundle(model_directory)
    return _load_stage0_model_unsealed(model_directory)


def train_stage0_overfit(
    dataset_path: Path,
    output_path: Path,
    *,
    config: Stage0TrainingConfig | None = None,
) -> Stage0TrainingResult:
    """Deliberately overfit one verified route and prove save/reload identity."""

    training = config or Stage0TrainingConfig()
    if training != CANONICAL_STAGE0_TRAINING_CONFIG:
        raise ValueError("Official Stage-0 training requires the frozen canonical configuration")
    source = detect_source_provenance()
    if source.git_commit is None or source.worktree_dirty is not False:
        raise ValueError("Official Stage-0 training requires one committed, clean implementation")
    output = _private_output_directory(output_path)
    if output.exists():
        raise ValueError("Stage-0 output directory already exists")
    output.mkdir(parents=True)
    (output / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (output / "events.jsonl").touch()
    _atomic_bytes(output / "index.html", _dashboard_html().encode("utf-8"))

    verified_manifest = verify_apprentice_dataset(dataset_path)
    dataset = load_apprentice_dataset(dataset_path)
    dataset_sha256 = _dataset_identity(verified_manifest)
    action_count = int(dataset.actions.shape[0])
    if action_count != STAGE0_Q1_ACTION_COUNT:
        raise ValueError("Stage-0 dataset does not have the frozen 419-action horizon")
    if not bool(dataset.episode_starts[0]) or np.count_nonzero(dataset.episode_starts) != 1:
        raise ValueError("Stage-0 requires exactly one episode start at action zero")
    if int(dataset.previous_actions[0]) != -1:
        raise ValueError("Stage-0 first action must use the no-previous-action sentinel")

    torch = _configure_torch(training.seed, training.torch_threads)
    frame_pairs_np = build_frame_pairs(dataset)
    frame_pairs = torch.from_numpy(frame_pairs_np)
    previous_actions = torch.from_numpy(dataset.previous_actions.astype(np.int64, copy=False))
    targets = torch.from_numpy(dataset.actions.astype(np.int64, copy=False))
    model_config = ApprenticeModelConfig()
    model = build_apprentice_policy(model_config).to("cpu")
    optimizer = torch.optim.Adam(model.parameters(), lr=training.learning_rate)
    criterion = torch.nn.CrossEntropyLoss()

    run_manifest = {
        "schema_version": 1,
        "protocol": STAGE0_PROTOCOL,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": dataset_sha256,
        "dataset_action_count": action_count,
        "configuration": training.public_dict(),
        "architecture": APPRENTICE_ARCHITECTURE,
        "architecture_sha256": model_config.sha256,
        "parameter_count": EXPECTED_PARAMETER_COUNT,
        "source": source.public_dict(),
        "actor_inputs": ["two_processed_pixel_frames", "previous_action", "recurrent_state"],
        "actor_forbidden_inputs": [
            "ram",
            "map_id",
            "coordinates",
            "milestone",
            "checkpoint_id",
            "route_position",
        ],
        "training_claim": "single-trajectory deliberate overfit only",
    }
    _atomic_json(output / "manifest.json", run_manifest)
    _append_event(output / "events.jsonl", "training_started", **run_manifest)

    metrics_path = output / "metrics.csv"
    started = time.monotonic()
    best_teacher = 0
    best_feedback = 0
    exact_streak = 0
    epoch = 0
    loss_value = float("nan")
    last_offline = OfflineEvaluation(0, 0, action_count, "", "", float("-inf"))
    stop_reason = "epoch_limit"
    _write_training_status(
        output,
        state="training",
        epoch=0,
        elapsed=0,
        loss=0,
        teacher_correct=0,
        feedback_correct=0,
        action_count=action_count,
        note="The first full-sequence update is starting.",
    )

    with metrics_path.open("w", encoding="utf-8", newline="") as metrics_file:
        writer = csv.writer(metrics_file)
        writer.writerow(
            [
                "epoch",
                "elapsed_seconds",
                "loss",
                "teacher_correct",
                "feedback_correct",
                "minimum_teacher_margin",
                "maximum_rss_mib",
            ]
        )
        for epoch in range(1, training.max_epochs + 1):
            model.train()
            optimizer.zero_grad(set_to_none=True)
            logits, _ = model(frame_pairs.unsqueeze(0), previous_actions.unsqueeze(0))
            loss = criterion(logits[0], targets)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), training.gradient_clip)
            optimizer.step()
            loss_value = float(loss.detach().item())

            model.eval()
            with torch.no_grad():
                check_logits, _ = model(
                    frame_pairs.unsqueeze(0), previous_actions.unsqueeze(0)
                )
                teacher_correct = int(
                    (check_logits[0].argmax(dim=-1) == targets).sum().item()
                )
            feedback_due = (
                teacher_correct == action_count
                or epoch == 1
                or epoch % training.status_interval_epochs == 0
            )
            if feedback_due:
                last_offline = _offline_evaluation(
                    model, frame_pairs, previous_actions, targets
                )
            else:
                last_offline = OfflineEvaluation(
                    teacher_correct=teacher_correct,
                    feedback_correct=last_offline.feedback_correct,
                    action_count=action_count,
                    teacher_predictions_sha256=last_offline.teacher_predictions_sha256,
                    feedback_predictions_sha256=last_offline.feedback_predictions_sha256,
                    minimum_teacher_margin=last_offline.minimum_teacher_margin,
                )
            best_teacher = max(best_teacher, last_offline.teacher_correct)
            best_feedback = max(best_feedback, last_offline.feedback_correct)
            exact_streak = exact_streak + 1 if last_offline.passed else 0
            elapsed = time.monotonic() - started
            writer.writerow(
                [
                    epoch,
                    f"{elapsed:.6f}",
                    f"{loss_value:.9f}",
                    last_offline.teacher_correct,
                    last_offline.feedback_correct,
                    f"{last_offline.minimum_teacher_margin:.9f}",
                    f"{_maximum_rss_mib():.3f}",
                ]
            )
            metrics_file.flush()

            if epoch == 1 or epoch % training.status_interval_epochs == 0 or last_offline.passed:
                _write_training_status(
                    output,
                    state="training",
                    epoch=epoch,
                    elapsed=elapsed,
                    loss=loss_value,
                    teacher_correct=last_offline.teacher_correct,
                    feedback_correct=last_offline.feedback_correct,
                    action_count=action_count,
                    note=(
                        f"Exact confirmation {exact_streak}/{training.required_exact_epochs}."
                        if last_offline.passed
                        else "Still fitting the one verified trajectory."
                    ),
                )
            if exact_streak >= training.required_exact_epochs:
                stop_reason = "offline_overfit_passed"
                break
            if elapsed >= training.max_seconds:
                stop_reason = "time_limit"
                break

    elapsed = time.monotonic() - started
    final_offline = _offline_evaluation(model, frame_pairs, previous_actions, targets)
    model_sha256 = _save_model(
        output,
        model,
        {
            "schema_version": 1,
            "protocol": STAGE0_PROTOCOL,
            "architecture": APPRENTICE_ARCHITECTURE,
            "architecture_sha256": model_config.sha256,
            "parameter_count": EXPECTED_PARAMETER_COUNT,
            "dataset_sha256": dataset_sha256,
            "seed": training.seed,
            "epochs": epoch,
            "offline_evaluation": final_offline.public_dict(),
        },
    )
    reloaded, _ = _load_stage0_model_unsealed(output)
    reload_offline = _offline_evaluation(
        reloaded, frame_pairs, previous_actions, targets
    )
    passed = (
        stop_reason == "offline_overfit_passed"
        and final_offline.passed
        and reload_offline == final_offline
    )
    summary = {
        "schema_version": 1,
        "protocol": STAGE0_PROTOCOL,
        "state": "passed" if passed else "failed",
        "stop_reason": stop_reason,
        "epochs": epoch,
        "elapsed_seconds": elapsed,
        "action_count": action_count,
        "best_teacher_correct": best_teacher,
        "best_feedback_correct": best_feedback,
        "offline": final_offline.public_dict(),
        "reload_offline": reload_offline.public_dict(),
        "reload_identical": reload_offline == final_offline,
        "model_sha256": model_sha256,
        "maximum_rss_mib": _maximum_rss_mib(),
        "claim_boundary": "one training trajectory; no recovery or generalization claim",
    }
    _atomic_json(output / "summary.json", summary)
    _append_event(output / "events.jsonl", "training_finished", **summary)
    _write_training_status(
        output,
        state="passed" if passed else "failed",
        epoch=epoch,
        elapsed=elapsed,
        loss=loss_value,
        teacher_correct=final_offline.teacher_correct,
        feedback_correct=final_offline.feedback_correct,
        action_count=action_count,
        note=(
            "Offline memorization and frozen reload passed. Live emulation is the next gate."
            if passed
            else "Offline gate failed; do not describe this checkpoint as a learned policy."
        ),
    )
    final_status = _read_canonical_json(
        output / "status.json",
        label="Training status",
    )
    _atomic_bytes(
        output / "index.html",
        _dashboard_html(final_status).encode("utf-8"),
    )
    if passed:
        seal_apprentice_bundle(
            output,
            kind=STAGE0_TRAINING_BUNDLE_KIND,
            subject_protocol=STAGE0_PROTOCOL,
            identities={
                "action_count": action_count,
                "dataset_sha256": dataset_sha256,
                "model_sha256": model_sha256,
                "parameter_tensor_sha256": _parameter_tensor_sha256(model),
                "source_commit": source.git_commit,
            },
        )
        verify_stage0_training_bundle(output)
    return Stage0TrainingResult(
        output_directory=output,
        passed=passed,
        stop_reason=stop_reason,
        epochs=epoch,
        elapsed_seconds=elapsed,
        best_teacher_correct=best_teacher,
        best_feedback_correct=best_feedback,
        action_count=action_count,
        model_sha256=model_sha256,
        offline=final_offline,
        reload_offline=reload_offline,
    )


@dataclass(frozen=True, slots=True)
class Stage0RolloutResult:
    output_directory: Path
    passed: bool
    stop_reason: str
    actions: int
    matched_teacher_prefix: int
    exact_teacher_actions: bool
    final_milestone: str
    model_sha256: str
    elapsed_seconds: float


def evaluate_stage0_policy(
    rom_path: Path,
    model_directory: Path,
    output_path: Path,
    *,
    max_actions: int = 1_000,
    dataset_path: Path,
) -> Stage0RolloutResult:
    """Run one frozen, clean-power-on exam with no snapshots, rewards, or updates."""

    if max_actions != 1_000:
        raise ValueError("Official Stage-0 evaluation requires the frozen 1,000-action ceiling")
    source = detect_source_provenance()
    if source.git_commit is None or source.worktree_dirty is not False:
        raise ValueError("Official Stage-0 evaluation requires one committed, clean implementation")
    training_receipt = verify_stage0_training_bundle(model_directory)
    dataset_manifest = verify_apprentice_dataset(dataset_path)
    dataset_sha256 = _dataset_identity(dataset_manifest)
    fingerprint = verify_rom(rom_path.expanduser().resolve())
    output = _private_output_directory(output_path)
    if output.exists():
        raise ValueError("Stage-0 evaluation output directory already exists")
    output.mkdir(parents=True)
    (output / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (output / "events.jsonl").touch()
    (output / "visuals").mkdir()

    torch = _configure_torch(0, 1)
    model, model_metadata = load_stage0_model(model_directory)
    if dataset_sha256 != model_metadata.get("dataset_sha256"):
        raise ValueError("Evaluation dataset does not match the model's training dataset")
    teacher_actions = load_apprentice_dataset(dataset_path).actions

    manifest = {
        "schema_version": 1,
        "protocol": STAGE0_PROTOCOL,
        "created_at": datetime.now(UTC).isoformat(),
        "model_sha256": model_metadata["model_sha256"],
        "dataset_sha256": dataset_sha256,
        "max_actions": max_actions,
        "policy": "deterministic_argmax",
        "start": "clean_power_on",
        "recurrent_state": "zero",
        "updates": False,
        "snapshots": False,
        "rewards": False,
        "retries": False,
        "interventions": False,
        "actor_inputs": ["two_processed_pixel_frames", "previous_action", "recurrent_state"],
        "source": source.public_dict(),
        "runtime": {
            "python": platform.python_version(),
            "pyboy": version("pyboy"),
            "torch": str(torch.__version__),
        },
        "rom": fingerprint.public_dict(),
        "training_bundle_sha256": training_receipt["bundle_sha256"],
    }
    _atomic_json(output / "manifest.json", manifest)
    _append_event(output / "events.jsonl", "evaluation_started", **manifest)

    selected: list[int] = []
    milestone_rows: list[dict[str, object]] = []
    recurrent_state = None
    prior_action = -1
    previous_frame: np.ndarray | None = None
    progress = MilestoneProgress("power_on", 0, "Power-on")
    stop_reason = "action_limit"
    started = time.monotonic()
    with (output / "actions.csv").open("w", encoding="utf-8", newline="") as trace_file:
        writer = csv.writer(trace_file)
        writer.writerow(["action", "button", "milestone_after_action"])
        with PokemonRedEmulator(rom_path) as emulator:
            actor = PixelsOnlyActor(emulator)
            reader = PokemonRedStateReader(emulator)
            for action_number in range(1, max_actions + 1):
                pixels = actor.observe()
                current_frame = preprocess_apprentice_frame(pixels)
                if previous_frame is None:
                    previous_frame = current_frame
                pair = np.stack((previous_frame, current_frame), axis=0)
                pair_tensor = torch.from_numpy(pair).unsqueeze(0)
                prior_tensor = torch.tensor([prior_action], dtype=torch.long)
                with torch.no_grad():
                    logits, recurrent_state = model.step(
                        pair_tensor, prior_tensor, recurrent_state
                    )
                action_index = int(logits.argmax(dim=-1).item())
                selected.append(action_index)
                action = BlindAction(
                    BLIND_ACTIONS[action_index],
                    ACTION_HOLD_FRAMES,
                    ACTION_RELEASE_FRAMES,
                )
                alive = actor.act(action)
                state = reader.read()
                prior_progress = progress
                progress = milestone_progress_for_state(state, inherited=progress)
                writer.writerow([action_number, action.button, progress.key])
                trace_file.flush()
                if progress.index > prior_progress.index:
                    image_name = f"{action_number:04d}-{progress.key}.png"
                    Image.fromarray(actor.observe()).save(output / "visuals" / image_name)
                    milestone_rows.append(
                        {
                            "action": action_number,
                            "milestone": progress.key,
                            "image": f"visuals/{image_name}",
                        }
                    )
                    _append_event(
                        output / "events.jsonl",
                        "milestone_reached",
                        action=action_number,
                        milestone=progress.key,
                    )
                previous_frame = current_frame
                prior_action = action_index
                if progress.key == "left_home":
                    stop_reason = "left_home_reached"
                    break
                if not alive:
                    stop_reason = "emulator_stopped"
                    break

    elapsed = time.monotonic() - started
    selected_array = np.asarray(selected, dtype=np.uint8)
    common = min(len(selected_array), len(teacher_actions))
    matched_prefix = 0
    for index in range(common):
        if int(selected_array[index]) != int(teacher_actions[index]):
            break
        matched_prefix += 1
    exact_teacher_actions = bool(
        len(selected_array) == len(teacher_actions)
        and np.array_equal(selected_array, teacher_actions)
    )
    passed = stop_reason == "left_home_reached"
    summary = {
        "schema_version": 1,
        "protocol": STAGE0_PROTOCOL,
        "passed": passed,
        "stop_reason": stop_reason,
        "actions": len(selected),
        "max_actions": max_actions,
        "matched_teacher_prefix": matched_prefix,
        "exact_teacher_actions": exact_teacher_actions,
        "selected_actions_sha256": _sha256_bytes(selected_array.tobytes()),
        "final_milestone": progress.key,
        "elapsed_seconds": elapsed,
        "actions_per_second": len(selected) / max(elapsed, 1e-9),
        "milestones": milestone_rows,
        "model_sha256": model_metadata["model_sha256"],
        "frozen_exam": {
            "clean_power_on": True,
            "zero_recurrent_state": True,
            "snapshots": False,
            "rewards": False,
            "updates": False,
            "retries": False,
            "interventions": False,
        },
        "claim_boundary": "single training trajectory; no recovery or generalization claim",
    }
    _atomic_json(output / "summary.json", summary)
    _atomic_json(
        output / "eval_attempts.json",
        {"schema_version": 1, "attempts": [summary]},
    )
    _append_event(output / "events.jsonl", "evaluation_finished", **summary)
    if passed:
        seal_apprentice_bundle(
            output,
            kind=STAGE0_EVALUATION_BUNDLE_KIND,
            subject_protocol=STAGE0_PROTOCOL,
            identities={
                "actions": len(selected),
                "dataset_sha256": dataset_sha256,
                "model_sha256": model_metadata["model_sha256"],
                "source_commit": source.git_commit,
                "training_bundle_sha256": training_receipt["bundle_sha256"],
            },
        )
        verify_stage0_evaluation_bundle(output)
    return Stage0RolloutResult(
        output_directory=output,
        passed=passed,
        stop_reason=stop_reason,
        actions=len(selected),
        matched_teacher_prefix=matched_prefix,
        exact_teacher_actions=exact_teacher_actions,
        final_milestone=progress.key,
        model_sha256=str(model_metadata["model_sha256"]),
        elapsed_seconds=elapsed,
    )


def verify_stage0_evaluation_bundle(path: Path) -> Mapping[str, Any]:
    """Verify the one-attempt clean-power-on result and its complete file closure."""

    directory = path.expanduser().resolve()
    receipt = verify_apprentice_bundle(
        directory,
        expected_kind=STAGE0_EVALUATION_BUNDLE_KIND,
        expected_subject_protocol=STAGE0_PROTOCOL,
    )
    files = set(receipt["files"])
    required = {
        ".gitignore",
        "actions.csv",
        "eval_attempts.json",
        "events.jsonl",
        "manifest.json",
        "summary.json",
    }
    if not required.issubset(files) or any(
        name not in required and not (name.startswith("visuals/") and name.endswith(".png"))
        for name in files
    ):
        raise ValueError("Stage-0 evaluation bundle file set is not canonical")
    manifest = _read_canonical_json(directory / "manifest.json", label="Evaluation manifest")
    summary = _read_canonical_json(directory / "summary.json", label="Evaluation summary")
    attempts = _read_canonical_json(
        directory / "eval_attempts.json",
        label="Evaluation attempt ledger",
    )
    if (
        manifest.get("protocol") != STAGE0_PROTOCOL
        or manifest.get("max_actions") != 1_000
        or manifest.get("policy") != "deterministic_argmax"
        or manifest.get("start") != "clean_power_on"
        or not isinstance(manifest.get("dataset_sha256"), str)
        or not isinstance(manifest.get("model_sha256"), str)
        or not isinstance(manifest.get("training_bundle_sha256"), str)
    ):
        raise ValueError("Stage-0 evaluation manifest is outside the frozen protocol")
    source = manifest.get("source")
    runtime = manifest.get("runtime")
    rom = manifest.get("rom")
    if (
        not isinstance(source, dict)
        or source.get("worktree_dirty") is not False
        or not isinstance(runtime, dict)
        or set(runtime) != {"python", "pyboy", "torch"}
        or not isinstance(rom, dict)
        or "filename" in rom
    ):
        raise ValueError("Stage-0 evaluation provenance is incomplete or unsafe")
    frozen = summary.get("frozen_exam")
    if (
        summary.get("passed") is not True
        or summary.get("stop_reason") != "left_home_reached"
        or summary.get("final_milestone") != "left_home"
        or not isinstance(summary.get("actions"), int)
        or not 1 <= summary["actions"] <= 1_000
        or summary.get("max_actions") != 1_000
        or not isinstance(frozen, dict)
        or frozen
        != {
            "clean_power_on": True,
            "zero_recurrent_state": True,
            "snapshots": False,
            "rewards": False,
            "updates": False,
            "retries": False,
            "interventions": False,
        }
    ):
        raise ValueError("Stage-0 clean-power-on gate did not pass")
    if attempts != {"schema_version": 1, "attempts": [summary]}:
        raise ValueError("Stage-0 attempt ledger disagrees with its summary")
    with (directory / "actions.csv").open(encoding="utf-8", newline="") as action_file:
        rows = list(csv.reader(action_file))
    if not rows or rows[0] != ["action", "button", "milestone_after_action"]:
        raise ValueError("Stage-0 action ledger header is invalid")
    action_rows = rows[1:]
    if len(action_rows) != summary["actions"] or any(
        len(row) != 3
        or row[0] != str(index)
        or row[1] not in BLIND_ACTIONS
        for index, row in enumerate(action_rows, start=1)
    ):
        raise ValueError("Stage-0 action ledger sequence is invalid")
    action_indices = np.asarray(
        [BLIND_ACTIONS.index(row[1]) for row in action_rows],
        dtype=np.uint8,
    )
    if (
        summary.get("model_sha256") != manifest["model_sha256"]
        or summary.get("selected_actions_sha256")
        != _sha256_bytes(action_indices.tobytes())
    ):
        raise ValueError("Stage-0 evaluation model or action identity disagrees")
    identities = receipt["identities"]
    expected_identities = {
        "actions": summary["actions"],
        "dataset_sha256": manifest["dataset_sha256"],
        "model_sha256": manifest["model_sha256"],
        "source_commit": source.get("git_commit"),
        "training_bundle_sha256": manifest["training_bundle_sha256"],
    }
    if identities != expected_identities:
        raise ValueError("Stage-0 evaluation receipt identities disagree")
    for milestone in summary.get("milestones", []):
        if not isinstance(milestone, dict) or milestone.get("image") not in files:
            raise ValueError("Stage-0 milestone image ledger is incomplete")
    return receipt


def remove_failed_stage0_output(path: Path) -> None:
    """Delete only an explicitly failed, private Stage-0 bundle during test cleanup."""

    resolved = _private_output_directory(path)
    if resolved.is_dir() and not (resolved / "SUCCESS").exists():
        shutil.rmtree(resolved)
