#!/usr/bin/env python3
"""jsonl/Prompt (the v1 arm) -> the defect cases, as one md a clinician can read.

Read-only, and no model: every case here was found by a scan over the file,
so the same command reproduces the same list. The GPT audit in GPT/ is what
suggested where to look; the counts are this script's.

    python3 Verify/tools/defect_cases.py
    python3 Verify/tools/defect_cases.py --arm Prompt2 --out docs/X.md

Each group carries the question it is asking, because the groups do not want
the same kind of answer: some are already decided and only need confirming,
one needs a radiologist, and one is a false alarm kept so it is not re-raised.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRRG = "/data3/CXR/SRRG/srrg_findings_csv/{split}.csv"

PLACEHOLDER = re.compile(
    r"^(not applicable|no (other )?(significant |additional |gross |acute )?"
    r"(findings?|abnormalit(y|ies))( (noted|reported|specified))?|"
    r"no abdominal findings reported)\.?$", re.I)
QUALITY = re.compile(r"rotat|study quality|image quality", re.I)
LIMIT = re.compile(r"limited assessment|assessment .{0,12}limited|poorly assessed"
                   r"|obscur|difficult to assess|degrad", re.I)
IN_PLACE = ("in place", "in situ", "in position")
TIPLIKE = re.compile(r"^(tip|tips|side_port|distal_end|loops|within|overlies|"
                     r"projecting|terminating)|_position$")
CHANGE_ADV = {"grossly", "markedly", "marked", "significant", "significantly",
              "substantially", "substantial", "essentially", "slight",
              "slightly", "minimally"}
INHERENT_BILATERAL = {"lungs", "pleura", "lung_bases", "lung_apices", "hila",
                      "ribs", "clavicles", "costophrenic_angles", "diaphragm",
                      "hemidiaphragms", "lung_fields", "chest_wall",
                      "pulmonary_vasculature", "lung_interstitium",
                      "lung_parenchyma", "airspaces"}


def load(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        for rec in doc.get("records", []):
            rec = dict(rec)
            rec["report_id"] = doc["id"]
            out.append(rec)
    return out


def originals(split):
    path = SRRG.format(split=split)
    if not os.path.exists(path):
        print(f"[warn] {path} 없음 -- 원본 대조를 건너뜁니다", file=sys.stderr)
        return {}
    csv.field_size_limit(10 ** 7)
    return {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}


def norm(t):
    return re.sub(r"\s+", " ", t or "").strip().lower()


# --------------------------------------------------------------- the scans

def group_placeholder(recs, orig):
    """proposition 0개인 발화 -- 자리표시자인가, 진짜 정상 진술인가."""
    out = []
    for r in recs:
        if r["propositions"]:
            continue
        u = r["utterance"]
        in_orig = norm(u).rstrip(".") in norm(
            (orig.get(r["report_id"]) or {}).get("original_report", ""))
        if QUALITY.search(u):
            kind = "촬영품질"
        elif LIMIT.search(u):
            kind = "판독제한"
        elif PLACEHOLDER.match(u.strip()):
            kind = "자리표시자"
        elif re.search(r"unchanged|interval change", u, re.I):
            kind = "비교만"
        else:
            kind = "기타"
        out.append({"kind": kind, "in_orig": in_orig, "rec": r})
    return out


def group_in_place(recs):
    out = []
    for r in recs:
        for p in r["propositions"]:
            cue = norm(p["assertion"].get("cue"))
            has_d = [d for d in p["descriptors"] if d["label"] == "in_place"]
            if any(h in cue for h in IN_PLACE):
                out.append({"where": "중복" if has_d else "assertion.cue",
                            "rec": r, "p": p, "cue": cue})
            elif (any(h in norm(r["utterance"]) for h in IN_PLACE)
                  and not has_d and p["entity"]["type"] == "device"):
                out.append({"where": "사라짐", "rec": r, "p": p, "cue": ""})
    return out


def group_tip(recs):
    out = []
    for r in recs:
        for p in r["propositions"]:
            roles = {a["role"] for a in p["anatomy"]}
            for d in p["descriptors"]:
                if d["type"] == "device_position" and TIPLIKE.search(d["label"]):
                    out.append({"rec": r, "p": p, "d": d,
                                "dup": "tip_location" in roles})
    return out


def group_adverb(recs):
    """부사가 비교 단어에 실제로 붙어 있을 때만 잡는다.

    "Slight blunting of the costophrenic angle, stable" 의 "Slight" 는 문장
    맨 앞에 있고 blunting 을 꾸민다 -- 같은 문장에 stable 이 있다는 것만으로
    잡으면 오탐이다. 부사와 비교 단어가 원문에서 **맞붙어 있을 때**만 부사가
    변화를 꾸민 것이다.
    """
    CHANGE_WORD = (r"improv|worsen|increas|decreas|chang|stable|unchanged"
                   r"|larger|smaller|reduc|progress|resol")
    out = []
    for r in recs:
        u = norm(r["utterance"])
        for p in r["propositions"]:
            if p["comparison"]["label"] == "none":
                continue
            for d in p["descriptors"]:
                if d["type"] not in ("severity", "extent"):
                    continue
                w = (norm(d["text"]).split() or [""])[0]
                if w not in CHANGE_ADV:
                    continue
                # 부사 바로 뒤(사이에 한 단어까지 허용)에 변화 단어가 오는가
                if re.search(rf"\b{re.escape(w)}\b(\s+\w+)?\s+\w*(?:{CHANGE_WORD})", u):
                    out.append({"rec": r, "p": p, "d": d})
    return out


def group_persistent(recs):
    """한 토큰이 comparison.cue 와 chronicity 서술자 양쪽에 있는 것.

    2026-09-15 정정. 이 묶음은 원래 "`persistent` 를 comparison 으로 읽은
    것이 틀렸다" 였다. 라벨된 표본이 17/17 로 그 판정을 뒤집었다 -- 흉부
    영상에서 `persistent` 는 이전 검사 대비 지속을 말하는 변화 서술자이고,
    `comparison=stable` 이 맞다. 결함은 어느 필드냐가 아니라 **둘 다**라는
    것이었다. 여기서는 중복만 센다.
    """
    out = []
    for r in recs:
        for p in r["propositions"]:
            cue = norm(p["comparison"].get("cue"))
            if not cue:
                continue
            for d in p["descriptors"]:
                if d["type"] == "chronicity" and norm(d["text"]) == cue:
                    out.append({"rec": r, "p": p, "d": d})
    return out


def group_persistent_no_comparison(recs):
    """`persistent` 가 만성도 서술자로만 있고 비교가 비어 있는 것.

    C-4 의 반대편이다. 같은 규칙("persistent 는 변화 서술자")을 적용하면
    이쪽은 비교가 통째로 빠진 것이 된다. 문장이 다른 비교어를 따로 말한
    경우(improved/worsened/stable)는 제외한다 -- 그때는 `persistent` 를
    서술자로 남긴 것이 방어 가능하다.
    """
    out = []
    for r in recs:
        for p in r["propositions"]:
            if p["comparison"]["label"] != "none":
                continue
            if norm(p["comparison"].get("cue")):
                continue
            for d in p["descriptors"]:
                if d["label"] == "persistent":
                    out.append({"rec": r, "p": p, "d": d})
    return out


NATURALLY_BILATERAL = {"pleura", "lungs", "hila", "ribs", "lung_bases",
                       "pulmonary_vasculature", "lung_interstitium",
                       "lung_parenchyma", "airspaces", "chest_wall",
                       "clavicles", "costophrenic_angles", "lung_apices",
                       "lung_fields", "pleural_sinuses"}


def group_schema(recs):
    """스키마가 스스로 모순인 자리 -- 프롬프트로는 절대 안 잡힌다.

    본래 양측인 구조에 `bilateral` 과 `unspecified` 가 둘 다 합법이면, 둘 다
    통과하고 둘 다 기록된다. 그러면 이 필드는 하류에서 아무것도 못 싣는다.
    """
    t = collections.defaultdict(collections.Counter)
    for r in recs:
        for p in r["propositions"]:
            for a in p["anatomy"]:
                if a["label"] in NATURALLY_BILATERAL:
                    t[a["label"]][a["laterality"]] += 1
    return t


def group_bilateral(recs):
    """GPT 가 지적했으나 오탐으로 본 것 -- 재확인용으로 남긴다."""
    cue = re.compile(r"\b(bilateral|bilaterally|both|bibasilar|biapical|either"
                     r"|lungs|each)\b", re.I)
    out = []
    for r in recs:
        for p in r["propositions"]:
            for a in p["anatomy"]:
                if (a["laterality"] == "bilateral"
                        and a["label"] not in INHERENT_BILATERAL
                        and not cue.search(r["utterance"])):
                    out.append({"rec": r, "p": p, "a": a})
    return out


# -------------------------------------------------------------- rendering

def pjson(p):
    keep = {"entity": p["entity"],
            "anatomy": [{k: v for k, v in a.items() if v is not None}
                        for a in p["anatomy"]],
            "descriptors": p["descriptors"],
            "assertion": p["assertion"],
            "comparison": p["comparison"]}
    return json.dumps(keep, ensure_ascii=False)


def case(r, p=None, note=""):
    out = [f"- `{r['utterance_id']}`  ({r['section']})",
           f"  - 원문: **{r['utterance']}**"]
    if note:
        out.append(f"  - {note}")
    if p is not None:
        out.append(f"  - 현재 JSON: `{pjson(p)}`")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="Prompt")
    ap.add_argument("--split", default="test_reviewed")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-cases", type=int, default=12,
                    help="md 에 펼쳐 보일 사례 수; 나머지는 tsv 로만")
    a = ap.parse_args()

    src = os.path.join(REPO, "jsonl", a.arm, f"{a.split}.jsonl")
    recs = load(src)
    orig = originals(a.split)
    nprop = sum(len(r["propositions"]) for r in recs)

    ph = group_placeholder(recs, orig)
    ip = group_in_place(recs)
    tp = group_tip(recs)
    ad = group_adverb(recs)
    ps = group_persistent(recs)
    pn = group_persistent_no_comparison(recs)
    bl = group_bilateral(recs)

    L = []
    W = L.append
    W(f"# `jsonl/{a.arm}/{a.split}.jsonl` — 검수가 필요한 지점\n")
    W(f"> 생성: `python3 Verify/tools/defect_cases.py --arm {a.arm}` · "
      f"대상 발화 {len(recs):,}개 / proposition {nprop:,}개\n")
    W("""이 문서는 **고쳐야 할 목록이 아니라, 판단이 필요한 목록**입니다.
