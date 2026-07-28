from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import pokemon_red_ai.apprentice_qualification as qualification_module
import pokemon_red_ai.apprentice_stage0 as stage0_module
from pokemon_red_ai.apprentice_data import ApprenticeDataset, preprocess_apprentice_frame
from pokemon_red_ai.apprentice_qualification import (
    qualify_stage0_composite,
    qualify_stage0_data,
    verify_stage0_composite,
)
from pokemon_red_ai.apprentice_stage0 import (
    Stage0TrainingConfig,
    evaluate_stage0_policy,
    load_stage0_model,
    train_stage0_overfit,
    verify_stage0_evaluation_bundle,
    verify_stage0_training_bundle,
)
from pokemon_red_ai.expedition import MilestoneProgress
from pokemon_red_ai.rom import RomFingerprint


def _clean_source() -> SimpleNamespace:
    return SimpleNamespace(
        git_commit="a" * 40,
        worktree_dirty=False,
        public_dict=lambda: {"git_commit": "a" * 40, "worktree_dirty": False},
    )


def _screen(value: int = 0) -> np.ndarray:
    return np.full((144, 160, 3), value, dtype=np.uint8)


def test_stage0_training_live_rollout_and_composite_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("torch")
    action_count = 8
    frames = np.stack(
        [preprocess_apprentice_frame(_screen(index)) for index in range(action_count + 1)]
    )
    actions = np.zeros(action_count, dtype=np.uint8)
    previous = np.asarray([-1, *([0] * (action_count - 1))], dtype=np.int16)
    starts = np.asarray([True, *([False] * (action_count - 1))], dtype=np.bool_)
    dataset_sha256 = "d" * 64
    dataset_manifest = {
        "dataset_sha256": dataset_sha256,
        "capture_id": "1" * 32,
        "implementation": _clean_source().public_dict(),
    }
    dataset = ApprenticeDataset(frames, actions, previous, starts, dataset_manifest)
    training_config = Stage0TrainingConfig(
        seed=123,
        learning_rate=1e-2,
        max_epochs=100,
        max_seconds=30,
        torch_threads=1,
        gradient_clip=1,
        required_exact_epochs=1,
        status_interval_epochs=2,
    )
    monkeypatch.setattr(stage0_module, "STAGE0_Q1_ACTION_COUNT", action_count)
    monkeypatch.setattr(stage0_module, "CANONICAL_STAGE0_TRAINING_CONFIG", training_config)
    monkeypatch.setattr(stage0_module, "detect_source_provenance", _clean_source)
    monkeypatch.setattr(
        stage0_module,
        "verify_apprentice_dataset",
        lambda _path: dataset_manifest,
    )
    monkeypatch.setattr(
        stage0_module,
        "load_apprentice_dataset",
        lambda _path: dataset,
    )

    training_output = tmp_path / "training"
    result = train_stage0_overfit(
        tmp_path / "dataset-a",
        training_output,
        config=training_config,
    )

    assert result.passed
    assert result.offline.teacher_correct == action_count
    assert result.offline.feedback_correct == action_count
    training_receipt = verify_stage0_training_bundle(training_output)
    model, metadata = load_stage0_model(training_output)
    assert model is not None
    assert metadata["dataset_sha256"] == dataset_sha256

    class FakeEmulator:
        instances: list[FakeEmulator] = []

        def __init__(self, _rom_path: Path) -> None:
            self.step = 0
            self.actions: list[tuple[str, int, int]] = []
            self.__class__.instances.append(self)

        def __enter__(self) -> FakeEmulator:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def screen_rgb(self) -> np.ndarray:
            return _screen(self.step)

        def press(self, button: str, *, hold_frames: int, release_frames: int) -> bool:
            self.actions.append((button, hold_frames, release_frames))
            self.step += 1
            return True

        def tick(self, frames: int, *, render_last: bool) -> bool:
            self.actions.append(("noop", frames // 2, frames - frames // 2))
            assert render_last is True
            self.step += 1
            return True

    class FakeReader:
        def __init__(self, emulator: FakeEmulator) -> None:
            self.emulator = emulator

        def read(self) -> SimpleNamespace:
            return SimpleNamespace(step=self.emulator.step)

    def fake_progress(
        state: SimpleNamespace,
        *,
        inherited: MilestoneProgress | None = None,
    ) -> MilestoneProgress:
        if state.step >= 2:
            return MilestoneProgress("left_home", 3, "Stepped outside")
        return inherited or MilestoneProgress("power_on", 0, "Power-on")

    fingerprint = RomFingerprint(
        filename="private.gb",
        title="POKEMON RED",
        size_bytes=1,
        sha1="b" * 40,
        sha256="c" * 64,
    )
    monkeypatch.setattr(stage0_module, "PokemonRedEmulator", FakeEmulator)
    monkeypatch.setattr(stage0_module, "PokemonRedStateReader", FakeReader)
    monkeypatch.setattr(stage0_module, "milestone_progress_for_state", fake_progress)
    monkeypatch.setattr(stage0_module, "verify_rom", lambda _path: fingerprint)

    evaluation_output = tmp_path / "evaluation"
    rollout = evaluate_stage0_policy(
        tmp_path / "private.gb",
        training_output,
        evaluation_output,
        dataset_path=tmp_path / "dataset-a",
    )

    assert rollout.passed
    assert rollout.actions == 2
    assert FakeEmulator.instances[-1].actions == [("up", 8, 12), ("up", 8, 12)]
    evaluation_receipt = verify_stage0_evaluation_bundle(evaluation_output)
    assert (
        evaluation_receipt["identities"]["training_bundle_sha256"]
        == training_receipt["bundle_sha256"]
    )
    with pytest.raises(ValueError, match="1,000-action ceiling"):
        evaluate_stage0_policy(
            tmp_path / "private.gb",
            training_output,
            tmp_path / "too-long",
            max_actions=1_001,
            dataset_path=tmp_path / "dataset-a",
        )

    first = tmp_path / "dataset-a"
    second = tmp_path / "dataset-b"
    first.mkdir()
    second.mkdir()
    (first / "manifest.json").write_text("{}\n", encoding="utf-8")
    (second / "manifest.json").write_text("{}\n", encoding="utf-8")
    first_manifest = {**dataset_manifest, "capture_id": "1" * 32}
    second_manifest = {**dataset_manifest, "capture_id": "2" * 32}
    monkeypatch.setattr(qualification_module, "STAGE0_Q1_ACTION_COUNT", action_count)
    monkeypatch.setattr(qualification_module, "detect_source_provenance", _clean_source)
    monkeypatch.setattr(
        qualification_module,
        "verify_apprentice_dataset",
        lambda path: first_manifest if path.resolve() == first.resolve() else second_manifest,
    )
    data_output = tmp_path / "data-qualification"
    data_receipt = qualify_stage0_data(first, second, data_output)
    assert data_receipt["identities"]["dataset_sha256"] == dataset_sha256

    composite_output = tmp_path / "composite"
    composite = qualify_stage0_composite(
        data_output,
        training_output,
        evaluation_output,
        composite_output,
    )
    assert composite["identities"]["model_sha256"] == result.model_sha256
    verify_stage0_composite(composite_output)

    metrics = training_output / "metrics.csv"
    metrics.write_text(metrics.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="file set or hash"):
        load_stage0_model(training_output)


def test_unsealed_model_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "failed-training"
    directory.mkdir()
    (directory / "model.json").write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(ValueError, match="SUCCESS"):
        load_stage0_model(directory)

