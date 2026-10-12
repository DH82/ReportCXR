"""Step 2 lookup tables -- the ones actually in use. None of this is sent to the model.

    SECTIONS            SRRG heading -> broad anatomy + compatible groups (rule 4)
    ANATOMY             canonical label -> (laterality, zone, group)
    ANATOMY_ALIASES     surface text -> canonical anatomy label
    ENTITY_ALIASES      surface term -> canonical entity label
    DESCRIPTOR_LEXICON  word -> (descriptor type, value)   -- rule 9
    NEGATION/UNCERTAINTY/COMPARISON_CUES                   -- rules 10, 12

E1 (laterality), E2 (vessel segment) and E3 (normality) are applied here; the
tables' sizes are the ontology fingerprint printed at the head of every
verification report.
"""

import re
from typing import Dict, List, Optional, Tuple

# The segment vocabulary lives with the other closed answer spaces; E2's split
# is the only thing that reads it outside the schema.
from Prompt2.vocabulary import VESSEL_SEGMENT_ALIASES

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# =============================================================================
#  SECTIONS  -- rule 4
# =============================================================================
# The heading may fill a MISSING broad anatomy only: never laterality, zone or lobe.

# "groups" = COMPATIBLE with, not typical of. A narrow reading fires false
# conflicts; only odd pairings (lung under Abdominal) should warn.
SECTIONS: Dict[str, Dict[str, object]] = {
    "Lungs and Airways":                    # 960
        {"anatomy": "lungs",
         "groups": ["lung", "airway", "pleura", "hilum", "vessel",
                    "diaphragm", "chest_wall"]},
    "Cardiovascular":                       # 917
        {"anatomy": "cardiovascular_structures",
         # cardiogenic edema and vascular congestion are lung findings
         # discussed here as a matter of course.
         "groups": ["heart", "vessel", "mediastinum", "hilum", "lung"]},
    "Pleura":                               # 763
        # the costophrenic angle and the hemidiaphragm are where a pleural
        # finding is seen.
        {"anatomy": "pleura",
         "groups": ["pleura", "lung", "chest_wall", "diaphragm"]},
    "Musculoskeletal and Chest Wall":       # 485
        {"anatomy": "chest_wall",
         "groups": ["bone", "chest_wall", "pleura", "diaphragm"]},
    "Hila and Mediastinum":                 # 438
        # the spine is behind the mediastinum: scoliosis distorting the
        # mediastinal contour is described here, not under bones.
        {"anatomy": "mediastinum",
         "groups": ["mediastinum", "hilum", "vessel", "heart", "airway",
                    "bone"]},
    "Other":                                # 304
        {"anatomy": None, "groups": []},
    "Tubes, Catheters, and Support Devices":  # 292
        {"anatomy": None, "groups": []},     # a device may be anywhere
    "Abdominal":                            # 103
        {"anatomy": "upper_abdomen",
         "groups": ["abdomen", "diaphragm", "chest_wall"]},
}

# Headings that are written differently in some rows.
SECTION_ALIASES: Dict[str, str] = {
    "mediastinum and hila": "Hila and Mediastinum",
    "lung and airways": "Lungs and Airways",
    "lungs": "Lungs and Airways",
    "tubes and lines": "Tubes, Catheters, and Support Devices",
    "devices": "Tubes, Catheters, and Support Devices",
    "support devices": "Tubes, Catheters, and Support Devices",
    "bones": "Musculoskeletal and Chest Wall",
    "musculoskeletal": "Musculoskeletal and Chest Wall",
    # Heading-as-anatomy forms. Only ones that are not themselves anatomy labels.
    "abdomen": "Abdominal", "cardiovascular": "Cardiovascular",
    # Singular/plural and near-miss spellings of a canonical heading.
    "hilum and mediastinum": "Hila and Mediastinum",
    "pleural": "Pleura",
    "others": "Other",
    "chest wall": "Musculoskeletal and Chest Wall",
    "upper abdomen": "Abdominal",
    # Compound headings. A record carries one heading, so a heading that names
    # two SRRG sections has to resolve to one, and the choice is the one whose
    # `groups` does not fire a rule 4 conflict on the other half's anatomy:
    #   lungs/airways already lists pleura as compatible;
    #   the device heading carries groups [] and so conflicts with nothing,
    #   which is what a heading spanning devices AND bones needs.
    "lungs, airways, and pleura": "Lungs and Airways",
    "devices, musculoskeletal and chest wall":
        "Tubes, Catheters, and Support Devices",
}

# A record whose heading is missing entirely. "Other" is the SRRG section that
# entails no anatomy (`anatomy: None`, `groups: []`), so defaulting to it adds
# no claim about where the finding is -- it only stops `section: null` from
# leaving the record outside every section-scoped metric.
SECTION_FALLBACK = "Other"

# =============================================================================
#  ANATOMY
# =============================================================================
# canonical label -> (laterality, zone, group). These are what the LABEL entails:
# normalize.py fills unspecified fields from them, validate.py catches contradictions.
# None = the label does not settle it; the model's answer stands.

