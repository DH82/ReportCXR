#!/usr/bin/env python3
"""Show v1 and v2 output side by side for one stratum, to eyeball whether a
moved metric is a real improvement."""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "out", "ab")
rows = [json.loads(l) for l in open(f"{OUT}/out.jsonl")]
want = sys.argv[1] if len(sys.argv) > 1 else None
byu = collections.defaultdict(dict)
for r in rows:
    byu[r["utterance"]][r["arm"]] = r

def render(r):
    if not r or "error" in (r or {}):
        return ["  <failed>"]
    out = []
    for p in (r["norm"]["propositions"] or []):
        e = p["entity"]
        a = " ; ".join(f"{x.get('label')}[{x.get('laterality')}"
                       + (f"/{x['zone']}" if x.get('zone') else "")
                       + (f"/{x['role']}" if x.get('role') not in (None,'site') else "")
                       + "]" for x in (p.get("anatomy") or [])) or "-"
        d = " ".join(f"{x['type']}={x['label']}" for x in (p.get("descriptors") or [])) or "-"
        out.append(f"  {p['id']} {e['label']}({e['type']}) {p['assertion']['label']}"
                   f"/{p['comparison']['label']}" + (f" <-{p['derived_from']}" if p.get("derived_from") else ""))
        out.append(f"      anat {a}")
        out.append(f"      desc {d}")
    if not out:
        out = ["  (no propositions)"]
    if r["norm"].get("warnings"):
        out.append(f"      warn {r['norm']['warnings']}")
    f = [x["code"] for x in r.get("findings") or []]
    if f:
        out.append(f"      ✗ {', '.join(f)}")
    return out

for u, d in byu.items():
    st = (d.get("v1") or d.get("v2"))["stratum"]
    if want and not st.startswith(want):
        continue
    print(f"\n{'='*100}\n[{st}] {u}")
    print(" -- v1 --"); print("\n".join(render(d.get("v1"))))
    print(" -- v2 --"); print("\n".join(render(d.get("v2"))))
