#!/usr/bin/env python3
"""Metric G2 -- does the cue support the label it was given?

`assertion` and `comparison` are the two fields a downstream reader trusts
absolutely: "absent" means the finding is not there, and a report that gets it
backwards is worse than one that never mentioned the finding. Both fields
carry a `cue` -- the word in the sentence that justifies the label -- which
makes them the only labels in the schema that can be checked against the text
without a gold standard.

Three disagreements, and they are not the same kind of problem:

  MISSING    the label needs a cue and has none. "absent" with no negation
             word quoted is an assertion resting on nothing.
  MISMATCHED the cue exists but is not a word that supports that label -- a
             negation word cited for a "present" finding, or vice versa.
  UNCITED    the sentence carries a negation or hedge word and NO proposition
             in it is absent or uncertain. This is the dangerous direction:
             a missed negation flips a finding from ruled-out to present.

The first two are precision, the third is recall, and only the third can be
wrong while every individual proposition looks fine -- which is why it is
counted per record rather than per proposition.

Cue vocabularies come from `Prompt2/ontology.py` (NEGATION_CUES,
UNCERTAINTY_CUES), the same tables step 3 validates against, so this metric
cannot disagree with the pipeline about what a negation word is.

    python3 m12_cue_agreement.py [split]
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'G2'
TITLE = 'Cue / label agreement (assertion and comparison)'
SCOPE = 'split'
ASKS = ("Does the quoted cue actually support the assertion or comparison "
        "label? And does a negated sentence have a negated proposition?")

MEANS = """## 한 줄로

**"없다"고 적고 근거로 댄 단어가 진짜 부정어인지 확인한다.**
그리고 반대로, **문장은 부정하는데 아무 명제도 "없음"이 아닌 경우**를 찾는다.

## 왜 이 두 칸이 특별한가

명제에는 두 개의 중요한 칸이 있다.

| 칸 | 값 | 뜻 |
|---|---|---|
| `assertion` | present / absent / uncertain | 있다 / 없다 / 아마도 |
| `comparison` | new / stable / improved … | 새로 생김 / 그대로 / 좋아짐 |

**`absent`(없다) 를 뒤집으면 환자 정보가 정반대가 된다.** 그 소견을 아예 언급
안 한 것보다 나쁘다. "기흉 없음"을 "기흉 있음"으로 읽으면 큰일이다.

다행히 두 칸에는 **근거 단어(cue)** 가 같이 적힌다 — 그렇게 판단한 이유가 된
문장 속 단어다. 그래서 **정답 없이 본문과 맞대 볼 수 있는 스키마 내 유일한
칸**이다.

    "No pneumothorax."
       assertion = absent,  cue = "No"      ← 근거가 맞다 ✅

## 세 종류의 어긋남

| 종류 | 뜻 | 예 |
|---|---|---|
| **근거 없음** | "없다"고 했는데 근거 단어가 비어 있다 | 근거 없이 서 있는 판단 |
| **근거 불일치** | 근거는 있는데 부정어가 아니다 | "없다"의 근거로 `"removal"` 을 댐 |
| **미인용** | 문장은 부정하는데 **어떤 명제도** "없음"이 아니다 | 부정을 통째로 놓침 |

앞의 둘은 *"있는 게 틀렸나"*, 셋째는 *"빠뜨렸나"* 다.
**셋째만이 개별 명제는 전부 멀쩡해 보이는 채로 틀릴 수 있어서** 명제가 아니라
문장 단위로 센다.

다만 셋째는 **결함이 아니라 후보**다. `"No significant change"`(큰 변화 없음)
같은 문장은 부정어가 있지만 **아무 소견도 부정하지 않는다.**

## ⚠️ 개발 중에 지표를 뒤집는 오답을 잡았다

근거 단어를 **부분 문자열**로 맞췄더니 이런 일이 생겼다.

    "not" 이 "noted" 안에 들어 있다
    → cue = "noted"(언급됨) 인 정상 명제 26건이
       "있다고 해 놓고 부정어를 근거로 댔다" 는
       이 요소에서 가장 심한 코드로 찍혔다

