"""
The closed answer spaces of the parser.

Every enum the schema in Section 2 of the specification writes out as a
"a | b | c" string lives here once, so the schema, the normalizer and the
validator cannot drift apart. Changing an answer space means editing this
file AND the wording in system.py that offers those answers.

schema.py, normalize.py and validate.py import from here; nothing in this
package imports back.
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

# null is a member: most anatomy has no zone at all.
ZONES = ["upper", "middle", "lower", "apical", "basilar", "perihilar",
         "retrocardiac", "diffuse", None]

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
    "ENTITY_TYPES", "LATERALITY", "ZONES", "ANATOMY_ROLES", "ANATOMY_SOURCES",
    "DESCRIPTOR_TYPES", "ASSERTION_LABELS", "COMPARISON_LABELS",
]
