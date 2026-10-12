#!/usr/bin/env python3
"""The flagged records only -> what the model thinks they should say instead.

A second pass, deliberately. audit_records.py detects and is forbidden to
propose, because one call asked for both is pulled two ways: the work of
rewriting a record suppresses borderline flags, and needing to produce a
correction manufactures issues to correct. Splitting them lets each be wrong
in only one direction, which is the direction each can be measured in.

It follows that this pass is only as good as the flags it is handed. Run
GPT/goldset.py first: repairing a code whose precision is 0.4 is work spent
on noise, and the output will look just as tidy either way.

Nothing here is written back into jsonl/. The proposals land beside the audit,
for a human and Verify/ to argue with.

    python3 GPT/repair.py                      # every flagged utterance
    python3 GPT/repair.py --verdict dropped    # one code
    python3 GPT/repair.py --min-confidence high --severity blocking
    python3 GPT/repair.py --dry-run
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as futures
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "Prompt2"))

import audit_records as A                                       # noqa: E402
from vocabulary import (ANATOMY_ROLES, ANATOMY_SOURCES, ASSERTION_LABELS,  # noqa: E402
                        COMPARISON_LABELS, DESCRIPTOR_TYPES, ENTITY_TYPES,
                        LATERALITY, ZONES)

OUTDIR = os.path.join(REPO, "out", "gpt_records")


def _nullable(*types):
    return {"type": list(types) + ["null"]}


# Spelled out so a proposal cannot invent a field or an enum value: a
# correction that does not fit the schema is not a correction.
PROPOSITION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "entity", "anatomy", "descriptors", "assertion",
                 "comparison", "derived_from"],
    "properties": {
        "id": {"type": "string"},
        "entity": {"type": "object", "additionalProperties": False,
                   "required": ["text", "label", "type"],
                   "properties": {"text": _nullable("string"),
                                  "label": {"type": "string"},
                                  "type": {"type": "string",
                                           "enum": ENTITY_TYPES}}},
        "anatomy": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["text", "label", "laterality", "zone", "role",
                         "source"],
            "properties": {"text": _nullable("string"),
                           "label": _nullable("string"),
                           "laterality": {"type": "string", "enum": LATERALITY},
                           "zone": {"type": ["string", "null"],
                                    "enum": list(ZONES)},
                           "role": {"type": "string", "enum": ANATOMY_ROLES},
                           "source": {"type": "string",
                                      "enum": ANATOMY_SOURCES}}}},
        "descriptors": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["text", "type", "label"],
            "properties": {"text": _nullable("string"),
                           "type": {"type": "string",
                                    "enum": DESCRIPTOR_TYPES},
                           "label": {"type": "string"}}}},
        "assertion": {"type": "object", "additionalProperties": False,
                      "required": ["label", "cue"],
                      "properties": {"label": {"type": "string",
                                               "enum": ASSERTION_LABELS},
                                     "cue": _nullable("string")}},
        "comparison": {"type": "object", "additionalProperties": False,
                       "required": ["label", "cue"],
                       "properties": {"label": {"type": "string",
                                                "enum": COMPARISON_LABELS},
                                      "cue": _nullable("string")}},
        "derived_from": _nullable("string"),
    },
}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["utterance_id", "propositions", "warnings", "changed",
                 "rationale"],
    "properties": {
        "utterance_id": {"type": "string"},
        "propositions": {"type": "array", "items": PROPOSITION_SCHEMA},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "changed": {"type": "array", "items": {"type": "string"},
                    "description": "what this proposal changes, one line each"},
        "rationale": {"type": "string"},
    },
}

SYSTEM_PROMPT = f"""You repair one utterance's extraction. An audit has already \
decided that something is wrong with it and told you what; your job is only to \
write what the record should be.

You are given the utterance, the section, the propositions as they stand, and
the issues the audit raised. Produce the COMPLETE corrected propositions array
for this utterance.

RULES
  1. Change only what the issues name. Everything else is copied through
     byte for byte. A proposal that quietly rewrites a field nobody
     questioned cannot be reviewed, because the reviewer cannot tell the
     repair from the drift.
  2. Every `text` and every `cue` must be a contiguous span of the utterance,
     copied exactly -- same characters, same order, nothing added.
  3. Keep proposition ids stable where the proposition survives. A new
     proposition gets the next free id.
  4. If the correct answer is zero propositions, return an empty array.
  5. Information has one home. A label never carries side (that is
     `laterality`), severity or normality (a descriptor), or where a device
     ends (`anatomy.role` = "tip_location").
  6. anatomy `source`: "utterance" only when the sentence names the
     structure, and then `text` is that span. Otherwise "entity_semantics"
     (implied by the finding), "section_context" (from the heading), or
     "linked_proposition" (inherited), and `text` is null.
  7. If you disagree that there is a defect, say so in `rationale` and return
     the propositions unchanged. Do NOT invent a change to satisfy the
     request -- an audit is wrong sometimes and a repair that pretends
     otherwise hides it.

