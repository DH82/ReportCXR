#!/usr/bin/env python3
"""Metric 1-F -- invariants that must hold AFTER normalization, checked against
this repository's ontology.

validate.py checks most of these, but against whichever ontology its checkout
has; running that over jsonl/ reports the gap between two tables as data
quality. The concrete case: SIDED_MIDLINE. A naive check calls "right upper
mediastinal opacity" a contradiction, when reports name the borders of a
midline compartment every day (measured: 49 contradictions without the set, 33
with it -- 16 were the checker's fault).

  laterality contradiction   ANATOMY implies one side, the record states the
                             other, and the label is not in SIDED_MIDLINE
  zone contradiction         same for zone, via zones_compatible()
  rule 4 leakage             an anatomy entry sourced from the heading that
                             carries a laterality or zone
  section canonical          the heading is one of the eight

Purely structural checks (enums, id graph, span containment) do not drift with
the tables and are left to validate.py.
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = '1-F'
TITLE = 'Post-normalization invariants'
SCOPE = 'split'          # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Does a label contradict the field beside it -- `mediastinum` (midline) "
        "carrying `laterality: right`?")

MEANS = """## 한 줄로

**이름표가 뜻하는 것과 옆 칸에 적힌 것이 서로 안 맞는 곳을 찾는다.**

## 예시

`mediastinum`(종격동) 은 가슴 **한가운데** 있는 부위다. 그러니 이 이름표에는
방향 칸이 `midline`(중앙) 이어야 한다. 그런데 `right`(오른쪽) 라고 적혀 있다면
앞뒤가 안 맞는다.

    이름표 = mediastinum   (한가운데 부위)
    방향   = right          ← 모순

## 왜 이런 일이 생기나

**같은 사실이 두 군데 적혀 있기 때문이다.** 부위 이름 자체가 이미 "가운데"를
뜻하는데 방향 칸에도 또 적는다. 한쪽만 고치는 일이 생기면 곧바로 어긋난다.

**여기는 어긋난 "결과"를 세는 자리다.** 왜 두 군데 적히게 됐는지는 마지막
묶음(과잉 특정)이 진단한다.

## ⚠️ 순진하게 만들면 크게 틀리는 검사다

`ANATOMY` 표는 종격동을 "가운데"로 정의한다. 그래서 순진한 검사는
**`"right upper mediastinal opacity"`(우측 상부 종격동 음영) 를 모순으로 잡는다.**

**그런데 이건 모순이 아니다.** 판독문은 가운데 부위의 **왼쪽 경계 / 오른쪽
경계** 를 매일 기술한다. "가운데 부위의 오른쪽 부분" 은 지극히 정상적인 말이다.

그래서 이 저장소의 표는 `SIDED_MIDLINE`(방향을 가질 수 있는 중앙 부위) 목록을
따로 들고 있고, 리포트는 **면제된 건수를 따로 보여 준다.**

> 실측: 예전 버전에서 잡힌 49건 중 **16건이 데이터 결함이 아니라 검사기의
> 결함**이었다.

## 읽는 법