ANATOMY: Dict[str, Tuple[Optional[str], Optional[str], str]] = {
    # -- lung, whole
    "lungs":                    ("bilateral", None, "lung"),
    # -- lobes
    "lingula":                  ("left", None, "lung"),
    # -- zones and regions
    "lung_bases":               ("bilateral", "basilar", "lung"),
    "lung_apices":              ("bilateral", "apical", "lung"),
    # Retrocardiac is a projection, not a side -- laterality stays None.
    "retrocardiac_region":      (None, "retrocardiac", "lung"),
    # -- airway
    "trachea":                  ("midline", None, "airway"),
    "carina":                   ("midline", None, "airway"),
    "bronchi":                  ("bilateral", None, "airway"),
    # -- pleura
    "pleura":                   (None, None, "pleura"),
    "costophrenic_angles":      ("bilateral", "basilar", "pleura"),
    "pleural_fissure":          (None, None, "pleura"),
    # -- heart and vessels
    "heart":                    ("midline", None, "heart"),
    "cardiac_silhouette":       ("midline", None, "heart"),
    "aorta":                    ("midline", None, "vessel"),
    "thoracic_aorta":           ("midline", None, "vessel"),
    "aortic_arch":              ("midline", None, "vessel"),
    "pulmonary_vasculature":    ("bilateral", None, "vessel"),
    "svc":                      ("midline", None, "vessel"),
    "distal_svc":               ("midline", None, "vessel"),
    "cavoatrial_junction":      ("midline", None, "vessel"),
    # -- mediastinum and hila
    "mediastinum":              ("midline", None, "mediastinum"),
    "upper_mediastinum":        ("midline", "upper", "mediastinum"),
    "hila":                     ("bilateral", "perihilar", "hilum"),
    # -- bone and chest wall
    "ribs":                     (None, None, "bone"),
    "clavicles":                ("bilateral", None, "bone"),
    "spine":                    ("midline", None, "bone"),
    "thoracic_spine":           ("midline", None, "bone"),
    "sternum":                  ("midline", None, "bone"),
    "chest_wall":               (None, None, "chest_wall"),
    "soft_tissues":             (None, None, "chest_wall"),
    # -- diaphragm and abdomen
    "diaphragm":                ("bilateral", None, "diaphragm"),
    "upper_abdomen":            (None, None, "abdomen"),
    # The gastric bubble is left; the stomach an enteric tube terminates in
    # is described as midline as often as not. Not the label's call.
    "stomach":                  (None, None, "abdomen"),
    # -- catch-all groups used by SECTIONS
    # Catch-all for the Cardiovascular heading; asserts no side.
    "cardiovascular_structures": (None, None, "heart"),

    # -- labels observed from the model that had no row here
    "bones":                    (None, None, "bone"),          # 7
    "cardiomediastinal_silhouette": ("midline", None, "mediastinum"),  # 3
    "aortic_knob":              ("left", None, "vessel"),       # 2
    "lumbar_spine":             ("midline", None, "bone"),
    "thoracolumbar_spine":      ("midline", None, "bone"),
    "shoulders":                ("bilateral", None, "bone"),
    "esophagus":                ("midline", None, "mediastinum"),
    "hiatus":                   ("midline", None, "mediastinum"),
    "mid_svc":                  ("midline", None, "vessel"),
    "lung_parenchyma":          ("bilateral", None, "lung"),
    "mid_lung":                 (None, "middle", "lung"),
    "lung_lobe":                (None, None, "lung"),
    # Own label, not an alias: the reading is probable, and an alias must be certain.
    "upper_atrium":             (None, None, "heart"),
    "cavoatrial_junction_or_right_atrium": (None, None, "heart"),

    # -- added from rows 30-59 of validate.csv
    "cervical_spine":           ("midline", None, "bone"),   # 2
    "lower_cervical_spine":     ("midline", None, "bone"),   # 2
    "thoracic_skeleton":        (None, None, "bone"),
    "lateral_chest_wall":       (None, None, "chest_wall"),
    "aortic_valve":             (None, None, "heart"),
    "mitral_valve":             (None, None, "heart"),
    "coronary_sinus":           (None, None, "heart"),
    "low_svc":                  ("midline", None, "vessel"),
    "mid_to_distal_svc":        ("midline", None, "vessel"),
    "lung_interstitium":        ("bilateral", None, "lung"),
    "peribronchial_region":     (None, None, "airway"),
    "pleural_sinuses":          ("bilateral", "basilar", "pleura"),
    "subpulmonic_space":        (None, "basilar", "pleura"),
    "abdomen":                  (None, None, "abdomen"),
    "subdiaphragmatic_region":  (None, None, "abdomen"),

    # -- side-less form of every lateralizable structure. laterality is None by design.
    "upper_lobe":               (None, "upper", "lung"),
    "lower_lobe":               (None, "lower", "lung"),
    "lung_base":                (None, "basilar", "lung"),
    "apex":                     (None, "apical", "lung"),
    "perihilar_region":         (None, "perihilar", "lung"),
    "infrahilar_region":        (None, "perihilar", "lung"),
    "upper_lung_field":         (None, "upper", "lung"),
    "mid_lung_field":           (None, "middle", "lung"),
    "lower_lung_field":         (None, "lower", "lung"),
    "hemithorax":               (None, None, "lung"),
    "costophrenic_angle":       (None, "basilar", "pleura"),
    "apical_pleura":            (None, "apical", "pleura"),
    "hemidiaphragm":            (None, None, "diaphragm"),
    "heart_border":             (None, None, "heart"),
    "subclavian_region":        (None, None, "vessel"),
    "subclavian_vein":          (None, None, "vessel"),
    "internal_jugular_vein":    (None, None, "vessel"),
    "jugular_region":           (None, None, "vessel"),
    "peripheral_vein":          (None, None, "vessel"),
    "lateral_rib":              (None, None, "bone"),
    "upper_extremity":          (None, None, "chest_wall"),

    # -- E1: stems that appear once the side prefix is stripped --------------
    # implied is None ("the label does not settle the side"), except where the
    # structure itself exists on one side only.
    "atrium":                   (None, None, "heart"),
    "ventricle":                (None, None, "heart"),
    "atrium_and_right_ventricle": ("right", None, "heart"),   # right-only
    "clavicle":                 (None, None, "bone"),
    "shoulder":                 (None, None, "bone"),
    "hilum":                    (None, "perihilar", "hilum"),
    "lung":                     (None, None, "lung"),
    "main_bronchus":            (None, None, "airway"),
    "middle_lobe":              ("right", "middle", "lung"),  # no middle lobe on the left
    "pleural_space":            (None, None, "pleura"),
    # -- frequent stems that used to fall through as passthrough (P1a residue).
    #    Paired with the aliases below.
    "upper_quadrant":           (None, None, "abdomen"),
    "axilla":                   (None, None, "chest_wall"),
    "pectoral":                 (None, None, "chest_wall"),
    "breast":                   (None, None, "chest_wall"),
    "neck":                     (None, None, "chest_wall"),
    "arm":                      (None, None, "chest_wall"),
    "humerus":                  (None, None, "bone"),
    "humeral_head":             (None, None, "bone"),
    "acromioclavicular_joint":  (None, None, "bone"),
    "glenohumeral_joint":       (None, None, "bone"),
    "pulmonary_artery":         (None, None, "vessel"),
    "brachiocephalic_vein":     (None, None, "vessel"),
    "cardiophrenic_angle":      (None, "basilar", "pleura"),
}

