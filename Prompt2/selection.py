"""Example selection. v1's rule with three changes, the last from v3:

  * two cue slots instead of one (11 examples now, not 8)
  * limitation, blanket and coordination sit first in the cue table -- first
    hit wins, and those are the types the earlier prompts failed hardest on.
    limitation goes above the negation cues on purpose: a sentence that both
    negates something and limits the reading gets the example for the thing
    v2 had no example for at all.
  * the negation test is a word-boundary match like every other cue, so
    "no" inside "nodule" no longer picks the qualified example.

Cap stays at 4. Everything else is v1: word-boundary match, first hit wins,
no example sent twice.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from Prompt2.examples import EXAMPLES

CUE_TABLE = [
    # rule 19 -- the sentence limits the reading rather than describing the
    # patient; 119 of 162 such utterances dropped the limitation entirely.
    ("limitation", ["limited", "limiting", "obscured", "obscuring",
                    "poorly assessed", "difficult to assess",
                    "excluded from", "suboptimal", "not well seen"]),
    # rule 2 -- names anatomy but stays vague; where no_propositions happens.
    ("blanket", ["no significant change", "no interval change",
                 "no change", "no acute", "no significant acute",
                 "unremarkable", "no abnormalit", "no evidence of"]),
    # rule 3 -- coordination; where entity_text_not_in_utterance happens.
    ("coordination", [", and ", ", or ", " or ", "and endotracheal",
                      "and enteric", "and tricuspid", "and mitral"]),
    ("inference", ["suggesting", "suggestive of", "likely", "cannot exclude",
                   "cannot be excluded", "may represent", "possible",
                   "probable", "consistent with", "concerning for",
                   "versus"]),
    ("device", ["tip", "terminates", "svc", "carina", "in place",
                "catheter", "picc", "tube", "line"]),
    ("multi_location", ["upper and lower", "upper and mid", "bilateral",
                        "and left", "and right"]),
    ("temporal", ["new", "unchanged", "stable", "improved", "worsened",
                  "increased", "decreased", "resolved", "remains",
                  "compared", "interval"]),
    ("normal", ["normal", "clear", "within normal limits",
                "grossly normal"]),
]

# The limitation cues on their own, for callers that want just that set.
LIMITATION_CUES = CUE_TABLE[0][1]

ALWAYS_FIRST = "basic"
_QUALIFIED = "qualified"
_MULTI = "multi_location"

MAX_EXAMPLES = 4
CUE_SLOTS = 2

_NEGATION = ["no ", "no.", "not ", "without", "free of", "negative for",
             "absent", "unremarkable"]


def _hit(text: str, cue: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(cue.strip()) +
                     r"(?![a-z0-9])", text) is not None


def cue_match(utterance: str) -> Optional[str]:
    """The first example name whose cue fires, or None."""
    text = (utterance or "").lower()
    for name, cues in CUE_TABLE:
        if any(_hit(text, c) for c in cues):
            return name
    return None


def select(utterance: str, max_examples: int = MAX_EXAMPLES) -> List[str]:
    """Two always-on slots, then CUE_SLOTS cue slots, first hit wins."""
    text = (utterance or "").lower()
    picked = [ALWAYS_FIRST]
    second = _QUALIFIED if any(_hit(text, c) for c in _NEGATION) else _MULTI
    picked.append(second)

    for name, cues in CUE_TABLE:
        if len(picked) >= min(max_examples, 2 + CUE_SLOTS):
            break
        if name in picked or name not in EXAMPLES:
            continue
        if any(_hit(text, c) for c in cues):
            picked.append(name)

    if len(picked) == 2:
        picked.append(_MULTI if second == _QUALIFIED else _QUALIFIED)

    for name in picked:
        if name not in EXAMPLES:
            raise KeyError(f"selection asked for unknown example {name!r}")
    return picked[:max_examples]


def selected(utterance: str, max_examples: int = MAX_EXAMPLES
             ) -> List[Dict[str, Any]]:
    """The examples themselves, ready to be rendered into the prompt."""
    return [EXAMPLES[n] for n in select(utterance, max_examples)]


__all__ = ["CUE_TABLE", "MAX_EXAMPLES", "CUE_SLOTS", "LIMITATION_CUES",
           "select", "selected", "cue_match"]