모델을 부르지 않고 파일 전체를 훑어서 뽑았으므로 건수는 표본이 아니라 전수입니다.

각 묶음은 **원하는 답의 종류가 다릅니다.**

| 묶음 | 무엇을 물어보나 | 누가 답하나 |
|---|---|---|
| **A. 자리표시자** | 원본에 없는 문장을 비워둔 것이 맞나 | 의사 |
| **B. 판독 신뢰도** | 담을 칸이 없는데 어떻게 할 것인가 | 의사 + 설계 |
| **C. 확정된 결함** | 고치는 방향이 맞는지 확인만 | 개발자 |
| **D. 오탐** | 정말 문제가 아닌지 재확인 | 의사 |

**A 와 B 는 임상 판단입니다. C 는 이미 고쳤고 확인만 받으면 됩니다.**
""")

    # ---- A
    fillers = [x for x in ph if x["kind"] == "자리표시자"]
    real = [x for x in ph if x["kind"] not in ("자리표시자", "촬영품질", "판독제한")]
    no_orig = [x for x in fillers if not x["in_orig"]]
    W("\n---\n\n## A. 섹션 자리표시자 — %d건\n" % len(fillers))
    W(f"""**질문: 이 문장들을 proposition 없이 비워둔 현재 동작이 맞습니까?**

