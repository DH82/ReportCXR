"""
Section 7 -- which few-shot examples this utterance gets.

The rule is fixed and the code is the rule, nothing more:

    always      one basic negation example
    always      one qualified-negation OR multi-location example
    then        at most one more, chosen by a cue in the utterance
    fallback    if no cue fires, the other half of the always-on pair
    cap         3-4 examples

    | cue in input                                | example       |
    | suggesting, likely, cannot exclude, or      | inference     |
    | tip, terminates, SVC, carina                | device        |
    | upper and lower, upper and mid              | multi_location|
    | new, unchanged, stable, improved            | temporal      |
    | normal, clear, within normal limits         | normal_state  |

Two things the table leaves open, decided here and only here:

  * More than one cue can fire. They are tried in the table's own order and
    the first hit wins, so selection stays deterministic -- the same utterance
    must produce the same prompt on every run, or the temperature-0 seed-0
    setting in qwen_client.py buys nothing.
  * "upper and lower" is both a cue and the second always-on slot. When it
    fires, multi_location has already been sent, so the cue slot falls through
    to the next matching cue rather than sending the same example twice.

Cues are matched on word boundaries against the lowercased utterance. "or" as
a substring would match "aorta"; "SVC" as a substring would match nothing else
but is matched the same way for consistency.

pipeline.py imports select(); nothing in this package imports back.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from Prompt.examples import EXAMPLES

# Section 7's table, in its own order. Multi-word cues are matched as phrases.
CUE_TABLE = [
    ("inference", ["suggesting", "suggestive of", "likely", "cannot exclude",
                   "cannot be excluded", "may represent", "possible",
                   "probable", "consistent with", "concerning for",
                   "versus", " or "]),
    ("device", ["tip", "terminates", "svc", "carina", "in place",
                "catheter", "picc", "tube", "line"]),
    ("multi_location", ["upper and lower", "upper and mid", "bilateral",
                        "and left", "and right"]),
    ("temporal", ["new", "unchanged", "stable", "improved", "worsened",
                  "increased", "decreased", "resolved", "remains",
                  "compared", "interval"]),
    ("normal", ["normal", "clear", "within normal limits", "unremarkable",
                "grossly normal"]),
]

# The two always-on slots. The second is a choice, not a pair: Section 7 says
# "qualified-negation OR multi-location".
ALWAYS_FIRST = "basic"
_QUALIFIED = "qualified"
_MULTI = "multi_location"

MAX_EXAMPLES = 4

# Qualified negation is the second slot only when the utterance actually
# negates something; otherwise the multi-location example is the more useful
# demonstration of how anatomy entries are grouped.
_NEGATION = ["no ", "no.", "not ", "without", "free of", "negative for",
             "absent", "unremarkable"]


def _hit(text: str, cue: str) -> bool:
    """Whole-word (or whole-phrase) match, so "or" does not match "aorta"."""
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
    """Section 7, applied. Returns example names in the order they are sent."""
    text = (utterance or "").lower()
    picked = [ALWAYS_FIRST]

    second = _QUALIFIED if any(n in text for n in _NEGATION) else _MULTI
    picked.append(second)

    # The cue slot. Anything already picked is skipped rather than repeated,
    # and the next firing cue is used instead.
    for name, cues in CUE_TABLE:
        if name in picked:
            continue
        if any(_hit(text, c) for c in cues):
            picked.append(name)
            break

    # Section 7 asks for three or four. When no cue fires, the slot is filled
    # with the other half of the always-on pair rather than left empty: a
    # request with two examples is the one shape Section 7 does not describe.
    if len(picked) < 3:
        other = _MULTI if second == _QUALIFIED else _QUALIFIED
        picked.append(other)

    for name in picked:
        if name not in EXAMPLES:
            raise KeyError(f"selection asked for unknown example {name!r}")
    return picked[:max(2, max_examples)]


def selected(utterance: str, max_examples: int = MAX_EXAMPLES
             ) -> List[Dict[str, Any]]:
    """The examples themselves, ready to be rendered into the prompt."""
    return [EXAMPLES[n] for n in select(utterance, max_examples)]


__all__ = ["CUE_TABLE", "MAX_EXAMPLES", "select", "selected", "cue_match"]
