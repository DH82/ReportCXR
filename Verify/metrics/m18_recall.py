#!/usr/bin/env python3
"""Metric P3 -- recall: what should be there and is not.

The other 38 checks are all PRECISION checks ("is what is here wrong?"). This
asks the reverse direction: does the utterance say something no proposition
covers?

No dictionary is declared by hand -- THE CORPUS IS ITS OWN DICTIONARY. If the
model extracted "effusion" 734 times, the data has already established that it
is an entity; the 735th occurrence that nothing covers is a miss candidate.

    coverage(term) = covered occurrences / all occurrences

Coverage is decided by CHARACTER OFFSET: string replacement leaves 'catheter'
behind in "...central catheter (PICC) line..." and false-positives.

LIMIT: a concept the model has never extracted is invisible here. That blind
spot needs an external vocabulary, and RadLex found none in 1.1M utterances.

    python3 m18_recall.py [--all] [--min-total 5] [--max-cov 0.99]
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'P3'
TITLE = 'Recall (misses)'
SCOPE = 'corpus'         # 'split' = per split, 'corpus' = whole corpus
ASKS = ("What did the extraction MISS -- words the utterance carries that no "
        "proposition accounts for?")

MEANS = """## 한 줄로

**뽑았어야 하는데 안 뽑은 것을 찾는다.**

## 다른 검사와 정반대 방향이다

거의 모든 검사는 *"여기 있는 게 틀렸나"* 를 묻는다(정밀도).
**이것만 반대를 묻는다** — *"원문이 말한 것 중 어디에도 안 담긴 게 있나"*(재현율).

    정밀도 : JSON 의 내용 → 원문에 있나?
    재현율 : 원문의 내용 → JSON 에 있나?     ← 이 요소

## 사전을 손으로 만들지 않는다

**코퍼스가 자기 자신의 사전이다.**

모델이 `effusion` 을 734번 뽑았다면, **그게 소견이라는 사실은 데이터가 이미
증명한 것**이다. 그러니 735번째로 나왔는데 아무 명제도 안 담았다면 **그 한 번이
누락 후보**다.

    피복률 = 담긴 횟수 ÷ 전체 나온 횟수

피복률이 0.99 면 거의 항상 뽑는다는 뜻이고, 0.065 면 거의 안 뽑는다는 뜻이다.

## 글자가 아니라 위치로 센다

문자열을 지우는 방식으로 세면 틀린다.

    "...central catheter (PICC) line..."
    모델이 "PICC line" 만 뽑았다
    → "catheter" 가 남아 있으니 "안 뽑았다" 고 잘못 판정

그래서 **문장 안의 몇 번째 글자부터 몇 번째 글자까지** 를 기준으로 센다.

## 한계 — 정직하게 밝힌다

> **모델이 한 번도 뽑은 적 없는 개념은 코퍼스가 모른다.** 사전이 코퍼스에서
> 나오니, 코퍼스에 없는 것은 보이지 않는다.
>
> 이 맹점은 외부 사전으로만 메울 수 있는데, RadLex 로 확인한 결과
> **111만 문장에서 0건**이었다. 즉 외부 사전이 도와줄 수 없고, 이 검사가
> 그나마 최선이다.

## 판정

