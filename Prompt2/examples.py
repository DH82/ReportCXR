"""The few-shot pool in use: the v1 pool with an explicit patch table, plus 3.

v1's examples taught four anatomy labels that the ontology does not have, so
step 2 undid them on every call; two of them it could not undo. Every example
here is a step 2 fixed point instead. The patch table below is the record of
what changed -- copying the pool wholesale would let the two drift apart.

    blanket        rule 2 -- vague negation that produced no propositions
    coordination   rule 3 -- distributed coordination losing its text span
    limitation     rule 19 -- a sentence about the examination, not the patient
                   (added with v3, when Prompt3/ was merged into this package)
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from Prompt.examples import EXAMPLES as _V1, NOTE_D  # noqa: F401

# -- patch 1: strip laterality out of anatomy labels (rule 16 / E1) -----------
# v1 already wrote the correct laterality field, so fixing the label loses nothing.
_ANATOMY_LABEL = {
    "right_upper_lobe": "upper_lobe",
    "right_lower_lobe": "lower_lobe",
    "left_subclavian_region": "subclavian_region",
    "right_infrahilar_region": "infrahilar_region",
}

# -- patch 2: vessel segment becomes a zone (rule 7 / E2) ---------------------
# distal_svc packs structure and segment into one label; VESSEL_SEGMENTS holds it.
_VESSEL = {"distal_svc": ("svc", "distal")}

# -- patch 3: strip normality out of entity labels (rule 14 / E3) -------------
_ENTITY_LABEL = {"clear_lungs": "lungs"}

# -- patch 4: drop tip position from descriptors (rule 7) ---------------------
# The anatomy entry with role=tip_location already says it.
_DROP_DESCRIPTOR_LABELS = {"tip_in_distal_svc"}


def _patch(ex: Dict[str, Any]) -> Dict[str, Any]:
    ex = copy.deepcopy(ex)
    for p in ex["output"]["propositions"]:
        ent = p["entity"]
        ent["label"] = _ENTITY_LABEL.get(ent["label"], ent["label"])
        for a in p.get("anatomy") or []:
            lab = a.get("label")
            if lab in _VESSEL:
                a["label"], a["zone"] = _VESSEL[lab]
            else:
                a["label"] = _ANATOMY_LABEL.get(lab, lab)
        p["descriptors"] = [d for d in (p.get("descriptors") or [])
                            if d.get("label") not in _DROP_DESCRIPTOR_LABELS]
    return ex


# -- new example 1: rule 2 -- a vague sentence still yields propositions ------
# The point is the line between a genuinely empty sentence and a vague one that
# still names anatomy.
BLANKET = {
    "name": "blanket",
    "input": {
        "utterance_id": "18_msk_01",
        "utterance": "No significant change in the soft tissues and osseous "
                     "structures.",
        "section": "Musculoskeletal and Chest Wall",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                "entity": {"text": "soft tissues", "label": "soft_tissue",
                           "type": "anatomical_state"},
                "anatomy": [{"text": "soft tissues", "label": "soft_tissue",
                             "laterality": "unspecified", "zone": None,
                             "role": "site", "source": "utterance"}],
                "descriptors": [],
                # rule 2: "no significant change" is stability, not absence.
                "assertion": {"label": "present", "cue": None},
                "comparison": {"label": "stable",
                               "cue": "No significant change"},
                "derived_from": None,
            },
            {
                "id": "p2",
                "entity": {"text": "osseous structures",
                           "label": "osseous_structure",
                           "type": "anatomical_state"},
                "anatomy": [{"text": "osseous structures",
                             "label": "osseous_structure",
                             "laterality": "unspecified", "zone": None,
                             "role": "site", "source": "utterance"}],
                "descriptors": [],
                "assertion": {"label": "present", "cue": None},
                "comparison": {"label": "stable",
                               "cue": "No significant change"},
                "derived_from": None,
            },
        ],
        "warnings": [],
    },
}

# -- new example 2: rule 3 -- text and label split under coordination ---------
# "enteric tubes" is not a contiguous span; writing it as text breaks rule 3,
# not splitting the proposition breaks rule 2. v1 left the two in conflict.
COORDINATION = {
    "name": "coordination",
    "input": {
        "utterance_id": "19_devices_01",
        "utterance": "No enteric or endotracheal tubes visualized.",
        "section": "Tubes, Catheters, and Support Devices",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                # text is only what can be pointed at; the concept is the label.
                "entity": {"text": "enteric", "label": "enteric_tube",
                           "type": "device"},
                "anatomy": [],
                "descriptors": [],
                "assertion": {"label": "absent", "cue": "No"},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
            {
                "id": "p2",
                "entity": {"text": "endotracheal tubes",
                           "label": "endotracheal_tube", "type": "device"},
                "anatomy": [],
                "descriptors": [],
                "assertion": {"label": "absent", "cue": "No"},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
        ],
        "warnings": [],
    },
}

# -- rule 19: the sentence says what could NOT be read --------------------------
# v1 kept only the osseous_structures proposition and dropped the clause after
# the semicolon, so a limited reading is stored as an ordinary one.
LIMITATION = {
    "name": "limitation",
    "input": {
        "utterance_id": "21_msk_01",
        "utterance": "Osseous structures appear grossly unremarkable; "
                     "limited evaluation due to body habitus.",
        "section": "Musculoskeletal and Chest Wall",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                "entity": {"text": "Osseous structures",
                           "label": "osseous_structure",
                           "type": "anatomical_state"},
                "anatomy": [{"text": "Osseous structures",
                             "label": "osseous_structure",
                             "laterality": "unspecified", "zone": None,
                             "role": "site", "source": "utterance"}],
                # rule 20: normality is a descriptor, never part of the label.
                "descriptors": [{"text": "unremarkable", "type": "normality",
                                 "label": "normal"}],
                "assertion": {"label": "present", "cue": None},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
            {
                "id": "p2",
                "entity": {"text": "limited evaluation",
                           "label": "limited_evaluation", "type": "other"},
                # rule 18: the structure is not named in this clause, so the
                # entry carries no text.
                "anatomy": [{"text": None, "label": "osseous_structure",
                             "laterality": "unspecified", "zone": None,
                             "role": "site", "source": "linked_proposition"}],
                "descriptors": [{"text": "body habitus", "type": "other",
                                 "label": "body_habitus"}],
                "assertion": {"label": "present", "cue": None},
                "comparison": {"label": "none", "cue": None},
                "derived_from": "p1",
            },
        ],
        "warnings": [
            "Assessment limited: the osseous structures were read on a "
            "limited examination.",
        ],
    },
}

EXAMPLES: Dict[str, Dict[str, Any]] = {n: _patch(e) for n, e in _V1.items()}
EXAMPLES["blanket"] = BLANKET
EXAMPLES["coordination"] = COORDINATION
EXAMPLES["limitation"] = LIMITATION

ALL_NAMES: List[str] = list(EXAMPLES)

__all__ = ["EXAMPLES", "ALL_NAMES", "NOTE_D", "BLANKET", "COORDINATION",
           "LIMITATION"]
