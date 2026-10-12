"""The prompt in use (v3.4), and the ontology in use.

Prompt/ keeps the original v1 prompt untouched as the baseline; everything the
E1/E3/E2 record reviews and the corpus fixed lives here, and step 2, step 3 and
Verify/ all read these tables. Prompt3/ used to hold the v3 prompt as a set of
patches applied to v2's text at import time; it was merged into this package,
so the text below is the final prompt as one document and there is no second
prompt package to keep in step.

    system.py      the prompt (v2's rules 2/3/7/11/16/17 + the v3 patches)
    examples.py    11 examples, each a step 2 fixed point
    selection.py   which of them an utterance gets
    ontology.py    step 2 tables -- the source of the ontology fingerprint
    vocabulary.py  closed answer spaces, including the E2 vessel zones
    relations.py   concepts and relations RadLex does not have
    schema.py      v1 schema with the zone enum widened

The A/B arms share these tables: if the tables moved per arm, a metric change
could not be attributed to the prompt. Because the merge resolved the v3
patches in place, the v2 prompt text is no longer importable -- it is in git
history, and the v2 arm's results are already recorded in out/ab/out.jsonl.
See README.md.
"""

from Prompt.user_template import USER_TEMPLATE, input_block, render   # same as v1

from Prompt2.vocabulary import (
    ANATOMY_ROLES, ANATOMY_SOURCES, ASSERTION_LABELS, COMPARISON_LABELS,
    DESCRIPTOR_TYPES, ENTITY_TYPES, LATERALITY, LUNG_ZONES, VESSEL_SEGMENTS,
    VESSEL_SEGMENT_ALIASES, ZONES,
)
from Prompt2.schema import FULL_RECORD, PROPOSITION, PROPOSITIONS, TOOL_NAME
from Prompt2.system import SYSTEM_PROMPT
from Prompt2.examples import ALL_NAMES, EXAMPLES, NOTE_D
from Prompt2.selection import (CUE_TABLE, LIMITATION_CUES, MAX_EXAMPLES,
                               cue_match, select, selected)
from Prompt2 import ontology
from Prompt2 import relations

__all__ = [
    "SYSTEM_PROMPT",
    "PROPOSITIONS", "PROPOSITION", "FULL_RECORD", "TOOL_NAME",
    "USER_TEMPLATE", "render", "input_block",
    "EXAMPLES", "ALL_NAMES", "NOTE_D",
    "select", "selected", "cue_match", "CUE_TABLE", "MAX_EXAMPLES",
    "LIMITATION_CUES",
    "ENTITY_TYPES", "LATERALITY", "ZONES", "LUNG_ZONES", "VESSEL_SEGMENTS",
    "VESSEL_SEGMENT_ALIASES", "ANATOMY_ROLES", "ANATOMY_SOURCES",
    "DESCRIPTOR_TYPES", "ASSERTION_LABELS", "COMPARISON_LABELS",
    "ontology", "relations",
]
