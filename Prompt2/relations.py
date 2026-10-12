"""Concepts and relations RadLex cannot answer.

RadLex 4.3 covers 46,898 concepts but not the whole chest-report vocabulary:
findings it lacks entirely (cardiomegaly), report-language constructs
(*_silhouette, *_contours) and normal states have no concept to hang on.
Anything RadLex CAN answer is deliberately not repeated here.

    CONCEPTS   label -> (type, nearest RadLex concept, note)
    LOCAL      (label A, label B) -> (relation, note), only pairs the RadLex
               hierarchy cannot judge

    relations: same | narrower | broader | distinct | unsure

Verify/metrics/m07_merge.py reads both, and its "needs a local definition"
list is what says to add here next. Notes are data: they are printed in reports.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

RELATIONS = ("same", "narrower", "broader", "distinct", "unsure")

# =============================================================================
#  Local concepts -- not in RadLex 4.3
# =============================================================================
# label -> (type, nearest RadLex concept or "", why RadLex lacks it)
# RadLex is strong on anatomy and imaging observations, thin on finding names
# and normal-state wording.
CONCEPTS: Dict[str, Tuple[str, str, str]] = {
    # -- findings RadLex does not have ---------------------------------------
    "cardiomegaly": ("disease", "RID1385 heart",
                     "enlarged heart; RadLex has none of cardiomegaly, "
                     "cardiac enlargement or enlarged heart"),
    "pleural_thickening": ("finding", "RID1362 pleura", "thickened pleura"),
    "hyperinflation": ("finding", "RID13437 lungs", "over-inflated lungs"),
    "pulmonary_vascular_congestion": ("finding", "RID1243 pulmonary vasculature",
                                      "congested pulmonary vessels"),
    "low_lung_volumes": ("anatomical_state", "RID13437 lungs", "reduced lung volume"),
    "degenerative_changes": ("finding", "", "degenerative change; a catch-all, site unspecified"),
    "osseous_abnormalities": ("finding", "RID2005 bone", "bone abnormality, catch-all"),
    "free_air": ("finding", "", "free air, i.e. intraperitoneal free gas"),
    "interstitial_edema": ("disease", "RID34539 effusion", "interstitial edema"),
    "pulmonary_infection": ("disease", "", "pulmonary infection, catch-all"),

    # -- devices ---------------------------------------------------------------
    "sternotomy_wires": ("device", "", "wires closing a sternotomy"),
    "median_sternotomy": ("postoperative_state", "", "prior median sternotomy"),

    # -- report-language constructs (silhouette) -------------------------------
    "cardiomediastinal_silhouette": ("anatomical_state", "RID35544 silhouette sign",
                                     "the heart plus mediastinal border; RadLex has "
                                     "only silhouette sign, which is a finding"),
    "cardiac_silhouette": ("anatomical_state", "RID1385 heart", "the cardiac border"),
    "mediastinal_silhouette": ("anatomical_state", "RID1384 mediastinum", "the mediastinal border"),
    "cardiomediastinal_contours": ("anatomical_state", "", "another wording for the silhouette above"),
    "mediastinal_contours": ("anatomical_state", "", "as above"),
    "hilar_contours": ("anatomical_state", "RID34566 pulmonary hilum", "the hilar border"),
    "bony_structures": ("anatomical_state", "RID2005 bone", "bony structures, catch-all"),

    # -- reading regions that are real but absent from RadLex --------------------
    "retrocardiac_region": ("anatomy", "RID1385 heart", "the region behind the heart"),
    "subdiaphragmatic_region": ("anatomy", "RID1360 diaphragm", "below the diaphragm"),
    "above_carina": ("anatomy", "RID1247 carina", "above the carina; used for tip position"),
    "cavoatrial_junction": ("anatomy", "RID1010 superior vena cava",
                            "cavoatrial junction; the reference point for a tip"),
    "mid_svc": ("anatomy", "RID1010 superior vena cava",
                "mid segment of the SVC; RadLex does not segment the SVC"),
}


# (A, B) -> (relation, note). Sorted A < B so each pair is written once.
LOCAL: Dict[Tuple[str, str], Tuple[str, str]] = {}


def _add(a: str, b: str, rel: str, why: str) -> None:
    assert rel in RELATIONS, rel
    LOCAL[tuple(sorted((a, b)))] = (rel, why)


# =============================================================================
#  silhouette / contour family -- RadLex has only silhouette sign (RID35544)
# =============================================================================
# Report wording for a border, not an anatomical concept. The wordings cover
# different extents, so they are narrower/broader, not the same.
_add("cardiac_silhouette", "cardiomediastinal_silhouette", "narrower",
     "the cardiac border is part of the cardiomediastinal one")
_add("mediastinal_silhouette", "cardiomediastinal_silhouette", "narrower",
     "the mediastinal border is part of the cardiomediastinal one")
_add("mediastinal_contours", "cardiomediastinal_contours", "narrower",
     "same relation as above")
_add("hilar_contours", "cardiomediastinal_contours", "distinct",
     "the hilar border is not part of the cardiomediastinal one")
_add("cardiac_silhouette", "mediastinal_silhouette", "distinct",
     "heart and mediastinum are different compartments")
# silhouette and contour are two wordings for the same thing.
_add("cardiomediastinal_silhouette", "cardiomediastinal_contours", "same",
     "silhouette and contour are interchangeable in reports")
_add("cardiac_silhouette", "cardiac_contour", "same", "as above")
_add("mediastinal_silhouette", "mediastinal_contours", "same", "as above")

# =============================================================================
#  findings RadLex does not have
# =============================================================================
_add("cardiomegaly", "cardiac_silhouette", "distinct",
     "cardiomegaly is a finding; the cardiac border is what it is read from")
_add("cardiomegaly", "heart_size", "distinct",
     "heart_size is the state; cardiomegaly is the abnormal verdict on it")
_add("cardiomegaly", "enlarged_heart", "same", "two wordings of one finding")
_add("cardiomegaly", "cardiac_enlargement", "same", "two wordings of one finding")

# =============================================================================
#  bone family -- osseous and bony are exact synonyms in reports
# =============================================================================
_add("osseous_abnormalities", "bony_abnormalities", "same", "lexical variant")
_add("osseous_structures", "bony_structures", "same", "lexical variant")
_add("osseous_abnormalities", "osseous_structures", "distinct",
     "an abnormality is not the structure itself")

# =============================================================================
#  vessel segments -- RadLex has only superior vena cava (RID1010)
# =============================================================================
# Segments describing a catheter tip position, not structures. They fold into
# svc + zone once E2 is implemented in normalize.py.
_add("low_svc", "lower_svc", "same", "two spellings of one segment")
_add("mid_svc", "distal_svc", "distinct", "different SVC segments")
_add("upper_svc", "low_svc", "distinct", "different SVC segments")
_add("cavoatrial_junction", "svc", "narrower",
     "the cavoatrial junction is the distal end of the SVC")

# =============================================================================
#  reading regions -- real chest regions absent from RadLex
# =============================================================================
_add("retrocardiac_region", "left_lower_lobe", "distinct",
     "the retrocardiac region overlaps the left lower lobe on film but is a different compartment")
_add("subdiaphragmatic_region", "below_diaphragm", "same", "two spellings of one region")
_add("upper_limit_of_normal", "upper_limits_of_normal", "same", "singular/plural variant")


def relation(a: str, b: str) -> Optional[Tuple[str, str]]:
    """(relation, note), or None when this table does not answer."""
    return LOCAL.get(tuple(sorted((a, b))))


def concept(label: str) -> Optional[Tuple[str, str, str]]:
    """(type, nearest RadLex concept, note), or None."""
    return CONCEPTS.get(label)


def coverage() -> Dict[str, int]:
    c: Dict[str, int] = {}
    for rel, _why in LOCAL.values():
        c[rel] = c.get(rel, 0) + 1
    return c


__all__ = ["CONCEPTS", "LOCAL", "RELATIONS", "concept", "relation",
           "coverage"]
