#!/usr/bin/env python3
"""Stratified sample for human review -- the only thing that answers "is the
normalization any good".

Every other metric is a proxy: 1-B proves two mappings disagree but not which
is right, coverage proves a table was consulted but not that it is correct.
Random sampling measures nothing here (140 of 150 random propositions are
opacity -> opacity), so four strata of differing risk are drawn evenly and
re-weighted afterwards:

    majority     the modal label for a surface form -- the bulk of the data
    minority     a non-modal label; 1-B says one side is wrong
    passthrough  no table decided it
    merged       many surface forms folded into one label

The sheet is (surface text -> label) with a yes/no column, and the weights turn
the answers back into an estimate for the whole dataset.
"""

from __future__ import annotations

# Runs standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


import argparse
import collections
import csv
import random
from typing import Any, Dict, List

from core import (classify_anatomy, classify_entity, norm_text,
                    propositions, table)

STRATA = ["majority", "minority", "passthrough", "merged"]
COLS = ["stratum", "field", "surface_text", "label", "n_this", "n_form",
        "utterance", "study_id", "verdict", "should_be", "note"]


def build(split: str, n: int, seed: int = 0) -> Dict[str, Any]:
    fwd = collections.defaultdict(collections.Counter)
    rev = collections.defaultdict(set)
    rows: List[Dict[str, Any]] = []

    for rec, prop in propositions(split):
        ent = prop.get("entity") or {}
        pairs = [("entity", norm_text(ent.get("text")), ent.get("label"))]
        for a in prop.get("anatomy") or []:
            pairs.append(("anatomy", norm_text(a.get("text")), a.get("label")))
        for field, txt, lab in pairs:
            if not txt or not lab:
                continue
            fwd[(field, txt)][lab] += 1
            rev[(field, lab)].add(txt)
            rows.append({"field": field, "surface_text": txt, "label": lab,
                         "utterance": rec.get("utterance"),
                         "study_id": rec.get("study_id")})

    # Stratum sizes over the WHOLE dataset -- the weights.
    sizes: collections.Counter = collections.Counter()
    for r in rows:
        r["stratum"] = _stratum(r, fwd, rev)
        sizes[r["stratum"]] += 1

    rng = random.Random(seed)
    per = max(1, n // len(STRATA))
    picked: List[Dict[str, Any]] = []
    by_stratum = collections.defaultdict(list)
    for r in rows:
        by_stratum[r["stratum"]].append(r)
    for s in STRATA:
        pool = by_stratum.get(s) or []
        picked += rng.sample(pool, min(per, len(pool)))

    for r in picked:
        c = fwd[(r["field"], r["surface_text"])]
        r["n_this"] = c[r["label"]]
        r["n_form"] = sum(c.values())
        r["verdict"] = r["should_be"] = r["note"] = ""
    return {"split": split, "rows": picked, "sizes": sizes,
            "total": len(rows)}


def _stratum(r, fwd, rev) -> str:
    field, txt, lab = r["field"], r["surface_text"], r["label"]
    counts = fwd[(field, txt)]
    if len(counts) > 1 and counts[lab] < max(counts.values()):
        return "minority"
    known = classify_entity if field == "entity" else classify_anatomy
    if known(lab) == "passthrough":
        return "passthrough"
    if len(rev[(field, lab)]) >= 10:
        return "merged"
    return "majority"


def write_sheet(res: Dict[str, Any], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(res["rows"], key=lambda x: (x["stratum"], x["field"])):
            w.writerow(r)


def score(path: str, sizes: Dict[str, int] = None) -> str:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    graded = [r for r in rows if (r.get("verdict") or "").strip()]
    if not graded:
        return ("No verdicts filled in yet. Put ok / wrong / unsure in the "
                "`verdict` column and run --score again.\n")

    per = collections.defaultdict(collections.Counter)
    for r in graded:
        per[r["stratum"]][r["verdict"].strip().lower()] += 1

    body = [f"\nGraded {len(graded)} of {len(rows)} sampled rows.\n"]
    out_rows = []
    for s in STRATA:
        c = per.get(s)
        if not c:
            continue
        n = sum(c.values())
        wrong = c["wrong"]
        out_rows.append([s, n, c["ok"], wrong, c["unsure"],
                         f"{100.0 * wrong / n:.1f}%",
                         (sizes or {}).get(s, "-")])
    body.append(table(out_rows, ["stratum", "graded", "ok", "wrong", "unsure",
                                 "error rate", "stratum size"]))

    if sizes:
        total = sum(sizes.values())
        est = sum((sizes.get(s, 0) / total) *
                  (per[s]["wrong"] / max(1, sum(per[s].values())))
                  for s in STRATA if per.get(s))
        body.append(f"\n**Weighted estimate of dataset-wide label error: "
                    f"{100 * est:.1f}%**\n")
        body.append("Per-stratum rates say where to spend the next hour; the "
                    "weighted number is the one to quote.\n")
    return "\n".join(body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="train")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("-o", "--out", default="review_sheet.csv")
    ap.add_argument("--score", default=None,
                    help="grade a filled-in sheet instead of building one")
    args = ap.parse_args()

    if args.score:
        res = build(args.split, 1, args.seed)      # sizes only
        print(score(args.score, res["sizes"]))
        return 0

    res = build(args.split, args.n, args.seed)
    write_sheet(res, args.out)
    print(f"wrote {args.out}: {len(res['rows'])} rows from {args.split} "
          f"({res['total']:,} mappings)")
    print(table([[s, res["sizes"].get(s, 0),
                  f"{100.0 * res['sizes'].get(s, 0) / res['total']:.1f}%",
                  sum(1 for r in res["rows"] if r["stratum"] == s)]
                 for s in STRATA],
                ["stratum", "size in dataset", "share", "sampled"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
