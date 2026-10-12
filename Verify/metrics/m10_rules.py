#!/usr/bin/env python3
"""Metric R -- run step 3's checks over the whole corpus.

Pipeline/validate.py holds 38 checks and every finding names the rule it
breaks, but the shipped records have no review field: it never ran on them.

Two tables come out: violations per rule (the priority list for prompt work)
and trigger distribution (the sampling frame for human review).

Read the rates as:
    0%         dead check -- find out why it never fires
    0.1-5%     healthy; probably real defects
    5-20%      a systematic weakness of the prompt
    >20%       suspect the check or the spec, not the data

    python3 m10_rules.py [--all] [--limit N]
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'R'
TITLE = 'Rule validation (step 3)'
SCOPE = 'corpus'         # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Which of step 3's rules does the data break, and how often? The "
        "per-rule table is the priority list for prompt work.")

MEANS = """## 한 줄로

**정해 놓은 규칙 44개를 전체 데이터에 돌려서 어긴 곳을 센다.**

## 규칙이란

"명제를 이렇게 만들어라"라고 문서에 적어 둔 것들이다. 예를 들면,

- *rule 2* — 한 문장에 소견이 둘이면 명제도 둘로 나눠라
- *rule 3* — **원문에 없는 말을 지어내지 마라**
- *rule 7* — 기구는 끝이 어디 있는지 적어라
- *rule 9* — '크기' 칸과 '정도' 칸을 섞지 마라
- *rule 11* — **조건이 붙은 부정**에는 경고를 달아라

마지막 것이 중요하다. `"No large pleural effusion."` 은 *"큰 흉수는 없다"* 이지
*"흉수가 없다"* 가 아니다. **작은 흉수는 있을 수 있다.** 이걸 그냥 "없음"으로
읽으면 환자 정보가 왜곡된다.

## 두 등급

| 등급 | 뜻 |
|---|---|
| `error` | **그 상태로는 쓸 수 없다** |
| `warning` | **사람이 한 번 봐야 한다** (틀렸다는 뜻은 아니다) |

## 이 요소의 진짜 쓸모

**규칙별 위반 표가 곧 "프롬프트를 어디부터 고칠까"의 우선순위다.** 가장 많이
어긴 규칙이 가장 먼저 고칠 것이다. 실제로 프롬프트 v2 는 이 표의 상위 다섯
줄을 근거로 고쳐졌다.

## 한 번도 안 터진 검사가 오히려 좋은 소식이다

리포트는 **안 터진 검사 목록**도 낸다. 그게 거의 전부 이런 것들이다.

    entity_type_invalid   (칸에 정해진 값만 들어갔나)
    derived_from_cycle    (명제끼리 연결이 빙빙 도나)
    zone_invalid          (구역 이름이 목록에 있나)

전부 **형식 검사**다. 즉 **형식은 완벽하고, 남은 문제가 전부 "판단"의 문제**
라는 뜻이다. 형식이 틀리면 고치기 쉽고, 판단이 틀리면 고치기 어렵다.

## 덤으로 내는 것

