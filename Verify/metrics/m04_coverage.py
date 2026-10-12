#!/usr/bin/env python3
"""Metric 1-A -- how much of the canonical form a TABLE actually decided.

Not "are the labels snake_case" (they are, by construction) but how many were
decided by the ontology versus merely lowercased and shipped. The difference is
invisible on disk: right_lower_lobe is in ANATOMY, peribronchial_cuffing_pattern
matched nothing and is canonical only in having no capitals.

  hit rate         table + alias, over all labels
  passthrough      the complement; not automatically a defect
  hapax            labels seen once -- a tail made of these never converged
  top passthrough  the real finding: something said thousands of times that no
                   table names is a missing ontology row

WARNING: this metric is gameable. An identity row in ENTITY_ALIASES moves tens
of thousands of mentions from passthrough to hit without deciding anything.
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = '1-A'
TITLE = 'Ontology coverage'
SCOPE = 'split'          # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Did a table decide this label, or did nothing match and snake() ship "
        "it untouched? Passthrough is the ceiling on what the ontology did.")

MEANS = """## 한 줄로

**이름표를 표에서 찾아 고쳤나, 못 찾아서 그냥 통과시켰나.**

## 세 가지 결과

판독문의 말을 이름표로 바꿀 때 셋 중 하나가 일어난다.

| 결과 | 뜻 | 비유 |
|---|---|---|
| `table` | 표에 그 이름표가 있었다 | 사전에 그 단어가 실려 있었다 |
| `alias` | 표가 **다른 말을 이 이름표로 고쳐 줬다** | 사전이 "흉수 → pleural effusion" 이라고 알려 줬다 |
| `passthrough` | 아무것도 안 맞았다. 소문자로만 바꿔서 그대로 내보냈다 | **사전에 없어서 그냥 넘어갔다** |

가운데(`alias`)가 가장 의미 있다. 표가 실제로 **일을 했다**는 뜻이기 때문이다.

## passthrough 가 많으면 나쁜가

꼭 그렇지는 않다. 판독문 어휘에는 아주 드물게 쓰이는 말이 끝없이 있고, 어떤
표도 그걸 다 담을 수는 없다. 다만 **"정리 작업 중 표 덕분이라고 말할 수 있는
몫의 천장"** 이 그만큼 낮다는 뜻이다.

## ⚠️ 이 숫자는 조작할 수 있다 — 목표로 삼으면 안 된다

이 지표는 "이름표가 승인 목록에 있나"로 판정한다. 그런데 표에는 이런 줄을
넣을 수 있다.

    "consolidation" → "consolidation"      (자기를 자기로 바꾼다)

**아무 일도 안 하는 줄이지만, 이 한 줄로 수만 건이 `passthrough` 에서 `적중`
으로 넘어간다.** 실제로 표에 그런 줄이 여럿 있다.

**그래서 이 요소의 판정은 `INFO` 다** — 점수가 아니라 참고 수치라는 뜻이다.
점수처럼 생겼다고 점수로 쓰면 안 된다.

## 진짜 원인

