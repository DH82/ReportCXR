"""Section 7 -- picking the few-shot examples for one utterance.

Deterministic by construction: cues are tried in CUE_TABLE order and the
first hit wins. Already-picked examples are skipped, never repeated.
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

# Second slot is a choice, not a pair: "qualified-negation OR multi-location".
ALWAYS_FIRST = "basic"
_QUALIFIED = "qualified"
_MULTI = "multi_location"

MAX_EXAMPLES = 4

# Qualified negation only when the utterance actually negates.
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

    # Cue slot; skip anything already picked.
    for name, cues in CUE_TABLE:
        if name in picked:
            continue
        if any(_hit(text, c) for c in cues):
            picked.append(name)
            break

    # No cue fired: fill with the other half of the always-on pair (never 2 examples).
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
