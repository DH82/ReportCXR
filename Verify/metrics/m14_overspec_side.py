#!/usr/bin/env python3
"""Metric P1a -- laterality welded into the anatomy label.

`right_internal_jugular_vein` says "right" twice: once in the label and once
in `laterality`. Two copies of one fact always drift, and where they have
drifted is exactly what 1-F counts.

E1 removed the side prefixes from the ANATOMY table, and this metric is how
that decision is checked. What remains after E1 is a different problem wearing
the same shape: a passthrough label whose STEM is not in the table either, so
stripping the prefix would leave an unknown label rather than a known one.
That is a coverage gap, not a laterality gap -- see `tools/laterality_gap.py`.

    python3 m14_overspec_side.py [--all]
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'P1a'
TITLE = 'Laterality welded into the anatomy label'
SCOPE = 'corpus'
ASKS = ("Does an anatomy label carry the side that `laterality` already "
        "holds? Two copies of one fact drift apart.")

MEANS = """## 한 줄로

**부위 이름표 안에 "왼쪽/오른쪽"이 구워져 들어간 경우를 센다.**

## 무엇이 문제인가

    잘못: 이름표 = right_internal_jugular_vein
          방향   = right
          → "오른쪽" 이 두 번 적혔다

    올바름: 이름표 = internal_jugular_vein   (구조만)
            방향   = right                    (방향은 방향 칸에)

**같은 사실이 두 군데 있으면 반드시 언젠가 어긋난다.** 한쪽만 고치는 일이
생기기 때문이다. 그리고 **어긋난 결과를 세는 것이 1-F** 다.

## 좋은 소식

**담을 칸이 이미 있다.** `laterality` 라는 방향 칸이 처음부터 있었으므로, 새
칸을 만들 필요 없이 **옮기기만** 하면 된다.

## 이 요소의 역할

**표 결정 E1 이 제대로 먹었는지 검증하는 자리다.** E1 은 `ANATOMY` 표에서 방향
접두가 붙은 줄을 전부 없앴고, 리포트의 "the ANATOMY table itself" 표가 그걸
직접 보여 준다 (목표는 **0 줄**).

## ⚠️ E1 이후에 남은 숫자는 성격이 다르다

남은 것들은 **방향을 떼어도 남는 줄기가 표에 없는** 경우다.

    right_sided  →  방향 떼면  "sided"     ← 표에 없다
    right_side   →  방향 떼면  "side"      ← 표에 없다

떼어 봤자 **모르는 이름표**가 남는다. 즉 이건 **방향 문제가 아니라 단어 부족
문제**이고, 고칠 자리는 방향 칸이 아니라 **단어장**이다.

리포트 표에서 `side-less label exists` 열이 `-` 인 줄이 그 경우다.

## 기계적으로 다 떼면 안 되는 예외가 있다

한쪽에만 있는 구조가 있다. 예를 들어 `lingula`(설상엽) 는 **왼쪽 폐에만 있다.**
이런 이름표에서 방향을 떼면 "오른쪽 설상엽" 이라는 **의학적으로 불가능한 조합**
이 허용된다. 리포트가 그 목록을 따로 낸다.
"""

import collections

import core
from core import ONT, SMALL, SPLITS, table
from metrics._overspec import SIDE_PREFIX, measured, per_split, summary_row

WARN_AT = 0.01          # share of anatomy mentions still carrying a side


def render(splits) -> str:
    r = measured(splits)
    out = ["### P1a  Laterality welded into the anatomy label\n",
           per_split(splits, [
               ("anatomy mentions", lambda x: f"{x['anat_total']:,}"),
               ("side-prefixed", lambda x: f"{sum(x['anat_sided'].values()):,}"),
               ("%", lambda x: f"{100*sum(x['anat_sided'].values())/max(1,x['anat_total']):.1f}%"),
               ("distinct labels", lambda x: f"{len(x['anat_sided']):,}"),
           ]),
           summary_row(r),
           "\nThe other branches are in `m15_overspec_tip.py` and "
           "`m16_overspec_normality.py`; the table above is repeated in all "
           "three so each file says where its branch sits.\n"]

    lat = [l for l in ONT.ANATOMY if SIDE_PREFIX.match(l)]
    stems = collections.defaultdict(list)
    for l in lat:
        stems[SIDE_PREFIX.sub("", l)].append(l)
    has_base = [s for s in stems if s in ONT.ANATOMY]
    single = [(s, ls[0]) for s, ls in sorted(stems.items())
              if len(ls) == 1 and s not in ONT.ANATOMY]

    out.append("\n**The ANATOMY table itself** -- E1 is measured here\n")
    out.append(table([
        ["ANATOMY total", f"{len(ONT.ANATOMY)}"],
        ["labels with a side prefix",
         f"{len(lat)}  ({100*len(lat)/len(ONT.ANATOMY):.0f}%)"],
        ["distinct stems", f"{len(stems)}"],
        ["stems that already have a side-less label",
         f"{len(has_base)}  <- pure duplication"],
        ["single-sided only (constraint to keep)", f"{len(single)}"],
    ], ["item", "value"]))
    if single:
        out.append("\nSingle-sided structures -- stripping the prefix "
                   "mechanically would allow a clinically impossible "
                   "combination:\n")
        out.append(table([[s, l, str(ONT.ANATOMY[l][0])] for s, l in single],
                         ["stem", "original label", "implied laterality"]))

    out.append("\n**Most frequent side-carrying labels in the data**\n")
    out.append(table([[l, f"{n:,}", SIDE_PREFIX.sub("", l),
                       "yes" if SIDE_PREFIX.sub("", l) in ONT.ANATOMY else "-"]
                      for l, n in r["anat_sided"].most_common(12)],
                     ["label", "mentions", "stem", "side-less label exists"]))
    out.append("\n> A row whose `side-less label exists` is `-` is NOT a "
               "laterality problem. The prefix could be stripped and the "
               "result would still be an unknown label, so the fix is "
               "vocabulary coverage, not the laterality field.\n")
    return "\n".join(out)


def run(cfg) -> core.Result:
    r = measured(cfg.splits)
    body = render(cfg.splits)
    sided = sum(r["anat_sided"].values())
    share = sided / max(1, r["anat_total"])
    table_rows = sum(1 for l in ONT.ANATOMY if SIDE_PREFIX.match(l))
    verdict = core.PASS if share < WARN_AT and not table_rows else core.WARN
    head = (f"{sided:,} anatomy mentions ({share:.1%}) still carry a side "
            f"prefix; ANATOMY has {table_rows} side-prefixed rows (E1 target: 0)")
    return core.Result(body, verdict, head,
                       {"sided_mentions": sided, "share": share,
                        "table_rows": table_rows})


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include train")
    print(render(SPLITS if ap.parse_args().all else SMALL))
