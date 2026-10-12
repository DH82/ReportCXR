#!/usr/bin/env python3
"""Detail behind section 0 -- read-only.

Section 0 counts how many records change; this dumps WHAT changes and how.

  task2  pairs laterality_from_label against
         section_context_laterality_dropped PER PROPOSITION. Section 0 compares
         totals, which is a weak signal: on train the totals differ by 7 while
         21 propositions actually disagree.
  task3  dumps before/after, field by field, for records with a NET diff.

    python3 tools/diff_probe.py train
"""
# Runs standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import argparse
import collections
import copy
import json
import os
import sys

from core import REPO, records
from metrics import m03_fixed_point as fixed_point

# Defaults to the frozen copy in Pipeline/; --normalize points elsewhere.
# Either way load_normalizer() puts this repo's packages first, so the ontology
# is always ours.
FROZEN = os.path.join(REPO, "Pipeline", "normalize.py")

STRIP = ("normalization", "review", "row_id", "study_id")
FILL, DROP = "laterality_from_label", "section_context_laterality_dropped"


def strip(rec):
    return {k: v for k, v in rec.items() if k not in STRIP}


def run(N, split, limit=None):
    asym, diffs = [], []
    tot = collections.Counter()
    for rec in records(split, limit):
        before = strip(rec)
        after = N.normalize_record(copy.deepcopy(before))
        notes = after.pop("normalization", []) or []

        # ---- task 2: pair notes per proposition --------------------------
        per = collections.defaultdict(collections.Counter)
        for nt in notes:
            per[nt.get("proposition")][nt["code"]] += 1
            tot[nt["code"]] += 1
        for pid, c in per.items():
            if c[FILL] != c[DROP]:
                bp = next((p for p in (before.get("propositions") or [])
                           if p.get("id") == pid), None)
                ap = next((p for p in (after.get("propositions") or [])
                           if p.get("id") == pid), None)
                asym.append({
                    "uid": rec.get("utterance_id"), "pid": pid,
                    "fill": c[FILL], "drop": c[DROP],
                    "utterance": (before.get("utterance") or "")[:80],
                    "anatomy_before": bp.get("anatomy") if bp else None,
                    "anatomy_after": ap.get("anatomy") if ap else None,
                })

        # ---- task 3: NET diff detail -------------------------------------
        if after != before:
            d = {"uid": rec.get("utterance_id"),
                 "utterance": (before.get("utterance") or "")[:80], "fields": []}
            if before.get("section") != after.get("section"):
                d["fields"].append(("section", before.get("section"),
                                    after.get("section")))
            for bp, ap in zip(before.get("propositions") or [],
                              after.get("propositions") or []):
                for k in bp:
                    if bp.get(k) != ap.get(k):
                        d["fields"].append((f"{bp.get('id')}.{k}",
                                            bp.get(k), ap.get(k)))
            diffs.append(d)
    return asym, diffs, tot


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("split")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--normalize", default=FROZEN,
                    help="path to normalize.py (default: the copy in Pipeline/)")
    a = ap.parse_args()
    N = fixed_point.load_normalizer(a.normalize)
    if N is None:
        sys.exit(f"normalize.py not found: {a.normalize}")
    asym, diffs, tot = run(N, a.split, a.limit)

    print(f"\n{'='*78}\n{a.split}   note totals: "
          f"{FILL}={tot[FILL]}  {DROP}={tot[DROP]}  "
          f"(diff {tot[FILL]-tot[DROP]:+d})\n{'='*78}")

    print(f"\n[task2] asymmetric per proposition: {len(asym)}")
    for x in asym[:12]:
        print(f"\n  {x['uid']}  {x['pid']}   fill={x['fill']} drop={x['drop']}")
        print(f"    {x['utterance']}")
        print(f"    before: {json.dumps(x['anatomy_before'], ensure_ascii=False)}")
        print(f"    after : {json.dumps(x['anatomy_after'],  ensure_ascii=False)}")
    if len(asym) > 12:
        print(f"\n  ... and {len(asym)-12} more")

    print(f"\n[task3] records with a NET diff: {len(diffs)}")
    for d in diffs[:20]:
        print(f"\n  {d['uid']}")
        print(f"    {d['utterance']}")
        for f, b, aa in d["fields"]:
            print(f"    {f}")
            print(f"      before: {json.dumps(b, ensure_ascii=False)[:300]}")
            print(f"      after : {json.dumps(aa, ensure_ascii=False)[:300]}")
    if len(diffs) > 20:
        print(f"\n  ... and {len(diffs)-20} more")
