#!/usr/bin/env python3
"""Metric 1-D -- merge candidates, judged by the RadLex hierarchy.

1-B catches splits the data reveals itself (one surface, two labels). 1-D looks
for two labels that share no surface form but mean the same thing, which no
self-consistency check can see because nothing contradicts.

Stem sharing is used for CANDIDATE GENERATION ONLY; the verdict comes from the
hierarchy. (Ranking shared stems by frequency put pleural_effusion <->
pneumothorax at the top, because modifiers like "resid"/"appea" read as signal.)

    same       both labels resolve to the same RID          -> merge
    overspec   equal only after stripping modifier/side     -> P1, not a merge
    narrower   one is an ancestor of the other              -> granularity call
    close      common ancestor within CLOSE steps of both   -> worth a human
    distant    further than that                            -> suppressed
    unknown    either side is absent from RadLex            -> needs a local definition

Unknowns are reported as LABELS, not pairs: listed as pairs, one frequent label
fills the whole list. A = concepts to define, B = pairs whose relation must be
written by hand in Prompt2/relations.py.
"""

from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = '1-D'
TITLE = 'Merge candidates (RadLex hierarchy)'
SCOPE = 'corpus'         # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Which two labels share no surface form at all and are still the "
        "same concept? RadLex decides; string overlap only nominates.")

MEANS = """## 한 줄로

**글자는 하나도 안 겹치는데 사실은 같은 개념인 두 이름표를 찾는다.**

## 왜 어려운 문제인가

`contour` 와 `contours` 는 글자가 비슷하니 쉽게 찾는다(그건 P2 가 한다).
그런데 이런 건 어떤가?

    costophrenic_angles   와   costophrenic_sulci
    chest_tube            와   pleural_tube

**글자가 전혀 안 겹치는데 같은 것**이다. 그리고 이건 **아무 모순도 일으키지
않기 때문에**, 스스로 모순을 찾는 다른 어떤 검사로도 절대 보이지 않는다.

## 어떻게 찾나

**RadLex** 라는 외부 의학 용어 사전의 **계층 구조**를 쓴다. 두 이름표가 그
사전에서 같은 번호(RID)로 가면 같은 개념이다.

> **예전 방식은 고장나 있었다.** 단어 앞 5글자가 같은 것끼리 후보로 뽑았더니
> 상위 40쌍이 **전부 오답**이었다. 1위가 `pleural_effusion` ↔ `pneumothorax`
> (흉수와 기흉 — 전혀 다른 병)였다. `resid`(residual), `cardi`(cardiac) 같은
> **수식어가 신호로 잡힌 것**이다.
>
> 지금은 글자 비슷함을 **후보 뽑기에만** 쓰고, 판정은 RadLex 계층이 한다.

## 결과가 여섯 통으로 나뉜다

| 통 | 뜻 | 조치 |
|---|---|---|
| **확실한 병합** | 두 이름표가 **그대로** 같은 번호 | 합친다. 의학 판단 불필요 |
| **과잉 특정** | 수식어를 떼야 같아진다 | **합치면 안 된다.** 다른 묶음 소관 |
| **입도 결정** | 한쪽이 다른 쪽의 하위 개념 | 합칠지는 결정 사항 |
| **가까운 사이** | 계층에서 2단계 이내 | 사람이 볼 가치 있음 |
| **차단됨** | 계층상 먼 사이 | 목록에서 뺀다 |
| **정의 필요** | 한쪽이라도 RadLex 에 없다 | 직접 정의해야 한다 |

> **위 두 통을 가르는 것이 이 요소의 핵심이다.**
> `aorta` 와 `tortuous_aorta` 는 같은 번호로 가지만 **합치면 안 된다.**
> `tortuous`(구불구불한) 를 떼야 같아지는 거라서, 고칠 자리는 병합표가 아니라
> **수식어 칸**이다. 이 구분이 없으면 절반이 잘못된 조치로 이어진다.

## RadLex 의 한계 — 이것도 산출물이다

RadLex 4.3 은 흉부 판독문 어휘가 얇다. 실제로 확인해 보니 **`cardiomegaly`
(심장비대) · `pleural thickening` · `hyperinflation` 이 전부 없다.** 가장 기본
용어들이다.

그래서 상당수 쌍을 계층으로 판정할 수 없고, **그 목록이 곧 직접 정의해야 할
대상**이 된다.

## 판정

`INFO` 다. 합칠지 말지는 결국 사람이 정한다.
"""

