"""Closed answer spaces (the schema enums) -- the ones in use.

Changing one means editing system.py's wording for it too.
"""

# -- entity ------------------------------------------------------------------
# Section 2 "entity.type", System Prompt rule 5.
ENTITY_TYPES = [
    "finding",              # something seen on the image: opacity, effusion
    "disease",              # an interpretation of it: pneumonia, edema
    "device",               # lines, tubes, hardware
    "anatomical_state",     # rule 14: "normal", "clear", "within normal limits"
    "postoperative_state",  # status post lobectomy, CABG
    "other",
]

# -- anatomy -----------------------------------------------------------------
LATERALITY = ["left", "right", "bilateral", "midline", "unspecified",
              "not_applicable"]

# -- zone ---------------------------------------------------------------------
# One slot, two value sets: the words that divide a lung and the words that
# divide a vessel do not overlap.

# Lung fields. ZONES was only this before E2.
LUNG_ZONES = ["upper", "middle", "lower", "apical", "basilar", "perihilar",
              "retrocardiac", "diffuse"]

# Vessel segments, for catheter tip position (rule 7 / E2). Kept separate from
# the lung values so that a value alone says which kind of zone it is: "upper"
# would be ambiguous, proximal/mid/distal is not.
# ASSUMES UPPER-BODY ACCESS (jugular/subclavian). Femoral access reverses
# proximal and distal.
VESSEL_SEGMENTS = ["proximal", "mid", "distal"]

# null is a member: most anatomy has no zone at all.
ZONES = LUNG_ZONES + VESSEL_SEGMENTS + [None]

# Anatomical wording -> canonical segment. Only consulted when the anatomy is a
# vessel. NOTE: ontology.ZONE_WORDS maps "mid" to the lung "middle"; that mapping
# must not be applied to a vessel label, so zone extraction has to be anatomy-aware.
VESSEL_SEGMENT_ALIASES = {
    "upper": "proximal", "high": "proximal", "superior": "proximal",
    "mid": "mid", "middle": "mid", "central": "mid",
    "midportion": "mid", "midsection": "mid",
    "low": "distal", "lower": "distal", "inferior": "distal",
    "distal": "distal", "proximal": "proximal",
}

# rule 7: a device has an insertion site and a tip location, and they are not
# the same kind of statement.
ANATOMY_ROLES = ["site", "insertion_site", "tip_location", "relative_location"]

# Where the anatomy came from. rule 4 makes "section_context" a weak source
# that may never carry laterality or zone; validate.py enforces that.
ANATOMY_SOURCES = ["utterance", "section_context", "entity_semantics",
                   "linked_proposition"]

# -- descriptor --------------------------------------------------------------
# rule 8. rule 9 keeps size and severity apart on purpose.
DESCRIPTOR_TYPES = ["size", "severity", "extent", "distribution", "number",
                    "morphology", "measurement", "device_position",
                    "chronicity", "normality", "other"]

# -- assertion ---------------------------------------------------------------
# rule 10. "unknown" is for a mention that asserts nothing about this study.
ASSERTION_LABELS = ["present", "absent", "uncertain", "unknown"]

# -- comparison --------------------------------------------------------------
# rule 12. "none" means the utterance makes no comparison, "unclear" means it
# makes one that cannot be resolved into a direction.
COMPARISON_LABELS = ["new", "improved", "worsened", "stable", "resolved",
                     "none", "unclear"]

__all__ = [
    "ENTITY_TYPES", "LATERALITY", "ZONES", "LUNG_ZONES", "VESSEL_SEGMENTS",
    "VESSEL_SEGMENT_ALIASES", "ANATOMY_ROLES", "ANATOMY_SOURCES",
    "DESCRIPTOR_TYPES", "ASSERTION_LABELS", "COMPARISON_LABELS",
]
