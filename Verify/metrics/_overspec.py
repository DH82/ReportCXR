#!/usr/bin/env python3
"""Shared measurement for P1a / P1b / P1c -- the label doing a field's job.

Three branches, one mistake: information in two places always drifts apart,
and where it has drifted is exactly metric 1-F.

  P1a  side in the label        right_internal_jugular_vein  vs laterality
  P1b  tip position in a descriptor   tip_in_mid_svc  vs anatomy.role=tip_location
  P1c  normality in the label    normal_heart_size  vs descriptor.type=normality

Every one of them has a field in the schema already, so no schema change is
needed to fix them. Decisions E1/E2/E3 came out of this measurement.

The three are separate metrics -- they pass and fail independently, and E1/E3
have landed while E2 has not -- but one pass over the data answers all three,
so the pass lives here and each metric renders its own branch.

FIXED 2026-09-15 -- P1b counted its own target. `VESSEL_SEG` matched any label
containing a segmented vessel name, and `svc` contains `svc`. So the canonical
label E2 is supposed to PRODUCE was counted as a defect, and the branch could
not fall no matter how well E2 went. A label is now a P1b defect only when
`vessel_segment_split` finds a segment glued in front of the vessel -- `mid_svc`
yes, `svc` no. Numbers from before this date are not comparable.
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import collections
import re
from typing import Any, Dict

from core import ONT, VOCAB, propositions, table

SIDE_PREFIX = re.compile(r"^(left|right|bilateral)_")
TIPPY = re.compile(r"^(tip_|.*_position$|in_situ$)")
NORMY = re.compile(r"^(normal_|unremarkable_|clear_|no_)")


def vessel_overspecified(label: str) -> bool:
    """True for `mid_svc`, false for `svc`.

    The question is whether a SEGMENT is welded to the vessel name, not
    whether the string mentions a vessel that happens to have segments.
    """
    split = ONT.vessel_segment_split(label)
    return bool(split and split[1] and split[0] != label)


_CACHE: Dict[tuple, Dict[str, Any]] = {}


def measured(splits) -> Dict[str, Any]:
    key = tuple(splits)
    if key not in _CACHE:
        _CACHE[key] = measure(splits)
    return _CACHE[key]


def measure(splits) -> Dict[str, Any]:
    r = {
        "anat_total": 0, "anat_sided": collections.Counter(),
        "desc_total": 0, "desc_tip": collections.Counter(),
        "anat_vessel": collections.Counter(),
        "ent_total": 0, "ent_normal": collections.Counter(),
        "ent_labels": collections.Counter(),
        "tip_role_used": 0, "device_props": 0,
    }
    for sp in splits:
        for _rec, p in propositions(sp):
            e = p.get("entity") or {}
            if e.get("label"):
                r["ent_total"] += 1
                r["ent_labels"][e["label"]] += 1
                if NORMY.match(e["label"]):
                    r["ent_normal"][e["label"]] += 1
            if e.get("type") == "device":
                r["device_props"] += 1
                if any(a.get("role") == "tip_location"
                       for a in p.get("anatomy") or []):
                    r["tip_role_used"] += 1
            for a in p.get("anatomy") or []:
                if not a.get("label"):
                    continue
                r["anat_total"] += 1
                if SIDE_PREFIX.match(a["label"]):
                    r["anat_sided"][a["label"]] += 1
                if vessel_overspecified(a["label"]):
                    r["anat_vessel"][a["label"]] += 1
            for d in p.get("descriptors") or []:
                if not d.get("label"):
                    continue
                r["desc_total"] += 1
                if TIPPY.match(d["label"]):
                    r["desc_tip"][d["label"]] += 1
    return r


def per_split(splits, rows) -> str:
    """The cross-split table each P1 branch opens with.

    `rows` is [(column title, fn(r) -> cell)], so a branch shows only its own
    numbers; the four-branch overview below it gives the corpus context.
    """
    from core import summary
    return summary(
        [[sp] + [fn(measured([sp])) for _t, fn in rows] for sp in splits],
        ["split"] + [t for t, _fn in rows])


def summary_row(r: Dict[str, Any]) -> str:
    """The four-branch overview table, repeated in each P1 file for context."""
    sided = sum(r["anat_sided"].values())
    tip = sum(r["desc_tip"].values())
    ves = sum(r["anat_vessel"].values())
    norm_ = sum(r["ent_normal"].values())
    return table([
        ["P1a side in the label", f"{sided:,}",
         f"{100*sided/max(1,r['anat_total']):.1f}%",
         f"{len(r['anat_sided']):,}", "laterality"],
        ["P1b tip position in a descriptor", f"{tip:,}",
         f"{100*tip/max(1,r['desc_total']):.1f}%", f"{len(r['desc_tip']):,}",
         "anatomy.role=tip_location"],
        ["P1b vessel segment in an anatomy label", f"{ves:,}",
         f"{100*ves/max(1,r['anat_total']):.1f}%", f"{len(r['anat_vessel']):,}",
         "anatomy.role + zone"],
        ["P1c normality in the label", f"{norm_:,}",
         f"{100*norm_/max(1,r['ent_total']):.1f}%", f"{len(r['ent_normal']):,}",
         "descriptor.type=normality"],
    ], ["branch", "mentions", "of that field", "distinct", "belongs in"])
