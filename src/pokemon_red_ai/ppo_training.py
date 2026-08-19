"""Backwards-compatible shim for the former single-file PPO training module.

The implementation now lives in :mod:`pokemon_red_ai.ppo`, split into modules by
responsibility. This module re-exports the full public and private surface so
every existing import path keeps working unchanged.

New code should import from :mod:`pokemon_red_ai.ppo` directly.
"""

from __future__ import annotations

from pokemon_red_ai.ppo import *  # noqa: F401,F403
from pokemon_red_ai.ppo import __all__ as _ppo_all

__all__ = list(_ppo_all)
