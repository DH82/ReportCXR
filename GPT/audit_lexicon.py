#!/usr/bin/env python3
"""Second opinion on out/lexicon/lexicon.tsv -- an external LLM audits the rows.

Direction: tools/lexicon.py decides mechanically (string match against RadLex),
so it cannot see meaning. It happily grades A a label that matched the WRONG
RadLex concept, leaves a misfiled label in `anatomy` because RadLex has no
opinion on our fields, and reports one label whose surface variants are in fact
two different findings. Those three are semantic, so they are what is asked
here; anything a regex already checks is not.

What the judge is shown per row -- and nothing else:

    field label n grade how rid canonical variants   from lexicon.tsv
    radlex_label / synonyms / branch / definition    joined on rid, so the
                                                     RID can be judged without
                                                     a lookup the model would
                                                     have to hallucinate

What it may answer is a closed set of codes (VERDICTS below). Free text is one
`note` field, for the human reading the report -- not a place to invent a code.

    export OPENAI_API_KEY=...
    python3 audit_lexicon.py --sample 400            # stratified, ~16 calls
    python3 audit_lexicon.py --grade A --min-n 50    # every A worth arguing about
    python3 audit_lexicon.py --sample 40 --dry-run   # print one prompt, call nothing

Resumable: every verdict is appended to out/gpt_audit/verdicts.jsonl keyed by
field|label, and a re-run skips what is already there (--refresh re-asks).
Cost is the reason -- a full 48k-row pass is ~2k calls.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as futures
import csv
import json
import os
import random
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

LEXICON = os.path.join(REPO, "out", "lexicon", "lexicon.tsv")
TERMS = os.path.join(REPO, "RadLex", "radlex_terms.tsv")
OUTDIR = os.path.join(REPO, "out", "gpt_audit")

# The name the user's account exposes; override per run rather than editing.
MODEL = os.environ.get("OPENAI_AUDIT_MODEL", "gpt-5.6-luna")
BATCH = 25                # rows per call: enough context to spot duplicates,
                          # short enough that one bad reply costs little
WORKERS = 4
MAX_VARIANTS = 8

# ---------------------------------------------------------------- the prompt

# The closed answer space. Every code is something the string matcher cannot
# decide by itself; "ok" is the expected majority and must stay cheap to give.
VERDICTS = {
    "ok":            "the row is sound as it stands",
    "wrong_rid":     "the RID names a different concept (homonym, wrong branch)",
    "wrong_field":   "belongs in another field (anatomy/entity/descriptor)",
    "overspecified": "the label carries side/modifier/severity that should be "
                     "flattened away, even if the tool did not grade it B",
    "mixed_variants":"the surface variants are not all the same concept",
    "not_a_concept": "not a term at all -- a fragment, a whole phrase, an artefact",
    "duplicate":     "the same concept as another label, in this batch or named "
                     "in `other`",
    "underspecified":"the label drops meaning the variants carry (a negation, a "
                     "device, a side that is part of the concept)",
}

SYSTEM_PROMPT = """You audit a chest-radiograph terminology lexicon. \
Each row is one LABEL that an extraction model produced over a corpus of CXR \
reports, together with how often it occurred (n), the surface strings it was \
extracted from (variants, `text:count`), and the result of an automatic match \
against RadLex.

The automatic match is pure string work, staged:
  exact | plural | wordorder -> grade A   the label IS a RadLex concept
  laterality | modifier      -> grade B   a RadLex concept PLUS something stripped
  (no match), n >= threshold -> grade C   absent from RadLex but frequent
  (no match), rare           -> grade D   tail

So the tool knows spelling and nothing else. You are asked for the part it \
cannot do: whether the row is TRUE.

Fields carry fixed meanings; a label in the wrong one is a real defect:
  anatomy      a body structure or reading region (pleura, left hilum, costophrenic angle)
  entity       a finding, disease or device (pneumothorax, chest tube, rib fracture)
  descriptor   a property of a finding (mild, patchy, increased, unchanged)

Stripping rules the builder used, which constrain what counts as over-specified:
  anatomy      side only; zone/lobe words (lower_lobe, apical) are granularity,
               NOT modifiers, and an anatomy label keeping them is correct
  entity       side and modifiers may be stripped (focal_consolidation -> consolidation)
  descriptor   side only