# Surface form -> canonical label. Keys are lowercased, laterality stripped;
# normalize.py re-attaches the side it read from the text.
ANATOMY_ALIASES: Dict[str, str] = {
    "lung": "lungs", "both lungs": "lungs", "bilateral lungs": "lungs",
    "pulmonary": "lungs", "lung fields": "lungs", "lung field": "lungs",
    "upper lobe": "upper_lobe", "middle lobe": "middle_lobe",
    # "middle lung" is a zone, not a lobe; see LATERALIZABLE below for the
    # left-sided case, which is the one that matters.
    "middle lung": "mid_lung_field", "middle lung zone": "mid_lung_field",
    "middle lung field": "mid_lung_field",
    "lower lobe": "lower_lobe", "lower lobes": "lower_lobe",
    "base": "lung_base", "bases": "lung_bases", "basilar": "lung_base",
    "apex": "apex", "apices": "lung_apices", "apical": "apex",
    "perihilar": "perihilar_region", "infrahilar": "infrahilar_region",
    "retrocardiac": "retrocardiac_region",
    "pleural": "pleura", "pleural space": "pleura",
    "pleural surface": "pleura", "fissure": "pleural_fissure",
    "costophrenic angle": "costophrenic_angle",
    "costophrenic sulcus": "costophrenic_angle",
    "cardiac": "cardiac_silhouette", "cardiomediastinal": "mediastinum",
    "cardiac shadow": "cardiac_silhouette",
    "heart size": "cardiac_silhouette",
    "superior vena cava": "svc", "sv c": "svc",
    "cavoatrial": "cavoatrial_junction",
    "subclavian": "subclavian_region", "ij": "internal_jugular_vein",
    "internal jugular": "internal_jugular_vein",
    "hilar": "hila", "hilum": "hila", "hilus": "hila",
    "mediastinal": "mediastinum", "mediastinal contour": "mediastinum",
    "vasculature": "pulmonary_vasculature",
    "pulmonary vascularity": "pulmonary_vasculature",
    # The model answers this one inconsistently across runs; the table settles it.
    "pulmonary vascular": "pulmonary_vasculature",
    "pulmonary vessels": "pulmonary_vasculature",
    "pulmonary vessel": "pulmonary_vasculature",
    "rib": "ribs", "clavicle": "clavicles",
    "hemidiaphragm": "hemidiaphragm", "diaphragmatic": "diaphragm",
    "thorax": "chest_wall", "chest": "chest_wall",
    # -- from the first 30 rows of validate.csv
    "bone": "bones", "osseous": "bones", "osseous structures": "bones",
    "bony structures": "bones", "skeletal": "bones",
    "cardiomediastinum": "cardiomediastinal_silhouette",
    "cardiomediastinal silhouette": "cardiomediastinal_silhouette",
    "cardiomediastinal contours": "cardiomediastinal_silhouette",
    "aortic knob": "aortic_knob",
    "shoulder": "shoulders",
    "lateral rib": "lateral_rib", "lateral ribs": "lateral_rib",
    "upper lung field": "upper_lung_field",
    "upper lung zone": "upper_lung_field",
    "mid lung field": "mid_lung_field", "mid lung zone": "mid_lung_field",
    "lower lung field": "lower_lung_field",
    "lower lung zone": "lower_lung_field",
    "mid lung": "mid_lung", "midlung": "mid_lung",
    "parenchyma": "lung_parenchyma",
    "lung parenchyma": "lung_parenchyma",
    "subpleural": "pleura", "perifissural": "pleural_fissure",
    "apical pleura": "apical_pleura",
    "subdiaphragmatic": "subdiaphragmatic_region",
    "subdiaphragm": "subdiaphragmatic_region",
    "mid superior vena cava": "mid_svc", "mid svc": "mid_svc",
    "subclavian vein": "subclavian_vein",
    "peripheral vein": "peripheral_vein",
    "catheter line": None,          # a device, not a place; see below
    # The section heading leaking in as an anatomy. rule 4 allows the heading
    # to name a broad structure; it does not make the heading itself one.
    "lungs and airways": "lungs", "lung and airways": "lungs",
    "lobe": "lung_lobe", "midline": "mediastinum",
    # "bibasilar" is a distribution, but the model answers it as a place.
    # Both readings point at the same structure, so it resolves there.
    "bibasilar": "lung_bases", "bibasal": "lung_bases",
    "lung apex": "apex", "lung apices": "lung_apices",
    "mid-to-upper abdomen": "upper_abdomen",
    "mid to upper abdomen": "upper_abdomen",
    # -- from rows 30-59
    "hemithorax": "hemithorax",
    "upper zone": "upper_lung_field", "lower zone": "lower_lung_field",
    "apical area": "apex", "apical region": "apex",
    "lower lung": "lower_lung_field", "upper lung": "upper_lung_field",
    "peribronchial": "peribronchial_region",
    "interstitium": "lung_interstitium",
    "heart border": "heart_border",
    "jugular region": "jugular_region", "jugular": "jugular_region",
    "upper extremity": "upper_extremity",
    "osseous and soft tissue structures": "bones",
    "thoracic skeleton": "thoracic_skeleton",
    "mid-to-distal svc": "mid_to_distal_svc",
    "low superior vena cava": "low_svc", "low svc": "low_svc",
    # -- aliases found in verification: other wordings of labels that already exist.
    "basilar region": "lung_base", "basal region": "lung_base",
    "basilar lung": "lung_base", "basal": "lung_base",
    "basilar pleura": "pleura",
    "hilar region": "hilum",
    "midlung zone": "mid_lung_field", "mid lung zone": "mid_lung_field",
    "mainstem bronchus": "main_bronchus",
    "lower hemithorax": "hemithorax", "upper hemithorax": "hemithorax",
    "costophrenic sulcus": "costophrenic_angle",
    "costophrenic sulci": "costophrenic_angles",
    "pulmonary parenchyma": "lung_parenchyma",
    # singular/plural -- spelling only, nothing to do with laterality
    "upper lobes": "upper_lobe", "ventricles": "ventricle",
    "perihilar regions": "perihilar_region", "mid lungs": "mid_lung",
    "soft tissues": "soft_tissue",
}
# "catheter line" -> None on purpose: a device name must not become a location.
ANATOMY_ALIASES = {k: v for k, v in ANATOMY_ALIASES.items() if v is not None}

# Midline compartments whose ANATOMY laterality is a DEFAULT, not an exclusion:
# reports name their right and left borders every day ("right mediastinal opacity").
# A stated side is not a contradiction for these. validate.py reads this set.
# Deliberately excluded: heart, thoracic_spine, svc, pulmonary_vasculature.
SIDED_MIDLINE = {
    "mediastinum",
    "upper_mediastinum",
    "lower_mediastinum",
    "anterior_mediastinum",
    "posterior_mediastinum",
    "cardiomediastinal_silhouette",
    "aortic_arch",
    # 2026-09-14: found by comparing v2/v2.1/v3.x A/B output -- 21 of 25
    # ANATOMY entries with implied_side "midline" had no exemption here,
    # so a real border/variant description read as a contradiction. Only
    # entries with an actual corpus example are added; the rest (carina,
    # aorta, esophagus, hiatus, sternum, ...) have no evidence yet and are
    # left alone rather than guessed.
    "trachea",              # "Mild indentation of the left trachea..."
    "heart", "cardiac_silhouette",  # "leads extending into the right heart"
    "spine", "thoracic_spine", "lumbar_spine", "cervical_spine",
    "thoracolumbar_spine", "lower_cervical_spine",  # scoliosis laterality
    "svc", "distal_svc", "mid_svc", "low_svc", "mid_to_distal_svc",
    "cavoatrial_junction",  # "persistent left SVC" is a real variant, not
                             # a promotion bug -- same shape as the aorta
}

# =============================================================================
#  E1 -- laterality is carried by the field alone
# =============================================================================
# v1 promoted lower_lobe + left into left_lower_lobe, duplicating the side in
# both label and field. No promotion happens now; what is left is clinical
# knowledge, not promotion.

# Not a side swap but a different structure: "left middle lobe" means the left
# mid lung field, because the left lung has no middle lobe.
LEFT_HAS_NO: Dict[str, str] = {
    "middle_lobe": "mid_lung_field",
}

