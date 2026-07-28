# ruff: noqa: E501
from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any

LANE_COLORS = {
    "uniform-broad": "#a9b4c7",
    "uniform-gentle": "#83d8ff",
    "uniform-multiscale": "#b59cff",
    "frontier-broad": "#ffd166",
    "frontier-gentle": "#6ee7a8",
    "frontier-multiscale": "#ff7e9d",
}


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _telemetry_value(status: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    """Read telemetry across old and new evolution status schemas."""

    containers: tuple[Mapping[str, Any], ...] = (
        status,
        status.get("selection_telemetry", {}),
        status.get("mutation_telemetry", {}),
        status.get("current_candidate", {}),
    )
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        for name in names:
            if container.get(name) is not None:
                return container[name]
    return default


def _sparkline(history: Sequence[Mapping[str, Any]], color: str) -> str:
    points = list(history[-240:])
    if len(points) < 2:
        return '<div class="waiting mini">Waiting for comparable heartbeats…</div>'
    coordinates: list[tuple[float, float]] = []
    for point in points:
        x_value = float(point.get("total_actions", 0) or 0)
        # The tiny vertical offsets keep equal tiers legible while preserving tier dominance.
        y_value = (
            float(point.get("fitness_tier", 0) or 0) * 1_000_000
            + float(point.get("maps_seen", 0) or 0) * 10_000
            + float(point.get("positions_seen", 0) or 0)
        )
        coordinates.append((x_value, y_value))
    min_x, max_x = coordinates[0][0], max(value[0] for value in coordinates)
    min_y, max_y = min(value[1] for value in coordinates), max(value[1] for value in coordinates)
    width, height, pad = 300, 58, 4
    span_x = max(max_x - min_x, 1)
    span_y = max(max_y - min_y, 1)
    rendered = " ".join(
        f"{pad + (x - min_x) / span_x * (width - 2 * pad):.1f},"
        f"{height - pad - (y - min_y) / span_y * (height - 2 * pad):.1f}"
        for x, y in coordinates
    )
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Best milestone progress by action count">'
        f'<polyline points="{rendered}" fill="none" stroke="{color}" stroke-width="3" '
        'stroke-linecap="round" stroke-linejoin="round" /></svg>'
    )


def _fitness_summary(value: Any) -> str:
    if not isinstance(value, (list, tuple)) or not value:
        return "waiting"
    return (
        "["
        + ", ".join(str(_number(item)) for item in value[:5])
        + (", …]" if len(value) > 5 else "]")
    )


