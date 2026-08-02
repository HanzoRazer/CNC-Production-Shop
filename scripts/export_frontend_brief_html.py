#!/usr/bin/env python3
"""Render the audio front-end spec as a styled HTML brief for handover.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

Companion to export_frontend_brief.py. Same governed record, same content, but
built to be read rather than diffed — the markdown is for the repo, this is
what goes to a PCB designer who has never seen this project.

    python scripts/export_frontend_brief_html.py [--out PATH]

Both exporters read the fixture directly, so neither can drift from the other:
there is no markdown-to-HTML step in which content could be lost.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "fixtures" / "subassemblies" / "sg_audio_frontend_v1.json"
REGISTER = ROOT / "fixtures" / "geometry" / "smart_guitar_component_register_v1.json"
DEFAULT_OUT = ROOT / "exports" / "subassemblies" / "sg_audio_frontend_brief.html"

CRITICALITY = {
    "shippable_blocker": ("Blocker", "blocker"),
    "high": ("High", "high"),
    "medium": ("Medium", "medium"),
    "low": ("Low", "low"),
}

STYLE = """
:root {
  --paper:#F6F7F9; --surface:#FFFFFF; --ink:#131820; --muted:#59636E;
  --rule:#DBE1E7; --rule-soft:#EAEEF2; --accent:#8A6A1F; --accent-soft:#F0E7D0;
  --blocker:#A72A20; --blocker-soft:#F7E2DF;
  --serif: "Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono: ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper:#101418; --surface:#171C22; --ink:#E7ECF1; --muted:#99A5B0;
    --rule:#272F37; --rule-soft:#1E252C; --accent:#CFA648; --accent-soft:#2A2313;
    --blocker:#EE8479; --blocker-soft:#331916;
  }
}
:root[data-theme="dark"] {
  --paper:#101418; --surface:#171C22; --ink:#E7ECF1; --muted:#99A5B0;
  --rule:#272F37; --rule-soft:#1E252C; --accent:#CFA648; --accent-soft:#2A2313;
  --blocker:#EE8479; --blocker-soft:#331916;
}
:root[data-theme="light"] {
  --paper:#F6F7F9; --surface:#FFFFFF; --ink:#131820; --muted:#59636E;
  --rule:#DBE1E7; --rule-soft:#EAEEF2; --accent:#8A6A1F; --accent-soft:#F0E7D0;
  --blocker:#A72A20; --blocker-soft:#F7E2DF;
}
* { box-sizing:border-box; }
body {
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:16.5px; line-height:1.62;
  -webkit-font-smoothing:antialiased;
}
.wrap { max-width:53rem; margin:0 auto; padding:3rem 1.5rem 6rem; }
.masthead { border-bottom:2px solid var(--ink); padding-bottom:1.5rem; }
.eyebrow {
  font-family:var(--mono); font-size:.72rem; letter-spacing:.14em;
  text-transform:uppercase; color:var(--accent); margin:0 0 .9rem;
}
h1 {
  font-family:var(--serif); font-weight:600; font-size:clamp(2rem,5vw,2.9rem);
  line-height:1.1; letter-spacing:-.015em; margin:0 0 1rem; text-wrap:balance;
}
.meta {
  display:flex; flex-wrap:wrap; gap:.45rem .5rem; align-items:center;
  font-family:var(--mono); font-size:.78rem; font-variant-numeric:tabular-nums;
}
.chip {
  border:1px solid var(--rule); padding:.2rem .55rem; color:var(--muted);
  white-space:nowrap;
}
.chip.strong { border-color:var(--accent); color:var(--accent); }
.counts {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(7.5rem,1fr));
  gap:1px; background:var(--rule); border:1px solid var(--rule); margin:2rem 0 0;
}
.count { background:var(--surface); padding:.9rem 1rem; }
.count b {
  display:block; font-family:var(--mono); font-size:1.6rem; font-weight:600;
  font-variant-numeric:tabular-nums; line-height:1.1;
}
.count.flag b { color:var(--blocker); }
.count span {
  display:block; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase;
  color:var(--muted); margin-top:.3rem;
}
.notice {
  border-left:3px solid var(--accent); background:var(--accent-soft);
  padding:.9rem 1.1rem; margin:2rem 0 0; font-size:.92rem;
}
.notice p { margin:0; }
.notice p + p { margin-top:.5rem; }
h2 {
  font-family:var(--serif); font-weight:600; font-size:1.6rem; letter-spacing:-.01em;
  margin:3.5rem 0 .3rem; padding-top:1.4rem; border-top:1px solid var(--rule);
  text-wrap:balance;
}
h2 .num {
  font-family:var(--mono); font-size:.8rem; color:var(--accent);
  display:block; margin-bottom:.45rem; letter-spacing:.1em;
}
h3 { font-size:1rem; letter-spacing:.02em; margin:2rem 0 .5rem; }
p { margin:.85rem 0; }
.lede { color:var(--muted); margin-top:.6rem; }
ul { padding-left:1.1rem; margin:.85rem 0; }
li { margin:.5rem 0; }
code, .mono { font-family:var(--mono); font-size:.86em; font-variant-numeric:tabular-nums; }
.scroll { overflow-x:auto; margin:1.2rem 0; border:1px solid var(--rule); }
table { border-collapse:collapse; width:100%; min-width:22rem; background:var(--surface); }
th, td {
  text-align:left; padding:.6rem .9rem; border-bottom:1px solid var(--rule-soft);
  font-size:.9rem; vertical-align:top;
}
th {
  font-size:.7rem; letter-spacing:.09em; text-transform:uppercase; color:var(--muted);
  font-weight:600; border-bottom:1px solid var(--rule);
}
td.val {
  font-family:var(--mono); font-variant-numeric:tabular-nums; text-align:right;
  white-space:nowrap;
}
tr:last-child td { border-bottom:none; }
.req { border-top:1px solid var(--rule); padding:1.4rem 0 .4rem; }
.req:first-of-type { border-top:none; }
.req-head { display:flex; flex-wrap:wrap; gap:.6rem; align-items:baseline; }
.req-id { font-family:var(--mono); font-weight:600; font-size:.95rem; }
.pill {
  font-family:var(--mono); font-size:.66rem; letter-spacing:.11em; text-transform:uppercase;
  padding:.18rem .5rem; border:1px solid var(--rule); color:var(--muted);
}
.pill.blocker { color:var(--blocker); border-color:var(--blocker); background:var(--blocker-soft); }
.why { color:var(--muted); font-size:.92rem; }
.why b { color:var(--ink); font-weight:600; }
.acc { border-top:1px solid var(--rule); padding:1.3rem 0; }
.acc-grid { display:grid; gap:.55rem; margin-top:.7rem; }
.acc-row { display:grid; grid-template-columns:6.5rem 1fr; gap:.9rem; font-size:.9rem; }
.acc-row dt {
  font-family:var(--mono); font-size:.68rem; letter-spacing:.1em; text-transform:uppercase;
  color:var(--muted); padding-top:.18rem;
}
.acc-row dd { margin:0; }
@media (max-width:34rem) { .acc-row { grid-template-columns:1fr; gap:.15rem; } }
.foot {
  margin-top:4rem; padding-top:1.2rem; border-top:2px solid var(--ink);
  font-size:.82rem; color:var(--muted);
}
a { color:var(--accent); }
a:focus-visible, summary:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
"""


def esc(text: object) -> str:
    return html.escape(str(text), quote=False)


def render(spec: dict, register: dict) -> str:
    dc = spec["document_control"]
    env = spec["envelope"]
    el = spec["electrical"]
    reqs = spec["requirements"]
    blockers = [r for r in reqs if r["criticality"] == "shippable_blocker"]
    board = next(
        (c for c in register["components"] if c["component_id"] == spec["component_id"]),
        None,
    )

    o: list[str] = []
    w = o.append
    w(f"<title>{esc(spec['subassembly_name'])} — {esc(dc['document_class'].upper())} "
      f"Rev {esc(dc['revision'])}</title>")
    w(f"<style>{STYLE}</style>")
    w('<div class="wrap">')

    # Masthead
    w('<header class="masthead">')
    w(f'<p class="eyebrow">{esc(spec["spec_id"])}</p>')
    w(f"<h1>{esc(spec['subassembly_name'])}</h1>")
    w('<div class="meta">')
    w(f'<span class="chip strong">{esc(dc["document_class"].upper())} — not a tender</span>')
    w(f'<span class="chip">Rev {esc(dc["revision"])}</span>')
    w(f'<span class="chip">Issued {esc(dc["issued"])}</span>')
    w(f'<span class="chip">Status: {esc(spec["status"])}</span>')
    w(f'<span class="chip">Dimensions: {esc(spec["units"])}</span>')
    w("</div></header>")

    w('<div class="counts">')
    for value, label, flag in (
        (len(reqs), "Requirements", False),
        (len(blockers), "Shippable blockers", True),
        (len(spec["interfaces"]), "Interfaces", False),
        (len(spec["acceptance"]), "Acceptance tests", False),
        (len(spec["open_questions"]), "Open questions", True),
    ):
        w(f'<div class="count{" flag" if flag else ""}"><b>{value}</b><span>{label}</span></div>')
    w("</div>")

    w('<div class="notice">')
    w(f"<p><b>This is an {esc(dc['document_class'].upper())}, not a tender.</b> It exists to "
      f"shortlist designers and cost the work. Commercial terms including IP transfer are "
      f"{'in' if dc.get('commercial_terms_in_scope') else 'out of'} scope at this revision.</p>")
    w(f"<p>Change requests: {esc(dc['change_contact'])}</p>")
    w("</div>")

    w('<p class="lede">This brief carries the <b>mechanical envelope, system interfaces and '
      "behavioural requirements</b> that come from the instrument. It deliberately does not "
      "specify circuit topology, part numbers or component values — those are yours to choose "
      "against these constraints.</p>")

    # 1 Form factor
    ff = spec["form_factor"]
    w('<h2><span class="num">01</span>Form factor</h2>')
    w(f"<p><b>{esc(ff['standard'])}</b></p>")
    w(f"<p>Mounting: {esc(ff['mounting'])}</p>")
    w(f"<p>{esc(ff['stacking'])}</p>")
    w(f'<div class="notice"><p>{esc(ff["authority_note"])}</p></div>')

    # 2 Envelope
    w('<h2><span class="num">02</span>Mechanical envelope</h2>')
    w('<div class="scroll"><table><tr><th>Dimension</th><th style="text-align:right">mm</th></tr>')
    for key, label in (
        ("board_length_mm", "Board length"),
        ("board_width_mm", "Board width"),
        ("pcb_thickness_mm", "PCB thickness"),
        ("assembly_height_target_mm", "Assembly height — target"),
        ("assembly_height_max_mm", "Assembly height — hard ceiling"),
        ("bottom_side_max_mm", "Bottom-side components — max"),
    ):
        w(f'<tr><td>{label}</td><td class="val">{env[key]}</td></tr>')
    w("</table></div>")
    w(f"<p>{esc(env['derivation'])}</p>")
    if board is not None:
        w(f"<p>The pocket holding this board derives from these numbers: standoff "
          f"{board['standoff_mm']}, lid clearance {board['lid_clearance_mm']}, "
          f"{board['margin_length_mm']} clearance per side.</p>")

    # 3 Electrical
    w('<h2><span class="num">03</span>Electrical envelope</h2>')
    w(f'<div class="notice"><p><b>Every figure in this section is proposed, not confirmed.</b> '
      f"{esc(el['provenance']['confidence'].upper())} — "
      f"{esc(el['provenance']['source'].replace('_', ' '))}. Confirm before pricing against "
      f"them.</p></div>")
    pa = el["power_architecture"]
    w(f"<p><b>Power architecture — <code>{esc(pa['mode'])}</code>.</b> {esc(pa['rationale'])}</p>")
    sup, au, pf, th, io = (
        el["supply"], el["audio"], el["performance"], el["thermal"], el["io_provision"]
    )
    rows = [
        ("Supply input, nominal", f"{sup['input_nominal_v']} V"),
        ("Supply input, range", f"{sup['input_min_v']} – {sup['input_max_v']} V"),
        ("Quiescent draw, max", f"{sup['quiescent_max_ma']} mA"),
        ("Peak draw, max", f"{sup['peak_max_ma']} mA"),
        ("Sample rate, primary", f"{au['sample_rate_primary_khz']} kHz"),
        ("Sample rate, capable", f"{au['sample_rate_capable_khz']} kHz"),
        ("Bit depth", au["bit_depth"]),
        ("Input full scale, min gain", f"{au['input_full_scale_vpp']} Vpp"),
        ("Input typical program level", f"{au['input_typical_vpp']} Vpp"),
        ("ADC SNR", f"≥ {pf['adc_snr_db_a_weighted']} dB A-wtd"),
        ("THD+N, max", f"{pf['thd_n_max_pct']} %"),
        ("Headphone power into 32 Ω", f"≥ {pf['headphone_power_mw_into_32r']} mW"),
        ("Cavity ambient", f"{th['cavity_ambient_min_c']} – {th['cavity_ambient_max_c']} °C"),
        ("Component rating, min", f"{th['component_rating_min_c']} °C"),
        ("Switch inputs", io["switch_inputs"]),
        ("Analog inputs", io["analog_inputs"]),
        ("Discrete LED outputs", io["discrete_led_outputs"]),
        ("Addressable LED channels", io["addressable_led_channels"]),
    ]
    w('<div class="scroll"><table><tr><th>Parameter</th>'
      '<th style="text-align:right">Value</th></tr>')
    for label, value in rows:
        w(f'<tr><td>{esc(label)}</td><td class="val">{esc(value)}</td></tr>')
    w("</table></div>")
    w("<h3>How these are to be demonstrated</h3>")
    w("<p>A requirement without a measurement method cannot be accepted or rejected.</p><ul>")
    for line in el["measurement_conditions"]:
        w(f"<li>{esc(line)}</li>")
    w("</ul>")
    w(f'<p class="why">{esc(el["provenance"]["note"])}</p>')

    # 4 Interfaces
    w('<h2><span class="num">04</span>Interfaces</h2>')
    w('<div class="scroll"><table><tr><th>Interface</th><th>Direction</th><th>Connection</th>'
      "<th>Notes</th></tr>")
    for i in spec["interfaces"]:
        w(f'<tr><td class="mono">{esc(i["interface_id"])}</td><td>{esc(i["direction"])}</td>'
          f'<td class="mono">{esc(i["connection"])}</td><td>{esc(i["description"])}</td></tr>')
    w("</table></div>")
    w("<p><b>The jacks are body-mounted, not board-mounted.</b> Audio interfaces are "
      "wire-to-board so the CNC can place jacks where the player expects them, and so board "
      "height stays low.</p>")

    # 5 Requirements
    w('<h2><span class="num">05</span>Requirements</h2>')
    w(f"<p>{len(blockers)} of {len(reqs)} are shippable blockers. Those are not tradeable as "
      "implementation details.</p>")
    for r in reqs:
        label, cls = CRITICALITY[r["criticality"]]
        w('<div class="req"><div class="req-head">')
        w(f'<span class="req-id">{esc(r["requirement_id"])}</span>')
        w(f'<span class="pill {cls}">{label}</span></div>')
        w(f"<p>{esc(r['requirement'])}</p>")
        w(f'<p class="why"><b>Why:</b> {esc(r["rationale"])}</p></div>')

    # 6 Environment / 7 Certification
    for num, title, lines in (
        ("06", "Operating environment", spec["environment"]),
        ("07", "Certification", spec["certification"]),
    ):
        w(f'<h2><span class="num">{num}</span>{title}</h2><ul>')
        for line in lines:
            w(f"<li>{esc(line)}</li>")
        w("</ul>")

    # 8 Acceptance
    w('<h2><span class="num">08</span>Acceptance matrix</h2>')
    w("<p>Every requirement, how it is demonstrated, and what counts as a pass. A MUST without "
      "a pass criterion is an opinion.</p>")
    for a in spec["acceptance"]:
        w('<div class="acc"><div class="req-head">')
        w(f'<span class="req-id">{esc(a["requirement_id"])}</span>')
        w(f'<span class="pill">{esc(a.get("stage", "—").replace("_", " "))}</span></div>')
        w('<dl class="acc-grid">')
        w(f'<div class="acc-row"><dt>Method</dt><dd>{esc(a["method"])}</dd></div>')
        w(f'<div class="acc-row"><dt>Pass</dt><dd>{esc(a["pass_criterion"])}</dd></div>')
        w("</dl></div>")

    # 9 Open questions / 10 Context
    for num, title, blurb, lines in (
        ("09", "Open questions",
         "These are unresolved at the time of writing and may change the design. Raise them "
         "before committing to a topology.", spec["open_questions"]),
        ("10", "Context worth knowing", "", spec["notes"]),
    ):
        w(f'<h2><span class="num">{num}</span>{title}</h2>')
        if blurb:
            w(f"<p>{blurb}</p>")
        w("<ul>")
        for line in lines:
            w(f"<li>{esc(line)}</li>")
        w("</ul>")

    w('<div class="foot">')
    w(f"<p>Generated from the governed record <code>fixtures/subassemblies/"
      f"{SPEC.name}</code>. Do not edit this page — edit the record and regenerate, or the "
      f"envelope will drift from the cavity that holds the board.</p>")
    hist = " · ".join(f"Rev {h['revision']} {h['date']}" for h in dc["revision_history"])
    w(f"<p class='mono'>{esc(hist)}</p>")
    w("</div></div>")
    return "\n".join(o) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    out = args.out if args.out.is_absolute() else (Path.cwd() / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(spec, register), encoding="utf-8")

    try:
        shown = out.relative_to(ROOT).as_posix()
    except ValueError:
        shown = out.as_posix()
    print(f"wrote {shown}")
    print(f"  {spec['spec_id']}  Rev {spec['document_control']['revision']}  "
          f"status {spec['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
