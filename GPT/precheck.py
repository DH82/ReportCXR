#!/usr/bin/env python3
"""The mechanical layer that must run BEFORE the model is asked anything.

Everything a regex can decide, a regex decides here, and the audit prompt is
then told not to raise it. Two reasons, and the second is the bigger one:

    cost      a model call to ask whether a span occurs in a string is waste
    accuracy  a judge that spends its attention on substring checks has less
              of it for the thing only a reader can do -- did the sentence say
              something the JSON does not

Most of this already existed and is reused, NOT reimplemented:

    Pipeline/validate.py   38 checks, per record. Spans, source/text coupling,
                           cue agreement, splitting, chronicity-vs-comparison,
                           device tip location. Measured on
                           jsonl/Prompt/test_reviewed.jsonl: 198 findings.
    Prompt2/vocabulary.py  the enums, so "in range" is not a second opinion
                           about what the range is

What is added here is only what neither covers:

    enum range             every closed field against vocabulary.py (measured:
                           0 violations -- kept because a silent 0 is the
                           point, and a future arm may not be at 0)
    derived_from resolves  to a proposition id in the same utterance (0)
    over-specified labels  the prefix/infix patterns E1/E2/E3 banned, which
                           live in Verify's corpus metrics but not in the
                           per-record validator (measured: 77)
    filler polarity        validate.py flags an empty proposition array as
                           `no_propositions`. For a section filler that is the
                           WRONG SIGN: the report builder writes one bullet per
                           heading whether or not a sentence was filed there,
                           and 34 of this file's 38 empty utterances do not
                           occur in the original report at all. Emptiness is
                           correct there, and a filler that DID produce
                           propositions is the defect.

    python3 GPT/precheck.py                       # jsonl/Prompt/test_reviewed
    python3 GPT/precheck.py --arm Prompt2
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for _p in (os.path.join(REPO, "Prompt2"), os.path.join(REPO, "Pipeline"), REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from vocabulary import (ANATOMY_ROLES, ANATOMY_SOURCES, ASSERTION_LABELS,   # noqa: E402
                        COMPARISON_LABELS, DESCRIPTOR_TYPES, ENTITY_TYPES,
                        LATERALITY, ZONES)
import validate as V                                                        # noqa: E402
from ontology import (DESCRIPTOR_LEXICON,                                   # noqa: E402
                      MODIFIER_LIFT_EXCEPTIONS,
                      NORMALITY_PREFIX_EXCEPTIONS)

# A bullet whose whole content is a generic no-content phrase. The report
# builder emits one per heading; it means "this section is empty", not "this
# region is normal". Kept identical in wording to Prompt2/system.py rule 2.
# 필러와 실질 음성("No pleural abnormalities")이 갈리는 지점이라 어휘로
# 못박는다. 필러의 표지는 **리포트에 대한 메타 술어**다 -- reported /
# specified / noted / applicable -- 이고, 해부나 소견을 명명하지 않는다.
META_PREDICATE = re.compile(
    r"\b(reported|specified|noted in this section|applicable|"
    r"documented|described)\b", re.I)

FILLER = re.compile(
    r"^(not applicable|no (other )?(significant |additional |gross |acute )?"
    r"(findings?|abnormalit(y|ies))( (noted|reported|specified))?|"
    r"no abdominal findings reported)\.?$", re.I)

# 패턴은 정밀도 우선으로 좁게 잡는다. 이 층의 지적에는 모델이 반박할 수
# 없고 -- "do not raise" 이므로 -- 오탐이 그대로 최종 출력까지 간다.
# 애매한 것은 잡지 않고 모델에게 남기는 편이 낫다. 아래 주석의 건수는
# jsonl/Prompt/test_reviewed.jsonl 에서 실제로 세어 본 값이다.
SIDE_PREFIX = re.compile(r"^(left|right|bilateral)_")
NORMAL_PREFIX = re.compile(r"^normal_")
# `_position$` 은 뺐다: appropriate_position / stable_position /
# expected_position / lateral_position / midline_position / similar_position
# 은 기구 끝 위치가 아니라 진짜 device_position 서술자다 (6개 라벨, 오탐).
# 남은 넷은 전부 "어디에" 를 라벨에 넣은 것이라 E2 위반이 확정적이다.
TIP_LABEL = re.compile(r"^tip_|^within_|^overlies_|^terminating_")
# 정도(severity) 접두/중위 패턴은 통째로 뺐다. 잡힌 2건이 둘 다 오탐이었다
# -- "small cell carcinoma" 는 병명이고 "large bowel" 은 장기 이름이다.
# 0건을 잡는 규칙과 2건을 틀리는 규칙 중에서는 전자가 낫다.

# 편측 접두가 라벨의 일부인 것들: 좌심방은 심방의 좌측형이 아니라 별개
# 구조이고, 좌우를 벗기면 다른 개념이 된다. ANATOMY 표의 implied 칸이
# 본래 이 질문에 답하는 자리이므로, 표가 아는 것은 표에 묻는다.
# "and" 가 개념의 일부인 것들. 떼면 다른 것이 된다.
AND_IS_THE_NAME = {
    "atrium_and_right_ventricle", "right_atrium_and_right_ventricle",
    "head_and_neck", "soft_tissues_and_osseous_structures",
}

# 수식어가 고유명의 일부인 것들. "median sternotomy" 는 정중선으로 한
# 흉골절개가 아니라 술식 이름이고, "small cell carcinoma" 는 작은 암이
# 아니다. 위에서 severity 접두 규칙을 통째로 뺀 이유가 이 둘이었는데,
# 규칙을 되살리는 대신 이름만 빼면 같은 오탐을 피하면서 나머지를 잡는다.
# normalize.py 는 이 표를 읽지 않는다 (MODIFIER_LIFT_EXCEPTIONS 와 별개).
MODIFIER_IS_THE_NAME = {
    "median_sternotomy", "small_cell_carcinoma", "non_small_cell_carcinoma",
    "large_bowel_loop", "large_bowel", "small_bowel_loop",
    # "No acute abnormality" 류는 판독문의 정형구다. "acute" 를 떼면
    # 남는 "abnormality" 가 원래 문장이 말한 것과 달라진다.
    "acute_abnormality", "acute_abnormalities", "acute_disease",
    "acute_process", "acute_cardiopulmonary_abnormality",
    "acute_cardiopulmonary_disease", "acute_cardiopulmonary_process",
    "acute_osseous_abnormality", "acute_intrathoracic_process",
}

SIDE_IS_THE_NAME = {
    "left_atrium", "right_atrium", "left_ventricle", "right_ventricle",
    "left_atrial_enlargement", "right_atrial_enlargement",
    "left_atrial_appendage", "left_main_bronchus", "right_main_bronchus",
    "left_heart_border", "right_heart_border", "left_cardiac_border",
    "right_cardiac_border", "left_hemithorax", "right_hemithorax",
    "right_middle_lobe", "left_lingula",
}

# The issue codes the model must NOT raise, because this file decides them.
# audit_records.py renders this into the prompt, so the two can never drift.
# rule 11 / Section 6A. 세 조건 전부 필드 조회와 어휘 매칭으로 끝나므로
# 모델에게 남길 이유가 없었다. 남겨 두었더니 지시가 충돌했다 -- precheck 가
# `qualified_negation_unwarned` 를 "이미 결정됨"으로 붙이면서, 같은 프롬프트가
# `bad_warning` 을 모델의 코드로 두고 판단 규칙까지 주고 있었다.
# 라벨된 표본이 이 집합을 넓혔다. "No ACUTE consolidation" 은 급성만 배제하고
# 만성은 남기므로 한정 부정인데, "acute" 가 chronicity 로 타입되어 걸리지
# 않았다 (표본에서 7건). rule 11 의 원문 목록보다 넓은 것이 맞다 -- 규칙은
# 타입 이름을 열거했지만, 실제로 부정을 한정하는 것은 "그 형태만 배제한다"는
# 성질이지 타입 이름이 아니다.
QUALIFYING_DESCRIPTORS = {"size", "severity", "extent", "distribution",
                          "number", "morphology", "chronicity"}
# "No NEW consolidation" 도 같다 -- 한정어가 descriptor 가 아니라
# comparison 에 들어가 있을 뿐이다 (표본에서 2건).
QUALIFYING_COMPARISONS = {"new"}
LOWER_BOUND = re.compile(r"\bat least\b|\bno less than\b|\bnot less than\b",
                         re.I)
ASSESSMENT_LIMITED = re.compile(
    r"\blimited\b|\bobscur|\bpoorly (assessed|seen|visualized)\b"
    r"|\bexcluded from the field of view\b|\bdifficult to assess\b"
    r"|\bsuboptimal\b|\bnot (well|fully) (seen|assessed|visualized)\b"
    r"|\bdegrad", re.I)

# 억제해도 되는 것과 안 되는 것은 정밀도가 아니라 **완전성**이 가른다.
# 억제란 "모델이 이 코드를 제기하지 마라" 이므로, 기계가 놓친 건은 아무도
# 못 잡게 된다. 그래서 필드 조회·스팬 대조·표 조회처럼 빠짐없이 도는 검사만
# 억제하고, 문장을 추정하는 휴리스틱 검사는 보여주기만 한다 -- 그쪽은 모델이
# 안전망이다. (라벨된 표본의 정밀도를 괄호에 적어 둔다. 낮은 정밀도는 그
# 검사를 고칠 이유이지, 억제 여부를 정하는 기준이 아니다.)
SUPPRESSED = {
    "span_grounding":   "quoted text/cue is a contiguous span of the utterance",
    "enum_range":       "every closed field is inside its vocabulary",
    "source_text":      "anatomy.text is null exactly when source is not "
                        "'utterance'",
    "derived_from":     "derived_from names a proposition in the same utterance",
    "overspecified":    "a label carrying side (left_lower_lobe), normality "
                        "(normal_heart_size) or where a device ends "
                        "(tip_in_mid_svc) -- NOT a label that merely names a "
                        "region finely, which is granularity and correct",
    "section_filler":   "a section filler is empty, and an empty utterance is "
                        "a filler",
    "chronicity_comparison_duplicated":
                        "the same token written as comparison.cue and as a "
                        "chronicity descriptor at once",
    # -- validate.py 쪽에서 넘어오는 것들 중 결정적인 것
    "entity_text_not_in_utterance":
                        "entity.text is not a span of the utterance (1.00)",
    "anatomy_source_carries_span":
                        "anatomy.text is set while source says the clause did "
                        "not name the structure (1.00)",
    "anatomy_span_is_side_only":
                        "anatomy.text is a bare side word, which names no "
                        "structure (1.00)",
    "laterality_contradicts_label":
                        "the label's implied side and the laterality field "
                        "disagree (1.00)",
    "warnings":         "the three warning conditions -- qualified negation, "
                        "qualified assertion (a lower bound), assessment "
                        "limited -- are decided by field lookup and word "
                        "match. (Only the missing direction: whether an "
                        "existing warning is warranted is NOT decided "
                        "mechanically.)",
}


# 보여주기만 하고 억제하지 않는 것. 기계가 문장을 추정하는 검사들이라
# 빠뜨리는 건이 있고, 그 자리를 모델이 메운다.
ADVISORY = {
    "no_propositions":          "0.77",
    "device_tip_not_located":   "0.80",
    "anatomy_span_is_relative": "표본 1건",
    "hedge_cue_on_present":     "0.50",
    "normal_state_as_absence":  "표본 2건",
    "should_be_one_proposition": "0.50",
    "coordination_not_split":   "0.00",
    "section_conflict":         "0.00 -- info 로 강등",
    # 2026-09-17 신설. 억제하는 층에 두지 않는 이유는 위 SIDE_PREFIX 주석과
    # 같다 -- 고유명을 수식어로 오독할 여지가 남아 있고, 그 판단은 문장을
    # 읽어야 갈린다. 여기 두면 모델이 반박할 수 있다.
    # 설명은 SUPPRESSED 에 두면 안 된다 -- 그 표가 곧 "do not raise" 목록이라
    # 모델이 반박할 수 없게 된다. 이 검사는 고유명을 수식어로 오독할 여지가
    # 남아 있어 반박 가능해야 한다.
    "modifier_only_in_label":   "미측정 -- goldset 시트로 셀 것",
}


def load(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        for rec in doc.get("records", []):
            rec.setdefault("propositions", [])
            rec.setdefault("warnings", [])
            rec["report_id"] = doc["id"]
            out.append(rec)
    return out


# 라벨이 이미 "그 상대 위치 자체"인 구역명. 이런 라벨에는 role=site 가 맞다.
_REGION_SUFFIX = ("_region", "_space", "_area", "_recess", "_gutter",
                  "_angle", "_junction")


def _region_label(rec, item) -> bool:
    pid = item.get("proposition")
    for p in rec.get("propositions") or []:
        if pid and p["id"] != pid:
            continue
        for a in p.get("anatomy") or []:
            lab = a.get("label") or ""
            if a.get("role") == "site" and lab.endswith(_REGION_SUFFIX):
                return True
    return False


def _add(out, code, pid, msg, severity="warning"):
    out.append({"code": code, "proposition": pid, "message": msg,
                "severity": severity, "by": "precheck"})


def _flag_modifier_only_in_label(found: list, pid: str, lab: str,
                                 p: dict) -> None:
    if (not lab or lab in MODIFIER_IS_THE_NAME
            or lab in MODIFIER_LIFT_EXCEPTIONS
            or lab in NORMALITY_PREFIX_EXCEPTIONS):
        return
    have = {(d.get("label") or "") for d in (p.get("descriptors") or [])}
    toks = lab.split("_")
    # 두 낱말 접두를 먼저 본다: "ill_defined_opacity" 는 "ill" 이 아니다.
    for n in (2, 1):
        if len(toks) <= n:
            continue
        pre, base = "_".join(toks[:n]), "_".join(toks[n:])
        hit = (DESCRIPTOR_LEXICON.get(pre)
               or DESCRIPTOR_LEXICON.get(pre.replace("_", " ")))
        if not hit or len(base) < 3:
            continue
        if hit[1] in have or pre in have:
            return                      # 이미 기록됨 -- lift 의 일이지 결함이 아니다
        _add(found, "modifier_only_in_label", pid,
             f"entity.label '{lab}' 의 '{pre}' 는 {hit[0]} 서술자인데 "
             f"descriptors 에 없다 -- 라벨 안에만 있다")
        return


def check_record(rec: dict) -> list:
    """Every mechanical finding for one utterance, from both layers."""
    found = []

    # -- layer 1: the existing validator, minus the filler sign error
    is_filler = bool(FILLER.match((rec.get("utterance") or "").strip()))
    try:
        res = V.validate_record(rec)
        items = res["findings"] if isinstance(res, dict) and "findings" in res \
            else (res if isinstance(res, list) else [])
    except Exception as exc:                                  # noqa: BLE001
        items = []
        _add(found, "validator_crashed", None, str(exc)[:160], "error")
    for it in items:
        if it["code"] == "no_propositions" and is_filler:
            continue        # 극성이 반대다 -- 필러는 비는 것이 맞다
        if it["code"] == "qualified_negation_unwarned":
            continue        # 아래 `warnings` 가 세 조건을 통째로 가진다;
                            # 한 결함이 두 코드로 나오면 건수가 거짓이 된다
        if it["code"] == "anatomy_span_is_relative" and _region_label(rec, it):
            # 표본 4/5 가 오탐. "No free air below the right hemidiaphragm"
            # 의 free air 는 실제로 횡격막하 공간에 있으므로
            # subdiaphragmatic_region + role=site 가 맞다. 이 검사는 결과
            # 라벨이 아니라 전치사 "below" 라는 표면형에 반응했다. 라벨이
            # 이미 그 상대 위치를 담은 구역명이면 relative_location 이
            # 아니다.
            continue
        if it["code"] == "section_conflict":
            # 표본 16/16 이 오탐. 이 검사의 메시지 자체가 "the utterance
            # stands" 라고 인정한다 -- 상류 SRRG 의 섹션 배정과 발화가
            # 어긋난다는 관찰이지, 구조화가 틀렸다는 판정이 아니다.
            # 지우지는 않는다. 상류 품질의 지표로는 값이 있다. 결함 집계
            # 에서 빼기 위해 severity 만 info 로 낮춘다.
            found.append({**it, "severity": "info", "by": "validate.py"})
            continue
        found.append({**it, "by": "validate.py"})

    # -- layer 2: what the validator does not look at
    if is_filler and rec["propositions"]:
        _add(found, "section_filler", None,
             "섹션 필러인데 proposition 이 생성되었다 -- 없는 음성 소견을 "
             "만들어낸다", "error")

    # -- warnings: 세 조건은 전부 기계적이다
    warns = rec.get("warnings") or []
    utt = rec.get("utterance") or ""
    owed = {}
    for p in rec["propositions"]:
        if (p.get("assertion") or {}).get("label") == "absent" and (
                any(d.get("type") in QUALIFYING_DESCRIPTORS
                    for d in p.get("descriptors") or [])
                or (p.get("comparison") or {}).get("label")
                in QUALIFYING_COMPARISONS):
            owed.setdefault("Qualified negation:", p["id"])
    if LOWER_BOUND.search(utt):
        owed.setdefault("Qualified assertion:", None)
    if ASSESSMENT_LIMITED.search(utt):
        owed.setdefault("Assessment limited:", None)
    for prefix, pid in owed.items():
        if not any(w.startswith(prefix) for w in warns):
            _add(found, "warnings", pid,
                 f"'{prefix}' 로 시작하는 경고가 필요한데 없다")

    # 반대 방향 -- "조건이 성립하지 않는데 경고가 있다" -- 은 넣었다가 뺐다.
    # 라벨된 표본에서 정밀도 0.06 (1/17). 한 코드 안에서 방향이 갈렸고
    # ("필요한데 없음" 은 13/13 = 1.00), 합치면 0.47 이 되어 둘 다 못 쓰게
    # 된다. 사람이 쓴 경고가 내 트리거 목록에 없다는 것은 대개 목록이 좁다는
    # 뜻이지 경고가 틀렸다는 뜻이 아니었다 -- "definite" 가 type=other 로
    # 타입되어 안 걸리는 식이다. 어휘를 다 열거할 수 있게 되기 전까지 이
    # 방향은 기계가 결정할 수 없다.

    # 같은 토큰이 comparison.cue 와 chronicity 서술자 양쪽에 있는 것.
    # 이것이 "persistent" 의 진짜 결함이다 -- 어느 필드냐가 아니라 둘 다냐.
    for p in rec["propositions"]:
        cue = ((p.get("comparison") or {}).get("cue") or "").strip().lower()
        if not cue:
            continue
        for d in p.get("descriptors") or []:
            if (d.get("type") == "chronicity"
                    and (d.get("text") or "").strip().lower() == cue):
                _add(found, "chronicity_comparison_duplicated", p["id"],
                     f"'{d['text']}' 가 comparison.cue 와 chronicity 서술자 "
                     f"양쪽에 있다 -- 한 사실은 한 자리에")

    ids = {p["id"] for p in rec["propositions"]}
    for p in rec["propositions"]:
        pid = p["id"]
        df = p.get("derived_from")
        if df and df not in ids:
            _add(found, "derived_from", pid,
                 f"derived_from '{df}' 가 이 발화에 없다", "error")

        ent = p.get("entity") or {}
        if ent.get("type") not in ENTITY_TYPES:
            _add(found, "enum_range", pid, f"entity.type '{ent.get('type')}'", "error")
        if (p.get("assertion") or {}).get("label") not in ASSERTION_LABELS:
            _add(found, "enum_range", pid, "assertion.label", "error")
        if (p.get("comparison") or {}).get("label") not in COMPARISON_LABELS:
            _add(found, "enum_range", pid, "comparison.label", "error")

        lab = ent.get("label") or ""
        if SIDE_PREFIX.match(lab) and lab not in SIDE_IS_THE_NAME:
            _add(found, "overspecified", pid,
                 f"entity.label '{lab}' 이 편측을 품는다 (E1)")
        # bad_split 로 잡히던 것 중 진짜 결함은 이쪽이었다: 라벨이 두 구조를
        # 미리 붙여 하나로 만든 것(cardiac_and_mediastinal_contours). 부위는
        # anatomy 가 두 항목으로 이미 나눠 담고 있으므로 라벨이 또 담을 일이
        # 아니다. 해부학 고유명에 든 "and" 는 제외한다.
        if "_and_" in lab and lab not in AND_IS_THE_NAME:
            _add(found, "overspecified", pid,
                 f"entity.label '{lab}' 이 두 구조를 라벨에 붙여 담았다 -- "
                 f"anatomy 항목이 질 일이다")
        if (NORMAL_PREFIX.match(lab)
                and lab not in NORMALITY_PREFIX_EXCEPTIONS
                and lab not in MODIFIER_LIFT_EXCEPTIONS):
            _add(found, "overspecified", pid,
                 f"entity.label '{lab}' 이 정상성을 품는다 (E3)")

        # 수식어가 라벨 안에만 있고 descriptor 로는 기록되지 않은 것.
        # lift_modifier_prefix 가 일부러 손대지 않는 여집합이다 -- 그쪽은
        # "이미 descriptor 에 있으면 라벨에서 뗀다" 이고, 여기는 "descriptor
        # 에 없으니 뗄 수 없다" 는 쪽이라 고칠 곳이 추출이다.
        _flag_modifier_only_in_label(found, pid, lab, p)

        for a in p.get("anatomy") or []:
            for field, space in (("laterality", LATERALITY), ("role", ANATOMY_ROLES),
                                 ("source", ANATOMY_SOURCES), ("zone", ZONES)):
                if a.get(field) not in space:
                    _add(found, "enum_range", pid,
                         f"anatomy.{field} '{a.get(field)}'", "error")
            if (SIDE_PREFIX.match(a.get("label") or "")
                    and a.get("label") not in SIDE_IS_THE_NAME):
                _add(found, "overspecified", pid,
                     f"anatomy.label '{a['label']}' 이 편측을 품는다 (E1)")

        for d in p.get("descriptors") or []:
            if d.get("type") not in DESCRIPTOR_TYPES:
                _add(found, "enum_range", pid,
                     f"descriptor.type '{d.get('type')}'", "error")
            if TIP_LABEL.search(d.get("label") or ""):
                _add(found, "overspecified", pid,
                     f"descriptor '{d['label']}' 이 기구 끝 위치를 품는다 "
                     f"-- anatomy.role=tip_location 의 일이다 (E2)")
    return found


def run(recs: list) -> dict:
    return {r["utterance_id"]: check_record(r) for r in recs}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", default="Prompt")
    ap.add_argument("--split", default="test_reviewed")
    ap.add_argument("--out", default=None,
                    help="default: out/gpt_records/<arm>/")
    a = ap.parse_args()
    if not a.out:
        a.out = os.path.join(REPO, "out", "gpt_records", a.arm)

    src = os.path.join(REPO, "jsonl", a.arm, f"{a.split}.jsonl")
    recs = load(src)
    res = run(recs)
    os.makedirs(a.out, exist_ok=True)

    path = os.path.join(a.out, "precheck.jsonl")
    byrec = {r["utterance_id"]: r for r in recs}
    with open(path, "w", encoding="utf-8") as fh:
        for uid, items in res.items():
            if not items:
                continue
            r = byrec[uid]
            fh.write(json.dumps({"report_id": r["report_id"],
                                 "utterance_id": uid,
                                 "section": r["section"],
                                 "utterance": r["utterance"],
                                 "findings": items}, ensure_ascii=False) + "\n")

    c = collections.Counter(i["code"] for v in res.values() for i in v)
    by = collections.Counter(i["by"] for v in res.values() for i in v)
    dirty = sum(1 for v in res.values() if v)
    L = [f"# 기계 사전검증 — jsonl/{a.arm}/{a.split}.jsonl\n",
         f"발화 {len(recs):,}건 중 **{dirty:,}건**에 기계적 지적 "
         f"{sum(c.values()):,}건. 나머지 {len(recs) - dirty:,}건은 "
         f"기계가 볼 수 있는 한 깨끗합니다.\n",
         "이 지적들은 **모델에게 묻지 않습니다.** 판정자는 읽어야만 알 수 있는 "
         "것에만 집중합니다.\n",
         f"\n| 출처 | 건수 |", "|---|---|"]
    for k, n in by.most_common():
        L.append(f"| {k} | {n} |")
    L += ["\n| 코드 | 건수 |", "|---|---|"]
    for k, n in c.most_common():
        L.append(f"| {k} | {n} |")
    p = os.path.join(a.out, "precheck.md")
    open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"[ok] {path}\n[ok] {p}", file=sys.stderr)
    print(f"[info] {dirty}/{len(recs)} 발화에 지적, 총 {sum(c.values())}건",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
