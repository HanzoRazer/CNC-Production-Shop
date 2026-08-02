#!/usr/bin/env python3
"""Emit a change list between an issued revision and the current one.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

The initial spec went to designers as a PDF, which corresponds to Rev A. Every
revision since changed a document already in someone else's hands, and a
recipient cannot diff a PDF against a regenerated markdown file. This produces
the diff for them.

    python scripts/export_frontend_delta.py [--from A]

Organised by what a bidder does with it: what changes a quote, what is new to
read, what was corrected, and what is still open. Generated from the record's
own revision history, so it cannot drift from the document it describes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "fixtures" / "subassemblies" / "sg_audio_frontend_v1.json"
DEFAULT_OUT = ROOT / "exports" / "subassemblies" / "SG_AUDIO_FRONTEND_CHANGES.md"

# What each revision means to someone holding the issued PDF. Keyed to the
# revision history in the record; the history itself is reproduced verbatim
# below, so this is the reading guide rather than the source of truth.
IMPACT = {
    "B": ("quote", "The entire ELECTRICAL ENVELOPE did not exist in the issued version, "
          "nor did the ACCEPTANCE MATRIX. A quote built on the PDF was priced against "
          "mechanical constraints and prose requirements only."),
    "C": ("read", "Physical separations were added. They have since been withdrawn and "
          "restated twice — see the figures section."),
    "D": ("quote", "REQ-HIZ gained a NOISE clause, a 100 pA bias-current limit, and a "
          "prototype-stage acceptance test with a defined dummy pickup source. This is "
          "new scope: a bench measurement that did not exist in the issued version."),
    "E": ("read", "An open question was corrected that assumed both product lines carry "
          "the same pickups. They do not. The board is unaffected."),
    "F": ("read", "Every physical separation was withdrawn rather than restated wrongly."),
    "G": ("read", "Battery moved from two cells to four, wired 2S2P. Nothing electrical "
          "changed — same 6.0-8.4 V. The BMS is now a 2S2P part."),
    "H": ("quote", "Board-to-Pi separation restored as 7.0 mm — far worse than anything "
          "in the issued version, and a materially harder EMC problem."),
    "I": ("quote", "The GPIO ribbon was lengthened to 150 mm specifically to buy "
          "separation. Board-to-Pi is now 42.0 mm. Required reach is 125.0 mm header to "
          "header."),
    "J": ("read", "One open question added: whether this board can carry an M.2 2230 slot."),
}


def render(spec: dict, since: str) -> str:
    dc = spec["document_control"]
    history = dc["revision_history"]
    after = [h for h in history if h["revision"] > since]

    out: list[str] = []
    w = out.append

    w(f"# {spec['subassembly_name']} — changes since Rev {since}")
    w("")
    w(f"`{spec['spec_id']}` · issued version **Rev {since}** (the PDF) · "
      f"current **Rev {dc['revision']}**")
    w("")
    w("> **You are holding a superseded document.** The version issued to you is")
    w("> Rev A. This lists what has changed since, so you do not have to diff a")
    w("> PDF against a regenerated file. Read it before quoting.")
    w("")
    w(f"Change requests: {dc['change_contact']}")
    w("")

    quote = [h for h in after if IMPACT.get(h["revision"], ("read", ""))[0] == "quote"]
    w("## Changes that affect a quote")
    w("")
    if quote:
        w(f"{len(quote)} of {len(after)} revisions change what the work is. If you have")
        w("already priced from the PDF, these are the ones to re-price against.")
        w("")
        for h in quote:
            w(f"### Rev {h['revision']} — {h['date']}")
            w("")
            w(IMPACT[h["revision"]][1])
            w("")
    else:
        w("None.")
        w("")

    w("## Everything else, in order")
    w("")
    for h in after:
        kind = IMPACT.get(h["revision"], ("read",))[0]
        tag = "**affects a quote**" if kind == "quote" else "read only"
        w(f"### Rev {h['revision']} — {h['date']} · {tag}")
        w("")
        w(h["change"])
        w("")

    w("## The figures that moved, in one place")
    w("")
    w("The board's distance from the Raspberry Pi changed four times. It is listed")
    w("as a sequence rather than a value because a figure that volatile should not")
    w("be read as settled:")
    w("")
    w("| Revision | Board to Pi | Why |")
    w("|---|---:|---|")
    w("| A (yours) | not stated | |")
    w("| C–E | 35.75 mm | From a pocket layout later found to be wrong |")
    w("| F | withdrawn | The layout was solved against a stale body outline |")
    w("| H | 7.0 mm | Real, and set by the GPIO ribbon rather than by the body |")
    w("| **J (current)** | **42.0 mm** | Ribbon lengthened to 150 mm to buy separation |")
    w("")
    w("**Price against 42.0 mm.** The acceptance condition never depended on it:")
    w("REQ-NOISE is measured in the assembled instrument with the Pi powered, so")
    w("the obligation is fixed by the venue of the measurement, not by a distance.")
    w("")

    w("## Still open")
    w("")
    w(f"{len(spec['open_questions'])} questions are unresolved and several change the")
    w("design. They are reproduced in full in the current brief; the headline ones:")
    w("")
    for q in spec["open_questions"]:
        head = q.split(".")[0].strip()
        if head.isupper() or head[:40].isupper():
            w(f"- {head}.")
    w("")
    w("## Revision history, verbatim")
    w("")
    w("| Rev | Date | Change |")
    w("|---|---|---|")
    for h in history:
        mark = " ← issued to you" if h["revision"] == since else ""
        w(f"| **{h['revision']}**{mark} | {h['date']} | {h['change']} |")
    w("")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="since", default="A", help="the issued revision")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    revisions = {h["revision"] for h in spec["document_control"]["revision_history"]}
    if args.since not in revisions:
        print(f"Rev {args.since} is not in the revision history: {sorted(revisions)}")
        return 1

    out = args.out if args.out.is_absolute() else (Path.cwd() / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(spec, args.since), encoding="utf-8")
    after = [h for h in spec["document_control"]["revision_history"] if h["revision"] > args.since]
    quote = [h for h in after if IMPACT.get(h["revision"], ("read",))[0] == "quote"]
    try:
        shown = out.relative_to(ROOT).as_posix()
    except ValueError:
        shown = out.as_posix()
    print(f"wrote {shown}")
    print(f"  Rev {args.since} -> {spec['document_control']['revision']}: "
          f"{len(after)} revisions, {len(quote)} affecting a quote")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
