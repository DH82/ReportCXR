"""Step 2 lookup tables, v1 (original). None of this is sent to the model.

    SECTIONS            SRRG heading -> broad anatomy + compatible groups (rule 4)
    ANATOMY             canonical label -> (laterality, zone, group)
    ANATOMY_ALIASES     surface text -> canonical anatomy label
    ENTITY_ALIASES      surface term -> canonical entity label
    DESCRIPTOR_LEXICON  word -> (descriptor type, value)   -- rule 9
    NEGATION/UNCERTAINTY/COMPARISON_CUES                   -- rules 10, 12

The tables actually used by normalize.py are Prompt2/ontology.py.
"""

from typing import Dict, List, Optional, Tuple

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
}

# =============================================================================
#  ANATOMY
# =============================================================================
# canonical label -> (laterality, zone, group). These are what the LABEL entails:
# normalize.py fills unspecified fields from them, validate.py catches contradictions.
# None = the label does not settle it; the model's answer stands.

ANATOMY: Dict[str, Tuple[Optional[str], Optional[str], str]] = {
    # -- lung, whole
    "lungs":                    ("bilateral", None, "lung"),
    "left_lung":                ("left", None, "lung"),
    "right_lung":               ("right", None, "lung"),
    # -- lobes
    "right_upper_lobe":         ("right", "upper", "lung"),
    "right_middle_lobe":        ("right", "middle", "lung"),
    "right_lower_lobe":         ("right", "lower", "lung"),
    "left_upper_lobe":          ("left", "upper", "lung"),
    "left_lower_lobe":          ("left", "lower", "lung"),
    "lingula":                  ("left", None, "lung"),
    # -- zones and regions
    "left_lung_base":           ("left", "basilar", "lung"),
    "right_lung_base":          ("right", "basilar", "lung"),
    "lung_bases":               ("bilateral", "basilar", "lung"),
    "left_apex":                ("left", "apical", "lung"),
    "right_apex":               ("right", "apical", "lung"),
    "lung_apices":              ("bilateral", "apical", "lung"),
    "left_perihilar_region":    ("left", "perihilar", "lung"),
    "right_perihilar_region":   ("right", "perihilar", "lung"),
    "right_infrahilar_region":  ("right", "perihilar", "lung"),
    "left_infrahilar_region":   ("left", "perihilar", "lung"),
    # Retrocardiac is a projection, not a side -- laterality stays None.
    "retrocardiac_region":      (None, "retrocardiac", "lung"),
    # -- airway
    "trachea":                  ("midline", None, "airway"),
    "carina":                   ("midline", None, "airway"),
    "left_main_bronchus":       ("left", None, "airway"),
    "right_main_bronchus":      ("right", None, "airway"),
    "bronchi":                  ("bilateral", None, "airway"),
    # -- pleura
    "pleura":                   (None, None, "pleura"),
    "left_pleural_space":       ("left", None, "pleura"),
    "right_pleural_space":      ("right", None, "pleura"),
    "left_costophrenic_angle":  ("left", "basilar", "pleura"),
    "right_costophrenic_angle": ("right", "basilar", "pleura"),
    "costophrenic_angles":      ("bilateral", "basilar", "pleura"),
    "pleural_fissure":          (None, None, "pleura"),
    # -- heart and vessels
    "heart":                    ("midline", None, "heart"),
    "cardiac_silhouette":       ("midline", None, "heart"),
    "left_ventricle":           ("left", None, "heart"),
    "right_atrium":             ("right", None, "heart"),
    "aorta":                    ("midline", None, "vessel"),
    "thoracic_aorta":           ("midline", None, "vessel"),
    "aortic_arch":              ("midline", None, "vessel"),
    "pulmonary_vasculature":    ("bilateral", None, "vessel"),
    "svc":                      ("midline", None, "vessel"),
    "distal_svc":               ("midline", None, "vessel"),
    "cavoatrial_junction":      ("midline", None, "vessel"),
    "left_subclavian_region":   ("left", None, "vessel"),
    "right_subclavian_region":  ("right", None, "vessel"),
    "left_internal_jugular_vein":  ("left", None, "vessel"),
    "right_internal_jugular_vein": ("right", None, "vessel"),
    # -- mediastinum and hila
    "mediastinum":              ("midline", None, "mediastinum"),
    "upper_mediastinum":        ("midline", "upper", "mediastinum"),
    "hila":                     ("bilateral", "perihilar", "hilum"),
    "left_hilum":               ("left", "perihilar", "hilum"),
    "right_hilum":              ("right", "perihilar", "hilum"),
    # -- bone and chest wall
    "ribs":                     ("bilateral", None, "bone"),
    "left_ribs":                ("left", None, "bone"),
    "right_ribs":               ("right", None, "bone"),
    "clavicles":                ("bilateral", None, "bone"),
    "left_clavicle":            ("left", None, "bone"),
    "right_clavicle":           ("right", None, "bone"),
    "spine":                    ("midline", None, "bone"),
    "thoracic_spine":           ("midline", None, "bone"),
    "sternum":                  ("midline", None, "bone"),
    "left_shoulder":            ("left", None, "bone"),
    "right_shoulder":           ("right", None, "bone"),
    "chest_wall":               (None, None, "chest_wall"),
    "soft_tissues":             (None, None, "chest_wall"),
    # -- diaphragm and abdomen
    "left_hemidiaphragm":       ("left", None, "diaphragm"),
    "right_hemidiaphragm":      ("right", None, "diaphragm"),
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
    "left_lateral_rib":         ("left", None, "bone"),
    "right_lateral_rib":        ("right", None, "bone"),
    "esophagus":                ("midline", None, "mediastinum"),
    "hiatus":                   ("midline", None, "mediastinum"),
    "right_atrium_and_right_ventricle": ("right", None, "heart"),
    "right_ventricle":          ("right", None, "heart"),
    "left_atrium":              ("left", None, "heart"),
    "mid_svc":                  ("midline", None, "vessel"),
    "left_subclavian_vein":     ("left", None, "vessel"),
    "right_subclavian_vein":    ("right", None, "vessel"),
    "right_peripheral_vein":    ("right", None, "vessel"),
    "lung_parenchyma":          ("bilateral", None, "lung"),
    "left_upper_lung_field":    ("left", "upper", "lung"),
    "right_upper_lung_field":   ("right", "upper", "lung"),
    "left_mid_lung_field":      ("left", "middle", "lung"),
    "right_mid_lung_field":     ("right", "middle", "lung"),
    "left_lower_lung_field":    ("left", "lower", "lung"),
    "right_lower_lung_field":   ("right", "lower", "lung"),
    "mid_lung":                 (None, "middle", "lung"),
    "left_apical_pleura":       ("left", "apical", "pleura"),
    "right_apical_pleura":      ("right", "apical", "pleura"),
    "left_subdiaphragmatic_region":  ("left", None, "abdomen"),
    "right_subdiaphragmatic_region": ("right", None, "abdomen"),
    "lung_lobe":                (None, None, "lung"),
    # Own label, not an alias: the reading is probable, and an alias must be certain.
    "upper_atrium":             (None, None, "heart"),
    "cavoatrial_junction_or_right_atrium": (None, None, "heart"),

    # -- added from rows 30-59 of validate.csv
    "left_hemithorax":          ("left", None, "lung"),      # 3
    "right_hemithorax":         ("right", None, "lung"),
    "cervical_spine":           ("midline", None, "bone"),   # 2
    "lower_cervical_spine":     ("midline", None, "bone"),   # 2
    "thoracic_skeleton":        (None, None, "bone"),
    "lateral_chest_wall":       (None, None, "chest_wall"),
    "left_upper_extremity":     ("left", None, "chest_wall"),
    "right_upper_extremity":    ("right", None, "chest_wall"),
    "aortic_valve":             (None, None, "heart"),
    "mitral_valve":             (None, None, "heart"),
    "coronary_sinus":           (None, None, "heart"),
    "left_heart_border":        ("left", None, "heart"),
    "right_heart_border":       ("right", None, "heart"),
    "low_svc":                  ("midline", None, "vessel"),
    "mid_to_distal_svc":        ("midline", None, "vessel"),
    "left_jugular_region":      ("left", None, "vessel"),
    "right_jugular_region":     ("right", None, "vessel"),
    "lung_interstitium":        ("bilateral", None, "lung"),
    "peribronchial_region":     (None, None, "airway"),
    "pleural_sinuses":          ("bilateral", "basilar", "pleura"),
    "subpulmonic_space":        (None, "basilar", "pleura"),
    "abdomen":                  (None, None, "abdomen"),
    "subdiaphragmatic_region":  (None, None, "abdomen"),

    # -- side-less form of every LATERALIZABLE key. laterality is None by design.
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
}