def _lane_card(
    spec: Mapping[str, Any],
    status: Mapping[str, Any] | None,
    process: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    *,
    max_actions: int,
    duration_seconds: float,
    cache_token: str,
) -> str:
    lane_id = str(spec["lane_id"])
    label = str(spec.get("label", lane_id))
    selection = str(spec.get("selection_strategy", "unknown"))
    mutation = str(spec.get("mutation_profile", "unknown"))
    color = LANE_COLORS.get(lane_id, "#c9ff61")
    if status is None:
        process_state = "STARTING" if process.get("process_alive") else "WAITING"
        return f"""
        <article class="lane" style="--lane:{color}">
          <header><div><div class="coordinates">{html.escape(selection)} selection ·
            {html.escape(mutation)} mutation</div><h2>{html.escape(label)}</h2></div>
            <span class="state">{process_state}</span></header>
          <div class="waiting tall">The first child has not reported yet.</div>
        </article>"""

    state = str(status.get("state", "starting")).upper()
    actions = _number(status.get("total_actions"))
    evaluations = _number(status.get("evaluations"))
    action_progress = min(100, 100 * actions / max(max_actions, 1))
    elapsed = float(status.get("elapsed_seconds", 0) or 0)
    time_progress = min(100, 100 * elapsed / max(duration_seconds, 1))
    budget_progress = max(action_progress, time_progress)
    parent_id = str(status.get("current_parent_id") or "root")
    genome_id = str(status.get("current_genome_id") or "starting")
    selection_channel = str(
        _telemetry_value(
            status,
            "selection_channel",
            "parent_selection_channel",
            "channel",
            default=selection,
        )
    )
    mutation_channel = str(
        _telemetry_value(
            status,
            "mutation_channel",
            "mutation_scale",
            "profile_channel",
            default=mutation,
        )
    )
    lineage_depth = _number(
        _telemetry_value(status, "lineage_depth", "current_lineage_depth", default=0)
    )
    parent_fitness = _telemetry_value(
        status, "parent_fitness", "current_parent_fitness", default=[]
    )
    candidate_actions = _number(status.get("candidate_actions"))
    candidate_budget = max(_number(status.get("candidate_action_budget"), 1), 1)
    child_progress = min(100, 100 * candidate_actions / candidate_budget)
    return f"""
    <article class="lane" style="--lane:{color}">
      <header>
        <div><div class="coordinates">{html.escape(selection)} selection ·
          {html.escape(mutation)} mutation</div><h2>{html.escape(label)}</h2></div>
        <span class="state">{html.escape(state)}</span>
      </header>
      <a class="frame-link" href="{html.escape(lane_id)}/index.html">
        <img class="screen" src="{html.escape(lane_id)}/latest.png?v={html.escape(cache_token)}"
          alt="Latest frame from {html.escape(label)}" />
      </a>
      <div class="budget-line"><strong>{actions:,}</strong><span>{action_progress:.1f}% actions ·
        {_duration(elapsed)}</span></div>
      <div class="bar"><i style="width:{budget_progress:.2f}%"></i></div>
      <dl class="headline">
        <div><dt>Milestone tier</dt><dd>{_number(status.get("fitness_tier"))}</dd></div>
        <div><dt>Maps / positions</dt><dd>{_number(status.get("maps_seen"))} /
          {_number(status.get("positions_seen"))}</dd></div>
        <div><dt>Party / level</dt><dd>{_number(status.get("max_party_count"))} /
          {_number(status.get("max_party_level"))}</dd></div>
        <div><dt>Children / archive</dt><dd>{evaluations} /
          {_number(status.get("archive_cells"))}</dd></div>
        <div><dt>Pokédex seen / owned</dt><dd>{_number(status.get("pokedex_seen"))} /
          {_number(status.get("pokedex_owned"))}</dd></div>
        <div><dt>Speed</dt><dd>{float(status.get("actions_per_second", 0) or 0):,.0f}/s</dd></div>
      </dl>
      <div class="child">
        <div><span>Living child</span><code>{html.escape(genome_id)}</code></div>
        <div class="child-bar"><i style="width:{child_progress:.2f}%"></i></div>
        <div class="lineage"><span>parent <code>{html.escape(parent_id)}</code></span>
          <span>depth {lineage_depth}</span></div>
      </div>
      <dl class="telemetry">
        <div><dt>Parent channel</dt><dd>{html.escape(selection_channel)}</dd></div>
        <div><dt>Mutation channel</dt><dd>{html.escape(mutation_channel)}</dd></div>
        <div><dt>Parent fitness</dt><dd>{html.escape(_fitness_summary(parent_fitness))}</dd></div>
        <div><dt>Changed weights</dt><dd>{_number(status.get("mutated_parameters")):,}</dd></div>
      </dl>
      {_sparkline(history, color)}
      <a class="details" href="{html.escape(lane_id)}/index.html">Open full lineage dashboard →</a>
    </article>"""


def _leader_summary(
    specs: Sequence[Mapping[str, Any]], statuses: Mapping[str, Mapping[str, Any] | None]
) -> str:
    ranked: list[tuple[tuple[int, ...], str]] = []
    for spec in specs:
        lane_id = str(spec["lane_id"])
        status = statuses.get(lane_id)
        if not status:
            continue
        fitness = status.get("best_fitness")
        if isinstance(fitness, list) and fitness:
            rank = tuple(_number(item) for item in fitness)
        else:
            rank = (
                _number(status.get("fitness_tier")),
                _number(status.get("badge_count")),
                _number(status.get("maps_seen")),
                _number(status.get("positions_seen")),
            )
        ranked.append((rank, str(spec.get("label", lane_id))))
    if not ranked:
        return "No lane has reported yet"
    best = max(rank for rank, _label in ranked)
    leaders = [label for rank, label in ranked if rank == best]
    return f"{' + '.join(leaders)} · fitness {_fitness_summary(best)}"


