from __future__ import annotations

import html
from typing import Any


def _number(value: int | float) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}"


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _line_chart(history: list[dict[str, int | float]]) -> str:
    if len(history) < 2:
        return '<div class="chart-empty">The first progress points are being collected.</div>'
    width, height, padding = 720, 220, 24
    maximum_x = max(float(point["elapsed_seconds"]) for point in history) or 1
    maximum_y = max(int(point["unique_visual_cells"]) for point in history) or 1
    points = []
    for point in history:
        x = padding + (float(point["elapsed_seconds"]) / maximum_x) * (width - padding * 2)
        y = height - padding - (
            int(point["unique_visual_cells"]) / maximum_y
        ) * (height - padding * 2)
        points.append(f"{x:.1f},{y:.1f}")
    return f"""
    <svg class="chart" viewBox="0 0 {width} {height}" role="img"
         aria-label="Unique visual cells discovered over elapsed time">
      <line x1="{padding}" y1="{height - padding}" x2="{width - padding}"
            y2="{height - padding}" class="axis" />
      <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}"
            class="axis" />
      <polyline points="{' '.join(points)}" class="curve" />
      <text x="{padding}" y="{height - 5}" class="tick">start</text>
      <text x="{width - padding}" y="{height - 5}" text-anchor="end" class="tick">
        {_duration(maximum_x)}
      </text>
      <text x="{padding + 5}" y="{padding + 12}" class="tick">{maximum_y:,} cells</text>
    </svg>
    """


def _action_bars(action_counts: dict[str, int]) -> str:
    maximum = max(action_counts.values(), default=1)
    rows = []
    for action, count in sorted(action_counts.items()):
        width = 100 * count / maximum
        rows.append(
            f"""
            <div class="action-row">
              <span>{html.escape(action.upper())}</span>
              <div class="bar-track"><div class="bar" style="width:{width:.2f}%"></div></div>
              <strong>{count:,}</strong>
            </div>
            """
        )
    return "".join(rows) or '<p class="muted">No actions recorded yet.</p>'


def _gallery(screenshots: list[dict[str, Any]]) -> str:
    cards = []
    for shot in screenshots[-12:]:
        source = html.escape(str(shot["file"]), quote=True)
        label = html.escape(str(shot["label"]))
        cards.append(
            f"""
            <figure>
              <img src="{source}" alt="{label}" width="320" height="288" loading="lazy" />
              <figcaption>{label}<small>after {int(shot['action']):,} actions</small></figcaption>
            </figure>
            """
        )
    return "".join(cards)