import collections
import itertools
from typing import Dict, List, Optional, Set, Tuple

import core
from core import (ONT, REPO, RADLEX_TSV, SMALL, SPLITS, norm_text,
                  propositions, table, unsnake)

from Prompt2 import relations as REL
from Pipeline.radlex_match import candidates as _rl_candidates

FIELDS = ("entity", "anatomy")
CLOSE = 2              # common ancestor within this depth on both sides = "close"
_MIN_STEM = 5
_MAX_BUCKET = 400

# Differ on one of these tokens and the concepts differ, however alike the strings.
_DISTINGUISHING = {
    "left", "right", "bilateral", "upper", "lower", "middle", "mid",
    "apical", "basilar", "anterior", "posterior", "no", "non", "without",
}
# What may be stripped differs per field (same rule as tools/lexicon.py).
_STRIP = {"anatomy": "side", "entity": "all"}


# =============================================================================
#  RadLex hierarchy
# =============================================================================

def load_hierarchy() -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    """RID -> ancestors (nearest first), RID -> label."""
    par: Dict[str, List[str]] = {}
    lab: Dict[str, str] = {}
    with open(RADLEX_TSV, encoding="utf-8") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split("\t")
            lab[p[0]] = p[1]
            par[p[0]] = [x for x in p[3].split("|") if x]
    anc: Dict[str, List[str]] = {}

    def walk(r: str) -> List[str]:
        if r in anc:
            return anc[r]
        out, seen, cur = [], {r}, r
        while True:
            ps = par.get(cur) or []
            if not ps or ps[0] in seen:
                break
            cur = ps[0]
            seen.add(cur)
            out.append(cur)
        anc[r] = out
        return out

    for r in par:
        walk(r)
    return anc, lab


def classify(a, b, anc: Dict[str, List[str]]) -> Tuple[str, str]:
    """(relation, note). a and b are (RID, match stage) or None.

    The same RID means different things depending on HOW it was reached:
    opacities/opacity is a merge, while aorta/tortuous_aorta matches only after
    stripping a modifier, which is over-specification (P1) and belongs in the
    descriptor field, not in a merge table.
    """
    if not a or not b:
        return "unknown", "not in RadLex"
    a_rid, a_how = a
    b_rid, b_how = b
    if a_rid == b_rid:
        if a_how in _STRIPPED or b_how in _STRIPPED:
            worn = a_how if a_how in _STRIPPED else b_how
            return "overspec", f"equal after stripping {worn} ({a_rid})"
        return "same", f"same concept {a_rid}"
    A, B = anc.get(a_rid, []), anc.get(b_rid, [])
    if b_rid in A:
        return "narrower", f"A is {A.index(b_rid)+1} step(s) below B"
    if a_rid in B:
        return "narrower", f"B is {B.index(a_rid)+1} step(s) below A"
    common = [x for x in A if x in B]
    if not common:
        return "distant", "no common ancestor"
    c = common[0]
    da, db = A.index(c) + 1, B.index(c) + 1
    if da <= CLOSE and db <= CLOSE:
        return "close", f"common ancestor at depth {da}/{db}"
    return "distant", f"common ancestor at depth {da}/{db}"


# =============================================================================
#  Candidate generation -- stem/token inverted index. Not a verdict: it only
#  produces pairs worth judging.
# =============================================================================

def _tokens(label: str) -> Set[str]:
    return set(label.split("_"))


def _blocked(a: str, b: str) -> bool:
    return (_tokens(a) & _DISTINGUISHING) != (_tokens(b) & _DISTINGUISHING)


def _candidate_pairs(labels: List[str], surfaces: Dict[str, Set[str]]):
    """Build candidates from an inverted index; same set as all-pairs comparison."""
    index: Dict[str, Set[str]] = collections.defaultdict(set)
    for lab in labels:
        keys = _tokens(lab) | surfaces.get(lab, set())
        for t in _tokens(lab) | {lab}:
            if len(t) >= 4:
                keys.add(t[:4])
            if len(t) >= _MIN_STEM:
                keys.add(t[-_MIN_STEM:])
        for key in keys:
            index[key].add(lab)
    seen: Set[Tuple[str, str]] = set()
    for _key, bucket in index.items():
        if len(bucket) > _MAX_BUCKET:
            continue
        for a, b in itertools.combinations(sorted(bucket), 2):
            if (a, b) not in seen:
                seen.add((a, b))
                yield a, b