def render_evolution_lab_dashboard(
    lab_status: Mapping[str, Any],
    lane_specs: Sequence[Mapping[str, Any]],
    statuses: Mapping[str, Mapping[str, Any] | None],
    histories: Mapping[str, Sequence[Mapping[str, Any]]],
) -> str:
    """Render a self-contained, script-free 2x3-capable comparison dashboard."""

    updated = str(lab_status.get("updated_at", "starting"))
    config = lab_status.get("config", {})
    if not isinstance(config, Mapping):
        config = {}
    max_actions = _number(config.get("max_actions_per_lane"), 1)
    duration_seconds = float(config.get("duration_seconds", 1) or 1)
    processes = lab_status.get("lanes", {})
    if not isinstance(processes, Mapping):
        processes = {}
    cards = "".join(
        _lane_card(
            spec,
            statuses.get(str(spec["lane_id"])),
            processes.get(str(spec["lane_id"]), {}),
            histories.get(str(spec["lane_id"]), []),
            max_actions=max_actions,
            duration_seconds=duration_seconds,
            cache_token=updated,
        )
        for spec in lane_specs
    )
    running = sum(
        bool(processes.get(str(spec["lane_id"]), {}).get("process_alive")) for spec in lane_specs
    )
    total_actions = sum(
        _number((statuses.get(str(spec["lane_id"])) or {}).get("total_actions"))
        for spec in lane_specs
    )
    total_evaluations = sum(
        _number((statuses.get(str(spec["lane_id"])) or {}).get("evaluations"))
        for spec in lane_specs
    )
    state = str(lab_status.get("state", "starting")).upper()
    leader = _leader_summary(lane_specs, statuses)
    seed_label = str(lab_status.get("seed_archive", {}).get("label", "sealed archive"))
    seed_contract = (
        "the same paired RNG seed"
        if bool(config.get("paired_seed", True))
        else "deterministic independent RNG seeds"
    )
    return f"""<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta http-equiv="refresh" content="5" />
  <title>Pokémon Red — Evolution 2×3 Lab</title>
  <style>
    :root {{ color-scheme:dark;--bg:#060914;--panel:#111725;--panel2:#0a101b;
      --ink:#f4f7ff;--muted:#98a5be;--line:#26324a }}
    * {{ box-sizing:border-box }} body {{ margin:0;color:var(--ink);font:14px/1.45
      ui-sans-serif,system-ui,sans-serif;background:radial-gradient(circle at 50% -20%,#263b70,
      var(--bg) 46%); }} main {{ width:min(1740px,calc(100% - 28px));margin:auto;padding:30px 0 60px }}
    .eyebrow {{ color:#b9c9ff;letter-spacing:.17em;font-size:.7rem;font-weight:900 }}
    h1 {{ font-size:clamp(2.3rem,5vw,5.5rem);line-height:.9;letter-spacing:-.06em;
      margin:.45rem 0 1rem }} .lede {{ color:var(--muted);font-size:1.05rem;max-width:950px }}
    .summary {{ display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin:20px 0 13px }}
    .summary div {{ border:1px solid var(--line);background:#0c1220;border-radius:13px;padding:10px 12px }}
    .summary span {{ display:block;color:var(--muted);font-size:.68rem }} .summary strong {{ font-size:1rem }}
    .leader {{ border:1px solid #4967a3;background:#101a31;border-radius:13px;padding:11px 13px;
      margin-bottom:17px }} .leader span {{ color:#9fbaff;text-transform:uppercase;font-size:.66rem;
      letter-spacing:.12em;font-weight:900;margin-right:8px }}
    .axis {{ display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;color:var(--muted);
      font-size:.7rem;text-align:center;text-transform:uppercase;letter-spacing:.1em;font-weight:850;
      margin:0 0 8px }}
    .matrix {{ display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px }}
    .lane {{ --lane:#fff;min-width:0;border:1px solid color-mix(in srgb,var(--lane) 43%,var(--line));
      background:linear-gradient(180deg,color-mix(in srgb,var(--lane) 7%,var(--panel)),var(--panel));
      border-radius:18px;padding:14px;box-shadow:0 18px 55px #0005 }}
    header {{ display:flex;justify-content:space-between;align-items:start;gap:8px;min-height:63px }}
    .coordinates {{ color:var(--lane);font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;
      font-weight:850 }} h2 {{ font-size:1.16rem;margin:.2rem 0 0 }} .state {{ color:var(--lane);
      border:1px solid currentColor;border-radius:99px;padding:4px 7px;font-size:.58rem;font-weight:900 }}
    .screen {{ display:block;width:100%;aspect-ratio:10/9;object-fit:contain;background:#03050a;
      border:1px solid var(--line);border-radius:10px;image-rendering:pixelated }} .frame-link {{ display:block }}
    .budget-line {{ display:flex;justify-content:space-between;align-items:baseline;margin-top:9px }}
    .budget-line strong {{ font-size:1.05rem }} .budget-line span {{ color:var(--muted);font-size:.68rem }}
    .bar,.child-bar {{ height:5px;background:#050810;border-radius:99px;overflow:hidden;margin:5px 0 10px }}
    .bar i,.child-bar i {{ display:block;height:100%;background:var(--lane) }}
    dl {{ margin:0;display:grid;grid-template-columns:repeat(3,1fr);gap:6px }} dl div {{ min-width:0;
      background:#080e18;border-radius:8px;padding:7px }} dt {{ color:var(--muted);font-size:.62rem }}
    dd {{ margin:2px 0 0;font-weight:780;overflow:hidden;text-overflow:ellipsis;white-space:nowrap }}
    .child {{ background:#090f1b;border:1px solid var(--line);border-radius:9px;padding:8px;margin:8px 0 }}
    .child>div:first-child,.lineage {{ display:flex;justify-content:space-between;gap:8px;color:var(--muted);
      font-size:.63rem }} code {{ color:var(--lane);overflow:hidden;text-overflow:ellipsis }}
    .child-bar {{ margin:6px 0 }} .telemetry {{ grid-template-columns:1fr 1fr }} .telemetry dd {{ font-size:.72rem }}
    .spark {{ display:block;width:100%;height:58px;background:#080e18;border-radius:8px;margin:8px 0 }}
    .details {{ color:var(--lane);text-decoration:none;font-size:.7rem;font-weight:780 }}
    .waiting {{ color:var(--muted);padding:22px }} .waiting.tall {{ min-height:370px }}
    .waiting.mini {{ padding:18px 8px;background:#080e18;border-radius:8px;margin:8px 0 }}
    .contract {{ margin-top:16px;color:var(--muted);border:1px solid var(--line);background:#0c1220;
      border-radius:14px;padding:14px }} .contract strong {{ color:var(--ink) }} footer {{ color:var(--muted);
      font-size:.68rem;margin-top:14px }}
    @media(max-width:1180px) {{ .matrix,.axis {{ grid-template-columns:repeat(2,minmax(0,1fr)) }}
      .axis {{ display:none }} .summary {{ grid-template-columns:1fr 1fr }} }}
    @media(max-width:650px) {{ .matrix {{ grid-template-columns:1fr }} .summary {{ grid-template-columns:1fr }} }}
  </style>
</head><body><main>
  <div class="eyebrow">LIVE LOCAL LAB · TWO SELECTION RULES × THREE MUTATION SCALES</div>
  <h1>Which descendants<br/>preserve useful accidents?</h1>
  <p class="lede">Six evolutionary branches inherit the same sealed collection of neural brains.
    Every individual still begins Pokémon Red at clean power-on. Rows change who becomes a parent;
    columns change how radically that parent is mutated.</p>
  <section class="summary">
    <div><span>Lab</span><strong>{html.escape(state)}</strong></div>
    <div><span>Living lanes</span><strong>{running} / {len(lane_specs)}</strong></div>
    <div><span>Combined evidence</span><strong>{total_actions:,} actions · {total_evaluations:,} children</strong></div>
    <div><span>Shared starting archive</span><strong>{html.escape(seed_label)}</strong></div>
  </section>
  <div class="leader"><span>Current headline</span>{html.escape(leader)}</div>
  <div class="axis"><span>Broad mutation</span><span>Gentle mutation</span><span>Multiscale mutation</span></div>
  <section class="matrix">{cards}</section>
  <section class="contract"><strong>Fair-comparison contract:</strong> identical archive, network,
    lifetime length, ROM revision, wall-clock ceiling, per-lane action ceiling, and
    {html.escape(seed_contract)}. Rankings are descriptive evidence from this engineering fork, not a
    fresh-seed confirmation and not proof that one method is universally superior.</section>
  <footer>Updated {html.escape(updated)} · No ROM bytes, save states, checkpoints, or raw traces are
    exposed by this local server.</footer>
</main></body></html>"""
