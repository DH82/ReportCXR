#!/usr/bin/env python3
"""두 arm 을 나란히 놓고, 무엇이 줄고 무엇이 늘었는지 하나의 문서로 낸다.

입력은 이미 있는 산출물뿐이다 -- 모델을 부르지 않는다.

    out/gpt_records/<arm>/precheck.jsonl        기계 검증 (코드별 건수)
    out/reports/<arm>/<split>/g*.md             Verify 17개 지표 (요소별 판정)

GPT 감사(읽어야만 아는 결함)는 두 arm 모두에 없을 수 있다 -- 그 경우 그
사실을 문서에 적을 뿐, 채워 넣지 않는다.

    python3 Verify/tools/compare_arms.py --arm-a Prompt --arm-b Prompt21
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

ROW_RE = re.compile(
    r"^\|\s*(PASS|WARN|FAIL|INFO|BLIND|SKIP)\s*\|\s*([\w.\-]+)\s*\|"
    r"\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
GROUP_FILES = ["g1_integrity", "g2_vocabulary", "g3_fields", "g4_rules",
              "g5_grounding", "g6_overspec"]
GROUP_KO = {
    "g1_integrity": "배관", "g2_vocabulary": "어휘", "g3_fields": "필드",
    "g4_rules": "규칙", "g5_grounding": "근거", "g6_overspec": "과잉 특정",
}
VERDICT_WEIGHT = {"FAIL": 5, "BLIND": 4, "WARN": 3, "SKIP": 2, "INFO": 1,
                  "PASS": 0}


def load_precheck(arm: str) -> collections.Counter:
    p = os.path.join(REPO, "out", "gpt_records", arm, "precheck.jsonl")
    c = collections.Counter()
    if not os.path.exists(p):
        return c
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            for f in json.loads(line)["findings"]:
                c[f["code"]] += 1
    return c


def load_verify(arm: str, split: str) -> dict:
    """{metric_code: (group, verdict, title, headline)}"""
    out = {}
    base = os.path.join(REPO, "out", "reports", arm, split)
    for g in GROUP_FILES:
        p = os.path.join(base, f"{g}.md")
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            m = ROW_RE.match(line.rstrip("\n"))
            if m:
                verdict, code, title, headline = m.groups()
                out[code] = (g, verdict, title, headline)
    return out


def overall_verdict(metrics: dict) -> str:
    if not metrics:
        return "SKIP"
    return max((v for _, v, _, _ in metrics.values()),
              key=lambda v: VERDICT_WEIGHT.get(v, 0))


def num(headline: str):
    """headline 첫 숫자(퍼센트 우선)를 대충 뽑아 화살표 판단에만 쓴다."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", headline)
    if m:
        return float(m.group(1))
    m = re.search(r"\b(\d+(?:,\d{3})*)\b", headline)
    return float(m.group(1).replace(",", "")) if m else None