Judge each row on what the row itself shows. Concretely:
  1. RID: does radlex_label/definition name the SAME concept as label? Watch for
     homonyms and for a match into an unrelated branch (an anatomy RID under a
     procedure branch, a device matched to a body part).
  2. Field: is the label in the field its meaning belongs to?
  3. Variants: do all listed surface strings mean the label? A variant carrying a
     negation, a different laterality, or a different finding is a defect --
     mixed_variants if the label is right, underspecified if the label is what
     lost the meaning.
  4. Over/under-specification, under the per-field rules above.
  5. Duplicates within the batch you are shown.

Do not penalise a row for being rare, for lacking a RID, or for grade D: absence
from RadLex is expected and is not itself an error. Do not propose a new
ontology. If a row is sound, say ok and move on -- most rows are.

Answer for EVERY row_id given, once, in the order received."""

USER_HEADER = """Audit these {k} rows.

verdict codes:
{codes}

For each row return:
  row_id      exactly as given
  verdict     one code from the list
  confidence  high | medium | low
  suggestion  the corrected value when one is implied (the right field, the
              right RID, the flattened label) -- otherwise ""
  other       the label this duplicates, for `duplicate` -- otherwise ""
  note        one short clause of evidence, naming the variant or the RadLex
              term you used. Empty for `ok`.

