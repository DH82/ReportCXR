#!/usr/bin/env python3
"""
Section 8, step 2 -- deterministic ontology normalization.

The model returns "canonical_snake_case" as well as a language model can. This
pass makes that claim true, using nothing but the tables in Prompt/ontology.py
and no further calls, so the same reply always normalizes to the same record.

What it does:

    spans         rule 3: an anatomy.text that is not in the utterance is
                  dropped to null and the entry falls back to source
                  "entity_semantics". Only the span claim is repaired.
    entity        label -> snake_case -> ENTITY_ALIASES.
                  type corrected against DISEASE_LABELS / DEVICE_LABELS
                  (rule 6: pneumonia is a disease even when the model says
                  finding).
    anatomy       label -> snake_case -> ANATOMY_ALIASES, then lateralized:
                  "lower lobe" + laterality right -> right_lower_lobe.
                  laterality and zone left unset are filled from what the
                  label itself entails, never from the section (rule 4).
    descriptors   text -> DESCRIPTOR_LEXICON -> (type, canonical value).
                  This is where rule 9 is enforced: small stays a size and
                  mild stays a severity no matter which axis the model put
                  them on. Measurements ("3.5 cm") are recognized by shape.
    assertion     rule 12's one hard consequence: comparison "resolved"
                  forces assertion "absent".
    comparison    a cue the model left unmapped is mapped (COMPARISON_CUES);
                  rule 13's "chronic"/"known" are moved off comparison and
                  onto a chronicity descriptor, where they belong.
    section       rule 4: the heading may fill a MISSING broad anatomy, with
                  source "section_context", and may never carry laterality
                  or zone. Both halves are enforced here.

What it deliberately does NOT do: overrule the model on what was asserted.
Where the evidence disagrees with the label -- a negation cue on a "present"
assertion, a comparison cue that maps elsewhere -- a note is recorded and the
label is left alone, because guessing which of the two is right is exactly
the judgement this step is not allowed to make. validate.py raises those as
findings instead.

Every change is appended to record["normalization"] as
{"code", "proposition", "field", "from", "to"}, so a normalized record can be
diffed against the raw reply without keeping both.

parse_utterances.py calls normalize_record(); nothing here calls the model.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

from Prompt.ontology import (
    ANATOMY,
    COMPARISON_NOT_DESCRIPTOR,
    ANATOMY_ALIASES,
    CHRONICITY_NOT_COMPARISON,
    COMPARISON_CUES,
    DESCRIPTOR_LEXICON,
    DEVICE_LABELS,
    DISEASE_LABELS,
    ENTITY_ALIASES,
    LATERALITY_WORDS,
    LATERALIZABLE,
    MEASUREMENT_UNITS,
    SECTION_ALIASES,
    SECTIONS,
    ZONE_WORDS,
    zones_compatible,
)
from Prompt.vocabulary import DESCRIPTOR_TYPES

# "3.5 cm", "2mm", "1.2 x 0.8 cm", "8-mm" -- the hyphenated form is how a
# measurement is written when it modifies a noun ("an 8-mm nodule").
_MEASUREMENT_RE = re.compile(
    r"\d+(?:\.\d+)?[\s-]*(?:x[\s-]*\d+(?:\.\d+)?[\s-]*)?(?:" +
    "|".join(MEASUREMENT_UNITS) + r")\b", re.I)

_WORD_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")

# Longest phrase the descriptor word scan may read by one of its words.
# "moderate to large" is three; anything longer is a clause, not a value.
_SCAN_MAX_WORDS = 3


# =============================================================================
#  SMALL HELPERS
# =============================================================================

def snake(text: Optional[str]) -> Optional[str]:
    """Any surface form -> canonical_snake_case. None stays None."""
    if text is None:
        return None
    t = str(text).strip().lower()
    if not t:
        return None
    t = t.replace("/", " ").replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", "_", t)
    return t.strip("_") or None


def words(text: Optional[str]) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def laterality_in(text: Optional[str]) -> Optional[str]:
    """The side a phrase states, or None. "bilateral" beats "left"+"right"."""
    ws = set(words(text))
    for word, value in LATERALITY_WORDS:
        if word in ws:
            if value in ("left", "right"):
                # "left and right" is bilateral, not whichever came first.
                sides = {v for w, v in LATERALITY_WORDS
                         if w in ws and v in ("left", "right")}
                return "bilateral" if len(sides) > 1 else value
            return value
    return None


def zone_in(text: Optional[str]) -> Optional[str]:
    ws = set(words(text))
    for word, value in ZONE_WORDS:
        if word in ws:
            return value
    return None


def canonical_section(section: Optional[str]) -> Optional[str]:
    """A heading as written -> the SRRG heading it is, or None."""
    if not section:
        return None
    s = section.strip().rstrip(":").strip()
    if s in SECTIONS:
        return s
    low = s.lower()
    for known in SECTIONS:
        if known.lower() == low:
            return known
    return SECTION_ALIASES.get(low)


class _Notes:
    """Collects what this pass changed, in the order it changed it."""

    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []

    def add(self, code: str, pid: Optional[str], field: str,
            was: Any = None, now: Any = None) -> None:
        self.items.append({"code": code, "proposition": pid, "field": field,
                           "from": was, "to": now})


# =============================================================================
#  ENTITY
# =============================================================================

def normalize_entity(ent: Dict[str, Any], pid: str, notes: _Notes) -> None:
    raw_label = ent.get("label") or ent.get("text")
    label = snake(raw_label)

    # Aliases are keyed on the spaced surface term; the model answers in
    # snake_case. Try both forms, and the raw mention as a last resort.
    spaced = (str(raw_label or "")).strip().lower()
    alias = (ENTITY_ALIASES.get(spaced)
             or ENTITY_ALIASES.get(spaced.replace("_", " "))
             or ENTITY_ALIASES.get((ent.get("text") or "").strip().lower()))
    if alias and alias != label:
        notes.add("entity_alias", pid, "entity.label", label, alias)
        label = alias
    if label != ent.get("label"):
        if not alias:
            notes.add("entity_snake_case", pid, "entity.label",
                      ent.get("label"), label)
        ent["label"] = label

    # rule 6: a diagnosis is a disease even if it was typed as a finding.
    kind = ent.get("type")
    want = None
    if label in DISEASE_LABELS and kind not in ("disease",):
        want = "disease"
    elif label in DEVICE_LABELS and kind != "device":
        want = "device"
    if want:
        notes.add("entity_type_from_ontology", pid, "entity.type", kind, want)
        ent["type"] = want


# =============================================================================
#  ANATOMY
# =============================================================================

def normalize_anatomy(entry: Dict[str, Any], pid: str, notes: _Notes,
                      section: Optional[str] = None) -> None:
    raw = entry.get("label")
    spaced = str(raw or entry.get("text") or "").strip().lower()
    # The prompt asks for canonical_snake_case and the model obliges, but
    # ANATOMY_ALIASES is keyed on the spaced surface form. Look up both, or
    # "right_pleura" misses an alias that "right pleura" would have hit.
    flat = spaced.replace("_", " ")

    # Strip the side off the surface form before looking it up: the table is
    # keyed on the bare structure ("lower lobe"), and the side comes back in
    # a moment through LATERALIZABLE.
    bare = flat
    for word, _ in LATERALITY_WORDS:
        bare = re.sub(rf"(?<![a-z]){re.escape(word)}(?![a-z])", " ", bare)
    bare = re.sub(r"[\s_]+", " ", bare).strip()

    # Two things the model puts in this field that are not places.
    #
    # The section heading itself: "No abnormalities detected." under
    # Hila and Mediastinum comes back with label "hila_and_mediastinum",
    # source "section_context". rule 4 lets the heading name a broad
    # structure; it does not make the heading's own name one.
    direct = snake(raw)
    section_of = None
    if direct not in ANATOMY:
        # "lungs" is a heading alias AND an anatomy label. A real label wins:
        # only something that is not already a place is read as a heading.
        section_of = canonical_section(flat) or canonical_section(spaced)
    if section_of:
        broad = (SECTIONS.get(section_of) or {}).get("anatomy")
        if broad:
            notes.add("anatomy_heading_as_label", pid, "anatomy.label", raw,
                      broad)
            entry["label"] = broad
            entry.setdefault("laterality", "unspecified")
            entry.setdefault("zone", None)
            entry.setdefault("role", "site")
            entry.setdefault("source", "section_context")
            _apply_section_context_rule(entry, pid, notes)
            return

    if direct in ANATOMY:
        # Already one of the canonical labels. Nothing to look up, and
        # nothing to strip: "left_lower_lobe" must not become "lower_lobe".
        label = direct
    else:
        label = (ANATOMY_ALIASES.get(spaced) or ANATOMY_ALIASES.get(flat)
                 or ANATOMY_ALIASES.get(bare))
        if not label:
            # The side-stripped form may itself be canonical rather than an
            # alias: ANATOMY_ALIASES has "pleural" -> "pleura" but no key for
            # "pleura", which is already a label. "right_pleura" has to find
            # it here, and gets its side back through LATERALIZABLE below.
            stripped = snake(bare)
            label = stripped if stripped in ANATOMY else (direct or stripped)

    # A bare direction ("bilateral", "central") is not a place, and this is
    # deliberately left alone. Filling the structure in from the heading was
    # tried and reverted: the side that made the label bare came from one
    # part of the utterance and the structure from another, so "central" under
    # Lungs became lungs+midline and "bibasilar" under Cardiovascular became
    # cardiovascular_structures+bilateral -- labels contradicting their own
    # laterality, invented by the repair. An uncovered label is a gap; a
    # contradictory one is a false statement.

    side = entry.get("laterality")
    if side in (None, "", "unspecified", "not_applicable"):
        found = laterality_in(entry.get("text")) or laterality_in(spaced)
        if found:
            notes.add("laterality_from_text", pid, "anatomy.laterality",
                      side, found)
            entry["laterality"] = side = found

    # "lower_lobe" + right -> "right_lower_lobe".
    if label in LATERALIZABLE and side in LATERALIZABLE[label]:
        label = LATERALIZABLE[label][side]

    if label and label != raw:
        notes.add("anatomy_label", pid, "anatomy.label", raw, label)
    entry["label"] = label

    implied_side, implied_zone, _group = ANATOMY.get(label, (None, None, None))

    if entry.get("laterality") in (None, "", "unspecified") and implied_side:
        notes.add("laterality_from_label", pid, "anatomy.laterality",
                  entry.get("laterality"), implied_side)
        entry["laterality"] = implied_side
    entry.setdefault("laterality", "unspecified")
    if entry["laterality"] in (None, ""):
        entry["laterality"] = "unspecified"

    if entry.get("zone") in (None, ""):
        zone = zone_in(entry.get("text")) or implied_zone
        if zone:
            notes.add("zone_from_text" if zone_in(entry.get("text"))
                      else "zone_from_label", pid, "anatomy.zone", None, zone)
        entry["zone"] = zone
    elif implied_zone and entry["zone"] != implied_zone and \
            zones_compatible(entry["zone"], implied_zone):
        # "left lung base" answered as zone "lower". Same region, coarser
        # word; the label's value is the one every other row uses, so the
        # two are folded together rather than left to disagree.
        notes.add("zone_canonicalized", pid, "anatomy.zone",
                  entry["zone"], implied_zone)
        entry["zone"] = implied_zone
    entry.setdefault("role", "site")
    entry.setdefault("source", "utterance")

    _apply_section_context_rule(entry, pid, notes)


def _apply_section_context_rule(entry: Dict[str, Any], pid: str,
                                notes: _Notes) -> None:
    """rule 4: the heading is broad context and nothing else.

    If the model used it to justify a side or a zone, that side or zone is
    not evidence and does not survive.
    """
    if entry.get("source") != "section_context":
        return
    if entry.get("laterality") not in (None, "unspecified", "not_applicable"):
        notes.add("section_context_laterality_dropped", pid,
                  "anatomy.laterality", entry["laterality"], "unspecified")
        entry["laterality"] = "unspecified"
    if entry.get("zone"):
        notes.add("section_context_zone_dropped", pid, "anatomy.zone",
                  entry["zone"], None)
        entry["zone"] = None


def drop_unsupported_spans(prop: Dict[str, Any], utterance: str,
                           notes: _Notes) -> None:
    """rule 3: an anatomy.text that is not in the utterance is not a span.

    The usual cause is the model copying a word out of a few-shot example --
    "pleural" onto "No pneumothorax", "cardiac" onto "Mild cardiomegaly". The
    LABEL is fine in both cases: a pneumothorax is in the pleural space and
    cardiomegaly is of the heart. What is false is only the claim that the
    utterance said so, so that claim is dropped and the entry falls back to
    what it actually was -- anatomy known from the entity, source
    "entity_semantics", which Section 2 has a slot for.

    Only the span is repaired. The label, the laterality and the zone are the
    model's reading and are left alone; if THEY are wrong, validate.py says so.
    Entity and descriptor text are not repaired here: neither is nullable, and
    an entity whose text is invented is a defect, not a formatting slip.
    """
    hay = re.sub(r"\s+", " ", (utterance or "").strip().lower())
    for entry in prop.get("anatomy") or []:
        text = entry.get("text")
        if not text:
            continue
        if re.sub(r"\s+", " ", str(text).strip().lower()) in hay:
            continue
        notes.add("anatomy_span_not_in_utterance", prop.get("id"),
                  "anatomy.text", text, None)
        entry["text"] = None
        if entry.get("source") == "utterance":
            notes.add("anatomy_source_downgraded", prop.get("id"),
                      "anatomy.source", "utterance", "entity_semantics")
            entry["source"] = "entity_semantics"


def fill_section_anatomy(prop: Dict[str, Any], section: Optional[str],
                         notes: _Notes) -> None:
    """rule 4, the half that adds: a heading may fill a MISSING broad anatomy.

    Only when the proposition has no anatomy at all, only the broad structure
    the heading names, and never with a side or a zone.

    A derived proposition is skipped even when its anatomy is empty. rule 6
    makes it an interpretation OF another proposition, so if it has a
    location that location is the parent's, not the heading's -- and Section
    6 D is explicit that a clause naming no location gets none.
    """
    if prop.get("anatomy") or prop.get("derived_from"):
        return
    canon = canonical_section(section)
    broad = (SECTIONS.get(canon) or {}).get("anatomy") if canon else None
    if not broad:
        return
    prop["anatomy"] = [{"text": None, "label": broad,
                        "laterality": "unspecified", "zone": None,
                        "role": "site", "source": "section_context"}]
    notes.add("anatomy_from_section", prop.get("id"), "anatomy", None, broad)


# =============================================================================
#  DESCRIPTORS
# =============================================================================

def normalize_descriptor(desc: Dict[str, Any], pid: str,
                         notes: _Notes) -> None:
    text = str(desc.get("text") or "").strip()
    key = text.lower()

    hit = DESCRIPTOR_LEXICON.get(key)

    # The word scan below reads a phrase by its strongest word, which is right
    # for "moderate to large" and destructive for anything longer. "tip in the
    # low superior vena cava (SVC)" is a device_position, and scanning it for
    # a known word finds "low" and files a catheter tip as a size. So the scan
    # is limited to short phrases, and never touches a device_position: rule 8
    # makes that label compositional -- device, verb, place -- so there is no
    # word in it that stands for the whole.
    scannable = (hit is None and len(words(key)) <= _SCAN_MAX_WORDS
                 and desc.get("type") != "device_position")
    if scannable:
        for w in words(key):
            if w in DESCRIPTOR_LEXICON:
                hit = DESCRIPTOR_LEXICON[w]
                break

    # A measurement is a shape, not a word, so the word-count limit above is
    # the wrong gate for it: "1.2 x 0.8 cm" tokenizes to six. What separates a
    # measurement from a phrase that merely contains one is how much of the
    # text it is. "8-mm" is all of it; "recommendation to withdraw 4.5 cm to
    # the lower SVC" is a sentence with a number in it.
    if hit is None and desc.get("type") != "device_position":
        m = _MEASUREMENT_RE.search(text)
        if m and len(m.group(0)) >= 0.6 * len(text.strip()):
            hit = ("measurement", snake(m.group(0)))

    if hit:
        want_type, want_label = hit
        # rule 9 lives here: the lexicon, not the model, decides whether a
        # word is a size or a severity.
        if desc.get("type") != want_type:
            notes.add("descriptor_type_from_lexicon", pid, "descriptor.type",
                      desc.get("type"), want_type)
            desc["type"] = want_type
        if desc.get("label") != want_label:
            notes.add("descriptor_label", pid, "descriptor.label",
                      desc.get("label"), want_label)
            desc["label"] = want_label
        return

    label = snake(desc.get("label") or text)
    if label != desc.get("label"):
        notes.add("descriptor_snake_case", pid, "descriptor.label",
                  desc.get("label"), label)
        desc["label"] = label
    if desc.get("type") not in DESCRIPTOR_TYPES:
        notes.add("descriptor_type_unknown", pid, "descriptor.type",
                  desc.get("type"), "other")
        desc["type"] = "other"


# =============================================================================
#  ASSERTION AND COMPARISON
# =============================================================================

def move_comparison_descriptors(prop: Dict[str, Any], pid: str,
                                notes: _Notes) -> None:
    """rule 12: "Stable" and "Unchanged" are a comparison, not a descriptor.

    The mirror of the rule 13 move in normalize_comparison(). The model files
    these under descriptors, typed "other" or "normality"; a temporal
    comparison recorded as a property of the finding is invisible to any
    query that asks what changed.

    Three cases, and they are not the same repair:

      comparison "none"      the comparison went unrecorded. Move it.
      comparison agrees      the model stated it twice, once in each place --
                             "Unchanged mediastinal contours" gives comparison
                             stable AND a normality descriptor "Unchanged".
                             Drop the copy; the comparison already has it.
      comparison disagrees   two readings of the same utterance. Left alone;
                             validate.py raises it, because choosing between
                             them is not a table's decision to make.
    """
    comp = prop.get("comparison") or {"label": "none", "cue": None}
    prop["comparison"] = comp

    keep: List[Dict[str, Any]] = []
    for desc in prop.get("descriptors") or []:
        text = str(desc.get("text") or "").strip().lower()
        mapped = COMPARISON_CUES.get(text) \
            if text in COMPARISON_NOT_DESCRIPTOR else None
        if not mapped:
            keep.append(desc)
        elif comp.get("label") == "none":
            notes.add("comparison_moved_off_descriptor", pid, "comparison",
                      desc.get("text"), mapped)
            comp["label"], comp["cue"] = mapped, desc.get("text")
        elif comp.get("label") == mapped:
            notes.add("duplicate_comparison_descriptor_dropped", pid,
                      "descriptors", desc.get("text"), None)
        else:
            keep.append(desc)
    prop["descriptors"] = keep


def repair_derived_from(prop: Dict[str, Any], known: List[str], pid: str,
                        notes: _Notes) -> None:
    """rule 6: derived_from is one id, and it has to be one of this
    utterance's.

    The model occasionally answers "p1, p2" -- a proposition read as two
    observations at once. The schema types the field as a string, so that
    passes the grammar and lands as a dangling link. The first id that
    actually exists is kept, because a link to the first parent is what the
    rest of the record already assumes; anything unrecoverable becomes null,
    which is what "not derived" is spelled as.
    """
    src = prop.get("derived_from")
    if src is None or src in known:
        return
    found = [tok for tok in re.split(r"[,;/ ]+", str(src)) if tok in known]
    new = found[0] if found else None
    notes.add("derived_from_repaired", pid, "derived_from", src, new)
    prop["derived_from"] = new


def normalize_comparison(prop: Dict[str, Any], pid: str,
                         notes: _Notes) -> None:
    comp = prop.get("comparison") or {"label": "none", "cue": None}
    prop["comparison"] = comp
    cue = (comp.get("cue") or "").strip().lower()

    # rule 13: "chronic" and "known" are not a comparison. Move them to the
    # chronicity descriptor they always were.
    if cue in CHRONICITY_NOT_COMPARISON:
        dtype, dlabel = DESCRIPTOR_LEXICON.get(cue, ("chronicity", snake(cue)))
        prop.setdefault("descriptors", []).append(
            {"text": comp.get("cue"), "type": dtype, "label": dlabel})
        notes.add("chronicity_moved_off_comparison", pid, "comparison",
                  comp.get("label"), "none")
        comp["label"], comp["cue"] = "none", None
        return

    mapped = COMPARISON_CUES.get(cue)
    if mapped and comp.get("label") == "none":
        # The model copied the cue but did not label it.
        notes.add("comparison_from_cue", pid, "comparison.label", "none",
                  mapped)
        comp["label"] = mapped
    elif mapped and mapped != comp.get("label"):
        # Two readings of the same word. Recorded, not resolved -- validate.py
        # raises it as a finding for review.
        notes.add("comparison_cue_mismatch", pid, "comparison.label",
                  comp.get("label"), mapped)


def apply_resolved_rule(prop: Dict[str, Any], pid: str,
                        notes: _Notes) -> None:
    """rule 12's only hard consequence: resolved -> assertion absent."""
    comp = prop.get("comparison") or {}
    assertion = prop.get("assertion") or {"label": "unknown", "cue": None}
    prop["assertion"] = assertion
    if comp.get("label") == "resolved" and assertion.get("label") != "absent":
        notes.add("resolved_implies_absent", pid, "assertion.label",
                  assertion.get("label"), "absent")
        assertion["label"] = "absent"


