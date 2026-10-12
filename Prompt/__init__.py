"""Prompt v1 -- the original prompt, preserved verbatim. One module per spec section.

    schema.py  (2)   system.py  (3)   user_template.py  (4)
    examples.py (5,6)   selection.py  (7)
    vocabulary.py    the closed answer spaces
    ontology.py      the step 2 lookup tables (NOT the ones in use; see Prompt2)

Nothing here calls the model or touches the filesystem.
See README.md for what runs it.
"""

from Prompt.vocabulary import (
    ANATOMY_ROLES,
    ANATOMY_SOURCES,
    ASSERTION_LABELS,
    COMPARISON_LABELS,
    DESCRIPTOR_TYPES,
    ENTITY_TYPES,
    LATERALITY,
    ZONES,
)
from Prompt.schema import FULL_RECORD, PROPOSITION, PROPOSITIONS, TOOL_NAME
from Prompt.system import SYSTEM_PROMPT
from Prompt.user_template import USER_TEMPLATE, input_block, render
from Prompt.examples import ALL_NAMES, EXAMPLES, NOTE_D
from Prompt.selection import CUE_TABLE, MAX_EXAMPLES, cue_match, select, selected
from Prompt import ontology

__all__ = [
    "SYSTEM_PROMPT",
    "PROPOSITIONS", "PROPOSITION", "FULL_RECORD", "TOOL_NAME",
    "USER_TEMPLATE", "render", "input_block",
    "EXAMPLES", "ALL_NAMES", "NOTE_D",
    "select", "selected", "cue_match", "CUE_TABLE", "MAX_EXAMPLES",
    "ENTITY_TYPES", "LATERALITY", "ZONES", "ANATOMY_ROLES", "ANATOMY_SOURCES",
    "DESCRIPTOR_TYPES", "ASSERTION_LABELS", "COMPARISON_LABELS",
    "ontology",
]
