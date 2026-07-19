from __future__ import annotations

import html
from typing import Any

MODE_ORDER = ("monkey", "curious", "outcome", "conventional")
MODE_LABELS = {
    "monkey": "Pure Monkey",
    "curious": "Visually Curious",
    "outcome": "Outcome-Rewarded",
    "conventional": "Conventional Agent",
}
MODE_SUBTITLES = {
    "monkey": "Pixels observed · no reward",
    "curious": "Pixels observed · visual novelty reward",
    "outcome": "Pixels observed · semantic outcome reward",
    "conventional": "Pixels + RAM observed · explicit objectives",
}
MODE_COLORS = {
    "monkey": "#f2c14e",
    "curious": "#55c1ff",
    "outcome": "#80e27e",
    "conventional": "#ff7f9f",
}


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _sparkline(points: list[dict[str, Any]], field: str, color: str) -> str:
    if len(points) > 500:
        stride = (len(points) + 499) // 500
        points = points[::stride]
    values = [
        (float(point.get("elapsed_seconds", 0)), float(point.get(field, 0))) for point in points
    ]
    if len(values) < 2:
        return '<div class="waiting">Collecting the first progress points…</div>'
    width, height, pad = 420, 96, 6
    maximum_x = max(point[0] for point in values) or 1
    maximum_y = max(point[1] for point in values) or 1
    coordinates = []
    for x_value, y_value in values:
        x = pad + x_value / maximum_x * (width - 2 * pad)
        y = height - pad - y_value / maximum_y * (height - 2 * pad)
        coordinates.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(field)} over time">'
        f'<polyline points="{" ".join(coordinates)}" fill="none" stroke="{color}" '
        'stroke-width="4" stroke-linecap="round" stroke-linejoin="round" /></svg>'
    )


def _agent_card(
    mode: str,
    status: dict[str, Any] | None,
    history: list[dict[str, Any]],
    cache_token: str,
) -> str:
    label = MODE_LABELS[mode]
    subtitle = MODE_SUBTITLES[mode]
    color = MODE_COLORS[mode]
    if status is None:
        return f"""
        <article class="agent" style="--agent:{color}">
          <header><div><h2>{label}</h2><p>{subtitle}</p></div>
            <span class="state">STARTING</span></header>
          <div class="waiting tall">Waiting for the first heartbeat…</div>
        </article>
        """
    state = str(status.get("state", "starting")).upper()
    elapsed = float(status.get("elapsed_seconds", 0))
    duration = max(float(status.get("duration_seconds", 1)), 1)
    progress = min(100, 100 * elapsed / duration)
    reward = float(status.get("reward_total", 0))
    image = f"{mode}/latest.png?v={html.escape(cache_token, quote=True)}"
    return f"""
    <article class="agent" style="--agent:{color}">
      <header>
        <div><h2>{label}</h2><p>{subtitle}</p></div>
        <span class="state">{html.escape(state)}</span>
      </header>
      <a href="{mode}/index.html"><img class="screen" src="{image}"
        alt="Latest frame from {html.escape(label)}" /></a>
      <div class="time"><strong>{_duration(elapsed)}</strong><span>{progress:.1f}%</span></div>
      <div class="progress"><i style="width:{progress:.2f}%"></i></div>
      <dl>
        <div><dt>Actions</dt><dd>{int(status.get("total_actions", 0)):,}</dd></div>
        <div><dt>Visual cells</dt><dd>{int(status.get("unique_visual_cells", 0)):,}</dd></div>
        <div><dt>Reward</dt><dd>{reward:,.2f}</dd></div>
        <div><dt>Speed</dt><dd>{float(status.get("actions_per_second", 0)):,.1f}/s</dd></div>
        <div><dt>Maps rewarded</dt><dd>{int(status.get("maps_seen", 0)):,}</dd></div>
        <div><dt>Party / badges</dt><dd>{int(status.get("max_party_count", 0)):,} /
          {int(status.get("badge_count", 0)):,}</dd></div>
        <div><dt>Learning updates</dt><dd>{int(status.get("learning_updates", 0)):,}</dd></div>
        <div><dt>Replay / important</dt><dd>{int(status.get("replay_transitions", 0)):,} /
          {int(status.get("important_replay_transitions", 0)):,}</dd></div>
      </dl>
      <div class="chart-label">Visual discovery</div>
      {_sparkline(history, "unique_visual_cells", color)}
      <a class="details" href="{mode}/index.html">Open this agent’s full dashboard →</a>
    </article>
    """


