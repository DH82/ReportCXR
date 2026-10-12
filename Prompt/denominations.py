"""
Appendix A.1.2 -- what the prompts call a finding.

Sent to the API: whatever `denom_for()` picks here lands in the
{label} slot of prompts 1-4. TERM_ALIASES is the bridge from an
open-vocabulary term to one of the thirteen paper labels.

maplez_struct.py imports from here; nothing in this package imports back.
"""

from typing import Dict

# =============================================================================
#  APPENDIX A.1.2 -- abnormality denominations
# =============================================================================
#  Kept as a resource, not as the label space. When an extracted entity is one
#  of these thirteen findings, the paper's denomination (which spells out the
#  synonyms) is what the downstream prompts see; anything else is asked about
#  under its own name.

DENOMINATIONS: Dict[str, str] = {
    "Enlarged cardiomediastinum": (
        "enlarged cardiomediastinum (enlarged heart silhouette or large heart "
        "vascularity or cardiomegaly or abnormal mediastinal contour)"),
    "Cardiomegaly": "cardiomegaly (enlarged cardiac/heart contours)",
    "Atelectasis": "atelectasis (collapse of the lung)",
    "Consolidation": "consolidation or infiltrate",
    "Edema": "lung edema (congestive heart failure)",
    "Fracture": "fracture (bone)",
    "Lung lesion": "lung lesion (mass or nodule)",
    "Pleural effusion": (
        "pleural effusion (pleural fluid) or hydrothorax/hydropneumothorax"),
    "Pneumonia": "pneumonia (infection)",
    "Pneumothorax": "pneumothorax (or pneumomediastinum or hydropneumothorax)",
    "Support devices": (
        "medical equipment or medical support devices (lines or tubes or pacers "
        "or apparatus)"),
    "Lung opacity": (
        "lung opacity (or decreased lucency or lung scarring or bronchial "
        "thickening or infiltration or reticulation or interstitial lung)"),
    "Pleural other": (
        "pleural abnormalities other than pleural effusion (pleural thickening, "
        "fibrosis, fibrothorax, pleural scaring)"),
}

# Denominations used only in the location / severity submodules.
DENOMINATIONS_ATTR: Dict[str, str] = dict(DENOMINATIONS)
DENOMINATIONS_ATTR["Support devices"] = (
    "medical equipment or support device (line or tube or pacer or apparatus or "
    "valve or catheter)")
DENOMINATIONS_ATTR["Pleural other"] = (
    "fibrothorax (not lung fibrosis) or pleural thickening or abnormalities in "
    "the pleura (not pleural effusion)")

# True -> never expand an entity into a paper denomination; always ask about the
# entity under the exact name prompt 0 gave it (the MAPLEZ-Generic ablation).
USE_GENERIC_DENOMINATIONS = False

# Open-vocabulary term -> paper label. Used for two things only: picking the
# denomination above, and picking the location keyword set of Appendix A.2.2.
# An entity that matches nothing here is still annotated, under its own name and
# with the generic thoracic keyword set.
TERM_ALIASES: Dict[str, str] = {
    "cardiomegaly": "Cardiomegaly",
    "enlarged heart": "Cardiomegaly",
    "enlarged cardiac silhouette": "Cardiomegaly",
    "cardiac enlargement": "Cardiomegaly",
    "enlarged cardiomediastinum": "Enlarged cardiomediastinum",
    "mediastinal abnormality": "Enlarged cardiomediastinum",
    "abnormal mediastinal contour": "Enlarged cardiomediastinum",
    "widened mediastinum": "Enlarged cardiomediastinum",
    "atelectasis": "Atelectasis",
    "lung collapse": "Atelectasis",
    "collapse": "Atelectasis",
    "consolidation": "Consolidation",
    "infiltrate": "Consolidation",
    "airspace disease": "Consolidation",
    "airspace opacity": "Consolidation",
    "edema": "Edema",
    "pulmonary edema": "Edema",
    "lung edema": "Edema",
    "vascular congestion": "Edema",
    "pulmonary vascular congestion": "Edema",
    "fracture": "Fracture",
    "rib fracture": "Fracture",
    "clavicle fracture": "Fracture",
    "compression fracture": "Fracture",
    "lung lesion": "Lung lesion",
    "lung mass": "Lung lesion",
    "mass": "Lung lesion",
    "nodule": "Lung lesion",
    "pulmonary nodule": "Lung lesion",
    "pleural effusion": "Pleural effusion",
    "effusion": "Pleural effusion",
    "pleural fluid": "Pleural effusion",
    "hydrothorax": "Pleural effusion",
    "hydropneumothorax": "Pleural effusion",
    "pneumonia": "Pneumonia",
    "infection": "Pneumonia",
    "pneumonitis": "Pneumonia",
    "pneumothorax": "Pneumothorax",
    "pneumomediastinum": "Pneumothorax",
    "lung opacity": "Lung opacity",
    "opacity": "Lung opacity",
    "opacification": "Lung opacity",
    "interstitial opacity": "Lung opacity",
    "reticulation": "Lung opacity",
    "bronchial thickening": "Lung opacity",
    "lung scarring": "Lung opacity",
    "scarring": "Lung opacity",
    "pleural thickening": "Pleural other",
    "pleural scarring": "Pleural other",
    "fibrothorax": "Pleural other",
    "endotracheal tube": "Support devices",
    "tracheostomy tube": "Support devices",
    "nasogastric tube": "Support devices",
    "enteric tube": "Support devices",
    "central venous catheter": "Support devices",
    "central line": "Support devices",
    "picc line": "Support devices",
    "chest tube": "Support devices",
    "pleural drain": "Support devices",
    "pacemaker": "Support devices",
    "defibrillator": "Support devices",
    "sternotomy wire": "Support devices",
    "surgical clip": "Support devices",
    "support device": "Support devices",
}
