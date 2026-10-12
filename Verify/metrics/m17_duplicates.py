#!/usr/bin/env python3
"""Metric P2 -- one concept, two label spellings.

The opposite stance to 1-D: take only what is near-certain at the STRING level,
so no clinical judgement is needed and false positives stay near zero.

  D1  singular/plural   rib_fracture / rib_fractures
  D2  synonym stems     bony_structures / osseous_structures
  D3  measurement in a label   above_carina absorbing "2.5 cm above the carina"
  D4  word order        mediastinal_hilar_contours / hilar_mediastinal_contours

Labels whose word order reverses the meaning (right_greater_than_left) are
excluded from key building on purpose.

    python3 m17_duplicates.py [--all]
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'P2'
TITLE = 'Same concept, split labels'
SCOPE = 'corpus'         # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Which labels are the same concept split in two by a plural, a tense "
        "or a word order -- `contours` vs `contour`?")

MEANS = """## 한 줄로

**단수·복수나 어순 때문에 같은 개념이 두 이름표로 갈린 것을 찾는다.**

## 예시

    contours : 9,958개    vs    contour : 24개
    nasogastric_tube : 9,768개  vs  nasogastric_tubes : 14개
    lung_volume : 3,807개  vs  lung_volumes : 3,798개

마지막 줄이 특히 나쁘다. **거의 반반**이라 어느 쪽이 정식인지 아무도 정하지
않았다는 뜻이다.

## 1-D 와 어떻게 다른가

**같은 결함을 정반대 방향에서 찾는다.**

| | P2 (이 요소) | 1-D |
|---|---|---|
| 찾는 방법 | **글자가 비슷한 것** | **글자가 전혀 안 겹치는 것** |
| 판정 근거 | 단어 모양 | RadLex 계층 |
| 오답 비율 | 거의 0 | 계층이 없으면 판정 불가 |

**하나만으로는 절반을 놓친다.** 그래서 둘 다 있다.

## 설계 원칙 — 오답을 0 에 가깝게

**오답이 섞인 목록은 쓸모가 없다.** 하나라도 틀린 게 보이면 사람이 목록 전체를
안 믿게 되기 때문이다. 그래서 **의학 판단이 전혀 필요 없는 것만** 남긴다.

> **개발 중에 오답을 하나 잡았다.** 초기 구현은 낱말을 알파벳순으로 정렬해
> 열쇠를 만들었는데, 그러면 이렇게 된다.
>
>     right_greater_than_left   (오른쪽이 왼쪽보다 심하다)
>     left_greater_than_right   (왼쪽이 오른쪽보다 심하다)
>     → 정렬하면 둘 다 "greater left right than" → 같은 묶음!
>
> **중복이 아니라 정반대 뜻**이다. 어순이 의미를 뒤집는 낱말이 든 이름표는
> 열쇠를 만들지 않도록 고쳤다.

## 덤으로 찾는 것

이름표에 **측정값이 섞여 들어간 것**(`tip_4cm_above_carina`, `8_mm`)도 같이
낸다. 다만 해부학적 번호(`L1` 척추, `8th_rib` 8번 갈비뼈)는 정당한 이름이므로
제외한다.

## split 별 표를 읽을 때