리포트 작성기가 **문장이 배정되지 않은 섹션에도 제목마다 한 줄씩** 채워 넣습니다.
{len(no_orig)}/{len(fillers)}건은 원본 판독문(`original_report`)에 그 문장이 실재하지 않습니다.

핵심은 이 한 줄의 뜻이 둘 중 무엇이냐입니다.

| 해석 | 결과 |
|---|---|
| "이 부위를 보았고 정상이다" | 음성 소견으로 기록해야 함 |
| **"이 섹션에 배정된 문장이 없다"** | 비워두어야 함. 기록하면 없는 음성 소견을 만들어냄 |

아래가 후자를 뒷받침하는 사례입니다. **판단해 주셔야 할 핵심 근거입니다.**
""")
    # 반례 찾기: 자리표시자가 있는데 같은 리포트에 해당 부위 소견이 실재
    ce = []
    bysec = collections.defaultdict(list)
    for r in recs:
        bysec[(r["report_id"], r["section"])].append(r)
    for x in fillers:
        r = x["rec"]
        o = (orig.get(r["report_id"]) or {}).get("original_report", "")
        # 단어 경계를 요구한다. "retrocardiac" 은 후폐야 음영이지 심장 소견이
        # 아니고, 이 표는 판단의 핵심 근거라 한 건의 오탐도 비싸다.
        key = {"Pleura": r"\bpneumothorax|\beffusion|\bpleural\b",
               "Cardiovascular": r"\bcardiomegaly\b|\bheart\b"
                                 r"|(?<!retro)(?<!mediastino)\bcardiac\b",
               "Abdominal": r"\bbowel\b|\babdomen\b|\babdominal\b",
               "Musculoskeletal and Chest Wall": r"\brib\b|\bribs\b|\bfracture"
                                                 r"|\bspine\b|\bsternot"}.get(r["section"])
        if key and re.search(key, o, re.I):
            ce.append((r, re.findall(r"[^.\n]*(?:%s)[^.\n]*" % key, o, re.I)[:1]))
    W(f"### A-1. 반례 — 자리표시자가 붙은 섹션에 원본은 소견을 적어 두었다 ({len(ce)}건)\n")
    W("이 경우 자리표시자를 \"정상\"으로 읽으면 **임상적으로 거짓인 음성 소견**이 됩니다.\n")
    for r, snip in ce[:a.max_cases]:
        W(f"- `{r['report_id']}` · 섹션 **{r['section']}**")
        W(f"  - 구조화본: “{r['utterance']}”")
        W(f"  - 원본 판독문: “{(snip[0].strip() if snip else '')[:160]}”")
    if len(ce) > a.max_cases:
        W(f"\n(외 {len(ce) - a.max_cases}건 — tsv 참조)")

    W(f"\n### A-2. 자리표시자 전체 문구 ({len(fillers)}건)\n")
    W("| 문구 | 건수 | 섹션 |")
    W("|---|---|---|")
    grp = collections.defaultdict(list)
    for x in fillers:
        grp[x["rec"]["utterance"]].append(x["rec"]["section"])
    for u, secs in sorted(grp.items(), key=lambda kv: -len(kv[1])):
        W(f"| {u} | {len(secs)} | {', '.join(sorted(set(secs)))} |")

    if real:
        W(f"\n### A-3. 자리표시자가 **아닌데** 비어 있는 것 ({len(real)}건) — 누락일 수 있습니다\n")
        for x in real:
            W("\n".join(case(x["rec"], note=(
                "원본 판독문에 실재함" if x["in_orig"] else "원본에 없음"))))

    # ---- B
    q = [x for x in ph if x["kind"] in ("촬영품질", "판독제한")]
    lim_all = [r for r in recs if LIMIT.search(r["utterance"]) or QUALITY.search(r["utterance"])]
    W(f"\n---\n\n## B. 판독 신뢰도 — {len(lim_all)}건 (그중 {len(q)}건은 통째로 비어 있음)\n")
    W("""**질문: "이 판독을 얼마나 믿을 수 있나"를 데이터에 남길 것입니까? 남긴다면 어디에?**