# Collective plurals (apex + bilateral -> lung_apices). The side rides on the
# plural, not a prefix, so E1 does not cover it; kept until that is decided.
BILATERAL_COLLECTIVE: Dict[str, str] = {
    "apex": "lung_apices",
    "lung_base": "lung_bases",
    "costophrenic_angle": "costophrenic_angles",
    "hemidiaphragm": "diaphragm",
    "lung": "lungs",
    "hilum": "hila",
    "clavicle": "clavicles",
    "shoulder": "shoulders",
    # Irregular plurals: rule 17 (snake_case, singular) has no morphological
    # cue to leave these alone, so it singularizes them same as any other
    # plural noun -- "bronchi" -> "bronchus", "pleural_sinuses" ->
    # "pleural_sinus" -- and without an entry here the result falls out of
    # ANATOMY entirely (observed: "pleural_sinus" x2 in jsonl/Prompt, an
    # unmatched passthrough that silently drops implied_side/implied_zone).
    "bronchus": "bronchi",
    "pleural_sinus": "pleural_sinuses",
}

# Collective -> singular. A collective means "both", so it cannot carry one side:
# without this, stripping the prefix gives lung -> lungs (bilateral) and the
# stated side contradicts it.
SINGULAR_OF = {v: k for k, v in BILATERAL_COLLECTIVE.items()}

# Side prefixes. normalize.py strips these into the laterality field.
LATERAL_PREFIXES = ("left_", "right_", "bilateral_")


# Laterality words, longest first so "bilateral" is not read as two sides.
LATERALITY_WORDS: List[Tuple[str, str]] = [
    ("bilateral", "bilateral"), ("bilaterally", "bilateral"),
    ("both", "bilateral"), ("biapical", "bilateral"), ("bibasilar", "bilateral"),
    ("midline", "midline"), ("central", "midline"),
    ("left", "left"), ("right", "right"),
    ("lt", "left"), ("rt", "right"),
]

# Zone pairs that name the same place (basilar/lower). Folded to the label's
# value by normalize.py instead of raised as a contradiction. Anything not here stays an error.
ZONE_SYNONYMS: List[Tuple[str, str]] = [
    ("basilar", "lower"),
    ("apical", "upper"),
    ("perihilar", "middle"),
]


# =============================================================================
#  E2 -- a vessel segment is carried by `zone`, not baked into the label
# =============================================================================
# "mid_svc" says the same thing twice over: the structure (SVC) and where along
# it (mid). vocabulary.VESSEL_SEGMENT_ALIASES holds the segment words and warns
# that ZONE_WORDS must not be applied here -- it maps "mid" to the lung
# "middle", and a vessel has no middle lobe. So the split happens on its own
# table and normalize.py reads zones differently for a vessel.


def vessel_segment_split(label: Optional[str]
                         ) -> Optional[Tuple[str, Optional[str]]]:
    """`"mid_svc"` -> `("svc", "mid")`. None when this is not a segmented vessel.

    The base has to resolve to a vessel label ON ITS OWN, which is what keeps
    a structure's own name from being read as a segment: "inferior vena cava"
    would otherwise split into "inferior" + "vena cava", and "vena cava" is
    not a label. Only "superior vena cava" is, via the alias table, and it is
    reached whole.

    A range ("mid to lower SVC") names two segments where the enum holds one.
    The segment is left empty rather than asserting the narrower of the two --
    `anatomy.text` still carries the range verbatim. An uncovered field is a
    gap; a narrowed one is a false statement.
    """
    if not label:
        return None
    parts = [p for p in str(label).split("_") if p]
    for cut in range(1, min(4, len(parts))):
        seg, base_parts = parts[:cut], parts[cut:]
        if not base_parts:
            break
        if not all(t in VESSEL_SEGMENT_ALIASES or t == "to" for t in seg):
            continue
        if all(t == "to" for t in seg):
            continue
        snake = "_".join(base_parts)
        base = snake if snake in ANATOMY else ANATOMY_ALIASES.get(" ".join(base_parts))
        if not base or (ANATOMY.get(base) or (None, None, None))[2] != "vessel":
            continue
        # The base may be a segmented label itself ("mid_to_distal_svc" cuts to
        # "distal_svc"). Strip until nothing is left to strip, or the answer
        # still carries a segment in its name.
        inner = vessel_segment_split(base)
        if inner:
            base = inner[0]
        if "to" in seg:
            return base, None
        return base, VESSEL_SEGMENT_ALIASES[seg[-1]]
    return None


# Vessels a catheter travels, which is what proximal/mid/distal divides. The
# regime is deliberately NOT every label in the "vessel" group:
# pulmonary_vasculature is a tree spread over both lungs and reports divide it
# by lung field ("perihilar", "diffuse"), not by segment. Applying segments
# there would throw away a true value to write a meaningless one.
SEGMENTED_VESSELS = {
    "svc", "cavoatrial_junction",
    "aorta", "thoracic_aorta",
    "brachiocephalic_vein", "internal_jugular_vein", "subclavian_vein",
    "peripheral_vein", "pulmonary_artery",
}


def vessel_segment_in(text: Optional[str]) -> Optional[str]:
    """The segment a surface form names, or None when it names no single one.

    Two ways to name none. A range ("mid to lower SVC", "mid/lower SVC")
    names two, and the enum holds one. And a direction word can belong to the
    structure's own name rather than to a place along it -- the "superior" of
    "superior vena cava" is not the proximal end of anything.
    """
    if not text:
        return None
    ws = _TOKEN_RE.findall(str(text).lower())
    hits = []
    for i, w in enumerate(ws):
        if w not in VESSEL_SEGMENT_ALIASES:
            continue
        if i + 1 < len(ws) and ws[i + 1] == "vena":     # "superior vena cava"
            continue
        hits.append(VESSEL_SEGMENT_ALIASES[w])
    return hits[0] if len(set(hits)) == 1 else None


def zones_compatible(a: Optional[str], b: Optional[str]) -> bool:
    """Do these two zone values describe the same region?"""
    if a == b or a is None or b is None:
        return True
    return (a, b) in ZONE_SYNONYMS or (b, a) in ZONE_SYNONYMS


ZONE_WORDS: List[Tuple[str, str]] = [
    ("upper", "upper"), ("middle", "middle"), ("mid", "middle"),
    ("lower", "lower"), ("apical", "apical"), ("apex", "apical"),
    ("apices", "apical"), ("basilar", "basilar"), ("base", "basilar"),
    ("bases", "basilar"), ("basal", "basilar"),
    ("perihilar", "perihilar"), ("infrahilar", "perihilar"),
    ("hilar", "perihilar"), ("retrocardiac", "retrocardiac"),
    ("diffuse", "diffuse"), ("throughout", "diffuse"),
]

# =============================================================================
#  ENTITY
# =============================================================================
# Surface term -> canonical label. Synonymy only: never changes what was asserted.

