#!/usr/bin/env python3
"""Metric 0 -- did normalization run, and is it stable?

Normalization is idempotent, so running step 2 over the shipped file separates
three different problems: the pass was skipped, it ran against another
ontology, or it is not idempotent.

Two numbers, and they are not the same thing:

    NOTES      what normalize.py says it changed   -> diagnostics
    NET DIFF   what actually differs afterwards    -> the verdict

They disagree when a pair of rules fires and cancels (a laterality filled from
the label, then dropped by rule 4): hundreds of notes, zero net change. Any
audit that grades the notes instead of the diff grades events that never
happened.

DEPENDENCY: Pipeline/normalize.py is the default; --normalize points at another
checkout. Either way the module is imported with THIS repo's package path
FIRST, so the normalizer always runs against the ontology that produced the data.
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = '0'
TITLE = 'Fixed point'
SCOPE = 'split'          # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Re-run step 2 on an already-normalized file: does anything change? "
        "If it does, the normalizer is not idempotent.")

MEANS = """## 한 줄로

**정리 규칙을 한 번 더 돌려도 아무것도 안 바뀌어야 한다.**

## 무슨 말인가

데이터를 만들 때 2단계에서 **정리(정규화)** 를 한다. 표를 보고 이름표를 통일하고,
빈 칸을 채우고, 형식을 맞춘다.

정리가 제대로 됐다면 **한 번 더 돌려도 바뀔 게 없어야 한다.** 방 청소를 끝낸
뒤에 다시 청소해도 더 치울 게 없는 것과 같다. 다시 돌렸는데 뭔가 바뀐다면
**정리 규칙 자체에 버그가 있다는 뜻**이다.

이렇게 "더 이상 안 변하는 상태"를 **고정점**이라고 부른다.

## 가장 중요한 함정

> **통과했다고 표가 옳은 것이 절대 아니다.**
>
> `pleural_effusion` 과 `effusion` 을 **따로 두는** 표도,
> **합쳐 두는** 표도 — 둘 다 완벽한 고정점이다.
> 둘 다 두 번 돌려도 안 바뀌기 때문이다.
>
> 즉 이 검사가 증명하는 것은 오직 **"정리가 실행되었고 멈췄다"** 까지다.
> **멈춘 그 자리가 옳은지는 전혀 말해 주지 않는다.** 그건 1-A ~ 1-F 가 묻는다.

## 왜 그래도 중요한가

고정점이 아니면 **이 리포트가 어느 버전의 파일에 대한 것인지 확정되지 않는다.**
돌릴 때마다 답이 달라지는 데이터로 잰 숫자는 근거가 될 수 없다. 그래서 판정은
`PASS` 아니면 `FAIL` 이고 중간이 없다.

## 서로 상쇄되는 기록에 주의

