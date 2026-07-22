"""Human-readable live dashboard for the parallel recurrent PPO experiments.

The renderer deliberately accepts both the flat Version-7 status payload and the richer nested
Version-8 payload.  That keeps old run directories readable while letting Version 8 tell the
important story plainly: an Explorer discovers, a separate Student studies only verified and
distilled discoveries, and frozen exams decide whether a skill is actually retained.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping, Sequence
from typing import Any

from pokemon_red_ai.milestones import MILESTONES

_MISSING = object()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(sources: Sequence[Mapping[str, Any]], *keys: str, default: object = None) -> object:
    for source in sources:
        for key in keys:
            if key in source and source[key] is not None:
                return source[key]
    return default


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _number(value: object, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _optional_integer(sources: Sequence[Mapping[str, Any]], *keys: str) -> int | None:
    value = _first(sources, *keys, default=_MISSING)
    if value is _MISSING:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _escaped(value: object, default: str = "unknown") -> str:
    resolved = default if value is None else str(value)
    return html.escape(resolved)


def _duration(seconds: object) -> str:
    remaining = max(0, _integer(seconds))
    days, remaining = divmod(remaining, 86_400)
    hours, remaining = divmod(remaining, 3_600)
    minutes, seconds_value = divmod(remaining, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    if hours:
        return f"{hours}h {minutes:02d}m {seconds_value:02d}s"
    return f"{minutes}m {seconds_value:02d}s"


def _bytes(value: object) -> str:
    amount = max(0, _integer(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    scaled = float(amount)
    unit = units[0]
    for unit in units:
        if scaled < 1024 or unit == units[-1]:
            break
        scaled /= 1024
    return f"{scaled:.0f} {unit}" if unit == "B" else f"{scaled:.1f} {unit}"


def _rate(successes: int, attempts: int) -> str:
    return "not tested" if attempts <= 0 else f"{successes / attempts:.0%}"


def _short_hash(value: object) -> str | None:
    if value is None:
        return None
    resolved = str(value).strip()
    if not resolved:
        return None
    return resolved[:12]


def _metric_card(label: str, value: str, *, note: str | None = None) -> str:
    note_html = "" if note is None else f"<small>{html.escape(note)}</small>"
    return (
        '<div class="card">'
        f"<span>{html.escape(label)}</span><strong>{value}</strong>{note_html}</div>"
    )


def _section(title: str, lead: str, cards: str, *, class_name: str = "") -> str:
    class_attribute = f' class="{html.escape(class_name)}"' if class_name else ""
    return (
        f'<section{class_attribute}><div class="section-heading">'
        f"<div><h2>{html.escape(title)}</h2><p>{html.escape(lead)}</p></div></div>"
        f'<div class="grid">{cards}</div></section>'
    )


def _is_v8(status: Mapping[str, Any]) -> bool:
    mode = str(status.get("mode", ""))
    protocol = str(status.get("protocol", ""))
    reward_protocol = str(status.get("reward_protocol", ""))
    return (
        mode == "self_taught_v8"
        or protocol
        in {
            "parallel-recurrent-ppo-v8",
            "parallel-recurrent-ppo-v9",
            "parallel-recurrent-ppo-v10",
        }
        or reward_protocol.startswith("distilled-self-generated-skills")
        or mode in {"self_taught_v9", "self_taught_v10"}
    )


def _is_v9(status: Mapping[str, Any]) -> bool:
    return (
        str(status.get("mode", "")) in {"self_taught_v9", "self_taught_v10"}
        or str(status.get("protocol", ""))
        in {"parallel-recurrent-ppo-v9", "parallel-recurrent-ppo-v10"}
        or str(status.get("reward_protocol", "")) == "self-correcting-student-v1"
        or str(status.get("reward_protocol", "")) == "recovery-before-reset-v1"
    )


def _is_v10(status: Mapping[str, Any]) -> bool:
    return (
        str(status.get("mode", "")) == "self_taught_v10"
        or str(status.get("protocol", "")) == "parallel-recurrent-ppo-v10"
        or str(status.get("reward_protocol", "")) == "recovery-before-reset-v1"
    )


def _legacy_learning_cards(status: Mapping[str, Any]) -> str:
    consolidation = _mapping(status.get("consolidation"))
    self_taught = _mapping(status.get("self_taught"))
    return "".join(
        (
            _metric_card(
                "Consolidation start",
                _escaped(consolidation.get("active_start_label"), "disabled"),
            ),
            _metric_card(
                "Consolidation target",
                _escaped(consolidation.get("target_label"), "disabled"),
            ),
            _metric_card(
                "Rolling competence",
                (
                    f"{_integer(consolidation.get('active_window_successes'))}/"
                    f"{_integer(consolidation.get('active_window_attempts'))}"
                ),
            ),
            _metric_card(
                "Backward gates passed",
                f"{_integer(consolidation.get('gates_passed_count')):,}",
            ),
            _metric_card(
                "Self-discovered skills",
                f"{_integer(self_taught.get('skills_discovered')):,}",
            ),
            _metric_card(
                "Competent skills",
                f"{_integer(self_taught.get('skills_competent')):,}",
            ),
            _metric_card(
                "Weakest skill",
                _escaped(self_taught.get("weakest_skill"), "none yet"),
            ),
            _metric_card(
                "Weakest skill window",
                (
                    f"{_integer(self_taught.get('weakest_window_successes'))}/"
                    f"{_integer(self_taught.get('weakest_window_attempts'))}"
                ),
            ),
            _metric_card(
                "Self-imitation examples",
                f"{_integer(self_taught.get('imitation_examples')):,}",
            ),
        )
    )


def _explorer_student_roles(status: Mapping[str, Any]) -> str:
    self_taught = _mapping(status.get("self_taught"))
    student = _mapping(self_taught.get("student"))
    student_sources = (student, self_taught, status)
    student_state = _escaped(
        _first(student_sources, "state", "student_state", default="waiting for a discovery")
    )
    student_updates = _integer(
        _first(student_sources, "optimizer_updates", "student_updates", default=0)
    )
    environments = max(0, _integer(status.get("environments")))
    world_label = "game world" if environments == 1 else "game worlds"
    explorer = (
        '<article class="role explorer"><div class="role-label">EXPLORER · LIVE PPO</div>'
        "<h2>Find something that works.</h2>"
        f"<p>{environments} {world_label} try actions and collect consequences. Their shared "
        "PPO policy is "
        "allowed to explore, fail, and discover new milestones.</p>"
        f"<strong>{_integer(status.get('total_actions')):,} actions tried</strong></article>"
    )
    learner = (
        '<article class="role student"><div class="role-label">STUDENT · SEPARATE NETWORK</div>'
        "<h2>Learn a cleaner verified lesson.</h2>"
        "<p>The Student never receives authored demonstrations. It studies only discoveries made "
        "by the Explorer and proven again by replay.</p>"
        f"<strong>{student_updates:,} Student-only updates</strong>"
        f"<small>Current state: {student_state}</small></article>"
    )
    return f'<section><div class="roles">{explorer}{learner}</div></section>'


def _depth_meter(
    number: int,
    title: str,
    index: int | None,
    label: object,
    explanation: str,
    *,
    total: int,
) -> str:
    if index is None:
        value = "not recorded yet"
        resolved_label = "Waiting for a measured depth"
        width = 0.0
        state = "missing"
    else:
        bounded = max(0, min(index, total))
        value = f"milestone {index} of {total}"
        resolved_label = str(label) if label not in {None, ""} else "label not recorded yet"
        width = 100.0 * bounded / max(1, total)
        state = "measured"
    return (
        f'<article class="depth-card {state}"><div class="depth-step">DEPTH {number}</div>'
        f"<h3>{html.escape(title)}</h3><strong>{html.escape(value)}</strong>"
        f"<p>{html.escape(resolved_label)}</p>"
        '<div class="depth-meter"><i '
        f'style="width:{width:.1f}%"></i></div><small>{html.escape(explanation)}</small>'
        "</article>"
    )


def _depth_section(status: Mapping[str, Any]) -> str:
    self_taught = _mapping(status.get("self_taught"))
    distillation = _mapping(self_taught.get("distillation"))
    exams = _mapping(self_taught.get("frozen_exams"))
    composition = _mapping(self_taught.get("composition"))
    best = _mapping(status.get("best_milestone"))
    total = max(
        1,
        _integer(
            _first(
                (status,),
                "milestone_count",
                "total_milestones",
                "hall_of_fame_index",
                default=len(MILESTONES),
            ),
            len(MILESTONES),
        ),
    )
    discovery_index = _optional_integer((best, status), "index", "discovery_best_index")
    distilled_index = _optional_integer(
        (distillation, self_taught, status),
        "best_index",
        "deepest_index",
        "best_distilled_index",
        "distilled_library_depth_index",
    )
    competent_index = _optional_integer(
        (exams, self_taught, status),
        "best_competent_index",
        "competence_best_index",
        "frozen_local_competence_index",
    )
    composition_index = _optional_integer(
        (composition, self_taught, status),
        "best_index",
        "best_composition_index",
        "restore_free_composition_index",
    )
    cards = "".join(
        (
            _depth_meter(
                1,
                "Discovery depth",
                discovery_index,
                _first((best, status), "label", "discovery_best_label", default=None),
                "Deepest milestone ever reached and replay-verified by the Explorer.",
                total=total,
            ),
            _depth_meter(
                2,
                "Distilled library depth",
                distilled_index,
                _first(
                    (distillation, self_taught, status),
                    "best_label",
                    "deepest_label",
                    "best_distilled_label",
                    default=None,
                ),
                "Deepest milestone represented by a compressed, replay-verified lesson.",
                total=total,
            ),
            _depth_meter(
                3,
                "Frozen local competence",
                competent_index,
                _first(
                    (exams, self_taught, status),
                    "best_competent_label",
                    "competence_best_label",
                    default=None,
                ),
                "Deepest local lesson passed by the frozen Student from its saved source state.",
                total=total,
            ),
            _depth_meter(
                4,
                "Restore-free composition",
                composition_index,
                _first(
                    (composition, self_taught, status),
                    "best_label",
                    "best_composition_label",
                    default=None,
                ),
                "Deepest continuous power-on attempt completed without restoring between skills.",
                total=total,
            ),
        )
    )
    return (
        '<section class="depth"><div class="section-heading"><div><h2>How deep is the learning?'
        "</h2><p>Four different claims, kept separate. Reaching a place is not the same as "
        "distilling it, passing it locally, or composing it from power-on.</p></div></div>"
        f'<div class="depth-grid">{cards}</div></section>'
    )


def _provenance_section(status: Mapping[str, Any]) -> str:
    self_taught = _mapping(status.get("self_taught"))
    checkpoints = _mapping(status.get("checkpoints"))
    denominator = _mapping(status.get("v7_denominator"))
    sources = (checkpoints, self_taught, status)
    explorer_hash = _short_hash(
        _first(
            sources,
            "explorer_sha256",
            "explorer_checkpoint_sha256",
            "model_file_sha256",
            default=None,
        )
    )
    student_hash = _short_hash(
        _first(
            sources,
            "student_sha256",
            "student_checkpoint_sha256",
            "student_model_file_sha256",
            default=None,
        )
    )
    if explorer_hash is None and student_hash is None and not denominator:
        return ""
    cards: list[str] = []
    if explorer_hash is not None:
        cards.append(
            _metric_card(
                "Explorer checkpoint",
                _escaped(explorer_hash),
                note="first 12 characters of the saved SHA-256",
            )
        )
    if student_hash is not None:
        cards.append(
            _metric_card(
                "Student checkpoint",
                _escaped(student_hash),
                note="first 12 characters of the saved SHA-256",
            )
        )
    denominator_html = ""
    if denominator:
        locked = denominator.get("locked") is True
        lock_label = "LOCKED V7 SNAPSHOT" if locked else "UNLOCKED V7 REFERENCE"
        denominator_sources = (denominator,)
        actions = _optional_integer(denominator_sources, "total_actions", "actions")
        best_index = _optional_integer(denominator_sources, "best_index", "milestone_index")
        action_text = "not recorded yet" if actions is None else f"{actions:,} actions"
        index_text = "?" if best_index is None else str(best_index)
        run_name = _escaped(
            _first(denominator_sources, "run_id", "run", "name", default="unnamed V7 run")
        )
        best_label = _escaped(
            _first(denominator_sources, "best_label", "milestone_label", default="not recorded yet")
        )
        denominator_hash = _short_hash(
            _first(
                denominator_sources,
                "checkpoint_sha256",
                "model_file_sha256",
                default=None,
            )
        )
        hash_text = "not supplied" if denominator_hash is None else html.escape(denominator_hash)
        source_state = _escaped(denominator.get("source_state_at_lock"), "unknown")
        denominator_html = (
            f'<article class="denominator {"locked" if locked else "unlocked"}">'
            f'<div class="role-label">{lock_label}</div><h3>{run_name}</h3>'
            f"<strong>{action_text}</strong><p>Best milestone {index_text}: {best_label}</p>"
            f"<small>Checkpoint {hash_text} · source was {source_state} at lock</small></article>"
        )
    return (
        '<section class="provenance"><div class="section-heading"><div><h2>Model identity and '
        "denominator</h2><p>Short hashes distinguish the two networks. A locked V7 checkpoint "
        "preserves one action-counted reference instead of moving it later; final claims still "
        "need matched-budget campaign results.</p></div></div>"
        f'<div class="grid">{"".join(cards)}{denominator_html}</div></section>'
    )


def _distillation_section(status: Mapping[str, Any]) -> str:
    self_taught = _mapping(status.get("self_taught"))
    distillation = _mapping(self_taught.get("distillation"))
    sources = (distillation, self_taught, status)
    original = _integer(
        _first(
            sources,
            "original_actions",
            "original_actions_total",
            "distillation_original_actions",
            default=0,
        )
    )
    distilled = _integer(
        _first(
            sources,
            "distilled_actions",
            "distilled_actions_total",
            "compressed_actions",
            "compressed_actions_total",
            default=0,
        )
    )
    removed = max(0, original - distilled)
    retention = min(1.0, max(0.0, distilled / original)) if original else 0.0
    removed_rate = min(1.0, max(0.0, removed / original)) if original else 0.0
    shorter = original / distilled if distilled else 0.0
    skills = _integer(
        _first(sources, "skills_distilled", "distilled_skills", "skills_discovered", default=0)
    )
    oracle_calls = _optional_integer(
        sources,
        "total_oracle_calls",
        "oracle_calls",
        "replay_oracle_calls",
    )
    replay_actions = _optional_integer(
        sources,
        "oracle_actions_replayed",
        "replay_actions",
        "replay_oracle_actions",
    )
    accepted_edits = _optional_integer(
        sources,
        "edits_accepted",
        "accepted_edits",
        "deletions_accepted",
    )
    rejected_edits = _optional_integer(
        sources,
        "edits_rejected",
        "rejected_edits",
        "deletions_rejected",
    )
    if accepted_edits is None:
        loop_accepted = _optional_integer(sources, "loop_deletions_accepted")
        chunk_accepted = _optional_integer(sources, "chunk_deletions_accepted")
        if loop_accepted is not None or chunk_accepted is not None:
            accepted_edits = (loop_accepted or 0) + (chunk_accepted or 0)
    if rejected_edits is None:
        loop_rejected = _optional_integer(sources, "loop_deletions_rejected")
        chunk_rejected = _optional_integer(sources, "chunk_deletions_rejected")
        if loop_rejected is not None or chunk_rejected is not None:
            rejected_edits = (loop_rejected or 0) + (chunk_rejected or 0)

    def optional_count(value: int | None) -> str:
        return "not recorded yet" if value is None else f"{value:,}"

    if original:
        compression_value = f"{shorter:.2f}× shorter" if distilled else "all noise removed"
        progress = (
            '<div class="meter-row"><div><span>Trajectory kept for teaching</span>'
            f'<b>{retention:.1%}</b></div><div class="meter"><i '
            f'style="width:{retention * 100:.1f}%"></i></div></div>'
        )
    else:
        compression_value = "waiting"
        progress = (
            '<div class="meter-row"><div><span>Trajectory kept for teaching</span>'
            '<b>waiting for first verified discovery</b></div><div class="meter"><i '
            'style="width:0%"></i></div></div>'
        )
    cards = "".join(
        (
            _metric_card("Actions as discovered", f"{original:,}"),
            _metric_card("Actions after distillation", f"{distilled:,}"),
            _metric_card(
                "Wandering removed",
                f"{removed:,}",
                note=(f"{removed_rate:.1%} of the discovered path" if original else None),
            ),
            _metric_card("Compression", compression_value),
            _metric_card("Skills distilled", f"{skills:,}"),
            _metric_card(
                "Replay-oracle calls",
                optional_count(oracle_calls),
                note=(
                    "candidate replays plus baseline and final checks"
                    if oracle_calls is not None
                    else None
                ),
            ),
            _metric_card(
                "Actions replayed by oracle",
                optional_count(replay_actions),
                note=(
                    "compute cost, separate from Explorer actions"
                    if replay_actions is not None
                    else None
                ),
            ),
            _metric_card("Proposed edits accepted", optional_count(accepted_edits)),
            _metric_card("Proposed edits rejected", optional_count(rejected_edits)),
        )
    )
    return (
        _section(
            "Discovery distillation",
            "Replay removes loops and dispensable detours without adding human actions.",
            cards,
            class_name="distillation",
        )
        + progress
    )


def _student_section(status: Mapping[str, Any]) -> str:
    self_taught = _mapping(status.get("self_taught"))
    student = _mapping(self_taught.get("student"))
    diagnostics = _mapping(student.get("diagnostics"))
    replay = _mapping(student.get("replay_memory"))
    sources = (diagnostics, student, self_taught, status)
    rounds = _integer(_first(sources, "training_rounds", "student_training_rounds", default=0))
    updates = _integer(_first(sources, "optimizer_updates", "student_updates", default=0))
    examples = _integer(_first(sources, "examples", "student_examples", default=0))
    action_nll = _number(
        _first(sources, "action_nll", "last_action_nll", "student_action_nll", default=0.0)
    )
    action_accuracy = _number(
        _first(
            sources,
            "action_accuracy",
            "last_action_accuracy",
            "student_action_accuracy",
            default=0.0,
        )
    )
    policy_entropy = _number(
        _first(sources, "policy_entropy", "student_policy_entropy", default=0.0)
    )
    demo_entropy = _number(
        _first(
            sources,
            "demonstration_entropy",
            "demo_entropy",
            "student_demo_entropy",
            default=0.0,
        )
    )
    shard_total = _integer(replay.get("skill_shards_total"))
    shard_loaded = _integer(replay.get("skill_shards_loaded"))
    owned_examples = _integer(replay.get("shard_train_examples_loaded"))
    context_examples = _integer(replay.get("shard_context_examples_loaded"))
    full_artifacts_opened = _integer(replay.get("full_skill_artifacts_opened"))
    coverage_cycle = _integer(
        _first(
            (replay,),
            "minimum_completed_coverage_cycles",
            "coverage_cycle_min",
            default=0,
        )
    )
    sampling_cycle = _integer(replay.get("sampling_cycle_size"))
    cards = "".join(
        (
            _metric_card("Training rounds", f"{rounds:,}"),
            _metric_card("Student updates", f"{updates:,}"),
            _metric_card("Sequence examples", f"{examples:,}"),
            _metric_card("Action accuracy", f"{action_accuracy:.1%}"),
            _metric_card("Action NLL", f"{action_nll:.3f}"),
            _metric_card("Student policy entropy", f"{policy_entropy:.3f}"),
            _metric_card("Discovery action entropy", f"{demo_entropy:.3f}"),
            _metric_card(
                "Bounded skill shards",
                f"{shard_loaded}/{shard_total} loaded",
                note="one persistent cursor-selected shard per learned skill",
            ),
            _metric_card(
                "Owned / context examples",
                f"{owned_examples:,} / {context_examples:,}",
                note="context warms recurrent memory but carries no training loss",
            ),
            _metric_card(
                "Shard bytes read this round",
                _bytes(replay.get("shard_bytes_read")),
            ),
            _metric_card(
                "Full skill files opened",
                f"{full_artifacts_opened:,}",
                note="should remain zero during routine Student replay",
            ),
            _metric_card("Minimum full-coverage cycles", f"{coverage_cycle:,}"),
            _metric_card("Weighted replay cycle", f"{sampling_cycle:,} tickets"),
            _metric_card(
                "Retained replay memory",
                _bytes(replay.get("retained_bytes")),
            ),
        )
    )
    return _section(
        "What the Student is learning",
        (
            "Accuracy and NLL measure imitation of the Explorer's verified sequences; entropy "
            "shows whether either policy has collapsed to too few actions."
        ),
        cards,
        class_name="student-learning",
    )


def _practice_section(status: Mapping[str, Any]) -> str:
    practice = _mapping(status.get("student_practice"))
    terminal_reasons = _mapping(practice.get("terminal_reasons"))
    attempts = _integer(practice.get("attempts"))
    successes = _integer(practice.get("successes"))
    ladders = _integer(practice.get("skills_with_ladders"))
    completed = _integer(practice.get("skills_completed"))
    promotion_window = _integer(practice.get("promotion_window"))
    promotion_required = _integer(practice.get("promotion_required_successes"))
    confirmations = _integer(practice.get("promotion_confirmations"))
    rung = _optional_integer((practice,), "active_rung_index")
    remaining = _optional_integer((practice,), "active_remaining_actions")
    if rung is None:
        active_rung = "waiting for a skill" if not ladders else "all ladders complete"
    elif remaining is None:
        active_rung = f"rung {rung + 1}"
    else:
        active_rung = f"rung {rung + 1} · last {remaining:,} actions"
    cards = "".join(
        (
            _metric_card("Practice ladders completed", f"{completed}/{ladders}"),
            _metric_card(
                "Practice promotion gate",
                (
                    f"{promotion_required}/{promotion_window} × {confirmations}"
                    if promotion_window and confirmations
                    else "not reported"
                ),
                note="consecutive, non-overlapping success windows",
            ),
            _metric_card(
                "Verified practice record",
                f"{successes}/{attempts}",
                note=_rate(successes, attempts),
            ),
            _metric_card(
                "Exact-target attempts",
                f"{_integer(terminal_reasons.get('exact_target')):,}",
            ),
            _metric_card(
                "Wrong-state milestone hits",
                f"{_integer(terminal_reasons.get('milestone_wrong_state')):,}",
            ),
            _metric_card(
                "Practice timeouts",
                f"{_integer(terminal_reasons.get('timeout')):,}",
            ),
            _metric_card(
                "Practice emulator stops",
                f"{_integer(terminal_reasons.get('emulator_stopped')):,}",
            ),
            _metric_card("Active reverse-practice rung", active_rung),
            _metric_card(
                "Successful rollouts retained",
                f"{_integer(practice.get('retained_success_rollouts')):,}",
                note="bounded Student-generated training evidence",
            ),
            _metric_card(
                "Aggregated rollouts replayed",
                f"{_integer(practice.get('aggregated_datasets_loaded_last_round')):,}",
                note="one rotating bounded sample per practiced rung",
            ),
            _metric_card(
                "Aggregated examples replayed",
                f"{_integer(practice.get('aggregated_train_examples_last_round')):,}",
            ),
            _metric_card(
                "Closed-loop practice actions",
                f"{_integer(practice.get('emulator_actions')):,}",
            ),
            _metric_card(
                "Replay-verification actions",
                f"{_integer(practice.get('verification_actions')):,}",
            ),
            _metric_card(
                "Success-only training updates",
                f"{_integer(practice.get('training_updates')):,}",
            ),
            _metric_card(
                "Failed attempts enter gradient",
                "no" if practice.get("success_only_gradient") is True else "not reported",
            ),
            _metric_card(
                "Memory reset at each attempt",
                (
                    "yes"
                    if practice.get("recurrent_state_reset_each_attempt") is True
                    else "not reported"
                ),
            ),
            _metric_card(
                "Recovery PPO escalation",
                (
                    "not active"
                    if practice.get("recovery_ppo") == "gated_future_escalation_not_active"
                    else _escaped(practice.get("recovery_ppo"), "not reported")
                ),
            ),
        )
    )
    return _section(
        "Closed-loop practice: can it recover from its own mistakes?",
        (
            "V9 begins near the end of each self-discovered skill, acts for itself, and expands "
            "the starting point backward only after repeated verified success. Failed attempts "
            "measure the gap but never become demonstrations."
        ),
        cards,
        class_name="student-practice",
    )


def _exam_section(status: Mapping[str, Any]) -> str:
    self_taught = _mapping(status.get("self_taught"))
    exams = _mapping(self_taught.get("frozen_exams"))
    composition = _mapping(self_taught.get("composition"))
    exam_sources = (exams, self_taught, status)
    composition_sources = (composition, self_taught, status)
    attempts = _integer(_first(exam_sources, "attempts", "frozen_exam_attempts", default=0))
    successes = _integer(_first(exam_sources, "successes", "frozen_exam_successes", default=0))
    rounds = _integer(_first(exam_sources, "rounds", "frozen_exam_rounds", default=0))
    next_at = _integer(
        _first(
            exam_sources,
            "next_at_action",
            "next_frozen_exam_action",
            "next_frozen_exam_actions",
            default=0,
        )
    )
    current_skill = _escaped(
        _first(exam_sources, "current_skill", "exam_skill", default="none selected")
    )
    competence_losses = _integer(
        _first(exam_sources, "competence_losses", "skill_competence_losses", default=0)
    )
    skills = _integer(_first(exam_sources, "skills_discovered", default=0))
    competent = _integer(_first(exam_sources, "skills_competent", default=0))
    composition_attempts = _integer(
        _first(composition_sources, "attempts", "composition_attempts", default=0)
    )
    composition_successes = _integer(
        _first(composition_sources, "successes", "composition_successes", default=0)
    )
    window_attempts = _integer(
        _first(
            composition_sources,
            "window_attempts",
            "composition_window_attempts",
            default=0,
        )
    )
    window_successes = _integer(
        _first(
            composition_sources,
            "window_successes",
            "composition_window_successes",
            default=0,
        )
    )
    best_composition_index = _optional_integer(
        composition_sources,
        "best_index",
        "best_composition_index",
        "restore_free_composition_index",
    )
    best_composition_label = _escaped(
        _first(
            composition_sources,
            "best_label",
            "best_composition_label",
            default="not recorded yet",
        )
    )
    hall_of_fame_completions = _optional_integer(
        composition_sources,
        "hall_of_fame_completions",
        "restore_free_hall_of_fame_completions",
    )
    next_exam = f"at action {next_at:,}" if next_at else "awaiting schedule"
    cards = "".join(
        (
            _metric_card("Competent skills", f"{competent}/{skills}"),
            _metric_card("Frozen exam rounds", f"{rounds:,}"),
            _metric_card(
                "Frozen exam record", f"{successes}/{attempts}", note=_rate(successes, attempts)
            ),
            _metric_card("Skill currently tested", current_skill),
            _metric_card("Next frozen exam", next_exam),
            _metric_card("Competence revoked", f"{competence_losses:,}"),
            _metric_card(
                "Composition exam record",
                f"{composition_successes}/{composition_attempts}",
                note=_rate(composition_successes, composition_attempts),
            ),
            _metric_card(
                "Recent composition window",
                f"{window_successes}/{window_attempts}",
                note=_rate(window_successes, window_attempts),
            ),
            _metric_card(
                "Best restore-free depth",
                (
                    "not recorded yet"
                    if best_composition_index is None
                    else f"milestone {best_composition_index}"
                ),
                note=html.unescape(best_composition_label),
            ),
            _metric_card(
                "Hall-of-Fame completions",
                (
                    "not recorded yet"
                    if hall_of_fame_completions is None
                    else f"{hall_of_fame_completions:,}"
                ),
                note="continuous frozen-Student runs from power-on",
            ),
        )
    )
    return _section(
        "Frozen exams: can it reproduce the lesson?",
        (
            "Student weights do not change during these attempts. Passing marks competence; "
            "later failures can revoke it. Composition exams test whether separate skills join "
            "into one continuous run while the trainer switches only among self-generated goal "
            "clips at declared RAM milestone endpoints."
        ),
        cards,
        class_name="exams",
    )


def _explorer_loop_recovery_section(status: Mapping[str, Any]) -> str:
    recovery = _mapping(status.get("explorer_loop_recovery"))
    started = _integer(recovery.get("windows_started"))
    escaped = _integer(recovery.get("escapes"))
    completed = _integer(recovery.get("completed_windows"))
    cards = "".join(
        (
            _metric_card("Recovery windows opened", f"{started:,}"),
            _metric_card("Credited policy escapes", f"{escaped:,}"),
            _metric_card(
                "Recovery escape rate",
                _rate(escaped, completed),
                note="credited escapes / completed windows; context changes are not successes",
            ),
            _metric_card("Completed recovery windows", f"{completed:,}"),
            _metric_card(
                "Context changes (no credit)",
                f"{_integer(recovery.get('context_changes')):,}",
            ),
            _metric_card("Expired and reset", f"{_integer(recovery.get('expirations')):,}"),
            _metric_card("Abandoned windows", f"{_integer(recovery.get('abandoned_windows')):,}"),
            _metric_card(
                "Abandoned on resume",
                f"{_integer(recovery.get('abandoned_on_resume')):,}",
            ),
            _metric_card(
                "Abandoned at episode end",
                f"{_integer(recovery.get('abandoned_on_episode_end')):,}",
            ),
            _metric_card(
                "Abandoned at campaign end",
                f"{_integer(recovery.get('abandoned_on_campaign_end')):,}",
            ),
            _metric_card(
                "Unresolved inactive windows",
                f"{_integer(recovery.get('unresolved_windows')):,}",
                note="must remain zero",
            ),
            _metric_card("Recovery actions", f"{_integer(recovery.get('actions')):,}"),
            _metric_card(
                "Active recovery environments",
                f"{_integer(recovery.get('active_environments')):,}",
            ),
            _metric_card(
                "Blocked-repeat triggers",
                f"{_integer(recovery.get('blocked_repeat_triggers')):,}",
            ),
            _metric_card(
                "Visual-cycle triggers",
                f"{_integer(recovery.get('visual_cycle_triggers')):,}",
            ),
            _metric_card(
                "Long-stagnation triggers",
                f"{_integer(recovery.get('progress_stagnation_triggers')):,}",
            ),
            _metric_card(
                "Blocked direction attempts",
                f"{_integer(recovery.get('blocked_direction_attempts')):,}",
            ),
            _metric_card(
                "Repeated blocked attempts",
                f"{_integer(recovery.get('repeated_blocked_attempts')):,}",
            ),
            _metric_card(
                "Trainer-selected buttons",
                f"{_integer(recovery.get('actor_action_overrides')):,}",
                note="must remain zero",
            ),
        )
    )
    return _section(
        "Explorer loop recovery: did it escape without a reset?",
        (
            "The policy still chooses every button. Pixels and the chosen action can identify "
            "a repeated no-effect direction, visual cycle, or long stagnation, opening a bounded "
            "practice window. A blocked-direction lesson credits a directional visual escape; "
            "dialogue or menu "
            "changes preserve it only as no-credit context changes. A visual-cycle or "
            "long-stagnation lesson can credit any material policy-chosen visual escape after its "
            "loop penalty. No route, coordinate, preferred direction, mask, or forced action is "
            "supplied."
        ),
        cards,
        class_name="recovery",
    )


def _common_cards(status: Mapping[str, Any], *, v8: bool, v10: bool) -> str:
    best = _mapping(status.get("best_milestone"))
    focus = _mapping(status.get("training_focus"))
    rewards = _mapping(status.get("reward_components"))
    battle_events = _mapping(status.get("battle_events"))
    loop_events = _mapping(status.get("loop_events"))
    cards = [
        _metric_card("State", _escaped(status.get("state"))),
        _metric_card("Elapsed", _duration(status.get("elapsed_seconds", 0))),
        _metric_card(
            "Explorer actions" if v8 else "Combined actions",
            f"{_integer(status.get('total_actions')):,}",
        ),
        _metric_card("Actions / second", f"{_number(status.get('actions_per_second')):,.1f}"),
        _metric_card("Best verified milestone", _escaped(best.get("label"), "Power-on")),
        _metric_card("Current lesson", _escaped(focus.get("label"), "Finish the game")),
        _metric_card("PPO updates", f"{_integer(status.get('ppo_updates')):,}"),
        _metric_card("Verified promotions", f"{_integer(status.get('verified_promotions')):,}"),
        _metric_card("Unique map positions", f"{_integer(status.get('unique_positions')):,}"),
        _metric_card("Episodes", f"{_integer(status.get('episodes')):,}"),
    ]
    if not v8:
        cards.extend([_legacy_learning_cards(status)])
    cards.extend(
        [
            _metric_card("Novelty memory", _escaped(status.get("novelty_scope"))),
            _metric_card("Reward protocol", _escaped(status.get("reward_protocol"))),
            _metric_card("Battle successes", f"{_integer(battle_events.get('success')):,}"),
            _metric_card(
                "No-progress battle exits",
                f"{_integer(battle_events.get('ended_without_progress')):,}",
            ),
            _metric_card(
                "Opponent-damage credit", f"{_number(rewards.get('opponent_damage')):,.2f}"
            ),
            _metric_card(
                "Net active-route credit",
                f"{_number(rewards.get('goal_route_progress')):,.2f}",
            ),
            _metric_card(
                "Navigation-recovery credit",
                f"{_number(rewards.get('navigation_recovery')):,.2f}",
            ),
            _metric_card(
                "New-best Mart approach credit",
                f"{_number(rewards.get('mart_approach')):,.2f}",
            ),
            _metric_card(
                "Mart dialogue-stage credit",
                f"{_number(rewards.get('mart_dialogue_progress')):,.2f}",
            ),
            _metric_card(
                "Visual loop triggers detected" if v10 else "Visual loops cut short",
                f"{_integer(loop_events.get('visual_cycle')):,}",
            ),
            _metric_card(
                "Long stagnations detected" if v10 else "Long stagnations cut short",
                f"{_integer(loop_events.get('progress_stagnation')):,}",
            ),
        ]
    )
    return "".join(cards)


def render_ppo_dashboard(status: Mapping[str, Any]) -> str:
    """Render one self-contained, mobile-friendly dashboard from public status counters."""

    v8 = _is_v8(status)
    v9 = _is_v9(status)
    v10 = _is_v10(status)
    mode = _escaped(str(status.get("mode", "unknown")).upper())
    updated_at = html.escape(str(status.get("updated_at", "")), quote=True)
    environment_label = "Explorer environment" if v8 else "Environment"
    frame_cards = "".join(
        (
            f'<figure><img src="env-{rank}.png?v={updated_at}" '
            f'alt="{environment_label} {rank + 1}"/>'
            f"<figcaption>{environment_label} {rank + 1}</figcaption></figure>"
        )
        for rank in range(max(0, _integer(status.get("environments"))))
    )
    headline = (
        "One agent explores.<br/>Another learns what worked."
        if v8
        else "Failures now<br/>teach the policy."
    )
    intro = (
        "The live Explorer searches several games at once. A separate Student studies only "
        "self-generated discoveries that replay successfully, then proves its learning in frozen "
        "exams."
        if v8
        else (
            "Several games collect experience for one shared recurrent policy. Trainer-only RAM "
            "computes rewards and verifies promotions; the actor boundary is shown explicitly "
            "below."
        )
    )
    v8_sections = (
        _explorer_student_roles(status)
        + _depth_section(status)
        + (_explorer_loop_recovery_section(status) if v10 else "")
        + _distillation_section(status)
        + _student_section(status)
        + (_practice_section(status) if v9 else "")
        + _exam_section(status)
        + _provenance_section(status)
        if v8
        else ""
    )
    common_cards = _common_cards(status, v8=v8, v10=v10)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta http-equiv="refresh" content="5"/><meta name="viewport" content="width=device-width"/>
<title>Parallel PPO · Pokémon Red</title><style>
:root{{--ink:#eef3e8;--muted:#aebbd0;--panel:#192232;--line:#33445f;--gold:#ffcc66;
--explorer:#67d5ff;--student:#b993ff;--good:#71df9b}}
*{{box-sizing:border-box}}body{{background:#10151f;color:var(--ink);font:16px/1.5 system-ui,
-apple-system,sans-serif;margin:0;padding:clamp(16px,3vw,32px)}}main{{max-width:1240px;margin:auto}}
h1{{font-size:clamp(2.25rem,7vw,5.25rem);line-height:.98;margin:.18em 0 .35em;
letter-spacing:-.04em}}
h2{{font-size:clamp(1.35rem,3vw,2rem);margin:0 0 .2em}}p{{max-width:72ch;color:#ced7e5}}
.eyebrow,.role-label{{color:var(--gold);letter-spacing:.14em;font-size:.78rem;font-weight:800}}
section{{margin-top:28px}}.section-heading{{display:flex;justify-content:space-between;gap:16px;
align-items:end;margin-bottom:10px}}.section-heading p{{margin:.2em 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:12px}}
.card,figure,.role{{background:var(--panel);border:1px solid var(--line);border-radius:14px;
padding:16px;margin:0;min-width:0}}.card strong,.role strong{{display:block;font-size:1.55rem;
line-height:1.15;overflow-wrap:anywhere}}.card span,figcaption,small{{color:var(--muted)}}
.card small,.role small{{display:block;margin-top:7px}}.roles{{display:grid;
grid-template-columns:1fr 1fr;
gap:12px}}.role{{padding:clamp(18px,3vw,28px)}}.role h2{{margin-top:10px}}
.role.explorer{{border-color:#2d7894}}.role.explorer .role-label{{color:var(--explorer)}}
.role.student{{border-color:#684c98}}.role.student .role-label{{color:var(--student)}}
.depth-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
.depth-card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}}
.depth-step{{color:var(--gold);font-size:.73rem;font-weight:800;letter-spacing:.12em}}
.depth-card h3,.denominator h3{{margin:.5em 0 .3em;font-size:1.1rem}}.depth-card strong,
.denominator strong{{font-size:1.3rem}}.depth-card p{{min-height:3em;margin:.35em 0}}
.depth-card small{{display:block;margin-top:10px}}.depth-card.missing{{border-style:dashed}}
.depth-meter{{height:9px;background:#0c1119;border-radius:999px;overflow:hidden;margin:11px 0}}
.depth-meter i{{display:block;height:100%;background:linear-gradient(90deg,var(--explorer),
var(--student),var(--good));border-radius:inherit}}.denominator{{background:#192232;border:1px solid
var(--line);border-radius:14px;padding:16px}}.denominator.locked{{border-color:#856d2e}}
.denominator.unlocked{{border-color:#974f58}}.denominator .role-label{{color:var(--gold)}}
.meter-row{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;
margin-top:12px}}.meter-row>div:first-child{{display:flex;justify-content:space-between;gap:14px}}
.meter{{height:12px;background:#0c1119;border-radius:999px;overflow:hidden;margin-top:10px}}
.meter i{{display:block;height:100%;background:linear-gradient(90deg,var(--student),var(--good));
border-radius:inherit}}.frames{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;
margin-top:12px}}img{{width:100%;image-rendering:pixelated;border-radius:8px;display:block}}
.boundary{{margin-top:24px;padding:17px;border-left:4px solid var(--gold);background:#151d2a}}
.boundary strong{{display:block;color:var(--gold)}}footer{{color:var(--muted);margin:28px 0 8px}}
@media(max-width:900px){{.depth-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:700px){{.roles,.frames{{grid-template-columns:1fr}}.grid{{grid-template-columns:
repeat(2,minmax(0,1fr))}}.card strong{{font-size:1.25rem}}}}
@media(max-width:430px){{.grid,.depth-grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="eyebrow">PARALLEL RECURRENT PPO · {mode}</div><h1>{headline}</h1>
<p>{html.escape(intro)}</p>{v8_sections}
<section><div class="section-heading"><div><h2>Live run</h2>
<p>Shared counters from the current experiment.</p>
</div></div><div class="grid">{common_cards}</div></section>
<section><div class="section-heading"><div><h2>Explorer screens</h2>
<p>Current frames from each parallel
game world.</p></div></div><div class="frames">{frame_cards}</div></section>
<div class="boundary"><strong>Information boundary</strong>
{_escaped(status.get("information_boundary"), "not reported")}</div>
<footer>Refreshes every five seconds · Last status:
{_escaped(status.get("updated_at"), "waiting")}</footer>
</main></body></html>"""


__all__ = ["render_ppo_dashboard"]
