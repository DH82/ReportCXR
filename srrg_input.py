#!/usr/bin/env python3
"""
The input side: whatever is on disk -> the three fields Section 1 asks for.

    {"utterance_id": "10_pleura_01",
     "utterance": "There is no pleural effusion.",
     "section": "Pleura"}

Three fields, and no fourth. history_section is a column of the SRRG CSV and
this file does not read it, because MD/Ko-SRRG_CXR_5category_parser_simple.md
Section 1 does not have a slot for it and rule 3 forbids a proposition
resting on text that is not in the utterance. Clinical history is what the
referring physician suspected, not what this image shows; letting it reach the
prompt is how "history of pneumonia" becomes a pneumonia proposition.

(ReportCXR/SRRG.py does send it, to a prior-report slot its pipeline has for
interval change. This parser has no such slot: one utterance is one call, and
comparison is whatever THAT utterance states about change -- see rule 12.)

Three sources, because three are what actually get used:

  SRRG CSV     /data3/CXR/SRRG/srrg_findings_csv/{train,validate,test}.csv.
               findings_section is a block of headings and "- " bullets:

                   Lungs and Airways:
                   - Linear opacity in the left lower lung.
                   Pleura:
                   - No pleural effusion.

               One bullet is one utterance, in the order it appears, carrying
               the heading it sits under as its section. Nothing is batched
               and nothing is re-ordered, so utterance #2 of a row is the same
               utterance in every run.
  JSONL        one Section 1 object per line. This is how a re-run over a
               fixed evaluation subset is done -- the ids stay what they were.
  --text       one utterance from the command line, for looking at a single
               sentence without touching a file.

utterance_id is "{row_id}_{section_slug}_{nn}", nn counting within the
section, which is the shape Section 1's own example uses. It is derived, not
stored: the same CSV always produces the same ids, so a parse can be joined
back to its input by id alone.

Sentence splitting is available (--split-sentences) but off. An SRRG bullet is
already one utterance by construction; splitting it changes what the unit of
analysis is, and that is a decision for the caller, not a default.

parse_utterances.py imports load_utterances(); nothing here calls the model.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
from typing import Any, Dict, Iterable, List, Optional

CSV_PATH = "/data3/CXR/SRRG/srrg_findings_csv/validate.csv"
# The only two columns this parser reads. The CSV also carries
# history_section; it is deliberately not read -- see the module docstring.
FINDINGS_COL = "findings_section"
ID_COL = "id"

# "Lungs and Airways:" -- a heading line, nothing else on it.
_HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z ,&/-]{2,47}?)\s*:\s*$")
# "- Linear opacity ..." / "* ..." / "1. ..."
_BULLET_RE = re.compile(r"^(?:[-*•]|\(?\d{1,2}[.)])\s+(.*)$")
# A sentence end that is not an abbreviation or a decimal point.
_SENT_RE = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(])")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def sanitize(text: str) -> str:
    """Report text -> plain ASCII, so a span match is a span match.

    Reports carry typographic quotes, non-breaking spaces and the occasional
    degree sign. rule 3 compares spans against this text character by
    character, so the normalization has to happen once, here, before anything
    is either sent or stored.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = (t.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-")
          .replace(" ", " "))
    t = t.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[ \t]+", " ", t).strip()


# Dropped before an id is built: they carry no information and turn
# "Lungs and Airways" into "lungs_and".
_STOPWORDS = {"and", "the", "of", "or", "a"}


def slug(section: Optional[str]) -> str:
    """"Lungs and Airways" -> "lungs_airways". Two content words, no more:
    "tubes_catheters_and_support_devices" is not an id, it is a paragraph."""
    parts = [w for w in _SLUG_RE.sub("_", (section or "body").lower()).split("_")
             if w and w not in _STOPWORDS]
    return "_".join(parts[:2]) or "body"


