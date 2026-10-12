#!/usr/bin/env python3
"""Shared measurement for 1-B and 1-C -- the two failure modes of a mapping.

Both are read off the same pass over the data: surface -> label (which is
1-B, under-normalization) and label -> surface (which is 1-C, over-
normalization). Measuring them twice would double the read of an 800MB split
for no new information, so the pass lives here and the two metrics render it.

  1-B  UNDER-normalization: one surface form reaches two labels. Measurable
       with no annotator, because the dataset contradicts ITSELF -- whichever
       label is right, the other is wrong. This is the headline number.
  1-C  OVER-normalization: one label absorbs surface forms that do not mean the
       same thing. NOT self-contradictory, so it is ranked for a human rather
       than scored.

Violations are counted two ways: `forms` (distinct surface strings, one mention
or four thousand alike) and `tokens` (the propositions they occupy, which is
what reaches a downstream model).
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import collections
import math
from typing import Any, Dict, Optional

from core import norm_text, propositions, pct, section, table

# How split a surface form is, by the share of its tokens on the losing side.
# The bands exist because one number cannot separate "a stray row on a form
# used 26,000 times" from "a form with no convention at all", and those two
# need opposite responses: the first is a one-line fix, the second is a
# decision nobody has made yet.
BANDS = [
    ("①<1% 사실상 합의", 0.0),
    ("②1-10% 꼬리", 0.01),
    ("③10-40% 실질 갈림", 0.10),
    ("④≥40% 규약 없음", 0.40),
]


def band_of(share: float) -> str:
    name = BANDS[0][0]
    for n, lo in BANDS:
        if share >= lo:
            name = n
    return name


_CACHE: Dict[tuple, Dict[str, Any]] = {}


def measured(split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """measure(), memoized: 1-B and 1-C both want the same pass."""
    key = (split, limit)
    if key not in _CACHE:
        _CACHE[key] = measure(split, limit)
    return _CACHE[key]

def _entropy(counter: collections.Counter) -> float:
    """Normalized Shannon entropy of a label distribution, 0.0 when pure."""
    total = sum(counter.values())
    if total <= 0 or len(counter) < 2:
        return 0.0
    h = -sum((n / total) * math.log2(n / total) for n in counter.values())
    return h / math.log2(len(counter))


def measure(split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    # surface -> label -> count, for entity and for anatomy separately.
    fwd: Dict[str, Dict[str, collections.Counter]] = {
        "entity": collections.defaultdict(collections.Counter),
        "anatomy": collections.defaultdict(collections.Counter),
    }
    rev: Dict[str, Dict[str, collections.Counter]] = {
        "entity": collections.defaultdict(collections.Counter),
        "anatomy": collections.defaultdict(collections.Counter),
    }

    for _rec, prop in propositions(split, limit):
        ent = prop.get("entity") or {}
        t, lab = norm_text(ent.get("text")), ent.get("label")
        if t and lab:
            fwd["entity"][t][lab] += 1
            rev["entity"][lab][t] += 1
        for a in prop.get("anatomy") or []:
            # Only spans the utterance actually carries. A null text is a
            # legitimate inferred entry and says nothing about the mapping.
            t, lab = norm_text(a.get("text")), a.get("label")
            if t and lab:
                fwd["anatomy"][t][lab] += 1
                rev["anatomy"][lab][t] += 1

    out: Dict[str, Any] = {"split": split, "under": {}, "over": {}}

    for kind in ("entity", "anatomy"):
        forms = fwd[kind]
        total_forms = len(forms)
        total_tokens = sum(sum(c.values()) for c in forms.values())
        bad = {t: c for t, c in forms.items() if len(c) > 1}
        bad_tokens = sum(sum(c.values()) for c in bad.values())

        # THE NUMBER THAT COUNTS DISAGREEMENTS. `bad_tokens` counts every
        # token sitting on an ambiguous form, the agreeing majority included,
        # so `opacity` -> opacity:26,418 | pulmonary_opacity:1 contributes
        # 26,419 "violations" for one actual disagreement. Minority tokens are
        # what a fix would actually remove; see BANDS.
        minority_tokens = sum(sum(c.values()) - c.most_common(1)[0][1]
                              for c in bad.values())
        bands = {name: {"forms": 0, "tokens": 0, "minority": 0}
                 for name, _lo in BANDS}
        for c in bad.values():
            tot = sum(c.values())
            mino = tot - c.most_common(1)[0][1]
            b = bands[band_of(mino / tot)]
            b["forms"] += 1
            b["tokens"] += tot
            b["minority"] += mino

        ranked = sorted(bad.items(),
                        key=lambda kv: (-(sum(kv[1].values())
                                          - kv[1].most_common(1)[0][1]),
                                        kv[0]))
        out["under"][kind] = {
            "minority_tokens": minority_tokens,
            "bands": bands,
            "forms": total_forms,
            "tokens": total_tokens,
            "violating_forms": len(bad),
            "violating_tokens": bad_tokens,
            "mean_entropy": (sum(_entropy(c) for c in bad.values()) / len(bad))
                            if bad else 0.0,
            # Ranked by MINORITY tokens, not by total. Ranking by total puts
            # `opacity` (26,418 vs 1) at the top of a list whose purpose is to
            # show what to fix, and there is nothing to fix there.
            "top": [(t, sum(c.values()),
                     sum(c.values()) - c.most_common(1)[0][1],
                     c.most_common(4)) for t, c in ranked[:15]],
        }

        labels = rev[kind]
        spread = sorted(
            ((lab, len(c), sum(c.values()), c.most_common(4))
             for lab, c in labels.items() if len(c) > 1),
            key=lambda x: (-x[1], -x[2]))
        out["over"][kind] = {
            "labels": len(labels),
            "multi_form_labels": len(spread),
            "top": spread[:15],
        }
    return out


