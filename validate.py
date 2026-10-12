#!/usr/bin/env python3
"""
Section 8, step 3 -- rule-based validation, and the automatic review queue.

Two different questions, answered together because they read the same record:

  findings   Is this record wrong? Each finding names the rule from Section 3
             that it breaks. Severity is one of:
                error    the record contradicts a rule, or contains text that
                         is not in the utterance. Not usable as it stands.
                warning  the record is internally consistent but says
                         something the rules call out -- a section conflict,
                         an unflagged qualified negation.
  triggers   Should a human look at this one? Section 8 lists seven triggers
             verbatim; TRIGGERS below is that list, and nothing else is in it.
             A trigger is not a defect. "two or more entities" fires on a
             perfectly correct record; it fires because that is where errors
             concentrate.

The expensive check is the first one. rule 3 says every "text" and "cue" is
exact source text, and a parser that quietly paraphrases is a parser whose
spans cannot be used for anything downstream -- not for grounding, not for
counterfactual swaps, not for agreement against a second annotator. So every
span is matched back against the utterance, whitespace-normalized and
case-insensitive, and a miss is an error rather than a warning.

Run it on a NORMALIZED record. A few checks (resolved -> absent, chronicity
off comparison) can only fire on a record that skipped normalize.py, and when
they do they are reported as such.

parse_utterances.py calls validate_record(); nothing here calls the model.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from Prompt.ontology import (
    ANATOMY,
    COMPARISON_NOT_DESCRIPTOR,
    CHRONICITY_NOT_COMPARISON,
    DESCRIPTOR_LEXICON,
    NEGATION_CUES,
    SECTIONS,
    UNCERTAINTY_CUES,
    zones_compatible,
)
from Prompt.vocabulary import (
    ANATOMY_ROLES,
    ANATOMY_SOURCES,
    ASSERTION_LABELS,
    COMPARISON_LABELS,
    DESCRIPTOR_TYPES,
    ENTITY_TYPES,
    LATERALITY,
    ZONES,
)
from normalize import canonical_section

# Section 8, verbatim. The order is the specification's.
TRIGGERS = [
    "two or more entities",
    "qualified negation",
    "uncertain interpretation",
    "multiple anatomy locations",
    "device tip location",
    "temporal comparison",
    "section conflict",
]

# rule 11: a negation with one of these attached is a QUALIFIED negation, and
# what is excluded is the qualified thing, not the finding.
QUALIFYING_TYPES = {"size", "severity", "extent", "measurement", "number"}

_WS = re.compile(r"\s+")
_TIP_WORDS = ("tip", "terminates", "terminating", "ends", "in the svc",
              "carina", "cavoatrial")


def _has_word(text: str, phrase: str) -> bool:
    """Whole-word match. "tip" as a substring is inside "multiple"."""
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])",
                     text) is not None


def _norm(text: Optional[str]) -> str:
    """Case- and whitespace-insensitive form, for span matching."""
    return _WS.sub(" ", (text or "").strip().lower())


class _Findings:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []

    def add(self, severity: str, code: str, rule: Optional[str],
            pid: Optional[str], message: str) -> None:
        self.items.append({"severity": severity, "code": code, "rule": rule,
                           "proposition": pid, "message": message})

    def error(self, code: str, rule: Optional[str], pid: Optional[str],
              msg: str) -> None:
        self.add("error", code, rule, pid, msg)

    def warn(self, code: str, rule: Optional[str], pid: Optional[str],
             msg: str) -> None:
        self.add("warning", code, rule, pid, msg)


# =============================================================================
#  rule 3 -- exact source text
# =============================================================================

def check_spans(record: Dict[str, Any], f: _Findings) -> None:
    hay = _norm(record.get("utterance"))

    def seen(span: Optional[str]) -> bool:
        s = _norm(span)
        return (not s) or (s in hay)

    for p in record.get("propositions") or []:
        pid = p.get("id")
        ent = p.get("entity") or {}
        if not seen(ent.get("text")):
            f.error("entity_text_not_in_utterance", "rule 3", pid,
                    f"entity.text {ent.get('text')!r} is not in the utterance")
        for a in p.get("anatomy") or []:
            # A section_context or linked_proposition entry legitimately has
            # no text; only a text that is present but wrong is an error.
            if a.get("text") and not seen(a.get("text")):
                f.error("anatomy_text_not_in_utterance", "rule 3", pid,
                        f"anatomy.text {a.get('text')!r} is not in the "
                        f"utterance")
        for d in p.get("descriptors") or []:
            if not seen(d.get("text")):
                f.error("descriptor_text_not_in_utterance", "rule 3", pid,
                        f"descriptor.text {d.get('text')!r} is not in the "
                        f"utterance")
        for key in ("assertion", "comparison"):
            cue = (p.get(key) or {}).get("cue")
            if cue and not seen(cue):
                f.error(f"{key}_cue_not_in_utterance", "rule 3", pid,
                        f"{key}.cue {cue!r} is not in the utterance")


# =============================================================================
#  Section 2 -- the answer spaces, and the id graph
# =============================================================================

def check_shape(record: Dict[str, Any], f: _Findings) -> None:
    props = record.get("propositions") or []
    ids: Set[str] = set()

    for i, p in enumerate(props, 1):
        pid = p.get("id")
        if not pid:
            f.error("missing_id", "section 2", None, f"proposition #{i} has no id")
            continue
        if pid in ids:
            f.error("duplicate_id", "section 2", pid, f"id {pid!r} is used twice")
        ids.add(pid)

        ent = p.get("entity") or {}
        if ent.get("type") not in ENTITY_TYPES:
            f.error("entity_type_invalid", "rule 5", pid,
                    f"entity.type {ent.get('type')!r} is not one of "
                    f"{ENTITY_TYPES}")
        if not ent.get("label"):
            f.error("entity_label_missing", "section 2", pid,
                    "entity.label is empty")
        elif ent["label"] != ent["label"].lower() or " " in ent["label"]:
            f.error("entity_label_not_canonical", "section 2", pid,
                    f"entity.label {ent['label']!r} is not canonical_snake_case")

        for a in p.get("anatomy") or []:
            if a.get("laterality") not in LATERALITY:
                f.error("laterality_invalid", "section 2", pid,
                        f"laterality {a.get('laterality')!r} is not in {LATERALITY}")
            if a.get("zone") not in ZONES:
                f.error("zone_invalid", "section 2", pid,
                        f"zone {a.get('zone')!r} is not in {ZONES}")
            if a.get("role") not in ANATOMY_ROLES:
                f.error("role_invalid", "rule 7", pid,
                        f"role {a.get('role')!r} is not in {ANATOMY_ROLES}")
            if a.get("source") not in ANATOMY_SOURCES:
                f.error("source_invalid", "section 2", pid,
                        f"source {a.get('source')!r} is not in {ANATOMY_SOURCES}")

        for d in p.get("descriptors") or []:
            if d.get("type") not in DESCRIPTOR_TYPES:
                f.error("descriptor_type_invalid", "rule 8", pid,
                        f"descriptor.type {d.get('type')!r} is not in "
                        f"{DESCRIPTOR_TYPES}")

        if (p.get("assertion") or {}).get("label") not in ASSERTION_LABELS:
            f.error("assertion_invalid", "rule 10", pid,
                    f"assertion {(p.get('assertion') or {}).get('label')!r} "
                    f"is not in {ASSERTION_LABELS}")
        if (p.get("comparison") or {}).get("label") not in COMPARISON_LABELS:
            f.error("comparison_invalid", "rule 12", pid,
                    f"comparison {(p.get('comparison') or {}).get('label')!r} "
                    f"is not in {COMPARISON_LABELS}")

    # rule 6: derived_from is a link, so it has to land somewhere real.
    for p in props:
        pid, src = p.get("id"), p.get("derived_from")
        if src is None:
            continue
        if src == pid:
            f.error("derived_from_self", "rule 6", pid,
                    "derived_from points at its own proposition")
        elif src not in ids:
            f.error("derived_from_unknown", "rule 6", pid,
                    f"derived_from {src!r} is not a proposition of this "
                    f"utterance")

    # A chain that loops is a chain nothing downstream can walk.
    parent = {p.get("id"): p.get("derived_from") for p in props}
    for pid in list(parent):
        seen, cur = set(), pid
        while cur is not None and cur in parent:
            if cur in seen:
                f.error("derived_from_cycle", "rule 6", pid,
                        "derived_from forms a cycle")
                break
            seen.add(cur)
            cur = parent[cur]


# =============================================================================
#  rules 4, 9, 10, 11, 12, 13, 14
# =============================================================================

def check_rules(record: Dict[str, Any], f: _Findings) -> None:
    utt = _norm(record.get("utterance"))
    canon = canonical_section(record.get("section"))
    section_groups = set((SECTIONS.get(canon) or {}).get("groups") or []) \
        if canon else set()
    warnings = " ".join(record.get("warnings") or []).lower()

    for p in record.get("propositions") or []:
        pid = p.get("id")
        ent = p.get("entity") or {}
        assertion = p.get("assertion") or {}
        comparison = p.get("comparison") or {}
        descs = p.get("descriptors") or []
        cue_a = _norm(assertion.get("cue"))
        cue_c = _norm(comparison.get("cue"))

        # -- rule 10: the cue and the label have to agree -------------------
        if cue_a and assertion.get("label") == "present" and \
                cue_a in {c.lower() for c in NEGATION_CUES}:
            f.error("negation_cue_on_present", "rule 10", pid,
                    f"assertion is present but the cue is {cue_a!r}")
        if cue_a and assertion.get("label") == "present" and \
                cue_a in {c.lower() for c in UNCERTAINTY_CUES}:
            f.warn("hedge_cue_on_present", "rule 10", pid,
                   f"assertion is present but the cue is {cue_a!r}; rule 10 "
                   f"makes a hedged statement uncertain")
        if assertion.get("label") == "absent" and not cue_a:
            f.warn("absent_without_cue", "rule 10", pid,
                   "assertion is absent but no cue was copied; an unmentioned "
                   "finding is not absent")

        # -- rule 11: qualified negation ------------------------------------
        quals = [d for d in descs if d.get("type") in QUALIFYING_TYPES]
        if assertion.get("label") == "absent" and quals:
            if "qualified negation" not in warnings:
                f.warn("qualified_negation_unwarned", "rule 11", pid,
                       f"{ent.get('label')} is absent only as qualified by "
                       f"{[d.get('label') for d in quals]}; Section 6 A asks "
                       f"for a warning saying the unqualified finding is not "
                       f"excluded")

        # -- rule 12 and 13 -------------------------------------------------
        if comparison.get("label") == "resolved" and \
                assertion.get("label") != "absent":
            f.error("resolved_not_absent", "rule 12", pid,
                    "comparison is resolved, so assertion must be absent")
        if cue_c in CHRONICITY_NOT_COMPARISON:
            f.error("chronicity_as_comparison", "rule 13", pid,
                    f"{cue_c!r} is chronicity, not a temporal comparison")

        # -- rule 9: the axes stay apart ------------------------------------
        for d in descs:
            hit = DESCRIPTOR_LEXICON.get(_norm(d.get("text")))
            if hit and d.get("type") != hit[0]:
                f.error("descriptor_wrong_axis", "rule 9", pid,
                        f"{d.get('text')!r} is {hit[0]}, recorded as "
                        f"{d.get('type')}")

        # -- rule 12: a comparison filed as a descriptor ---------------------
        for d in descs:
            if _norm(d.get("text")) in COMPARISON_NOT_DESCRIPTOR:
                f.error("comparison_as_descriptor", "rule 12", pid,
                        f"{d.get('text')!r} is a temporal comparison, "
                        f"recorded as a {d.get('type')} descriptor")

        # -- rule 14 ---------------------------------------------------------
        if ent.get("type") == "anatomical_state" and \
                assertion.get("label") == "absent":
            f.warn("normal_state_as_absence", "rule 14", pid,
                   "an anatomical state is asserted, not negated; a normal "
                   "statement is not the absence of every disease")

        # -- rule 4 and rule 7: anatomy --------------------------------------
        for a in p.get("anatomy") or []:
            label = a.get("label")
            implied_side, implied_zone, group = ANATOMY.get(
                label, (None, None, None))
            side, zone = a.get("laterality"), a.get("zone")

            if implied_side and side not in (None, "unspecified") and \
                    side != implied_side:
                f.error("laterality_contradicts_label", "section 2", pid,
                        f"anatomy {label!r} is {implied_side}, recorded as "
                        f"{side}")
            if implied_zone and zone and not zones_compatible(zone,
                                                              implied_zone):
                # Only a real disagreement. "basilar" vs "lower" is the same
                # region under two names and normalize.py has already folded
                # it; "upper" vs "lower" is not.
                f.error("zone_contradicts_label", "section 2", pid,
                        f"anatomy {label!r} is zone {implied_zone}, recorded "
                        f"as {zone}")

            if a.get("source") == "section_context":
                if side not in (None, "unspecified", "not_applicable"):
                    f.error("section_context_has_laterality", "rule 4", pid,
                            "the heading may never contribute a laterality")
                if zone:
                    f.error("section_context_has_zone", "rule 4", pid,
                            "the heading may never contribute a zone")

            if group and section_groups and group not in section_groups and \
                    a.get("source") == "utterance":
                # rule 4: the utterance wins, but the disagreement is recorded.
                f.warn("section_conflict", "rule 4", pid,
                       f"anatomy {label!r} ({group}) is not what the heading "
                       f"{canon!r} describes; the utterance stands")

            if a.get("role") in ("insertion_site", "tip_location") and \
                    ent.get("type") != "device":
                f.warn("device_role_on_non_device", "rule 7", pid,
                       f"role {a.get('role')!r} on a "
                       f"{ent.get('type')!r} entity")

        if ent.get("type") == "device" and \
                any(_has_word(utt, w) for w in _TIP_WORDS) and \
                not any(a.get("role") == "tip_location"
                        for a in p.get("anatomy") or []):
            f.warn("device_tip_not_located", "rule 7", pid,
                   "the utterance states where the device ends, but no "
                   "anatomy entry carries role tip_location")

    # -- rule 6: an inference cue with nothing derived from anything ---------
    props = record.get("propositions") or []
    if props and not any(p.get("derived_from") for p in props):
        cues = [c for c in ("suggesting", "suggestive of", "may represent",
                            "cannot be excluded", "concerning for",
                            "compatible with", "consistent with")
                if c in utt]
        if cues and len(props) == 1:
            f.warn("inference_not_split", "rule 6", None,
                   f"the utterance hedges ({cues[0]!r}) but only one "
                   f"proposition was produced; rule 6 keeps the observation "
                   f"and its interpretation apart")

    if not props and utt:
        f.warn("no_propositions", "rule 2", None,
               "no propositions were produced for a non-empty utterance")


# =============================================================================
#  Section 8 -- the automatic review triggers
# =============================================================================

def review_triggers(record: Dict[str, Any],
                    findings: List[Dict[str, Any]]) -> List[str]:
    """Section 8's seven triggers, in the specification's order."""
    props = record.get("propositions") or []
    fired: List[str] = []

    entities = {(p.get("entity") or {}).get("label") for p in props}
    entities.discard(None)
    if len(entities) >= 2:
        fired.append("two or more entities")

    if any((p.get("assertion") or {}).get("label") == "absent"
           and any(d.get("type") in QUALIFYING_TYPES
                   for d in p.get("descriptors") or [])
           for p in props):
        fired.append("qualified negation")

    if any((p.get("assertion") or {}).get("label") == "uncertain"
           for p in props):
        fired.append("uncertain interpretation")

    if any(len(p.get("anatomy") or []) > 1 for p in props):
        fired.append("multiple anatomy locations")

    if any(a.get("role") == "tip_location"
           for p in props for a in p.get("anatomy") or []):
        fired.append("device tip location")

    if any((p.get("comparison") or {}).get("label") not in (None, "none")
           for p in props):
        fired.append("temporal comparison")

    if any(f["code"] == "section_conflict" for f in findings):
        fired.append("section conflict")

    return [t for t in TRIGGERS if t in fired]


# =============================================================================
#  ONE RECORD
# =============================================================================

def validate_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Findings and review triggers for one normalized record.

    Returns {"ok", "errors", "warnings", "findings", "triggers"}. The record
    itself is not modified: what is wrong with a record and the record are two
    different things, and only one of them is the parser's output.
    """
    f = _Findings()
    check_spans(record, f)
    check_shape(record, f)
    check_rules(record, f)

    errors = [x for x in f.items if x["severity"] == "error"]
    warns = [x for x in f.items if x["severity"] == "warning"]
    return {
        "ok": not errors,
        "errors": len(errors),
        "warnings": len(warns),
        "findings": f.items,
        "triggers": review_triggers(record, f.items),
    }


__all__ = ["validate_record", "review_triggers", "TRIGGERS", "check_spans",
           "check_shape", "check_rules"]