# =============================================================================
#  Main
# =============================================================================

def collect(splits, field):
    freq = collections.Counter()
    surf: Dict[str, Set[str]] = collections.defaultdict(set)
    for sp in splits:
        for _rec, p in propositions(sp):
            if field == "entity":
                items = [p.get("entity") or {}]
            else:
                items = p.get("anatomy") or []
            for it in items:
                lab = it.get("label")
                if not lab:
                    continue
                freq[lab] += 1
                t = norm_text(it.get("text"))
                for w in t.split():
                    if len(w) >= _MIN_STEM:
                        surf[lab].add(w[:_MIN_STEM])
    return freq, surf


# Matching at this stage means the label added something to the RadLex concept.
_STRIPPED = {"laterality", "modifier"}


def resolve_rids(labels, field, by_label, by_syn, mods):
    """label -> (RID, match stage). The stage matters; see classify()."""
    fmods = mods if _STRIP.get(field) == "all" else set()
    out = {}
    for lab in labels:
        for cand, how in _rl_candidates(lab, fmods):
            rid = by_label.get(cand) or by_syn.get(cand)
            if rid:
                out[lab] = (rid, how)
                break
    return out


def measure(splits, field, min_freq=3):
    from Pipeline.radlex_match import load_radlex as _lr
    by_label, by_syn, _ = _lr(RADLEX_TSV)
    mods = set()
    for w in ONT.DESCRIPTOR_LEXICON:
        mods.update(unsnake(w).split())
    for _w, z in ONT.ZONE_WORDS:
        mods.add(z)

    anc, rlab = load_hierarchy()
    freq, surf = collect(splits, field)
    labels = [l for l, n in freq.items() if n >= min_freq]
    rids = resolve_rids(labels, field, by_label, by_syn, mods)

    buckets = collections.defaultdict(list)
    n_pairs = 0
    for a, b in _candidate_pairs(labels, surf):
        if _blocked(a, b):
            continue
        n_pairs += 1
        loc = REL.relation(a, b)
        if loc:
            rel, why = loc
            buckets["local:" + rel].append((a, b, freq[a], freq[b], why, ""))
            continue
        rel, why = classify(rids.get(a), rids.get(b), anc)
        ra = (rids.get(a) or ("-",))[0]
        rb = (rids.get(b) or ("-",))[0]
        buckets[rel].append((a, b, freq[a], freq[b], why, f"{ra}/{rb}"))
    return buckets, n_pairs, len(labels), freq