Closed vocabularies you must stay inside:
  entity.type       {', '.join(ENTITY_TYPES)}
  laterality        {', '.join(LATERALITY)}
  anatomy.role      {', '.join(ANATOMY_ROLES)}
  anatomy.source    {', '.join(ANATOMY_SOURCES)}
  descriptor.type   {', '.join(DESCRIPTOR_TYPES)}
  assertion.label   {', '.join(ASSERTION_LABELS)}
  comparison.label  {', '.join(COMPARISON_LABELS)}

List in `changed` one line per difference from the input, in the form
"p1.assertion: present -> absent". Return JSON only."""


def build_user(rec, issues):
    out = [f"utterance_id: {rec['utterance_id']}",
           f"section: {rec['section']}",
           f"utterance: {rec['utterance']}",
           "",
           "propositions as they stand:"]
    for p in rec["propositions"]:
        out.append("  " + json.dumps(p, ensure_ascii=False))
    if not rec["propositions"]:
        out.append("  (none)")
    if rec.get("warnings"):
        out.append(f"warnings: {'; '.join(rec['warnings'])}")
    out += ["", "issues the audit raised:"]
    for i in issues:
        out.append(f"  [{i['proposition_id'] or '-'}] {i['field']} — "
                   f"{i['verdict']} ({i['severity']}/{i['confidence']})")
        if i.get("quote"):
            out.append(f"      근거: \"{i['quote']}\"")
        if i.get("note"):
            out.append(f"      {i['note']}")
    return "\n".join(out)


class Repairer:
    def __init__(self, model, effort, timeout, temperature=None):
        from openai import OpenAI
        self.client = OpenAI(timeout=timeout, max_retries=2)
        self.model, self.effort, self.temperature = model, effort, temperature
        self.calls = 0
        self.in_tokens = self.out_tokens = 0
        self.lock = threading.Lock()

    def ask(self, rec, issues):
        kwargs = {"model": self.model,
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user",
                                "content": build_user(rec, issues)}],
                  "response_format": {"type": "json_schema",
                                      "json_schema": {"name": "repair",
                                                      "strict": True,
                                                      "schema": SCHEMA}}}
        if self.effort:
            kwargs["reasoning_effort"] = self.effort
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        rsp = self.client.chat.completions.create(**kwargs)
        data = json.loads(rsp.choices[0].message.content)
        with self.lock:
            self.calls += 1
            if rsp.usage:
                self.in_tokens += rsp.usage.prompt_tokens
                self.out_tokens += rsp.usage.completion_tokens
        data["utterance_id"] = rec["utterance_id"]
        return data


def verify_spans(rec, proposal):
    """A proposal whose spans are not in the sentence is not a proposal.

    The same check precheck.py runs over the data, run over the repair before
    anyone reads it -- rule 2 is the one a model breaks most often, and a
    reviewer should not have to be the one who notices.
    """
    hay = " ".join((rec["utterance"] or "").lower().split())
    bad = []

    def seen(span):
        return not span or " ".join(span.lower().split()) in hay

    for p in proposal.get("propositions", []):
        if not seen((p.get("entity") or {}).get("text")):
            bad.append(f"{p['id']}.entity.text")
        for a in p.get("anatomy") or []:
            if a.get("source") == "utterance" and not seen(a.get("text")):
                bad.append(f"{p['id']}.anatomy.text")
            if a.get("source") != "utterance" and a.get("text") is not None:
                bad.append(f"{p['id']}.anatomy.text(should be null)")
        for d in p.get("descriptors") or []:
            if not seen(d.get("text")):
                bad.append(f"{p['id']}.descriptor.text")
        for f in ("assertion", "comparison"):
            if not seen((p.get(f) or {}).get("cue")):
                bad.append(f"{p['id']}.{f}.cue")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default=A.RECORDS)
    ap.add_argument("--out", default=None,
                    help="default: out/gpt_records/<arm>/")
    ap.add_argument("--model", default=A.MODEL)
    ap.add_argument("--reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--verdict", action="append", help="이 코드만, 반복 가능")
    ap.add_argument("--severity", action="append",
                    choices=["blocking", "major", "minor"])
    ap.add_argument("--min-confidence", choices=["high", "medium", "low"],
                    default="low")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=A.WORKERS)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.out = A.out_for(a.records, a.out)
    print(f"[info] arm={A.arm_of(a.records)} out={a.out}", file=sys.stderr)

    flag_path = os.path.join(a.out, "flagged.jsonl")
    if not os.path.exists(flag_path):
        print(f"[error] {flag_path} 없음 — 먼저 audit_records.py 를 돌리십시오.",
              file=sys.stderr)
        return 1
    rows = [json.loads(l) for l in open(flag_path, encoding="utf-8")
            if l.strip()]

    rank = {"high": 0, "medium": 1, "low": 2}
    keep = [r for r in rows
            if (not a.verdict or r["verdict"] in a.verdict)
            and (not a.severity or r.get("severity") in a.severity)
            and rank.get(r.get("confidence"), 3) <= rank[a.min_confidence]]

    recs = {r["utterance_id"]: r for rep in A.load_reports(a.records)
            for r in rep["records"]}
    byu = collections.defaultdict(list)
    for r in keep:
        byu[r["utterance_id"]].append(r)
    todo = sorted(byu)
    if a.limit:
        todo = todo[:a.limit]
    print(f"[info] 이슈 {len(keep)}/{len(rows)}건 · 발화 {len(todo)}건 "
          f"= {len(todo)} 콜", file=sys.stderr)
    if not todo:
        return 1

    os.makedirs(a.out, exist_ok=True)
    done_path = os.path.join(a.out, "repairs.jsonl")
    done = {}
    if os.path.exists(done_path) and not a.refresh:
        for line in open(done_path, encoding="utf-8"):
            line = line.strip()
            if line:
                v = json.loads(line)
                done[v["utterance_id"]] = v

    if a.dry_run:
        print(SYSTEM_PROMPT)
        print("\n" + "=" * 70 + "\n")
        print(build_user(recs[todo[0]], byu[todo[0]]))
        return 0

    ask = [u for u in todo if u not in done]
    print(f"[info] {len(ask)} 물어봄, {len(todo) - len(ask)} 캐시",
          file=sys.stderr)
    if ask:
        rp = Repairer(a.model, a.reasoning_effort, a.timeout, a.temperature)
        fh = open(done_path, "a", encoding="utf-8")
        lock = threading.Lock()

        def work(uid):
            for attempt in range(3):
                try:
                    return rp.ask(recs[uid], byu[uid])
                except Exception as exc:                      # noqa: BLE001
                    if attempt == 2:
                        print(f"[error] {uid}: {exc}", file=sys.stderr)
                        return None
                    time.sleep(2 ** attempt)

        t0 = time.time()
        with futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
            for i, got in enumerate(pool.map(work, ask), 1):
                if got:
                    got["span_violations"] = verify_spans(
                        recs[got["utterance_id"]], got)
                    with lock:
                        fh.write(json.dumps(got, ensure_ascii=False) + "\n")
                        fh.flush()
                print(f"[{i}/{len(ask)}] {rp.calls} calls, "
                      f"{time.time() - t0:.0f}s", file=sys.stderr)
        fh.close()
        for line in open(done_path, encoding="utf-8"):
            line = line.strip()
            if line:
                v = json.loads(line)
                done[v["utterance_id"]] = v

    md = ["# 수정 제안 — 아직 반영되지 않았습니다\n",
          f"발화 {len(done)}건. `jsonl/` 은 건드리지 않았습니다.\n",
          "각 항목은 **현재 → 제안** 과, 모델이 스스로 적은 변경 목록입니다. "
          "`changed` 에 없는 차이가 보이면 그건 드리프트이지 수정이 "
          "아닙니다.\n"]
    nviol = nnochange = 0
    for uid in sorted(done):
        v = done[uid]
        rec = recs.get(uid)
        if not rec:
            continue
        md.append(f"\n---\n\n### `{uid}`\n")
        md.append(f"- 원문: **{rec['utterance']}**")
        for i in byu.get(uid, []):
            md.append(f"- 지적: {i['verdict']} · {i['field']} "
                      f"({i.get('severity','')}/{i.get('confidence','')})")
        if not v.get("changed"):
            nnochange += 1
            md.append("- **모델이 수정할 것이 없다고 판단** "
                      f"— {v.get('rationale','')}")
        for c in v.get("changed", []):
            md.append(f"  - 변경: `{c}`")
        if v.get("span_violations"):
            nviol += 1
            md.append(f"  - ⚠ **스팬 위반**: {', '.join(v['span_violations'])} "
                      f"— 이 제안은 원문에 없는 글자를 씁니다")
        md.append(f"- 현재: `{json.dumps(rec['propositions'], ensure_ascii=False)}`")
        md.append(f"- 제안: `{json.dumps(v.get('propositions'), ensure_ascii=False)}`")
        if v.get("rationale"):
            md.append(f"- 근거: {v['rationale']}")
        md.append("- 검토: ( ) 채택  ( ) 기각  — ")
    md.insert(3, f"스팬 위반 {nviol}건 · 모델이 수정 불요라고 본 것 "
                 f"{nnochange}건.\n")
    p = os.path.join(a.out, "repairs.md")
    open(p, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(f"[ok] {done_path}\n[ok] {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