`INFO` 다. 무엇이 진짜 누락이고 무엇이 그냥 흔한 단어인지는 사람이 본다.
"""


import argparse
import collections
import re

import core
from core import SMALL, SPLITS, covered_ranges, records, table, toks

MAXGRAM = 4
_TOK = re.compile(r"[a-z0-9]+")


def build_vocab(splits, min_n):
    """The surfaces the model extracted as entities ARE the dictionary."""
    v = collections.Counter()
    for sp in splits:
        for rec in records(sp):
            for p in rec.get("propositions") or []:
                t = (((p.get("entity") or {}).get("text")) or "").lower().strip()
                w = _TOK.findall(t)
                if w and len(w) <= MAXGRAM and len(t) > 3:
                    v[" ".join(w)] += 1
    return {t for t, n in v.items() if n >= min_n}


def measure(splits, vocab):
    stat = collections.defaultdict(lambda: [0, 0])
    example = {}
    n_utt = 0
    for sp in splits:
        for rec in records(sp):
            n_utt += 1
            tk = toks(rec.get("utterance"))
            if not tk:
                continue
            rng = covered_ranges(rec)
            for i in range(len(tk)):
                for k in range(1, MAXGRAM + 1):
                    if i + k > len(tk):
                        break
                    gram = " ".join(w for w, _s, _e in tk[i:i + k])
                    if gram not in vocab:
                        continue
                    s0, e0 = tk[i][1], tk[i + k - 1][2]
                    hit = any(s < e0 and s0 < e for s, e in rng)
                    stat[gram][0 if hit else 1] += 1
                    if not hit and gram not in example:
                        example[gram] = (rec.get("utterance") or "")[:86]
    return stat, example, n_utt


def report(splits, min_vocab=3, min_total=5, max_cov=0.99) -> str:
    vocab = build_vocab(splits, min_vocab)
    stat, example, n_utt = measure(splits, vocab)
    out = ["### P3  Recall -- clinical terms in the utterance that no span covers\n",
           f"Dictionary built by the corpus itself: {len(vocab):,} surfaces "
           f"(0 declared by hand). Utterances checked: {n_utt:,}\n"]

    rows = [(t, c, u, c / (c + u)) for t, (c, u) in stat.items()
            if c + u >= min_total]
    band = collections.Counter()
    for _t, _c, _u, r in rows:
        band["0.99 ~ 1.00" if r >= .99 else
             "0.95 ~ 0.99" if r >= .95 else
             "0.80 ~ 0.95" if r >= .80 else
             "0.50 ~ 0.80" if r >= .50 else "0.00 ~ 0.50"] += 1
    out.append("**Coverage distribution** -- self-consistency is the confidence measure\n")
    out.append(table([[b, f"{band[b]:,}"] for b in
                      ("0.99 ~ 1.00", "0.95 ~ 0.99", "0.80 ~ 0.95",
                       "0.50 ~ 0.80", "0.00 ~ 0.50") if band[b]],
                     ["coverage", "surfaces"]))

    cand = sorted([r for r in rows if r[3] <= max_cov and r[2] > 0],
                  key=lambda x: -x[2])
    out.append(f"\n**Miss candidates** -- coverage <= {max_cov}, "
               f"{sum(x[2] for x in cand):,} uncovered occurrences "
               f"across {len(cand)} surfaces\n")
    out.append(table([[t, f"{c:,}", f"{u:,}", f"{r:.3f}", example.get(t, "")[:60]]
                      for t, c, u, r in cand[:20]],
                     ["surface", "covered", "uncovered", "coverage", "example"]))
    out.append("\nThe closer the coverage is to 1.0, the more likely those few "
               "uncovered occurrences are real misses. A low rate means the word "
               "may not be an entity in that context, and needs a human.\n")
    return "\n".join(out)


def _join(parts):
    return "\n".join(parts)


def run(cfg) -> core.Result:
    body = (
        "\n> **이 요소만 split 별 표가 없다.** 손으로 선언한 사전이 없고 "
        "**코퍼스가 자기 자신의 사전**이기 때문이다. split 하나만 보면 그 split "
        "안에서 드문 용어가 전부 누락 후보로 올라오고, 반대로 코퍼스 전체가 "
        "한 번도 뽑지 않은 개념은 어느 split 에서도 보이지 않는다. "
        "피복률은 어휘 전체에 대해서만 뜻이 있다. 아래 숫자는 "
        f"`{', '.join(cfg.splits)}` 를 합친 것이다.\n")
    body += report(cfg.splits)
    return core.Result(body, core.INFO,
                       "candidate misses, ranked for a human")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--min-vocab", type=int, default=3)
    ap.add_argument("--min-total", type=int, default=5)
    ap.add_argument("--max-cov", type=float, default=0.99)
    a = ap.parse_args()
    print(report(SPLITS if a.all else SMALL, a.min_vocab, a.min_total, a.max_cov))