def split_bullets(findings_section: str) -> List[Dict[str, Any]]:
    """The findings block -> its bullets, in order, each with its heading.

    A line that is neither a heading nor a bullet is the wrapped continuation
    of the bullet above it and is joined onto it.
    """
    units: List[Dict[str, Any]] = []
    header: Optional[str] = None
    for raw in (findings_section or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _HEADER_RE.match(line)
        if m:
            header = m.group(1).strip()
            continue
        b = _BULLET_RE.match(line)
        if b:
            text = b.group(1).strip()
            if text:
                units.append({"index": len(units) + 1, "section": header,
                              "text": text})
            continue
        if units and units[-1]["section"] == header:
            units[-1]["text"] += " " + line
        else:
            units.append({"index": len(units) + 1, "section": header,
                          "text": line})
    return units


def split_sentences(text: str) -> List[str]:
    """Only used when --split-sentences is passed. See the module docstring."""
    parts = [p.strip() for p in _SENT_RE.split(text or "") if p.strip()]
    return parts or ([text.strip()] if text and text.strip() else [])


def utterances_from_row(row: Dict[str, str], *, split: bool = False
                        ) -> List[Dict[str, Any]]:
    rid = str(row.get(ID_COL) or "?")
    findings = sanitize(row.get(FINDINGS_COL) or "")
    out: List[Dict[str, Any]] = []
    per_section: Dict[str, int] = {}

    for unit in split_bullets(findings):
        texts = split_sentences(unit["text"]) if split else [unit["text"]]
        for text in texts:
            key = slug(unit["section"])
            per_section[key] = per_section.get(key, 0) + 1
            out.append({
                "utterance_id": f"{rid}_{key}_{per_section[key]:02d}",
                "utterance": text,
                "section": unit["section"],
                "row_id": rid,
                "bullet_index": unit["index"],
            })
    return out


# =============================================================================
#  SOURCES
# =============================================================================

def load_csv_rows(path: str) -> List[Dict[str, str]]:
    csv.field_size_limit(10 ** 7)
    with open(path, encoding="utf-8", newline="") as fp:
        rows = list(csv.DictReader(fp))
    if not rows:
        sys.exit(f"{path} has no rows")
    if FINDINGS_COL not in rows[0]:
        sys.exit(f"{path} has no column {FINDINGS_COL!r}; found "
                 f"{list(rows[0].keys())}")
    return rows


def select_rows(rows: List[Dict[str, str]], args: Any) -> List[Dict[str, str]]:
    """--id / --row / --rows / --limit / --all, in that order, no repeats."""
    picked: List[Dict[str, str]] = []
    if getattr(args, "id", None):
        by_id = {r.get(ID_COL): r for r in rows}
        for rid in args.id:
            if rid not in by_id:
                sys.exit(f"id {rid!r} is not in the file")
            picked.append(by_id[rid])
    for n in getattr(args, "row", None) or []:
        if not 0 <= n < len(rows):
            sys.exit(f"--row {n} is out of range (0..{len(rows) - 1})")
        picked.append(rows[n])
    if getattr(args, "rows", None):
        m = re.fullmatch(r"(\d+)-(\d+)", args.rows)
        if not m:
            sys.exit("--rows takes a range like 0-9")
        picked.extend(rows[int(m.group(1)):int(m.group(2)) + 1])
    if getattr(args, "limit", None) is not None:
        picked.extend(rows[:args.limit])
    if getattr(args, "all", False):
        picked = list(rows)
    if not picked:
        picked = [rows[0]]
    seen, unique = set(), []
    for r in picked:
        key = r.get(ID_COL) or id(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """One Section 1 object per line. Ids are taken as given, not rebuilt."""
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as fp:
        for n, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"{path}:{n}: {e}")
            if "utterance" not in obj:
                sys.exit(f"{path}:{n}: no 'utterance' key")
            out.append({
                "utterance_id": obj.get("utterance_id") or f"line{n:04d}",
                "utterance": sanitize(obj["utterance"]),
                "section": obj.get("section"),
                "row_id": obj.get("row_id"),
                "bullet_index": obj.get("bullet_index"),
            })
    return out


def load_utterances(args: Any) -> List[Dict[str, Any]]:
    """Whichever source the flags name -> a flat list of Section 1 objects."""
    if getattr(args, "text", None):
        return [{"utterance_id": getattr(args, "utterance_id", None) or "adhoc_01",
                 "utterance": sanitize(args.text),
                 "section": getattr(args, "section", None),
                 "row_id": None, "bullet_index": 1}]

    if getattr(args, "jsonl", None):
        items = load_jsonl(args.jsonl)
    else:
        rows = load_csv_rows(args.csv)
        picked = select_rows(rows, args)
        print(f"{args.csv}: {len(rows)} row(s) available, {len(picked)} "
              f"selected", file=sys.stderr)
        items = [u for row in picked
                 for u in utterances_from_row(
                     row, split=getattr(args, "split_sentences", False))]

    if getattr(args, "max_utterances", None):
        items = items[:args.max_utterances]
    return items


def dry_run(items: Iterable[Dict[str, Any]]) -> None:
    """What would be sent, and which few-shot examples each one would get."""
    from Prompt import select

    items = list(items)
    for u in items:
        names = select(u["utterance"])
        print(f"  {u['utterance_id']:<28} [{u.get('section') or '-'}]")
        print(f"      {u['utterance']}")
        print(f"      few-shot: {', '.join(names)}")
    print(f"\n{len(items)} utterance(s), one call each. No calls were made.")


__all__ = ["CSV_PATH", "FINDINGS_COL", "ID_COL",
           "sanitize", "slug", "split_bullets", "split_sentences",
           "utterances_from_row", "load_csv_rows", "select_rows", "load_jsonl",
           "load_utterances", "dry_run"]