**행끼리 직접 비교하면 안 된다.** 이름표가 한 split 에서 일정 횟수 이상 나와야
후보가 되므로, 같은 결함률이라도 **작은 split 이 적게 보고한다.** 그 split
크기에 대한 비율로 읽어야 한다.
"""


import argparse
import collections
import re

import core
from core import ONT, SMALL, SPLITS, propositions, table

FIELDS = ("entity", "anatomy", "descriptor")

# Stems used interchangeably in reports: a lexical fact, not a clinical call.
STEM_SYN = {
    "bony": "osseous", "boney": "osseous", "bone": "osseous",
    "low": "lower", "hi": "upper", "high": "upper",
    "cardiac": "heart", "pulmonary": "lung", "osseus": "osseous",
}
_NUM = re.compile(r"\d")
# Only a number with a unit counts; L1, T12, 8th_rib are anatomical numbering.
_MEASURE = re.compile(r"\d\s*_?(cm|mm|centimeter|millimeter)(_|$)")

# Sorting words destroys order. Labels containing these words have their
# meaning reversed by order (right_greater_than_left vs left_greater_than_right),
# so no key is built for them.
ORDER_SENSITIVE = {"greater", "worse", "more", "less", "than", "versus", "vs"}

# Since E1, singular and collective plural differ ON PURPOSE: lung + laterality
# is one side, lungs is both. Reporting that pair as a duplicate would propose
# undoing E1.
BY_DESIGN = {frozenset((k, v)) for k, v in ONT.BILATERAL_COLLECTIVE.items()}

_IRREG = {"hila": "hilum", "apices": "apex", "bases": "base",
          "bronchi": "bronchus", "pleurae": "pleura", "vertebrae": "vertebra",
          "hemidiaphragms": "hemidiaphragm", "lungs": "lung", "lobes": "lobe"}


def singular(w: str) -> str:
    if w in _IRREG:
        return _IRREG[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ses") and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def key_of(label: str):
    """Key for duplicate detection: depluralize, fold synonym stems, sort.

    Returns None for labels whose word order reverses the meaning, so they
    are never grouped.
    """
    ws = [w for w in label.split("_") if w]
    if any(w in ORDER_SENSITIVE for w in ws):
        return None
    return " ".join(sorted(STEM_SYN.get(singular(w), singular(w)) for w in ws))


def collect(splits):
    freq = {f: collections.Counter() for f in FIELDS}
    for sp in splits:
        for _rec, p in propositions(sp):
            e = p.get("entity") or {}
            if e.get("label"):
                freq["entity"][e["label"]] += 1
            for a in p.get("anatomy") or []:
                if a.get("label"):
                    freq["anatomy"][a["label"]] += 1
            for d in p.get("descriptors") or []:
                if d.get("label"):
                    freq["descriptor"][d["label"]] += 1
    return freq


def _totals(splits, min_freq=5):
    """(duplicate groups, mentions on a minority spelling) across all fields.

    report() computes these while rendering; run() needs them as numbers for
    the index row, and recomputing is cheaper than threading them out of the
    prose.
    """
    freq = collect(splits)
    groups = loss = 0
    for field in FIELDS:
        buckets = collections.defaultdict(list)
        for l, n in freq[field].items():
            if n < min_freq:
                continue
            k = key_of(l)
            if k is not None:
                buckets[k].append((l, n))
        dups = {k: sorted(v, key=lambda x: -x[1])
                for k, v in buckets.items()
                if len(v) > 1 and frozenset(l for l, _n in v) not in BY_DESIGN}
        groups += len(dups)
        loss += sum(sum(n for _l, n in v) - v[0][1] for v in dups.values())
    return groups, loss


def report(splits, min_freq=5) -> str:
    freq = collect(splits)
    out = ["### P2  One concept, split labels\n",
           "Only what needs no clinical judgement; the list is useless with "
           "false positives in it.\n"]
    grand = 0
    for field in FIELDS:
        c = freq[field]
        groups = collections.defaultdict(list)
        for l, n in c.items():
            if n < min_freq:
                continue
            k = key_of(l)
            if k is not None:
                groups[k].append((l, n))
        dups = {k: sorted(v, key=lambda x: -x[1])
                for k, v in groups.items()
                if len(v) > 1
                and frozenset(l for l, _n in v) not in BY_DESIGN}
        loss = sum(sum(n for _l, n in v) - v[0][1] for v in dups.values())
        grand += loss
        out.append(f"\n**{field}** -- {len(dups)} duplicate groups; "
                   f"{loss:,} mentions sit on the minority spelling\n")
        rows = []
        for k, v in sorted(dups.items(),
                           key=lambda x: -sum(n for _l, n in x[1]))[:12]:
            rows.append([" / ".join(f"{l}:{n:,}" for l, n in v[:4]),
                         f"{sum(n for _l, n in v):,}"])
        if rows:
            out.append(table(rows, ["split labels (count)", "total"]))

        # D3 -- measurement inside a label; anatomical numbering is excluded.
        meas = [(l, n) for l, n in c.items() if _MEASURE.search(l) and n >= 2]
        if meas:
            meas.sort(key=lambda x: -x[1])
            out.append(f"\nD3 measurement inside a label -- {len(meas)} labels / "
                       f"{sum(n for _l, n in meas):,} mentions "
                       f"(anatomical numbering such as L1 or 8th_rib is excluded)\n")
            out.append(table([[l, f"{n:,}"] for l, n in meas[:8]],
                             ["label", "mentions"]))
    out.append(f"\n**Total: {grand:,} mentions on a minority spelling.** "
               f"Merging them is deterministic and needs no clinical judgement.\n")
    return "\n".join(out)


def _join(parts):
    return "\n".join(parts)


def run(cfg) -> core.Result:
    body = core.summary(
        [[sp] + list(_totals([sp], cfg.min_freq)) for sp in cfg.splits],
        ["split", "duplicate groups", "mentions on the minority spelling"],
        f"A label must appear at least {cfg.min_freq} times in a split to be "
        "considered, so a small split reports fewer groups than a large one "
        "even at the same defect rate. **Compare the rightmost column as a "
        "share of that split's size, not row against row.**\n\n"
        "The detail below is measured over ALL splits at once, because a "
        "split spelling `contours` and another spelling `contour` is exactly "
        "the defect and splitting the count would hide it.")
    body += report(cfg.splits, cfg.min_freq)
    groups, minority = _totals(cfg.splits, cfg.min_freq)
    verdict = core.WARN if groups else core.PASS
    head = (f"{groups:,} label groups are one concept split in two; "
            f"{minority:,} mentions sit on the minority spelling"
            if groups else "no split spellings above the frequency floor")
    return core.Result(body, verdict, head,
                       {"groups": groups, "minority_mentions": minority})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--min-freq", type=int, default=5)
    a = ap.parse_args()
    print(report(SPLITS if a.all else SMALL, a.min_freq))
