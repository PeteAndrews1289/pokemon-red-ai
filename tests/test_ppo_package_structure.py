"""Guards for the ppo package split.

``ppo_training`` was a single 7,255-line module. It is now a package, with the
old module kept as a re-export shim. Two things have to stay true: nothing that
used to be importable stopped being importable, and no module quietly grows back
into the thing that was split apart.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "pokemon_red_ai" / "ppo"
SHIM = ROOT / "src" / "pokemon_red_ai" / "ppo_training.py"

# The largest module today is distillation at ~1,020 lines. The cap leaves room
# to work without leaving room to recreate a 7,000-line file.
MAX_MODULE_LINES = 1200


def module_paths() -> list[Path]:
    return sorted(PACKAGE.glob("*.py"))


def test_package_exists_and_is_split() -> None:
    modules = module_paths()
    assert len(modules) >= 15, "the package should stay split, not re-merge"


@pytest.mark.parametrize("path", module_paths(), ids=lambda p: p.name)
def test_no_module_exceeds_the_size_cap(path: Path) -> None:
    line_count = len(path.read_text().splitlines())
    assert line_count <= MAX_MODULE_LINES, (
        f"{path.name} is {line_count} lines, over the {MAX_MODULE_LINES} cap. "
        "Split it rather than raising the cap."
    )


@pytest.mark.parametrize("path", module_paths(), ids=lambda p: p.name)
def test_every_module_has_a_docstring(path: Path) -> None:
    tree = ast.parse(path.read_text())
    assert ast.get_docstring(tree), f"{path.name} needs a module docstring"


def test_shim_reexports_the_whole_original_surface() -> None:
    """Every name the old module exposed must still import from it."""
    from pokemon_red_ai import ppo, ppo_training

    missing = [name for name in ppo.__all__ if not hasattr(ppo_training, name)]
    assert missing == [], f"the shim stopped re-exporting: {missing}"


def test_shim_and_package_expose_the_same_objects() -> None:
    """The shim must alias, not re-implement."""
    from pokemon_red_ai import ppo, ppo_training

    for name in ppo.__all__:
        assert getattr(ppo_training, name) is getattr(ppo, name), name


def test_known_public_entry_points_are_importable_from_the_old_path() -> None:
    from pokemon_red_ai.ppo_training import (  # noqa: F401
        ParallelPpoConfig,
        PokemonRedPpoEnvironment,
        PpoRunCallback,
        request_parallel_ppo_stop,
        run_parallel_ppo,
        show_parallel_ppo_status,
    )


def test_callback_behaviour_lives_in_mixins() -> None:
    """The callback class should compose mixins rather than hold everything."""
    from pokemon_red_ai.ppo.callback import PpoRunCallback

    base_names = {base.__name__ for base in PpoRunCallback.__mro__}
    for expected in [
        "StatusReportingMixin",
        "RunPersistenceMixin",
        "V8DistillationMixin",
        "V9PracticeMixin",
        "V12EvaluationMixin",
    ]:
        assert expected in base_names, f"{expected} is no longer part of the callback"


def test_no_mixin_method_names_collide() -> None:
    """Two mixins defining the same method would make MRO order load-bearing."""
    from pokemon_red_ai.ppo import (
        callback_persistence,
        callback_recovery,
        callback_status,
        callback_v8,
        callback_v9,
        callback_v12,
    )

    modules = [
        callback_status,
        callback_persistence,
        callback_recovery,
        callback_v8,
        callback_v9,
        callback_v12,
    ]
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for module in modules:
        mixin = next(
            value
            for name, value in vars(module).items()
            if isinstance(value, type) and name.endswith("Mixin")
        )
        for attribute in vars(mixin):
            if attribute.startswith("__"):
                continue
            if attribute in seen:
                collisions.append(f"{attribute} in both {seen[attribute]} and {mixin.__name__}")
            seen[attribute] = mixin.__name__
    assert collisions == [], collisions
