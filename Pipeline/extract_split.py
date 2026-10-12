#!/usr/bin/env python3
"""Re-extract one split with another prompt package, into jsonl/<arm>/.

    jsonl/Prompt/<split>.jsonl        the utterances (input)
    jsonl/<arm>/<split>.jsonl         steps 1-3 rerun with that arm's prompt

Only the prompt changes. The tables, the normalizer and the validator are the
same for every arm (see PROVENANCE.md), so a difference between two arms is a
difference the prompt made.

RESUMABLE. One study per line, flushed as it finishes; a rerun skips the study
ids already in the output. A 1,565-utterance split is ~13 hours on this host,
so the run has to survive a disconnect.

Records are written in the dataset's own shape -- the five keys of Section 2,
with nothing this pipeline adds (no normalization, no review, no row_id) --
because Verify's section S compares record keys strictly.

    python3 extract_split.py --split test_reviewed --arm Prompt2
    python3 extract_split.py --split test_reviewed --arm Prompt2 --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, REPO)

SPEC_KEYS = ("utterance_id", "utterance", "section", "propositions", "warnings")


def source_path(split: str) -> str:
    return os.path.join(REPO, "jsonl", "Prompt", f"{split}.jsonl")


def out_path(arm: str, split: str) -> str:
    return os.path.join(REPO, "jsonl", arm, f"{split}.jsonl")


def done_ids(path: str) -> set:
    """Study ids already written, so a rerun continues instead of restarting."""
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.add(json.loads(line)["id"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True)
    ap.add_argument("--arm", default="Prompt2", help="prompt package (default: Prompt2)")
    ap.add_argument("--limit", type=int, help="stop after N studies (smoke test)")
    ap.add_argument("--out", help="override the output path")
    a = ap.parse_args()

    os.environ["REPORTCXR_PROMPT"] = a.arm      # read by qwen_client at import
    import qwen_client as Q                     # noqa: E402
    from parse_utterances import parse_one      # noqa: E402

    src = source_path(a.split)
    dst = a.out or out_path(a.arm, a.split)
    if not os.path.exists(src):
        sys.exit(f"source not found: {src}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    studies = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
    already = done_ids(dst)
    todo = [s for s in studies if s["id"] not in already]
    n_utt = sum(len(s["records"]) for s in todo)

    print(f"arm {a.arm}  split {a.split}", flush=True)
    print(f"  source      {src}", flush=True)
    print(f"  output      {dst}", flush=True)
    print(f"  studies     {len(studies):,}  (done {len(already):,}, todo {len(todo):,})",
          flush=True)
    print(f"  utterances  {n_utt:,}  (~{n_utt * 30 / 3600:.1f} h at 30 s/call)",
          flush=True)
    if a.limit is not None:                 # 0 is a valid "do nothing" check
        todo = todo[:a.limit]
        n_utt = sum(len(s["records"]) for s in todo)

    log = Q.CallLog(os.path.join(REPO, "out", "extract", a.arm, a.split),
                    f"{a.arm}_{a.split}")
    llm = Q.Qwen(log)

    pre = Q.preflight(llm)
    print(f"  server      {'ok' if pre.get('ok') else 'NOT READY'}"
          f"  (tool calls: {pre.get('tool_calls')})", flush=True)
    if not pre.get("ok"):
        return 1

    t0 = time.time()
    done_utt = 0
    with open(dst, "a", encoding="utf-8") as fh:
        for i, study in enumerate(todo, 1):
            records = []
            for rec in study["records"]:
                item = {"utterance_id": rec["utterance_id"],
                        "utterance": rec["utterance"],
                        "section": rec.get("section")}
                full = parse_one(llm, item)
                records.append({k: full[k] for k in SPEC_KEYS})
                done_utt += 1
            fh.write(json.dumps({"id": study["id"], "split": study["split"],
                                 "records": records}, ensure_ascii=False) + "\n")
            fh.flush()
            el = time.time() - t0
            left = (n_utt - done_utt) * el / max(1, done_utt) / 60
            print(f"[{i}/{len(todo)}] {study['id']}  "
                  f"{done_utt}/{n_utt} utt  {el/60:.1f} min elapsed, "
                  f"~{left:.0f} min left", flush=True)

    print(f"done. {done_utt:,} utterances -> {dst}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
