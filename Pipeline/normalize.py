#!/usr/bin/env python3
"""Section 8, step 2 -- deterministic ontology normalization.

Applies Prompt2/ontology.py to one record and makes no calls, so the same
reply always normalizes to the same record.

    spans        rule 3: an anatomy.text absent from the utterance -> null
    entity       snake_case -> ENTITY_ALIASES; type fixed by DISEASE/DEVICE_LABELS
    anatomy      ANATOMY_ALIASES; side stripped into laterality (E1); unset
                 laterality/zone filled from the label, never from the section
    descriptors  DESCRIPTOR_LEXICON -> (type, value); measurements by shape
    assertion    comparison "resolved" forces assertion "absent"
    comparison   unmapped cues mapped; "chronic"/"known" moved to chronicity
    section      rule 4: heading may fill a MISSING broad anatomy only

It never overrules the model on what was asserted: conflicting evidence is
recorded as a note and left for validate.py. Every change is appended to
record["normalization"] as {code, proposition, field, from, to}.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

from Prompt2.ontology import (
    MODIFIER_LIFT_EXCEPTIONS,
    NORMALITY_PREFIXES,
    NORMALITY_PREFIX_EXCEPTIONS,
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
    BILATERAL_COLLECTIVE,
    SINGULAR_OF,
    LATERAL_PREFIXES,
    LEFT_HAS_NO,
    MEASUREMENT_UNITS,
    SECTION_ALIASES,
    SECTION_FALLBACK,
    SECTIONS,
    SIDE_ONLY_LABELS,
    SIDE_ONLY_SPANS,
    ZONE_WORDS,
    zones_compatible,
    vessel_segment_split,
    vessel_segment_in,
    SEGMENTED_VESSELS,
)
from Prompt2.vocabulary import DESCRIPTOR_TYPES, VESSEL_SEGMENTS

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

# Leftovers after the side word is stripped: not structures, so never labels.
# Reached only when the model gives label=null and text "Right-sided"; a null
# label states "this utterance names no structure" and must not be filled in.
SIDE_LEFTOVERS = {"sided", "side", "sides"}


def normalize_anatomy(entry: Dict[str, Any], pid: str, notes: _Notes,
                      section: Optional[str] = None) -> None:
    raw = entry.get("label")
    spaced = str(raw or entry.get("text") or "").strip().lower()
    # The prompt asks for canonical_snake_case and the model obliges, but
    # ANATOMY_ALIASES is keyed on the spaced surface form. Look up both, or
    # "right_pleura" misses an alias that "right pleura" would have hit.
    flat = spaced.replace("_", " ")

    # Strip the side off the surface form before looking it up: the table is
    # keyed on the bare structure ("lower lobe").
    #
    # Since E1 the side never comes back: laterality_in(spaced) moves a side
    # baked into the label into the field, and a mismatch is reported as
    # lateral_prefix_conflict.
    bare = flat
    for word, _ in LATERALITY_WORDS:
        bare = re.sub(rf"(?<![a-z]){re.escape(word)}(?![a-z])", " ", bare)
    bare = re.sub(r"[\s_]+", " ", bare).strip()

    # Things the model puts here that are not places -- chiefly the section
    # heading itself. rule 4 lets a heading name a broad structure; it does not
    # make the heading's own name one.
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
            # The side-stripped form may already be canonical rather than an
            # alias ("pleura" is a label, not an alias key).
            stripped = snake(bare)
            label = stripped if stripped in ANATOMY else (direct or stripped)

    # Undo a text-filled label that turned out to be only a side leftover.
    # A leftover the model itself supplied as a label is left alone.
    if not raw and label in SIDE_LEFTOVERS:
        notes.add("side_leftover_not_a_place", pid, "anatomy.label",
                  label, None)
        label = None

    # A bare direction ("bilateral", "central") is not a place and is left
    # alone on purpose: filling the structure in from the heading was tried and
    # reverted, because it invented labels that contradicted their own laterality.
    # An uncovered label is a gap; a contradictory one is a false statement.

    side = entry.get("laterality")
    if side in (None, "", "unspecified", "not_applicable"):
        found = laterality_in(entry.get("text")) or laterality_in(spaced)
        if found:
            notes.add("laterality_from_text", pid, "anatomy.laterality",
                      side, found)
            entry["laterality"] = side = found
    else:
        # Label says one side, field says another. Report it; validate.py decides.
        in_label = laterality_in(spaced)
        if in_label and in_label != side:
            notes.add("lateral_prefix_conflict", pid, "anatomy.laterality",
                      f"label={spaced}", side)

    # No middle lobe on the left: anatomy knowledge, not laterality handling.
    if label in LEFT_HAS_NO and side == "left":
        notes.add("left_has_no", pid, "anatomy.label", label,
                  LEFT_HAS_NO[label])
        label = LEFT_HAS_NO[label]

    # Collective plurals carry the side in the plural, not a prefix, so E1 does
    # not cover them; the promotion stays until that is decided.
    if label in BILATERAL_COLLECTIVE and side == "bilateral":
        label = BILATERAL_COLLECTIVE[label]

    # A collective pointing at one side is lowered to the singular: the alias
    # table promotes lung -> lungs, which now contradicts the laterality field.
    if side in ("left", "right") and label in SINGULAR_OF:
        notes.add("collective_to_singular", pid, "anatomy.label",
                  label, SINGULAR_OF[label])
        label = SINGULAR_OF[label]

    # E2: a vessel segment belongs in `zone`. "mid_svc" -> "svc" + zone "mid".
    # This runs on the resolved label so the alias table is already through
    # ("mid superior vena cava" -> "mid_svc" -> here), and it also reaches the
    # segmented labels that never had a row of their own ("lower_svc").
    segment = None
    split = vessel_segment_split(label)
    if split:
        label, segment = split

    if label and label != raw:
        notes.add("anatomy_label", pid, "anatomy.label", raw, label)
    entry["label"] = label

    implied_side, implied_zone, _group = ANATOMY.get(label, (None, None, None))
    # E2 applies to conduits only -- see SEGMENTED_VESSELS.
    is_vessel = label in SEGMENTED_VESSELS

    # rule 4 drops anything a section_context entry carries, so filling it
    # from the label first is a round trip: it fired 1,024 times per pass and
    # netted to zero, which is exactly the note pair section 0 warns about.
    from_heading = entry.get("source") == "section_context"

    if entry.get("laterality") in (None, "", "unspecified") and implied_side \
            and not from_heading:
        notes.add("laterality_from_label", pid, "anatomy.laterality",
                  entry.get("laterality"), implied_side)
        entry["laterality"] = implied_side
    entry.setdefault("laterality", "unspecified")
    if entry["laterality"] in (None, ""):
        entry["laterality"] = "unspecified"

    if is_vessel and not from_heading:
        # E2. A vessel is divided by proximal/mid/distal, a lung by
        # upper/middle/lower, and the two vocabularies must not mix: ZONE_WORDS
        # reads "mid" as the lung "middle", which is not a thing a vessel has.
        # So a vessel's zone is only ever read by vessel_segment_*, and a lung
        # value sitting on a vessel is replaced rather than kept.
        found = segment or vessel_segment_in(entry.get("text"))
        current = entry.get("zone")
        if found and current != found:
            notes.add("vessel_segment_from_label" if segment
                      else "vessel_segment_from_text",
                      pid, "anatomy.zone", current, found)
            entry["zone"] = found
        elif current and current not in VESSEL_SEGMENTS:
            # No segment to put there, and what is there is a lung word.
            notes.add("lung_zone_on_vessel_dropped", pid, "anatomy.zone",
                      current, None)
            entry["zone"] = None
        entry.setdefault("zone", None)
    elif entry.get("zone") in (None, "") and not from_heading:
        zone = zone_in(entry.get("text")) or implied_zone
        if zone:
            notes.add("zone_from_text" if zone_in(entry.get("text"))
                      else "zone_from_label", pid, "anatomy.zone", None, zone)
        entry["zone"] = zone
    elif implied_zone and entry["zone"] != implied_zone and not from_heading \
            and zones_compatible(entry["zone"], implied_zone):
        # "left lung base" answered as zone "lower". Same region, coarser
        # word; the label's value is the one every other row uses, so the
        # two are folded together rather than left to disagree.
        notes.add("zone_canonicalized", pid, "anatomy.zone",
                  entry["zone"], implied_zone)
        entry["zone"] = implied_zone
    entry.setdefault("role", "site")
    entry.setdefault("source", "utterance")

    lift_side_only_span(entry, pid, notes)
    _apply_section_context_rule(entry, pid, notes)


def lift_side_only_span(entry: Dict[str, Any], pid: str,
                        notes: _Notes) -> None:
    """E5: a direction is not a structure name.

    "Small left pleural effusion" arrives as

        {text: "left", label: "pleura", laterality: "left", source: "utterance"}

    and that record says the side twice while naming the pleura nowhere.
    `source: "utterance"` claims the clause named the structure; it did not.
    The label is right -- an effusion entails the pleura -- so what is wrong is
    only the span and the provenance, and both are fixable without a model.

    WHY THE SPAN IS NULLED RATHER THAN REPAIRED.  The obvious alternative is to
    find the structure's real surface form in the utterance and put THAT in
    `text`. Measured on train, 53.7% of these do have such a form -- but 46.4
    of those 53.7 points are matches that fall INSIDE the entity's own span
    ("pleural" of "pleural effusion"), and copying one there would record the
    same words as both the entity and its location: the exact double-recording
    this pipeline exists to avoid. Only 7.0% are safe standalone matches, which
    is not worth a rule that has to guess an offset. And for the overlapping
    ones `entity_semantics` is not a compromise but the truth -- the pleura is
    entailed by "effusion", not named beside it.

    The side is NOT lost: it is already in `laterality` (measured: 6 entries in
    1.1M lacked it), and this fills it from the span before dropping it.

    WHAT THIS DOES NOT FIX.  When the LABEL is itself a direction
    (`{text: "left", label: "left"}`, 13,771 in train) no structure was ever
    extracted, and no table can invent one. Those are left alone and stay
    visible as `anatomy_span_is_side_only` for the prompt to fix.
    """
    span = re.sub(r"\s+", " ",
                  (entry.get("text") or "").strip().lower()).rstrip(".")
    if span not in SIDE_ONLY_SPANS:
        return
    if (entry.get("label") or "") in SIDE_ONLY_LABELS or not entry.get("label"):
        notes.add("side_only_span_no_structure", pid, "anatomy.label",
                  entry.get("label"), entry.get("label"))
        return

    if entry.get("laterality") in (None, "", "unspecified"):
        found = laterality_in(span)
        if found:
            notes.add("laterality_from_side_span", pid, "anatomy.laterality",
                      entry.get("laterality"), found)
            entry["laterality"] = found

    notes.add("side_only_span_lifted", pid, "anatomy.text",
              entry.get("text"), None)
    entry["text"] = None
    if entry.get("source") == "utterance":
        notes.add("side_only_span_source", pid, "anatomy.source",
                  "utterance", "entity_semantics")
        entry["source"] = "entity_semantics"


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

    # The word scan reads a phrase by its strongest word: right for "moderate to
    # large", destructive for longer text ("tip in the low SVC" would file a
    # catheter tip as a size). Limited to short phrases, never a device_position.
    scannable = (hit is None and len(words(key)) <= _SCAN_MAX_WORDS
                 and desc.get("type") != "device_position")
    if scannable:
        for w in words(key):
            if w in DESCRIPTOR_LEXICON:
                hit = DESCRIPTOR_LEXICON[w]
                break

    # A measurement is a shape, not a word, so the word limit above is the wrong
    # gate. What separates one from a phrase containing a number is how much of
    # the text it covers.
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

def lift_normality_prefix(prop: Dict[str, Any], pid: str,
                          notes: _Notes) -> None:
    """E3: "normal_heart_size" -> "heart_size" + normality descriptor.

    Same shape as move_comparison_descriptors(): if the normality axis is empty
    a descriptor is created, otherwise only the label prefix is dropped (almost
    always the latter -- 99.95% already carry the descriptor).

    Must run BEFORE normalize_entity(), because the stripped base may itself be
    an alias key (unremarkable_osseous_structures ->
    osseous_structures -> bones).
    """
    ent = prop.get("entity") or {}
    label = ent.get("label") or ""
    if label in NORMALITY_PREFIX_EXCEPTIONS:
        return
    for prefix, value in NORMALITY_PREFIXES:
        if not label.startswith(prefix) or len(label) <= len(prefix):
            continue
        base = label[len(prefix):]
        notes.add("normality_prefix_lifted", pid, "entity.label", label, base)
        ent["label"] = base

        descs = prop.get("descriptors") or []
        if not any(d.get("type") == "normality" for d in descs):
            # Only when the axis is empty. text stays None: rule 3 wants a real
            # span and the prefix has no known position in the utterance.
            descs.append({"text": None, "type": "normality", "label": value})
            prop["descriptors"] = descs
            notes.add("normality_from_prefix", pid, "descriptors", None, value)
        return


def lift_modifier_prefix(prop: Dict[str, Any], pid: str,
                         notes: _Notes) -> None:
    """E3's lift, generalized: strip a modifier the descriptors already hold.

    "focal_consolidation" with {extent "focal"} stores one fact twice, and the
    entity vocabulary then grows with every modifier combination (measured:
    970 propositions over 235 label forms; 1-D calls the same population
    "over-specified" and says the fix belongs in the descriptor field).

    Only fires when the modifier is ALREADY a descriptor on this proposition.
    Nothing is invented: a label whose modifier was never recorded keeps it,
    because dropping it would lose the only copy.

    Runs with lift_normality_prefix(), before normalize_entity(), so the base
    can still be aliased.
    """
    ent = prop.get("entity") or {}
    # A label can carry two of them ("focal_nodular_density" with {focal} and
    # {nodular}), so keep going until nothing more comes off. Stripping one
    # per pass is not idempotent, and step 2 has to be.
    while True:
        label = ent.get("label") or ""
        # NORMALITY_PREFIX_EXCEPTIONS too: E3 declared those labels
        # indivisible, and stripping one here only for an alias to put it back
        # is a cycle that nets to zero and fills the audit trail.
        if not label or label in MODIFIER_LIFT_EXCEPTIONS \
                or label in NORMALITY_PREFIX_EXCEPTIONS:
            return
        for d in prop.get("descriptors") or []:
            mod = d.get("label") or ""
            if not mod or not label.startswith(mod + "_"):
                continue
            base = label[len(mod) + 1:]
            # A base too short to be a concept means the prefix ate the label.
            if len(base) < 3 or not any(c.isalpha() for c in base):
                continue
            notes.add("modifier_prefix_lifted", pid, "entity.label", label,
                      base)
            ent["label"] = base
            break                      # label changed: rescan from the top
        else:
            return                     # a full pass with nothing to strip


# rule 7 / E2: a device's tip position is an anatomy entry with a role, never a
# descriptor. These are the prefixes the model actually writes.
_TIP_PREFIXES = ("tip_in_", "tip_at_", "tip_within_", "tip_terminates_in_")


def lift_device_position(prop: Dict[str, Any], pid: str, notes: _Notes,
                         section: Optional[str] = None) -> None:
    """E2: `{device_position: tip_in_mid_svc}` -> anatomy `svc` zone `mid`.

    Where the tip sits is a place, and a place belongs in `anatomy` with a
    role -- rule 7 says so and the prompt has said so since v2, but the
    corpus was extracted before that and 28,732 descriptors still carry it.
    A descriptor cannot say "mid SVC": the segment has nowhere to go, so the
    whole thing collapses into one opaque label.

    The candidate is normalized by normalize_anatomy BEFORE anything is
    committed, and the move only happens if it lands on a label the table
    knows. That keeps one copy of the resolution rules rather than a second
    set here, and an unresolvable tip ("tip_at_gej") is left alone: an
    uncovered descriptor is a gap, a wrong anatomy entry is a false statement.
    """
    kept: List[Dict[str, Any]] = []
    for desc in prop.get("descriptors") or []:
        label = desc.get("label") or ""
        prefix = next((p for p in _TIP_PREFIXES if label.startswith(p)), None)
        if not prefix:
            kept.append(desc)
            continue

        probe = {"text": desc.get("text"), "label": label[len(prefix):],
                 "laterality": None, "zone": None,
                 "role": "tip_location", "source": "utterance"}
        normalize_anatomy(probe, pid, _Notes(), section)
        if probe.get("label") not in ANATOMY:
            kept.append(desc)                      # not a place we know
            continue

        twin = next((a for a in prop.get("anatomy") or []
                     if a.get("label") == probe["label"]
                     and a.get("role") == "tip_location"), None)
        if twin:
            # The model wrote it both ways. The anatomy entry is the one rule 7
            # asks for, so the descriptor is the copy that goes.
            if twin.get("zone") in (None, "") and probe.get("zone"):
                twin["zone"] = probe["zone"]
            notes.add("device_position_duplicate_dropped", pid,
                      "descriptors", label, None)
            continue

        # The span belongs to the descriptor's phrase ("tip in the mid SVC"),
        # not to the structure alone, and rule 18 wants only the structure's
        # own span under source "utterance". Leaving it null states less than
        # the phrase does, which is the safe direction.
        probe["text"] = None
        prop.setdefault("anatomy", []).append(probe)
        notes.add("device_position_to_anatomy", pid, "descriptors",
                  label, f"anatomy {probe['label']}"
                         + (f" zone {probe['zone']}" if probe.get("zone") else ""))
    prop["descriptors"] = kept


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
        lift_normality_prefix(prop, pid, notes)      # E3: before label aliasing
        lift_modifier_prefix(prop, pid, notes)       # same, for other axes
        # The modifier lift can uncover a normality prefix it was hiding:
        # "well_expanded_clear_lungs" -> "clear_lungs" -> "lungs" + clear.
        lift_normality_prefix(prop, pid, notes)
        normalize_entity(prop["entity"], pid, notes)

        prop.setdefault("anatomy", [])
        for entry in prop["anatomy"]:
            normalize_anatomy(entry, pid, notes, section)
        # E2: after the existing entries are canonical, so the duplicate check
        # compares canonical labels, and before the span drop, which the moved
        # entry (text null) passes trivially.
        prop.setdefault("descriptors", [])
        lift_device_position(prop, pid, notes, section)
        drop_unsupported_spans(prop, out.get("utterance") or "", notes)
        if use_section:
            fill_section_anatomy(prop, section, notes)

        for desc in prop["descriptors"]:
            normalize_descriptor(desc, pid, notes)

        move_comparison_descriptors(prop, pid, notes)
        normalize_comparison(prop, pid, notes)
        apply_resolved_rule(prop, pid, notes)
        prop.setdefault("derived_from", None)
        repair_derived_from(prop, known_ids, pid, notes)

    canon = canonical_section(section)
    if not section:
        # No heading at all. Left as null the record falls out of every
        # section-scoped metric silently; SECTION_FALLBACK is the section that
        # entails no anatomy, so this places the record without claiming anything.
        canon = SECTION_FALLBACK
    if canon and canon != section:
        notes.add("section_canonical", None, "section", section, canon)
        out["section"] = canon

    out["normalization"] = notes.items
    return out


__all__ = ["normalize_record", "drop_unsupported_spans",
           "lift_side_only_span",
           "lift_normality_prefix",
           "move_comparison_descriptors", "repair_derived_from", "snake", "laterality_in", "zone_in",
           "canonical_section", "normalize_entity", "normalize_anatomy",
           "normalize_descriptor", "normalize_comparison"]
