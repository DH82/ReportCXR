#!/usr/bin/env python3
"""Metric P1b -- device position welded into a descriptor or an anatomy label.

The schema already has the right place for both halves of "tip in the mid
SVC": `anatomy.role = tip_location` names the structure, `zone` names the
segment. Rule 7 of the system prompt asks for exactly that. Where the data
instead ships a descriptor `tip_in_mid_svc`, or an anatomy label `mid_svc`,
the position is welded into a string and nothing downstream can query it.

This is the branch decision E2 was written for, and the only P1 branch still
open: prompt v2 already emits `svc` + `zone=mid`, but step 2 has no table that
would turn a legacy `mid_svc` back into the pair.

    python3 m15_overspec_tip.py [--all]
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'P1b'
TITLE = 'Device position welded into a descriptor or anatomy label'
SCOPE = 'corpus'
ASKS = ("Is a tip position carried as a string, when "
        "`anatomy.role=tip_location` + `zone` is the field pair for it?")

MEANS = """## 한 줄로

**기구의 끝이 어디 있는지가 이름표 문자열 안에 녹아든 경우를 센다.**

## 무엇이 문제인가

환자 몸에 넣은 관(카테터)은 **끝이 어디 있는지**가 중요하다. 너무 깊거나 얕으면
위험하기 때문이다.

    잘못: 수식어 = "tip_in_mid_svc"        (한 덩어리 문자열)
          또는 부위 = "mid_svc"

    올바름: 부위 = svc,  역할 = tip_location,  구역 = mid
            → "상대정맥의 중간 부분에 끝이 있다"

**올바른 쪽은 나중에 질문할 수 있다** — "끝이 SVC 에 있는 관을 다 찾아줘" 가
가능하다. 잘못된 쪽은 문자열 하나라서 검색이 안 된다.

## 상태

**P1 세 갈래 중 유일하게 아직 열려 있는 갈래다.** 프롬프트 v2 는 이미 올바른
형태로 내보내는데, **2단계에 옛 `mid_svc` 를 올바른 쌍으로 되돌릴 표가 없다.**

## ✅ 2026-09-15 — 이 요소는 자기 정답을 결함으로 세고 있었다

혈관 구간 검사가 **"구간이 있는 혈관 이름을 포함한 이름표"** 를 전부 잡았다.
그런데 **`svc` 안에는 `svc` 가 들어 있다.**

    svc        ← E2 가 만들어 내야 할 정답인데
               → "혈관 이름을 포함" 하므로 결함으로 집계됨

즉 **E2 가 아무리 잘 돼도 이 줄은 내려갈 수 없었다.** 지금은 혈관 **앞에 구간이
붙은** 경우만 센다.

    mid_svc  →  결함 ✅ (중간 + SVC 가 붙어 있다)
    svc      →  정상 ✅

> **이 날짜 이전의 이 줄 숫자는 비교 대상이 아니다.**
"""

import core
from core import SMALL, SPLITS, VOCAB, table
from metrics._overspec import measured, per_split, summary_row

WARN_AT = 0.01          # share of descriptor mentions carrying a position


def render(splits) -> str:
    r = measured(splits)
    out = ["### P1b  Device position welded into a string\n",
           per_split(splits, [
               ("descriptors", lambda x: f"{x['desc_total']:,}"),
               ("carry a position", lambda x: f"{sum(x['desc_tip'].values()):,}"),
               ("%", lambda x: f"{100*sum(x['desc_tip'].values())/max(1,x['desc_total']):.1f}%"),
               ("vessel segment welded", lambda x: f"{sum(x['anat_vessel'].values()):,}"),
               ("device props using tip_location",
                lambda x: f"{100*x['tip_role_used']/max(1,x['device_props']):.1f}%"),
           ]),
           summary_row(r),
           "\n> **The vessel-segment row read wrong until 2026-09-15.** It "
           "matched any label containing a segmented vessel name, and `svc` "
           "contains `svc` -- so E2's own output was counted as E2's failure "
           "and the row could not fall. It now counts only a segment welded "
           "in front of the vessel (`mid_svc` yes, `svc` no). Earlier numbers "
           "for this row are not comparable.\n"]

    out.append("\n**The convention exists; the question is whether the data "
               "follows it**\n")
    out.append(f"`ANATOMY_ROLES = {VOCAB.ANATOMY_ROLES}`, and rule 7 of the "
               f"system prompt asks for tip_location.\n")
    used = r["tip_role_used"]
    dev = r["device_props"]
    out.append(table([
        ["device propositions", f"{dev:,}"],
        ["of those, using tip_location",
         f"{used:,}  ({100*used/max(1,dev):.1f}%)"],
    ], ["item", "value"]))

    out.append("\n**Descriptors carrying a position**\n")
    out.append(table([[l, f"{n:,}"] for l, n in r["desc_tip"].most_common(10)]
                     or [["(none)", "0"]], ["descriptor label", "mentions"]))
    out.append("\n**Anatomy labels with a segment welded to the vessel**\n")
    out.append(table([[l, f"{n:,}"] for l, n in r["anat_vessel"].most_common(10)]
                     or [["(none)", "0"]], ["anatomy label", "mentions"]))
    return "\n".join(out)


def run(cfg) -> core.Result:
    r = measured(cfg.splits)
    body = render(cfg.splits)
    tip = sum(r["desc_tip"].values())
    ves = sum(r["anat_vessel"].values())
    share = tip / max(1, r["desc_total"])
    verdict = core.PASS if (share < WARN_AT and not ves) else core.WARN
    head = (f"{tip:,} descriptors ({share:.1%}) carry a position and {ves:,} "
            f"anatomy labels weld a segment to the vessel; "
            f"{100*r['tip_role_used']/max(1,r['device_props']):.1f}% of device "
            f"propositions use tip_location")
    return core.Result(body, verdict, head,
                       {"desc_tip": tip, "anat_vessel": ves,
                        "tip_role_share": r["tip_role_used"] / max(1, r["device_props"])})


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include train")
    print(render(SPLITS if ap.parse_args().all else SMALL))
