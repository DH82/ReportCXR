#!/usr/bin/env python3
"""A/B: parse the same 64 utterances with prompt v1 and the current prompt.

Held fixed: one ontology, one normalizer, one validator for both arms; the two
arms alternate utterance by utterance so a slow server cannot bias one; sampler
stays at the qwen_client defaults. Rows are flushed to out.jsonl as they finish.
"""
import json, os, sys, time, copy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "out", "ab")            # artifacts go to the repo out/
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "Pipeline"))

import qwen_client as Q
from normalize import normalize_record
from validate import validate_record
import Prompt, Prompt2

# Arm names are stored in out.jsonl. Every v2.x and v3.x arm was the same
# module at a different commit, and since Prompt3/ was merged into Prompt2/ the
# importable prompt is the final one (v3.4). So only v1 and v3.4 can be run
# now; every earlier arm is read back from out.jsonl, which is what the scoring
# already did (same server, model and sample, so still comparable).
ARMS = {
    "v1": (Prompt.SYSTEM_PROMPT, Prompt.selected),
    "v3.4": (Prompt2.SYSTEM_PROMPT, Prompt2.selected),
}

# Retired: their prompt text lives only in git history. Naming one is a mistake
# worth catching loudly rather than silently re-running it as v3.4.
RETIRED = ["v2", "v2.1", "v3", "v3.1", "v3.2", "v3.2b", "v3.3"]

# Which arm to run; no argument means both v1 and v3.4.
WANT = sys.argv[1:] or ["v1", "v3.4"]
for a in WANT:
    if a in RETIRED:
        sys.exit(f"arm {a} is retired: its prompt text is in git history only, "
                 f"and its rows are already in out.jsonl. Runnable: "
                 f"{', '.join(ARMS)}")
    if a not in ARMS:
        sys.exit(f"unknown arm: {a}  (known: {', '.join(ARMS)})")

def set_arm(arm):
    Q.SYSTEM_PROMPT, Q.selected = ARMS[arm]

sample = [json.loads(l) for l in open(f"{HERE}/sample.jsonl")]
out_path = f"{OUT}/out.jsonl"
done = set()
if os.path.exists(out_path):
    for l in open(out_path):
        try:
            d = json.loads(l); done.add((d["arm"], d["utterance"]))
        except Exception:
            pass
    print(f"resuming: {len(done)} already done")

log = Q.CallLog(f"{OUT}/logs", "ab")
llm = Q.Qwen(log, max_examples=4)

todo = [(arm, it) for it in sample for arm in WANT
        if (arm, it["utterance"]) not in done]
print(f"{len(todo)} calls remaining  (~{len(todo)*65/60:.0f} min)", flush=True)

t0 = time.time()
with open(out_path, "a") as fh:
    for i, (arm, it) in enumerate(todo, 1):
        set_arm(arm)
        row = {"arm": arm, "stratum": it["stratum"],
               "utterance_id": it["utterance_id"], "utterance": it["utterance"],
               "section": it["section"], "v1_codes_jsonl": it["v1_codes"]}
        try:
            res = llm.parse(it["utterance_id"], it["utterance"], it["section"])
            rec = {"utterance_id": it["utterance_id"], "utterance": it["utterance"],
                   "section": it["section"],
                   "propositions": res.get("propositions") or [],
                   "warnings": res.get("warnings") or []}
            row["raw"] = copy.deepcopy(rec)                 # step 1 output, untouched
            norm = normalize_record(copy.deepcopy(rec))     # step 2
            row["norm"] = norm
            row["findings"] = validate_record(norm)["findings"]   # step 3
            row["examples"] = res.get("examples")
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        fh.write(json.dumps(row, ensure_ascii=False) + "\n"); fh.flush()
        el = time.time() - t0
        print(f"[{i}/{len(todo)}] {arm} {it['stratum'][:2]} "
              f"{el/60:.1f} min elapsed, ~{(len(todo)-i)*el/i/60:.0f} min left", flush=True)
print("done")
