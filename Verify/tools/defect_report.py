#!/usr/bin/env python3
"""확정된 결함 하나의 문서. 사람이 읽고, 나중에 다시 찾아보는 용도.

세 갈래의 증거를 한 장으로 합친다. 합치는 이유는 편의가 아니라, **각각이
얼마나 믿을 만한지가 다르고 그 차이를 옆에 두지 않으면 독자가 알 수 없기
때문**이다.

    기계 검증   GPT/precheck.py          코드별 정밀도 측정됨 (교차검증 192건)
    GPT 감사    GPT/audit_records.py     249건 전수를 별도 모델 패스가
                                         교차검증 -- 추정이 아니라 건별 확정
    원본 대조   SRRG CSV original_report 상류가 만든 문장인지 판별

**"확정"의 의미를 정확히 하자면:** GPT 감사의 "교차검증"은 사람이 아니라
**다른 모델 패스가 같은 행을 다시 판정한 결과**다. 1차 판정자 혼자보다는
믿을 만하지만(두 모델이 독립적으로 같은 결론에 이른 것), 두 모델이 같은
맹점을 공유하면 "일치"가 "정확"을 뜻하지 않는다. `persistent` 반전 사례
(README.md 참조)처럼 이 방식으로도 실수를 잡은 적이 있지만, 임상적으로
쓰기 전에는 여전히 사람의 확인이 필요하다.

`--labels` 가 주어지면 GPT 감사는 **교차검증에서 yes 로 나온 것만** 싣는다.
정밀도가 0.62 인 목록을 그대로 실으면 읽는 사람이 세 건 중 한 건을
헛짚게 되고, 그러면 문서 전체의 신용이 같이 내려간다.

    python3 Verify/tools/defect_report.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import defect_cases as DC                                        # noqa: E402

GPT = os.path.join(REPO, "out", "gpt_records")
LABELS = os.path.join(GPT, "goldset", "sheet_precision_labeled.tsv")

# 코드별 정밀도. 249건 전수 라벨의 결과이고, 이 표가 문서의 신뢰 계약이다.
PRECISION = {
    "wrong_anatomy":    (36, 39), "wrong_entity":    (19, 21),
    "dropped":          (16, 20), "wrong_descriptor": (52, 79),
    "wrong_assertion":   (9, 23), "wrong_comparison": (16, 43),
    "bad_split":         (6, 23), "hallucinated":      (1, 1),
}

CODE_KO = {
    "wrong_anatomy": "부위·편측·역할이 문장과 다름",
    "wrong_entity": "무엇인지를 잘못 짚음",
    "dropped": "문장에 있는데 기록되지 않음",
    "wrong_descriptor": "상태 서술이 빠졌거나 종류가 틀림",
    "wrong_assertion": "있다/없다/애매를 잘못 읽음",
    "wrong_comparison": "이전 검사와의 비교를 잘못 읽음",
    "bad_split": "둘을 하나로 뭉치거나 하나를 둘로 쪼갬",
    "hallucinated": "문장에 없는 것을 지어냄",
}


def load_labels(path):
    if not os.path.exists(path):
        return [], []
    rows = list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))
    yes = [r for r in rows if r["LABEL_true_defect"].strip().lower() == "yes"]
    no = [r for r in rows if r["LABEL_true_defect"].strip().lower() == "no"]
    return yes, no


def load_precheck(path):
    out = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", default="Prompt")
    ap.add_argument("--split", default="test_reviewed")
    ap.add_argument("--labels", default=None,
                    help="default: out/gpt_records/<arm>/goldset/"
                         "sheet_precision_labeled.tsv")
    ap.add_argument("--max-cases", type=int, default=10)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    arm_gpt = os.path.join(GPT, a.arm)
    if a.labels is None:
        a.labels = os.path.join(arm_gpt, "goldset",
                                "sheet_precision_labeled.tsv")

    src = os.path.join(REPO, "jsonl", a.arm, f"{a.split}.jsonl")
    recs = DC.load(src)
    yes, no = load_labels(a.labels)
    pre = load_precheck(os.path.join(arm_gpt, "precheck.jsonl"))
    n_pre = sum(len(p["findings"]) for p in pre)
    if not os.path.exists(a.labels):
        print(f"[warn] {a.labels} 없음 -- 이 arm 은 아직 다른 모델 패스로 "
              f"교차검증된 시트가 없습니다. 2장이 비어 나옵니다.",
              file=sys.stderr)

    L = []
    W = L.append
    W(f"# `jsonl/{a.arm}/{a.split}.jsonl` — 확정 결함 종합\n")
    W(f"> 발화 {len(recs):,} · 리포트 233 · 생성 "
      f"`python3 Verify/tools/defect_report.py`\n")
    W("""**이 문서 하나만 보시면 됩니다.** 세 갈래로 찾은 것을 합쳤고,