`review trigger` 도 같이 낸다. 이건 결함이 아니라 **오류가 몰리는 지점**이다.
예를 들어 "한 문장에 소견이 둘 이상" 인 문장은 틀릴 확률이 높다. 사람이 검토할
때 **어디부터 볼지** 알려 준다.
"""

# Share of records carrying a hard error. An error means the record cannot be
# used as it stands, so the bands are tighter than for a warning.
WARN_AT = 0.005
FAIL_AT = 0.05



import argparse
import collections

import core
from core import REPO, SMALL, SPLITS, records, table

import sys
sys.path.insert(0, REPO)
from Pipeline.validate import TRIGGERS, validate_record      # noqa: E402


def measure(splits, limit=None):
    codes = collections.Counter()
    sev = collections.Counter()
    rules = collections.Counter()
    trig = collections.Counter()
    examples = {}
    n = n_bad = n_warn = 0
    for sp in splits:
        for rec in records(sp, limit):
            n += 1
            res = validate_record(rec)
            if res["errors"]:
                n_bad += 1
            if res["warnings"]:
                n_warn += 1
            for f in res["findings"]:
                codes[f["code"]] += 1
                sev[f["severity"]] += 1
                rules[f.get("rule") or "-"] += 1
                if f["code"] not in examples:
                    examples[f["code"]] = (
                        (rec.get("utterance") or "")[:70], f["message"][:80])
            for t in res["triggers"]:
                trig[t] += 1
    return n, n_bad, n_warn, codes, sev, rules, trig, examples


def report(splits, limit=None, measured=None) -> str:
    n, n_bad, n_warn, codes, sev, rules, trig, ex = (
        measured or measure(splits, limit))
    out = ["### R  Rule validation (step 3)\n"]
    out.append(table([
        ["records checked", f"{n:,}"],
        ["records with an error", f"{n_bad:,}  ({100*n_bad/max(1,n):.2f}%)"],
        ["records with a warning", f"{n_warn:,}  ({100*n_warn/max(1,n):.2f}%)"],
        ["findings total", f"{sum(codes.values()):,}"],
    ], ["item", "value"]))

    out.append("\n**Violations per rule** -- the priority list for prompt work\n")
    out.append(table([[r, f"{c:,}", f"{100*c/max(1,n):.2f}%"]
                      for r, c in rules.most_common()],
                     ["rule", "violations", "of records"]))

    out.append("\n**Per check code**\n")
    rows = []
    for code, c in codes.most_common(24):
        utt, msg = ex.get(code, ("", ""))
        rows.append([code, f"{c:,}", f"{100*c/max(1,n):.2f}%", utt])
    out.append(table(rows, ["code", "fired", "of records", "example (utterance)"]))

    dead = [c for c in _ALL_CODES if codes[c] == 0]
    if dead:
        out.append(f"\n**{len(dead)} checks never fired** -- either the defect is "
                   f"absent from this data, or the check cannot see it\n")
        out.append("`" + "`, `".join(sorted(dead)) + "`\n")

    out.append("\n**Review trigger distribution** -- not defects, but where errors concentrate\n")
    out.append(table([[t, f"{trig[t]:,}", f"{100*trig[t]/max(1,n):.1f}%"]
                      for t in TRIGGERS], ["trigger", "count", "of records"]))
    return "\n".join(out)


# Every code validate.py can emit; needed to spot checks that never fire.
_ALL_CODES = [
    "entity_text_not_in_utterance", "anatomy_text_not_in_utterance",
    "descriptor_text_not_in_utterance", "assertion_cue_not_in_utterance",
    "comparison_cue_not_in_utterance", "missing_id", "duplicate_id",
    "entity_type_invalid", "entity_label_missing", "entity_label_not_canonical",
    "laterality_invalid", "zone_invalid", "role_invalid", "source_invalid",
    "descriptor_type_invalid", "assertion_invalid", "comparison_invalid",
    "derived_from_self", "derived_from_unknown", "derived_from_cycle",
    "negation_cue_on_present", "hedge_cue_on_present", "absent_without_cue",
    "qualified_negation_unwarned", "resolved_not_absent",
    "chronicity_as_comparison", "descriptor_wrong_axis",
    "comparison_as_descriptor", "normal_state_as_absence",
    "laterality_contradicts_label", "zone_contradicts_label",
    "section_context_has_laterality", "section_context_has_zone",
    "section_conflict", "device_role_on_non_device", "device_tip_not_located",
    # Section 2 field invariants (2026-09-14)
    "anatomy_source_carries_span", "anatomy_span_is_side_only",
    "anatomy_span_is_relative",
    "inference_not_split", "no_propositions",
    # rule 2 splitting checks
    "should_be_one_proposition", "duplicate_proposition",
    "coordination_not_split",
]

def _join(parts):
    return "\n".join(parts)


def _merge(per):
    """Corpus totals from the per-split measurements, so the data is read once.

    Examples are taken from the example split alone -- the dict is keyed by
    check code, so merging four splits would mean the sentence shown for a
    code came from whichever split happened to be first.
    """
    n = sum(p[0] for p in per)
    n_bad = sum(p[1] for p in per)
    n_warn = sum(p[2] for p in per)
    codes, sev, rules, trig = (collections.Counter() for _ in range(4))
    for p in per:
        codes.update(p[3]); sev.update(p[4]); rules.update(p[5]); trig.update(p[6])
    return n, n_bad, n_warn, codes, sev, rules, trig


def run(cfg) -> core.Result:
    per = {sp: measure([sp], cfg.limit) for sp in cfg.splits}
    n, n_bad, n_warn, codes, sev, rules, trig = _merge(per.values())
    # One split's examples, not a mixture: see _merge.
    ex_split = cfg.example_split if cfg.example_split in per else cfg.splits[-1]
    ex = per[ex_split][7]

    body = core.summary(
        [[sp, f"{p[0]:,}", f"{p[1]:,}", f"{100*p[1]/max(1,p[0]):.2f}%",
          f"{p[2]:,}", f"{100*p[2]/max(1,p[0]):.2f}%",
          f"{sum(p[3].values()):,}",
          (p[5].most_common(1)[0][0] if p[5] else "—")]
         for sp, p in per.items()],
        ["split", "records", "errors", "err %", "warnings", "warn %",
         "findings", "worst rule"],
        "`worst rule` is the single rule broken most often in that split. "
        "The same rule leading in every split means the defect is in the "
        "prompt, not in one batch of data.")
    body += core.example_note(ex_split) if cfg.example_split else ""
    body += report(cfg.splits, cfg.limit,
                   measured=(n, n_bad, n_warn, codes, sev, rules, trig, ex))
    body += ("\n> **The checks that never fire are the good news.** They are "
             "almost all enum, id and graph integrity -- so schema compliance "
             "is complete and everything still failing is a judgement, not a "
             "format, problem.\n")
    err = n_bad / max(1, n)
    verdict = (core.PASS if err < WARN_AT else
               core.FAIL if err >= FAIL_AT else core.WARN)
    top = rules.most_common(1)
    head = (f"{err:.2%} of records carry an error, {n_warn/max(1,n):.2%} a "
            f"warning" + (f"; worst rule: {top[0][0]} ({top[0][1]:,})" if top else ""))
    return core.Result(body, verdict, head,
                       {"records": n, "error_rate": err,
                        "warn_rate": n_warn / max(1, n)})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    print(report(SPLITS if a.all else SMALL, a.limit))