"환자가 회전되어 있다", "심장 평가가 제한적이다" 는 **환자의 상태가 아니라 사진의 상태**입니다.
지금 스키마에는 이걸 담을 축이 없어서, 부위·소견·정상 어디에도 들어가지 않습니다.
**빠뜨리면 불확실한 소견이 확실해 보입니다.**
""")
    for r in lim_all[:a.max_cases]:
        W("\n".join(case(r, r["propositions"][0] if r["propositions"] else None,
                         note=("**현재 완전히 비어 있음**" if not r["propositions"] else ""))))
    if len(lim_all) > a.max_cases:
        W(f"\n(외 {len(lim_all) - a.max_cases}건 — tsv 참조)")

    # ---- C
    W("\n---\n\n## C. 확정된 결함 — 고치는 방향까지 정해진 것\n")
    W("""이 넷은 임상 판단이 필요 없습니다. **방향이 맞는지만 봐 주시면 됩니다.**
괄호 안은 `Prompt2` 팔에서 같은 스캔을 돌린 결과입니다.
""")
    ipc = collections.Counter(x["where"] for x in ip)
    W(f"\n### C-1. 기구가 “제자리에 있다”가 엉뚱한 칸으로 — {len(ip)}건\n")
    W(f"`assertion.cue` {ipc['assertion.cue']}건 · 이중기록 {ipc['중복']}건 · "
      f"아예 사라짐 {ipc['사라짐']}건\n")
    W("“in place / in situ / in position” 은 **기구가 어떻게 놓여 있는지**를 말하는 "
      "`device_position` descriptor 인데, "
      "“기구가 있다”는 판정의 근거 단어(`assertion.cue`)로 들어갔습니다.\n")
    for x in ip[:a.max_cases]:
        W("\n".join(case(x["rec"], x["p"], note=f"현재 위치: **{x['where']}**")))
    if len(ip) > a.max_cases:
        W(f"\n(외 {len(ip) - a.max_cases}건 — tsv 참조)")

    W(f"\n### C-2. 기구 끝 위치가 라벨 안에 박힘 — {len(tp)}건 "
      f"(그중 {sum(1 for x in tp if x['dup'])}건은 제 칸에도 이미 있어 중복)\n")
    W("`ONTOLOGY_SPEC_V2.md` 의 **E2 결정** 위반입니다. 끝 위치는 "
      "`anatomy.role=\"tip_location\"` 이 집니다.\n")
    for x in tp[:a.max_cases]:
        W("\n".join(case(x["rec"], x["p"],
                         note=f"문제 라벨: `{x['d']['label']}`"
                              f"{' · 같은 내용이 anatomy 에도 있음' if x['dup'] else ''}")))
    if len(tp) > a.max_cases:
        W(f"\n(외 {len(tp) - a.max_cases}건 — tsv 참조)")

    W(f"\n### C-3. 변화를 꾸미는 부사를 소견의 정도로 읽음 — {len(ad)}건\n")
    W("“Marked improvement” 의 *marked* 는 **개선의 정도**지 부종이 심하다는 뜻이 "
      "아닙니다. 소견의 severity 로 기록하면 없는 중증도를 만들어냅니다.\n")
    for x in ad[:a.max_cases]:
        W("\n".join(case(x["rec"], x["p"],
                         note=f"문제 descriptor: `{x['d']['text']}` → "
                              f"{x['d']['type']}/{x['d']['label']} "
                              f"(comparison={x['p']['comparison']['label']})")))
    if len(ad) > a.max_cases:
        W(f"\n(외 {len(ad) - a.max_cases}건 — tsv 참조)")

    W(f"\n### C-4. 같은 단어가 두 칸에 동시에 들어감 — {len(ps)}건\n")
    W("""`Persistent` 하나가 **`comparison` 의 근거 단어이면서 동시에