각각이 얼마나 믿을 만한지를 옆에 적었습니다.

| 어디를 보시나 | 읽을 곳 |
|---|---|
| **의사** — 임상 판단이 필요한 것 | [1장](#1-의사-판단이-필요한-것) |
| **개발** — 지금 고칠 수 있는 것 | [2장](#2-확정된-결함--지금-고칠-수-있는-것) |
| 왜 이 숫자를 믿나 | [3장](#3-근거와-신뢰도) |
| 아직 못 쓰는 것 | [4장](#4-아직-쓸-수-없는-것) |
| 중간에 틀렸던 판단 | [5장](#5-정정-이력) |
""")

    # ---------------- 1. 의사
    W("\n---\n\n## 1. 의사 판단이 필요한 것\n")
    W("""세 가지입니다. 셋 다 **데이터를 고치기 전에 무엇이 옳은지부터
정해야** 하는 것들이고, 코드로는 답이 나오지 않습니다.
""")
    ph = DC.group_placeholder(recs, DC.originals(a.split))
    fillers = [x for x in ph if x["kind"] == "자리표시자"]
    no_orig = [x for x in fillers if not x["in_orig"]]
    lim = [r for r in recs
           if DC.LIMIT.search(r["utterance"]) or DC.QUALITY.search(r["utterance"])]
    sch = DC.group_schema(recs)
    split = {k: c for k, c in sch.items() if c["bilateral"] and c["unspecified"]}
    W("| # | 질문 | 규모 | 자세히 |")
    W("|---|---|---|---|")
    W(f"| 1-A | 원본에 없는 **섹션 자리표시자**를 비워둔 것이 맞습니까? "
      f"| {len(fillers)}건 (원본에 없음 {len(no_orig)}) | "
      f"[A장](PROMPT_DEFECTS_{a.arm}_{a.split}.md) |")
    W(f"| 1-B | **판독 신뢰도**(회전·판독 제한)를 남길 것입니까? 남긴다면 "
      f"어디에? | {len(lim)}건 | [B장](PROMPT_DEFECTS_{a.arm}_{a.split}.md) |")
    W(f"| 1-C | 본래 양측인 구조의 `laterality` 기본값을 하나로 "
      f"고정하시겠습니까? | {len(split)}개 구조 | "
      f"[E장](PROMPT_DEFECTS_{a.arm}_{a.split}.md) |")
    W(f"| 1-D | **`density`(밀도) 서술자 축을 신설**하시겠습니까? | "
      f"아래 참조 | 이 문서 |")

    W("""
### 1-D. `density` 축이 없어서 생기는 문제 (신규)

`dense opacity`(짙은 음영)의 "dense" 를 담을 칸이 스키마에 없습니다. 지금은
`severity`(얼마나 심한가) 아니면 `morphology`(어떤 모양인가)에 넣는데,
**둘 다 정확하지 않습니다.** 밀도는 심각도도 모양도 아닙니다.

검증 과정에서 나온 판단입니다:

> "`dense` 는 밀도 축이라 severity/morphology 어느 쪽도 정확하지 않음 —
> `density` 타입 신설이 필요"

같은 이유로 `prominent`, `accentuated`, `conspicuous` 도 판정이 갈립니다.
축을 만들지 않으실 거라면 **어느 쪽으로 보낼지를 정해서 어휘표에
못박아야** 합니다. 지금은 정해지지 않아 레코드마다 다릅니다.
""")

    # ---------------- 2. 확정 결함
    W("\n---\n\n## 2. 확정된 결함 — 지금 고칠 수 있는 것\n")
    W(f"""**추정이 아니라 전수 교차검증입니다.** GPT 감사가 낸 지적 249건을
**별도 모델 패스**가 하나씩 다시 판정했고, 그중 **{len(yes)}건이 실제
결함으로 확정**됐습니다. 아래는 확정된 것만입니다. (나머지 {len(no)}건은
4장으로 갔습니다.)

> **"확정"은 사람이 낸 결론이 아닙니다.** 1차 판정자(감사 모델)와 2차
> 판정자(교차검증 모델)가 독립적으로 같은 결론에 이르렀다는 뜻이고, 그래서
> 1차 혼자보다는 신뢰도가 높습니다. 다만 두 모델이 같은 맹점을 공유하면
> "일치"가 "정확"을 보장하지 않습니다. 임상 판단에 쓰기 전에는 사람의
> 최종 확인이 필요합니다.

기계 검증은 별도로 {n_pre}건을 냈고, 코드별 정밀도가 측정돼 있습니다.
""")

    # 2026-09-17: 이 절은 Prompt 한 팔에서 한 번 잰 값을 하드코딩하고
    # 있었다. 그 뒤로 검사가 늘고 줄었고, 팔마다 데이터가 다르므로 수치도
    # 다르다. 라벨된 precheck 시트가 있으면 그것을 읽고, 없을 때만
    # 하드코딩 표로 물러선다 -- 문서가 재지 않은 숫자를 주장하지 않도록.
    W("\n### 2-A. 기계가 잡은 것 — 검사별 측정 정밀도\n")
    codes = collections.Counter(f["code"] for p in pre for f in p["findings"])
    MEAN = {"overspecified": "라벨이 편측·정상성·기구끝위치를 품음",
            "modifier_only_in_label": "수식어가 라벨 안에만 있고 "
                                      "`descriptors` 에는 없음",
            "anatomy_source_carries_span": "`source` 가 utterance 가 아닌데 "
                                           "`text` 가 채워짐",
            "anatomy_span_is_side_only": "`anatomy.text` 가 방향어뿐이라 "
                                         "구조를 명명하지 않음",
            "entity_text_not_in_utterance": "인용한 글자가 원문에 없음",
            "comparison_cue_not_in_utterance": "`comparison.cue` 가 원문에 없음",
            "laterality_contradicts_label": "라벨이 함의하는 쪽과 "
                                            "`laterality` 가 충돌",
            "zone_contradicts_label": "라벨이 함의하는 zone 과 충돌",
            "normal_state_as_absence": "정상 상태를 질환의 부재로 인코딩",
            "should_be_one_proposition": "한 소견이 여러 명제로 쪼개짐",
            "warnings": "rule 11 / rule 19 의 경고가 필요한데 없음",
            "device_tip_not_located": "기구 끝 위치가 anatomy 에 없음",
            "section_conflict": "anatomy 가 섹션 제목과 다름",
            "no_propositions": "빈 발화가 아닌데 명제가 없음",
            "section_filler": "섹션 필러인데 명제가 생성됨",
            "coordination_not_split": "한 발화의 서로 다른 개체가 한 명제에"}
    sheet = os.path.join(REPO, "out", "gpt_records", a.arm, "goldset",
                         "sheet_precheck_labeled.tsv")
    measured = {}
    if os.path.exists(sheet):
        agg = collections.defaultdict(lambda: [0, 0])
        for row in csv.DictReader(open(sheet, encoding="utf-8"),
                                  delimiter="\t"):
            v = (row.get("LABEL_true_defect") or "").strip().lower()
            if v not in ("yes", "no"):
                continue
            agg[row["code"]][1] += 1
            agg[row["code"]][0] += (v == "yes")
        measured = {k: (y, n) for k, (y, n) in agg.items() if n}
    if measured:
        W("정밀도는 `out/gpt_records/%s/goldset/sheet_precheck_labeled.tsv` "
          "에서 실제로 세어 본 값입니다. **별도 판정이지 정답지가 아닙니다** "
          "-- 사람 검수를 대체하지 않습니다.\n" % a.arm)
        W("| 검사 | 이 파일의 건수 | 표본 정밀도 | 쓰는 법 | 뜻 |")
        W("|---|---|---|---|---|")
        def band(r):
            return ("목록으로 쓴다" if r >= 0.9 else
                    "사람이 걸러야 한다" if r >= 0.6 else
                    "**쓰지 않는다 — 고치거나 버린다**")
        for k, (y, n) in sorted(measured.items(),
                                key=lambda kv: (-(kv[1][0] / kv[1][1]),
                                                -kv[1][1])):
            r = y / n
            W(f"| `{k}` | {codes.get(k, 0)} | {r:.2f} ({y}/{n}) | "
              f"{band(r)} | {MEAN.get(k, '')} |")
        low = [k for k, (y, n) in measured.items() if y / n < 0.6]
        if low:
            W("\n> **0.6 미만인 검사는 이 문서의 집계에서 빼고 읽으십시오**: "
              + ", ".join(f"`{k}`" for k in sorted(low))
              + ". 잡힌 건수가 그 코드의 결함 수가 아니라, 그 검사가 어떻게 "
                "오독했는지를 세고 있습니다.\n")
        W("\n표본이 한 자리인 코드는 구간이 0 에서 1 까지 벌어집니다. "
          "중간값을 답으로 읽지 마십시오.\n")
    else:
        W("> **이 팔은 precheck 정밀도가 측정되지 않았습니다.** 아래는 "
          "건수일 뿐이고, 그중 몇 건이 진짜인지는 알 수 없습니다. "
          "`python3 GPT/goldset.py sample --mode precheck "
          f"--records jsonl/{a.arm}/{a.split}.jsonl` 로 시트를 만들어 "
          "채우십시오.\n")
        W("| 검사 | 건수 | 뜻 |")
        W("|---|---|---|")
        for k, v in sorted(codes.items(), key=lambda kv: -kv[1]):
            W(f"| `{k}` | {v} | {MEAN.get(k, '')} |")

    W("\n### 2-B. 읽어야만 아는 것 — 교차검증으로 확정된 GPT 감사 결과\n")
    by = collections.defaultdict(list)
    for r in yes:
        by[r["judge_verdict"]].append(r)
    W("| 코드 | 확정 | 그 코드의 정밀도 | 뜻 |")
    W("|---|---|---|---|")
    for k in sorted(by, key=lambda k: -len(by[k])):
        y, n = PRECISION.get(k, (0, 0))
        W(f"| `{k}` | **{len(by[k])}** | {y}/{n} = {y/n:.2f} | "
          f"{CODE_KO.get(k,'')} |")
    W(f"| **계** | **{len(yes)}** | | |")

    for k in sorted(by, key=lambda k: -len(by[k])):
        W(f"\n#### {k} — 확정 {len(by[k])}건  ·  {CODE_KO.get(k,'')}\n")
        for r in by[k][:a.max_cases]:
            W(f"- `{r['utterance_id']}` ({r['section']})")
            W(f"  - 원문: **{r['utterance']}**")
            if r["judge_quote"]:
                W(f"  - 근거: “{r['judge_quote']}”")
            W(f"  - 무엇이: {r['judge_note']}")
            # 실제로 어떻게 들어가 있는지를 병기한다. "무엇이" 는 판정자의
            # 말이고, 이 줄은 데이터 자체다 -- 읽는 사람이 재판정할 수 있게
            # 두 가지를 같이 준다.
            prop = (r.get("propositions") or "").strip()
            if prop:
                try:
                    prop = json.dumps(json.loads(prop), ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    pass
                W(f"  - 현재: `{prop}`")
            if r["LABEL_note"].strip():
                W(f"  - 확인: {r['LABEL_note']}")
        if len(by[k]) > a.max_cases:
            W(f"\n(외 {len(by[k]) - a.max_cases}건 — "
              f"`out/gpt_records/{a.arm}/goldset/"
              f"sheet_precision_labeled.tsv` 에서 "
              f"`judge_verdict={k}` 이고 `LABEL_true_defect=yes` 인 행)")

    # ---------------- 3. 신뢰도
    W("\n---\n\n## 3. 근거와 신뢰도\n")
    W("""이 문서의 모든 숫자는 **측정된 것**입니다. 그 측정이 어떻게
이루어졌는지가 아래입니다.

| 근거 | 어떻게 검증했나 | 결과 |
|---|---|---|
| 기계 검증 | 코드별 30건씩 **별도 모델 패스**가 교차검증 (192건) | 주요 검사 1.00, 낮은 것 둘은 제거·강등 |
| GPT 감사 | 지적 249건 **전수**를 **별도 모델 패스**가 교차검증 | 전체 정밀도 0.62, 코드별 0.26~0.92 |
| 원본 대조 | SRRG CSV `original_report` 문자열 대조 (기계적, 모델 무관) | 자리표시자 34/38 이 원본에 없음 |

### 알아두실 것 세 가지

**① "확정"은 사람이 낸 결론이 아닙니다.** 위 표의 "교차검증"은 감사를
수행한 모델과는 별도의 모델 패스가, 같은 행을 다시 읽고 독립적으로 낸
판정입니다. 사람이 라벨링한 것이 아닙니다. 두 모델이 독립적으로 같은
결론에 이르렀다는 것은 1차 판정자 혼자보다 강한 증거이지만, 두 모델이
공유하는 맹점(같은 훈련 데이터의 관례, 같은 방식으로 헤지 표현을 읽는 것
등)에는 여전히 취약합니다. 이 문서의 "정밀도"는 **모델 간 일치도**로
읽으십시오 — 임상적으로 쓰기 전에는 사람의 최종 확인이 필요합니다.

**② 만장일치는 정답이 아닙니다.** (이건 별개 장치입니다 — 위 ①의
교차검증이 아니라, 감사 모델 자신에게 같은 리포트를 3번 물어 다수결을
낸 것입니다.) 3표 받은 지적의 정밀도가 **0.55**, 2표가 **0.70** 으로
**역전**이었습니다. 같은 모델의 세 표본은 같은 편향을 공유하기 때문입니다
— 실제로 3/3 만장일치 18건이 통째로 한 가지 오탐이었습니다. 투표는
**재현성**을 샀을 뿐 정확도를 사지 못했습니다.

**③ 재현율은 모릅니다.** 이 문서는 "찾은 것이 맞다"는 것만 보증하고,
"빠뜨린 것이 없다"는 보증하지 않습니다. 특히 `dropped` 는 같은 문장을 3번
읽었을 때 읽어낸 주장의 개수가 **283/1,565 발화(18%)** 에서 달랐습니다.
확정된 16건 외에 더 있을 가능성이 높습니다.
""")

    # ---------------- 4. 못 쓰는 것
    W("\n---\n\n## 4. 아직 쓸 수 없는 것\n")
    W(f"""지적 {len(no)}건이 **별도 모델 패스에 의해** 오탐으로 판정됐습니다
(사람이 아닙니다 — 3장 참조). **데이터의 문제가 아니라 판정 규칙의
문제**이므로 결함 목록에 넣지 않았습니다. 다만 사유가 곧 수정안이라
유형별로 남깁니다.
""")
    kinds = collections.Counter()
    ex = collections.defaultdict(list)
    for r in no:
        n = r["LABEL_note"]
        k = ("판정 규칙이 추출 규칙과 충돌" if "rule " in n or "충돌" in n else
             "이미 다른 칸이 담은 것을 또 요구(축 중복)" if "중복" in n else
             "경계 사례 — 어느 쪽도 방어 가능" if "경계" in n or "양가" in n
             else "판독문의 관례를 모름" if "관례" in n or "RadGraph" in n
             else "기타")
        kinds[k] += 1
        if len(ex[k]) < 2:
            ex[k].append(r)
    W("| 유형 | 건수 |")
    W("|---|---|")
    for k, v in kinds.most_common():
        W(f"| {k} | {v} |")
    W("\n대표 사유:\n")
    for k, v in kinds.most_common():
        W(f"\n**{k}** ({v}건)")
        for r in ex[k]:
            W(f"- “{r['utterance'][:70]}” — {r['LABEL_note'][:190]}")
    W(f"""
각 행의 `LABEL_note` 에 `[수정]` 으로 시작하는 구체안이 달려 있습니다
({sum(1 for r in no if '[수정]' in r['LABEL_note'])}건).
판정 프롬프트를 고칠 때 그대로 쓰면 됩니다.
""")

    # ---------------- 5. 정정
    W("\n---\n\n## 5. 정정 이력\n")
    W("""틀렸던 판단을 지우지 않고 남깁니다. 같은 추론으로 다시 같은 실수를
하지 않기 위해서입니다.

| 날짜 | 무엇을 | 왜 틀렸나 |
|---|---|---|
| 2026-09-15 | **`persistent` 를 만성도로 옮기려 함** | 흉부 영상에서 `persistent` 는 이전 검사 대비 지속을 뜻하는 **변화 서술자**이므로 `comparison=stable` 이 맞습니다. 표본 17건이 **17/17 로 오탐** 판정. `ontology.py` 와 `Prompt2/system.py` 수정을 되돌렸고, 진짜 결함은 **같은 단어가 두 칸에 동시에 있는 것**(17건)이었습니다 |
| 2026-09-15 | **"득표가 가장 무거운 신호"** | 3/3 이 2/3 보다 부정확했습니다(0.55 vs 0.70). 계통 편향은 만장일치를 만듭니다 |
| 2026-09-15 | 기계 검증의 `section_conflict` · `chronicity_as_comparison` | 각각 0/16, 0/17 로 전부 오탐. 전자는 정보성으로 강등, 후자는 반대 방향(중복 검출)으로 교체 |
""")

    out = a.out or os.path.join(REPO, "docs",
                                f"DEFECTS_FINAL_{a.arm}_{a.split}.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"[ok] {out}", file=sys.stderr)
    print(f"[info] 확정 {len(yes)} · 보류 {len(no)} · 기계 {n_pre}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
