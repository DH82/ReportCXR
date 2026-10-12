#!/usr/bin/env python3
"""Metric 1-B -- under-normalization: one surface form, two labels.

The strongest signal in this audit that needs no annotator. If "left" is
`left_pleural_space` in one proposition and `chest_wall` in the next, the
dataset contradicts ITSELF: whichever reading is right, the other is wrong,
and no clinical judgement is required to see it.

It is also the number that does NOT move when the ontology is cleaned up,
which is why it gets its own file. E1 stripped laterality prefixes off labels
and this barely shifted -- 1-B measures the ambiguity of the mapping from
surface to label, not the shape of the labels, and that is a separate
unsolved problem (diagnosed in P1).

Measurement lives in `_mapping.py`, shared with 1-C.

    python3 m05_under_norm.py [split]
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = '1-B'
TITLE = 'Under-normalization (one surface form, two labels)'
SCOPE = 'split'
ASKS = ("Does the same surface string reach two different labels? "
        "Wherever it does, the dataset contradicts itself.")

MEANS = """## 한 줄로

**같은 말에 서로 다른 이름표가 붙은 곳을 찾는다.**

## 왜 이게 가장 강한 신호인가

정답지가 없어도 **기계 혼자 판정할 수 있는 유일한 종류의 결함**이기 때문이다.

같은 문장 속 `"left"` 가 한 곳에서는 `pleura`(흉막), 다른 곳에서는
`chest_wall`(가슴벽) 이라면 — **어느 쪽이 맞든 다른 쪽은 틀렸다.** 의학 지식이
전혀 없어도 이 말은 할 수 있다. **데이터가 스스로 모순되기 때문이다.**

## 두 가지로 센다 — 이 구분이 핵심이다

| 열 | 뜻 |
|---|---|
| **`MINORITY`** | **지는 쪽에 붙은 개수.** 고치면 실제로 줄어드는 수 |
| `on a split form` | 갈린 말에 붙은 **모든** 개수 (이긴 쪽 포함) |

> ⚠️ **2026-09-15 — 세는 방식이 바뀌었다. 이전 리포트와 비교하면 안 된다.**
>
> 예전에는 뒤쪽 숫자로 판정했다. 그러면 이런 일이 생긴다.
>
>     "opacity"  →  opacity : 26,418개
>                   pulmonary_opacity : 1개
>
> **어긋난 것은 1개인데 위반이 26,419개로 세어졌다.** 이런 "거의 다 합의된"
> 말들이 위반 숫자의 4분의 1에서 3분의 1을 차지했다.
>
> 더 나쁜 것은 **고쳐도 티가 안 난다**는 점이었다. 저 1개를 고치면 위반이 1
> 줄어야 하는데 26,419가 통째로 사라져서, **실제의 수천 배로 부풀려진 개선**
> 으로 보였다. 전량 기준 44.1% 였던 숫자가 소수파로 세니 6.6% 였다.

## 밴드 표를 꼭 볼 것

한 숫자로는 **"2만 번 쓰이는 말에 어긋난 한 줄"** 과 **"아예 규칙이 없는 말"** 을
구분할 수 없다. 그런데 둘은 대응이 정반대다.

| 밴드 (지는 쪽 비율) | 뜻 | 해야 할 일 |
|---|---|---|
| ①  1% 미만 | 사실상 합의됨 | 꼬리만 정리 |
| ② 1~10% | 꼬리 | 꼬리만 정리 |
| ③ 10~40% | 진짜로 갈림 | 수식어 분리 · 단복수 병합 |
| ④ 40% 이상 | **동전 던지기** | **사람이 규칙을 정해야 한다** |

④ 는 반반이라는 뜻이고, 그건 그 말에 대해 **규칙이 아예 존재하지 않는다**는
증거다.

## 여기 걸린 게 전부 어휘 문제는 아니다

train 에서 anatomy 쪽 갈림의 **42%가 `"left"` · `"bilateral"` 같은 순수 방향어**
에서 나왔다. 그런데 **방향어는 부위 이름이 아니다.**

    "Small left pleural effusion"  (왼쪽에 적은 흉수)
       부위 이름표 = pleura   ← 맞다 (흉수는 흉막에 생긴다)
       인용한 문구 = "left"   ← 틀렸다. 이건 방향이지 부위가 아니다

이름표는 소견의 뜻에서 제대로 나온 것이고, 잘못된 것은 **방향어를 부위 문구인
것처럼 적은 쪽**이었다. **표 결정 E5 가 이걸 고쳤고**(문구를 비우고 방향은
방향 칸에 그대로 둔다), 전량 약 7만 건이 해소되었다. 재추출 없이 2단계에서
처리되었다.