적중률이 안 오르는 이유는 별칭이 부족해서가 아니라 **타입별 이름표 목록이
없어서**다. `질병` 과 `기구` 목록은 있는데 `해부학적 상태` · `수술 후 상태` ·
`기타` 용 목록이 없다. 그것들은 비교할 대상이 없으니 전부 `passthrough` 가 된다.
"""


import collections
from typing import Any, Dict, List, Optional

import core
from core import (classify_anatomy, classify_descriptor, classify_entity,
                    propositions, pct, section, table)


def measure(split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    kinds = ("entity", "anatomy", "descriptor")
    klass = {k: collections.Counter() for k in kinds}
    freq = {k: collections.Counter() for k in kinds}
    passthrough = {k: collections.Counter() for k in kinds}

    for _rec, prop in propositions(split, limit):
        ent = (prop.get("entity") or {}).get("label")
        klass["entity"][classify_entity(ent)] += 1
        if ent:
            freq["entity"][ent] += 1
            if classify_entity(ent) == "passthrough":
                passthrough["entity"][ent] += 1

        for a in prop.get("anatomy") or []:
            lab = a.get("label")
            c = classify_anatomy(lab)
            klass["anatomy"][c] += 1
            if lab:
                freq["anatomy"][lab] += 1
                if c == "passthrough":
                    passthrough["anatomy"][lab] += 1

        for d in prop.get("descriptors") or []:
            lab = d.get("label")
            c = classify_descriptor(lab)
            klass["descriptor"][c] += 1
            if lab:
                freq["descriptor"][lab] += 1
                if c == "passthrough":
                    passthrough["descriptor"][lab] += 1

    out: Dict[str, Any] = {"split": split, "kinds": {}}
    for k in kinds:
        c = klass[k]
        total = sum(c.values()) - c["missing"]
        hit = c["table"] + c["alias"]
        out["kinds"][k] = {
            "total": total,
            "missing": c["missing"],
            "table": c["table"],
            "alias": c["alias"],
            "passthrough": c["passthrough"],
            "hit_rate": (hit / total) if total else 0.0,
            "distinct": len(freq[k]),
            "hapax": sum(1 for v in freq[k].values() if v == 1),
            "top_passthrough": passthrough[k].most_common(15),
        }
    return out


def render(res: Dict[str, Any], cfg=None) -> str:
    show_ex = cfg is None or cfg.shows_examples(res["split"])
    rows: List[List[Any]] = []
    for kind, d in res["kinds"].items():
        rows.append([
            kind, d["total"], d["table"], d["alias"], d["passthrough"],
            pct(d["table"] + d["alias"], d["total"]),
            d["distinct"], d["hapax"], pct(d["hapax"], d["distinct"]),
        ])
    body = [section(f"1-A  Ontology coverage  ({res['split']})"),
            table(rows, ["field", "labels", "table", "alias", "passthru",
                         "hit rate", "distinct", "hapax", "hapax %"])]

    for kind, d in res["kinds"].items():
        if not d["top_passthrough"] or not show_ex:
            continue
        body.append(f"\n**Most frequent unmatched `{kind}` labels** "
                    f"(candidate ontology rows):\n")
        body.append(table([[lab, n] for lab, n in d["top_passthrough"]],
                          ["label", "count"]))
    return "\n".join(body) + "\n"


def _join(parts):
    return "\n".join(parts)


def run(cfg) -> core.Result:
    per = [measure(sp, cfg.limit) for sp in cfg.splits]
    body = core.summary(
        [[r["split"]] + [f"{r['kinds'][k]['hit_rate']:.1%}"
                         for k in ("entity", "anatomy", "descriptor")]
         + [f"{r['kinds']['entity']['passthrough']:,}"] for r in per],
        ["split", "entity hit", "anatomy hit", "descriptor hit",
         "entity passthrough"],
        "A hit rate that is flat across four splits is a structural property "
        "of the ontology, not sampling noise -- which is what makes the "
        "gameability warning below the important part of this metric.")
    body += _join(render(r, cfg) for r in per)
    body += ("\n> **This number is gameable and must not be a target.** "
             "`classify_entity` asks whether a label is in an approved set, "
             "and `ENTITY_ALIASES` contains identity rows "
             "(`\"consolidation\": \"consolidation\"`). One such row moves "
             "thousands of mentions from passthrough to hit without any "
             "normalization having happened. Read it as a ceiling, not a "
             "score.\n")

    rates = {}
    for kind in ("entity", "anatomy", "descriptor"):
        hit = sum(r["kinds"][kind]["table"] + r["kinds"][kind]["alias"]
                  for r in per)
        tot = sum(r["kinds"][kind]["total"] for r in per)
        rates[kind] = hit / tot if tot else 0.0
    verdict = core.INFO
    head = " | ".join(f"{k} {v:.1%}" for k, v in rates.items()) + " hit rate"
    return core.Result(body, verdict, head, rates)


if __name__ == "__main__":
    import sys
    sp = sys.argv[1] if len(sys.argv) > 1 else "test"
    print(render(measure(sp)))