`descriptors` 의 만성도 항목**으로도 기록되어 있습니다. 한 사실이 두 자리를
차지한 것이고, 두 자리에 있으면 반드시 어긋납니다 — E1 편측성 모순 2,266건과
똑같은 구조입니다.

> **2026-09-15 정정.** 이 항목은 원래 "`persistent` 를 비교로 읽은 것이
> 틀렸다"고 적혀 있었습니다. **그 판정이 틀렸습니다.** 표본 17건을 라벨링한
> 결과 **17건 전부가 오탐**이었습니다 — 흉부 영상에서 `persistent` 는 이전
> 검사 대비 지속을 뜻하는 변화 서술자이므로 `comparison=stable` 이 맞습니다.
> 그에 따라 `ontology.py` 와 `Prompt2/system.py` 의 관련 수정도 되돌렸고,
> 여기서는 **중복만** 셉니다.

분포가 이 판단을 뒷받침합니다.

| `persistent` 가 놓인 자리 | 건수 |
|---|---|
| **comparison + descriptor 양쪽 (결함)** | **17** |
| comparison 만 (올바름) | 1 |
| descriptor 만 (비교가 누락된 쪽) | 11 |

고칠 방향은 **만성도 서술자를 지우고 `comparison` 을 남기는 것**입니다.
""")
    for x in ps[:a.max_cases]:
        W("\n".join(case(x["rec"], x["p"],
                         note=f"중복된 단어: `{x['d']['text']}` — "
                              f"comparison.cue 이면서 chronicity 서술자")))
    if len(ps) > a.max_cases:
        W(f"\n(외 {len(ps) - a.max_cases}건 — tsv 참조)")

    W(f"\n### C-5. 반대편 — 비교가 통째로 빠짐 — {len(pn)}건\n")
    W("""C-4 와 같은 규칙의 반대 결과입니다. `persistent` 가 만성도 서술자로만