rows:
"""


def row_block(r: dict) -> str:
    """One row, as lines -- a JSON blob costs tokens and reads worse."""
    out = [f"row_id: {r['row_id']}",
           f"  field: {r['field']}   label: {r['label']}   n: {r['n']}",
           f"  grade: {r['grade']}   matched_by: {r['how'] or '(no match)'}"]
    if r["rid"]:
        out.append(f"  radlex: {r['rid']}  {r.get('radlex_label') or '?'}"
                   f"   (matched form: {r['canonical']})")
        if r.get("radlex_synonyms"):
            out.append(f"  radlex_synonyms: {r['radlex_synonyms']}")
        if r.get("radlex_branch"):
            out.append(f"  radlex_branch: {r['radlex_branch']}")
        if r.get("radlex_definition"):
            out.append(f"  radlex_definition: {r['radlex_definition'][:300]}")
    variants = "; ".join(r["variants"].split("|")[:MAX_VARIANTS])
    out.append(f"  variants ({r['n_variants']} distinct): {variants}")
    return "\n".join(out)


def build_user(batch: list) -> str:
    codes = "\n".join(f"  {k:<15}{v}" for k, v in VERDICTS.items())
    body = "\n\n".join(row_block(r) for r in batch)
    return USER_HEADER.format(k=len(batch), codes=codes) + "\n" + body


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["row_id", "verdict", "confidence",
                             "suggestion", "other", "note"],
                "properties": {
                    "row_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "confidence": {"type": "string",
                                   "enum": ["high", "medium", "low"]},
                    "suggestion": {"type": "string"},
                    "other": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}

# ------------------------------------------------------------------- loading


def load_lexicon(path: str) -> list:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    for r in rows:
        r["n"] = int(r["n"])
        r["n_variants"] = int(r["n_variants"])
        r["row_id"] = f"{r['field']}|{r['label']}"
    return rows


def join_radlex(rows: list, path: str) -> None:
    """Attach the RadLex term behind each RID, so the RID is judgeable."""
    if not os.path.exists(path):
        print(f"[warn] no {path}; RIDs will be judged blind", file=sys.stderr)
        return
    wanted = {r["rid"] for r in rows if r["rid"]}
    terms = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for t in csv.DictReader(fh, delimiter="\t"):
            if t["rid"] in wanted:
                terms[t["rid"]] = t
    for r in rows:
        t = terms.get(r["rid"])
        if t:
            r["radlex_label"] = t.get("label", "")
            r["radlex_synonyms"] = t.get("synonyms", "")
            r["radlex_branch"] = t.get("branch", "")
            r["radlex_definition"] = t.get("definition", "")


def select(rows: list, args) -> list:
    """Filter, then sample -- stratified by field x grade, frequent rows first.

    A uniform sample of 48k rows is a sample of the D tail, which is the part
    nobody will act on. Each stratum is taken half by frequency and half at
    random, so the cheap wins surface without the sample becoming a top-n list.
    """
    rows = [r for r in rows if r["n"] >= args.min_n]
    if args.field:
        rows = [r for r in rows if r["field"] in args.field]
    if args.grade:
        rows = [r for r in rows if r["grade"] in args.grade]
    if not args.sample or args.sample >= len(rows):
        return sorted(rows, key=lambda r: (r["field"], r["grade"], -r["n"]))

    strata = collections.defaultdict(list)
    for r in rows:
        strata[(r["field"], r["grade"])].append(r)
    per = max(1, args.sample // max(1, len(strata)))
    rng = random.Random(args.seed)
    picked = []
    for key in sorted(strata):
        pool = sorted(strata[key], key=lambda r: -r["n"])
        head = pool[: per // 2]
        tail = pool[per // 2:]
        rng.shuffle(tail)
        picked.extend(head + tail[: per - len(head)])
    rng.shuffle(picked)
    return picked[: args.sample]


# -------------------------------------------------------------------- asking


class Judge:
    def __init__(self, model: str, effort: str | None, timeout: float,
                 temperature: float | None = None):
        from openai import OpenAI
        self.client = OpenAI(timeout=timeout, max_retries=2)
        self.model = model
        self.effort = effort
        self.temperature = temperature
        self.calls = 0
        self.in_tokens = self.out_tokens = 0
        self.lock = threading.Lock()

    def ask(self, batch: list) -> list:
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": build_user(batch)}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "lexicon_audit", "strict": True,
                                "schema": SCHEMA},
            },
        }
        if self.effort:
            kwargs["reasoning_effort"] = self.effort
        # Reasoning models reject `temperature` outright -- gpt-5.6-luna 400s on
        # any value but the default. Sampling is therefore opt-in, for the older
        # models that both accept it and need it pinned to be reproducible.
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        rsp = self.client.chat.completions.create(**kwargs)
        data = json.loads(rsp.choices[0].message.content)
        with self.lock:
            self.calls += 1
            if rsp.usage:
                self.in_tokens += rsp.usage.prompt_tokens
                self.out_tokens += rsp.usage.completion_tokens

        # A reply that renames or drops a row is a reply about rows we did not
        # ask about; keep only what lines up, and report the shortfall.
        want = {r["row_id"] for r in batch}
        seen, out = set(), []
        for v in data.get("verdicts", []):
            if v["row_id"] in want and v["row_id"] not in seen:
                seen.add(v["row_id"])
                out.append(v)
        if len(out) != len(batch):
            print(f"[warn] {len(batch) - len(out)}/{len(batch)} rows unanswered",
                  file=sys.stderr)
        return out


def run(rows: list, judge: Judge, args, done_path: str) -> None:
    batches = [rows[i:i + args.batch] for i in range(0, len(rows), args.batch)]
    lock = threading.Lock()
    fh = open(done_path, "a", encoding="utf-8")

    def work(batch):
        for attempt in range(3):
            try:
                return judge.ask(batch)
            except Exception as exc:                     # noqa: BLE001
                if attempt == 2:
                    print(f"[error] batch dropped: {exc}", file=sys.stderr)
                    return []
                time.sleep(2 ** attempt)

    t0 = time.time()
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, got in enumerate(pool.map(work, batches), 1):
            with lock:
                for v in got:
                    fh.write(json.dumps(v, ensure_ascii=False) + "\n")
                fh.flush()
            print(f"[{i}/{len(batches)}] {judge.calls} calls, "
                  f"{time.time() - t0:.0f}s", file=sys.stderr)
    fh.close()


# ------------------------------------------------------------------ reporting


def report(rows: list, verdicts: dict) -> str:
    by = {r["row_id"]: r for r in rows}
    counts = collections.Counter(v["verdict"] for v in verdicts.values())
    cross = collections.Counter(
        (by[k]["grade"], v["verdict"]) for k, v in verdicts.items() if k in by)

    out = ["## GPT audit of lexicon.tsv\n",
           f"{len(verdicts)} rows judged; "
           f"{counts['ok']} ok, {len(verdicts) - counts['ok']} flagged.\n",
           "| verdict | rows | mentions |", "|---|---|---|"]
    for code, k in counts.most_common():
        occ = sum(by[r]["n"] for r, v in verdicts.items()
                  if v["verdict"] == code and r in by)
        out.append(f"| {code} | {k} | {occ} |")

    out.append("\n| grade | " + " | ".join(VERDICTS) + " |")
    out.append("|---" * (len(VERDICTS) + 1) + "|")
    for g in "ABCD":
        cells = " | ".join(str(cross[(g, c)]) for c in VERDICTS)
        out.append(f"| {g} | {cells} |")

    flagged = [(by[k]["n"], k, v) for k, v in verdicts.items()
               if v["verdict"] != "ok" and k in by]
    flagged.sort(reverse=True)
    out.append("\n### Flagged, by corpus weight\n")
    out.append("| field | label | n | grade | verdict | conf | suggestion | note |")
    out.append("|---|---|---|---|---|---|---|---|")
    for n, k, v in flagged[:60]:
        r = by[k]
        out.append(f"| {r['field']} | {r['label']} | {n} | {r['grade']} | "
                   f"{v['verdict']} | {v['confidence']} | "
                   f"{v['suggestion'] or v['other']} | {v['note']} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lexicon", default=LEXICON)
    ap.add_argument("--out", default=OUTDIR)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--temperature", type=float, default=None,
                    help="only for non-reasoning models; reasoning models "
                         "reject any value (default: do not send the field)")
    ap.add_argument("--field", action="append",
                    choices=["anatomy", "entity", "descriptor"])
    ap.add_argument("--grade", action="append", choices=list("ABCD"))
    ap.add_argument("--min-n", type=int, default=1)
    ap.add_argument("--sample", type=int, default=0, help="0 = every matching row")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--refresh", action="store_true",
                    help="re-ask rows already in verdicts.jsonl")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the first prompt and the selection, call nothing")
    args = ap.parse_args()

    rows = load_lexicon(args.lexicon)
    join_radlex(rows, TERMS)
    picked = select(rows, args)
    print(f"[info] {len(picked)} of {len(rows)} rows selected", file=sys.stderr)
    if not picked:
        return 1

    os.makedirs(args.out, exist_ok=True)
    done_path = os.path.join(args.out, "verdicts.jsonl")
    done = {}
    if os.path.exists(done_path):
        with open(done_path, encoding="utf-8") as fh:
            for line in fh:
                v = json.loads(line)
                done[v["row_id"]] = v          # later line wins

    if args.dry_run:
        print(SYSTEM_PROMPT)
        print("\n" + "=" * 70 + "\n")
        print(build_user(picked[: args.batch]))
        print("\n" + "=" * 70)
        print(f"{len(picked)} rows -> "
              f"{-(-len(picked) // args.batch)} calls, model {args.model}",
              file=sys.stderr)
        return 0

    todo = picked if args.refresh else [r for r in picked
                                        if r["row_id"] not in done]
    print(f"[info] {len(todo)} to ask, {len(picked) - len(todo)} cached",
          file=sys.stderr)
    if todo:
        judge = Judge(args.model, args.reasoning_effort, args.timeout,
                      args.temperature)
        run(todo, judge, args, done_path)
        print(f"[info] {judge.calls} calls, {judge.in_tokens} in / "
              f"{judge.out_tokens} out tokens", file=sys.stderr)
        with open(done_path, encoding="utf-8") as fh:
            for line in fh:
                v = json.loads(line)
                done[v["row_id"]] = v

    judged = {r["row_id"]: done[r["row_id"]] for r in picked
              if r["row_id"] in done}
    md = os.path.join(args.out, "audit.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(report(rows, judged))

    tsv = os.path.join(args.out, "audit.tsv")
    by = {r["row_id"]: r for r in rows}
    cols = ["field", "label", "n", "grade", "how", "rid", "verdict",
            "confidence", "suggestion", "other", "note"]
    with open(tsv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for k, v in sorted(judged.items(), key=lambda kv: -by[kv[0]]["n"]):
            w.writerow({**by[k], **v})
    print(f"[ok] {md}\n[ok] {tsv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