# Surface form -> canonical label. Keys are lowercased, laterality stripped;
# normalize.py re-attaches the side it read from the text.
ANATOMY_ALIASES: Dict[str, str] = {
    "lung": "lungs", "both lungs": "lungs", "bilateral lungs": "lungs",
    "pulmonary": "lungs", "lung fields": "lungs", "lung field": "lungs",
    "upper lobe": "upper_lobe", "middle lobe": "right_middle_lobe",
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
}

LATERALIZABLE: Dict[str, Dict[str, str]] = {
    # THERE IS NO LEFT MIDDLE LOBE -- "left mid lung" is a zone, not a lobe.
    # Without this row the side is stripped and the label comes back as the
    # RIGHT middle lobe, i.e. the opposite side. Side-less "middle lobe" is right.
    "right_middle_lobe":     {"left": "left_mid_lung_field",
                              "right": "right_middle_lobe"},
    # A diaphragm with a side is a hemidiaphragm; both labels already exist.
    "diaphragm":             {"left": "left_hemidiaphragm",
                              "right": "right_hemidiaphragm"},
    "upper_lobe":            {"left": "left_upper_lobe",
                              "right": "right_upper_lobe"},
    "lower_lobe":            {"left": "left_lower_lobe",
                              "right": "right_lower_lobe"},
    "lung_base":             {"left": "left_lung_base",
                              "right": "right_lung_base",
                              "bilateral": "lung_bases"},
    "apex":                  {"left": "left_apex", "right": "right_apex",
                              "bilateral": "lung_apices"},
    "perihilar_region":      {"left": "left_perihilar_region",
                              "right": "right_perihilar_region"},
    "infrahilar_region":     {"left": "left_infrahilar_region",
                              "right": "right_infrahilar_region"},
    "costophrenic_angle":    {"left": "left_costophrenic_angle",
                              "right": "right_costophrenic_angle",
                              "bilateral": "costophrenic_angles"},
    "hemidiaphragm":         {"left": "left_hemidiaphragm",
                              "right": "right_hemidiaphragm",
                              "bilateral": "diaphragm"},
    "subclavian_region":     {"left": "left_subclavian_region",
                              "right": "right_subclavian_region"},
    "internal_jugular_vein": {"left": "left_internal_jugular_vein",
                              "right": "right_internal_jugular_vein"},
    "pleura":                {"left": "left_pleural_space",
                              "right": "right_pleural_space"},
    "lungs":                 {"left": "left_lung", "right": "right_lung"},
    "ribs":                  {"left": "left_ribs", "right": "right_ribs"},
    "clavicles":             {"left": "left_clavicle",
                              "right": "right_clavicle"},
    "hila":                  {"left": "left_hilum", "right": "right_hilum"},
    # -- from the first 30 rows of validate.csv
    "lateral_rib":           {"left": "left_lateral_rib",
                              "right": "right_lateral_rib"},
    "upper_lung_field":      {"left": "left_upper_lung_field",
                              "right": "right_upper_lung_field"},
    "mid_lung_field":        {"left": "left_mid_lung_field",
                              "right": "right_mid_lung_field"},
    "lower_lung_field":      {"left": "left_lower_lung_field",
                              "right": "right_lower_lung_field"},
    "apical_pleura":         {"left": "left_apical_pleura",
                              "right": "right_apical_pleura"},
    "subdiaphragmatic_region": {"left": "left_subdiaphragmatic_region",
                                "right": "right_subdiaphragmatic_region"},
    "subclavian_vein":       {"left": "left_subclavian_vein",
                              "right": "right_subclavian_vein"},
    "peripheral_vein":       {"right": "right_peripheral_vein"},
    # -- from rows 30-59
    "hemithorax":            {"left": "left_hemithorax",
                              "right": "right_hemithorax"},
    "heart_border":          {"left": "left_heart_border",
                              "right": "right_heart_border"},
    "jugular_region":        {"left": "left_jugular_region",
                              "right": "right_jugular_region"},
    "upper_extremity":       {"left": "left_upper_extremity",
                              "right": "right_upper_extremity"},
}

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
    "clear lungs": "clear_lungs",
    "lungs are clear": "clear_lungs",
    "normal": "normal_appearance",
    "within normal limits": "normal_appearance",
    "unremarkable": "normal_appearance",
}