def render_blind_dashboard(
    status: dict[str, Any],
    history: list[dict[str, int | float]],
    screenshots: list[dict[str, Any]],
) -> str:
    state = str(status["state"])
    state_label = "RUNNING" if state == "running" else "FINISHED"
    state_class = "running" if state == "running" else "finished"
    snapshot_assisted = "yes" if status["snapshot_assisted"] else "no"
    continuous = "yes" if status["continuous_playthrough"] else "no"
    archive_value = (
        _number(int(status["archive_cells"]))
        if status["mode"] == "archivist"
        else "not used"
    )
    stop_reason = status.get("stop_reason") or "bounded run is active"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{html.escape(str(status['run_name']))}</title>
  <style>
    :root {{ color-scheme: dark; --ink:#eef4ef; --muted:#9cafaa; --panel:#151e1d;
      --line:#2a3b38; --accent:#74e0aa; --accent2:#f7d774; --bg:#09100f; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:radial-gradient(circle at 20% 0,#17322a 0,var(--bg) 38%);
      color:var(--ink); font:16px/1.55 ui-sans-serif,system-ui,sans-serif; }}
    main {{ width:min(1120px,calc(100% - 32px)); margin:0 auto; padding:48px 0 72px; }}
    .eyebrow {{ color:var(--accent); letter-spacing:.12em; text-transform:uppercase;
      font-size:.75rem; font-weight:800; }}
    h1 {{ font-size:clamp(2rem,6vw,4.6rem); line-height:.98; max-width:900px;
      margin:.35rem 0 1rem; letter-spacing:-.05em; }}
    .lede {{ color:var(--muted); max-width:760px; font-size:1.12rem; }}
    .badge {{ display:inline-block; border:1px solid var(--accent); color:var(--accent);
      padding:.3rem .65rem; border-radius:999px; font-weight:800; font-size:.72rem;
      letter-spacing:.1em; }}
    .badge.finished {{ color:var(--accent2); border-color:var(--accent2); }}
    .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:32px 0; }}
    .card,.panel {{ background:color-mix(in srgb,var(--panel) 94%,transparent);
      border:1px solid var(--line); border-radius:18px; box-shadow:0 18px 50px #0004; }}
    .card {{ padding:20px; }} .card span {{ color:var(--muted); display:block; font-size:.8rem; }}
    .card strong {{ font-size:1.7rem; display:block; margin-top:6px; }}
    .panel {{ padding:24px; margin-top:16px; }}
    .panel h2 {{ margin:0 0 8px; font-size:1.2rem; }}
    .truth {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
    .truth div {{ background:#0d1514; border-radius:12px; padding:14px; }}
    .truth small {{ display:block; color:var(--muted); }}
    .truth b {{ color:var(--accent); }}
    .chart {{ display:block; width:100%; height:auto; margin-top:12px; }}
    .axis {{ stroke:var(--line); stroke-width:1; }} .curve {{ fill:none; stroke:var(--accent);
      stroke-width:4; stroke-linecap:round; stroke-linejoin:round; }}
    .tick {{ fill:var(--muted); font-size:12px; }}
    .chart-empty {{ color:var(--muted); padding:60px 0; }}
    .two {{ display:grid; grid-template-columns:1.35fr 1fr; gap:16px; }}
    .action-row {{ display:grid; grid-template-columns:64px 1fr 70px; align-items:center;
      gap:10px; margin:9px 0; font-size:.8rem; }}
    .action-row strong {{ text-align:right; }} .bar-track {{ height:8px; background:#0a1110;
      border-radius:20px; overflow:hidden; }} .bar {{ height:100%; background:var(--accent2); }}
    .gallery {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
    figure {{ margin:0; background:#0a1110; border:1px solid var(--line); border-radius:14px;
      overflow:hidden; }}
    figure img {{ display:block; width:100%; height:auto; image-rendering:pixelated; }}
    figcaption {{ padding:10px; font-size:.82rem; }}
    figcaption small {{ color:var(--muted); display:block; }}
    .latest {{ width:min(480px,100%); image-rendering:pixelated; border:1px solid var(--line);
      border-radius:12px; }} code {{ color:var(--accent2); }} .muted {{ color:var(--muted); }}
    footer {{ color:var(--muted); margin-top:28px; font-size:.82rem; }}
    @media (max-width:800px) {{ .grid,.gallery {{ grid-template-columns:repeat(2,1fr); }}
      .two,.truth {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body><main>
  <div class="eyebrow">Pokémon Red · game-naive experiment</div>
  <h1>{html.escape(str(status['run_name']))}</h1>
  <p class="lede">The button chooser is uniformly random. In Archivist mode, a separate trainer
    uses coarse rendered pixels, novelty membership, and archive visit counts to preserve and
    revisit screens—without a map, objective, walkthrough, labels, or Pokémon knowledge.</p>
  <span class="badge">DEVELOPMENT</span>
  <span class="badge {state_class}">{state_label}</span>

  <section class="grid" aria-label="Run summary">
    <div class="card"><span>Elapsed</span>
      <strong>{_duration(float(status['elapsed_seconds']))}</strong></div>
    <div class="card"><span>Controller actions</span>
      <strong>{_number(int(status['total_actions']))}</strong></div>
    <div class="card"><span>Visual cells found</span>
      <strong>{_number(int(status['unique_visual_cells']))}</strong></div>
    <div class="card"><span>Discovery archive</span><strong>{archive_value}</strong></div>
  </section>

  <section class="panel">
    <h2>The experimental contract</h2>
    <div class="truth">
      <div><small>Button chooser</small><b>Seeded uniform random</b></div>
      <div><small>Trainer input</small><b>Coarse rendered pixels</b></div>
      <div><small>Semantic RAM used</small><b>No</b></div>
    </div>
    <p class="muted">Start: clean power-on · Pretrained components: none ·
      Human demonstrations: none</p>
    <p class="muted">Snapshot-assisted: <strong>{snapshot_assisted}</strong>
      · Archive restores: <strong>{int(status['archive_restores']):,}</strong> ·
      Continuous playthrough: <strong>{continuous}</strong></p>
  </section>

  <div class="two">
    <section class="panel">
      <h2>Discovery over time</h2>
      <p class="muted">Growth means the trainer is encountering coarse screen patterns it has
        not previously counted as definitely novel.</p>
      {_line_chart(history)}
    </section>
    <section class="panel">
      <h2>Button distribution</h2>
      {_action_bars(status['action_counts'])}
    </section>
  </div>

  <section class="panel">
    <h2>Latest view</h2>
    <img class="latest" src="latest.png" alt="The agent's latest rendered Game Boy screen" />
    <p class="muted">Speed: {_number(float(status['actions_per_second']))} actions/s ·
      Novelty rate: {100 * float(status['novelty_rate']):.2f}% ·
      Stop state: {html.escape(str(stop_reason))}</p>
  </section>

  <section class="panel">
    <h2>Discovery reel</h2>
    <div class="gallery">{_gallery(screenshots)}</div>
  </section>
  <footer>Generated locally from bounded run counters and rendered screenshots. The dashboard
    contains no ROM, save-state, RAM value, remote script, or model-generated game action.</footer>
</main></body></html>"""
