"""
Prompt 3 -- severity.

Condenses Appendix A.1.1 prompts 12 and 13; the scale is this script's
six-step ladder, not the paper's three classes. Editing
SEVERITY_SCALE means editing the wording here too.
Placeholders: {sentence}, {label}.  Stage id: q3.

maplez_struct.py imports from here; nothing in this package imports back.
"""

from Prompt.vocabulary import SEVERITY_SCALE

P3 = ('Given the line "{sentence}" from a chest X-ray report, characterize the '
      'severity of "{label}" only from the words of the line, and not from '
      'comparisons or changes. The scale runs from least to most severe: '
      '"None" (a degree is stated and it is zero), "Trace", "Minimal" (minimal, '
      'minor, subtle, slight), "Mild" (mild, small), "Moderate", "Severe" '
      '(severe, large, marked, massive, extensive). Answer "Undefined" when the '
      'line states no degree at all. For a range such as "mild to moderate", '
      'answer with the upper end. Do not add extra words to your answer and '
      'exclusively use one of those seven options.')

S_SEVERITY = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": SEVERITY_SCALE + ["Undefined"]},
    },
    "required": ["severity"],
}
