"""Sections 5 and 6 -- the few-shot pool.

One dict per example: the input, and the answer the model should have given,
in the exact shape one call returns. selection.py picks 3-4 per utterance.

    basic  negation_multi  qualified  multi_location
    device  inference  temporal  normal
"""

from typing import Any, Dict, List

# -- Section 5 ---------------------------------------------------------------

BASIC = {
    "name": "basic",
    "input": {
        "utterance_id": "10_pleura_01",
        "utterance": "There is no pleural effusion.",
        "section": "Pleura",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                "entity": {"text": "pleural effusion",
                           "label": "pleural_effusion", "type": "finding"},
                "anatomy": [{"text": "pleural", "label": "pleura",
                             "laterality": "unspecified", "zone": None,
                             "role": "site", "source": "utterance"}],
                "descriptors": [],
                "assertion": {"label": "absent", "cue": "no"},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
        ],
        "warnings": [],
    },
}

# rule 2: the negation scopes over both entities, so the cue is copied into both.
NEGATION_MULTI = {
    "name": "negation_multi",
    "input": {
        "utterance_id": "11_pleura_01",
        "utterance": "No pleural effusion or pneumothorax.",
        "section": "Pleura",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                "entity": {"text": "pleural effusion",
                           "label": "pleural_effusion", "type": "finding"},
                "anatomy": [{"text": "pleural", "label": "pleura",
                             "laterality": "unspecified", "zone": None,
                             "role": "site", "source": "utterance"}],
                "descriptors": [],
                "assertion": {"label": "absent", "cue": "No"},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
            {
                "id": "p2",
                "entity": {"text": "pneumothorax", "label": "pneumothorax",
                           "type": "finding"},
                "anatomy": [{"text": None, "label": "pleura",
                             "laterality": "unspecified", "zone": None,
                             "role": "site", "source": "entity_semantics"}],
                "descriptors": [],
                "assertion": {"label": "absent", "cue": "No"},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
        ],
        "warnings": [],
    },
}

# -- Section 6 A -------------------------------------------------------------

QUALIFIED = {
    "name": "qualified",
    "input": {
        "utterance_id": "12_pleura_01",
        "utterance": "No large pleural effusion.",
        "section": "Pleura",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                "entity": {"text": "pleural effusion",
                           "label": "pleural_effusion", "type": "finding"},
                "anatomy": [{"text": "pleural", "label": "pleura",
                             "laterality": "unspecified", "zone": None,
                             "role": "site", "source": "utterance"}],
                # rule 9: "large" is size, never severity.
                "descriptors": [{"text": "large", "type": "size",
                                 "label": "large"}],
                "assertion": {"label": "absent", "cue": "No"},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
        ],
        # rule 11: the negation is over "large pleural effusion".
        "warnings": [
            "Qualified negation: smaller pleural effusion is not excluded."],
    },
}

# -- Section 6 B -------------------------------------------------------------

MULTI_LOCATION = {
    "name": "multi_location",
    "input": {
        "utterance_id": "13_lungs_01",
        "utterance": "Multifocal consolidation in the right upper and lower "
                     "lobes.",
        "section": "Lungs and Airways",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                "entity": {"text": "consolidation", "label": "consolidation",
                           "type": "finding"},
                # rule 2: one proposition with two anatomy entries, not two propositions.
                "anatomy": [
                    {"text": "right upper", "label": "right_upper_lobe",
                     "laterality": "right", "zone": "upper", "role": "site",
                     "source": "utterance"},
                    {"text": "lower lobes", "label": "right_lower_lobe",
                     "laterality": "right", "zone": "lower", "role": "site",
                     "source": "utterance"},
                ],
                "descriptors": [{"text": "Multifocal", "type": "distribution",
                                 "label": "multifocal"}],
                "assertion": {"label": "present", "cue": None},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
        ],
        "warnings": [],
    },
}

# -- Section 6 C -------------------------------------------------------------

DEVICE = {
    "name": "device",
    "input": {
        "utterance_id": "14_devices_01",
        "utterance": "Left subclavian PICC line in place with tip in the "
                     "distal SVC, unchanged in position.",
        "section": "Tubes, Catheters, and Support Devices",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                "entity": {"text": "PICC line", "label": "picc_line",
                           "type": "device"},
                # rule 7: where it goes in, and where it ends up, are two
                # different statements about the same device.
                "anatomy": [
                    {"text": "Left subclavian",
                     "label": "left_subclavian_region", "laterality": "left",
                     "zone": None, "role": "insertion_site",
                     "source": "utterance"},
                    {"text": "distal SVC", "label": "distal_svc",
                     "laterality": "midline", "zone": None,
                     "role": "tip_location", "source": "utterance"},
                ],
                "descriptors": [{"text": "tip in the distal SVC",
                                 "type": "device_position",
                                 "label": "tip_in_distal_svc"}],
                "assertion": {"label": "present", "cue": "in place"},
                "comparison": {"label": "stable",
                               "cue": "unchanged in position"},
                "derived_from": None,
            },
        ],
        "warnings": [],
    },
}

# -- Section 6 D -------------------------------------------------------------

