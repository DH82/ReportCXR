"""v2 schema: the v1 document with the zone enum widened, nothing else.

The structure has one source, Prompt/schema.py. v1's zone enum lacks the E2
vessel segments (proximal/mid/distal), which the grammar would then forbid.
The assertion below fails at import if anything but zone differs.
"""

import copy

from Prompt.schema import FULL_RECORD as _V1_FULL
from Prompt.schema import PROPOSITION as _V1_PROPOSITION
from Prompt.schema import PROPOSITIONS as _V1_PROPOSITIONS
from Prompt.schema import TOOL_NAME                      # same tool name on both arms
from Prompt2.vocabulary import ZONES


PROPOSITION = copy.deepcopy(_V1_PROPOSITION)
PROPOSITION["properties"]["anatomy"]["items"]["properties"]["zone"]["enum"] = list(ZONES)

PROPOSITIONS = copy.deepcopy(_V1_PROPOSITIONS)
PROPOSITIONS["properties"]["propositions"]["items"] = PROPOSITION

FULL_RECORD = copy.deepcopy(_V1_FULL)
FULL_RECORD["properties"]["propositions"]["items"] = PROPOSITION


def _assert_only_zone_differs() -> None:
    """Fail loudly if v1 and v2 differ anywhere but the zone enum."""
    probe = copy.deepcopy(PROPOSITIONS)
    zone = probe["properties"]["propositions"]["items"]["properties"]["anatomy"]
    zone["items"]["properties"]["zone"]["enum"] = list(
        _V1_PROPOSITION["properties"]["anatomy"]["items"]["properties"]["zone"]["enum"])
    if probe != _V1_PROPOSITIONS:
        raise AssertionError(
            "Prompt2/schema.py: v1 and v2 differ somewhere other than zone. "
            "If Prompt/schema.py changed, update this file with it.")


_assert_only_zone_differs()

__all__ = ["TOOL_NAME", "PROPOSITION", "PROPOSITIONS", "FULL_RECORD"]
