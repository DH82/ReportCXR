#!/usr/bin/env python3
"""Metric P1c -- normality welded into the entity label.

`normal_heart_size` and `heart_size` are the same entity with a descriptor
attached, and shipping them as two labels splits every count of the heart in
half. `DESCRIPTOR_TYPES` has had a `normality` axis all along, so the fix
needed no schema change -- only E3, which lifts the prefix into a descriptor
before the label is aliased.

This is the branch where that worked: 8.0% before E3, effectively nil after.
It stays in the report as the check that keeps it there.

    python3 m16_overspec_normality.py [--all]
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'P1c'
TITLE = 'Normality welded into the entity label'
SCOPE = 'corpus'
ASKS = ("Does an entity label carry a normality prefix that "
        "`descriptor.type=normality` is the field for?")

MEANS = """## 한 줄로

**"정상이다"라는 판단이 소견 이름표 안에 구워져 들어간 경우를 센다.**

## 무엇이 문제인가

    normal_heart_size   와   heart_size

**이 둘은 같은 것**이다. 앞의 것은 "정상"이라는 수식어가 붙었을 뿐이다. 그런데
이름표를 둘로 나누면 **심장 크기에 대한 모든 집계가 반으로 쪼개진다.**

"심장 크기를 언급한 판독문이 몇 건?" 이라고 물으면 **절반만 나온다.**

## 어떻게 고쳤나

`descriptor` 에는 `normality`(정상 여부) 칸이 **처음부터 있었다.** 그래서 새
칸을 만들 필요 없이, **표 결정 E3** 이 접두어를 그 칸으로 들어올리기만 했다.

    normal_heart_size
      → 이름표 = heart_size
      → 수식어 = normality : normal

이름표가 별칭 처리되기 **전에** 접두를 떼는 것이 요령이다. 순서가 반대면 표가
`normal_heart_size` 를 못 찾아 그냥 통과시킨다.

## 상태 — P1 세 갈래 중 성공한 갈래다

**E3 이전 8.0% → 사실상 0%.**

이 요소가 리포트에 계속 남아 있는 이유는 **그 상태가 유지되는지 지키기 위해서**
다. 한 번 고쳤다고 끝이 아니라, 새 데이터가 들어올 때마다 다시 확인한다.

## 리포트 읽는 법

표에서 `its mentions` 열이 **비어 있지 않은** 줄은, **같은 것의 집계가 지금
두 이름표로 쪼개져 있다**는 뜻이다.
"""

import core
from core import SMALL, SPLITS, VOCAB, table
from metrics._overspec import NORMY, measured, per_split, summary_row

WARN_AT = 0.005         # share of entity mentions carrying a normality prefix


def render(splits) -> str:
    r = measured(splits)
    out = ["### P1c  Normality welded into the entity label\n",
           per_split(splits, [
               ("entity mentions", lambda x: f"{x['ent_total']:,}"),
               ("normality-prefixed", lambda x: f"{sum(x['ent_normal'].values()):,}"),
               ("%", lambda x: f"{100*sum(x['ent_normal'].values())/max(1,x['ent_total']):.2f}%"),
           ]),
           summary_row(r),
           "\n**A prefixed label duplicates the plain one**\n"]
    rows = []
    for l, n in r["ent_normal"].most_common(12):
        base = NORMY.sub("", l)
        rows.append([l, f"{n:,}", base,
                     f"{r['ent_labels'][base]:,}" if base in r["ent_labels"]
                     else "-"])
    out.append(table(rows or [["(none)", "0", "-", "-"]],
                     ["label", "mentions", "plain form", "its mentions"]))
    out.append(f"\n`DESCRIPTOR_TYPES` already has the `normality` axis: "
               f"{'normality' in VOCAB.DESCRIPTOR_TYPES}. A row above with a "
               f"non-empty `its mentions` is a count that has been split in "
               f"two.\n")
    return "\n".join(out)


def run(cfg) -> core.Result:
    r = measured(cfg.splits)
    body = render(cfg.splits)
    n = sum(r["ent_normal"].values())
    share = n / max(1, r["ent_total"])
    verdict = core.PASS if share < WARN_AT else core.WARN
    head = (f"{n:,} entity mentions ({share:.2%}) carry a normality prefix "
            f"(E3 landed: was 8.0%)")
    return core.Result(body, verdict, head, {"mentions": n, "share": share})


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include train")
    print(render(SPLITS if ap.parse_args().all else SMALL))
