#!/usr/bin/env python3
"""A cross-check set, and the precision/recall of the judge against it, per
code.

WHAT THIS ACTUALLY IS. The "labeller" here is a SECOND MODEL PASS, run
separately over the same rows, not a person. Calling it a "gold set" is
therefore loose: gold implies a human or clinical ground truth, and this is
inter-model agreement -- one model checking another's issues one row at a
time. That is still useful (it catches a systematic misreading the first
model made, the way the `persistent` reversal in this repo's history was
caught), but it is weaker evidence than a human read, for one specific
reason: the two passes can share a correlated blind spot -- a convention
neither model knows, a hedge word both read the same wrong way -- in which
case "agreement" is not "correctness", it is two models being wrong the same
way. Read every number this file prints as "what a second model pass
confirmed", not as clinical ground truth. If a finding here needs to go in
front of a clinician, it still needs an actual person to look at it.

Without this the 233-report output is unusable. Not because it is wrong, but
because nobody can say HOW wrong: `hallucinated` and `dropped` are probably
trustworthy, `bad_warning` and the descriptor-type half of `wrong_descriptor`
probably are not, and a number that mixes them tells you nothing about either.
A code whose precision is 0.4 is a queue to triage; a code whose precision is
0.95 is a list to act on. Same output, opposite uses.

Three commands, in order:

    sample   pick the reports, BEFORE the judge has run on them if possible,
             and write a blank labelling sheet
    (a second model pass labels the sheet -- run it separately, e.g. by hand
     with another chat model, or swap in a real human here if one is
     available; either way this script does not do it)
    score    read the sheet back, compare with the judge, print precision,
             recall and F1 per issue code with Wilson intervals

    python3 GPT/goldset.py sample --reports 30
    python3 GPT/goldset.py score

WHY THE SAMPLE IS RANDOM AND NOT STRATIFIED BY THE JUDGE'S OUTPUT: a set built
around what the judge flagged measures precision and CANNOT measure recall --
the defects it missed are, by construction, not in the sample. The sample is
drawn from the file with a fixed seed and nothing else, so a defect the judge
never mentioned still has its chance to appear.

TWO SHEET MODES, and they answer different questions:

    precheck   the mechanical layer's own findings, sampled. This one is not
               optional-feeling: precheck's findings are labelled "do not
               raise" to the model, so the model CANNOT contradict them and a
               false positive there rides straight into the final output with
               nothing between it and the reader. Measured once on
               jsonl/Prompt/test_reviewed: the first pass had 16 false
               positives in 94 `overspecified` findings (small_cell_carcinoma
               read as a severity, appropriate_position as a tip location),
               which is why the patterns were narrowed. That number is only
               known because it was counted.
    full       every utterance in the sample, with a blank line per utterance.
               The labeller marks every defect THEY find, judge output unseen.
               Gives precision AND recall. Costs real hours.
    precision  only the utterances the judge flagged. The labeller rules each
               issue true or false. Cheap, gives precision only. Recall stays
               unknown, and the report says so rather than implying a number.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import audit_records as A                                       # noqa: E402

OUTDIR = os.path.join(REPO, "out", "gpt_records", "goldset")


def wilson(k: int, n: int, z: float = 1.96):
    """A proportion's interval that does not go negative at small n.

    At n = 12 -- which is what a per-code count looks like in a 30-report gold
    set -- the textbook normal interval is meaningless and sometimes leaves
    [0, 1]. Wilson is the one that stays honest there, and honesty about the
    width is the entire reason for computing it.
    """
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def cmd_sample(a) -> int:
    reports = A.load_reports(a.records)
    rng = random.Random(a.seed)
    picked = sorted(rng.sample(reports, min(a.reports, len(reports))),
                    key=lambda r: r["id"])
    ids = [r["id"] for r in picked]
    os.makedirs(a.out, exist_ok=True)
    # 모드마다 따로 쓴다. 한 파일에 쓰면 두 번째 모드를 뽑는 순간 첫 번째
    # 모드의 표본 기록이 사라지고, score 가 엉뚱한 시트를 채점한다.
    json.dump({"seed": a.seed, "mode": a.mode, "report_ids": ids},
              open(os.path.join(a.out, f"sample_{a.mode}.json"), "w"), indent=1)

    if a.mode == "precheck":
        # 리포트로 자르지 않는다. 재고 싶은 것은 "이 리포트들이 어떤가" 가
        # 아니라 "이 코드의 정밀도가 얼마인가" 이고, 그건 코드마다 따로
        # 물어야 한다. 리포트 30개로 자르면 큰 코드조차 11건이 되어
        # 95% 구간이 0.74-1.00 -- 즉 아무것도 말하지 않는다.
        import precheck as P
        allrecs = P.load(a.records)
        found = P.run(allrecs)
        byu = {r["utterance_id"]: r for r in allrecs}
        pool = collections.defaultdict(list)
        for uid, items in found.items():
            for f in items:
                pool[f["code"]].append((uid, f))
        rows = []
        for code in sorted(pool, key=lambda k: -len(pool[k])):
            got = pool[code]
            rng.shuffle(got)
            for uid, f in got[:a.per_code]:
                rec = byu[uid]
                rows.append({
                    "report_id": rec["report_id"],
                    "utterance_id": uid,
                    "section": rec["section"],
                    "utterance": rec["utterance"],
                    "propositions": json.dumps(rec["propositions"],
                                               ensure_ascii=False),
                    "code": f["code"], "by": f["by"],
                    "proposition": f.get("proposition") or "",
                    "message": f["message"],
                    "LABEL_true_defect": "",     # yes / no
                    "LABEL_note": "",
                })
        picked = allrecs
        ids = sorted({r["report_id"] for r in allrecs})
        cols = list(rows[0]) if rows else []
        path = os.path.join(a.out, "sheet_precheck.tsv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, cols, delimiter="\t")
            w.writeheader()
            w.writerows(rows)
        n_by = collections.Counter(r["code"] for r in rows)
        tot_by = {k: len(v) for k, v in pool.items()}
        g = [f"# precheck 오탐 확인 — {len(rows)}행\n",
             f"파일 전체에서 **코드별로 최대 {a.per_code}건씩** 무작위로 "
             f"뽑았습니다 (seed {a.seed}). 리포트 단위가 아닙니다 — 재는 "
             f"대상이 리포트가 아니라 코드이기 때문입니다.\n",
             "| 코드 | 표본 | 전체 | 전부 맞을 때 95% 구간 |",
             "|---|---|---|---|"]
        for code, n in n_by.most_common():
            lo, hi = wilson(n, n)[1:]
            g.append(f"| {code} | {n} | {tot_by[code]} | {lo:.2f} – {hi:.2f} |")
        g += ["",
              "마지막 칸이 좁을수록 그 코드에 대해 말할 수 있는 것이 "
              "많습니다. **n 이 한 자리인 코드는 이 시트로 결론을 낼 수 "
              "없습니다** — 전체 건수 자체가 적다는 뜻이니, 그 코드는 "
              "차라리 전수를 보십시오.\n",
             "**이 층의 지적에는 판정 모델이 반박할 수 없습니다** -- 프롬프트가 "
             "\"do not raise\" 라고 하기 때문입니다. 따라서 여기의 오탐은 "
             "아무 여과 없이 최종 출력까지 갑니다. 그 비율을 아는 유일한 "
             "방법이 이 시트입니다. **이 표를 채우는 것도 결국 또 다른 "
             "판정(별도 모델 또는 사람)이라는 점을 유념하십시오** — 정답지가 "
             "아니라 두 번째 의견입니다.\n",
             f"`{os.path.relpath(path, REPO)}` 의 `LABEL_true_defect` 에 "
             "`yes`(지적이 맞다) / `no`(오탐) 를 채우십시오.\n",
             "코드 하나가 0.9 아래면 그 패턴을 좁히거나 모델에게 "
             "돌려주어야 합니다.\n"]
        gp = os.path.join(a.out, "HOWTO_precheck.md")
        open(gp, "w", encoding="utf-8").write("\n".join(g) + "\n")
        print(f"[ok] {path}\n[ok] {gp}", file=sys.stderr)
        print(f"[info] 리포트 {len(picked)} · 라벨링할 행 {len(rows)}",
              file=sys.stderr)
        return 0

    verd = {}
    vp = os.path.join(REPO, "out", "gpt_records", A.arm_of(a.records),
                      "verdicts.jsonl")
    if os.path.exists(vp):
        for line in open(vp, encoding="utf-8"):
            line = line.strip()
            if line:
                v = json.loads(line)
                verd[v["report_id"]] = v

    # precision 모드도 리포트로 자르지 않는다. 재는 것은 "이 리포트들이
    # 어떤가" 가 아니라 "이 코드의 정밀도가 얼마인가" 이고, 지적은 233개
    # 리포트에 흩어져 있다. precheck 모드에서 같은 실수를 한 번 했다.
    rows = []
    if a.mode == "precision":
        flag = os.path.join(REPO, "out", "gpt_records", A.arm_of(a.records),
                            "flagged.jsonl")
        if not os.path.exists(flag):
            print(f"[error] {flag} 없음 -- 먼저 audit_records.py 를 "
                  f"돌리십시오.", file=sys.stderr)
            return 1
        items = [json.loads(l) for l in open(flag, encoding="utf-8")
                 if l.strip()]
        # 이미 답을 아는 유형은 표시해 둔다. 라벨을 대신 채우지는 않는다 --
        # 그건 2차 판정(교차검증) 모델의 판단을 가로채는 것이다 -- 다만
        # 같은 논쟁을 249번째로 다시 판정하게 할 이유도 없다.
        PRIOR = {"persistent": "이전 교차검증에서 17/17 오탐 판정된 유형"}
        pool = collections.defaultdict(list)
        for it in items:
            pool[it["verdict"]].append(it)
        for code in sorted(pool, key=lambda k: -len(pool[k])):
            got = sorted(pool[code],
                         key=lambda x: (x.get("votes") != "3/3",
                                        x["utterance_id"]))
            if a.per_code:
                head = [g for g in got if g.get("votes") == "3/3"][:a.per_code]
                tail = [g for g in got if g.get("votes") != "3/3"]
                rng.shuffle(tail)
                got = head + tail[:max(0, a.per_code - len(head))]
            for it in got:
                prior = ""
                for k, v in PRIOR.items():
                    if k in (it.get("quote") or "").lower():
                        prior = v
                rows.append({
                    "report_id": it.get("report_id", ""),
                    "utterance_id": it["utterance_id"],
                    "section": it["section"],
                    "utterance": it["utterance"],
                    "propositions": json.dumps(it.get("current"),
                                               ensure_ascii=False),
                    "judge_proposition": it["proposition_id"],
                    "judge_field": it["field"],
                    "judge_verdict": it["verdict"],
                    "judge_votes": it.get("votes", ""),
                    "judge_severity": it.get("severity", ""),
                    "judge_confidence": it.get("confidence", ""),
                    "judge_quote": it.get("quote", ""),
                    "judge_note": it["note"],
                    "PRIOR": prior,
                    "LABEL_true_defect": "",     # yes / no
                    "LABEL_note": "",
                })
        picked = []
        ids = sorted({r["report_id"] for r in rows if r["report_id"]})

    cols = list(rows[0]) if rows else []
    path = os.path.join(a.out, f"sheet_{a.mode}_labeled.tsv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    guide = [f"# 교차검증 시트 안내 ({a.mode} 모드)\n",
             "**이 시트를 채우는 것은 사람이 아니어도 됩니다.** 지금까지 이 "
             "시트는 별도 모델 패스로 채워졌고 — 즉 다른 LLM 이 같은 행을 "
             "다시 판정한 결과입니다. 사람이 직접 채우면 더 신뢰도가 "
             "높아지지만, 그렇지 않아도 이 안내는 동일하게 적용됩니다. "
             "아래 표의 '정밀도'는 두 모델 간 일치도이지 임상적으로 "
             "검증된 정답은 아닙니다.\n",
             f"대상: 리포트 {len(picked)}개 · 행 {len(rows)}개 · seed {a.seed}\n",
             f"파일: `{os.path.relpath(path, REPO)}` — 엑셀에서 열어 "
             f"`LABEL_` 로 시작하는 칸만 채우십시오.\n"]
    if a.mode == "full":
        guide += [
            "\n## 채울 칸\n",
            "| 칸 | 값 |",
            "|---|---|",
            "| `LABEL_status` | `ok` 또는 `flagged` |",
            "| `LABEL_verdicts` | flagged 일 때만. 아래 코드 중 해당하는 것을 "
            "쉼표로 |",
            "| `LABEL_note` | 한 줄 이유 (선택) |",
            "\n## 코드\n", "| 코드 | 뜻 |", "|---|---|"]
        for k, v in A.VERDICTS.items():
            guide.append(f"| `{k}` | {v} |")
        guide += [
            "\n## 중요\n",
            "- **1차 판정자(audit_records.py 를 돌린 모델) 출력을 보지 "
            "마십시오.** 같은 모델 계열이면 특히, 보고 나면 이 시트는 "
            "재현율을 재지 못합니다 — 1차가 놓친 결함을 2차도 같은 이유로 "
            "놓치게 됩니다. 가능하면 1차와 **다른 모델**로 이 시트를 "
            "채우십시오 — 같은 모델의 두 번째 실행은 같은 편향을 공유할 "
            "위험이 큽니다.",
            "- 아래는 결함이 **아닙니다**: 섹션 필러가 비어 있는 것, "
            "본래 양측인 구조의 `bilateral`, `source` 가 `utterance` 가 "
            "아닐 때의 `text: null`, 철자만 다른 라벨.",
            "- 스팬·enum·과잉명세 라벨은 기계가 이미 봅니다. "
            "`GPT/precheck.py` 담당이니 여기서 라벨하지 마십시오.",
        ]
    else:
        byv = collections.Counter(r["judge_verdict"] for r in rows)
        guide += [
            "\n## 채울 칸\n",
            "| 칸 | 값 |", "|---|---|",
            "| `LABEL_true_defect` | `yes` (판정자가 맞다) / `no` (오탐) |",
            "| `LABEL_note` | 한 줄 이유. **오탐일 때는 꼭 적어 주십시오** "
            "— 규칙을 어떻게 고칠지가 거기서 나옵니다 |",
            "\n## 읽는 순서\n",
            "코드별로 묶고, 각 코드 안에서 **만장일치(3/3)를 먼저** "
            "놓았습니다. 중간에 멈추셔도 각 코드의 가장 강한 주장부터 "
            "판정됩니다.\n",
            "| 코드 | 건수 |", "|---|---|",
        ]
        for _k, _n in byv.most_common():
            guide.append(f"| `{_k}` | {_n} |")
        guide += [
            "\n## `PRIOR` 칸이 채워진 행\n",
            "이미 같은 논쟁을 판정하신 유형입니다. 라벨을 대신 채우지 "
            "않았습니다 — 판단을 가로채지 않기 위해서입니다 — 다만 "
            "249번째로 다시 읽으실 필요는 없으니 같은 판정을 빠르게 "
            "채우시면 됩니다.\n",
            "\n## 만장일치가 정답이라는 뜻은 아닙니다\n",
            "이 모델은 `temperature` 를 받지 않아 같은 리포트를 3번 물었고, "
            "`3/3` 은 세 번 다 같은 지적이 나왔다는 뜻입니다. 그런데 같은 "
            "모델의 세 표본은 **같은 편향을 공유**합니다. 실제로 "
            "`wrong_comparison` 의 3/3 중 18건이 이미 오탐으로 판정된 한 "
            "가지 논쟁입니다.\n",
            "**투표는 무작위 흔들림만 걸러내고 계통적 편향은 못 "
            "걸러냅니다.** 득표가 높다고 넘기지 마십시오.\n",
            "\n## 한계\n",
            "이 모드는 **정밀도만** 잽니다. 판정자가 놓친 결함은 시트에 "
            "아예 없으므로 재현율은 알 수 없습니다. 특히 `dropped` 는 "
            "만장일치율이 15% 로 가장 낮아, 정밀도가 높게 나와도 **놓친 "
            "것이 많을 수 있습니다.** 재현율이 필요하면 `--mode full` 로 "
            "따로 뽑으십시오.",
        ]
    gp = os.path.join(a.out, f"HOWTO_{a.mode}.md")
    open(gp, "w", encoding="utf-8").write("\n".join(guide) + "\n")
    print(f"[ok] {path}\n[ok] {gp}", file=sys.stderr)
    print(f"[info] 리포트 {len(picked)} · 라벨링할 행 {len(rows)}",
          file=sys.stderr)
    return 0


def cmd_score(a) -> int:
    mode = a.mode
    if not mode:
        found = [m for m in ("full", "precision", "precheck")
                 if os.path.exists(os.path.join(a.out, f"sample_{m}.json"))]
        if len(found) != 1:
            print(f"[error] 표본이 {len(found)}개 있습니다 ({found}). "
                  f"--mode 로 하나를 지정하십시오.", file=sys.stderr)
            return 1
        mode = found[0]
    meta = json.load(open(os.path.join(a.out, f"sample_{mode}.json"),
                          encoding="utf-8"))
    sheet = os.path.join(a.out, f"sheet_{mode}_labeled.tsv")
    rows = list(csv.DictReader(open(sheet, encoding="utf-8"), delimiter="\t"))
    labelled = [r for r in rows if any(v.strip() for k, v in r.items()
                                       if k.startswith("LABEL_"))]
    if not labelled:
        print(f"[error] {sheet} 에 라벨이 없습니다. 먼저 채워 주십시오.",
              file=sys.stderr)
        return 1

    # precheck 모드는 기계층만 채점한다. 모델 판정 결과가 없어도 -- 아직
    # 한 번도 돌리지 않았어도 -- 돌아가야 한다. 기계층 검증을 모델 실행보다
    # 먼저 하라고 권한 것이 이 도구 자신이므로.
    judge = {}
    if mode != "precheck":
        vp = os.path.join(REPO, "out", "gpt_records", A.arm_of(a.records),
                          "verdicts.jsonl")
        if not os.path.exists(vp):
            print(f"[error] {vp} 없음 -- 이 모드는 audit_records.py 의 "
                  f"판정 결과를 채점합니다.", file=sys.stderr)
            return 1
        for line in open(vp, encoding="utf-8"):
            line = line.strip()
            if line:
                v = json.loads(line)
                for u in v["utterances"]:
                    judge[u["utterance_id"]] = u

    L = ["# 1차 판정자 검증 — 2차(교차검증) 모델 대비\n",
         "**주의:** 아래의 '정밀도'·'재현율'은 사람이 매긴 정답 대비가 "
         "아니라, **다른 모델 패스가 같은 행을 다시 판정한 결과와의 "
         "일치도**입니다. 두 모델이 같은 편향을 공유하면 이 수치는 실제보다 "
         "높게 나올 수 있습니다 — 특히 두 패스가 같은 모델 계열일 때 그렇고, "
         "사람이 최종 확인하기 전까지는 잠정치로 다루십시오.\n",
         f"모드 `{mode}` · 리포트 {len(meta['report_ids'])} · "
         f"교차검증된 행 {len(labelled)}/{len(rows)} · seed {meta['seed']}\n"]

    if mode in ("precision", "precheck"):
        key = "judge_verdict" if mode == "precision" else "code"
        per = collections.defaultdict(lambda: [0, 0])
        for r in labelled:
            lab = r["LABEL_true_defect"].strip().lower()
            if lab not in ("yes", "no"):
                continue
            c = per[r[key]]
            c[1] += 1
            c[0] += (lab == "yes")
        L += ["**정밀도만** 측정합니다. 1차 판정자가 놓친 것은 이 시트에 "
              "없으므로 재현율은 알 수 없습니다.\n",
              "| 코드 | 맞음 | 전체 | 정밀도 | 95% 구간 |", "|---|---|---|---|---|"]
        tk = tn = 0
        for code, (k, n) in sorted(per.items(), key=lambda kv: -kv[1][1]):
            p, lo, hi = wilson(k, n)
            tk += k; tn += n
            L.append(f"| {code} | {k} | {n} | {p:.2f} | {lo:.2f} – {hi:.2f} |")
        p, lo, hi = wilson(tk, tn)
        L.append(f"| **전체** | {tk} | {tn} | **{p:.2f}** | {lo:.2f} – {hi:.2f} |")
    else:
        # 발화 단위 집합 비교. 2차(교차검증) 모델의 판정을 정답 삼아,
        # 1차 판정자의 예측과 대조한다 -- 사람 라벨이 아니다.
        per = collections.defaultdict(lambda: collections.Counter())
        st = collections.Counter()
        for r in labelled:
            uid = r["utterance_id"]
            gold_flag = r["LABEL_status"].strip().lower() == "flagged"
            gold = {c.strip() for c in r["LABEL_verdicts"].split(",")
                    if c.strip()} if gold_flag else set()
            u = judge.get(uid)
            # abstain 은 예측이 아니다. 판정 거부를 flagged 로 치면 정밀도가
            # 부풀고, ok 로 치면 재현율이 부당하게 깎인다. 별도로 세고 분모
            # 에서 뺀다.
            if u and u["status"] == "abstain":
                st["abstained"] += 1
                st["abstain_gold_flagged"] += gold_flag
                continue
            pred_flag = bool(u) and u["status"] == "flagged"
            pred = {i["verdict"] for i in (u or {}).get("issues", [])} \
                if pred_flag else set()
            st["gold_flagged"] += gold_flag
            st["pred_flagged"] += pred_flag
            st["both"] += gold_flag and pred_flag
            st["n"] += 1
            for c in gold | pred:
                if c in gold and c in pred:
                    per[c]["tp"] += 1
                elif c in pred:
                    per[c]["fp"] += 1
                else:
                    per[c]["fn"] += 1
        L += ["| 코드 | TP | FP | FN | 정밀도 | 95% 구간 | 재현율 | 95% 구간 | F1 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for code, c in sorted(per.items(), key=lambda kv: -(kv[1]["tp"] + kv[1]["fn"])):
            tp, fp, fn = c["tp"], c["fp"], c["fn"]
            pr, plo, phi = wilson(tp, tp + fp)
            rc, rlo, rhi = wilson(tp, tp + fn)
            f1 = 2 * pr * rc / (pr + rc) if (pr + rc) else 0.0
            L.append(f"| {code} | {tp} | {fp} | {fn} | {pr:.2f} | "
                     f"{plo:.2f} – {phi:.2f} | {rc:.2f} | {rlo:.2f} – {rhi:.2f} "
                     f"| {f1:.2f} |")
        L += [f"\n채점 대상 발화 {st['n']}건 · 2차 모델이 flagged "
              f"{st['gold_flagged']} · 1차 판정자가 flagged "
              f"{st['pred_flagged']} · 둘 다 {st['both']}\n",
              f"1차 판정자가 기권한 {st['abstained']}건은 분모에서 뺐습니다 "
              f"(그중 2차 모델이 결함이라 본 것 "
              f"{st['abstain_gold_flagged']}건). **기권이 2차 모델의 판단과 "
              f"자주 어긋나면 기권 기준이 너무 넓은 것입니다.**\n"]

    L += ["\n## 이 표를 어떻게 쓰나\n",
          "이 정밀도는 **모델 대 모델 일치도**입니다. 사람이 검토하기 전 "
          "우선순위를 매기는 용도로 쓰되, 최종 확정은 아닙니다.\n",
          "| 정밀도 | 그 코드의 결과를 |", "|---|---|",
          "| 0.9 이상 | 목록으로 쓴다 — 건별 확인 없이 집계해도 된다 (다만 "
          "사람 검수 전 최종 확정으로 쓰지는 않는다) |",
          "| 0.6 – 0.9 | 분류 대기열로 쓴다 — 사람이 걸러야 한다 |",
          "| 0.6 미만 | 쓰지 않는다. 그 코드는 프롬프트를 고치거나 버린다 |",
          "\n구간이 넓으면(예: 0.3 – 0.9) 그건 그 코드의 사례가 너무 "
          "적다는 뜻이지, 중간값이 답이라는 뜻이 아닙니다. "
          "표본을 늘리거나 판단을 미루십시오.\n"]
    p = os.path.join(a.out, f"score_{mode}.md")
    open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"[ok] {p}", file=sys.stderr)
    print("\n".join(L))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sample", "score"):
        q = sub.add_parser(name)
        q.add_argument("--records", default=A.RECORDS)
        q.add_argument("--out", default=None,
                       help="default: out/gpt_records/<arm>/goldset/")
        q.add_argument("--seed", type=int, default=20260915)
        q.add_argument("--reports", type=int, default=30)
        q.add_argument("--per-code", type=int, default=30,
                       help="precheck 모드 전용: 코드당 표본 수")
        q.add_argument("--mode", choices=["full", "precision", "precheck"],
                       default="full" if name == "sample" else None)
    a = ap.parse_args()
    if not a.out:
        a.out = os.path.join(REPO, "out", "gpt_records",
                             A.arm_of(a.records), "goldset")
    print(f"[info] arm={A.arm_of(a.records)} out={a.out}", file=sys.stderr)
    return cmd_sample(a) if a.cmd == "sample" else cmd_score(a)


if __name__ == "__main__":
    sys.exit(main())