남은 것은 **이름표 자체가 방향어**인 경우다. 부위가 애초에 뽑히지 않았으므로
어떤 표로도 만들어 낼 수 없고, 프롬프트를 고쳐야 한다.
"""

from typing import Any, Dict

import core
from core import pct, section, table

from metrics._mapping import BANDS, measured

# Share of MINORITY tokens -- the ones a fix would actually remove. See the
# note in run() for why the other number cannot carry a verdict.
FAIL_AT = 0.10
WARN_AT = 0.02


def render(res: Dict[str, Any], cfg=None) -> str:
    show_ex = cfg is None or cfg.shows_examples(res["split"])
    body = [section(f"1-B  Under-normalization  ({res['split']})")]
    rows = []
    for kind, d in res["under"].items():
        rows.append([kind, d["forms"], d["violating_forms"],
                     pct(d["violating_forms"], d["forms"]),
                     d["tokens"], d["minority_tokens"],
                     pct(d["minority_tokens"], d["tokens"]),
                     d["violating_tokens"],
                     pct(d["violating_tokens"], d["tokens"]),
                     f"{d['mean_entropy']:.3f}"])
    body.append(table(rows, ["field", "forms", "split forms", "% forms",
                             "tokens", "MINORITY", "% minority",
                             "on a split form", "%", "mean entropy"]))
    body.append(
        "\n**`MINORITY` is the defect count; `on a split form` is not.** The "
        "second counts every token on an ambiguous surface form, the agreeing "
        "majority included, so one stray row on a common word contributes "
        "thousands. `mean entropy` is 0.0 when a split is 99%/1% (a rare slip) "
        "and 1.0 when it is 50%/50% (a coin flip, i.e. no convention).\n")

    for kind, d in res["under"].items():
        body.append(f"\n**`{kind}` — how split are the split forms**\n")
        body.append(table(
            [[name, d["bands"][name]["forms"], d["bands"][name]["tokens"],
              d["bands"][name]["minority"],
              pct(d["bands"][name]["minority"], d["minority_tokens"])]
             for name, _lo in BANDS],
            ["band (소수파 비율)", "forms", "tokens on them", "MINORITY",
             "% of minority"]))

    for kind, d in res["under"].items():
        if not d["top"] or not show_ex:
            continue
        body.append(f"\n**Worst `{kind}` splits, ranked by minority tokens**\n")
        body.append(table(
            [[t, mino, n, ", ".join(f"{l}:{c}" for l, c in labs)]
             for t, n, mino, labs in d["top"]],
            ["surface form", "MINORITY", "total", "labels"]))
    return "\n".join(body) + "\n"


def run(cfg) -> core.Result:
    per = [measured(sp, cfg.limit) for sp in cfg.splits]
    body = core.summary(
        [[r["split"]] + [v for d in (r["under"]["entity"], r["under"]["anatomy"])
                         for v in (d["tokens"], d["minority_tokens"],
                                   pct(d["minority_tokens"], d["tokens"]),
                                   pct(d["violating_tokens"], d["tokens"]))]
         for r in per],
        ["split", "entity tokens", "MINORITY", "%", "(on a split form %)",
         "anatomy tokens", "MINORITY", "%", "(on a split form %)"],
        "**The verdict rests on `MINORITY`.** The parenthesised column is the "
        "number this metric used to report; it is kept because it says how "
        "much of the vocabulary is touched by ambiguity, but it cannot be a "
        "defect count -- see below.")
    body += core.example_note(cfg.example_split) if cfg.example_split else ""
    body += "\n".join(render(r, cfg) for r in per)

    body += ("\n> **2026-09-15 — 이 요소의 판정 기준이 바뀌었다. 이전 숫자와 "
             "비교하면 안 된다.**\n>\n"
             "> 예전에는 갈린 표면형에 얹힌 토큰을 **다수파까지 전부** 세었다. "
             "그래서 `opacity -> opacity:26,418 | pulmonary_opacity:1` 이 "
             "**어긋남 1건에 위반 26,419건**을 기여했고, train 에서 그런 "
             "'소수파 1% 미만' 형태가 위반 토큰의 26~36%를 차지했다. "
             "전량 기준 44.1% 는 그렇게 만들어진 숫자이고, 소수파로 세면 "
             "6.6% 다.\n>\n"
             "> 더 나쁜 것은 개선이 보이지 않는다는 점이었다. `opacity` 의 "
             "어긋난 1건을 고치면 위반이 1 줄어야 하는데 26,419 가 통째로 "
             "사라져, **실제의 수천 배로 과장된 개선**으로 찍혔다. "
             "P1b 가 정본인 `svc` 자신을 세던 것과 같은 부류의 결함이다.\n")

    tok = sum(d["minority_tokens"] for r in per for d in r["under"].values())
    allt = sum(d["violating_tokens"] for r in per for d in r["under"].values())
    tot = sum(d["tokens"] for r in per for d in r["under"].values())
    share = tok / tot if tot else 0.0
    verdict = (core.FAIL if share >= FAIL_AT else
               core.WARN if share >= WARN_AT else core.PASS)
    head = (f"{share:.1%} of entity+anatomy tokens ({tok:,}/{tot:,}) sit on "
            f"the losing side of a surface form that gets two labels "
            f"({allt:,} tokens sit on such a form at all)")
    return core.Result(body, verdict, head,
                       {"minority_share": share, "minority_tokens": tok,
                        "tokens_on_split_forms": allt, "tokens": tot})


if __name__ == "__main__":
    print(render(measured(_sys.argv[1] if len(_sys.argv) > 1 else "test")))