ENTITY_ALIASES: Dict[str, str] = {
    "effusion": "pleural_effusion",
    "pleural fluid": "pleural_effusion",
    "fluid": "pleural_effusion",
    "layering effusion": "pleural_effusion",
    "ptx": "pneumothorax",
    "consolidation": "consolidation",
    "airspace opacity": "opacity",
    "airspace disease": "opacity",
    "air space opacity": "opacity",
    "opacification": "opacity",
    "density": "opacity",
    "infiltrate": "opacity",
    "atelectasis": "atelectasis",
    "collapse": "atelectasis",
    "volume loss": "atelectasis",
    "edema": "pulmonary_edema",
    "vascular congestion": "pulmonary_vascular_congestion",
    "pulmonary vascular congestion": "pulmonary_vascular_congestion",
    "congestion": "pulmonary_vascular_congestion",
    "chf": "pulmonary_edema",
    "infection": "pulmonary_infection",
    "pneumonia": "pneumonia",
    "cardiomegaly": "cardiomegaly",
    "enlarged cardiac silhouette": "cardiomegaly",
    "enlarged heart": "cardiomegaly",
    "nodule": "pulmonary_nodule",
    "mass": "mass",
    "fracture": "fracture",
    "rib fracture": "rib_fracture",
    "et tube": "endotracheal_tube",
    "endotracheal tube": "endotracheal_tube",
    "ett": "endotracheal_tube",
    "ng tube": "nasogastric_tube",
    "nasogastric tube": "nasogastric_tube",
    "og tube": "orogastric_tube",
    "enteric tube": "enteric_tube",
    "feeding tube": "enteric_tube",
    "chest tube": "chest_tube",
    "pigtail catheter": "pigtail_catheter",
    "picc": "picc_line",
    "picc line": "picc_line",
    "central line": "central_venous_catheter",
    "central venous catheter": "central_venous_catheter",
    "cvc": "central_venous_catheter",
    "port": "port_catheter",
    "pacemaker": "pacemaker",
    "aicd": "implantable_cardioverter_defibrillator",
    "icd": "implantable_cardioverter_defibrillator",
    "sternotomy wires": "sternotomy_wires",
    "cabg": "coronary_artery_bypass_graft",
    "lobectomy": "lobectomy",
    "clear lungs": "lungs",
    "lungs are clear": "lungs",
    "normal": "normal_appearance",
    "within normal limits": "normal_appearance",
    "unremarkable": "normal_appearance",
    # -- spelling duplicates confirmed by both P2 and 1-D (same RadLex RID).
    #    No clinical judgement involved.
    "opacities": "opacity",
    "consolidations": "consolidation",
    "cardiomediastinal silhouettes": "cardiomediastinal_silhouette",
    "cardiac size": "heart_size",
    "heart silhouette": "cardiac_silhouette",
    "low lung volume": "low_lung_volumes",
    "osseous abnormality": "osseous_abnormalities",
    "focal consolidations": "focal_consolidation",
    "degenerative change": "degenerative_changes",
    "central venous catheters": "central_venous_catheter",
    "mediastinal contour": "mediastinal_contours",
    # Do not alias a generic word like "contour": normalize_entity falls back to
    # entity.text, and that path overwrites a more specific label.
    "pulmonary nodules": "pulmonary_nodule",
    "masses": "mass",
    "chest tubes": "chest_tube",
    "surgical clip": "surgical_clips",
    "adenopathy": "lymphadenopathy",
    "scar": "scarring",
    "surgical drain": "drain",
    "leads": "lead",
}

# Entities that are an interpretation, not something seen. rule 6: if one of
# these comes back typed "finding", the type is wrong, not the label.
# =============================================================================
#  E3 -- normality is a descriptor axis, not part of the label
# =============================================================================
# "normal_heart_size" bakes concept and verdict into one label; 99.95% of them
# already carried the normality descriptor too, so stripping is pure de-duplication.
# ORDER MATTERS: longer prefixes first, or "normal_appearing_x" becomes "appearing_x".
# Looks like a prefix but is not: stripping "normal_appearance" leaves the
# meaningless "appearance". Used when the utterance names no structure at all.
NORMALITY_PREFIX_EXCEPTIONS = {"normal_appearance", "normal_variant"}

# Labels a modifier lift must not touch: the modifier is not a qualifier of the
# base, it is part of what the term names. Stripping it leaves a different
# concept, not a cleaner one.
MODIFIER_LIFT_EXCEPTIONS = {
    "free_air",            # not "air" that happens to be free
    "small_bowel",         # an organ, not a small bowel
    "great_vessels",
    "soft_tissue",
    "soft_tissues",
    "low_lung_volumes",    # the finding IS the volume being low; E6 territory
    "low_lung_volume",
    # Stripping leaves an adjective, not a concept: "well_expanded" -> "expanded".
    "well_expanded",
    "well_aerated",
    "well_positioned",
}

NORMALITY_PREFIXES: List[Tuple[str, str]] = [
    ("unremarkable_", "normal"),
    ("normal_appearing_", "normal"),
    ("grossly_normal_", "normal"),
    ("grossly_unremarkable_", "normal"),
    ("normal_", "normal"),
    ("clear_", "clear"),
]


DISEASE_LABELS = {
    "pneumonia", "pulmonary_edema", "pulmonary_infection", "chf",
    "aspiration", "malignancy", "metastasis", "tuberculosis", "empyema",
    "ards", "copd", "emphysema", "fibrosis", "sarcoidosis",
}

DEVICE_LABELS = {
    "endotracheal_tube", "nasogastric_tube", "orogastric_tube", "enteric_tube",
    "chest_tube", "pigtail_catheter", "picc_line", "central_venous_catheter",
    "port_catheter", "pacemaker", "implantable_cardioverter_defibrillator",
    "sternotomy_wires", "swan_ganz_catheter", "tracheostomy_tube",
    "mediastinal_drain", "surgical_clips",
}

# =============================================================================
#  DESCRIPTORS  -- rule 8 and rule 9
# =============================================================================
# word -> (type, value). This table IS rule 9: small is size, mild is severity.

