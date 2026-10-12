#!/usr/bin/env python3
"""Metric G1 -- is every extracted span actually in the utterance?

The one question this audit was missing. Metrics 1-A through 1-F ask whether
the ONTOLOGY was applied consistently; they cannot tell you whether the
extraction read the sentence, because a hallucinated span normalizes just as
cleanly as a real one. This is the check the RadGraph-family evaluations lead
with, and it needs no gold standard and no model: a `text` field either occurs
in `utterance` or it does not.

WHAT IS EXEMPT, AND WHY IT MATTERS.  Not every field is supposed to be a
quotation. The schema marks inferred anatomy with `source: entity_semantics`
("pneumothorax" implies the pleura, which the sentence never names) and
heading-derived anatomy with `source: section_context`, and both legitimately
carry `text: null`. That design is what makes this metric possible -- because
inference is declared, anything left that fails the substring test is an
undeclared invention rather than a modelling choice.

So a span is a defect only when it is non-null and absent from the utterance.
A null span on a declared-inferred entry is correct; a null span on a
`source: utterance` entry is a separate fault and counted separately.

Comparison with step 3: `validate.py` has `*_not_in_utterance` checks and R
reports them among forty-four others. This metric pulls them out, reports them
per field, and matches loosely as well as strictly -- so that a span differing
from the sentence only by whitespace or case is not counted with a span that
was invented.

    python3 m11_span_grounding.py [split]
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'G1'
TITLE = 'Span grounding (is every quoted span really in the utterance?)'
SCOPE = 'split'
ASKS = ("Does every non-null `text` / `cue` occur in the utterance it was "
        "taken from? Anything that does not was invented.")

MEANS = """## 한 줄로

**JSON 이 "원문에서 이 말을 가져왔다"고 한 것이, 진짜 원문에 있는지 확인한다.**

## 왜 이 검사가 필요한가

앞의 검사들은 전부 *"정해진 이름표를 일관되게 썼나"* 를 묻는다. 그 검사들은
**모델이 문장을 실제로 읽었는지 아닌지를 볼 수 없다.** 지어낸 말도 똑같이
깨끗하게 이름표로 바뀌기 때문이다.

실제로 걸린 예를 보자.

> **원문**: `"Status post sternotomy with mitral and aortic valve replacements."`
> (흉골절개술 후, 승모판 및 대동맥판 치환술)
>
> **JSON**: `"mitral valve replacement"` 를 인용했다고 적었다.
>
> 원문에 **그런 연속된 구절은 없다.** 모델이 "mitral ... valve replacements" 를
> 떼어다 붙여 만들어 낸 것이다. 뜻은 맞지만 **인용은 거짓**이다.

이런 걸 잡는 데 **정답 데이터도, AI 를 다시 부르는 것도 필요 없다.** 그 문구가
문장 안에 있거나 없거나 둘 중 하나다.

## 무엇이 면제인가 — 이게 이 검사의 핵심이다

모든 칸이 인용인 것은 아니다. 스키마는 **추론한 것을 추론이라고 밝히게** 되어
있다.

    "No pneumothorax."  (기흉 없음)
       부위 = 흉막(pleura),  인용 문구 = 없음(null)
       출처 = entity_semantics   ← "기흉이라는 말에서 추론했다"

문장에 "흉막"이라는 말은 없다. 하지만 기흉은 흉막에 생기는 병이므로 부위를
채울 수 있고, **추론이라고 정직하게 밝혔다.**

**추론을 밝히게 되어 있기 때문에**, 밝히지 않고 원문에 없는 말이 남아 있으면
그건 **신고하지 않은 창작**이다.

## 세 갈래로 나눠 센다

| 갈래 | 뜻 |
|---|---|
| `exact` | 원문에 그대로 있다 ✅ |
| `whitespace/case` | 띄어쓰기·대소문자만 다르다 (**정리 실수이지 창작이 아니다**) |
| `ABSENT` | 어떤 형태로도 문장에 없다 ❌ **지어냈다** |

> **이 셋을 한 칸에 합치면 띄어쓰기 하나 틀린 것과 지어낸 것이 같은 수로
> 세어진다.** 그래서 나눠 놓았다.

## 근거 단어(cue) 는 왜 안 세나

