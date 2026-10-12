"""
Everything maplez_struct.py sends to the API, plus the value sets and lookup
tables it judges the answers against.

One module per API question. Each prompt module holds the prompt template and
the tool schema that question must answer with, because the two only ever
change together.

    system.py            the system prompt, sent with every call
    p0_entity.py         e0  which single finding is this line about
    p1_presence.py       q1  Present / Uncertain / Absent / Not asserted
    p2_location.py       q2  localizing expressions
    p3_severity.py       q3  None .. Severe, or Undefined
    p4_change.py         q4  what the line says about change

Predefined content, shared by the modules above:

    vocabulary.py        the answer spaces (entity kinds, presence values,
                         severity ladder, change values)
    denominations.py     Appendix A.1.2 -- what the prompts call a finding,
                         and the open-vocabulary term -> paper label bridge
    location_tables.py   Appendix A.2.1-A.2.2 -- keyword rules applied to the
                         answer of prompt 2. These are NOT sent to the API.

Import from the package, not from the modules:

    from Prompt import SYSTEM_PROMPT, P0, S_ENTITY

Adding an axis means adding a module here and wiring one stage in
maplez_struct.py; changing an answer space means editing vocabulary.py AND the
prompt wording that offers those answers.
"""

from Prompt.vocabulary import (
    ENTITY_TYPES,
    ANNOTATED_ENTITY_TYPES,
    SEVERITY_SCALE,
    SEVERITY_ORDINAL,
    SEVERITY_BY_ORDINAL,
    SEVERITY_WORDS,
    NO_SEVERITY_WORDS,
    SEVERITY_LOOKUP,
    CHANGE_VALUES,
    CHANGE_DIRECTION,
    CHANGE_CUES,
    PRESENT_LIKE,
    ABSENT_LIKE,
    CATEGORICAL_VALUES,
)
from Prompt.denominations import (
    DENOMINATIONS,
    DENOMINATIONS_ATTR,
    USE_GENERIC_DENOMINATIONS,
    TERM_ALIASES,
)
from Prompt.location_tables import (
    THORAX,
    LOCATION_KEYWORDS,
    RIB_ORDINALS,
    REPLACEMENT,
    MAKES_NEGATIVE,
    PREVENT_NEGATIVE,
)
from Prompt.system import SYSTEM_PROMPT
from Prompt.p0_entity import P0, S_ENTITY
from Prompt.p1_presence import P1, S_PRESENCE
from Prompt.p2_location import P2, S_EXPRESSIONS
from Prompt.p3_severity import P3, S_SEVERITY
from Prompt.p4_change import P4, S_CHANGE_CUE

# Stage id -> (prompt template, tool schema, tool name). The pipeline does not
# read this; it is here so that a caller can enumerate what gets sent.
PROMPTS = {
    "e0": (P0, S_ENTITY, "name_entity"),
    "q1": (P1, S_PRESENCE, "answer_presence"),
    "q2": (P2, S_EXPRESSIONS, "list_expressions"),
    "q3": (P3, S_SEVERITY, "answer_severity"),
    "q4": (P4, S_CHANGE_CUE, "answer_change"),
}

__all__ = [
    "SYSTEM_PROMPT", "PROMPTS",
    "P0", "P1", "P2", "P3", "P4",
    "S_ENTITY", "S_PRESENCE", "S_EXPRESSIONS", "S_SEVERITY", "S_CHANGE_CUE",
    "ENTITY_TYPES", "ANNOTATED_ENTITY_TYPES",
    "SEVERITY_SCALE", "SEVERITY_ORDINAL", "SEVERITY_BY_ORDINAL",
    "SEVERITY_WORDS", "NO_SEVERITY_WORDS", "SEVERITY_LOOKUP",
    "CHANGE_VALUES", "CHANGE_DIRECTION", "CHANGE_CUES",
    "PRESENT_LIKE", "ABSENT_LIKE", "CATEGORICAL_VALUES",
    "DENOMINATIONS", "DENOMINATIONS_ATTR", "USE_GENERIC_DENOMINATIONS",
    "TERM_ALIASES",
    "THORAX", "LOCATION_KEYWORDS", "RIB_ORDINALS", "REPLACEMENT",
    "MAKES_NEGATIVE", "PREVENT_NEGATIVE",
]
