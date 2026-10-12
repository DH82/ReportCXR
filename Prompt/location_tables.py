"""
Appendix A.2.1-A.2.2 -- location keyword rules.

NOT sent to the API. These tables run after prompt 2 has answered:
they turn free-text localizing expressions into positive / negative /
unlabeled keyword labels.

maplez_struct.py imports from here; nothing in this package imports back.
"""

from typing import Dict, List

# =============================================================================
#  APPENDIX A.2.2 -- location keywords per abnormality
# =============================================================================

THORAX = ["apical", "middle", "right", "left", "upper", "lower", "base",
           "lateral", "perihilar", "retrocardiac"]

LOCATION_KEYWORDS: Dict[str, List[str]] = {
    "Cardiomegaly": ["right", "left", "upper", "lower", "base", "ventricle",
                     "atrium"],
    "Enlarged cardiomediastinum": ["right", "left", "upper", "lower", "base",
                                   "ventricle", "atrium"],
    "Lung opacity": list(THORAX),
    "Edema": list(THORAX),
    "Consolidation": list(THORAX),
    "Atelectasis": list(THORAX),
    "Pneumonia": list(THORAX),
    "Pneumothorax": list(THORAX),
    "Lung lesion": list(THORAX),
    "Pleural other": list(THORAX),
    "Support devices": list(THORAX),
    "Pleural effusion": THORAX + ["fissure"],
    "Fracture": ["middle", "right", "left", "upper", "lower", "lateral",
                 "posterior", "anterior", "rib", "third", "fourth", "fifth",
                 "sixth", "seventh", "eighth", "ninth", "clavicular", "spine"],
}

RIB_ORDINALS = ["third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth"]

# Words that, when present in a location expression, make the keyword positive.
REPLACEMENT: Dict[str, List[str]] = {
    "left": ["leftward", "left-sided", "left-side", "lingula", "bilateral",
             "bilaterally", "lungs", "biapical", "apices", "apexes",
             "retrocardiac", "bases", "bibasilar", "ventricles", "atriums",
             "clavicles"],
    "right": ["right-sided", "right-side", "rightward", "bilateral",
              "bilaterally", "lungs", "biapical", "apices", "apexes", "bases",
              "bibasilar", "ventricles", "atriums", "clavicles"],
    "lower": ["infrahilar", "lingula", "retrocardiac"],
    "upper": ["suprahilar"],
    "fissure": ["fissural", "fissures"],
    "perihilar": ["central", "medial", "medially"],
    # "costrophenic" is the spelling used in the paper; the correct spelling is
    # kept alongside it so that either form is caught.
    "base": ["costrophenic", "costophrenic", "basilar", "bases", "bibasilar"],
    "apical": ["biapical", "apices", "apexes", "apex", "apically", "apicolateral"],
    "middle": ["mid"],
    "ventricle": ["ventricular", "ventricles"],
    "atrium": ["atriums"],
    "spine": ["vertebrae", "vertebra", "vertebral", "spinal"],
    "clavicular": ["clavicles", "clavicle"],
    "posterior": ["posterolateral"],
    "lateral": ["posterolateral", "apicolateral"],
    "rib": ["ribs"],
    "third": ["3rd", "3"],
    "fourth": ["4th", "4", "four"],
    "fifth": ["5th", "5", "five"],
    "sixth": ["6th", "6", "six"],
    "seventh": ["7th", "7", "seven"],
    "eighth": ["8th", "8", "eight"],
    "ninth": ["9th", "9", "nine"],
}

# Appendix A.2.1: a positive keyword makes these keywords negative, unless the
# keyword is protected by PREVENT_NEGATIVE.
MAKES_NEGATIVE: Dict[str, List[str]] = {
    "apical": ["lower", "base", "retrocardiac", "ventricle", "atrium"],
    "middle": ["apical", "base", "ventricle", "atrium"],
    "right": ["left", "retrocardiac", "atrium", "ventricle"],
    "left": ["right", "atrium"],
    "upper": ["lower", "base", "retrocardiac", "ventricle", "atrium"],
    "lower": ["upper", "apical", "clavicular"],
    "base": ["upper", "apical", "middle"],
    "lateral": ["perihilar", "retrocardiac", "atrium", "spine"],
    "perihilar": ["lateral"],
    "ventricle": ["right", "atrium", "upper", "apical"],
    "atrium": ["ventricle", "upper", "apical", "lateral"],
    "posterior": ["clavicular", "anterior", "spine"],
    "anterior": ["clavicular", "posterior", "spine"],
    "rib": ["clavicular", "spine"],
    "retrocardiac": ["right", "lateral", "upper", "apical"],
    "clavicular": RIB_ORDINALS + ["spine", "rib", "lower"],
    "spine": RIB_ORDINALS + ["clavicular", "rib", "lateral"],
}
for _r in RIB_ORDINALS:
    MAKES_NEGATIVE[_r] = [x for x in RIB_ORDINALS if x != _r] + ["clavicular",
                                                                 "spine"]

# Appendix A.2.1: a positive keyword protects these keywords from becoming
# negative. The paper prints "'base': saylower"; read as "lower".
PREVENT_NEGATIVE: Dict[str, List[str]] = {
    "apical": ["upper"],
    "middle": ["upper", "lower"],
    "upper": ["apical", "middle"],
    "lower": ["base", "retrocardiac", "middle"],
    "base": ["lower", "retrocardiac"],
    "perihilar": ["atrium", "ventricle"],
    "ventricle": ["retrocardiac", "perihilar", "lower", "left"],
    "atrium": ["retrocardiac", "perihilar", "lower"],
    "posterior": ["rib"],
    "anterior": ["rib"],
    "clavicular": ["upper", "apical"],
    "spine": ["perihilar"],
    "retrocardiac": ["left", "lower", "perihilar", "base", "atrium", "ventricle"],
}
for _r in RIB_ORDINALS:
    PREVENT_NEGATIVE[_r] = ["rib"]
