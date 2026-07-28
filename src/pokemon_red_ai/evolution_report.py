from __future__ import annotations

import html
from typing import Any


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _sparkline(history: list[dict[str, Any]], field: str) -> str:
    values = [float(item.get(field, 0)) for item in history[-500:]]
    if len(values) < 2:
        return '<div class="waiting">Waiting for population history…</div>'
    width, height, pad = 720, 100, 6
    maximum = max(values) or 1
    points = []
    for index, value in enumerate(values):
        x = pad + index / (len(values) - 1) * (width - 2 * pad)
        y = height - pad - value / maximum * (height - 2 * pad)
        points.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(field)}">'
        f'<polyline points="{" ".join(points)}" fill="none" stroke="#c9ff61" '
        'stroke-width="4" stroke-linecap="round" /></svg>'
    )


def _elite_rows(elites: list[dict[str, Any]]) -> str:
    if not elites:
        return (
            '<tr><td colspan="5" class="waiting">'
            "No child has completed a lifetime yet.</td></tr>"
        )
    return "".join(
        "<tr>"
        f'<td><code>{html.escape(str(elite.get("genome_id", "")))}</code></td>'
        f'<td>{int(elite.get("generation", 0))}</td>'
        f'<td>{html.escape(str(elite.get("descriptor", [])))}</td>'
        f'<td>{html.escape(str(elite.get("fitness", [])))}</td>'
        f'<td>{int(elite.get("metrics", {}).get("maps_seen", 0))} / '
        f'{int(elite.get("metrics", {}).get("max_party_count", 0))} / '
        f'{int(elite.get("metrics", {}).get("badges", 0))}</td>'
        "</tr>"
        for elite in elites[:24]
    )


def _genealogy_rows(records: list[dict[str, Any]]) -> str:
    completed = [record for record in records if record.get("kind") == "candidate_completed"][-24:]
    if not completed:
        return '<tr><td colspan="6" class="waiting">The first child is still living.</td></tr>'
    return "".join(
        "<tr>"
        f'<td>{int(record.get("generation", 0))}.{int(record.get("candidate_index", 0))}</td>'
        f'<td><code>{html.escape(str(record.get("genome_id", "")))}</code></td>'
        f'<td><code>{html.escape(str(record.get("parent_id") or "root"))}</code></td>'
        f'<td>{int(record.get("mutated_parameters", 0)):,}</td>'
        f'<td>{"SURVIVED" if record.get("archive_inserted") else "EXTINCT"}</td>'
        f'<td>{html.escape(str(record.get("descriptor", [])))}</td>'
        "</tr>"
        for record in reversed(completed)
    )