정리 기록을 보면 **규칙 하나가 값을 채우고 다른 규칙이 곧바로 그걸 버리는**
왕복이 보인다. 결과적으로 아무 일도 안 일어났지만 기록은 두 줄 남는다.
합계만 보면 오해하기 쉬우니, 정확히 보려면 `tools/diff_probe.py` 를 쓴다.
"""


import collections
import copy
import importlib.util
import os
import sys
from typing import Any, Dict, List, Optional

import core
from core import REPO, propositions, records, pct, section, table

DEFAULT_NORMALIZE = os.path.join(REPO, "Pipeline", "normalize.py")


def load_normalizer(path: str):
    """Import normalize.py from another checkout, ours ontology first.

    sys.path already has REPO in front (common.py put it there), so the
    normalizer's `from Prompt2.ontology import ...` resolves to this
    repository's tables, not its own.
    """
    if not os.path.exists(path):
        return None
    pkg_dir = os.path.dirname(os.path.abspath(path))
    if pkg_dir in sys.path:
        sys.path.remove(pkg_dir)
    sys.path.append(pkg_dir)          # appended: never shadows our Prompt/
    spec = importlib.util.spec_from_file_location("_norm_step2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _strip(rec: Dict[str, Any]) -> Dict[str, Any]:
    """The record as the dataset carries it -- audit fields removed."""
    out = {k: v for k, v in rec.items()
           if k not in ("normalization", "review", "row_id", "study_id")}
    return out


def measure(split: str, normalize_path: str = DEFAULT_NORMALIZE,
            limit: Optional[int] = None) -> Dict[str, Any]:
    mod = load_normalizer(normalize_path)
    if mod is None:
        return {"split": split, "available": False, "path": normalize_path}

    notes = collections.Counter()
    noted_records = 0
    net_records = 0
    changed_fields = collections.Counter()
    examples: List[Dict[str, Any]] = []
    total = 0

    for rec in records(split, limit):
        total += 1
        before = _strip(rec)
        after = mod.normalize_record(copy.deepcopy(before))
        note_items = after.pop("normalization", []) or []
        if note_items:
            noted_records += 1
            for n in note_items:
                notes[n["code"]] += 1
        if after != before:
            net_records += 1
            if before.get("section") != after.get("section"):
                changed_fields["section"] += 1
            for p0, p1 in zip(before.get("propositions") or [],
                              after.get("propositions") or []):
                for key in p0:
                    if p0.get(key) != p1.get(key):
                        changed_fields[key] += 1
            if len(examples) < 5:
                examples.append({
                    "utterance": (before.get("utterance") or "")[:90],
                    "section_before": before.get("section"),
                    "section_after": after.get("section"),
                })

    # A code that always appears the same number of times as another, on a
    # file with no net change, is a cancelling pair.
    counts = collections.Counter(notes)
    pairs = [(a, b, counts[a]) for i, a in enumerate(sorted(counts))
             for b in sorted(counts)[i + 1:]
             if counts[a] == counts[b] and counts[a] > 10]

    return {
        "split": split, "available": True, "records": total,
        "noted_records": noted_records, "net_records": net_records,
        "notes": notes.most_common(20),
        "changed_fields": changed_fields.most_common(),
        "cancelling_pairs": pairs,
        "examples": examples,
    }


def render(res: Dict[str, Any], cfg=None) -> str:
    show_ex = cfg is None or cfg.shows_examples(res["split"])
    if not res.get("available"):
        return (section(f"0  Fixed-point check  ({res['split']})") +
                f"SKIPPED -- normalize.py not found at `{res['path']}`.\n"
                f"Pass --normalize /path/to/normalize.py to enable it.\n")

    body = [section(f"0  Fixed-point check  ({res['split']})"),
            table([[res["records"], res["noted_records"],
                    pct(res["noted_records"], res["records"]),
                    res["net_records"],
                    pct(res["net_records"], res["records"])]],
                  ["records", "records with notes", "%",
                   "records with NET diff", "%"]),
            "\n**Verdict**: " + (
                "fixed point -- step 2 ran on this file."
                if res["net_records"] == 0 else
                f"{res['net_records']} record(s) still change. "
                f"Step 2 was skipped, ran against another ontology, or is "
                f"not idempotent here.") + "\n"]

    if res["changed_fields"]:
        body.append("\n**Fields that actually differ**\n")
        body.append(table([[k, v] for k, v in res["changed_fields"]],
                          ["field", "records"]))
    if res["notes"]:
        body.append("\n**Notes emitted** (diagnostic -- not proof of change)\n")
        body.append(table([[k, v] for k, v in res["notes"]],
                          ["code", "count"]))
    if res["cancelling_pairs"]:
        body.append("\n**Cancelling note pairs** -- equal counts on a file "
                    "that barely changes. These inflate the audit trail:\n")
        body.append(table([[a, b, n] for a, b, n in res["cancelling_pairs"]],
                          ["code A", "code B", "count"]))
    if res["examples"] and show_ex:
        body.append("\n**Examples of real change**\n")
        body.append(table(
            [[e["utterance"], repr(e["section_before"]),
              repr(e["section_after"])] for e in res["examples"]],
            ["utterance", "section before", "section after"]))
    return "\n".join(body) + "\n"


def _join(parts):
    return "\n".join(parts)


def run(cfg) -> core.Result:
    path = cfg.normalize_path or DEFAULT_NORMALIZE
    per = [measure(sp, path, cfg.limit) for sp in cfg.splits]
    body = core.summary(
        [[r["split"]] + (["(normalize.py not importable)", "", ""]
                         if not r["available"] else
                         [f"{r['records']:,}", f"{r['net_records']:,}",
                          # changed_fields is Counter.most_common() -- a list
                          # of (field, count) pairs, not a mapping.
                          ", ".join(f"{k}:{v}" for k, v in
                                    r["changed_fields"]) or "—"])
         for r in per],
        ["split", "records", "still change", "fields that change"],
        "Zero in `still change` is the fixed point. It proves step 2 ran and "
        "settled -- NOT that what it settled on is right.")
    body += _join(render(r, cfg) for r in per)

    if not any(r["available"] for r in per):
        return core.Result(body, core.SKIP, f"normalize.py not importable ({path})")
    seen = [r for r in per if r["available"]]
    net = sum(r["net_records"] for r in seen)
    verdict = core.PASS if net == 0 else core.FAIL
    head = (f"fixed point reached on {len(seen)} split(s)" if net == 0
            else f"{net:,} records still change on re-normalization")
    body += ("\n> **A fixed point is not a correct ontology.** A table that "
             "splits `pleural_effusion` from `effusion` and one that merges "
             "them are both perfect fixed points. This metric proves step 2 "
             "RAN and settled -- 1-A through 1-F ask whether what it settled "
             "on is right.\n")
    return core.Result(body, verdict, head, {"net_records": net})


if __name__ == "__main__":
    sp = sys.argv[1] if len(sys.argv) > 1 else "test"
    print(render(measure(sp)))
