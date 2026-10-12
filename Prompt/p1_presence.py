"""
Prompt 1 -- presence.

Condenses Appendix A.1.1 prompts 1 and 8 into one question with four
answers, so no probability is needed to separate Present from
Uncertain.  Placeholders: {sentence}, {label}.  Stage id: q1.

maplez_struct.py imports from here; nothing in this package imports back.
"""

from Prompt.vocabulary import CATEGORICAL_VALUES

P1 = ('Given the line "{sentence}" from a chest X-ray report, decide what the '
      'line states about "{label}" in this study. '
      '"Present": the radiologist asserts it is there. Cue: "there is", '
      '"demonstrates", "consistent with", "compatible with", or a plain noun '
      'phrase stated without hedging. '
      '"Uncertain": the radiologist leaves it open. Cue: "possible", '
      '"probable", "likely", "suspicious for", "may represent", "cannot be '
      'excluded", "questionable", "concerning for", "versus". '
      '"Absent": the radiologist asserts it is not there. Cue: "no", "without", '
      '"free of", "negative for", "clear", "unremarkable", "normal". Read "no '
      'definite", "no significant" and "no gross" as Absent. '
      '"Not asserted": the line names it but asserts nothing about this study '
      '-- past history, a recommendation, a hypothetical. '
      'A differential ("A versus B", "A or B") makes every candidate Uncertain. '
      'Check the scope of a negation: answer Absent only when "{label}" falls '
      'inside it. Copy into "cue" the word or phrase you judged from. '
      'Respond with exactly one of: Present, Uncertain, Absent, Not asserted.')

S_PRESENCE = {
    "type": "object",
    "properties": {
        "presence": {"type": "string", "enum": CATEGORICAL_VALUES},
        "cue": {"type": "string"},
    },
    "required": ["presence", "cue"],
}
