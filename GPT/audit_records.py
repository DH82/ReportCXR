#!/usr/bin/env python3
"""jsonl/Prompt/test_reviewed.jsonl -> a per-report verdict, field by field.

DETECTION ONLY. This pass says what is wrong and never says what it should be
instead -- repair is GPT/repair.py, over the flagged records alone. Asking one
call to do both biases it in two directions at once: the cost of rewriting a
record suppresses flags, and having to produce a correction manufactures them.

It is also the SECOND layer. GPT/precheck.py runs first and decides everything
a regex can decide -- spans, enums, source/text coupling, over-specified
labels, section fillers -- and this prompt is told not to raise any of it. What
is left is the part that needs a reader:

    does the sentence say something the JSON does not?     (dropped)
    does the JSON say something the sentence does not?     (hallucinated)
    is the assertion, the comparison, the side, the
      descriptor what the words actually mean?

`dropped` is the code worth the most here and the one an audit design can most
easily destroy: show a model a sentence next to a list of propositions and it
reads to confirm the list. So the model must ENUMERATE what the sentence claims
before it is allowed to look at the verdict, and that enumeration is returned
and stored -- it is checkable evidence, not a warm-up.

Direction: Verify/ scores the same file with 17 mechanical metrics and cannot
read. A record can pass all 17 while asserting a finding the sentence negates,
dropping half a compound sentence, or hanging a finding on the wrong lung.

Why a whole report per call: the model sees the utterances of one study
together, so a device named two ways across neighbouring sentences, or an
anatomy carried over from the sentence before, is visible at all. Splitting
reports into batches of utterances hides exactly those.

    export OPENAI_API_KEY=...
EVERY REPORT IS ASKED K TIMES (default 3) AND THE ANSWERS ARE VOTED. This is
not caution, it is arithmetic: the model refuses `temperature`, so it runs at
its default sampling and the same report genuinely gets different answers.
Measured on three identical runs of three reports, before this was added --
21 utterances, 19 of them the same status all three times, but of the three
distinct issues raised, ONE appeared in all three runs, one in two, one in a
single run. A single pass is therefore not a list of this file's defects, it
is one draw. Worse, `claims` itself moved in 7 of 21 utterances (one sentence
read as 5, then 4, then 6 assertions), and `dropped` is defined as a claim
with no proposition -- so the most valuable code is the least stable one.

Voting does not make the model right. It makes the run REPEATABLE, and it
turns disagreement into a number you can threshold instead of a coin you
cannot see. An issue that shows up once in three is kept out of the report and
counted, not silently dropped.

    python3 audit_records.py --limit 3 --dry-run   # print one prompt, call nothing
    python3 audit_records.py --limit 10            # 10 reports x 3 samples
    python3 audit_records.py --samples 1           # old behaviour, one draw
    python3 audit_records.py                       # all 233 x 3 = 699 calls

Outputs, under out/gpt_records/:
    samples.jsonl           one line per (report, sample). RAW, never voted:
                            the cache, and the thing a changed voting rule is
                            recomputed from without asking anything again
    verdicts.jsonl          the vote. One line per report, each issue carrying
                            `votes`
    by_report/<id>.json     per report: every utterance, what the model read
                            out of the sentence, its per-field verdicts, and
                            the mechanical findings from precheck
    flagged.jsonl           only the failing fields, one line each -- what
                            repair.py consumes and what a human reviews
    flagged.md              the same, readable, grouped by defect kind
    audit.md                counts

Run GPT/precheck.py first (this calls it automatically if its output is
missing). Then GPT/goldset.py, because a judge whose precision per code is
unknown produces numbers nobody can act on.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as futures
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "Prompt2"))

from vocabulary import (ANATOMY_ROLES, ANATOMY_SOURCES, ASSERTION_LABELS,
                        COMPARISON_LABELS, DESCRIPTOR_TYPES, ENTITY_TYPES,
                        LATERALITY, ZONES)                      # noqa: E402
import precheck                                                 # noqa: E402

RECORDS = os.path.join(REPO, "jsonl", "Prompt", "test_reviewed.jsonl")
OUTDIR = os.path.join(REPO, "out", "gpt_records")

MODEL = os.environ.get("OPENAI_AUDIT_MODEL", "gpt-5.6-luna")
WORKERS = 4


def arm_of(records_path: str) -> str:
    """".../jsonl/<arm>/<split>.jsonl" -> "<arm>".

    Every GPT/*.py script's cache lives under out/gpt_records/, and until
    2026-09-16 that directory was flat -- shared by every arm. A --rebuild
    for Prompt21 silently served up Prompt (v1)'s cached samples, because
    samples.jsonl only keyed on (report_id, sample_index), which two arms
    share. The fix is this: every output path is under
    out/gpt_records/<arm>/, and the arm is read from --records rather than
    typed twice, so it cannot drift from what was actually asked about.
    """
    parts = os.path.normpath(records_path).split(os.sep)
    try:
        i = parts.index("jsonl")
        return parts[i + 1]
    except (ValueError, IndexError):
        return "Prompt"


def out_for(records_path: str, explicit_out: str | None) -> str:
    """explicit_out 이 주어졌으면 그대로, 아니면 arm 하위로."""
    if explicit_out:
        return explicit_out
    return os.path.join(OUTDIR, arm_of(records_path))

# The fields a verdict can name. One row of a report's scorecard is one of
# these on one proposition -- finer than "this record is wrong", coarse enough
# that two readers agree on where a defect lives.
# The fields a verdict can name. `derived_from` and section membership are
# absent on purpose: precheck.py resolves the first and validate.py's
# `section_conflict` decides the second, and both need other sentences to
# judge, which an utterance-level reader does not have.
FIELDS = ["entity.text", "entity.label", "entity.type", "anatomy",
          "descriptors", "assertion", "comparison", "proposition_set"]

# The closed answer space. Every code is a reading failure -- none of them is
# something a schema check or a table lookup could have caught.
VERDICTS = {
    "hallucinated":    "asserts something the utterance does not support",
    "dropped":         "the utterance states something with no proposition for it",
    "wrong_assertion": "present/absent/uncertain is wrong, or the cue does not "
                       "carry the negation/hedge it is credited with",
    "wrong_comparison":"the comparison label or cue misreads the change (or "
                       "invents one)",
    "wrong_anatomy":   "wrong site, laterality, zone, or role",
    "wrong_entity":    "the entity label, text or type is not what the phrase names",
    "wrong_descriptor":"a descriptor is missing, has the wrong type, or its "
                       "label misreads the modifier",
    "bad_split":       "ONE finding written as two propositions that duplicate "
                       "it. NOT a proposition that carries several anatomy "
                       "entries: the extraction rules require exactly that "
                       "when entity, assertion and descriptors are the same "
                       "and only the site differs",
}
# `bad_warning` 은 없다. 세 조건(한정 부정 · 하한 명시 · 판독 제한)이 전부
# 필드 조회와 어휘 매칭으로 끝나므로 precheck.py 가 통째로 가진다. 여기에
# 남겨 두면 지시가 충돌한다 -- 같은 프롬프트가 "이건 이미 결정됐다"고 하면서
# 판단 규칙을 함께 주게 된다.

# Severity is not confidence. Confidence says how sure the judge is that the
# defect is real; severity says how much it matters if it is. A review queue
# sorted by only one of them reads the wrong records first.
SEVERITY = {
    # 2026-09-17 측정: 원시 판정 1,260건에서 blocking 이 **0회** 쓰였다.
    # 원인은 이 표가 **한 번도 전송되지 않았다**는 것이다 -- 스키마가 enum
    # 키 세 낱말만 보냈고, 판정자는 뜻을 추측해야 했다. VERDICTS 는
    # USER_HEADER 의 {codes} 로 설명이 가는데 이 표만 빠져 있었다. 이제
    # 함께 보내고, 어느 코드가 blocking 인지도 코드 이름으로 못박는다.
    "blocking": "changes what the record clinically asserts. USE IT, AND ONLY "
                "IT, FOR: hallucinated; dropped; wrong_assertion where "
                "present/absent is flipped; wrong_anatomy where laterality is "
                "flipped. Those four are blocking by definition -- do not "
                "downgrade one to major because the rest of the record looks "
                "careful",
    "major":    "loses or distorts information a downstream query would use",
    "minor":    "a defensible reading that is still not the best one",
}



# ---------------------------------------------------------------- the prompt

SYSTEM_PROMPT = f"""You audit a structured extraction over chest-radiograph \
reports. You are given ONE report: its utterances in order, each with the \
section it was filed under and the propositions a model built from it.

A proposition is one finding, and its fields divide the work:

  entity        what is said to exist. type is one of: {', '.join(ENTITY_TYPES)}
  anatomy       where. `laterality` ({' | '.join(LATERALITY)}) and `zone`
                carry side and region; `role` ({' | '.join(ANATOMY_ROLES)})
                says how the structure relates to the entity -- site is where
                a finding is, tip_location where a device ends, insertion_site
                where it enters. `source` is one of
                {', '.join(ANATOMY_SOURCES)}:
                  utterance          the text named the structure
                  entity_semantics   implied by the finding (pneumothorax ->
                                     pleura)
                  section_context    taken from the section heading, a
                                     legitimate weak source: the heading may
                                     fill a broad anatomy nothing else settles
                  linked_proposition inherited from the proposition this one
                                     derives from
                The last three are legitimate and are NOT hallucinations.
                `text` is null for them precisely because the sentence did not
                name the structure.
  descriptors   properties of the finding: {', '.join(DESCRIPTOR_TYPES)}
  assertion     {' | '.join(ASSERTION_LABELS)}, with the word in the utterance
                that decided it (`cue`). A CUE IS REQUIRED ONLY FOR "absent"
                AND "uncertain". "present" is exempt by design -- a finding is
                asserted by being named at all, and quoting a word for it
                fills the field with noise. `{{"label": "present", "cue": null}}`
                is correct and complete, including when the sentence happens
                to contain "present", "is seen" or "noted".
  comparison    {' | '.join(COMPARISON_LABELS)}, with its cue -- only when the
                sentence compares to a prior study
  derived_from  the proposition this one elaborates. A differential ("A or B")
                hangs its candidates off the observation they explain, so
                several propositions over one clause is expected.
  warnings      per-utterance notes

HOW TO READ EACH UTTERANCE. Do this in order. The order is the method, not a
formality: a list of propositions read first becomes the list you check
against, and whatever the sentence says that is not on it stops being visible.

  STEP 1. Read the utterance and NOTHING ELSE. Enumerate, in `claims`, every
          separate thing the sentence asserts, denies, or hedges about the
          patient or the image -- one short phrase each, in the sentence's own
          words. "Clear lungs without focal consolidation" is two claims.
          "Small effusion, unchanged" is one claim plus a comparison.
          Bookkeeping is not a claim (see SECTION FILLERS below).
  STEP 2. Now look at the propositions, and match each claim to one. A claim
          with no proposition is `dropped`. A proposition matching no claim is
          `hallucinated`.
          Two exemptions, which exist so that this step and the mechanical
          layer do not demand opposite things:
            - a section filler owes nothing (see below). The tell is a meta
              predicate about the REPORT -- "reported", "specified",
              "noted in this section", "not applicable" -- with no anatomy
              or finding named.
            - an utterance that names no anatomy and no finding, and only
              states a comparison ("Relatively unchanged."), owes nothing.
  STEP 3. For the matched pairs, check field by field.

ALREADY DECIDED MECHANICALLY -- DO NOT RAISE ANY OF THESE. A separate program
decides them by field lookup, span comparison or table lookup, so it does not
miss cases and you cannot add anything by agreeing. Its findings for this
report are shown under `precheck` where they exist. Raising them again adds
noise and nothing else:
{{mechanical}}

ALSO CHECKED, BUT NOT SETTLED. The same program only guesses at these, and is
wrong in both directions, so you ARE the safety net for them -- raise one if
you see it whether or not `precheck` names it, and say plainly in `note` if
`precheck` named it and you disagree:
{{advisory}}

  - AN OVER-SPECIFIED LABEL. precheck decides this one, and where the two of
    you would disagree, it is because the line runs here: a label that
    repeats what a FIELD already holds is over-specified (left_lower_lobe --
    side is `laterality`; severe_edema -- `descriptors`; normal_heart_size --
    a normality descriptor; tip_in_mid_svc -- `anatomy.role`). A label that
    merely names a region FINELY is granularity, and correct: lower_lobe,
    apical, retrocardiac, subpleural. The test is whether some other field in
    the same proposition already says it.

ALSO NOT A DEFECT. Each line below is one way a labelled audit of this same
file went wrong, with the count of issues it produced:

  - A SPAN ALREADY SPENT. If a phrase is `assertion.cue` or
    `comparison.cue`, it has been recorded. Do not then ask for a descriptor
    over the same words -- that is the same fact in two fields, which is the
    defect this project is built to avoid, not the fix for one. (13)
    "Endotracheal tube in place" with cue "in place" is complete.
  - "appears", "appear", "seems", "is seen", "is noted", "consistent with",
    "compatible with" are NOT hedges. They are how an observation is stated.
    An assertion of "present" beside them is right. (10)
  - "persistent", "remains", "continues" ARE comparisons with the prior
    study, even when no prior study is named -- that is what the word does
    in a chest radiograph report. comparison "stable" is correct for them.
    `chronicity` is for the course of the lesion itself: acute, chronic,
    old, longstanding. (19)
  - SEVERAL ANATOMY ENTRIES ON ONE PROPOSITION. Same entity, same
    assertion, same descriptors, two sites -> one proposition with two
    anatomy entries. That is the rule, not a merge defect. (16)
  - A LABEL NORMALISED TO A STANDARD TERM. Mapping a surface phrase onto
    the project's canonical label is the intended behaviour. Judge it by
    STRENGTH OF CLAIM, not by wording: a label weaker than or equal to the
    utterance passes; only a label that claims MORE than the sentence
    ("numerous" -> "innumerable") is a defect. (3)
  - `entity.type` disputes. finding vs disease has no operational
    definition in this project yet -- there is no answer to "if atelectasis
    is a disease, why is effusion a finding" -- so an argument about it is
    an argument with an undefined term. Leave type alone. (2)
  - A COMPARISON INHERITED THROUGH `derived_from`. A proposition that
    interprets another may carry its parent's comparison. (3)
  - A NORMAL STATEMENT ABOUT A STRUCTURE. When `entity.type` is
    `anatomical_state`, "normal" and "unremarkable" belong in a
    `normality` descriptor with assertion "present". Do not ask for
    assertion "absent" -- that would say the structure itself is missing. (2)

ALSO NOT A DEFECT:
  - A SECTION FILLER. The report builder writes one bullet per heading even
    when no sentence was filed there: "No findings specified.", "No
    significant findings reported.", "No abnormalities noted.", "Not
    applicable". These mean the section is EMPTY, not that the region is
    normal, and zero propositions is correct for them. A named structure
    changes this -- "No pleural abnormalities." names the pleura and does owe
    a proposition.
  - laterality "bilateral" on a structure bilateral by nature: lungs, pleura,
    hila, ribs, lung bases, pulmonary vasculature, lung interstitium, lung
    parenchyma, airspaces, chest wall.
  - a label spelled differently than you would spell it, same meaning.
  - terseness, or what a radiologist "would have written" instead.

TIE-BREAKS. Where two answers are both arguable, these decide, so that two
readings of the same sentence agree:

  descriptor type. This chooses the CATEGORY OF ONE MODIFIER. It does not
  say how many descriptors a proposition has: take each modifier the sentence
  writes, separately, and give it the first category below that it matches.
  "two small nodules" is TWO descriptors -- "two" is number, "small" is size.
  Order:
    measurement   a number with a unit ("8 mm")
    number        a count ("two", "multiple")
    size          how big ("small", "large", "enlarged")
    severity      how bad ("mild", "moderate", "severe", "marked")
    extent        how much of the structure ("focal", "patchy", "diffuse",
                  "extensive") -- how much of ONE site
    distribution  where within/among structures ("bibasilar", "multifocal",
                  "perihilar", "left greater than right") -- across sites
    morphology    what shape ("rounded", "linear", "nodular")
    chronicity    how long ("chronic", "acute", "persistent", "new to this
                  admission" when no prior study is named)
    normality     "normal", "clear", "unremarkable", "within normal limits"
    device_position how a device sits ("in place", "coiled", "standard")
    other         none of the above
  "focal" is extent, not distribution: it says how much of one site, not which
  sites. "multifocal" is distribution -- several sites is a where.

  site vs relative_location is decided by the preposition, not by anatomy:
    relative_location   over, overlying, projecting over, below, beneath,
                        above, subjacent to, adjacent to, abutting,
                        anterior/posterior to, behind
    site                in, within, at, involving, in the region of,
                        throughout, of

  THIS PREPOSITION TEST IS FOR FINDINGS, NOT FOR WHERE A DEVICE ENDS. The
  structure a catheter, tube, line or drain terminates at is
  role "tip_location" whatever preposition names it -- "tip in the mid SVC",
  "tip 4 cm above the carina" and "tip at the cavoatrial junction" are all
  tip_location. The extraction spec gives the second of those as its own
  worked example, so a record that writes
      anatomy {{label "carina", role "tip_location"}}
      + descriptor {{type "measurement", text "4 cm"}}
  is following the spec exactly. Do not read "above" and ask for
  relative_location there. (This paragraph exists because the test above,
  applied to a device tip, produced a unanimous wrong flag.)

  A VESSEL SEGMENT'S `zone` IS A TABLE LOOKUP, NOT A READING. Along a vessel
  or catheter path the zone vocabulary is exactly proximal | mid | distal,
  and the project's table maps the words onto it: superior, upper and high
  -> "proximal"; inferior, lower and low -> "distal". So "superior cavoatrial
  junction" with zone "proximal" is the table working, not a misreading of
  "superior". Raise it only if the segment is the wrong END of the vessel.

  A WORD THE PROJECT'S TABLE ALREADY TYPES IS NOT YOURS TO RE-TYPE. The
  extraction runs against a fixed lexicon, and for a word in it the type is a
  decision already taken, not a reading. Where the report contains such words
  they are listed under `fixed types` in the user message. Do not raise
  `wrong_descriptor` for one of them on the ground that another category fits
  better -- that argument is with the table, not with this record. Raise it
  only if the word in THIS sentence is not being used in the sense the table
  names.
  A modifier named in none of the lists above takes the category of the
  question it answers -- "prominent" answers how big (size), "coarse" answers
  what shape (morphology), "mild-to-moderate" answers how bad (severity).
  Use "other" ONLY when no category's question fits at all. Do not use it as
  a shelf for words that are merely not listed.

  an adverb belongs to whatever word it stands next to. Do not reason about
  what it "usually" modifies -- apply this test.

  "Next to" means the NEAREST CONTENT WORD, reading forward, skipping
  function words (a, the, of, in) and words that themselves only modify the
  comparison ("interval", "further", "slightly" when it precedes another
  modifier). If that content word is a comparison or negation word, the
  adverb is part of THAT field's span and the finding gets no descriptor
  from it.
    "Marked improvement in edema"        -> nearest content word is
                                            "improvement": comparison. The
                                            edema's severity is UNSTATED.
    "Slight interval improvement in edema" -> "interval" is skipped; the
                                            nearest content word is
                                            "improvement": comparison. Not a
                                            severity descriptor on the edema.
                                            ("interval" before a change word
                                            is frequent in these reports.)
    "Grossly stable cardiac silhouette"  -> "stable": comparison.
    "No significant change in the opacity" -> "change": comparison.
    "Slight blunting ..., stable"        -> nearest content word is
                                            "blunting": severity descriptor.
                                            The comma and "stable" are a
                                            separate span.
    "Stable moderate cardiomegaly"       -> two modifiers, judged separately.
                                            "Stable" -> comparison.
                                            "moderate" -> nearest content word
                                            is "cardiomegaly": severity.

  a warning is owed under exactly these conditions and no others:
{{warning_conditions}}
  Any other missing note is not `bad_warning`.

THE BAR FOR `flagged`. This audit is deliberately ROUGH. It looks for records
that SAY WHAT THE SENTENCE DOES NOT, or MISS WHAT THE SENTENCE DOES. It does
not look for the best of several defensible encodings.

  One question decides it: could a careful reader of THIS sentence have
  written THIS record and been right? If yes, the status is `ok` -- even when
  another encoding is tidier, finer, or closer to what you would have chosen.
  You are not ranking encodings. You are catching claims that are not in the
  sentence.

  A coarser label that is still true passes. A field left null that the
  sentence never settled passes. A choice between two categories that the
  sentence does not decide is `abstain`, not `flagged`.

  THIS LENIENCY DOES NOT EXTEND TO THE TWO THAT MATTER. A record asserting
  something the sentence never said, or dropping something it plainly did,
  is the whole reason this pass exists. Being relaxed about encoding style is
  not being relaxed about those -- flag them at full strength, and do not
  talk yourself out of one because the rest of the record looks careful.

THE THREE STATUSES ARE NOT A SCALE OF CONFIDENCE. They say different things:

  ok        you read the sentence and the JSON matches it.
  flagged   you are taking a side: the JSON is wrong. `confidence` then says
            how strongly -- "low" still means you LEAN toward it being a
            defect, not that you are unsure whether to judge.
  abstain   you refuse to judge, because two readings of the sentence are
            BOTH defensible and the record is right under one and wrong
            under the other. This is not a weak flag. Put both readings in
            `abstain_reason`, and list in `issues` what would be wrong under
            the reading that fails, so the record can be found later.

`certainty` IS THE SAME DISTINCTION, ONE LEVEL DOWN, AND IT IS THE ONE YOU
WILL ACTUALLY NEED. `status` is per utterance, but an utterance routinely
carries one issue you are sure of and one that is merely arguable. When that
happens the status is `flagged` and the arguable issue has nowhere to go, so
it is filed as a defect and counted as one. Mark every issue:

  certainty "defect"     the sentence decides it, and the record is on the
                         wrong side.
  certainty "borderline" both encodings are defensible and nothing in THIS
                         sentence chooses between them. Say in `note` what
                         the other reading is.

A borderline issue is kept but is NOT counted as a defect. This is not a
softer flag -- it is the same refusal `abstain` makes, addressed to one
field instead of the whole utterance. In a labelled audit of this project,
32 of 94 false positives were exactly this: "either encoding is defensible".
They were written as defects because there was no other box to put them in.

A descriptor-type dispute over a word that is NOT in `fixed types` is the
commonest thing that should be "abstain" and is not. If the word is absent
from the table and two categories both answer a question it could be
answering -- "dense" is how-pronounced (severity) or what-texture
(morphology) -- there is nothing in the sentence that decides it. That is
two defensible readings, which is exactly certainty "borderline" (and
"abstain" if it is the only issue in the utterance). Flagging it as a defect
makes the count of `wrong_descriptor` a count of your taste.

Never use "abstain" for "probably fine" -- that is "ok". Never use
"flagged"+"low" for "I could not decide" -- that is "abstain". An abstain
costs nothing; a confident wrong flag costs a human the time to refute it,
and a flag that means "unsure" makes every count of that code meaningless.

DO NOT propose corrections. Another pass does that. Saying what is wrong is
this pass's whole job, and reaching for a fix here makes the flag itself worse.

Use nothing but this report as evidence. Answer for EVERY utterance_id given,
once, in the order received."""

SYSTEM_PROMPT = SYSTEM_PROMPT.replace(
    "{mechanical}",
    "\n".join(f"  {k:<30}{v}" for k, v in precheck.SUPPRESSED.items())
).replace(
    "{advisory}",
    "\n".join(f"  {k}" for k in sorted(precheck.ADVISORY)))


USER_HEADER = """Audit this report.

issue codes:
{codes}

field names (use exactly one per issue):
{fields}

certainty (required on every issue):
  defect      the sentence decides it and the record is on the wrong side
  borderline  both encodings are defensible; nothing in THIS sentence
              chooses. Kept, but not counted as a defect

severity (what it costs if the issue is real -- NOT how sure you are):
{severity}

confidence (how sure you are that it IS a defect):
  high | medium | low

report_id: {rid}
utterances ({k}):
"""


def record_block(rec: dict, mech: dict) -> str:
    """The sentence FIRST, then the JSON. Never the other way round -- the
    reading order is the anti-anchoring measure the prompt's STEP 1 relies on.
    """
    out = [f"utterance_id: {rec['utterance_id']}",
           f"  section: {rec['section']}",
           f"  utterance: {rec['utterance']}"]
    for p in rec["propositions"]:
        out.append("  " + json.dumps(p, ensure_ascii=False))
    if not rec["propositions"]:
        out.append("  (no propositions)")
    if rec.get("warnings"):
        out.append(f"  warnings: {'; '.join(rec['warnings'])}")
    found = mech.get(rec["utterance_id"]) or []
    if found:
        # 두 층을 한 줄에 합치면 안 된다. ADVISORY 는 시스템 프롬프트가
        # "너가 안전망이니 보이면 제기하라" 고 말하는 코드들인데, 여기서
        # "already decided -- do not raise" 라고 통보하면 발화 옆에 붙은
        # 이 줄이 이긴다. 2026-09-17 측정: precheck 이 지적한 119 발화 중
        # 57 발화(48%)가 ADVISORY 를 그렇게 통보받고 있었다.
        codes = {f["code"] for f in found}
        settled = sorted(codes & set(precheck.SUPPRESSED))
        advis = sorted(codes - set(precheck.SUPPRESSED))
        if settled:
            out.append("  precheck (already decided -- do not raise): "
                       + "; ".join(settled))
        if advis:
            out.append("  precheck (a GUESS, not settled -- agree or "
                       "disagree, and say which in `note`): "
                       + "; ".join(advis))
    return "\n".join(out)


def fixed_types(report: dict) -> str:
    """이 리포트가 실제로 쓴 서술자 중 표가 타입을 못박은 것만.

    표 전체(수백 항목)를 매번 보내는 것은 낭비이고, 안 보내면 모델이 표와
    다툰다 -- 3콜 시험에서 지적 5건 중 1건이 `elevated`->morphology 를
    뒤집으려 한 것이었고, 그건 system.py 의 예시이자 표의 값이다.
    """
    from ontology import DESCRIPTOR_LEXICON
    seen = {}
    for rec in report["records"]:
        for p in rec["propositions"]:
            for d in p["descriptors"]:
                key = " ".join((d.get("text") or "").lower().split())
                hit = DESCRIPTOR_LEXICON.get(key)
                if hit:
                    seen[key] = hit[0]
    if not seen:
        return ""
    body = ", ".join(f"{k} -> {v}" for k, v in sorted(seen.items()))
    return ("\nfixed types (the project lexicon already decides these; a "
            "better-fitting category is an argument with the table, not with "
            "this record):\n  " + body + "\n")


def build_user(report: dict, mech: dict) -> str:
    codes = "\n".join(f"  {k:<18}{v}" for k, v in VERDICTS.items())
    fields = "  " + ", ".join(FIELDS)
    # 이 표는 2026-09-17 까지 전송되지 않았다. enum 키만 나가고 뜻은 안
    # 나갔으므로 `blocking` 은 1,260 판정에서 0회였다.
    sev = "\n".join(f"  {k:<10}{v}" for k, v in SEVERITY.items())
    body = "\n\n".join(record_block(r, mech) for r in report["records"])
    return (USER_HEADER.format(codes=codes, fields=fields, severity=sev,
                               rid=report["id"], k=len(report["records"]))
            + fixed_types(report) + "\n" + body)


# The reply shape. `claims` is FIRST in `required` on purpose: the model
# generates keys in this order, so the enumeration is written before any
# verdict exists to anchor on. Moving it later silently removes the measure.
# There is no field for a correction: that is repair.py's pass.
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["report_id", "utterances"],
    "properties": {
        "report_id": {"type": "string"},
        "utterances": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                # KEY ORDER IS THE MECHANISM, not formatting. The model
                # generates keys in this order, so `claims` is written before
                # any verdict exists to anchor on, and `status` is written
                # only after the issues that justify it. Put `status` or
                # `issues` first and STEP 1-3 above become decoration.
                "required": ["utterance_id", "claims", "issues", "status",
                             "abstain_reason"],
                "properties": {
                    "utterance_id": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "STEP 1: what the sentence asserts, "
                                       "read before looking at the JSON",
                    },
                    "issues": {
                        "type": "array",
                        "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["proposition_id", "field", "verdict",
                                         "certainty", "severity",
                                         "confidence", "quote", "note"],
                            "properties": {
                                "proposition_id": {"type": "string"},
                                "field": {"type": "string", "enum": FIELDS},
                                "verdict": {"type": "string",
                                            "enum": list(VERDICTS)},
                                # defect | borderline. borderline 은 보관하되
                                # 결함으로 세지 않는다 -- utterance 단위
                                # `abstain` 이 닿지 못하는 자리다.
                                "certainty": {"type": "string",
                                              "enum": ["defect",
                                                       "borderline"]},
                                "severity": {"type": "string",
                                             "enum": list(SEVERITY)},
                                "confidence": {"type": "string",
                                               "enum": ["high", "medium",
                                                        "low"]},
                                "quote": {"type": "string"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "status": {"type": "string",
                               "enum": ["ok", "flagged", "abstain"]},
                    "abstain_reason": {"type": ["string", "null"]},
                },
            },
        },
    },
}


# ------------------------------------------------------------------- loading


def load_reports(path: str) -> list:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            for rec in doc.get("records", []):
                rec.setdefault("propositions", [])
                rec.setdefault("warnings", [])
            out.append(doc)
    return out


# -------------------------------------------------------------------- asking


class Judge:
    def __init__(self, model, effort, timeout, temperature=None):
        from openai import OpenAI
        self.client = OpenAI(timeout=timeout, max_retries=2)
        self.model, self.effort, self.temperature = model, effort, temperature
        self.calls = 0
        self.in_tokens = self.out_tokens = 0
        self.lock = threading.Lock()

    def ask(self, report: dict, mech: dict) -> dict:
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": build_user(report, mech)}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "report_audit",
                                                "strict": True,
                                                "schema": SCHEMA}},
        }
        if self.effort:
            kwargs["reasoning_effort"] = self.effort
        # Reasoning models reject `temperature`; sampling is opt-in.
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        rsp = self.client.chat.completions.create(**kwargs)
        data = json.loads(rsp.choices[0].message.content)
        with self.lock:
            self.calls += 1
            if rsp.usage:
                self.in_tokens += rsp.usage.prompt_tokens
                self.out_tokens += rsp.usage.completion_tokens

        # A reply about utterances we did not ask about is not an answer.
        want = {r["utterance_id"] for r in report["records"]}
        seen, kept = set(), []
        for u in data.get("utterances", []):
            if u["utterance_id"] in want and u["utterance_id"] not in seen:
                seen.add(u["utterance_id"])
                kept.append(u)
        missing = sorted(want - seen)
        if missing:
            print(f"[warn] {report['id']}: {len(missing)} unanswered",
                  file=sys.stderr)
        return {"report_id": report["id"], "utterances": kept,
                "unanswered": missing}


def run(jobs: list, judge: Judge, args, done_path: str) -> None:
    """jobs 는 (report, sample_index) 의 목록. 표본 하나가 호출 하나다."""
    lock = threading.Lock()
    fh = open(done_path, "a", encoding="utf-8")

    def work(job):
        rep, si = job
        for attempt in range(3):
            try:
                got = judge.ask(rep, args.mech)
                got["sample"] = si
                return got
            except Exception as exc:                     # noqa: BLE001
                if attempt == 2:
                    print(f"[error] {rep['id']}#{si} dropped: {exc}",
                          file=sys.stderr)
                    return None
                time.sleep(2 ** attempt)

    t0 = time.time()
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, got in enumerate(pool.map(work, jobs), 1):
            if got:
                with lock:
                    fh.write(json.dumps(got, ensure_ascii=False) + "\n")
                    fh.flush()
            print(f"[{i}/{len(jobs)}] {judge.calls} calls, "
                  f"{time.time() - t0:.0f}s", file=sys.stderr)
    fh.close()


# ------------------------------------------------------------------- voting


def vote(samples: list, k: int, threshold: float) -> dict:
    """K 개의 raw 응답 -> 하나의 합의.

    지적의 동일성은 (verdict, field) 로 본다. 같은 결함을 두 실행이 다른
    문장으로 설명하는 것은 흔들림이 아니고, 한 실행만 제기한 것은 흔들림이다.
    quote/note 처럼 자유 서술인 칸까지 일치를 요구하면 무엇도 합의되지 않는다.

    status 가 갈리면 abstain 으로 간다. 판정자 자신이 나뉘었다는 것이 바로
    "두 독법이 모두 방어 가능하다" 이고, 그게 abstain 의 정의다.
    """
    byu = collections.defaultdict(list)
    for si, sam in enumerate(samples):
        for u in sam["utterances"]:
            byu[u["utterance_id"]].append((si, u))

    out = []
    need = max(2, int(round(threshold * k))) if k > 1 else 1
    for uid, seen in byu.items():
        statuses = [u["status"] for _, u in seen]
        sc = collections.Counter(statuses)
        top, n = sc.most_common(1)[0]
        status = top if n * 2 > len(seen) else "abstain"

        # 득표는 **서로 다른 표본의 수**다. 한 표본이 p1 과 p2 에 같은 종류를
        # 지적하면 그것은 두 결함이지 두 표가 아니다 -- 세어 보니 실제로
        # 25건 있었고, 그 탓에 "9/3" 같은 득표가 나왔다. 그래서 명제 id 를
        # 키에 넣고(데이터에서 온 값이라 표본 간에 안정적이다), 같은 키는
        # 표본당 한 번만 센다.
        voters = collections.defaultdict(set)
        inst = {}
        for si, u in seen:
            for i in u["issues"]:
                key = (i.get("proposition_id") or "", i["verdict"], i["field"])
                voters[key].add(si)
                inst.setdefault(key, []).append(i)
        votes = collections.Counter({k: len(v) for k, v in voters.items()})

        issues, rejected, borderline = [], [], []
        for key, n_v in votes.most_common():
            group = inst[key]
            pick = dict(group[0])
            # severity 와 confidence 는 최빈값. 한 실행의 기분이 아니라
            # 세 실행이 공통으로 본 무게여야 한다.
            for f in ("severity", "confidence", "certainty"):
                pick[f] = collections.Counter(
                    g.get(f) or ("defect" if f == "certainty" else None)
                    for g in group).most_common(1)[0][0]
            pick["votes"] = f"{n_v}/{k}"
            pick["vote_n"] = n_v
            if n_v < need:
                rejected.append(pick)
            elif pick.get("certainty") == "borderline":
                # 문턱은 넘었지만 결함이 아니다. 버리지도 세지도 않는다.
                borderline.append(pick)
            else:
                issues.append(pick)

        claim_lists = [u.get("claims", []) for _, u in seen]
        out.append({
            "utterance_id": uid,
            "claims": max(claim_lists, key=len) if claim_lists else [],
            "claims_per_sample": [len(c) for c in claim_lists],
            "claims_stable": len(set(len(c) for c in claim_lists)) == 1,
            "issues": issues,
            "borderline_issues": borderline,  # 양쪽 다 방어 가능한 것
            "rejected_issues": rejected,      # 문턱을 못 넘은 것. 버리지 않는다
            # borderline 만 남은 발화는 flagged 가 아니라 abstain 이다 --
            # 판정자가 "이 문장이 정하지 않는다" 고 말한 것이므로.
            "status": ("flagged" if issues else
                       ("abstain" if (borderline or status == "abstain")
                        else "ok")),
            "abstain_reason": next((u.get("abstain_reason")
                                    for _, u in seen if u.get("abstain_reason")),
                                   None),
            "samples_seen": len(seen),
            "status_per_sample": statuses,
        })
    return {"report_id": samples[0]["report_id"], "utterances": out}


# ------------------------------------------------------------------ writing


def write_by_report(reports, done, outdir, mech):
    """Per report: what is in the file, what the judge said, what it proposes.

    Original and proposal sit side by side deliberately. A proposal alone is
    unreviewable -- the question is always what it CHANGES.
    """
    d = os.path.join(outdir, "by_report")
    os.makedirs(d, exist_ok=True)
    n = 0
    for rep in reports:
        v = done.get(rep["id"])
        if not v:
            continue
        byu = {u["utterance_id"]: u for u in v["utterances"]}
        doc = {"report_id": rep["id"], "utterances": []}
        for rec in rep["records"]:
            u = byu.get(rec["utterance_id"])
            doc["utterances"].append({
                "utterance_id": rec["utterance_id"],
                "section": rec["section"],
                "utterance": rec["utterance"],
                "status": (u or {}).get("status", "unanswered"),
                "issues": (u or {}).get("issues", []),
                "borderline_issues": (u or {}).get("borderline_issues", []),
                "current_propositions": rec["propositions"],
                "current_warnings": rec["warnings"],
                "abstain_reason": (u or {}).get("abstain_reason"),
                "claims_read_from_sentence": (u or {}).get("claims", []),
                "claims_per_sample": (u or {}).get("claims_per_sample", []),
                "claims_stable": (u or {}).get("claims_stable"),
                "status_per_sample": (u or {}).get("status_per_sample", []),
                "rejected_issues": (u or {}).get("rejected_issues", []),
                "precheck_findings": mech.get(rec["utterance_id"], []),
            })
        with open(os.path.join(d, f"{rep['id']}.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
        n += 1
    return n, d


def write_flagged(reports, done, outdir):
    """Only the failing fields. This is the file a human argues with."""
    byrec = {r["utterance_id"]: (rep["id"], r)
             for rep in reports for r in rep["records"]}
    rows = []
    for v in done.values():
        for u in v["utterances"]:
            if u["status"] not in ("flagged", "abstain"):
                continue
            rid, rec = byrec.get(u["utterance_id"], (None, None))
            if rec is None:
                continue
            for iss in u["issues"] or [{"proposition_id": "", "field": "",
                                        "verdict": "", "severity": "",
                                        "confidence": "", "quote": "",
                                        "note": "", "votes": ""}]:
                cur = next((p for p in rec["propositions"]
                            if p["id"] == iss.get("proposition_id")), None)
                rows.append({
                    "report_id": rid,
                    "utterance_id": u["utterance_id"],
                    "section": rec["section"],
                    "utterance": rec["utterance"],
                    **{k: iss.get(k, "") for k in
                       ("proposition_id", "field", "verdict", "severity",
                        "confidence", "quote", "note", "votes")},
                    "vote_n": iss.get("vote_n", 0),
                    "claims": u.get("claims", []),
                    "current": cur,
                    "verified": "",          # 사람이 채우는 칸
                    "verified_note": "",
                })
    path = os.path.join(outdir, "flagged.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    md = [f"# GPT 가 문제라고 본 것 — {len(rows)}건\n",
          "> `out/gpt_records/flagged.jsonl` 의 사람이 읽는 판. "
          "**아직 검증되지 않았습니다.**\n",
          "이 패스는 탐지만 합니다 — 수정안은 `GPT/repair.py` 가 따로 냅니다. "
          "한 호출에 판정과 수정을 같이 시키면 재작성 부담이 플래그를 "
          "누르거나, 수정안을 내려고 이슈를 지어냅니다.\n",
          "⚠️ **득표를 신뢰도로 읽지 마십시오.** 라벨된 249건에서 "
          "3/3 의 정밀도는 **0.55**, 2/3 은 **0.70** 으로 **역전**이었습니다 "
          "— 같은 모델의 세 표본은 같은 편향을 공유하므로, 계통 오탐일수록 "
          "만장일치가 됩니다(3/3 중 18건이 통째로 한 가지 오탐이었습니다). "
          "득표는 **재현성**이지 정확도가 아닙니다. 아래 정렬은 읽는 "
          "순서일 뿐 우선순위가 아닙니다.\n",
          "같은 측정에서 `confidence` 도 거의 신호가 없었습니다 "
          "(high 0.64 · medium 0.48, 225/249 가 high). `severity` 는 "
          "더 없었습니다 (major 0.62 · minor 0.63). **코드별 정밀도**"
          "(`goldset.py score`)가 지금까지 유일하게 값을 한 정렬 기준입니다.\n"]
    by_kind = collections.defaultdict(list)
    for r in rows:
        by_kind[r["verdict"]].append(r)
    md.append("| 코드 | 건수 | 만장일치 | blocking | major | minor | "
              "high | med | low |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for k, v in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        c = collections.Counter(x["confidence"] for x in v)
        sv = collections.Counter(x["severity"] for x in v)
        una = sum(1 for x in v
                  if x.get("votes", "").split("/")[:1]
                  == x.get("votes", "/").split("/")[1:])
        md.append(f"| {k} | {len(v)} | {una} | {sv['blocking']} | "
                  f"{sv['major']} | {sv['minor']} | {c['high']} | "
                  f"{c['medium']} | {c['low']} |")
    rank = {"high": 0, "medium": 1, "low": 2}
    for k, v in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        md.append(f"\n---\n\n## {k} — {len(v)}건\n")
        md.append(f"*{VERDICTS.get(k, '')}*\n")
        # 득표가 먼저다. 확신은 한 실행이 스스로 매긴 값이고, 득표는 서로
        # 다른 실행들이 같은 것을 보았다는 사실이다. 후자가 더 무겁다.
        for r in sorted(v, key=lambda x: (-x.get("vote_n", 0),
                                          rank.get(x["confidence"], 3))):
            md.append(f"### `{r['utterance_id']}` · {r['field']} "
                      f"(**{r.get('votes', '?')} 득표** · {r['severity']} / "
                      f"확신 {r['confidence']})\n")
            md.append(f"- 섹션: {r['section']}")
            md.append(f"- 원문: **{r['utterance']}**")
            if r.get("claims"):
                md.append(f"- 모델이 문장에서 읽어낸 것: "
                          + "; ".join(f"“{c}”" for c in r["claims"]))
            if r["quote"]:
                md.append(f"- 근거: “{r['quote']}”")
            if r["note"]:
                md.append(f"- GPT: {r['note']}")
            if r["current"] is not None:
                md.append(f"- 현재: `{json.dumps(r['current'], ensure_ascii=False)}`")
            md.append("- 검증: ( ) 타당  ( ) 오탐  — ")
    mdp = os.path.join(outdir, "flagged.md")
    open(mdp, "w", encoding="utf-8").write("\n".join(md) + "\n")
    return len(rows), path, mdp


def write_summary(reports, done, outdir, records_path=RECORDS):
    asked = [r for r in reports if r["id"] in done]
    us = [u for v in done.values() for u in v["utterances"]]
    flagged = [u for u in us if u["status"] == "flagged"]
    iss = [i for u in flagged for i in (u["issues"] or [])]
    # 2026-09-17: 파일명이 하드코딩돼 있어 --records 로 다른 팔을 감사해도
    # 헤더는 늘 Prompt 라고 찍혔다. 결과는 맞는데 머리말만 틀려서, 나중에
    # 리포트만 보면 어느 팔인지 정반대로 읽게 된다.
    L = [f"# GPT 검증 요약 — {os.path.relpath(records_path, REPO)}\n",
         f"리포트 {len(asked)}/{len(reports)} · 발화 {len(us):,} · "
         f"flagged {len(flagged):,} ({len(flagged)/max(1,len(us)):.1%}) · "
         f"지적 {len(iss):,}건\n",
         "표본이 아니라 이 파일 전체입니다. 한 모델이 읽은 의견이고 "
         "정답지가 아닙니다 — `flagged.md` 를 사람이 검증한 뒤에야 결론입니다.\n",
         "\n| 코드 | 건수 |", "|---|---|"]
    for k, n in collections.Counter(i["verdict"] for i in iss).most_common():
        L.append(f"| {k} | {n} |")
    L.append("\n| 필드 | 건수 |")
    L.append("|---|---|")
    for k, n in collections.Counter(i["field"] for i in iss).most_common():
        L.append(f"| {k} | {n} |")
    vc = collections.Counter(i.get("votes", "?") for i in iss)
    L.append("\n| 득표 | 지적 |")
    L.append("|---|---|")
    for k, n in sorted(vc.items(), reverse=True):
        L.append(f"| {k} | {n} |")
    unstable = sum(1 for u in us if u.get("claims_stable") is False)
    L.append(f"\n문장에서 읽어낸 주장의 개수가 실행마다 달랐던 발화: "
             f"**{unstable}/{len(us)}**. 이 값이 크면 `dropped` 를 "
             f"믿기 어렵습니다 -- 짝 없는 주장이 곧 `dropped` 이므로.\n")
    rej = sum(len(u.get("rejected_issues", [])) for u in us)
    L.append(f"문턱을 못 넘어 제외된 지적: **{rej}건**. 버리지 않고 "
             f"`by_report/*.json` 의 `rejected_issues` 에 남아 있습니다.\n")
    L.append("\n| 섹션 | 발화 | flagged |")
    L.append("|---|---|---|")
    sec = {r["utterance_id"]: r["section"]
           for rep in reports for r in rep["records"]}
    tot = collections.Counter(sec[u["utterance_id"]] for u in us
                              if u["utterance_id"] in sec)
    bad = collections.Counter(sec[u["utterance_id"]] for u in flagged
                              if u["utterance_id"] in sec)
    for s in sorted(tot):
        L.append(f"| {s} | {tot[s]} | {bad[s]} |")
    p = os.path.join(outdir, "audit.md")
    open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default=RECORDS)
    ap.add_argument("--out", default=None,
                    help="default: out/gpt_records/<arm>/, <arm> read from "
                         "--records")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--temperature", type=float, default=None,
                    help="non-reasoning models only; reasoning models reject it")
    ap.add_argument("--limit", type=int, default=0,
                    help="first N reports (0 = all)")
    ap.add_argument("--report", action="append",
                    help="one report id, repeatable")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--samples", type=int, default=3,
                    help="리포트당 호출 수. 1 이면 투표 없음 (재현 안 됨)")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="지적을 남길 최소 득표 비율 (기본 0.5 = 3표 중 2표)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="samples.jsonl 에서 투표만 다시 계산, 호출 없음")
    a = ap.parse_args()
    a.out = out_for(a.records, a.out)
    print(f"[info] arm={arm_of(a.records)} out={a.out}", file=sys.stderr)

    reports = load_reports(a.records)

    # 기계층이 먼저다. 이 결과는 프롬프트에 들어가고, 모델은 이 코드들을
    # 다시 제기하지 말라는 지시를 함께 받는다.
    mech_recs = precheck.load(a.records)
    a.mech = precheck.run(mech_recs)
    n_mech = sum(len(v) for v in a.mech.values())
    n_sup = sum(1 for v in a.mech.values()
                for f in v if f["code"] in precheck.SUPPRESSED)
    print(f"[info] precheck: {sum(1 for v in a.mech.values() if v)} 발화에 "
          f"기계적 지적 {n_mech}건 -- 그중 {n_sup}건만 억제(모델에게 묻지 "
          f"않음), 나머지 {n_mech - n_sup}건은 참고로 보여주고 모델이 "
          f"반박할 수 있다", file=sys.stderr)
    picked = reports
    if a.report:
        picked = [r for r in reports if r["id"] in set(a.report)]
    elif a.limit:
        picked = reports[:a.limit]
    print(f"[info] {len(picked)}/{len(reports)} reports, "
          f"{sum(len(r['records']) for r in picked):,} utterances",
          file=sys.stderr)

    os.makedirs(a.out, exist_ok=True)
    raw_path = os.path.join(a.out, "samples.jsonl")

    def load_raw():
        """(report_id, sample) -> raw 응답. 같은 키의 나중 줄이 이긴다."""
        got = {}
        if os.path.exists(raw_path):
            for line in open(raw_path, encoding="utf-8"):
                line = line.strip()
                if line:
                    v = json.loads(line)
                    got[(v["report_id"], v.get("sample", 0))] = v
        return got

    raw = load_raw()

    if a.dry_run:
        print(SYSTEM_PROMPT)
        print("\n" + "=" * 70 + "\n")
        print(build_user(picked[0], a.mech))
        print("\n" + "=" * 70)
        print(f"{len(picked)} reports -> {len(picked)} calls, model {a.model}",
              file=sys.stderr)
        return 0

    if not a.rebuild:
        jobs = [(r, i) for r in picked for i in range(a.samples)
                if a.refresh or (r["id"], i) not in raw]
        print(f"[info] {len(jobs)} calls to make "
              f"({len(picked)} reports x {a.samples} samples, "
              f"{len(picked) * a.samples - len(jobs)} cached)", file=sys.stderr)
        if jobs:
            judge = Judge(a.model, a.reasoning_effort, a.timeout, a.temperature)
            run(jobs, judge, a, raw_path)
            print(f"[info] {judge.calls} calls, {judge.in_tokens:,} in / "
                  f"{judge.out_tokens:,} out tokens", file=sys.stderr)
            raw = load_raw()

    # 투표는 raw 위에서 계산한다. 규칙을 바꿔도 --rebuild 로 다시 세면 되고,
    # 다시 물을 필요가 없다.
    by_report = collections.defaultdict(list)
    for (rid, _si), v in sorted(raw.items()):
        by_report[rid].append(v)
    done = {rid: vote(sams, a.samples, a.threshold)
            for rid, sams in by_report.items() if sams}
    vpath = os.path.join(a.out, "verdicts.jsonl")
    with open(vpath, "w", encoding="utf-8") as fh:
        for rid in sorted(done):
            fh.write(json.dumps(done[rid], ensure_ascii=False) + "\n")

    n, d = write_by_report(picked, done, a.out, a.mech)
    k, fj, fm = write_flagged(picked, done, a.out)
    s = write_summary(picked, done, a.out, a.records)
    print(f"[ok] {d}/  ({n} reports)\n[ok] {fj}  ({k} issues)\n"
          f"[ok] {fm}\n[ok] {s}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
