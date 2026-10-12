#!/usr/bin/env python3
"""Metric 1-E -- rule 9, on words the lexicon does not have.

validate.py already raises descriptor_wrong_axis for words IN
DESCRIPTOR_LEXICON. It cannot fire on a word the table lacks, which is where
the risk is, so this asks the only question available without a table: is the
assignment at least self-consistent?

  table conflicts   text is in the lexicon and the type disagrees. Should be 0
                    on a normalized file; anything else means step 2 did not
                    run, or ran with another lexicon. NOTE: 0 here can also
                    mean the lexicon knows almost nothing -- read it with the
                    lexicon's coverage.
  OOV axis splits   not in the lexicon, seen under two or more types. Ranked by
                    how lopsided the split is: 200/3 is a typo, 90/80 is a
                    genuinely ambiguous word that needs a decision.

size vs severity is reported separately -- rule 9 names that pair because it is
the one a language model actually confuses.
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = '1-E'
TITLE = 'Descriptor axis purity'
SCOPE = 'split'          # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Does a descriptor word always land on the same axis (size / severity / "
        "...), where nothing has forced it to?")

MEANS = """## 한 줄로

**같은 단어가 항상 같은 칸에 들어가는지 본다.**

## 무슨 말인가

소견을 꾸미는 말에는 **칸(축)** 이 정해져 있다.

| 칸 | 무엇을 말하나 | 예 |
|---|---|---|
| `size` | 크기 | small, large |
| `severity` | 정도 | mild, severe |
| `extent` | 범위 | focal, widespread |
| `morphology` | 모양 | round, linear |

`"mild"` 를 어떤 데서는 `severity`(정도) 칸에, 다른 데서는 `extent`(범위) 칸에
넣었다면 — 나중에 "심한 소견만 찾아줘" 라고 물었을 때 **절반이 안 나온다.**

## ⚠️ 2026-09-15 — 판정 근거가 바뀌었다

예전에는 **"표가 아는 단어의 칸이 표와 다른가"** 로 판정했다. **쓸 수 없는
근거였다.**

이유는 이렇다. 2단계 정리 규칙이 **표에 맞춰 칸을 덮어쓴다.**

    모델이 말한 칸  →  표가 말하는 칸으로 강제 변경

그러니 정리가 끝난 데이터에서 **둘은 항상 같을 수밖에 없다.** 실제로 train
59만 건 중 어긋남이 **0** 이었다. **데이터가 깨끗해서가 아니라, 반박이
불가능하게 되어 있어서다.**

**커버리지(표가 아는 단어 비율)를 목표로 삼는 건 더 나빴다.** 단어를 표에
등록하면 "표 밖 분열" 목록에서도 빠지기 때문이다. 즉 **등록은 측정을 시작시키는
게 아니라 끝낸다.** 1-A 의 조작 가능성과 똑같은 함정이다.

## 지금은 두 갈래로 본다

| 갈래 | 뜻 | 조작 가능한가 |
|---|---|---|
| **표 밖 칸 분열** (판정 근거) | **표가 모르는** 단어를 두 칸에 나눠 썼다 | **불가능 — 아무것도 일치를 강제하지 않는다** |
| **표가 모델을 고친 횟수** | 2단계가 모델의 칸을 몇 번 갈아엎었나 | 기록된 사실 |

**두 숫자는 맞교환된다.** 단어를 등록하면 앞에서 빠지고 뒤로 옮겨 가므로
**합이 대체로 보존되고, 등록으로 판정을 좋게 만들 수 없다.**

## 고친 횟수는 왜 따로 기록하나

**데이터에서 읽을 수 없기 때문이다.** 배포되는 레코드에는 최종 답만 있고,
모델의 원래 답은 2단계가 덮어쓰는 순간 사라진다. 작업 메모를 레코드에 넣으면
S 검사가 결함으로 잡는다.

그래서 `renormalize.py` 가 **그 순간의 카운트를** `out/normalization/` 에 따로
남기고, 이 요소가 그것을 읽는다.

> ⚠️ **처음 만든 방식은 한 시간 만에 그 숫자를 잃었다.** 마지막 실행만 저장했기
> 때문이다. **고정점에 도달한 파일은 다시 돌려도 아무것도 안 바뀌므로**, 그 뒤에
> 돌린 2건짜리 실행이 *"표가 모델을 2,135번 고쳤다"* 를 **0 으로 덮어썼다.**
>
> 지금은 실행 **이력**을 쌓고, 각 항목마다 **마지막으로 실제 0 이 아니었던
> 실행**을 찾아 읽는다. 리포트에 그 실행 날짜와 당시 온톨로지 지문이 같이 찍힌다.

