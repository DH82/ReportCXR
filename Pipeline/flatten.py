#!/usr/bin/env python3
"""Section 8's last step -- the nested record, flattened into tables.

The nested JSON stays the record of truth (it is what keeps each factor attached
to its entity, rule 1); the tables are a projection for counting, written next
to it rather than instead of it.

    propositions.csv   one row per proposition: the single-valued categories
                       plus the link, the counts and the utterance's triggers
    anatomy.csv        one row per anatomy entry (rule 2 allows several)
    descriptors.csv    one row per descriptor (rule 8 allows several)
    review.csv         one row per utterance that fired a trigger or an error

Join key is (utterance_id, proposition_id), stable across runs because
srrg_input.py derives utterance_id from the CSV rather than counting calls.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Tuple

PROPOSITION_COLS = [
    "utterance_id", "row_id", "section", "proposition_id",
    "entity_text", "entity_label", "entity_type",
    "assertion", "assertion_cue", "comparison", "comparison_cue",
    "derived_from", "n_anatomy", "n_descriptors",
    "triggers", "errors", "warnings", "utterance",
]

ANATOMY_COLS = [
    "utterance_id", "proposition_id", "anatomy_index",
    "text", "label", "laterality", "zone", "role", "source",
]

DESCRIPTOR_COLS = [
    "utterance_id", "proposition_id", "descriptor_index",
    "text", "type", "label",
]

REVIEW_COLS = [
    "utterance_id", "row_id", "section", "utterance",
    "n_propositions", "triggers", "errors", "warnings", "findings",
]


def _join(values: List[str]) -> str:
    return "; ".join(v for v in values if v)


def flatten(records: List[Dict[str, Any]]
            ) -> Tuple[List[List[Any]], List[List[Any]], List[List[Any]]]:
    """The three tables, as rows in the column order above."""
    props: List[List[Any]] = []
    anas: List[List[Any]] = []
    descs: List[List[Any]] = []

    for rec in records:
        uid = rec.get("utterance_id")
        review = rec.get("review") or {}
        triggers = _join(review.get("triggers") or [])
        n_err = review.get("errors", 0)
        n_warn = review.get("warnings", 0)

        for p in rec.get("propositions") or []:
            pid = p.get("id")
            ent = p.get("entity") or {}
            a = p.get("assertion") or {}
            c = p.get("comparison") or {}
            anatomy = p.get("anatomy") or []
            descriptors = p.get("descriptors") or []

            props.append([
                uid, rec.get("row_id"), rec.get("section"), pid,
                ent.get("text"), ent.get("label"), ent.get("type"),
                a.get("label"), a.get("cue"), c.get("label"), c.get("cue"),
                p.get("derived_from"), len(anatomy), len(descriptors),
                triggers, n_err, n_warn, rec.get("utterance"),
            ])
            for i, entry in enumerate(anatomy, 1):
                anas.append([uid, pid, i, entry.get("text"), entry.get("label"),
                             entry.get("laterality"), entry.get("zone"),
                             entry.get("role"), entry.get("source")])
            for i, d in enumerate(descriptors, 1):
                descs.append([uid, pid, i, d.get("text"), d.get("type"),
                              d.get("label")])

    return props, anas, descs


def review_rows(records: List[Dict[str, Any]]) -> List[List[Any]]:
    """The queue: anything a human is asked to look at, and why."""
    out: List[List[Any]] = []
    for rec in records:
        review = rec.get("review") or {}
        triggers = review.get("triggers") or []
        findings = review.get("findings") or []
        if not triggers and not findings:
            continue
        out.append([
            rec.get("utterance_id"), rec.get("row_id"), rec.get("section"),
            rec.get("utterance"), len(rec.get("propositions") or []),
            _join(triggers), review.get("errors", 0), review.get("warnings", 0),
            _join([f"{f['severity']}:{f['code']}"
                   f"{'@' + f['proposition'] if f.get('proposition') else ''}"
                   for f in findings]),
        ])
    return out


def _write(path: str, header: List[str], rows: List[List[Any]]) -> str:
    # utf-8-sig so the sheets open in Excel with the report text intact.
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(header)
        w.writerows(rows)
    return path


def write_tables(records: List[Dict[str, Any]], outdir: str,
                 stamp: str) -> List[str]:
    os.makedirs(outdir, exist_ok=True)
    props, anas, descs = flatten(records)
    return [
        _write(os.path.join(outdir, f"propositions_{stamp}.csv"),
               PROPOSITION_COLS, props),
        _write(os.path.join(outdir, f"anatomy_{stamp}.csv"),
               ANATOMY_COLS, anas),
        _write(os.path.join(outdir, f"descriptors_{stamp}.csv"),
               DESCRIPTOR_COLS, descs),
        _write(os.path.join(outdir, f"review_{stamp}.csv"),
               REVIEW_COLS, review_rows(records)),
    ]


__all__ = ["flatten", "review_rows", "write_tables", "PROPOSITION_COLS",
           "ANATOMY_COLS", "DESCRIPTOR_COLS", "REVIEW_COLS"]