DESCRIPTOR_LEXICON: Dict[str, Tuple[str, str]] = {
    # -- 2026-09-15 batch 1 ---------------------------------------------------
    # From the rebuilt lexicon's grade C: frequent in the corpus, absent from
    # RadLex. Coverage was 1.52% of distinct descriptor strings, and at that
    # coverage metric 1-E cannot see anything -- a conflict is only countable
    # against a word the table knows, so "0 conflicts" meant "no measurement".
    #
    # ONLY words whose axis is decidable WITHOUT looking at the data are here.
    # The corpus's own majority vote was used as confirmation, never as the
    # reason: a table built by majority vote is a mirror of the data and can
    # never disagree with it, which is the same defect that makes 1-A's
    # coverage gameable by identity rows.
    #
    # Deliberately left out, and why:
    #   "dense", "throughout", "grossly", "vague", "overlying"  -- the corpus
    #     itself splits them across two axes. Registering the majority would
    #     launder a live ambiguity into a settled table entry; they stay in
    #     1-E's out-of-vocabulary split list where they belong.
    #   "prior", "previously noted", "previous"  -- chronicity or comparison is
    #     rule 14's contested boundary. That is a decision, not a lookup.
    #   "mildly enlarged", "moderate size"  -- compounds that weld severity to
    #     size, which rule 9 keeps apart on purpose. Registering them would
    #     endorse the welding.
    #   "stable position", "unchanged position"  -- a comparison welded into a
    #     device position.

    # size
    "small amount": ("size", "small"), "very small": ("size", "small"),
    "small-to-moderate": ("size", "small_to_moderate"),
    # severity
    "slightly": ("severity", "mild"), "minor": ("severity", "mild"),
    "faint": ("severity", "subtle"), "minimally": ("severity", "minimal"),
    "somewhat": ("severity", "mild"), "frank": ("severity", "overt"),
    "mild to moderate": ("severity", "mild_to_moderate"),
    "mild-to-moderate": ("severity", "mild_to_moderate"),
    "appreciable": ("severity", "significant"),
    # number
    "one": ("number", "1"), "two": ("number", "2"),
    "three": ("number", "3"), "second": ("number", "2"),
    "numerous": ("number", "innumerable"),
    # extent
    "multilevel": ("extent", "widespread"),
    "subsegmental": ("extent", "partial"),
    "near complete": ("extent", "near_complete"),
    # morphology
    "rounded": ("morphology", "round"), "round": ("morphology", "round"),
    "ovoid": ("morphology", "round"),
    "coarse": ("morphology", "coarse"),
    "indistinct": ("morphology", "ill_defined"),
    "unfolded": ("morphology", "ectatic"),
    "s-shaped": ("morphology", "s_shaped"),
    "curvilinear": ("morphology", "linear"),
    "band-like": ("morphology", "plate_like"),
    "sclerotic": ("morphology", "sclerotic"),
    "calcific": ("morphology", "calcified"),
    # distribution
    "diffusely": ("distribution", "diffuse"),
    "generalized": ("distribution", "diffuse"),
    # 2026-09-15 감사: 아래 낱말들이 표에 없어서 호출마다 타입이 갈렸고,
    # 라벨된 오탐 9건의 원인이었다. 값은 새로 정하지 않고 **표가 이미 내린
    # 결정에 맞춘다** -- `prominent` 가 아래에서 severity 이므로 그 동류도
    # severity 다. 표와 다른 값을 여기에 적으면 뒤쪽 항목이 이겨서 조용히
    # 무시되고, 고친 사람은 왜 안 먹히는지 알 수 없게 된다.
    "accentuated": ("severity", "prominent"),
    "conspicuous": ("severity", "prominent"),
    "globular": ("morphology", "globular"),
    # `dense` 는 일부러 넣지 않았다: 밀도는 크기도 심각도도 모양도 아니라서
    # 어디에 넣어도 틀린다. density 축 신설 여부는 사람이 정할 문제이고
    # docs/DEFECTS_FINAL_*.md 1-D 에 결정 사항으로 올려 두었다.

    # normality
    "normal in size": ("normality", "normal"),
    "normal size": ("normality", "normal"),
    "upper limits of normal": ("normality", "upper_limit_of_normal"),
    "at the upper limits of normal": ("normality", "upper_limit_of_normal"),
    "within normal limits for size": ("normality", "normal"),
    "within normal size limits": ("normality", "normal"),
    "top normal": ("normality", "upper_limit_of_normal"),
    "well-expanded": ("normality", "well_expanded"),
    "well-aerated": ("normality", "well_aerated"),
    "normally expanded": ("normality", "well_expanded"),
    "grossly clear": ("normality", "clear"),
    # device_position
    "in situ": ("device_position", "in_place"),
    "in position": ("device_position", "in_place"),
    "appropriate position": ("device_position", "appropriate"),
    "satisfactory position": ("device_position", "appropriate"),
    "good position": ("device_position", "appropriate"),
    "appropriately located": ("device_position", "appropriate"),
    "aligned": ("device_position", "appropriate"),
    # -- end batch 1 ----------------------------------------------------------

    # size
    "tiny": ("size", "tiny"), "small": ("size", "small"),
    "moderate-sized": ("size", "moderate"), "medium": ("size", "moderate"),
    "large": ("size", "large"), "massive": ("size", "large"),
    "enlarged": ("size", "enlarged"), "enlargement": ("size", "enlarged"),
    "tiny-to-small": ("size", "tiny"),
    # severity
    "minimal": ("severity", "minimal"), "mild": ("severity", "mild"),
    "mildly": ("severity", "mild"), "slight": ("severity", "minimal"),
    "trace": ("severity", "trace"), "moderate": ("severity", "moderate"),
    "moderately": ("severity", "moderate"), "severe": ("severity", "severe"),
    "marked": ("severity", "severe"), "markedly": ("severity", "severe"),
    "extensive": ("severity", "severe"),
    # extent
    "partial": ("extent", "partial"), "complete": ("extent", "complete"),
    "near-complete": ("extent", "near_complete"),
    "focal": ("extent", "focal"), "widespread": ("extent", "widespread"),
    "small-volume": ("extent", "small_volume"),
    # distribution
    "multifocal": ("distribution", "multifocal"),
    "diffuse": ("distribution", "diffuse"),
    "patchy": ("distribution", "patchy"),
    "scattered": ("distribution", "scattered"),
    "streaky": ("distribution", "streaky"),
    "confluent": ("distribution", "confluent"),
    "bibasilar": ("distribution", "bibasilar"),
    "peripheral": ("distribution", "peripheral"),
    "dependent": ("distribution", "dependent"),
    # number
    "single": ("number", "1"), "solitary": ("number", "1"),
    "multiple": ("number", "multiple"), "several": ("number", "multiple"),
    "few": ("number", "few"), "innumerable": ("number", "innumerable"),
    # morphology
    "linear": ("morphology", "linear"), "nodular": ("morphology", "nodular"),
    "reticular": ("morphology", "reticular"),
    "plate-like": ("morphology", "plate_like"),
    "platelike": ("morphology", "plate_like"),
    "wedge-shaped": ("morphology", "wedge_shaped"),
    "irregular": ("morphology", "irregular"),
    "loculated": ("morphology", "loculated"),
    "layering": ("morphology", "layering"),
    "hazy": ("morphology", "hazy"), "ground-glass": ("morphology", "ground_glass"),
    # chronicity  -- rule 13
    "chronic": ("chronicity", "chronic"), "acute": ("chronicity", "acute"),
    "subacute": ("chronicity", "subacute"),
    "known": ("chronicity", "known"), "old": ("chronicity", "old"),
    "longstanding": ("chronicity", "chronic"),
    "long-standing": ("chronicity", "chronic"),
    "remote": ("chronicity", "old"), "healed": ("chronicity", "old"),
    # normality  -- rule 14
    "normal": ("normality", "normal"), "clear": ("normality", "clear"),
    "unremarkable": ("normality", "normal"),
    "within normal limits": ("normality", "normal"),
    "grossly normal": ("normality", "normal"),
    "intact": ("normality", "normal"),
    "preserved": ("normality", "normal"),
    # device position  -- rule 7 / Section 6 C
    "in place": ("device_position", "in_place"),
    "well-positioned": ("device_position", "appropriate"),
    "appropriately positioned": ("device_position", "appropriate"),
    "malpositioned": ("device_position", "malpositioned"),
    "kinked": ("device_position", "kinked"),
    "coiled": ("device_position", "coiled"),
    "retracted": ("device_position", "retracted"),
    "advanced": ("device_position", "advanced"),
    # -- added from the first 30 rows of validate.csv
    "low": ("size", "low"), "high": ("size", "high"),
    "prominent": ("severity", "prominent"),
    "significant": ("severity", "significant"),
    "subtle": ("severity", "subtle"),
    "moderate to severe": ("severity", "moderate_to_severe"),
    "moderate-to-large": ("size", "moderate_to_large"),
    "moderate to large": ("size", "moderate_to_large"),
    "small to moderate": ("size", "small_to_moderate"),
    "partially": ("extent", "partial"),
    "residual": ("extent", "residual"),
    "calcified": ("morphology", "calcified"),
    "heterogeneous": ("morphology", "heterogeneous"),
    "homogeneous": ("morphology", "homogeneous"),
    "hyperdense": ("morphology", "hyperdense"),
    "ill-defined": ("morphology", "ill_defined"),
    "ill defined": ("morphology", "ill_defined"),
    "well-defined": ("morphology", "well_defined"),
    "ectatic": ("morphology", "ectatic"),
    "tortuous": ("morphology", "tortuous"),
    "flattened": ("morphology", "flattened"),
    "levoconvex": ("morphology", "levoconvex"),
    "dextroconvex": ("morphology", "dextroconvex"),
    "elevated": ("morphology", "elevated"),
    "well expanded": ("normality", "well_expanded"),
    "well inflated": ("normality", "well_inflated"),
    "well aerated": ("normality", "well_aerated"),
    "upper limit of normal": ("normality", "upper_limit_of_normal"),
    "not fully visualized": ("other", "not_fully_visualized"),
    "partially visualized": ("other", "partially_visualized"),
    "partially imaged": ("other", "partially_imaged"),
    "right greater than left": ("distribution", "right_greater_than_left"),
    "left greater than right": ("distribution", "left_greater_than_right"),
    "persistent": ("chronicity", "persistent"),
    "well": ("normality", "well"),
    "midline": ("normality", "midline"),
    "denser": ("severity", "denser"),
    "median": ("morphology", "median"),
    "distorting": ("other", "distorted"),
    "definite": ("other", "definite"),
    "symmetrically": ("distribution", "symmetric"),
    "symmetric": ("distribution", "symmetric"),
    "asymmetric": ("distribution", "asymmetric"),
    "overt": ("severity", "overt"),
    "slightly decreased": ("severity", "slightly_decreased"),
    "at least moderately": ("severity", "moderate"),
    "larger on the left": ("distribution", "left_greater_than_right"),
    "larger on the right": ("distribution", "right_greater_than_left"),
    # -- from rows 30-59
    "worse": ("severity", "worsened"), "more pronounced": ("severity", "worse"),
    "relatively prominent": ("severity", "prominent"),
    "discrete": ("morphology", "discrete"),
    "honeycomb": ("morphology", "honeycomb"),
    "displaced": ("morphology", "displaced"),
    "non-displaced": ("morphology", "non_displaced"),
    "nondisplaced": ("morphology", "non_displaced"),
    "deformity": ("morphology", "deformity"),
    "nonspecific": ("morphology", "nonspecific"),
    "local": ("distribution", "focal"),
    "some": ("extent", "some"),
    "area": ("extent", "area"),
    "early": ("chronicity", "early"), "recent": ("chronicity", "recent"),
    "chronic appearing": ("chronicity", "chronic"),
    "apparent": ("other", "apparent"),
    "suspicious": ("other", "suspicious"),
    "grossly unremarkable": ("normality", "normal"),
    "fully expanded": ("normality", "fully_expanded"),
    "at the upper limit of normal": ("normality", "upper_limit_of_normal"),
    "upper limits of normal size": ("normality", "upper_limit_of_normal"),
    "not fully evaluated": ("other", "not_fully_evaluated"),
    "limited assessment": ("other", "limited_assessment"),
    "standard position": ("device_position", "standard"),
}
# device_position phrases are compositional and deliberately absent: no finite list.