"없다"의 근거인 `"no"` 같은 단어는 **없는 게 정상인 경우가 많다.** 그냥 있는
소견을 말할 때는 근거 단어가 필요 없다. 근거 단어가 **있어야 하는데 없는**
경우는 다음 요소(G2)가 묻는다.
"""

import collections
import re
from typing import Any, Dict, Optional

import core
from core import norm_text, records, pct, section, table

# Any nonzero count here is a hard fault: an invented span is not a matter of
# degree. The band exists only so a single stray row does not read the same as
# a systematic failure.
FAIL_AT = 0.002

# `source` values that declare the entry was inferred, not quoted. An entry
# with one of these is allowed -- required, in fact -- to carry text: null.
# Taken from the vocabulary rather than written out here, so a source added to
# the schema cannot silently start reading as an invented span.
INFERRED_SOURCES = set(core.VOCAB.ANATOMY_SOURCES) - {"utterance"}

_WS = re.compile(r"\s+")


def _loose(t: str) -> str:
    """Whitespace- and punctuation-insensitive form, for the near-miss bucket."""
    return _WS.sub(" ", re.sub(r"[^a-z0-9 ]+", " ", t.lower())).strip()


def _fields(rec: Dict[str, Any]):
    """(field, text, source) for every span-bearing slot in the record."""
    for p in rec.get("propositions") or []:
        ent = p.get("entity") or {}
        yield "entity.text", ent.get("text"), "utterance"
        for a in p.get("anatomy") or []:
            yield "anatomy.text", a.get("text"), a.get("source") or "utterance"
        for d in p.get("descriptors") or []:
            yield "descriptor.text", d.get("text"), "utterance"
        for k in ("assertion", "comparison"):
            # A cue is legitimately absent -- "present" with no hedge word,
            # "comparison: none" with nothing to compare to. Whether a LABEL
            # requires a cue is metric G2's question, not this one's, so a
            # null cue is marked not-applicable here rather than a fault.
            yield f"{k}.cue", (p.get(k) or {}).get("cue"), "optional"


def measure(split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    per = collections.defaultdict(
        lambda: {"total": 0, "null_ok": 0, "null_bad": 0,
                 "exact": 0, "loose": 0, "absent": 0})
    examples = collections.defaultdict(list)
    bad_records = set()

    for rec in records(split, limit):
        utt = rec.get("utterance") or ""
        low, loose_utt = utt.lower(), _loose(utt)
        for field, text, source in _fields(rec):
            d = per[field]
            d["total"] += 1
            if text is None or text == "":
                # A null span is correct exactly when the entry says it was
                # inferred. On a `source: utterance` entry it is a fault of a
                # different kind: the entry claims a quotation it does not have.
                if source in INFERRED_SOURCES or source == "optional":
                    d["null_ok"] += 1
                else:
                    d["null_bad"] += 1
                    bad_records.add(rec.get("utterance_id"))
                continue
            if norm_text(text) in low or text.lower() in low:
                d["exact"] += 1
            elif _loose(text) and _loose(text) in loose_utt:
                d["loose"] += 1
            else:
                d["absent"] += 1
                bad_records.add(rec.get("utterance_id"))
                if len(examples[field]) < 12:
                    examples[field].append((rec.get("utterance_id"), text, utt))

    return {"split": split, "per_field": dict(per), "examples": dict(examples),
            "bad_records": len(bad_records),
            "records": sum(1 for _ in records(split, limit))}


def render(res: Dict[str, Any], cfg=None) -> str:
    show_ex = cfg is None or cfg.shows_examples(res["split"])
    out = [section(f"G1  Span grounding  ({res['split']})")]
    rows = []
    for field, d in sorted(res["per_field"].items()):
        quoted = d["exact"] + d["loose"] + d["absent"]
        rows.append([field, d["total"], d["null_ok"], d["null_bad"],
                     d["exact"], d["loose"], d["absent"],
                     pct(d["absent"], quoted)])
    out.append(table(rows, ["field", "slots", "null (declared/optional)",
                            "null (claimed quote)", "exact", "whitespace/case",
                            "ABSENT", "% absent"]))
    out.append(
        "\n`exact` is a substring of the utterance. `whitespace/case` differs "
        "only in spacing or punctuation -- a normalization slip, not an "
        "invention. `ABSENT` is text that is not in the sentence in any form: "
        "the extraction made it up.\n"
        "\n`null (declared/optional)` is the schema working as designed -- "
        "`source: entity_semantics` on a pneumothorax pointing at the pleura "
        "the sentence never names, or an assertion with no hedge word to "
        "quote. `null (claimed quote)` is an anatomy entry that says "
        "`source: utterance` and then has no span to show.\n")

    for field, ex in sorted(res["examples"].items()):
        if not ex or not show_ex:
            continue
        out.append(f"\n**Invented `{field}` spans**\n")
        out.append(table([[uid, f"`{t}`", u] for uid, t, u in ex],
                         ["utterance_id", "span claimed", "utterance"]))
    return "\n".join(out) + "\n"


def run(cfg) -> core.Result:
    per = [measure(sp, cfg.limit) for sp in cfg.splits]

    def tot(r, key):
        return sum(d[key] for d in r["per_field"].values())

    body = core.summary(
        [[r["split"], f"{tot(r,'exact')+tot(r,'loose')+tot(r,'absent'):,}",
          f"{tot(r,'exact'):,}", f"{tot(r,'loose'):,}", f"{tot(r,'absent'):,}",
          f"{tot(r,'null_bad'):,}",
          pct(tot(r, "absent") + tot(r, "null_bad"),
              tot(r, "exact") + tot(r, "loose") + tot(r, "absent"))]
         for r in per],
        ["split", "quoted slots", "exact", "whitespace/case", "ABSENT",
         "null (claimed quote)", "% defective"],
        "`ABSENT` + `null (claimed quote)` are the defects; "
        "`whitespace/case` is a normalization slip, not an invention.")
    body += core.example_note(cfg.example_split) if cfg.example_split else ""
    body += "\n".join(render(r, cfg) for r in per)

    absent = sum(d["absent"] for r in per for d in r["per_field"].values())
    nullbad = sum(d["null_bad"] for r in per for d in r["per_field"].values())
    loose = sum(d["loose"] for r in per for d in r["per_field"].values())
    quoted = sum(d["exact"] + d["loose"] + d["absent"]
                 for r in per for d in r["per_field"].values())
    share = (absent + nullbad) / quoted if quoted else 0.0
    verdict = (core.PASS if not (absent or nullbad) else
               core.FAIL if share >= FAIL_AT else core.WARN)
    head = (f"{absent:,} invented spans + {nullbad:,} claimed-but-missing "
            f"({share:.2%} of {quoted:,} quoted slots); {loose:,} differ only "
            f"in whitespace or case")
    return core.Result(body, verdict, head,
                       {"absent": absent, "null_claimed": nullbad,
                        "loose": loose, "quoted_slots": quoted})


if __name__ == "__main__":
    print(render(measure(_sys.argv[1] if len(_sys.argv) > 1 else "test")))