**단어 경계로 고친 뒤 0건이 되었고**, 같은 원인으로 부풀어 있던 "미인용" 도
226 → 24 로 내려갔다. **근거 단어 맞추기는 언제나 단어 경계로.**

## 실제로 남은 진짜 문제

    "Interval removal of a right chest tube."   (우측 흉관 제거함)
       assertion = absent,  cue = "removal"

**판독은 맞다.** 제거했으니 지금은 없다. 그런데 **부정어 목록에 "제거/발관"
계열 단어가 없어서** 어긋남으로 잡힌다. 이건 **표를 고쳐야 하는 진짜 구멍**이다.

## "뒤집힘" 은 따로 센다

`present`(있다) 인데 부정어를 근거로 댄 경우를 **뒤집힘(flip)** 이라 부른다.
**건당 심각도가 가장 높지만 수는 아주 적다.** 그래서 한 건이라도 있으면
headline 에 반드시 적되, **패턴이라고 부를 만큼 쌓였을 때만** 판정을 떨어뜨린다.
두 건 때문에 "이걸 고치기 전엔 나머지 숫자가 무의미"라는 판정을 주는 건
과하기 때문이다.
"""

import collections
import re
from typing import Any, Dict, Optional

import core
from core import ONT, records, pct, section, table

# Share of propositions whose cue disagrees with its label. An assertion is
# the field a reader trusts most, so the bands are the tightest in the audit.
WARN_AT = 0.01
FAIL_AT = 0.05

# Assertion flips -- `present` citing a negation word -- get their own band,
# because they are severe per instance and rare in aggregate. An earlier draft
# failed the whole metric on any flip at all, which put FAIL ("fix this before
# the other numbers mean anything") on two rows out of twenty thousand. A flip
# always shows up in the headline; it fails the metric only once there are
# enough of them to be a pattern rather than a pair of sentences.
FLIP_FAIL_AT = 0.001

NEG = {c.lower() for c in ONT.NEGATION_CUES}
UNC = {c.lower() for c in ONT.UNCERTAINTY_CUES}
CMP = {c.lower() for c in ONT.COMPARISON_CUES}

# Built after _phrase_re is defined; see below.


def _phrase_re(words) -> "re.Pattern":
    """Word-boundary alternation over a cue vocabulary, longest phrase first.

    Plain substring matching is wrong here and wrong in a way that inverts the
    metric: "not" is inside "noted", so `cue: "noted"` on a PRESENT finding was
    read as a negation word cited for a present label -- the single most severe
    code this metric has -- on 26 perfectly correct rows. Boundaries, always.
    """
    return re.compile(r"(?<![a-z])(?:" +
                      "|".join(re.escape(w) for w in
                               sorted(words, key=len, reverse=True)) +
                      r")(?![a-z])")


def _supports(cue: str, pattern: "re.Pattern") -> bool:
    """A cue supports a label when one of the label's words occurs in it as a
    word -- "no evidence of" is quoted inside several longer phrasings."""
    c = (cue or "").lower().strip()
    return bool(c) and bool(pattern.search(c))


_NEG_RE = _phrase_re(NEG)
_UNC_RE = _phrase_re(UNC)


# Function words carry no evidence, and letting them match would excuse the
# exact rows this licence must keep: "suggestive of" and "Resolution of" share
# "of" and nothing else.
_CUE_STOP = frozenset({"of", "the", "a", "an", "in", "on", "at", "is", "are",
                       "was", "has", "have", "been", "be", "to", "with",
                       "and", "or", "for", "from", "interval", "now"})
_CUE_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _content(cue: str) -> set:
    return {t for t in _CUE_TOKEN_RE.findall((cue or "").lower())
            if t not in _CUE_STOP}


def _resolution_licenses_absent(prop) -> bool:
    """rule 12: "resolved -> resolved and assertion=absent".

    A finding that went away is absent, and the word that says so is a
    RESOLUTION word, not a negation -- "Interval removal of a right chest
    tube", "Normalization of ...". Demanding a negation cue there flags data
    the prompt's own rule 12 asked for: 27 of 35 such rows already carry
    comparison=resolved.

    The licence is deliberately narrow. It is not enough that the proposition
    compares as resolved; the assertion must be citing THAT resolution -- the
    two cues have to share a word. Otherwise
        "Improved aeration ..., suggestive of resolving atelectasis"
            assertion {absent, "suggestive of"}  comparison {resolved, "resolving"}
    would be excused, and quoting a hedge as the negation cue is a real rule 10
    defect that this metric exists to catch. 2026-09-17.
    """
    c = prop.get("comparison") or {}
    if c.get("label") != "resolved":
        return False
    acue = ((prop.get("assertion") or {}).get("cue") or "").lower()
    ccue = (c.get("cue") or "").lower()
    return bool(_content(acue) & _content(ccue))


def measure(split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    stat = collections.Counter()
    examples = collections.defaultdict(list)

    def note(kind, uid, detail, utt):
        stat[kind] += 1
        if len(examples[kind]) < 10:
            examples[kind].append((uid, detail, utt))

    for rec in records(split, limit):
        utt = rec.get("utterance") or ""
        low = utt.lower()
        props = rec.get("propositions") or []
        for p in props:
            a = p.get("assertion") or {}
            lab, cue = a.get("label"), a.get("cue")
            stat["assertions"] += 1
            if lab == "absent":
                if not cue:
                    note("absent_no_cue", rec.get("utterance_id"),
                         f"{p.get('id')}: absent, cue null", utt)
                elif not _supports(cue, _NEG_RE) and \
                        not _resolution_licenses_absent(p):
                    note("absent_bad_cue", rec.get("utterance_id"),
                         f"{p.get('id')}: absent, cue `{cue}`", utt)
            elif lab == "uncertain":
                if not cue:
                    note("uncertain_no_cue", rec.get("utterance_id"),
                         f"{p.get('id')}: uncertain, cue null", utt)
                elif not _supports(cue, _UNC_RE):
                    note("uncertain_bad_cue", rec.get("utterance_id"),
                         f"{p.get('id')}: uncertain, cue `{cue}`", utt)
            elif lab == "present" and cue and _supports(cue, _NEG_RE):
                note("present_negation_cue", rec.get("utterance_id"),
                     f"{p.get('id')}: present, cue `{cue}`", utt)

            c = p.get("comparison") or {}
            clab, ccue = c.get("label"), c.get("cue")
            stat["comparisons"] += 1
            if clab and clab not in ("none", "unclear") and not ccue:
                note("comparison_no_cue", rec.get("utterance_id"),
                     f"{p.get('id')}: comparison {clab}, cue null", utt)

        # -- the recall direction, per record -------------------------------
        if props:
            if _NEG_RE.search(low) and not any(
                    (p.get("assertion") or {}).get("label") == "absent"
                    for p in props):
                note("negation_uncited", rec.get("utterance_id"),
                     f"sentence negates; no proposition is absent", utt)
            if _UNC_RE.search(low) and not any(
                    (p.get("assertion") or {}).get("label") == "uncertain"
                    for p in props):
                note("hedge_uncited", rec.get("utterance_id"),
                     f"sentence hedges; no proposition is uncertain", utt)
            stat["records"] += 1

    return {"split": split, "stat": stat, "examples": dict(examples)}


PRECISION = [
    ("absent_no_cue", "`absent` with no cue quoted"),
    ("absent_bad_cue", "`absent` citing a word that is not a negation"),
    ("uncertain_no_cue", "`uncertain` with no cue quoted"),
    ("uncertain_bad_cue", "`uncertain` citing a word that is not a hedge"),
    ("present_negation_cue", "`present` citing a NEGATION word -- a flip"),
    ("comparison_no_cue", "a comparison other than `none` with no cue"),
]
RECALL = [
    ("negation_uncited", "sentence carries a negation; nothing is `absent`"),
    ("hedge_uncited", "sentence carries a hedge; nothing is `uncertain`"),
]


def render(res: Dict[str, Any], cfg=None) -> str:
    show_ex = cfg is None or cfg.shows_examples(res["split"])
    st = res["stat"]
    out = [section(f"G2  Cue / label agreement  ({res['split']})")]

    out.append("\n**Precision -- the cue does not support the label** "
               f"(over {st['assertions']:,} propositions)\n")
    out.append(table([[k, desc, f"{st[k]:,}", pct(st[k], st["assertions"])]
                      for k, desc in PRECISION],
                     ["code", "what it means", "count", "of propositions"]))

    out.append("\n**Recall -- the sentence says it and no proposition does** "
               f"(over {st['records']:,} records)\n")
    out.append(table([[k, desc, f"{st[k]:,}", pct(st[k], st["records"])]
                      for k, desc in RECALL],
                     ["code", "what it means", "count", "of records"]))
    out.append(
        "\n> The recall rows are candidates, not defects. `\"No change\"` and "
        "`\"not otherwise specified\"` carry a negation word that negates no "
        "finding, and a hedge can sit on a comparison rather than on an "
        "assertion. They are ranked here because a genuine miss in this "
        "direction flips a finding from ruled-out to present, which is the "
        "worst error this schema can make.\n")

    for k, desc in PRECISION + RECALL:
        ex = res["examples"].get(k)
        if not ex or not show_ex:
            continue
        out.append(f"\n**`{k}`** -- {desc}\n")
        out.append(table([[uid, d, u] for uid, d, u in ex],
                         ["utterance_id", "what", "utterance"]))
    return "\n".join(out) + "\n"


def run(cfg) -> core.Result:
    per = [measure(sp, cfg.limit) for sp in cfg.splits]
    body = core.summary(
        [[r["split"], f"{r['stat']['assertions']:,}",
          f"{sum(r['stat'][k] for k, _d in PRECISION):,}",
          pct(sum(r["stat"][k] for k, _d in PRECISION), r["stat"]["assertions"]),
          f"{r['stat']['present_negation_cue']:,}",
          f"{r['stat']['negation_uncited']:,}",
          f"{r['stat']['hedge_uncited']:,}"] for r in per],
        ["split", "propositions", "cue/label 불일치", "%", "flips",
         "negation uncited", "hedge uncited"],
        "`flips` (present citing a negation word) is the severe column: it is "
        "the one defect here that reverses a finding rather than weakening it.")
    body += core.example_note(cfg.example_split) if cfg.example_split else ""
    body += "\n".join(render(r, cfg) for r in per)

    st = collections.Counter()
    for r in per:
        st.update(r["stat"])
    bad = sum(st[k] for k, _d in PRECISION)
    share = bad / st["assertions"] if st["assertions"] else 0.0
    flips = st["present_negation_cue"]
    flip_share = flips / st["assertions"] if st["assertions"] else 0.0
    verdict = (core.FAIL if share >= FAIL_AT or flip_share >= FLIP_FAIL_AT else
               core.WARN if share >= WARN_AT or flips else core.PASS)
    head = (f"{bad:,} cue/label disagreements ({share:.2%} of "
            f"{st['assertions']:,} propositions), {flips:,} of them assertion "
            f"flips; {st['negation_uncited']:,} sentences negate with nothing "
            f"marked absent")
    return core.Result(body, verdict, head,
                       {"disagreements": bad, "share": share,
                        "flips": flips, "flip_share": flip_share,
                        "negation_uncited": st["negation_uncited"]})


if __name__ == "__main__":
    print(render(measure(_sys.argv[1] if len(_sys.argv) > 1 else "test")))