NOTE_D = """Section 6 D gives only the four expected propositions in prose:

    p1: right infrahilar opacity - present
    p2: atelectasis - uncertain - derived_from p1
    p3: pulmonary edema - uncertain - derived_from p1
    p4: pulmonary infection - uncertain - derived_from p1

and says to encode all four in the Section 2 schema. The encoding below is
this file's, and two choices in it are worth knowing about because they are
the ones a reader would otherwise have to guess:

  * p2 and p3 carry the anatomy of p1 with source "linked_proposition". They
    are interpretations OF that opacity, so they are at its location, but the
    location is not restated in their own clause.
  * p4 has no anatomy at all. "concurrent infection cannot be excluded" is a
    separate clause that names no location, and rule 3 forbids inventing one.
"""

_RIGHT_INFRAHILAR_LINKED = {
    "text": None, "label": "right_infrahilar_region", "laterality": "right",
    "zone": "perihilar", "role": "site", "source": "linked_proposition",
}

INFERENCE = {
    "name": "inference",
    "input": {
        "utterance_id": "15_lungs_01",
        "utterance": "Right infrahilar opacity suggesting atelectasis or "
                     "edema; concurrent infection cannot be excluded.",
        "section": "Lungs and Airways",
    },
    "output": {
        "propositions": [
            # rule 6: the observation is asserted; the readings of it are not.
            {
                "id": "p1",
                "entity": {"text": "opacity", "label": "opacity",
                           "type": "finding"},
                "anatomy": [{"text": "Right infrahilar",
                             "label": "right_infrahilar_region",
                             "laterality": "right", "zone": "perihilar",
                             "role": "site", "source": "utterance"}],
                "descriptors": [],
                "assertion": {"label": "present", "cue": None},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
            {
                "id": "p2",
                "entity": {"text": "atelectasis", "label": "atelectasis",
                           "type": "disease"},
                "anatomy": [dict(_RIGHT_INFRAHILAR_LINKED)],
                "descriptors": [],
                "assertion": {"label": "uncertain", "cue": "suggesting"},
                "comparison": {"label": "none", "cue": None},
                "derived_from": "p1",
            },
            {
                "id": "p3",
                "entity": {"text": "edema", "label": "pulmonary_edema",
                           "type": "disease"},
                "anatomy": [dict(_RIGHT_INFRAHILAR_LINKED)],
                "descriptors": [],
                "assertion": {"label": "uncertain", "cue": "suggesting"},
                "comparison": {"label": "none", "cue": None},
                "derived_from": "p1",
            },
            {
                "id": "p4",
                "entity": {"text": "infection", "label": "pulmonary_infection",
                           "type": "disease"},
                "anatomy": [],
                "assertion": {"label": "uncertain",
                              "cue": "cannot be excluded"},
                "descriptors": [],
                "comparison": {"label": "none", "cue": None},
                "derived_from": "p1",
            },
        ],
        "warnings": [],
    },
}

# -- cues Section 7 selects on but Section 6 does not write out --------------

TEMPORAL = {
    "name": "temporal",
    "input": {
        "utterance_id": "16_lungs_01",
        "utterance": "Right lower lobe atelectasis has improved compared with "
                     "the prior study.",
        "section": "Lungs and Airways",
    },
    "output": {
        "propositions": [
            {
                "id": "p1",
                "entity": {"text": "atelectasis", "label": "atelectasis",
                           "type": "finding"},
                "anatomy": [{"text": "Right lower lobe",
                             "label": "right_lower_lobe",
                             "laterality": "right", "zone": "lower",
                             "role": "site", "source": "utterance"}],
                "descriptors": [],
                # rule 12: improvement is a comparison; the finding is still present.
                "assertion": {"label": "present", "cue": None},
                "comparison": {"label": "improved", "cue": "improved"},
                "derived_from": None,
            },
        ],
        "warnings": [],
    },
}

NORMAL = {
    "name": "normal",
    "input": {
        "utterance_id": "17_lungs_01",
        "utterance": "The lungs are clear.",
        "section": "Lungs and Airways",
    },
    "output": {
        "propositions": [
            # rule 14: one anatomical_state proposition. NOT an absent
            # proposition for every lung disease that would have been visible.
            {
                "id": "p1",
                "entity": {"text": "lungs are clear", "label": "clear_lungs",
                           "type": "anatomical_state"},
                "anatomy": [{"text": "lungs", "label": "lungs",
                             "laterality": "bilateral", "zone": None,
                             "role": "site", "source": "utterance"}],
                "descriptors": [{"text": "clear", "type": "normality",
                                 "label": "clear"}],
                "assertion": {"label": "present", "cue": None},
                "comparison": {"label": "none", "cue": None},
                "derived_from": None,
            },
        ],
        "warnings": [],
    },
}

EXAMPLES: Dict[str, Dict[str, Any]] = {
    e["name"]: e for e in (BASIC, NEGATION_MULTI, QUALIFIED, MULTI_LOCATION,
                           DEVICE, INFERENCE, TEMPORAL, NORMAL)
}

ALL_NAMES: List[str] = list(EXAMPLES)

__all__ = ["EXAMPLES", "ALL_NAMES", "NOTE_D", "BASIC", "NEGATION_MULTI",
           "QUALIFIED", "MULTI_LOCATION", "DEVICE", "INFERENCE", "TEMPORAL",
           "NORMAL"]
