from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

try:  # Stage 0 is optional; the emulator and archive tools must work without PyTorch.
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - exercised by the base, torch-free installation.
    torch = None
    nn = None


APPRENTICE_MODEL_SCHEMA = 1
APPRENTICE_ARCHITECTURE = "visual-apprentice-cnn-lstm-v1"
EXPECTED_PARAMETER_COUNT = 468_312
TORCH_INSTALL_HELP = (
    "Visual Apprentice training requires the optional PyTorch dependency. "
    "Install it with: python -m pip install -e '.[apprentice]'"
)


@dataclass(frozen=True, slots=True)
class ApprenticeModelConfig:
    observation_height: int = 72
    observation_width: int = 80
    frame_history: int = 2
    action_count: int = 8
    feature_units: int = 256
    recurrent_units: int = 128

    def __post_init__(self) -> None:
        expected = (72, 80, 2, 8, 256, 128)
        actual = (
            self.observation_height,
            self.observation_width,
            self.frame_history,
            self.action_count,
            self.feature_units,
            self.recurrent_units,
        )
        if actual != expected:
            raise ValueError(
                "Stage-0 architecture is frozen at 2x72x80 pixels, 8 actions, "
                "256 visual features, and 128 recurrent units"
            )

    def public_dict(self) -> dict[str, int | str]:
        return {
            "schema_version": APPRENTICE_MODEL_SCHEMA,
            "architecture": APPRENTICE_ARCHITECTURE,
            **asdict(self),
        }

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.public_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def require_torch() -> Any:
    if torch is None or nn is None:
        raise RuntimeError(TORCH_INSTALL_HELP)
    return torch


if nn is not None:

    class ApprenticePolicy(nn.Module):
        """Small pixels-only recurrent policy used by the Stage-0 apprenticeship.

        The policy receives only two processed screen frames, the previous controller action,
        and its own recurrent state. The value function is deliberately deferred until the PPO
        stages so this first test isolates behavioral cloning.
        """

        def __init__(self, config: ApprenticeModelConfig | None = None) -> None:
            super().__init__()
            self.config = config or ApprenticeModelConfig()
            self.encoder = nn.Sequential(
                nn.Conv2d(2, 16, kernel_size=8, stride=4),
                nn.ReLU(),
                nn.Conv2d(16, 32, kernel_size=4, stride=2),
                nn.ReLU(),
                nn.Conv2d(32, 32, kernel_size=3, stride=1),
                nn.ReLU(),
                nn.Flatten(),
                nn.Linear(32 * 5 * 6, self.config.feature_units),
                nn.ReLU(),
            )
            recurrent_inputs = self.config.feature_units + self.config.action_count
            self.recurrent = nn.LSTM(
                recurrent_inputs,
                self.config.recurrent_units,
                num_layers=1,
                batch_first=True,
            )
            self.policy_head = nn.Linear(
                self.config.recurrent_units,
                self.config.action_count,
            )

            actual_parameters = sum(parameter.numel() for parameter in self.parameters())
            if actual_parameters != EXPECTED_PARAMETER_COUNT:
                raise RuntimeError(
                    "Visual Apprentice parameter count changed without a schema bump: "
                    f"{actual_parameters:,} != {EXPECTED_PARAMETER_COUNT:,}"
                )

        def forward(
            self,
            frame_pairs: Any,
            previous_actions: Any,
            recurrent_state: tuple[Any, Any] | None = None,
        ) -> tuple[Any, tuple[Any, Any]]:
            """Return logits for ``[batch, time, 2, 72, 80]`` observations."""

            if frame_pairs.ndim != 5:
                raise ValueError("frame_pairs must have [batch, time, history, height, width]")
            batch, steps, history, height, width = frame_pairs.shape
            expected_shape = (
                self.config.frame_history,
                self.config.observation_height,
                self.config.observation_width,
            )
            if (history, height, width) != expected_shape:
                raise ValueError(f"frame_pairs must end in {expected_shape}")
            if tuple(previous_actions.shape) != (batch, steps):
                raise ValueError("previous_actions must have [batch, time]")

            pixels = frame_pairs.reshape(batch * steps, history, height, width)
            visual = self.encoder(pixels.float().div(255.0)).reshape(batch, steps, -1)
            previous = previous_actions.to(dtype=torch.long)
            valid = (previous >= 0) & (previous < self.config.action_count)
            one_hot = torch.zeros(
                batch,
                steps,
                self.config.action_count,
                dtype=visual.dtype,
                device=visual.device,
            )
            safe_previous = previous.clamp(min=0, max=self.config.action_count - 1)
            one_hot.scatter_(2, safe_previous.unsqueeze(-1), 1.0)
            one_hot = one_hot * valid.unsqueeze(-1)
            recurrent_input = torch.cat((visual, one_hot), dim=-1)
            recurrent_output, next_state = self.recurrent(recurrent_input, recurrent_state)
            return self.policy_head(recurrent_output), next_state

        def step(
            self,
            frame_pair: Any,
            previous_action: Any,
            recurrent_state: tuple[Any, Any] | None = None,
        ) -> tuple[Any, tuple[Any, Any]]:
            """Evaluate one decision while retaining an explicit recurrent state."""

            if frame_pair.ndim != 4:
                raise ValueError("frame_pair must have [batch, history, height, width]")
            if previous_action.ndim != 1 or previous_action.shape[0] != frame_pair.shape[0]:
                raise ValueError("previous_action must have [batch]")
            logits, next_state = self.forward(
                frame_pair.unsqueeze(1),
                previous_action.unsqueeze(1),
                recurrent_state,
            )
            return logits[:, 0], next_state

else:

    class ApprenticePolicy:  # pragma: no cover - behavior is the dependency error itself.
        def __init__(self, config: ApprenticeModelConfig | None = None) -> None:
            del config
            raise RuntimeError(TORCH_INSTALL_HELP)


def build_apprentice_policy(
    config: ApprenticeModelConfig | None = None,
) -> ApprenticePolicy:
    require_torch()
    return ApprenticePolicy(config)