def render_arena_dashboard(
    arena_status: dict[str, Any],
    statuses: dict[str, dict[str, Any] | None],
    histories: dict[str, list[dict[str, Any]]],
) -> str:
    updated = str(arena_status.get("updated_at", "starting"))
    cards = "".join(
        _agent_card(mode, statuses.get(mode), histories.get(mode, []), updated)
        for mode in MODE_ORDER
    )
    running = sum(
        statuses.get(mode, {}).get("state") == "running"
        for mode in MODE_ORDER
        if statuses.get(mode)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta http-equiv="refresh" content="5" />
  <title>Pokémon Red — Four-Agent Arena</title>
  <style>
    :root {{ color-scheme:dark; --bg:#070a12; --panel:#111724; --ink:#f4f7ff;
      --muted:#98a4bd; --line:#263149; }}
    * {{ box-sizing:border-box }}
    body {{ margin:0; background:radial-gradient(circle at 50% -20%,#24345d,var(--bg) 45%);
      color:var(--ink); font:15px/1.5 ui-sans-serif,system-ui,sans-serif }}
    main {{ width:min(1540px,calc(100% - 28px)); margin:auto; padding:34px 0 64px }}
    .eyebrow {{ color:#9eb8ff; letter-spacing:.15em; font-size:.72rem; font-weight:800 }}
    h1 {{ font-size:clamp(2.2rem,5vw,5rem); letter-spacing:-.055em; line-height:.95;
      margin:.4rem 0 1rem }}
    .lede {{ max-width:880px; color:var(--muted); font-size:1.08rem }}
    .summary {{ display:flex; flex-wrap:wrap; gap:10px; margin:20px 0 28px }}
    .pill {{ padding:7px 12px; border:1px solid var(--line); border-radius:999px;
      background:#0c111c; color:var(--muted) }}
    .arena {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px }}
    .agent {{ --agent:#fff;
      background:linear-gradient(180deg,color-mix(in srgb,var(--agent) 8%,var(--panel)),
        var(--panel));
      border:1px solid color-mix(in srgb,var(--agent) 40%,var(--line)); border-radius:20px;
      padding:16px; min-width:0; box-shadow:0 20px 70px #0005 }}
    header {{ display:flex; justify-content:space-between; gap:8px; align-items:start;
      min-height:76px }}
    h2 {{ margin:0; font-size:1.28rem }}
    header p {{ color:var(--muted); margin:.2rem 0 0; font-size:.76rem }}
    .state {{ color:var(--agent); border:1px solid currentColor; border-radius:999px;
      font-size:.61rem; padding:4px 7px; font-weight:900; letter-spacing:.08em }}
    .screen {{ display:block; width:100%; aspect-ratio:10/9; object-fit:contain; background:#05070b;
      image-rendering:pixelated; border-radius:12px; border:1px solid var(--line) }}
    .time {{ display:flex; justify-content:space-between; margin-top:12px }}
    .time span {{ color:var(--muted) }}
    .progress {{ height:6px; background:#080b12; border-radius:99px; overflow:hidden;
      margin:6px 0 14px }}
    .progress i {{ display:block; height:100%; background:var(--agent) }}
    dl {{ display:grid; grid-template-columns:1fr 1fr; gap:7px; margin:0 }}
    dl div {{ background:#090e18; padding:9px; border-radius:10px }}
    dt {{ color:var(--muted);font-size:.68rem }}
    dd {{ margin:2px 0 0; font-weight:750 }}
    .chart-label {{ color:var(--muted);font-size:.7rem;margin-top:14px }}
    .spark {{ width:100%; display:block; background:#090e18; border-radius:10px;
      margin:5px 0 12px }}
    .details {{ color:var(--agent); text-decoration:none; font-size:.76rem; font-weight:750 }}
    .waiting {{ color:var(--muted); padding:28px 0 }} .tall {{ min-height:330px }}
    .contract {{ margin-top:18px; padding:18px; background:#0d131f; border:1px solid var(--line);
      border-radius:16px; color:var(--muted) }} .contract strong {{ color:var(--ink) }}
    footer {{ color:var(--muted);font-size:.75rem;margin-top:20px }}
    @media(max-width:1180px) {{ .arena {{ grid-template-columns:repeat(2,1fr) }} }}
    @media(max-width:650px) {{ .arena {{ grid-template-columns:1fr }} }}
  </style>
</head>
<body><main>
  <div class="eyebrow">LIVE LOCAL EXPERIMENT · FOUR INFORMATION BOUNDARIES</div>
  <h1>Four ways to play Pokémon Red.</h1>
  <p class="lede">Every lane begins from power-on. Moving left to right adds guidance: chance,
    visual curiosity, outcome rewards, then privileged observations and explicit objectives.</p>
  <div class="summary">
    <span class="pill">Arena:
      {html.escape(str(arena_status.get("state", "starting")).upper())}</span>
    <span class="pill">Agents running: {running}/4</span>
    <span class="pill">Same ROM revision</span><span class="pill">Local execution</span>
    <span class="pill">Updated: {html.escape(updated)}</span>
  </div>
  <section class="arena">{cards}</section>
  <section class="contract"><strong>How to read this:</strong> reward totals are meaningful only
    within an agent’s declared reward scheme. Compare game progress through the sealed referee and
    compare discovery both by equal wall time and equal action count. Click a live frame for that
    agent’s complete trace dashboard.</section>
  <footer>No ROM bytes or save states are served. This server binds only to this Mac.</footer>
</main></body></html>"""