def render(buckets, n_pairs, n_labels, freq, field) -> str:
    out = [f"\n### `{field}` -- {n_pairs:,} candidate pairs / {n_labels:,} labels\n"]

    def block(title, key, note, limit=15, sort_rare=True):
        rows = buckets.get(key) or []
        if not rows:
            return
        rows = sorted(rows, key=(lambda r: -min(r[2], r[3])) if sort_rare
                      else (lambda r: -(r[2] + r[3])))
        out.append(f"\n**{title}** -- {len(rows):,} pairs. {note}\n")
        out.append(table([[a, f"{na:,}", b, f"{nb:,}", why]
                          for a, b, na, nb, why, _rid in rows[:limit]],
                         ["label A", "n(A)", "label B", "n(B)", "basis"]))

    block("Certain merge -- same RadLex concept", "same",
          "Both labels resolve **as they are** to the same RID. No clinical "
          "judgement needed.")
    block("Over-specified -- NOT a merge", "overspec",
          "Equal only after stripping a modifier or a side. The fix belongs in "
          "the descriptor/laterality field, not in a merge table (P1, E1-E3).")
    block("Local definition: same", "local:same",
          "`Prompt2/relations.py` declares these the same.")
    block("Granularity call -- narrower/broader", "narrower",
          "One is below the other. Whether to collapse them is a decision.")
    block("Local definition: narrower", "local:narrower",
          "`Prompt2/relations.py` declares the relation.")
    block("Close -- worth a human look", "close",
          f"Common ancestor within {CLOSE} steps on both sides.")

    blocked = len(buckets.get("distant") or []) + \
        len(buckets.get("local:distinct") or [])
    out.append(f"\n**Suppressed** -- {blocked:,} pairs the hierarchy judged distant, "
               f"or the local table declared distinct. A stem-ranked list would put "
               f"`pleural_effusion` / `pneumothorax` at the top; here it is suppressed.\n")

    # --- needs a local definition, listed per label ---------------------------
    unk = buckets.get("unknown") or []
    no_rid = collections.Counter()      # unmatched label -> candidate pairs it appears in
    both = []                           # pairs where neither side matched
    for a, b, na, nb, _why, rid in unk:
        ra, rb = (rid.split("/") + ["-"])[:2]
        if ra == "-":
            no_rid[a] += 1
        if rb == "-":
            no_rid[b] += 1
        if ra == "-" and rb == "-":
            both.append((a, b, na, nb))

    defined = [l for l in no_rid if REL.concept(l)]
    todo = [l for l in no_rid if not REL.concept(l)]
    out.append(f"\n**A. concepts to define** -- {len(no_rid):,} labels absent from "
               f"RadLex (the cause of {len(unk):,} unjudged pairs). "
               f"**{len(defined):,} are already in `Prompt2/relations.py`**, "
               f"{len(todo):,} remain. Define them in frequency order.\n")
    rows = sorted(((l, freq.get(l, 0), c) for l, c in no_rid.items()),
                  key=lambda r: -r[1])[:20]
    out.append(table([[l, f"{n:,}", f"{c:,}",
                       "defined" if REL.concept(l) else "-"]
                      for l, n, c in rows],
                     ["label", "mentions", "unjudged pairs", "local definition"]))

    out.append(f"\n**B. relations to define** -- {len(both):,} candidate pairs where "
               f"neither side is in RadLex. Defining the concepts is not enough: "
               f"with no hierarchy, the relation has to be written by hand.\n")
    if both:
        both = sorted(both, key=lambda r: -min(r[2], r[3]))[:15]
        out.append(table([[a, f"{na:,}", b, f"{nb:,}"] for a, b, na, nb in both],
                         ["label A", "n(A)", "label B", "n(B)"]))
    return "\n".join(out)


def run(cfg) -> core.Result:
    parts = [
        "\n> **이 요소만 split 별 표가 없다.** 판정 단위가 split 이 아니라 "
        "**어휘 전체**이기 때문이다. 두 라벨이 같은 개념인지는 그 둘이 어느 "
        "split 에 나왔는지와 무관하고, split 마다 따로 세면 한쪽에만 나온 쌍이 "
        "사라진다. 아래 숫자는 "
        f"`{', '.join(cfg.splits)}` 를 합친 어휘에 대한 것이다.\n",
    ]
    sure, unmatched = 0, 0
    for field in FIELDS:
        b, n, nl, fr = measure(cfg.splits, field)
        parts.append(render(b, n, nl, fr, field))
        sure += len(b.get("same") or []) + len(b.get("local:same") or [])
        unmatched += len(b.get("unknown") or [])
    cov = REL.coverage()
    parts.append(f"\n---\n\n`Prompt2/relations.py` currently holds "
                 f"{len(REL.LOCAL)} pairs: "
                 + ", ".join(f"{k} {v}" for k, v in sorted(cov.items())) + "\n")
    parts.append(
        "\n> **'certain merge' and 'over-specified' must not be one list.** "
        "`aorta` and `tortuous_aorta` reach the same RID, and merging them "
        "would be wrong -- `tortuous` has to move to a descriptor, which is "
        "P1's job, not this table's. Collapsing the two buckets sends about "
        "half the rows to the wrong fix.\n")
    body = "\n".join(parts)

    verdict = core.INFO
    head = (f"{sure:,} certain merges (same RID, no clinical judgement "
            f"needed); {unmatched:,} pairs unjudgeable -- a label is not in "
            f"RadLex")
    return core.Result(body, verdict, head,
                       {"certain_merges": sure, "unmatched_labels": unmatched})


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--field", choices=FIELDS)
    a = ap.parse_args()

    class _C:
        splits = SPLITS if a.all else SMALL
    if a.field:
        b, n, nl, fr = measure(_C.splits, a.field)
        print(render(b, n, nl, fr, a.field))
    else:
        print(run(_C))
