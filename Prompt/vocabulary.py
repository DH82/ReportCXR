"""Closed answer spaces (the schema enums), defined once.

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

# null is a member: most anatomy has no zone.
ZONES = ["upper", "middle", "lower", "apical", "basilar", "perihilar",
         "retrocardiac", "diffuse", None]

# rule 7
ANATOMY_ROLES = ["site", "insertion_site", "tip_location", "relative_location"]

# rule 4: "section_context" may never carry laterality or zone (validate.py enforces).
ANATOMY_SOURCES = ["utterance", "section_context", "entity_semantics",
                   "linked_proposition"]

# -- descriptor --------------------------------------------------------------
# rule 8, rule 9
DESCRIPTOR_TYPES = ["size", "severity", "extent", "distribution", "number",
                    "morphology", "measurement", "device_position",
                    "chronicity", "normality", "other"]

# -- assertion ---------------------------------------------------------------
# rule 10
ASSERTION_LABELS = ["present", "absent", "uncertain", "unknown"]

# -- comparison --------------------------------------------------------------
# rule 12: "none" = no comparison made, "unclear" = made but no direction.
COMPARISON_LABELS = ["new", "improved", "worsened", "stable", "resolved",
                     "none", "unclear"]

__all__ = [
    "ENTITY_TYPES", "LATERALITY", "ZONES", "ANATOMY_ROLES", "ANATOMY_SOURCES",
    "DESCRIPTOR_TYPES", "ASSERTION_LABELS", "COMPARISON_LABELS",
]
