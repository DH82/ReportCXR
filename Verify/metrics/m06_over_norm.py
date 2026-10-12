#!/usr/bin/env python3
"""Metric 1-C -- over-normalization: one label absorbing many surface forms.

The mirror of 1-B, and deliberately NOT scored the same way. A label with
forty surface forms is not evidence of anything on its own -- `pleural_effusion`
legitimately absorbs "effusion", "pleural fluid", "layering fluid". Nothing
contradicts anything, so no self-consistency check can call it wrong, and only
a reader who knows the domain can say whether a merge went too far.

So this metric ranks rather than judges, and its verdict is INFO. Its output
is a worklist, not a score. Treating a ranked list as a failure count is how
an audit starts reporting its own reading of the ontology as data quality.

Measurement lives in `_mapping.py`, shared with 1-B.

    python3 m06_over_norm.py [split]
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = '1-C'
TITLE = 'Over-normalization candidates (one label, many surface forms)'
SCOPE = 'split'
ASKS = ("Which labels absorbed the most distinct surface forms? A ranked "
        "list for a human -- absorbing many forms is not by itself a defect.")

MEANS = """## 한 줄로

**하나의 이름표가 너무 많은 표현을 빨아들이지 않았나.** 1-B 의 정반대다.

## 1-B 와 무엇이 다른가

| | 1-B (과소) | 1-C (과대) |
|---|---|---|
| 실수 | 같은 말을 **안 뭉쳤다** | 다른 말을 **뭉쳤다** |
| 결과 | 한 개념이 둘로 쪼개짐 | 두 개념이 하나로 합쳐짐 |
| 스스로 모순되나 | **그렇다** | **아니다** |

## 왜 채점하지 않고 순위만 매기나

표현 마흔 개를 가진 이름표가 **그 자체로는 아무 문제의 증거도 아니다.**
`pleural_effusion` 은 "effusion", "pleural fluid", "layering fluid" 를 정당하게
전부 빨아들인다. 같은 것을 여러 말로 부른 것이니 뭉치는 게 맞다.

문제는 이것이다 — **아무것도 아무것과 모순되지 않는다.** 1-B 는 "같은 말에 다른
이름표"라서 어느 쪽이든 하나는 틀렸다고 **기계가 말할 수 있다.** 그런데 1-C 는
합친 게 맞는지 지나친지를 **의학을 아는 사람만** 판단할 수 있다.

그래서 이 요소는 판정하지 않고 **순위만 매긴다.** 산출물은 점수가 아니라
**사람이 검토할 작업 목록**이고, 판정은 언제나 `INFO` 다.

> **이 목록의 줄 수를 결함 수로 세면 안 된다.** 그러면 이 감사 도구가 온톨로지를
> 어떻게 해석했는지를, 데이터의 품질인 것처럼 보고하게 된다. 감사가 자기 의견을
> 사실인 척 내보내기 시작하는 지점이 바로 여기다.
"""

from typing import Any, Dict

import core
from core import pct, section, table

from metrics._mapping import measured


def render(res: Dict[str, Any], cfg=None) -> str:
    show_ex = cfg is None or cfg.shows_examples(res["split"])
    body = [section(f"1-C  Over-normalization candidates  ({res['split']})")]
    rows = [[kind, d["labels"], d["multi_form_labels"],
             pct(d["multi_form_labels"], d["labels"])]
            for kind, d in res["over"].items()]
    body.append(table(rows, ["field", "labels", "multi-form", "%"]))

    for kind, d in res["over"].items():
        if not d["top"] or not show_ex:
            continue
        body.append(f"\n**`{kind}` labels absorbing the most distinct "
                    f"surface forms** (review, not a defect):\n")
        body.append(table(
            [[lab, nforms, n, ", ".join(f"{t}:{c}" for t, c in ex)]
             for lab, nforms, n, ex in d["top"]],
            ["label", "forms", "count", "examples"]))
    return "\n".join(body) + "\n"


def run(cfg) -> core.Result:
    per = [measured(sp, cfg.limit) for sp in cfg.splits]
    body = core.summary(
        [[r["split"]] + [v for d in (r["over"]["entity"], r["over"]["anatomy"])
                         for v in (d["labels"], d["multi_form_labels"],
                                   pct(d["multi_form_labels"], d["labels"]))]
         for r in per],
        ["split", "entity labels", "multi-form", "%",
         "anatomy labels", "multi-form", "%"])
    body += core.example_note(cfg.example_split) if cfg.example_split else ""
    body += "\n".join(render(r, cfg) for r in per)
    body += ("\n> **Why this is INFO and not a score.** Nothing here "
             "contradicts anything: a label with many surface forms may be a "
             "correct merge or a collapsed distinction, and only a reader who "
             "knows the domain can tell which. Counting the rows as defects "
             "would report this audit's reading of the ontology as a property "
             "of the data.\n")

    labels = sum(d["multi_form_labels"] for r in per for d in r["over"].values())
    total = sum(d["labels"] for r in per for d in r["over"].values())
    head = (f"{labels:,} of {total:,} labels carry more than one surface form "
            f"-- ranked for review")
    return core.Result(body, core.INFO, head,
                       {"multi_form_labels": labels, "labels": total})


if __name__ == "__main__":
    print(render(measured(_sys.argv[1] if len(_sys.argv) > 1 else "test")))