들어가고 `comparison` 은 `none` 입니다. `persistent` 가 변화 서술자라면
이쪽은 **이전 검사 대비 지속이라는 정보가 통째로 사라진** 것입니다.

문장이 다른 비교어(`improved`/`worsened`)를 따로 말한 경우는 뺐습니다 —
그때는 `persistent` 를 서술자로 남긴 것이 방어 가능합니다.
""")
    for x in pn[:a.max_cases]:
        W("\n".join(case(x["rec"], x["p"],
                         note="comparison 이 none — stable 이어야 하는가?")))
    if len(pn) > a.max_cases:
        W(f"\n(외 {len(pn) - a.max_cases}건 — tsv 참조)")

    # ---- D
    W(f"\n---\n\n## D. 오탐으로 판단한 것 — {len(bl)}건\n")
    W("""**질문: 정말 문제가 아닌지 확인 부탁드립니다.**

GPT 감사가 “원문이 양측이라고 말하지 않았는데 `laterality: bilateral`” 이라고
여러 건 지적했습니다. 확인해 보니 대부분 **본래 양측 구조**(폐혈관, 폐간질,
폐실질)라 `bilateral` 이 맞다고 판단했습니다. 그렇게 보아 제외하고 남은 것이
아래입니다.
""")
    for x in bl[:a.max_cases]:
        W("\n".join(case(x["rec"], x["p"],
                         note=f"부위 `{x['a']['label']}` 를 bilateral 로 봄")))
    if len(bl) > a.max_cases:
        W(f"\n(외 {len(bl) - a.max_cases}건 — tsv 참조)")

    # ---- E
    sch = group_schema(recs)
    split = {k: c for k, c in sch.items()
             if c["bilateral"] and c["unspecified"]}
    W(f"\n---\n\n## E. 스키마 자체의 모순 — {len(split)}개 구조\n")
    W("""**질문: 본래 양측인 구조의 `laterality` 기본값을 하나로 고정하시겠습니까?**

이건 결함 목록이 아니라 **설계 결정**입니다. 그리고 이 감사로는 절대
잡히지 않습니다 -- 두 값이 모두 스키마상 합법이라 어느 쪽도 규칙을 어기지
않기 때문입니다.

흉막이나 폐처럼 본래 양쪽에 있는 구조에 `bilateral` 과 `unspecified` 가
둘 다 허용되면, 같은 뜻이 두 값으로 갈려 기록됩니다. **그러면 이 칸으로는
아무것도 걸러낼 수 없습니다** -- "양쪽 흉막"을 찾으려고 `bilateral` 로
필터하면 대부분이 빠집니다.
""")
    W("| 구조 | bilateral | unspecified | left | right | midline |")
    W("|---|---|---|---|---|---|")
    for k, c in sorted(sch.items(), key=lambda kv: -sum(kv[1].values())):
        if sum(c.values()) < 3:
            continue
        mark = " ⚠" if k in split else ""
        W(f"| {k}{mark} | {c['bilateral']} | {c['unspecified']} | "
          f"{c['left']} | {c['right']} | {c['midline']} |")
    W("""
