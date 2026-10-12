#!/usr/bin/env python3
"""Lexicon builder: RadLex (external authority) + corpus (observation).

Neither source is enough alone -- RadLex says what is a concept but lacks
cardiomegaly, the silhouette family and real reading regions; the corpus says
how a concept is used but knows nothing the model never extracted. Each entry
carries both, plus a verdict:

    A confirmed   in RadLex, used enough in the corpus       -> adopt
    B respecify   a RadLex concept plus side/modifier        -> flatten it
    C local       absent from RadLex but frequent            -> define locally
    D tail        rare and unmatched                         -> leave

B is the point of the tool: it records the canonical form and the stripped
component, which is the input an E1/E2 migration needs.

Per-field rules differ (anatomy strips side only; "lower_lobe" is granularity,
not a modifier), or anatomy labels get flattened into nonsense.

    python3 tools/lexicon.py            # small splits -> ../out/lexicon/lexicon.tsv
    python3 tools/lexicon.py --all      # including train (minutes)
    python3 tools/lexicon.py --field anatomy
"""

from __future__ import annotations

# Runs standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


import argparse
import collections
import os
import sys

from core import (ONT, RADLEX_CLINICAL, REPO, SMALL, SPLITS, propositions,
                    table, unsnake)

sys.path.insert(0, REPO)
from Pipeline.radlex_match import (candidates, load_radlex)   # noqa: E402

OUT = os.path.join(REPO, "out", "lexicon", "lexicon.tsv")
FIELDS = ("entity", "anatomy", "descriptor")

# Stages that produce grade B: matching only here means the label is over-specified.
RESPEC = {"laterality", "modifier"}

# What may be stripped differs per field -- "lower" in lower_lobe is anatomical
# granularity, not a modifier.
#
#   anatomy     side only; zone words are part of the structure
#   entity      side + modifiers (focal_consolidation -> consolidation)
#   descriptor  side only; stripping a descriptor off a descriptor is pointless
STRIP_BY_FIELD = {"anatomy": "side", "entity": "all", "descriptor": "side"}


def collect(splits):
    freq = {f: collections.Counter() for f in FIELDS}
    surf = {f: collections.defaultdict(collections.Counter) for f in FIELDS}
    for sp in splits:
        for _rec, p in propositions(sp):
            e = p.get("entity") or {}
            if e.get("label"):
                freq["entity"][e["label"]] += 1
                if e.get("text"):
                    surf["entity"][e["label"]][e["text"].lower().strip()] += 1
            for a in p.get("anatomy") or []:
                if a.get("label"):
                    freq["anatomy"][a["label"]] += 1
                    if a.get("text"):
                        surf["anatomy"][a["label"]][a["text"].lower().strip()] += 1
            for d in p.get("descriptors") or []:
                if d.get("label"):
                    freq["descriptor"][d["label"]] += 1
                    if d.get("text"):
                        surf["descriptor"][d["label"]][d["text"].lower().strip()] += 1
    return freq, surf


def build(splits, min_freq, fields):
    by_label, by_syn, _rl = load_radlex(
        os.path.join(REPO, "RadLex", "radlex_terms.tsv"))
    mods = set()
    for w in ONT.DESCRIPTOR_LEXICON:
        mods.update(unsnake(w).split())
    for _w, z in ONT.ZONE_WORDS:
        mods.add(z)

    freq, surf = collect(splits)
    rows = []
    for field in fields:
        # An empty modifier set makes candidates() skip the modifier stage.
        fmods = mods if STRIP_BY_FIELD.get(field) == "all" else set()
        for label, n in freq[field].items():
            hit_how = hit_rid = norm_form = None
            for cand, how in candidates(label, fmods):
                rid = by_label.get(cand) or by_syn.get(cand)
                if rid:
                    hit_how, hit_rid, norm_form = how, rid, cand
                    break
            if hit_how in ("exact", "plural", "wordorder"):
                grade = "A"
            elif hit_how in RESPEC:
                grade = "B"
            elif n >= min_freq:
                grade = "C"
            else:
                grade = "D"
            variants = surf[field][label].most_common(8)
            rows.append({
                "field": field, "label": label, "n": n,
                "grade": grade, "how": hit_how or "", "rid": hit_rid or "",
                "canonical": norm_form or "",
                "n_variants": len(surf[field][label]),
                "variants": "|".join(f"{v}:{c}" for v, c in variants),
            })
    rows.sort(key=lambda r: (r["field"], -r["n"]))
    return rows


def report(rows) -> str:
    out = ["## Lexicon -- RadLex + corpus\n"]
    out.append("Grades: **A** adopt as is · **B** over-specified, flatten to the "
               "canonical form · **C** absent from RadLex but frequent, define "
               "locally · **D** tail\n")
    per = collections.defaultdict(lambda: collections.Counter())
    occ = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        per[r["field"]][r["grade"]] += 1
        occ[r["field"]][r["grade"]] += r["n"]
    body = []
    for f in FIELDS:
        if not per[f]:
            continue
        tot_l = sum(per[f].values())
        tot_n = sum(occ[f].values())
        body.append([f] + [f"{per[f][g]:,} ({occ[f][g]:,})" for g in "ABCD"]
                    + [f"{tot_l:,} ({tot_n:,})"])
    out.append(table(body, ["field", "A adopt", "B respecify", "C local",
                            "D tail", "total"]))
    out.append("\nMentions in parentheses.\n")

    for f in FIELDS:
        bs = [r for r in rows if r["field"] == f and r["grade"] == "B"][:10]
        if bs:
            out.append(f"\n**{f} -- top grade B (to be flattened)**\n")
            out.append(table([[r["label"], f"{r['n']:,}", r["how"],
                               r["canonical"], r["rid"]] for r in bs],
                             ["label", "mentions", "added on top", "RadLex form", "RID"]))
    for f in FIELDS:
        cs = [r for r in rows if r["field"] == f and r["grade"] == "C"][:10]
        if cs:
            out.append(f"\n**{f} -- top grade C (frequent, absent from RadLex)**\n")
            out.append(table([[r["label"], f"{r['n']:,}", f"{r['n_variants']}",
                               r["variants"][:56]] for r in cs],
                             ["label", "mentions", "surfaces", "surface forms"]))
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--min-freq", type=int, default=30)
    ap.add_argument("--field", action="append", choices=FIELDS)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    rows = build(SPLITS if a.all else SMALL, a.min_freq, a.field or FIELDS)
    cols = ["field", "label", "n", "grade", "how", "rid", "canonical",
            "n_variants", "variants"]
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    print(report(rows))
    print(f"\n-> {a.out}  ({len(rows):,} rows)")