# Words that are a comparison wherever they appear; normalize.py moves them out
# of descriptors (the mirror of CHRONICITY_NOT_COMPARISON).
COMPARISON_NOT_DESCRIPTOR = {
    "stable", "unchanged", "new", "improved", "worsened", "increased",
    "decreased", "resolved", "similar", "larger", "smaller",
    "no interval change", "unchanged in position",
}

# rule 13 again, from the other side: these must never end up on comparison.
# "persistent" is NOT here -- see COMPARISON_CUES. It is a change descriptor
# in this domain, not a duration one.
CHRONICITY_NOT_COMPARISON = {"chronic", "known", "old", "longstanding",
                             "long-standing", "remote", "healed"}

# A measurement, e.g. "3.5 cm", "2 mm". Recognized as a shape, not a word.
MEASUREMENT_UNITS = ("mm", "cm", "millimeter", "millimeters", "centimeter",
                     "centimeters")

# =============================================================================
#  CUES  -- rule 10 and rule 12
# =============================================================================

# rule 10 과 한 글자도 어긋나면 안 된다 -- 표와 프롬프트가 다투면 표가 이기고,
# 프롬프트를 고친 사람은 왜 안 먹히는지 알 수 없게 된다.
# "appears"/"appear"/"seems"/"consistent with"/"compatible with" 는 헤지가
# 아니다. 라벨된 감사에서 10건이 이 오해에서 나왔다.
NOT_HEDGES = frozenset({"appears", "appear", "seems", "seem", "is seen",
                        "seen", "noted", "is noted", "consistent with",
                        "compatible with", "demonstrates", "shows"})

NEGATION_CUES = ["no", "not", "without", "no evidence of", "not identified",
                 "not seen", "free of", "negative for", "absence of",
                 "no definite", "no significant", "no gross", "resolved",
                 "cleared", "ruled out", "no longer",
                 # 2026-09-17: 같은 낱말의 다른 꼴이 빠져 있었다. 이 표를
                 # 읽는 곳은 validate.py 와 Verify/m12 뿐이고 둘 다 단어
                 # 경계 정규식으로 맞추므로, "resolved" 가 있어도
                 # "resolution" 은 걸리지 않았다. rule 12 가 "resolved ->
                 # resolved and assertion=absent" 를 지시하고 모델이 그대로
                 # 따랐는데 검사기만 그 낱말을 몰라 결함으로 셌다.
                 # 판단이 아니라 형태론이므로 사람 검토 없이 넣는다.
                 "resolution",            # <- "resolved"
                 "free from",             # <- "free of"
                 "no longer seen", "no longer present"]  # <- "no longer"