## `BLIND` 의 뜻도 바뀌었다

커버리지가 낮다는 뜻이 아니라, **그 기록이 없어서 표 안쪽 절반을 판정할 수 없다**
는 뜻이다. 깨끗한 것인지 강제된 것인지 구분할 방법이 없기 때문이다.

## 실제로 걸린 예

    dense       : severity 2,460  /  morphology 352
    throughout  : distribution 971  /  extent 654
    dual lead   : device_position 758 / other 497 / number 176

**`throughout` 처럼 971 대 654 면 동전 던지기와 같다.** 그 단어에 대해서는
규칙이 존재하지 않는다는 뜻이다.
"""

# Share of descriptor mentions sitting on the losing axis of a word the
# lexicon does not know. These are the only axis disagreements nothing has
# enforced away, so they are what the verdict is built on.
WARN_AT = 0.005
FAIL_AT = 0.05


import collections
import json
import os

# Share of descriptor mentions sitting on the losing axis of a word the
# lexicon does not know. These are the only axis disagreements nothing has
# enforced away, so they are what the verdict is built on.
WARN_AT = 0.005
FAIL_AT = 0.05
from typing import Any, Dict, List, Optional

import core
from core import ONT, norm_text, propositions, pct, section, table

_WATCHED_PAIR = {"size", "severity"}


def measure(split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    seen: Dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    table_conflicts: collections.Counter = collections.Counter()
    total = 0

    for _rec, prop in propositions(split, limit):
        for d in prop.get("descriptors") or []:
            txt, typ = norm_text(d.get("text")), d.get("type")
            if not txt or not typ:
                continue
            total += 1
            seen[txt][typ] += 1
            hit = ONT.DESCRIPTOR_LEXICON.get(txt)
            if hit and hit[0] != typ:
                table_conflicts[f"{txt}: {typ} (lexicon says {hit[0]})"] += 1

    oov_split = []
    for txt, types in seen.items():
        if len(types) < 2 or txt in ONT.DESCRIPTOR_LEXICON:
            continue
        ranked = types.most_common()
        n = sum(types.values())
        minority = n - ranked[0][1]
        oov_split.append({
            "text": txt, "n": n, "types": ranked,
            "minority": minority,
            "lopsided": minority / n,
            "size_severity": set(types) >= _WATCHED_PAIR,
        })
    oov_split.sort(key=lambda r: (-r["n"], r["lopsided"]))

    return {
        "split": split,
        "descriptors": total,
        # Tokens, not just distinct words: one split word used 3,000 times is
        # not the same finding as one used twice, and the verdict rides on it.
        "oov_split_tokens": sum(r["minority"] for r in oov_split),
        "oov_split_mentions": sum(r["n"] for r in oov_split),
        "distinct_texts": len(seen),
        "in_lexicon": sum(1 for t in seen if t in ONT.DESCRIPTOR_LEXICON),
        "table_conflicts": table_conflicts.most_common(15),
        "table_conflict_total": sum(table_conflicts.values()),
        "oov_axis_splits": oov_split[:20],
        "oov_axis_split_total": len(oov_split),
        "size_severity_splits": sum(1 for r in oov_split
                                    if r["size_severity"]),
    }


NOTES_DIR = os.path.join(core.REPO, "out", "normalization")

# Notes that say the table overruled the model on a descriptor.
_TABLE_ACTED = ("descriptor_type_from_lexicon", "descriptor_label")


def sidecar(split: str) -> Optional[Dict[str, Any]]:
    """The last run on which step 2 ACTUALLY changed something, per note.

    Step 2 destroys the evidence this metric needs: `normalize_descriptor`
    overwrites `descriptor.type` to whatever the lexicon says, so afterwards
    the data agrees with the table BY CONSTRUCTION. `renormalize.py` records
    the counts at the moment of the overwrite, which is the only moment the
    disagreement exists.

    WHY THE LATEST RUN IS THE WRONG ONE TO READ.  A file at its fixed point
    changes nothing on the next pass by definition, so the most recent entry is
    usually a row of zeros -- and reading it reported "the table corrected the
    model 0 times" on the very day it corrected it 2,135 times. For each note
    this walks the history backwards and takes the last run where the count was
    not zero, which is the run that did the work.
    """
    path = os.path.join(NOTES_DIR, f"{core.ARM}_{split}_notes.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None

    history = doc.get("history") or ([doc] if doc.get("notes") else [])
    writes = [h for h in history if not h.get("dry_run")] or history
    if not writes:
        return None
    out: Dict[str, Any] = {"runs": len(history), "latest": writes[-1]}
    for code in _TABLE_ACTED:
        for h in reversed(writes):
            if (h.get("notes") or {}).get(code):
                out[code] = {"count": h["notes"][code],
                             "applied": h.get("applied"),
                             "ontology": h.get("ontology_content_hash")}
                break
        else:
            out[code] = {"count": 0, "applied": writes[-1].get("applied"),
                         "ontology": writes[-1].get("ontology_content_hash")}
    return out


def render(res: Dict[str, Any]) -> str:
    body = [section(f"1-E  Descriptor axis purity (rule 9)  ({res['split']})"),
            table([[res["descriptors"], res["distinct_texts"],
                    res["in_lexicon"],
                    pct(res["in_lexicon"], res["distinct_texts"]),
                    res["table_conflict_total"],
                    res["oov_axis_split_total"],
                    res["size_severity_splits"]]],
                  ["descriptors", "distinct", "in lexicon", "lexicon cov",
                   "table conflicts", "OOV axis splits", "size/severity"])]

    note = sidecar(res["split"])
    body.append("\n**Did the table do any work?** (from "
                "`out/normalization/`, written by step 2)\n")
    if note:
        body.append(table(
            [[k, f"{note[k]['count']:,}", note[k]["applied"] or "?",
              note[k]["ontology"] or "?"] for k in _TABLE_ACTED],
            ["note", "count", "last run that fired it", "ontology then"]))
        body.append(f"\n`{note['runs']}` recorded step-2 runs for this split. "
                    f"**The count shown is from the last run on which the note "
                    f"actually fired, not the most recent run** -- a file at "
                    f"its fixed point changes nothing on a re-run, so the "
                    f"latest entry is normally zeros.\n")
        body.append(
            "\n`descriptor_type_from_lexicon` is **the number this metric "
            "used to be unable to see**: how many times the model filed a word "
            "on one axis and the table moved it to another. After step 2 runs, "
            "the record shows only the table's answer, so this count is the "
            "only surviving trace of the disagreement.\n")
    else:
        body.append("\n> **No sidecar for this split.** `renormalize.py` has "
                    "not run since it started recording what it changes, so "
                    "there is no way to tell whether the in-vocabulary half of "
                    "this metric is clean or merely enforced. That is what "
                    "BLIND means here.\n")

    if res["table_conflicts"]:
        body.append("\n**Lexicon conflicts** -- a descriptor the lexicon knows, "
                    "filed on another axis. Step 2 should have rewritten these, "
                    "so a nonzero count means the data was not renormalized "
                    "against this table:\n")
        body.append(table([[k, v] for k, v in res["table_conflicts"]],
                          ["text: recorded type", "count"]))
    else:
        body.append(
            "\n> **`table conflicts 0` is not evidence of anything.** Step 2 "
            "rewrites `descriptor.type` to match the lexicon, so on "
            "renormalized data this count is zero by construction -- it "
            "reports that normalization ran, not that the axes are right. "
            "The live signals are the sidecar above and the out-of-vocabulary "
            "splits below.\n")

    if res["oov_axis_splits"]:
        body.append(
            f"\n**Words outside the lexicon filed on two or more axes** — "
            f"{res['oov_axis_split_total']:,} words, "
            f"{res['oov_split_tokens']:,} minority mentions. **This is what "
            f"the verdict rides on.** Nothing enforces agreement here, so a "
            f"split is the corpus contradicting itself:\n")
        body.append(table(
            [[r["text"], r["n"],
              ", ".join(f"{t}:{c}" for t, c in r["types"]),
              f"{r['lopsided']:.2f}",
              "YES" if r["size_severity"] else ""]
             for r in res["oov_axis_splits"]],
            ["text", "count", "types", "minority frac", "size/severity"]))
    return "\n".join(body) + "\n"


def _join(parts):
    return "\n".join(parts)


def run(cfg) -> core.Result:
    per = [measure(sp, cfg.limit) for sp in cfg.splits]
    notes = {sp: sidecar(sp) for sp in cfg.splits}
    body = core.summary(
        [[r["split"], f"{r['descriptors']:,}", f"{r['distinct_texts']:,}",
          f"{r['in_lexicon']:,}",
          f"{r['in_lexicon']/max(1, r['distinct_texts']):.2%}",
          f"{r['oov_axis_split_total']:,}",
          f"{r['oov_split_tokens']:,}",
          pct(r["oov_split_tokens"], r["descriptors"]),
          (f"{notes[r['split']]['descriptor_type_from_lexicon']['count']:,}"
           if notes[r["split"]] else "—"),
          r["table_conflict_total"]] for r in per],
        ["split", "descriptors", "distinct", "in lexicon", "lexicon cov",
         "OOV split words", "OOV minority", "%", "table overruled model",
         "table conflicts"],
        "**The verdict rides on `OOV minority`** -- mentions of a word the "
        "lexicon does NOT know, sitting on the losing axis. Nothing enforces "
        "agreement there, so a split is the corpus contradicting itself.\n\n"
        "`table conflicts` is zero by construction on renormalized data (step "
        "2 rewrites the type to match), and `lexicon cov` is not a score: "
        "registering a word REMOVES it from `OOV split words` and makes its "
        "axis unfalsifiable. The two columns roughly trade off, which is the "
        "point -- coverage cannot be gamed into a better verdict.")
    body += core.example_note(cfg.example_split) if cfg.example_split else ""
    body += _join(render(r) for r in per)

    body += ("\n> **2026-09-15 — 이 요소의 판정 근거가 바뀌었다.**\n>\n"
             "> 예전에는 `table conflicts`(표가 아는 단어의 축이 표와 다른가)와 "
             "렉시콘 커버리지로 판정했다. **둘 다 쓸 수 없는 근거였다.**\n>\n"
             "> `normalize_descriptor` 는 렉시콘에 맞춰 `descriptor.type` 을 "
             "**덮어쓴다**. 그래서 정규화된 데이터에서 이 충돌은 구조적으로 "
             "0 이고, 실측으로 train 596,816 언급 중 0 이었다. **데이터가 "
             "깨끗해서가 아니라 반박이 불가능하게 되어 있어서다.**\n>\n"
             "> 커버리지는 더 나빴다. 단어를 표에 등록하면 `oov_axis_splits` "
             "목록에서도 빠지므로(코드가 `txt in DESCRIPTOR_LEXICON` 이면 "
             "건너뛴다), **등록은 측정을 시작시키는 게 아니라 끝낸다.** "
             "커버리지를 목표로 삼으면 1-A 의 항등행과 같은 조작이 된다.\n>\n"
             "> 지금은 **표 밖의 축 분열**이 판정을 지고, 표가 모델을 몇 번 "
             "고쳤는지는 step 2 가 남긴 사이드카에서 읽는다. 등록이 늘면 앞 "
             "숫자가 줄고 뒤 숫자가 늘어 **합이 대체로 보존된다.**\n")

    tokens = sum(r["oov_split_tokens"] for r in per)
    total = sum(r["descriptors"] for r in per)
    words = sum(r["oov_axis_split_total"] for r in per)
    share = tokens / total if total else 0.0
    have_notes = [sp for sp, n in notes.items() if n]

    # BLIND is no longer about coverage. It is about whether the in-vocabulary
    # half of this metric has ANY independent evidence: without a sidecar, step
    # 2's overwrite means that half cannot be judged at all.
    if not have_notes:
        verdict = core.BLIND
        head = (f"step 2 left no record of what it changed, so the "
                f"{sum(r['in_lexicon'] for r in per):,} in-vocabulary words "
                f"cannot be judged; {words:,} out-of-vocabulary words split "
                f"across axes")
    else:
        verdict = (core.FAIL if share >= FAIL_AT else
                   core.WARN if share >= WARN_AT else core.PASS)
        overruled = sum(n["descriptor_type_from_lexicon"]["count"]
                        for n in notes.values() if n)
        head = (f"{words:,} out-of-vocabulary words split across axes "
                f"({tokens:,} minority mentions, {share:.2%} of descriptors); "
                f"the table overruled the model {overruled:,} times")
    return core.Result(body, verdict, head,
                       {"oov_split_words": words, "oov_split_tokens": tokens,
                        "share": share, "splits_with_notes": have_notes})


if __name__ == "__main__":
    import sys
    sp = sys.argv[1] if len(sys.argv) > 1 else "test"
    print(render(measure(sp)))
