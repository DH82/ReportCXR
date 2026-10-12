"""
Answer spaces -- the value sets every axis is allowed to return.

These are the enums the tool schemas enforce and the prompts spell out,
so a value may not be added here without editing the prompt that offers
it. The severity lookup table is derived from SEVERITY_WORDS.

maplez_struct.py imports from here; nothing in this package imports back.
"""

from typing import Dict, List, Optional, Tuple

# Entity kinds prompt 0 may return.
ENTITY_TYPES = ["imaging_finding", "diagnosis", "device", "procedure",
                "technical", "none"]

# Kinds that go through the presence / location / severity / change axes.
# "technical" (low lung volumes, rotated film) and "none" (a symptom, a piece of
# clinical history, an empty heading) are recorded and skipped: they are not
# findings, so a presence judgement would be meaningless.
ANNOTATED_ENTITY_TYPES = {"imaging_finding", "diagnosis", "device", "procedure"}

# =============================================================================
#  SEVERITY LADDER -- extends the three classes of Appendix A.3.2.2
# =============================================================================
#  None(0) < Trace(1) < Minimal(2) < Mild(3) < Moderate(4) < Severe(5)
#
#  The paper folds trace/minimal/small into "Mild"; this ladder keeps them
#  apart. Everything at or above "severe" -- marked, massive, extensive -- stays
#  in Severe, so the top of the scale matches the paper. Map Trace/Minimal down
#  to Mild to compare the two.

SEVERITY_SCALE: List[str] = ["None", "Trace", "Minimal", "Mild", "Moderate",
                             "Severe"]
SEVERITY_ORDINAL: Dict[str, int] = {n: i for i, n in enumerate(SEVERITY_SCALE)}
SEVERITY_BY_ORDINAL: Dict[int, str] = {i: n for n, i in SEVERITY_ORDINAL.items()}

# Report wording -> ladder step. Range expressions resolve to their upper bound,
# which is how the paper's table reads ("mild to moderate" -> Moderate).
SEVERITY_WORDS: Dict[str, List[str]] = {
    "None": ["none", "no residual", "not present"],
    "Trace": ["trace", "traces", "tiny"],
    "Minimal": ["minimal", "minimally", "minor", "subtle", "slight", "slightly",
                "trace to minimal"],
    "Mild": ["mild", "mildly", "small", "low-grade", "faint", "minimal to mild",
             "borderline"],
    "Moderate": ["moderate", "moderately", "mild to moderate",
                 "mild-to-moderate", "small to moderate"],
    "Severe": ["severe", "severely", "large", "advanced", "high-grade",
               "marked", "markedly", "massive", "gross", "pronounced",
               "extensive", "extensively", "widespread",
               "moderate to severe", "moderate-to-severe", "moderate to large"],
}

# Stripped before the lookup: change words and acuity words are not degrees.
NO_SEVERITY_WORDS = ["increasing", "increased", "decreasing", "decreased",
                     "worsening", "improving", "acute", "new"]

# Longest phrases first so that "mild to moderate" wins over "mild".
SEVERITY_LOOKUP: List[Tuple[str, str]] = sorted(
    [(w, cls) for cls, ws in SEVERITY_WORDS.items() for w in ws],
    key=lambda t: -len(t[0]))

# =============================================================================
#  INTERVAL CHANGE VOCABULARY  (this script's extension, not from the paper)
# =============================================================================

# "Stable" is the Stable/Unchanged step: the finding is there and has not moved.
CHANGE_VALUES = ["Resolved", "Improved", "Stable", "Worsened", "New",
                 "Not comparable"]
# Direction on the ladder, for sorting and for sanity checks. New and
# Not comparable are off-ladder and carry no direction.
CHANGE_DIRECTION: Dict[str, Optional[int]] = {
    "Resolved": -2, "Improved": -1, "Stable": 0, "Worsened": 1,
    "New": None, "Not comparable": None,
}
# What prompt 4 may report from the line's own wording.
CHANGE_CUES = ["Resolved", "Improved", "Stable", "Worsened", "New", "Not stated"]

# =============================================================================
#  PRESENCE VOCABULARY
# =============================================================================

PRESENT_LIKE = {"Present", "Uncertain"}
ABSENT_LIKE = {"Absent", "Not asserted"}
CATEGORICAL_VALUES = ["Present", "Uncertain", "Absent", "Not asserted"]