UNCERTAINTY_CUES = ["possible", "possibly", "probable", "probably", "likely",
                    "may represent", "may reflect", "suggesting",
                    "suggestive of", "suspicious for", "concerning for",
                    "questionable", "cannot exclude", "cannot be excluded",
                    "versus", "or",
                    "differential", "equivocal", "indeterminate",
                    "worrisome for", "could represent",
                    # 2026-09-17: 위와 같은 형태론 누락. 어느 것도 새로운
                    # 헤지가 아니라 이미 인정된 낱말의 다른 꼴이다.
                    "suggests", "suggest", "suggestion of",   # <- "suggesting"
                    "may suggest", "may indicate",            # <- "may represent"
                    "may relate to", "may be related to",     # <- "may reflect"
                    "not excluded", "cannot be fully excluded",  # <- "cannot be excluded"
                    "raising the possibility of",             # <- "possible"
                    "potentially indicating", "could",        # <- "could represent"
                    "concern for",                            # <- "concerning for"
                    # 2026-09-15 감사로 뺀 것: "consistent with",
                    # "compatible with". 판독문에서 이 둘은 소견과 진단을
                    # 잇는 단정 표현이지 망설임이 아니다 -- RadGraph ·
                    # CheXpert · ConText 계열이 모두 단정으로 다룬다. 헤지로
                    # 읽으면 평범한 소견이 uncertain 이 되어 이 축이 정보를
                    # 싣지 못한다. 불확실성은 별도의 낱말이 말한다.
                    # ("appears"/"seems" 는 애초에 목록에 없었다. 아래 주석
                    #  참조 -- 그 판단은 이번 감사가 확인해 주었다.)
                    # "appearance of an elevated hemidiaphragm" asserts the
                    # look, not the fact. NOT "appear"/"appears": in this
                    # corpus those hedge about half the time ("appears
                    # narrowed") and are ordinary phrasing the other half
                    # ("appear clear"), so a row for them would be a check
                    # that is wrong every second time it fires.
                    "appearance of"]

# =============================================================================
#  SIDE_ONLY_SPANS  -- E5
# =============================================================================
# `anatomy.text` is supposed to hold the words that NAME the structure. These
# do not name one: they are directions. "Small left pleural effusion" with
# `anatomy.text = "left"` records the side twice -- once here and once in
# `laterality` -- and names the pleura nowhere, even though `label` says
# pleura because the effusion entails it.
#
# validate.py warns on these; normalize.py repairs them (see
# lift_side_only_span). Both read this one table so they cannot disagree
# about what counts as a direction.
SIDE_ONLY_SPANS = {"left", "right", "bilateral", "bilaterally", "midline",
                   "left-sided", "right-sided", "left sided", "right sided",
                   "left side", "right side", "both", "both sides"}

# NOT side-only, and the distinction is the whole point of the table:
# "bibasilar" (17,740 in train) and "biapical" (1,704) DO name a place -- the
# lung bases, the apices -- they merely name it with the side folded in, and
# `lung_bases` is the right label for them. "central" is a zone, not a side.
# Lifting those would delete a real structure mention, which is the opposite
# of what E5 is for.

# Labels that are themselves a direction rather than a structure. An entry
# whose LABEL is one of these names no place at all, so there is nothing for
# E5 to lift -- the structure was never extracted and no table can invent it.
# These are left for the prompt, and counted separately.
SIDE_ONLY_LABELS = {"left", "right", "bilateral", "midline", "both",
                    "left_sided", "right_sided", "left_side", "right_side",
                    "sided", "side", "sides", "bilaterally",
                    "contralateral", "ipsilateral"}

# rule 12, as a lookup: cue -> comparison label.
COMPARISON_CUES: Dict[str, str] = {
    "new": "new", "newly": "new", "interval development": "new",
    "developed": "new", "not previously seen": "new",
    "unchanged": "stable", "stable": "stable", "remains": "stable",
    "persistent": "stable", "persists": "stable", "no interval change": "stable",
    "similar": "stable", "again seen": "stable",
    # 2026-09-15: "persistent" was briefly removed from this table on the
    # reading that it states duration rather than a comparison. A SEPARATE
    # model pass, cross-checking the audit that removed it (not a human
    # reader), says that reading is wrong for chest radiography, where
    # "persistent" is a change descriptor -- it asserts continuation with
    # respect to the prior study, which is exactly comparison=stable
    # (17/17 cross-checked rows judged the removal a false positive).
    # Cross-model agreement, not clinical ground truth; still pending a
    # human review before this is treated as final.
    # The real defect is the OTHER direction, and it is duplication: 17
    # propositions carry "persistent" in comparison.cue AND as a chronicity
    # descriptor at once. One token, two homes. GPT/precheck.py's
    # `chronicity_comparison_duplicated` counts those; nothing here changes.
    "improved": "improved", "improvement": "improved",
    "decreased": "improved", "decreasing": "improved", "smaller": "improved",
    "less": "improved", "reduced": "improved", "clearing": "improved",
    "worsened": "worsened", "worsening": "worsened",
    "increased": "worsened", "increasing": "worsened", "larger": "worsened",
    "progression": "worsened", "progressed": "worsened",
    "resolved": "resolved", "resolution": "resolved",
    "no longer seen": "resolved", "no longer present": "resolved",
    "interval change": "unclear", "changed": "unclear",
    # Phrases COMPARISON_NOT_DESCRIPTOR names but this table had no row for,
    # so the duplicate-drop in normalize.py could not recognize them.
    # 2026-09-15: 아래 셋은 표에 없어서 비교로도 서술자로도 가지 못하고
    # 사라지곤 했다. 등재하되, 같은 스팬이 device_position 서술자에도
    # 들어가면 그건 중복이고 GPT/precheck.py 의
    # `chronicity_comparison_duplicated` 와 같은 종류의 결함이다.
    "stable position": "stable", "remains in place": "stable",
    "in stable position": "stable", "similar position": "stable",
    "unchanged in position": "stable", "unchanged in appearance": "stable",
    "no interval change": "stable", "stable in appearance": "stable",
}

__all__ = [
    "SECTIONS", "SECTION_ALIASES", "SECTION_FALLBACK", "NORMALITY_PREFIXES",
    "NORMALITY_PREFIX_EXCEPTIONS",
    "ANATOMY", "ANATOMY_ALIASES", "LEFT_HAS_NO", "BILATERAL_COLLECTIVE", "SINGULAR_OF",
    "LATERAL_PREFIXES",
    "LATERALITY_WORDS", "ZONE_WORDS",
    "ENTITY_ALIASES", "DISEASE_LABELS", "DEVICE_LABELS",
    "DESCRIPTOR_LEXICON", "CHRONICITY_NOT_COMPARISON",
    "COMPARISON_NOT_DESCRIPTOR", "ZONE_SYNONYMS", "zones_compatible",
    "vessel_segment_split", "vessel_segment_in", "VESSEL_SEGMENT_ALIASES",
    "SEGMENTED_VESSELS",
    "MEASUREMENT_UNITS",
    "NEGATION_CUES", "UNCERTAINTY_CUES", "COMPARISON_CUES",
    "SIDE_ONLY_SPANS", "SIDE_ONLY_LABELS",
]
