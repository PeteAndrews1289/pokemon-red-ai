"""Explorer-loop recovery bookkeeping.

Split out of the single ``PpoRunCallback`` class. These methods were moved
verbatim; ``self`` resolution and attribute access are unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pokemon_red_ai.pixel_recovery import (
    RECOVERY_TRIGGERS,
)


class ExplorerRecoveryMixin:
    """Explorer-loop recovery bookkeeping."""


    def _abandon_active_recoveries(self, reason: str) -> int:
        if reason not in {"resume", "campaign_end"}:
            raise ValueError("Explorer recovery abandonment reason is unsupported")
        active_ranks = [
            rank for rank, active in self.explorer_loop_recovery_active.items() if active
        ]
        if active_ranks:
            self.explorer_loop_recovery_events[f"abandoned_on_{reason}"] += len(active_ranks)
            for rank in active_ranks:
                self.explorer_loop_recovery_active[rank] = False
        return len(active_ranks)

    def _record_explorer_loop_recovery(self, info: Mapping[str, Any]) -> None:
        recovery = info.get("explorer_loop_recovery")
        if not isinstance(recovery, Mapping):
            return
        submitted = recovery.get("submitted_action")
        executed = recovery.get("executed_action")
        if submitted != executed:
            raise RuntimeError("Explorer loop recovery changed the PPO-selected action")
        rank = info.get("rank")
        if isinstance(rank, int):
            self.explorer_loop_recovery_active[rank] = bool(recovery.get("active", False))
        if recovery.get("recovery_action") is True:
            self.explorer_loop_recovery_events["actions"] += 1
        if recovery.get("blocked_direction_attempt") is True:
            self.explorer_loop_recovery_events["blocked_direction_attempts"] += 1
        if recovery.get("repeated_blocked_attempt") is True:
            self.explorer_loop_recovery_events["repeated_blocked_attempts"] += 1
        recovery_event = recovery.get("event")
        if recovery_event == "started":
            self.explorer_loop_recovery_events["windows_started"] += 1
            trigger = recovery.get("trigger")
            if trigger in RECOVERY_TRIGGERS:
                self.explorer_loop_recovery_events[f"{trigger}_triggers"] += 1
        elif recovery_event == "escaped":
            self.explorer_loop_recovery_events["escapes"] += 1
        elif recovery_event == "context_changed":
            self.explorer_loop_recovery_events["context_changes"] += 1
        elif recovery_event == "expired":
            self.explorer_loop_recovery_events["expirations"] += 1
        if info.get("episode_end") is True and recovery.get("active") is True:
            self.explorer_loop_recovery_events["abandoned_on_episode_end"] += 1
            if isinstance(rank, int):
                self.explorer_loop_recovery_active[rank] = False