⚠ 가 붙은 것이 두 값으로 갈린 구조입니다. **두 라벨이 정반대로 기울어
있다는 점**이 이것이 우연이 아님을 보여줍니다:

| | bilateral | unspecified |
|---|---|---|
| `pleura` | 32 | **230** |
| `lungs` | **211** | 81 |

같은 종류의 구조인데 한쪽은 주로 `bilateral`, 다른 쪽은 주로 `unspecified`
입니다. 규칙이 없다는 뜻입니다.

선택지는 셋입니다.

| 선택 | 뜻 | 대가 |
|---|---|---|
| **`bilateral` 로 고정** | 본래 양측인 구조는 항상 양측 | "어느 쪽인지 말하지 않았다"를 표현할 수 없음 |
| **`unspecified` 로 고정** | 문장이 말했을 때만 편측을 채움 | 양측임이 자명한데도 매번 비어 있음 |
| **`not_applicable` 신설 적용** | 이 구조에는 편측 개념이 없음 | 기존 데이터 마이그레이션 필요 |

`ontology.py` 의 `ANATOMY[label]` 첫 칸(`implied_laterality`)이 이미 이
질문에 답하는 자리입니다 -- 값을 정해 넣고 `validate.py` 가 강제하면
됩니다. **정할 것은 어느 값이냐 하나뿐입니다.**
""")

    W("\n---\n\n## 판정 기록란\n")
    W("| 묶음 | 건수 | 판정 | 판정자 | 날짜 | 비고 |")
    W("|---|---|---|---|---|---|")
    for name, n in [("A 자리표시자", len(fillers)), ("B 판독 신뢰도", len(lim_all)),
                    ("C-1 in place", len(ip)), ("C-2 끝위치 라벨", len(tp)),
                    ("C-3 변화 부사", len(ad)), ("C-4 단어 중복", len(ps)),
                    ("C-5 비교 누락", len(pn)),
                    ("D bilateral", len(bl)),
                    ("E 스키마 기본값", len(split))]:
        W(f"| {name} | {n} |  |  |  |  |")

    out_md = a.out or os.path.join(REPO, "docs",
                                   f"PROMPT_DEFECTS_{a.arm}_{a.split}.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    open(out_md, "w", encoding="utf-8").write("\n".join(L) + "\n")

    out_tsv = out_md.rsplit(".", 1)[0] + "_cases.tsv"
    with open(out_tsv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["group", "utterance_id", "report_id", "section",
                    "utterance", "detail", "proposition"])
        def dump(g, items, det):
            for x in items:
                r = x["rec"] if isinstance(x, dict) and "rec" in x else x
                p = x.get("p") if isinstance(x, dict) else None
                w.writerow([g, r["utterance_id"], r["report_id"], r["section"],
                            r["utterance"], det(x) if p or True else "",
                            pjson(p) if p else ""])
        dump("A_자리표시자", ph, lambda x: f"{x['kind']}/원본에 {'있음' if x['in_orig'] else '없음'}")
        dump("B_판독신뢰도", [{"rec": r} for r in lim_all], lambda x: "")
        dump("C1_in_place", ip, lambda x: x["where"])
        dump("C2_끝위치라벨", tp, lambda x: x["d"]["label"] + ("/중복" if x["dup"] else ""))
        dump("C3_변화부사", ad, lambda x: f"{x['d']['text']}→{x['d']['label']}")
        dump("C4_단어중복", ps, lambda x: x["d"]["text"])
        dump("C5_비교누락", pn, lambda x: x["d"]["text"])
        dump("D_bilateral", bl, lambda x: x["a"]["label"])

    print(f"[ok] {out_md}\n[ok] {out_tsv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