# =============================================================================
#  ONE RECORD
# =============================================================================

def normalize_record(record: Dict[str, Any], *, section: Optional[str] = None,
                     use_section: bool = True) -> Dict[str, Any]:
    """Normalize one Section 2 record. Returns a new record; input untouched.

    `section` defaults to the record's own. use_section=False turns off the
    rule 4 fill, for measuring how much of the anatomy came from the heading
    rather than from the utterance.
    """
    out = copy.deepcopy(record)
    section = section if section is not None else out.get("section")
    notes = _Notes()

    props = out.get("propositions") or []
    known_ids = [p.get("id") or f"p{i}" for i, p in enumerate(props, 1)]

    for i, prop in enumerate(props, 1):
        pid = prop.get("id") or f"p{i}"
        prop["id"] = pid

        prop.setdefault("entity", {})
        normalize_entity(prop["entity"], pid, notes)

        prop.setdefault("anatomy", [])
        for entry in prop["anatomy"]:
            normalize_anatomy(entry, pid, notes, section)
        drop_unsupported_spans(prop, out.get("utterance") or "", notes)
        if use_section:
            fill_section_anatomy(prop, section, notes)

        prop.setdefault("descriptors", [])
        for desc in prop["descriptors"]:
            normalize_descriptor(desc, pid, notes)

        move_comparison_descriptors(prop, pid, notes)
        normalize_comparison(prop, pid, notes)
        apply_resolved_rule(prop, pid, notes)
        prop.setdefault("derived_from", None)
        repair_derived_from(prop, known_ids, pid, notes)

    canon = canonical_section(section)
    if canon and canon != section:
        notes.add("section_canonical", None, "section", section, canon)
        out["section"] = canon

    out["normalization"] = notes.items
    return out


__all__ = ["normalize_record", "drop_unsupported_spans",
           "move_comparison_descriptors", "repair_derived_from", "snake", "laterality_in", "zone_in",
           "canonical_section", "normalize_entity", "normalize_anatomy",
           "normalize_descriptor", "normalize_comparison"]
