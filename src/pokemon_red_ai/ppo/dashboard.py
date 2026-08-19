"""HTML rendering for the run status dashboard."""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any

from pokemon_red_ai.ppo.modes import _is_distilled_student_mode
from pokemon_red_ai.ppo_dashboard import render_ppo_dashboard


def _render_dashboard_legacy(status: Mapping[str, Any]) -> str:
    best = status.get("best_milestone", {})
    focus = status.get("training_focus", {})
    rewards = status.get("reward_components", {})
    consolidation = status.get("consolidation", {})
    self_taught = status.get("self_taught", {})
    mode = html.escape(str(status.get("mode", "unknown")))
    frame_cards = "".join(
        f'<figure><img src="env-{rank}.png?v={status.get("updated_at", "")}" '
        f'alt="Environment {rank}"/><figcaption>Environment {rank + 1}</figcaption></figure>'
        for rank in range(int(status.get("environments", 0)))
    )
    cards = "".join(
        f'<div class="card"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in (
            ("State", html.escape(str(status.get("state")))),
            (
                "Explorer actions"
                if _is_distilled_student_mode(str(status.get("mode", "")))
                else "Combined actions",
                f"{int(status.get('total_actions', 0)):,}",
            ),
            (
                "Actions / second",
                f"{float(status.get('actions_per_second', 0)):,.1f}",
            ),
            (
                "Best verified milestone",
                html.escape(str(best.get("label", "Power-on"))),
            ),
            (
                "Current lesson",
                html.escape(str(focus.get("label", "Finish the game"))),
            ),
            ("PPO updates", f"{int(status.get('ppo_updates', 0)):,}"),
            (
                "Verified promotions",
                f"{int(status.get('verified_promotions', 0)):,}",
            ),
            (
                "Unique map positions",
                f"{int(status.get('unique_positions', 0)):,}",
            ),
            ("Episodes", f"{int(status.get('episodes', 0)):,}"),
            (
                "Consolidation start",
                html.escape(str(consolidation.get("active_start_label", "disabled"))),
            ),
            (
                "Consolidation target",
                html.escape(str(consolidation.get("target_label", "disabled"))),
            ),
            (
                "Rolling competence",
                (
                    f"{int(consolidation.get('active_window_successes', 0))}/"
                    f"{int(consolidation.get('active_window_attempts', 0))}"
                ),
            ),
            (
                "Backward gates passed",
                f"{int(consolidation.get('gates_passed_count', 0)):,}",
            ),
            (
                "Self-discovered skills",
                f"{int(self_taught.get('skills_discovered', 0)):,}",
            ),
            (
                "Competent skills",
                f"{int(self_taught.get('skills_competent', 0)):,}",
            ),
            (
                "Weakest skill",
                html.escape(str(self_taught.get("weakest_skill") or "none yet")),
            ),
            (
                "Weakest skill window",
                (
                    f"{int(self_taught.get('weakest_window_successes', 0))}/"
                    f"{int(self_taught.get('weakest_window_attempts', 0))}"
                ),
            ),
            (
                "Self-imitation examples",
                f"{int(self_taught.get('imitation_examples', 0)):,}",
            ),
            (
                "Novelty memory",
                html.escape(str(status.get("novelty_scope", "unknown"))),
            ),
            (
                "Reward protocol",
                html.escape(str(status.get("reward_protocol", "unknown"))),
            ),
            (
                "Battle successes",
                f"{int(status.get('battle_events', {}).get('success', 0)):,}",
            ),
            (
                "No-progress battle exits",
                f"{int(status.get('battle_events', {}).get('ended_without_progress', 0)):,}",
            ),
            (
                "Opponent-damage credit",
                f"{float(rewards.get('opponent_damage', 0)):,.2f}",
            ),
            (
                "Net active-route credit",
                f"{float(rewards.get('goal_route_progress', 0)):,.2f}",
            ),
            (
                "Navigation-recovery credit",
                f"{float(rewards.get('navigation_recovery', 0)):,.2f}",
            ),
            (
                "New-best Mart approach credit",
                f"{float(rewards.get('mart_approach', 0)):,.2f}",
            ),
            (
                "Mart dialogue-stage credit",
                f"{float(rewards.get('mart_dialogue_progress', 0)):,.2f}",
            ),
            (
                "Visual loops cut short",
                f"{int(status.get('loop_events', {}).get('visual_cycle', 0)):,}",
            ),
            (
                "Long stagnations cut short",
                f"{int(status.get('loop_events', {}).get('progress_stagnation', 0)):,}",
            ),
        )
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"/>
<meta http-equiv="refresh" content="5"/><meta name="viewport" content="width=device-width"/>
<title>Parallel PPO · Pokémon Red</title><style>
body{{background:#10151f;color:#eef3e8;font:16px system-ui;margin:0;padding:24px}}
main{{max-width:1200px;margin:auto}}h1{{font-size:clamp(2rem,6vw,4.7rem);margin:.15em 0}}
.eyebrow{{color:#ffcc66;letter-spacing:.16em;font-weight:700}}.grid{{display:grid;
grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.card,figure{{background:#192232;border:1px solid #33445f;border-radius:14px;
padding:16px;margin:0}}strong{{display:block;font-size:1.7rem}}
span,figcaption{{color:#aebbd0}}img{{width:100%;image-rendering:pixelated;border-radius:8px}}
.frames{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:12px}}
@media(max-width:650px){{.frames{{grid-template-columns:1fr}}}}</style></head><body><main>
<div class="eyebrow">PARALLEL RECURRENT PPO · {mode.upper()}</div>
<h1>Failures now<br/>teach the policy.</h1>
<p>Several games collect experience for one shared recurrent policy. Trainer-only RAM computes
rewards and verifies promotions; the actor boundary is shown explicitly below.</p>
<section class="grid">{cards}</section><section class="frames">{frame_cards}</section>
<p><strong>Information boundary</strong> {html.escape(str(status.get("information_boundary")))}</p>
</main></body></html>"""


def _render_dashboard(status: Mapping[str, Any]) -> str:
    return render_ppo_dashboard(status)