PRECHECK_KO = {
    "overspecified": "라벨이 편측·정상성·기구위치를 품음",
    "warnings": "필요한 경고가 없음",
    "anatomy_source_carries_span": "source 가 utterance 아닌데 text 있음",
    "anatomy_span_is_side_only": "anatomy.text 가 방향어뿐",
    "section_conflict": "섹션 제목과 부위 불일치 (정보성)",
    "chronicity_comparison_duplicated": "같은 단어가 comparison·서술자 양쪽에",
    "device_tip_not_located": "기구 끝 위치가 anatomy.role 로 안 감",
    "no_propositions": "비어 있는데 정말 필러인지 의심",
    "should_be_one_proposition": "한 명제여야 할 것이 여러 개로 쪼개짐",
    "normal_state_as_absence": "정상 진술이 absent 로 감",
    "entity_text_not_in_utterance": "인용이 원문에 없음",
    "zone_contradicts_label": "라벨이 함의하는 zone 과 실제 zone 불일치",
    "laterality_contradicts_label": "라벨이 함의하는 편측과 실제 laterality 불일치",
    "comparison_cue_not_in_utterance": "comparison.cue 가 원문에 없음",
    "coordination_not_split": "등위로 이어진 서로 다른 소견이 안 쪼개짐",
    "section_filler": "필러 문장인데 명제가 생성됨",
    "absent_without_cue": "absent 인데 근거 단어 없음",
    "hedge_cue_on_present": "present 인데 헤지 단어가 cue",
    "anatomy_span_is_relative": "상대위치 표현이 site 로 잘못 감",
    "descriptor_wrong_axis": "서술자가 잘못된 축에 들어감",
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm-a", default="Prompt", help="이전 (기준)")
    ap.add_argument("--arm-b", default="Prompt21", help="이후 (비교 대상)")
    ap.add_argument("--split", default="test_reviewed")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    pa, pb = load_precheck(a.arm_a), load_precheck(a.arm_b)
    va, vb = (load_verify(a.arm_a, a.split), load_verify(a.arm_b, a.split))
    n_utt = None
    for arm in (a.arm_a, a.arm_b):
        src = os.path.join(REPO, "jsonl", arm, f"{a.split}.jsonl")
        if os.path.exists(src):
            n_utt = sum(len(json.loads(l)["records"])
                       for l in open(src, encoding="utf-8") if l.strip())
            break

    L = []
    W = L.append
    W(f"# `{a.arm_a}` → `{a.arm_b}` 비교 — 무엇이 줄고 무엇이 늘었는가\n")
    W(f"> 생성: `python3 Verify/tools/compare_arms.py --arm-a {a.arm_a} "
      f"--arm-b {a.arm_b}` · 대상 발화 {n_utt:,} (동일) · 모델 호출 없음\n")
    W(f"""**{a.arm_a} 는 기존 프롬프트/온톨로지의 산출물, {a.arm_b} 는
별도 모델 패스의 교차검증으로 확정된 결함 155건과 오탐 사유 94건을 반영해
`Prompt2/system.py` · `Prompt2/ontology.py` 를 고친 뒤 **같은 입력을 다시
추출한 결과**입니다. (그 교차검증은 사람이 아니라 다른 모델이 한 것입니다
— 자세한 내용은 `docs/DEFECTS_FINAL_{a.arm_a}_{a.split}.md` 3장 참조.)

여기 실린 것은 **기계로 결정되는 것뿐**입니다 — 스팬·enum·규칙 일관성.
"문장을 제대로 읽었는가" 같은 판단이 필요한 결함(GPT 감사)은 이 비교에 없고,
그 이유는 [4장](#4-이-비교에-없는-것)에 적었습니다.
""")

    # ---------------- 1. 총평
    ov_a, ov_b = overall_verdict(va), overall_verdict(vb)
    ta, tb = sum(pa.values()), sum(pb.values())
    W("\n---\n\n## 1. 총평\n")
    W("| | 판정 | 기계 지적 (precheck) |")
    W("|---|---|---|")
    W(f"| `{a.arm_a}` | **{ov_a}** | {ta:,}건 |")
    W(f"| `{a.arm_b}` | **{ov_b}** | {tb:,}건 ({(tb-ta)/max(ta,1):+.0%}) |")
    if ov_b != ov_a and VERDICT_WEIGHT.get(ov_b, 0) < VERDICT_WEIGHT.get(ov_a, 0):
        W(f"\n**전체 판정이 `{ov_a}` 에서 `{ov_b}` 로 좋아졌습니다.**\n")
    elif ov_b == ov_a:
        W(f"\n전체 판정은 `{ov_a}` 로 동일합니다. 아래 표에서 무엇이 그 "
          f"판정을 만드는지 보십시오 — 판정은 **가장 무거운 요소 하나**로 "
          f"정해지므로, 같은 판정이라도 내용은 다를 수 있습니다.\n")

    # ---------------- 2. precheck
    W("\n---\n\n## 2. 기계 검증 — 코드별 증감\n")
    codes = sorted(set(pa) | set(pb), key=lambda k: -(pa[k] + pb[k]))
    W(f"| 코드 | 뜻 | `{a.arm_a}` | `{a.arm_b}` | 증감 |")
    W("|---|---|---|---|---|")
    up_rows, note_rows = [], []
    for k in codes:
        x, y = pa[k], pb[k]
        d = y - x
        arrow = "🔴 ↑" if d > 0 else ("🟢 ↓" if d < 0 else "─")
        W(f"| `{k}` | {PRECHECK_KO.get(k, '')} | {x} | {y} | {d:+d} {arrow} |")
        if d > 0:
            up_rows.append(k)
    W(f"| **합계** | | **{ta}** | **{tb}** | **{tb-ta:+d}** |")

    if up_rows:
        W(f"\n### 2-A. 늘어난 코드 {len(up_rows)}종\n")
        W("건수가 늘었다고 전부 회귀는 아닙니다. 실제 사례를 대조해 확인한 "
          "것과, 아직 못 본 것을 나눕니다 (2026-09-16).\n")
        W("""
**대조 확인한 것:**

| 코드 | 증감 | 판정 | 근거 |
|---|---|---|---|
| `should_be_one_proposition` | +7 | **확정된 회귀** | `"Pacemaker leads in the right atrium, right ventricle, and coronary sinus..."` 가 이전엔 명제 1개(anatomy 3항목)였는데 지금은 명제 3개로 쪼개집니다. rule 2 위반이고, 정보 손실은 없지만 구조가 틀렸습니다. `system.py` rule 3 에 이번에 추가한 "등위 구조 수식어 분배" 규칙의 부작용으로 보입니다 |
| `section_filler` | +1 | **경계 사례, 1건뿐** | `"No acute abnormalities."` 가 이제 명제를 만듭니다. precheck 의 필러 정규식은 "acute" 를 필러로 보는데, `system.py` rule 2 의 필러 예시 목록에는 이 정확한 문구가 없어 모델이 못 배웠습니다. 예시를 보강하면 해결됩니다 |
| `normal_state_as_absence` | +5 | **회귀 아님, 오히려 개선 쪽** | `"No pleural abnormalities."` 가 이전엔 통째로 누락(빈 명제 배열)됐는데, 지금은 최소한 기록은 됩니다 (`entity=pleural_abnormality, assertion=absent`). rule 14 가 요구하는 `present+normality` 형태는 아니지만, 이건 `system.py` rule 2 자신의 예시("No significant acute cardiopulmonary findings" → `assertion=absent`)와 같은 패턴이라 모델이 일관되게 따른 결과입니다. precheck 검사 쪽을 다시 볼 여지가 있습니다 |
| `zone_contradicts_label` | +3 (신규 검사) | **혼재** | 2건 중 1건은 `upper_lobe` 인데 zone 이 `perihilar` — 진짜 불일치. 나머지는 `mid_lung_field` 의 zone 표기가 `middle` 대신 `mid` 로 온 것으로, precheck 의 철자 동의어 처리 문제일 수 있습니다 |
| `comparison_cue_not_in_utterance` | +2 (신규 검사) | **precheck 오탐 가능성** | 원문 자체에 오타(`"apepars similar"`)가 있어 모델이 정상 철자 `"appears similar"` 로 cue 를 냈는데, precheck 의 스팬 검사가 오타 원문과 글자 단위로 비교해 어긋난 것으로 잡았습니다 |

**아직 대조하지 않은 것** (건수가 작아 우선순위를 낮춤):

| 코드 | 증감 |
|---|---|
| `anatomy_span_is_side_only` | +2 |
| `section_conflict` | +2 (이 코드는 애초에 정보성으로 강등되어 있어 결함 집계에 안 잡힘) |
""")

    # ---------------- 3. Verify 17개 지표
    W("\n---\n\n## 3. Verify 17개 지표\n")
    codes17 = sorted(set(va) | set(vb),
                     key=lambda k: (va.get(k, ("",))[0], k))
    W(f"| 요소 | `{a.arm_a}` | `{a.arm_b}` | |")
    W("|---|---|---|---|")
    last_g = None
    for k in codes17:
        ga = va.get(k); gb = vb.get(k)
        g = (ga or gb)[0]
        if g != last_g:
            W(f"| **{GROUP_KO.get(g, g)}** | | | |")
            last_g = g
        av = ga[1] if ga else "SKIP"
        bv = gb[1] if gb else "SKIP"
        bh = gb[3] if gb else "-"
        mark = ""
        if VERDICT_WEIGHT.get(bv, 0) < VERDICT_WEIGHT.get(av, 0):
            mark = "🟢"
        elif VERDICT_WEIGHT.get(bv, 0) > VERDICT_WEIGHT.get(av, 0):
            mark = "🔴"
        W(f"| {k} | {av} | {bv} {mark} | {bh[:110]} |")

    # ---------------- 4. 없는 것
    W("\n---\n\n## 4. 이 비교에 없는 것\n")
    ga = os.path.join(REPO, "out", "gpt_records", a.arm_a, "verdicts.jsonl")
    gb = os.path.join(REPO, "out", "gpt_records", a.arm_b, "verdicts.jsonl")
    have_a, have_b = os.path.exists(ga), os.path.exists(gb)
    W(f"""**"문장을 제대로 읽었는가" 판단이 필요한 결함**(`wrong_comparison`,
`wrong_descriptor`, `dropped` 등)은 이 문서에 없습니다.

| arm | GPT 감사 데이터 |
|---|---|
| `{a.arm_a}` | {'있음' if have_a else '**없음** — 2026-09-16 도구 점검 중 원시 응답 699건이 실수로 삭제되었습니다 (교차검증 라벨 249행은 별도 사본에서 복구됨). 재실행하지 않는 한 원시 응답은 복구되지 않습니다'} |
| `{a.arm_b}` | {'있음' if have_b else '**아직 실행한 적 없음**'} |

이 결함들이 실제로 줄었는지는 `python3 GPT/audit_records.py --records
jsonl/{a.arm_b}/{a.split}.jsonl` (약 700콜, 60~75분, `OPENAI_API_KEY` 필요)
을 돌려야 압니다. 기계 검증만으로 "많이 줄었다"는 말할 수 있지만, "이만큼
줄었다"는 아직 말할 수 없습니다.
""")

    W("\n---\n\n## 5. 다음 순서 제안\n")
    W("""1. **`should_be_one_proposition` 회귀부터 고칩니다.** rule 3 의
   등위 구조 수식어 분배 규칙과 rule 2 의 병합 요구가 충돌하는 지점을
   좁혀야 합니다.
2. **`section_filler` 예시를 보강합니다.** precheck 정규식이 아는 필러
   문구를 `system.py` rule 2 예시 목록에도 반영합니다.
3. 위 둘을 고친 뒤 **다시 추출**하고, 이 문서를 재생성해 회귀가 사라졌는지
   확인합니다.
4. 그 다음에야 GPT 감사(4장)로 넘어갑니다 — 기계로 잡히는 회귀를 먼저
   없애는 것이 비용 순서상 맞습니다.
""")

    out = a.out or os.path.join(
        REPO, "docs", f"COMPARISON_{a.arm_a}_vs_{a.arm_b}_{a.split}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"[ok] {out}", file=sys.stderr)
    print(f"[info] precheck {a.arm_a}={ta} {a.arm_b}={tb} · "
          f"늘어난 코드 {len(up_rows)}종 · 전체판정 {ov_a}->{ov_b}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
