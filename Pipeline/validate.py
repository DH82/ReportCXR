#!/usr/bin/env python3
"""Section 8, step 3 -- rule-based validation and the review queue.

    findings   Is this record wrong? Each finding names the rule it breaks.
                 error    contradicts a rule, or carries text not in the
                          utterance. Not usable as it stands.
                 warning  internally consistent but called out by a rule.
    triggers   Should a human look at it? The seven triggers from Section 8,
               verbatim. A trigger is not a defect -- it marks where errors
               concentrate.

Every span is matched back against the utterance (whitespace-normalized,
case-insensitive) and a miss is an error: rule 3 spans that quietly paraphrase
are unusable downstream.

Run it on a NORMALIZED record. Checks that can only fire on an un-normalized
one (resolved -> absent, chronicity off comparison) say so when they do.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from Prompt2.ontology import (
    ANATOMY,
    ANATOMY_ALIASES,
    DEVICE_LABELS,
    DISEASE_LABELS,
    ENTITY_ALIASES,
    COMPARISON_NOT_DESCRIPTOR,
    CHRONICITY_NOT_COMPARISON,
    DESCRIPTOR_LEXICON,
    NEGATION_CUES,
    SECTIONS,
    SIDE_ONLY_SPANS,
    SIDED_MIDLINE,
    UNCERTAINTY_CUES,
    zones_compatible,
)
from Prompt2.vocabulary import (
    ANATOMY_ROLES,
    ANATOMY_SOURCES,
    ASSERTION_LABELS,
    COMPARISON_LABELS,
    DESCRIPTOR_TYPES,
    ENTITY_TYPES,
    LATERALITY,
    ZONES,
)
from Pipeline.normalize import canonical_section

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

# Section 2 field invariants. Each was found by reading records by hand and
# then counted over validate + test + test_reviewed (22,493 anatomy entries,
# 20,948 propositions); none of them fires today, which is why they are here.
#
# They are warnings, not errors: the record stays usable and the label stays
# right. What is wrong is the provenance or the span, which matters downstream
# for grounding, not for reading the proposition.

# "source" says the structure was NOT named in this clause, so a span
# contradicts it. 358 entries (1.59%).
DERIVED_SOURCES = {"entity_semantics", "section_context", "linked_proposition"}

# A side word is not a structure (rule 16 says so for labels; the same holds
# for the span). 1,090 entries (4.85%).
# A span that opens with a preposition gives a position against a landmark,
# which is role "relative_location", not the site itself. 120 entries.
_RELATIVE_PREP = re.compile(
    r"^(below|above|beneath|under|adjacent to|next to|near|behind|overlying|"
    r"at the level of|superior to|inferior to)\b", re.I)


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
                    side != implied_side and label not in SIDED_MIDLINE:
                # SIDED_MIDLINE exemption: a midline compartment still has a
                # left and a right border that reports name every day
                # ("widened left mediastinum"), so a stated side is not a
                # contradiction. s08_invariants.py applies the same exemption.
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
            elif implied_zone and a.get("source") != "section_context":
                # E7: 23 labels (lung_base, hilum, upper_lobe, ...) bake a
                # zone into the label itself, so the same fact lives in two
                # fields. That is only safe as long as the two fields are
                # never allowed to say different things -- a fixed point, not
                # a coincidence. normalize.py either fills the empty zone
                # from the label or canonicalizes a compatible-but-different
                # one (e.g. "basilar" -> "lower"); either way the field must
                # come out exactly equal to what the label implies. A
                # heading (section_context) is exempt: rule 4 clears its
                # zone entirely, checked above as section_context_has_zone.
                if not zone:
                    f.error("zone_missing_from_label", "section 2", pid,
                            f"anatomy {label!r} implies zone {implied_zone!r} "
                            f"but zone is empty; normalize.py should have "
                            f"filled it")
                elif zone != implied_zone:
                    f.error("zone_not_canonicalized", "section 2", pid,
                            f"anatomy {label!r} implies zone {implied_zone!r}; "
                            f"recorded zone {zone!r} is compatible but was "
                            f"not folded to the label's spelling")

            if a.get("source") == "section_context":
                if side not in (None, "unspecified", "not_applicable"):
                    f.error("section_context_has_laterality", "rule 4", pid,
                            "the heading may never contribute a laterality")
                if zone:
                    f.error("section_context_has_zone", "rule 4", pid,
                            "the heading may never contribute a zone")

            # -- Section 2 field invariants ----------------------------------
            span = (a.get("text") or "").strip()
            if span and a.get("source") in DERIVED_SOURCES:
                f.warn("anatomy_source_carries_span", "section 2", pid,
                       f"source {a.get('source')!r} says this clause did not "
                       f"name the structure, but text is {span!r}")
            if _norm(span).rstrip(".") in SIDE_ONLY_SPANS:
                f.warn("anatomy_span_is_side_only", "section 2", pid,
                       f"anatomy.text {span!r} is a side, not a structure")
            if _RELATIVE_PREP.match(span) and a.get("role") == "site":
                f.warn("anatomy_span_is_relative", "section 2", pid,
                       f"anatomy.text {span!r} places the finding against a "
                       f"landmark; that is role 'relative_location', not "
                       f"'site'")

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
#  rule 2 -- proposition splitting
# =============================================================================
# rule 2 constrains both directions: one entity in several places is ONE
# proposition with several anatomy entries (no over-splitting), while
# "No pleural effusion or pneumothorax" is TWO (no under-splitting).

_COORD = re.compile(r"(?<![a-z0-9])(or|and)(?![a-z0-9])")

# Entity surfaces the ontology knows. Length >= 5 only (shorter ones sit inside
# other words), and alias VALUES as well as keys (pneumothorax exists only as
# the value of "ptx"). Words the descriptor lexicon owns are excluded, or
# "unremarkable" would make a second entity out of a descriptor.
# A place word is not evidence of a second entity: after E3 made "lungs" an
# entity surface, "Consolidation in the lower lungs" read as two entities.
# Nor is a component of a device: "Pacemaker and ICD leads" is one device with
# its parts, not two entities.
_COMPONENT_WORDS = {"lead", "leads", "tip", "tips", "wire", "wires",
                    "lumen", "lumens", "cuff", "balloon"}

_PLACE_WORDS = ({a.replace("_", " ") for a in ANATOMY}
                | {k for k in ANATOMY_ALIASES}
                | {v.replace("_", " ") for v in ANATOMY_ALIASES.values()})

_ENTITY_SURFACES = sorted(
    ({w for w in ENTITY_ALIASES if len(w) >= 5}
     | {l.replace("_", " ") for l in
        (set(ENTITY_ALIASES.values()) | DISEASE_LABELS | DEVICE_LABELS)
        if len(l) >= 5})
    - set(DESCRIPTOR_LEXICON) - _PLACE_WORDS - _COMPONENT_WORDS,
    key=len, reverse=True)


def _known_entities(utt: str) -> Set[str]:
    """Distinct known entity labels in the utterance.

    Longest surface first, consuming the span it matched, so "rib fracture"
    does not also count as "fracture".
    """
    spans: List[Tuple[int, int, str]] = []
    for surf in _ENTITY_SURFACES:                 # already longest-first
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(surf) + r"(?![a-z0-9])",
                             utt):
            if any(s < m.end() and m.start() < e for s, e, _l in spans):
                continue                          # a longer surface took it
            spans.append((m.start(), m.end(),
                          ENTITY_ALIASES.get(surf, surf.replace(" ", "_"))))
    # Two adjacent matches are one compound: "aspiration pneumonia" is one entity.
    spans.sort()
    out: Set[str] = set()
    prev_end = -99
    for start, end, label in spans:
        if start - prev_end <= 1:                 # only a space between them
            prev_end = end
            continue
        out.add(label)
        prev_end = end
    return out


def _split_key(prop: Dict[str, Any]) -> tuple:
    """Everything except anatomy. Equal keys should have been one proposition."""
    ent = prop.get("entity") or {}
    return (
        ent.get("label"),
        ent.get("type"),
        (prop.get("assertion") or {}).get("label"),
        (prop.get("comparison") or {}).get("label"),
        prop.get("derived_from"),
        frozenset((d.get("type"), d.get("label"))
                  for d in prop.get("descriptors") or []),
    )


def check_splitting(record: Dict[str, Any], f: _Findings) -> None:
    props = record.get("propositions") or []
    utt = _norm(record.get("utterance"))

    # -- over-splitting --------------------------------------------------------
    # Everything but anatomy is identical: the spec wants one proposition.
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for p in props:
        groups.setdefault(_split_key(p), []).append(p)
    for key, same in groups.items():
        if len(same) < 2 or key[0] is None:
            continue
        # A location is (label, laterality, zone). Label alone is not enough:
        # since E1 both sides share one label and would look like one place.
        sites = [tuple(sorted((a.get("label") or "", a.get("laterality") or "",
                               a.get("zone") or "")
                              for a in (p.get("anatomy") or []))) for p in same]
        if len(set(sites)) < 2:
            # Same anatomy too: that is duplication, not splitting.
            f.warn("duplicate_proposition", "rule 2",
                   same[1].get("id"),
                   f"{key[0]!r} has {len(same)} propositions with identical anatomy too")
            continue
        f.warn("should_be_one_proposition", "rule 2", same[1].get("id"),
               f"{key[0]!r} is split across {len(same)} propositions with the same "
               f"assertion/descriptors ({', '.join(p.get('id') or '?' for p in same)}); "
               f"rule 2 asks for one proposition with several anatomy entries")

    # -- under-splitting -------------------------------------------------------
    # Fires only when BOTH sides of the conjunction name a known entity.
    # "negation + conjunction + one proposition" was tried and was a false
    # positive every time: report conjunctions usually join adjectives, places
    # or predicates, not entities. Recall is low by design.
    if len(props) == 1:
        found = _known_entities(utt)
        if len(found) >= 2:
            f.warn("coordination_not_split", "rule 2", props[0].get("id"),
                   f"distinct entities {sorted(found)} in one utterance but only "
                   f"one proposition; rule 2 asks for one per entity")

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
    check_splitting(record, f)

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
           "check_shape", "check_rules", "check_splitting"]