모순이 **한 이름표에 몰려 있는지 흩어져 있는지**가 조치를 가른다. 몰려 있다면
**그 이름표 하나만 결정하면 절반이 해결된다.**
"""

# Share of anatomy entries contradicting their own label. A handful is the
# long tail of a large vocabulary; a percent is a missing table decision.
WARN_AT = 0.005
FAIL_AT = 0.05


import collections

# Share of anatomy entries contradicting their own label. A handful is the
# long tail of a 100k-label vocabulary; a percent is a table decision missing.
WARN_AT = 0.005
FAIL_AT = 0.05
from typing import Any, Dict, List, Optional

import core
from core import ONT, propositions, records, pct, section, table

SIDED_MIDLINE = set(getattr(ONT, "SIDED_MIDLINE", ()) or ())
_SOFT_SIDE = (None, "unspecified", "not_applicable")


def canonical_section(heading: Optional[str]) -> Optional[str]:
    """A heading as written -> the SRRG heading it is, or None.

    Mirrors normalize.canonical_section so this module has no cross-repo
    import. Kept deliberately short: if it ever needs to grow, the audit is
    reimplementing the pipeline and should import it instead.
    """
    if not heading:
        return None
    s = heading.strip().rstrip(":").strip()
    if s in ONT.SECTIONS:
        return s
    low = s.lower()
    for known in ONT.SECTIONS:
        if known.lower() == low:
            return known
    return ONT.SECTION_ALIASES.get(low)


def measure(split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    lat = collections.Counter()
    lat_excused = collections.Counter()
    zone = collections.Counter()
    leak_side = collections.Counter()
    leak_zone = collections.Counter()
    n_anat = 0

    for _rec, prop in propositions(split, limit):
        for a in prop.get("anatomy") or []:
            n_anat += 1
            lab, side, zn = a.get("label"), a.get("laterality"), a.get("zone")
            imp_side, imp_zone, _grp = ONT.ANATOMY.get(lab, (None, None, None))

            if imp_side and side not in _SOFT_SIDE and side != imp_side:
                if lab in SIDED_MIDLINE:
                    lat_excused[lab] += 1
                else:
                    lat[f"{lab}: {imp_side} -> {side}"] += 1
            if imp_zone and zn and not ONT.zones_compatible(zn, imp_zone):
                zone[f"{lab}: {imp_zone} -> {zn}"] += 1

            if a.get("source") == "section_context":
                if side not in _SOFT_SIDE:
                    leak_side[f"{lab}: {side}"] += 1
                if zn:
                    leak_zone[f"{lab}: {zn}"] += 1

    raw = collections.Counter()
    fixable = collections.Counter()
    unmapped = collections.Counter()
    n_rec = 0
    for rec in records(split, limit):
        n_rec += 1
        head = rec.get("section")
        if head in ONT.SECTIONS:
            continue
        raw[str(head)] += 1
        (fixable if canonical_section(head) else unmapped)[str(head)] += 1

    return {
        "split": split,
        "anatomy_entries": n_anat,
        "records": n_rec,
        "laterality": {"total": sum(lat.values()), "top": lat.most_common(12)},
        "laterality_excused": {"total": sum(lat_excused.values()),
                               "top": lat_excused.most_common(8)},
        "zone": {"total": sum(zone.values()), "top": zone.most_common(8)},
        "rule4_side": {"total": sum(leak_side.values()),
                       "top": leak_side.most_common(8)},
        "rule4_zone": {"total": sum(leak_zone.values()),
                       "top": leak_zone.most_common(8)},
        "section_noncanonical": sum(raw.values()),
        "section_fixable": fixable.most_common(20),
        "section_unmapped": unmapped.most_common(20),
    }


def render(res: Dict[str, Any], cfg=None) -> str:
    show_ex = cfg is None or cfg.shows_examples(res["split"])
    body = [section(f"1-F  Post-normalization invariants  ({res['split']})"),
            table([[res["anatomy_entries"], res["records"],
                    res["laterality"]["total"], res["zone"]["total"],
                    res["rule4_side"]["total"], res["rule4_zone"]["total"],
                    res["section_noncanonical"],
                    res["laterality_excused"]["total"]]],
                  ["anatomy", "records", "lat contra", "zone contra",
                   "r4 side leak", "r4 zone leak", "non-canon section",
                   "excused by SIDED_MIDLINE"])]

    for key, title in (("laterality", "Laterality contradictions"),
                       ("zone", "Zone contradictions"),
                       ("rule4_side", "Rule 4: heading contributed a side"),
                       ("rule4_zone", "Rule 4: heading contributed a zone")):
        if res[key]["top"] and show_ex:
            body.append(f"\n**{title}**\n")
            body.append(table([[k, v] for k, v in res[key]["top"]],
                              ["label: implied -> recorded", "count"]))

    if res["laterality_excused"]["top"] and show_ex:
        body.append("\n**Excused by SIDED_MIDLINE** (an older ontology would "
                    "report these as defects):\n")
        body.append(table([[k, v] for k, v in res["laterality_excused"]["top"]],
                          ["label", "count"]))

    if res["section_fixable"]:
        body.append("\n**Headings an alias already covers** -- "
                    "re-running normalize.py fixes these:\n")
        body.append(table([[k, v, canonical_section(k)]
                           for k, v in res["section_fixable"]],
                          ["heading", "records", "would become"]))
    if res["section_unmapped"]:
        body.append("\n**Headings no alias covers** -- need a SECTION_ALIASES "
                    "row or a manual decision:\n")
        body.append(table([[k, v] for k, v in res["section_unmapped"]],
                          ["heading", "records"]))
    return "\n".join(body) + "\n"


def _join(parts):
    return "\n".join(parts)


def run(cfg) -> core.Result:
    per = [measure(sp, cfg.limit) for sp in cfg.splits]
    body = core.summary(
        [[r["split"], f"{r['anatomy_entries']:,}", r["laterality"]["total"],
          r["zone"]["total"],
          pct(r["laterality"]["total"] + r["zone"]["total"],
              r["anatomy_entries"]),
          r["laterality_excused"]["total"]] for r in per],
        ["split", "anatomy entries", "laterality contra", "zone contra",
         "%", "excused by SIDED_MIDLINE"],
        "`excused` is not a defect count -- it is how many rows an ontology "
        "without SIDED_MIDLINE would have reported as defects and this one "
        "correctly does not.")
    body += _join(render(r, cfg) for r in per)

    bad = sum(r["laterality"]["total"] + r["zone"]["total"] for r in per)
    tot = sum(r["anatomy_entries"] for r in per)
    excused = sum(r["laterality_excused"]["total"] for r in per)
    share = bad / tot if tot else 0.0
    verdict = (core.PASS if share < WARN_AT else
               core.FAIL if share >= FAIL_AT else core.WARN)
    head = (f"{bad:,} of {tot:,} anatomy entries ({share:.2%}) contradict "
            f"their label; {excused:,} excused by SIDED_MIDLINE")
    return core.Result(body, verdict, head,
                       {"contradictions": bad, "entries": tot,
                        "share": share, "excused": excused})


if __name__ == "__main__":
    import sys
    sp = sys.argv[1] if len(sys.argv) > 1 else "test"
    print(render(measure(sp)))
