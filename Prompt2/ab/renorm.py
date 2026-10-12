#!/usr/bin/env python3
"""Re-run step 2 and step 3 from the stored step 1 output.

Arms normalized by different versions of normalize.py are not comparable. Both
steps are deterministic and free, so run this before scoring. No LLM calls.
"""
import copy, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "out", "ab")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "Pipeline"))
from normalize import normalize_record
from validate import validate_record

path = f"{OUT}/out.jsonl"
rows = [json.loads(l) for l in open(path)]
n = 0
for r in rows:
    if "raw" not in r:
        continue
    r["norm"] = normalize_record(copy.deepcopy(r["raw"]))
    r["findings"] = validate_record(r["norm"])["findings"]
    n += 1
with open(path, "w") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{n} records renormalized and revalidated")
