#!/usr/bin/env python3
"""Where E1 (laterality separation) fails to apply.

normalize.py strips a side prefix only when the remaining stem is in ANATOMY,
so the P1a residue is a COVERAGE gap, not a missing alias. This counts how many
mentions each missing stem would move, which is the work list.

No LLM calls; independent of the prompt work.
"""
import json, sys, os, collections, copy

ROOT = "/home/ldh/ReportCXR-Ko"
ARM = os.environ.get("REPORTCXR_ARM", "Prompt")   # jsonl/<arm>/
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "Pipeline"))
from Prompt2.ontology import ANATOMY, ANATOMY_ALIASES
from normalize import normalize_record

PREFIX = ("left_", "right_", "bilateral_")
BARE = {"left", "right", "bilateral", "left_side", "right_side",
        "left_sided", "right_sided", "left_lateral", "right_lateral"}

counts = collections.Counter()
splits = sys.argv[1:] or ["train", "validate", "test", "test_reviewed"]
for sp in splits:
    for line in open(f"{ROOT}/jsonl/{ARM}/{sp}.jsonl"):
        for rec in json.loads(line).get("records") or []:
            for p in rec.get("propositions") or []:
                for a in p.get("anatomy") or []:
                    l = a.get("label") or ""
                    if l in BARE or l.startswith(PREFIX):
                        counts[l] += 1

def stem(l):
    for pre in PREFIX:
        if l.startswith(pre):
            return l[len(pre):]
    return None

known = lambda s: s in ANATOMY or s in ANATOMY_ALIASES

stems = collections.Counter()
bare_n = 0
already = 0
for l, n in counts.items():
    if l in BARE:
        bare_n += n
        continue
    s = stem(l)
    if s and known(s):
        already += n           # step 2 already undoes these
    elif s:
        stems[s] += n          # these need the stem added to ANATOMY

tot = sum(counts.values())
print(f"anatomy labels carrying a side: {tot:,} mentions  (splits={','.join(splits)})\n")
print(f"  already undone by step 2 (stem is in ANATOMY)  {already:>9,}  {100*already/tot:5.1f}%")
print(f"  left as is (stem missing from ANATOMY)         {sum(stems.values()):>9,}  {100*sum(stems.values())/tot:5.1f}%")
print(f"  no structure named at all (left, right_sided)  {bare_n:>9,}  {100*bare_n/tot:5.1f}%")
print(f"     -> the first two are fixed by adding stems to ANATOMY.")
print(f"     -> bare labels cannot be fixed by a table; that is rule 16.\n")

print(f"{'stem to add to ANATOMY':38s} {'mentions moved':>14s}  cum%")
run = 0
for s, n in stems.most_common(40):
    run += n
    print(f"  {s:36s} {n:>12,}  {100*run/sum(stems.values()):5.1f}%")

print(f"\nBare labels (prompt's job)")
for l, n in sorted(((l, n) for l, n in counts.items() if l in BARE),
                   key=lambda x: -x[1]):
    print(f"  {l:36s} {n:>12,}")
