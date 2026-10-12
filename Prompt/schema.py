"""Section 2 -- the JSON Schema the model must answer.

llama.cpp compiles this into a GGBNF grammar, so anything left loose here is
something the model may get wrong.

    PROPOSITIONS   what one call returns (propositions + warnings only)
    FULL_RECORD    the whole record as written to disk
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

TOOL_NAME = "return_propositions"

_ENTITY = {
    "type": "object",
    "properties": {
        # rule 3: copied from the utterance, not paraphrased.
        "text": {"type": "string"},
        # canonical_snake_case; normalize.py is what actually guarantees it.
        "label": {"type": "string"},
        "type": {"type": "string", "enum": ENTITY_TYPES},
    },
    "required": ["text", "label", "type"],
    "additionalProperties": False,
}

_ANATOMY = {
    "type": "object",
    "properties": {
        "text": {"type": ["string", "null"]},
        "label": {"type": ["string", "null"]},
        "laterality": {"type": "string", "enum": LATERALITY},
        "zone": {"enum": ZONES},
        "role": {"type": "string", "enum": ANATOMY_ROLES},
        "source": {"type": "string", "enum": ANATOMY_SOURCES},
    },
    "required": ["text", "label", "laterality", "zone", "role", "source"],
    "additionalProperties": False,
}

_DESCRIPTOR = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "type": {"type": "string", "enum": DESCRIPTOR_TYPES},
        "label": {"type": "string"},
    },
    "required": ["text", "type", "label"],
    "additionalProperties": False,
}

_ASSERTION = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ASSERTION_LABELS},
        "cue": {"type": ["string", "null"]},
    },
    "required": ["label", "cue"],
    "additionalProperties": False,
}

_COMPARISON = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": COMPARISON_LABELS},
        "cue": {"type": ["string", "null"]},
    },
    "required": ["label", "cue"],
    "additionalProperties": False,
}

PROPOSITION = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},                 # "p1", "p2", ...
        "entity": _ENTITY,
        "anatomy": {"type": "array", "items": _ANATOMY},
        "descriptors": {"type": "array", "items": _DESCRIPTOR},
        "assertion": _ASSERTION,
        "comparison": _COMPARISON,
        # rule 6: an interpretation points back at what it was inferred from.
        "derived_from": {"type": ["string", "null"]},
    },
    "required": ["id", "entity", "anatomy", "descriptors", "assertion",
                 "comparison", "derived_from"],
    "additionalProperties": False,
}

# What one API call returns.
PROPOSITIONS = {
    "type": "object",
    "properties": {
        # rule 2: zero, one, or many. An empty array is a legal answer.
        "propositions": {"type": "array", "items": PROPOSITION},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["propositions", "warnings"],
    "additionalProperties": False,
}

# The Section 2 record as it is written to disk.
FULL_RECORD = {
    "type": "object",
    "properties": {
        "utterance_id": {"type": ["string", "null"]},
        "utterance": {"type": "string"},
        "section": {"type": ["string", "null"]},
        "propositions": {"type": "array", "items": PROPOSITION},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["utterance_id", "utterance", "section", "propositions",
                 "warnings"],
    "additionalProperties": False,
}

__all__ = ["TOOL_NAME", "PROPOSITION", "PROPOSITIONS", "FULL_RECORD"]
