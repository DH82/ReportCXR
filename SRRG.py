#!/usr/bin/env python3
"""
Drive maplez_struct.py over the SRRG findings CSV, one bullet at a time.

Input columns
    findings_section : SRRG findings block -- anatomical headings, "- " bullets
    history_section  : one or two clinical sentences

Each "- " bullet becomes one input, in the order it appears, carrying the
heading it sits under. The bullet below is input #1, the next one input #2, and
so on; nothing is batched and nothing is re-ordered.

    Lungs and Airways:                    ->  #1  section = "Lungs and Airways"
    - Linear opacity in the left lower            text    = "Linear opacity ..."
      lung suggestive of plate-like
      atelectasis.

    Pleura:                               ->  #2  section = "Pleura"
    - No pleural effusion.                        text    = "No pleural effusion."

history_section goes into the pipeline's prior-report slot, annotated once per
row and shared by every bullet of that row. Clinical history is not an imaging
comparison: prompt 0 answers "none" for a symptom or an indication, so the
history normally contributes no findings and the change axis comes out
"Not comparable" -- unless the bullet itself says "new", which is the one case
the rule lets through. Pass --no-history to skip those calls entirely.

Usage
    python SRRG.py --dry-run              # show what would be sent; no API calls
    python SRRG.py                        # annotate the first row
    python SRRG.py --row 3                # one row by position (0-based)
    python SRRG.py --id mimic-00000001    # one row by id
    python SRRG.py --rows 0-9 --yes       # a range
    python SRRG.py --limit 50 --yes       # the first 50 rows
Results land in ./out_srrg_maplez/ as four files: the full JSON and CSV, and a
slim JSON and CSV holding the judgements (entity, presence, severity,
laterality, location, change) next to the bullet they came from. Every API call
is logged under logs/.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maplez_struct as M  # noqa: E402

# =============================================================================
#  CONFIG
# =============================================================================

CSV_PATH = "/data3/CXR/SRRG/srrg_findings_csv/validate.csv"
FINDINGS_COL = "findings_section"
HISTORY_COL = "history_section"
ID_COL = "id"

OUTPUT_DIR = "./out_srrg_maplez"
LOG_DIR = os.path.join(OUTPUT_DIR, "logs")

# More rows than this need an explicit --yes: every row costs real API calls.
CONFIRM_ABOVE = 20

# Upper bound per bullet (entity + presence + location + severity + change).
CALLS_PER_BULLET = 5

# =============================================================================
#  PARSING findings_section
# =============================================================================

# "Lungs and Airways:" -- a heading line, nothing else on it.
_HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z ,&/-]{2,47}?)\s*:\s*$")
# "- Linear opacity ..." / "* ..." / "1. ..."
_BULLET_RE = re.compile(r"^(?:[-*\u2022]|\(?\d{1,2}[.)])\s+(.*)$")
# Sentence ends, for spotting a bullet that carries more than one finding.
_SENTENCES_RE = re.compile(r"[.!?](?:\s|$)")


def split_bullets(findings_section: str) -> List[Dict[str, Any]]:
    """SRRG findings block -> the bullets, in order, each with its heading.

    A line that is neither a heading nor a bullet is treated as the wrapped
    continuation of the bullet above it, and joined onto it.
    """
    units: List[Dict[str, Any]] = []
    header = "BODY"
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
                units.append({"index": len(units) + 1, "header": header,
                              "text": text})
            continue
        if units and units[-1]["header"] == header:
            units[-1]["text"] += " " + line          # wrapped bullet
        else:
            units.append({"index": len(units) + 1, "header": header,
                          "text": line})
    return units


def render(unit: Dict[str, Any]) -> str:
    """The bullet as it looked in the CSV, for display and logging."""
    return f'{unit["header"]}:\n- {unit["text"]}'


def load_rows(path: str) -> List[Dict[str, str]]:
    csv.field_size_limit(10 ** 7)
    with open(path, encoding="utf-8", newline="") as fp:
        rows = list(csv.DictReader(fp))
    if not rows:
        sys.exit(f"{path} has no rows")
    for col in (FINDINGS_COL, HISTORY_COL):
        if col not in rows[0]:
            sys.exit(f"{path} has no column {col!r}; found "
                     f"{list(rows[0].keys())}")
    return rows


def select_rows(rows: List[Dict[str, str]], args: argparse.Namespace
                ) -> List[Dict[str, str]]:
    picked: List[Dict[str, str]] = []
    if args.id:
        by_id = {r.get(ID_COL): r for r in rows}
        for rid in args.id:
            if rid not in by_id:
                sys.exit(f"id {rid!r} is not in {args.csv}")
            picked.append(by_id[rid])
    for n in args.row or []:
        if not 0 <= n < len(rows):
            sys.exit(f"--row {n} is out of range (0..{len(rows) - 1})")
        picked.append(rows[n])
    if args.rows:
        m = re.fullmatch(r"(\d+)-(\d+)", args.rows)
        if not m:
            sys.exit("--rows takes a range like 0-9")
        a, b = int(m.group(1)), int(m.group(2))
        picked.extend(rows[a:b + 1])
    if args.limit is not None:
        picked.extend(rows[:args.limit])
    if args.all:
        picked = list(rows)
    if not picked:
        picked = [rows[0]]                     # default: the first row
    seen, unique = set(), []
    for r in picked:                           # keep order, drop repeats
        key = r.get(ID_COL) or id(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique

# =============================================================================
#  ANNOTATION -- one CSV row
# =============================================================================

def annotate_row(llm: Any, row: Dict[str, str], use_history: bool = True
                 ) -> Dict[str, Any]:
    """Annotate every bullet of one CSV row, in order, against its history."""
    rid = row.get(ID_COL) or "?"
    findings = M.sanitize_report(row.get(FINDINGS_COL) or "")
    history = M.sanitize_report(row.get(HISTORY_COL) or "")
    units = split_bullets(findings)

    have_history = bool(history) and use_history
    hist_anns: List[M.Annotation] = []
    if have_history:
        hist_anns = M.annotate_report(llm, history, "prior", judge_change=False)

    anns: List[M.Annotation] = []
    for u in units:
        M.assert_ascii(u["text"], f"bullet[{rid}#{u['index']}]")
        a = M.annotate_line(llm,
                            {"section": u["header"], "text": u["text"]},
                            "current", u["index"], judge_change=True)
        if _SENTENCES_RE.findall(u["text"])[1:]:
            # One bullet is one input, so a bullet that states two findings
            # keeps only the first; the rest land in other_candidates. Rare
            # (5 bullets in validate.csv) but worth seeing in the output.
            a.flags.append("multi_sentence_bullet")
        anns.append(a)

    mapping = M.match_prior(anns, hist_anns, have_history)
    for a in anns:
        if a.annotated:
            a.change, a.change_reason = M.interval_change(a, mapping[a.id])
    M.mark_duplicates(anns)

    return {
        "row_id": rid,
        "bullets": len(units),
        "findings": sum(1 for a in anns if a.annotated),
        "history_used": have_history,
        "history_text": history,
        "current": [asdict(a) for a in anns],
        "prior": [asdict(a) for a in hist_anns],
        "inputs": [{"index": u["index"], "block": render(u)} for u in units],
    }

# =============================================================================
#  OUTPUT
# =============================================================================

# Every annotation column, and the same sheet without the working columns
# (see M.SLIM_DROP). Both carry the CSV row id and the bullet's position.
COMBINED_COLS = ["row_id", "bullet_index"] + M.CSV_COLS
SLIM_COMBINED_COLS = ["row_id", "bullet_index"] + M.SLIM_COLS


def write_outputs(results: List[Dict[str, Any]], meta: Dict[str, Any],
                  outdir: str = OUTPUT_DIR) -> List[str]:
    os.makedirs(outdir, exist_ok=True)
    stamp = meta["run_id"]

    jpath = os.path.join(outdir, f"srrg_{stamp}.json")
    with open(jpath, "w", encoding="utf-8") as fp:
        json.dump({"meta": meta, "rows": results}, fp, ensure_ascii=False,
                  indent=2)

    flat = [(res["row_id"], i, a)
            for res in results
            for i, a in enumerate(res["current"], 1)]
    rows = [([rid, i], M.csv_row(a)) for rid, i, a in flat]

    cpath = os.path.join(outdir, f"srrg_{stamp}.csv")
    with open(cpath, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(COMBINED_COLS)
        w.writerows(head + row for head, row in rows)

    scpath = os.path.join(outdir, f"srrg_{stamp}_slim.csv")
    with open(scpath, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(SLIM_COMBINED_COLS)
        w.writerows(head + M.slim_row(row) for head, row in rows)

    # Flat twin of the slim sheet: one record per bullet, across every row, so
    # it loads with the same shape as the CSV. Native types are kept, so
    # location_expressions is a list rather than a ";"-joined string.
    sjpath = os.path.join(outdir, f"srrg_{stamp}_slim.json")
    with open(sjpath, "w", encoding="utf-8") as fp:
        json.dump({"meta": meta,
                   "annotations": [dict(row_id=rid, bullet_index=i,
                                        **M.slim_record(a))
                                   for rid, i, a in flat]},
                  fp, ensure_ascii=False, indent=2)
    return [jpath, cpath, sjpath, scpath]


def print_row(res: Dict[str, Any]) -> None:
    print(f"\n=== {res['row_id']}  ({res['bullets']} bullet(s), "
          f"{res['findings']} finding(s))")
    if res["history_text"]:
        mark = "" if res["history_used"] else "  [not sent]"
        print(f'    history: "{res["history_text"]}"{mark}')
    hdr = ["#", "section", "entity", "presence", "severity", "change"]
    w = [3, 24, 30, 13, 9, 15]
    print("    " + "  ".join(h.ljust(x) for h, x in zip(hdr, w)))
    print("    " + "-" * (sum(w) + 2 * len(w)))
    for i, a in enumerate(res["current"], 1):
        if not a.get("annotated"):
            cells = [i, (a.get("section") or "")[:24],
                     "(no finding)", "-", "-", "-"]
        else:
            cells = [i, (a.get("section") or "")[:24],
                     (a.get("entity") or "")[:30],
                     a.get("categorical") or "", a.get("severity") or "-",
                     a.get("change") or ""]
        print("    " + "  ".join(str(c).ljust(x) for c, x in zip(cells, w)))
        flags = [f for f in (a.get("flags") or [])
                 if not f.startswith("not_annotated")]
        if flags:
            print("    " + " " * 5 + "flags: " + ";".join(flags))


def dry_run(rows: List[Dict[str, str]]) -> None:
    total_bullets = 0
    for row in rows:
        rid = row.get(ID_COL) or "?"
        findings = M.sanitize_report(row.get(FINDINGS_COL) or "")
        history = M.sanitize_report(row.get(HISTORY_COL) or "")
        units = split_bullets(findings)
        total_bullets += len(units)
        print(f"\n=== {rid}  ({len(units)} bullet(s))")
        if history:
            print(f'    history_section -> prior slot: "{history}"')
        for u in units:
            block = render(u).replace("\n", "\n        ")
            print(f"    #{u['index']}  {block}")
    print(f"\n{len(rows)} row(s), {total_bullets} bullet(s); "
          f"up to {total_bullets * CALLS_PER_BULLET} API calls for the bullets "
          f"plus one per history sentence. No calls were made.")

# =============================================================================
#  MAIN
# =============================================================================

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Feed SRRG findings bullets into maplez_struct, one at a time.")
    ap.add_argument("--csv", default=CSV_PATH, help=f"default: {CSV_PATH}")
    ap.add_argument("--row", type=int, action="append",
                    help="0-based row index; repeatable")
    ap.add_argument("--rows", help="inclusive range of row indices, e.g. 0-9")
    ap.add_argument("--id", action="append", help=f"value of the {ID_COL!r} column; repeatable")
    ap.add_argument("--limit", type=int, help="the first N rows")
    ap.add_argument("--all", action="store_true", help="every row in the file")
    ap.add_argument("--no-history", action="store_true",
                    help="do not send history_section (saves one call per sentence)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the inputs that would be sent; no API calls")
    ap.add_argument("--yes", action="store_true",
                    help=f"required for more than {CONFIRM_ABOVE} rows")
    ap.add_argument("--out", default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    args = ap.parse_args()

    rows = load_rows(args.csv)
    picked = select_rows(rows, args)
    print(f"{args.csv}: {len(rows)} row(s) available, {len(picked)} selected",
          file=sys.stderr)

    if args.dry_run:
        dry_run(picked)
        return

    if len(picked) > CONFIRM_ABOVE and not args.yes:
        sys.exit(f"{len(picked)} rows would each cost API calls. Re-run with "
                 f"--yes if that is what you want, or use --dry-run first.")
    if not M.API_KEY:
        sys.exit("API_KEY is empty. export OPENAI_API_KEY=...")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + \
        uuid.uuid4().hex[:6]
    log = M.CallLog(os.path.join(args.out, "logs"), run_id)
    llm = M.OpenAIChat(M.API_KEY, log)

    results: List[Dict[str, Any]] = []
    try:
        for n, row in enumerate(picked, 1):
            rid = row.get(ID_COL) or "?"
            print(f"[{n}/{len(picked)}] {rid} ...", file=sys.stderr)
            res = annotate_row(llm, row, use_history=not args.no_history)
            results.append(res)
            print_row(res)
    finally:
        calls, itok, otok = llm.calls, llm.in_tokens, llm.out_tokens
        log_paths = [log.jsonl_path, log.text_path]
        log.close()

    meta = {
        "run_id": run_id, "model": M.MODEL, "csv": args.csv,
        "rows": len(results),
        "bullets": sum(r["bullets"] for r in results),
        "findings": sum(r["findings"] for r in results),
        "history_used": not args.no_history,
        "api_calls": calls, "input_tokens": itok, "output_tokens": otok,
        "log_files": log_paths,
    }
    paths = write_outputs(results, meta, args.out)
    print(f"\nrows={meta['rows']}  bullets={meta['bullets']}  "
          f"findings={meta['findings']}  api_calls={calls}  "
          f"in={itok}  out={otok}")
    print("saved: " + " , ".join(paths))
    print("logs : " + " , ".join(log_paths))


if __name__ == "__main__":
    main()