# Entities that are an interpretation, not something seen. rule 6: if one of
# these comes back typed "finding", the type is wrong, not the label.
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
CHRONICITY_NOT_COMPARISON = {"chronic", "known", "old", "longstanding",
                             "long-standing", "remote", "healed"}

# A measurement, e.g. "3.5 cm", "2 mm". Recognized as a shape, not a word.
MEASUREMENT_UNITS = ("mm", "cm", "millimeter", "millimeters", "centimeter",
                     "centimeters")

# =============================================================================
#  CUES  -- rule 10 and rule 12
# =============================================================================

NEGATION_CUES = ["no", "not", "without", "no evidence of", "not identified",
                 "not seen", "free of", "negative for", "absence of",
                 "no definite", "no significant", "no gross", "resolved",
                 "cleared", "ruled out", "no longer"]

UNCERTAINTY_CUES = ["possible", "possibly", "probable", "probably", "likely",
                    "may represent", "may reflect", "suggesting",
                    "suggestive of", "suspicious for", "concerning for",
                    "questionable", "cannot exclude", "cannot be excluded",
                    "consistent with", "compatible with", "versus", "or",
                    "differential", "equivocal", "indeterminate",
                    "worrisome for", "could represent"]

# rule 12, as a lookup: cue -> comparison label.
COMPARISON_CUES: Dict[str, str] = {
    "new": "new", "newly": "new", "interval development": "new",
    "developed": "new", "not previously seen": "new",
    "unchanged": "stable", "stable": "stable", "remains": "stable",
    "persistent": "stable", "persists": "stable", "no interval change": "stable",
    "similar": "stable", "again seen": "stable",
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
    "unchanged in position": "stable", "unchanged in appearance": "stable",
    "no interval change": "stable", "stable in appearance": "stable",
}

__all__ = [
    "SECTIONS", "SECTION_ALIASES",
    "ANATOMY", "ANATOMY_ALIASES", "LATERALIZABLE",
    "LATERALITY_WORDS", "ZONE_WORDS",
    "ENTITY_ALIASES", "DISEASE_LABELS", "DEVICE_LABELS",
    "DESCRIPTOR_LEXICON", "CHRONICITY_NOT_COMPARISON",
    "COMPARISON_NOT_DESCRIPTOR", "ZONE_SYNONYMS", "zones_compatible",
    "MEASUREMENT_UNITS",
    "NEGATION_CUES", "UNCERTAINTY_CUES", "COMPARISON_CUES",
]