def render_evolution_dashboard(
    status: dict[str, Any],
    history: list[dict[str, Any]],
    genealogy: list[dict[str, Any]],
) -> str:
    state = html.escape(str(status.get("state", "starting")).upper())
    elapsed = float(status.get("elapsed_seconds", 0))
    duration = max(float(status.get("duration_seconds", 1)), 1)
    progress = min(100, elapsed / duration * 100)
    generation = int(status.get("generation", 0))
    candidate = int(status.get("candidate_index", 0)) + 1
    population = int(status.get("population_size", 0))
    candidate_actions = int(status.get("candidate_actions", 0))
    candidate_budget = max(int(status.get("candidate_action_budget", 1)), 1)
    child_progress = min(100, candidate_actions / candidate_budget * 100)
    genome_id = html.escape(str(status.get("current_genome_id", "starting")))
    parent_id = html.escape(str(status.get("current_parent_id") or "root genome"))
    return f"""<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta http-equiv="refresh" content="5" />
  <title>Evolutionary Explorer — Live Population</title>
  <style>
    :root {{ color-scheme:dark; --bg:#07100e; --panel:#101b18; --ink:#f3fff9;
      --muted:#9bb6aa; --line:#294139; --lime:#c9ff61; --cyan:#64e9dd }}
    * {{ box-sizing:border-box }} body {{ margin:0; background:radial-gradient(circle at 20% -10%,
      #244735,var(--bg) 42%); color:var(--ink); font:15px/1.5 ui-sans-serif,system-ui,sans-serif }}
    main {{ width:min(1280px,calc(100% - 28px));margin:auto;padding:36px 0 70px }}
    .eyebrow {{ color:var(--lime);letter-spacing:.16em;font-size:.72rem;font-weight:850 }}
    h1 {{ font-size:clamp(2.4rem,6vw,5.5rem);line-height:.92;letter-spacing:-.055em;
      margin:.45rem 0 1rem }} h2 {{ margin:0 0 12px }}
    .lede {{ max-width:900px;color:var(--muted);font-size:1.08rem }}
    .summary {{ display:flex;gap:9px;flex-wrap:wrap;margin:20px 0 }}
    .pill {{ border:1px solid var(--line);background:#0b1512;border-radius:99px;padding:7px 11px }}
    .grid {{ display:grid;grid-template-columns:1.1fr .9fr;gap:16px }}
    .panel {{ background:linear-gradient(180deg,#14231e,var(--panel));border:1px solid var(--line);
      border-radius:18px;padding:18px;box-shadow:0 20px 60px #0005 }}
    .screen {{ width:100%;max-height:440px;object-fit:contain;image-rendering:pixelated;
      background:#020604;border-radius:12px;border:1px solid var(--line) }}
    .bar {{ height:8px;background:#050a08;border-radius:99px;overflow:hidden;margin:7px 0 16px }}
    .bar i {{ display:block;height:100%;background:linear-gradient(90deg,var(--lime),var(--cyan)) }}
    dl {{ display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 }}
    dl div {{ background:#091310;padding:10px;border-radius:10px }} dt {{ color:var(--muted);
      font-size:.69rem }} dd {{ margin:2px 0 0;font-weight:800 }}
    code {{ color:var(--cyan);font-size:.8em }} svg {{ width:100%;background:#08110e;
      border-radius:12px;margin-top:8px }} .wide {{ grid-column:1/-1 }}
    table {{ width:100%;border-collapse:collapse;font-size:.82rem }} th,td {{ text-align:left;
      padding:9px;border-bottom:1px solid var(--line);vertical-align:top }}
    th {{ color:var(--muted) }}
    .waiting {{ color:var(--muted);padding:20px }} .contract {{ color:var(--muted) }}
    @media(max-width:850px) {{ .grid {{ grid-template-columns:1fr }}
      dl {{ grid-template-columns:1fr 1fr }} }}
  </style>
</head><body><main>
  <div class="eyebrow">LIVE · CLEAN-START NEUROEVOLUTION · DEVELOPMENT</div>
  <h1>Useful accidents<br/>have descendants.</h1>
  <p class="lede">One fixed neural child reads pixels and acts for a bounded lifetime. The sealed
    referee decides whether its genome joins the diverse archive. The next child inherits weights,
    never RAM or game progress.</p>
  <div class="summary"><span class="pill">{state}</span>
    <span class="pill">Elapsed {_duration(elapsed)} · {progress:.1f}%</span>
    <span class="pill">Generation {generation}</span>
    <span class="pill">Child {candidate}/{population}</span>
    <span class="pill">{int(status.get('evaluations', 0)):,} evaluated</span></div>
  <section class="grid">
    <article class="panel"><img class="screen"
      src="latest.png?v={html.escape(str(status.get('updated_at', '')))}"
      alt="Latest rendered frame from the living neural child" /></article>
    <article class="panel"><h2>Current child</h2>
      <div><code>{genome_id}</code> ← <code>{parent_id}</code></div>
      <div class="bar"><i style="width:{child_progress:.2f}%"></i></div>
      <dl>
        <div><dt>Lifetime actions</dt><dd>{candidate_actions:,} / {candidate_budget:,}</dd></div>
        <div><dt>Mutation σ</dt><dd>{float(status.get('mutation_sigma', 0)):.3f}</dd></div>
        <div><dt>Changed weights</dt><dd>{int(status.get('mutated_parameters', 0)):,}</dd></div>
        <div><dt>Archive cells</dt><dd>{int(status.get('archive_cells', 0)):,}</dd></div>
        <div><dt>Best fitness tier</dt><dd>{int(status.get('fitness_tier', 0))}</dd></div>
        <div><dt>Speed</dt><dd>{float(status.get('actions_per_second', 0)):,.1f}/s</dd></div>
        <div><dt>Best maps</dt><dd>{int(status.get('maps_seen', 0))}</dd></div>
        <div><dt>Best party / level</dt>
          <dd>{int(status.get('max_party_count', 0))} /
            {int(status.get('max_party_level', 0))}</dd></div>
        <div><dt>Pokédex seen / owned</dt>
          <dd>{int(status.get('pokedex_seen', 0))} /
            {int(status.get('pokedex_owned', 0))}</dd></div>
      </dl></article>
    <article class="panel wide"><h2>Population progress</h2>
      {_sparkline(history, 'fitness_tier')}</article>
    <article class="panel wide"><h2>Surviving elites</h2><table><thead><tr><th>Genome</th>
      <th>Gen</th><th>Behavior cell</th><th>Fitness vector</th><th>Maps / party / badges</th>
      </tr></thead><tbody>{_elite_rows(list(status.get('elites', [])))}</tbody></table></article>
    <article class="panel wide"><h2>Recent family history</h2><table><thead><tr><th>Child</th>
      <th>Genome</th><th>Parent</th><th>Changed</th><th>Fate</th><th>Behavior cell</th>
      </tr></thead><tbody>{_genealogy_rows(genealogy)}</tbody></table></article>
    <article class="panel wide contract"><strong>Evidence boundary:</strong> every child starts at
      clean power-on. Neural inputs are the 20×18 quantized rendered screen and previous action.
      RAM is used only after actions by the sealed selector and dashboard. No child changes weights
      during its lifetime; learning occurs through ancestry between lifetimes.</article>
  </section>
</main></body></html>"""
