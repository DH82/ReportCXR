"""
Prompt 4 -- what the line itself says about change.

This script's own prompt. It reports only the wording present in the
line; the rule engine decides the final change value from this plus
the matched prior annotation.
Placeholders: {sentence}, {label}.  Stage id: q4.

maplez_struct.py imports from here; nothing in this package imports back.
"""

from Prompt.vocabulary import CHANGE_CUES

P4 = ('Given the line "{sentence}" from a chest X-ray report, decide what the '
      'line itself states about how "{label}" has changed since a previous '
      'imaging study. Use only wording present in the line; never infer a '
      'change from the severity, and never guess. '
      '"new", "newly", "interval development", "not previously seen", "not seen '
      'on the prior" indicate New. '
      '"resolved", "resolution", "no longer seen", "cleared", "no longer '
      'present" indicate Resolved. '
      '"decreased", "decreasing", "smaller", "less prominent", "improving", '
      '"improved", "regressed", "partially resolved" indicate Improved. '
      '"increased", "increasing", "larger", "enlarging", "more prominent", '
      '"progression", "progressed", "worsening", "worsened" indicate Worsened. '
      '"unchanged", "stable", "no interval change", "no significant change", '
      '"persistent", "persists", "chronic", "similar to the prior" indicate '
      'Stable. '
      'If the line makes no comparison with a previous study, answer "Not '
      'stated". Respond with exactly one of: New, Resolved, Improved, '
      'Worsened, Stable, Not stated.')

S_CHANGE_CUE = {
    "type": "object",
    "properties": {"change": {"type": "string", "enum": CHANGE_CUES}},
    "required": ["change"],
}
