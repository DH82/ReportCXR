"""
Everything that is sent to the model, plus the tables its answer is judged
against.

One module per section of MD/Ko-SRRG_CXR_5category_parser_simple.md, because
section of the specification and a file here should be the same unit of
change:

    spec section    module              what it holds
    -----------------------------------------------------------------------
    2               schema.py           the JSON Schema one call must answer
    3               system.py           the system prompt, verbatim
    4               user_template.py    the user message, and how it renders
    5, 6            examples.py         the few-shot pool, as literal replies
    7               selection.py        which 3-4 of them this utterance gets
    (2's enums)     vocabulary.py       the closed answer spaces
    (8's step 2)    ontology.py         the normalization lookup tables

Nothing in this package calls the model or touches the filesystem. The three
steps of Section 8 live one directory up:

    qwen_client.py   step 1   LLM extraction
    normalize.py     step 2   deterministic ontology normalization
    validate.py      step 3   rule-based validation

Import from the package, not from the modules:

    from Prompt import SYSTEM_PROMPT, PROPOSITIONS, TOOL_NAME, select

Adding a factor means editing vocabulary.py AND schema.py AND the rule in
system.py that offers it. Adding a synonym means editing ontology.py only.
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
