#!/usr/bin/env python3
"""The driver: one utterance in, one Section 2 record out.

    qwen_client.py  ->  normalize.py  ->  validate.py
    step 1 (paid)       step 2 (free)     step 3 (free)

The only place the three steps meet. One server call per utterance; steps 2
and 3 are local and deterministic, which is why every judgement that can be
made from a table is made there.

    python parse_utterances.py --check              # server only
    python parse_utterances.py --dry-run --limit 5  # what would be sent
    python parse_utterances.py --text "..." --section Pleura
    python parse_utterances.py --rows 0-9 --yes
    python parse_utterances.py --jsonl subset.jsonl --yes
    python parse_utterances.py --selftest           # no server needed

Writes to ./out_parse/, sharing one run id: parse_{run}.json (nested records,
the output of record), three flattened CSVs, review_{run}.csv, and
logs/api_calls_{run}.jsonl. The nested JSON is written first and the tables are
derived from it -- a flattened row cannot be un-flattened.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                     # sibling modules
sys.path.insert(0, os.path.dirname(_HERE))    # prompt packages at the repo root

import flatten as F                    # noqa: E402
import srrg_input as I                 # noqa: E402
from normalize import normalize_record  # noqa: E402
from validate import validate_record    # noqa: E402
import qwen_client as Q                 # noqa: E402

OUTPUT_DIR = "./out_parse"
SPEC_DOC = "Ko-SRRG_CXR_5category_parser_simple.md"   # the spec this parser follows

# More utterances than this need an explicit --yes. One call each, tens of
# seconds each, on a 27B model split over four 1080 Ti's.
CONFIRM_ABOVE = 50


# =============================================================================
#  ONE UTTERANCE
# =============================================================================

def parse_one(llm: Q.Qwen, item: Dict[str, Any], *,
              use_section: bool = True) -> Dict[str, Any]:
    """Steps 1-3 for one utterance.

    Returns Section 2's object plus normalization (what step 2 changed), review
    (findings and triggers) and row_id. A call that fails every retry returns a
    record with no propositions and an error in review, so one bad utterance
    costs one row rather than the run.
    """
    t0 = time.time()
    raw: Dict[str, Any]
    error: Optional[str] = None
    try:
        raw = llm.parse(item["utterance_id"], item["utterance"],
                        item.get("section"))
    except Exception as e:                              # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
        raw = {"propositions": [], "warnings": []}

    # rule 3: the input fields are re-attached from the input, never echoed
    # back by the model, so "exact input text" cannot be broken by a typo.
    record = {
        "utterance_id": item["utterance_id"],
        "utterance": item["utterance"],
        "section": item.get("section"),
        "propositions": raw.get("propositions") or [],
        "warnings": raw.get("warnings") or [],
    }

    record = normalize_record(record, use_section=use_section)
    review = validate_record(record)
    if error:
        review = dict(review, ok=False, errors=review["errors"] + 1,
                      findings=[{"severity": "error", "code": "call_failed",
                                 "rule": None, "proposition": None,
                                 "message": error}] + review["findings"])

    record["review"] = review
    record["row_id"] = item.get("row_id")
    record["bullet_index"] = item.get("bullet_index")
    record["elapsed_s"] = round(time.time() - t0, 2)
    return record


# The utterance the worked request at the end of the dump is built from.
# Section 5's own example, so the dump can be checked against the spec.
_DUMP_UTTERANCE = ("10_pleura_01", "There is no pleural effusion.", "Pleura")


def dump_prompt(path: str) -> str:
    """Write everything that goes on the wire as one file. No calls.

    Rendered from the same modules the request is built from, so it cannot
    drift from what is sent. REPORTCXR_PROMPT decides which package is dumped.
    """
    import qwen_client as QC
    P = QC.PROMPT
    EXAMPLES, SYSTEM_PROMPT = P.EXAMPLES, P.SYSTEM_PROMPT
    render, selected = P.render, P.selected
    PROPOSITIONS, TOOL_NAME = QC.PROPOSITIONS, QC.TOOL_NAME   # one schema, always
    ALWAYS_FIRST = P.selection.ALWAYS_FIRST
    CUE_TABLE, MAX_EXAMPLES = P.CUE_TABLE, P.MAX_EXAMPLES
    from Prompt.user_template import _HEADER, input_block, render_example

    uid, utt, sec = _DUMP_UTTERANCE
    picked = selected(utt)
    out: List[str] = []
    w = out.append

    w(f"# The prompt as it goes on the wire ({QC._PROMPT_PKG})\n")
    w(f"Generated by: `python parse_utterances.py --dump-prompt {path}`  \n"
      f"Rendered from the prompt modules themselves; nothing here is transcribed.\n")
    w("One utterance is one request, assembled from three pieces.\n")
    w("```")
    w("messages[0]  role=system   section 1, byte-identical on every call")
    w("messages[1]  role=user     header + 3-4 examples (section 3) + the utterance")
    w(f"tools[0]     {TOOL_NAME}  the schema, forced with tool_choice=\"required\"")
    w("```\n")
    w("---\n")

    w("## 1. SYSTEM message\n")
    w(f"Byte-identical on every call ({len(SYSTEM_PROMPT):,} chars). "
      f"Source: `{QC._PROMPT_PKG}/system.py`.\n")
    w("```text")
    w(SYSTEM_PROMPT.rstrip("\n"))
    w("```")
    w("(The file has one extra trailing newline; the block above omits only that.)\n")
    w("---\n")

    w(f"## 2. USER message -- the few-shot pool ({len(EXAMPLES)} examples)\n")
    w(f"3-4 of these are selected per utterance and inlined at the head of the "
      f"user message. Source: `{QC._PROMPT_PKG}/examples.py`.\n")
    w("The N in `### Example N` is the position within THAT request and is "
      "renumbered every time; below they are listed in pool order.\n")
    for i, name in enumerate(EXAMPLES, 1):
        w(f"### `{name}`\n")
        w("```text")
        w(render_example(EXAMPLES[name], i).rstrip())
        w("```\n")
    w("---\n")

    w("## 3. Which examples are sent\n")
    w("```")
    w(f"[1] {ALWAYS_FIRST!r}                                    always")
    w("[2] 'qualified' (if the utterance negates) / 'multi_location'  always")
    w("[3] the first cue in the table below that fires               cue")
    w("[3'] if no cue fires, the other half of [2]                    fallback")
    w(f"    never more than {MAX_EXAMPLES} in total")
    w("```\n")
    w("Table order is priority order. Cues match on word boundaries.\n")
    w("| # | example | cue |")
    w("|---|---|---|")
    for i, (nm, cues) in enumerate(CUE_TABLE, 1):
        w(f"| {i} | `{nm}` | " +
          " · ".join(f"`{c.strip()}`" for c in cues) + " |")
    w("")
    w("---\n")

    w("## 4. USER message -- the target utterance block\n")
    w("Appended after the examples; this is the only part that changes.\n")
    w("```text")
    w("### Now parse this one\n")
    w("Parse this SRRG chest X-ray utterance.\n")
    w(input_block("{{ID}}", "{{UTTERANCE}}", "{{SECTION_OR_NULL}}"))
    w("\nReturn JSON only.")
    w("```\n")
    w("A missing `utterance_id` or `section` is JSON `null`, not a string.\n")
    w("---\n")

    w("## 5. TOOL schema\n")
    w(f"`tools[0].function.name = \"{TOOL_NAME}\"`, "
      f"`tool_choice = \"required\"`. llama.cpp compiles this into a GGBNF "
      f"grammar, so a value absent here cannot be generated at all. "
      f"Source: `Prompt2/schema.py` + `Prompt2/vocabulary.py`.\n")
    w("```json")
    w(json.dumps(PROPOSITIONS, ensure_ascii=False, indent=2))
    w("```\n")
    w("---\n")

    w("## 6. One assembled request\n")
    w(f"Utterance: `{utt}` (section `{sec}`)  \n")
    w(f"Examples selected: {', '.join('`' + e['name'] + '`' for e in picked)}\n")
    user = render(uid, utt, sec, picked)
    w(f"### messages[0] · system ({len(SYSTEM_PROMPT):,} chars)\n")
    w("Identical to section 1.\n")
    w(f"### messages[1] · user ({len(user):,} chars)\n")
    w("```text")
    w(user)
    w("```\n")
    w("---\n")

    w("## 7. Added only in json mode\n")
    w("If the server cannot do tool calls, the text below is appended to the same "
      "user message and the schema is resent as `response_format=json_schema`.\n")
    w("```text")
    w(QC.JSON_INSTRUCTION.format(schema="<the schema from section 5>").strip())
    w("```\n")
    w("---\n")

    w("## 8. What is NOT sent\n")
    w("| file | why it never goes on the wire |")
    w("|---|---|")
    w("| `Prompt2/ontology.py` | used only AFTER the reply, to normalize it |")
    w("| `Prompt/user_template.py` `USER_TEMPLATE` | keeps the spec wording; `render()` does the work |")
    w("| `Prompt/schema.py` `FULL_RECORD` | validates records read back from disk |")
    w("| `Prompt/examples.py` `NOTE_D` | a note on how the spec example was encoded |")
    w("")

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(out).rstrip() + "\n")
    return path


def replay(log_path: str, *, use_section: bool = True
           ) -> List[Dict[str, Any]]:
    """Re-run steps 2 and 3 over a previous run's raw replies. No calls.

    Reads logs/api_calls_{run}.jsonl, normalizes and validates again. The
    model's answers are untouched -- only what this repo does to them is redone,
    which is how "what does this ontology row change" is answered without GPU time.
    """
    latest: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    with open(log_path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("status") != "ok" or not entry.get("response"):
                continue
            uid = entry.get("utterance_id")
            if uid not in latest:
                order.append(uid)
            latest[uid] = entry            # a retry supersedes its attempt

    records: List[Dict[str, Any]] = []
    for uid in order:
        entry = latest[uid]
        raw = entry["response"]
        section = entry.get("section")
        record = {
            "utterance_id": uid,
            "utterance": entry.get("utterance") or "",
            "section": section,
            "propositions": raw.get("propositions") or [],
            "warnings": raw.get("warnings") or [],
        }
        record = normalize_record(record, use_section=use_section)
        record["review"] = validate_record(record)
        # row_id is not logged; it is the part of the id before the section
        # slug that srrg_input.py built the id from.
        sep = f"_{I.slug(section)}_"
        record["row_id"] = uid.split(sep)[0] if sep in uid else None
        record["bullet_index"] = None
        record["elapsed_s"] = 0.0
        records.append(record)
    return records


def print_record(rec: Dict[str, Any]) -> None:
    props = rec.get("propositions") or []
    review = rec.get("review") or {}
    mark = "" if review.get("ok") else "  [ERRORS]"
    print(f"\n=== {rec['utterance_id']}  [{rec.get('section') or '-'}]"
          f"  {len(props)} proposition(s){mark}")
    print(f'    "{rec["utterance"]}"')
    for p in props:
        ent = p.get("entity") or {}
        a = p.get("assertion") or {}
        c = p.get("comparison") or {}
        loc = ", ".join(
            f"{x.get('label')}"
            f"{'/' + x['laterality'] if x.get('laterality') not in (None, 'unspecified') else ''}"
            f"{'[' + x['role'] + ']' if x.get('role') != 'site' else ''}"
            for x in p.get("anatomy") or []) or "-"
        desc = ", ".join(f"{d.get('type')}={d.get('label')}"
                         for d in p.get("descriptors") or []) or "-"
        link = f"  <- {p['derived_from']}" if p.get("derived_from") else ""
        print(f"    {p.get('id')}  {ent.get('label')} ({ent.get('type')})"
              f"  assertion={a.get('label')}"
              f"  comparison={c.get('label')}{link}")
        print(f"        anatomy    : {loc}")
        print(f"        descriptors: {desc}")
    for w in rec.get("warnings") or []:
        print(f"    warning: {w}")
    for f in review.get("findings") or []:
        where = f" @{f['proposition']}" if f.get("proposition") else ""
        print(f"    {f['severity']}: {f['code']}{where} "
              f"({f.get('rule') or '-'}) {f['message']}")
    if review.get("triggers"):
        print(f"    review: {'; '.join(review['triggers'])}")


# =============================================================================
#  OUTPUT
# =============================================================================

# The five keys Section 2 defines, in the order the specification writes them.
SPEC_KEYS = ["utterance_id", "utterance", "section", "propositions",
             "warnings"]


def spec_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The records with nothing this pipeline added -- Section 2's five keys only."""
    return [{k: rec.get(k) for k in SPEC_KEYS} for rec in records]


def write_spec_json(records: List[Dict[str, Any]], path: str) -> str:
    """Write the Section 2 records as one JSON array, in report order."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(spec_records(records), fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    return path


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def write_spec_dir(records: List[Dict[str, Any]], outdir: str) -> List[str]:
    """One Section 2 file per source row: DIR/{row_id}.json, in report order.

    Records from --text have no row id and land in adhoc.json.
    """
    os.makedirs(outdir, exist_ok=True)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        groups.setdefault(str(rec.get("row_id") or "adhoc"), []).append(rec)

    paths: List[str] = []
    for key, recs in groups.items():
        name = _UNSAFE.sub("_", key) or "adhoc"
        paths.append(write_spec_json(recs, os.path.join(outdir,
                                                        f"{name}.json")))
    return paths


def write_outputs(records: List[Dict[str, Any]], meta: Dict[str, Any],
                  outdir: str) -> List[str]:
    os.makedirs(outdir, exist_ok=True)
    stamp = meta["run_id"]
    jpath = os.path.join(outdir, f"parse_{stamp}.json")
    with open(jpath, "w", encoding="utf-8") as fp:
        json.dump({"meta": meta, "records": records}, fp, ensure_ascii=False,
                  indent=2)
    return [jpath] + F.write_tables(records, outdir, stamp)


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    props = [p for r in records for p in r.get("propositions") or []]
    reviews = [r.get("review") or {} for r in records]
    per_utterance: Dict[str, int] = {}
    for r in records:
        n = len(r.get("propositions") or [])
        per_utterance[str(n)] = per_utterance.get(str(n), 0) + 1
    triggers: Dict[str, int] = {}
    for v in reviews:
        for t in v.get("triggers") or []:
            triggers[t] = triggers.get(t, 0) + 1
    return {
        "utterances": len(records),
        "propositions": len(props),
        "propositions_per_utterance": dict(sorted(per_utterance.items())),
        "with_errors": sum(1 for v in reviews if not v.get("ok", True)),
        "with_warnings": sum(1 for v in reviews if v.get("warnings")),
        "flagged_for_review": sum(1 for v in reviews if v.get("triggers")),
        "triggers": triggers,
        "derived_propositions": sum(1 for p in props if p.get("derived_from")),
        "multi_anatomy_propositions":
            sum(1 for p in props if len(p.get("anatomy") or []) > 1),
    }


# =============================================================================
#  SELFTEST  -- no server needed
# =============================================================================

def selftest() -> None:
    """Steps 2 and 3 against the few-shot pool, then against broken records.

    The pool must be a fixed point: if normalization changes it or validation
    finds anything, a table has drifted from the prompt that teaches it.
    """
    import qwen_client as QC
    EXAMPLES = QC.PROMPT.EXAMPLES

    failures: List[str] = []

    for name, ex in EXAMPLES.items():
        rec = dict(ex["input"], **ex["output"])
        norm = normalize_record(rec)
        changed = [n["code"] for n in norm["normalization"]]
        review = validate_record(norm)
        errs = [f["code"] for f in review["findings"]]
        status = "ok" if not changed and not errs else "CHANGED"
        print(f"  {name:<16} {status:<8} normalization={changed or '[]'} "
              f"findings={errs or '[]'} triggers={review['triggers'] or '[]'}")
        if changed:
            failures.append(f"{name}: normalization changed the gold answer "
                            f"({changed})")
        if errs:
            failures.append(f"{name}: validation flagged the gold answer "
                            f"({errs})")

    print("\n  -- deliberately broken records: each must be caught --")
    broken = [
        ("invented span", {
            "utterance": "No pleural effusion.", "section": "Pleura",
            "propositions": [{"id": "p1",
                              "entity": {"text": "pneumothorax",
                                         "label": "pneumothorax",
                                         "type": "finding"},
                              "anatomy": [], "descriptors": [],
                              "assertion": {"label": "absent", "cue": "No"},
                              "comparison": {"label": "none", "cue": None},
                              "derived_from": None}],
            "warnings": []}, "entity_text_not_in_utterance"),
        ("resolved not absent", {
            "utterance": "Pneumothorax has resolved.", "section": "Pleura",
            "propositions": [{"id": "p1",
                              "entity": {"text": "Pneumothorax",
                                         "label": "pneumothorax",
                                         "type": "finding"},
                              "anatomy": [], "descriptors": [],
                              "assertion": {"label": "present", "cue": None},
                              "comparison": {"label": "resolved",
                                             "cue": "resolved"},
                              "derived_from": None}],
            "warnings": []}, "resolved_implies_absent"),
        ("laterality from the heading", {
            "utterance": "Pleural thickening.", "section": "Pleura",
            "propositions": [{"id": "p1",
                              "entity": {"text": "Pleural thickening",
                                         "label": "pleural_thickening",
                                         "type": "finding"},
                              "anatomy": [{"text": None, "label": "pleura",
                                           "laterality": "left", "zone": None,
                                           "role": "site",
                                           "source": "section_context"}],
                              "descriptors": [],
                              "assertion": {"label": "present", "cue": None},
                              "comparison": {"label": "none", "cue": None},
                              "derived_from": None}],
            "warnings": []}, "section_context_laterality_dropped"),
        # normalize.py repairs this one before the validator sees it, so the
        # code to expect is the repair. validate.py's derived_from_unknown is
        # the net under a record that was read from disk unnormalized.
        ("dangling derived_from", {
            "utterance": "Opacity suggesting pneumonia.",
            "section": "Lungs and Airways",
            "propositions": [{"id": "p1",
                              "entity": {"text": "pneumonia",
                                         "label": "pneumonia",
                                         "type": "disease"},
                              "anatomy": [], "descriptors": [],
                              "assertion": {"label": "uncertain",
                                            "cue": "suggesting"},
                              "comparison": {"label": "none", "cue": None},
                              "derived_from": "p9"}],
            "warnings": []}, "derived_from_repaired"),
    ]

    for name, rec, expect in broken:
        norm = normalize_record(rec)
        review = validate_record(norm)
        codes = ([n["code"] for n in norm["normalization"]] +
                 [f["code"] for f in review["findings"]])
        hit = expect in codes
        print(f"  {name:<28} {'caught' if hit else 'MISSED'}  ({expect})")
        if not hit:
            failures.append(f"{name}: {expect} was not raised; got {codes}")

    print()
    if failures:
        for msg in failures:
            print(f"  FAIL  {msg}")
        sys.exit(f"{len(failures)} selftest failure(s)")
    print("  selftest passed")


# =============================================================================
#  MAIN
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="SRRG chest X-ray utterances -> 5-category propositions, "
                    "against the local Qwen3.8-27B llama.cpp server.")
    src = ap.add_argument_group("input")
    src.add_argument("--csv", default=I.CSV_PATH, help=f"default: {I.CSV_PATH}")
    src.add_argument("--jsonl", help="one Section 1 object per line, instead "
                                     "of the CSV")
    src.add_argument("--text", help="parse this one utterance and exit")
    src.add_argument("--section", help="section heading for --text")
    src.add_argument("--utterance-id", help="id for --text")
    src.add_argument("--row", type=int, action="append",
                     help="0-based row index; repeatable")
    src.add_argument("--rows", help="inclusive range of row indices, e.g. 0-9")
    src.add_argument("--id", action="append",
                     help=f"value of the {I.ID_COL!r} column; repeatable")
    src.add_argument("--limit", type=int, help="the first N rows")
    src.add_argument("--all", action="store_true", help="every row")
    src.add_argument("--max-utterances", type=int,
                     help="stop after N utterances, whatever the rows hold")
    src.add_argument("--split-sentences", action="store_true",
                     help="split a bullet into sentences (off: one bullet is "
                          "one utterance)")

    run = ap.add_argument_group("run")
    run.add_argument("--out", default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    run.add_argument("--dry-run", action="store_true",
                     help="print what would be sent, and which few-shot "
                          "examples; no calls")
    run.add_argument("--yes", action="store_true",
                     help=f"required above {CONFIRM_ABOVE} utterances")
    run.add_argument("--no-section-anatomy", action="store_true",
                     help="do not let the heading fill a missing broad "
                          "anatomy (rule 4)")
    run.add_argument("--spec-json", metavar="PATH",
                     help="also write the records to PATH in the Section 2 "
                          "shape only -- the five keys, no run metadata")
    run.add_argument("--dump-prompt", metavar="PATH",
                     help="write everything that goes on the wire -- system "
                          "message, tool schema, every few-shot example, one "
                          "assembled request -- to PATH; no server")
    run.add_argument("--replay", metavar="LOG",
                     help="re-run steps 2 and 3 over the raw replies in a "
                          "previous run's api_calls_*.jsonl; no server, no "
                          "calls")
    run.add_argument("--spec-dir", metavar="DIR",
                     help="also write one Section 2 file per source row, as "
                          "DIR/{id}.json")
    run.add_argument("--selftest", action="store_true",
                     help="run steps 2 and 3 against the few-shot pool; no "
                          "server needed")

    srv = ap.add_argument_group("local server")
    srv.add_argument("--base-url", default=Q.BASE_URL,
                     help=f"default: {Q.BASE_URL}")
    srv.add_argument("--model", default=Q.MODEL, help=f"default: {Q.MODEL}")
    srv.add_argument("--api-key", default=Q.API_KEY,
                     help="only needed if llama-server was started with "
                          "--api-key")
    srv.add_argument("--thinking", nargs="?", const="low", default=None,
                     choices=["low", "medium", "xhigh"],
                     help="enable thinking at this reasoning effort "
                          "(default: off; bare --thinking means low)")
    srv.add_argument("--mode", default="auto", choices=["auto", "tool", "json"],
                     help="how the structured answer is obtained "
                          "(default: auto)")
    srv.add_argument("--timeout", type=float, default=Q.REQUEST_TIMEOUT,
                     help=f"per-request seconds (default: "
                          f"{Q.REQUEST_TIMEOUT:.0f})")
    srv.add_argument("--max-tokens", type=int, default=Q.MAX_TOKENS,
                     help=f"response cap (default: {Q.MAX_TOKENS})")
    srv.add_argument("--max-examples", type=int, default=4,
                     help="few-shot examples per call (Section 7 says 3-4)")
    srv.add_argument("--check", action="store_true",
                     help="run the preflight only, then exit")
    srv.add_argument("--no-preflight", action="store_true",
                     help="skip the preflight and start calling")
    return ap


def main() -> None:
    args = build_parser().parse_args()

    if args.selftest:
        selftest()
        return

    if args.dump_prompt:
        print("saved: " + dump_prompt(args.dump_prompt))
        return

    if args.check:
        log = Q.CallLog(os.path.join(args.out, "logs"),
                        "check-" + uuid.uuid4().hex[:6])
        try:
            llm = Q.Qwen(log, base_url=args.base_url, model=args.model,
                         api_key=args.api_key, thinking=args.thinking,
                         timeout=args.timeout, mode=args.mode)
            res = Q.preflight(llm)
        finally:
            log.close()
        sys.exit(0 if res.get("ok") else 1)

    if args.replay:
        records = replay(args.replay,
                         use_section=not args.no_section_anatomy)
        print(f"{len(records)} record(s) replayed from {args.replay}",
              file=sys.stderr)
        for rec in records:
            print_record(rec)
        run_id = "replay-" + os.path.basename(args.replay).replace(
            "api_calls_", "").replace(".jsonl", "")
        meta = {"run_id": run_id, "spec": SPEC_DOC, "source": args.replay,
                "replayed_from": args.replay,
                "section_anatomy": not args.no_section_anatomy,
                "api_calls": 0, "input_tokens": 0, "output_tokens": 0,
                "backend": None, "summary": summarize(records),
                "elapsed_s": 0.0}
        paths = write_outputs(records, meta, args.out)
        if args.spec_json:
            paths.append(write_spec_json(records, args.spec_json))
        if args.spec_dir:
            written = write_spec_dir(records, args.spec_dir)
            paths.append(f"{args.spec_dir}/ ({len(written)} file(s))")
        sm = meta["summary"]
        print(f"\nutterances={sm['utterances']}  "
              f"propositions={sm['propositions']}  "
              f"errors={sm['with_errors']}  review={sm['flagged_for_review']}")
        print("saved: " + " , ".join(paths))
        return

    items = I.load_utterances(args)
    print(f"{len(items)} utterance(s) to parse", file=sys.stderr)

    if args.dry_run:
        I.dry_run(items)
        return

    if len(items) > CONFIRM_ABOVE and not args.yes:
        sys.exit(f"{len(items)} utterances, one call each on a local 27B "
                 f"model. Re-run with --yes, or look at --dry-run first.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + \
        uuid.uuid4().hex[:6]
    log = Q.CallLog(os.path.join(args.out, "logs"), run_id)
    llm = Q.Qwen(log, base_url=args.base_url, model=args.model,
                 api_key=args.api_key, thinking=args.thinking,
                 timeout=args.timeout, max_tokens=args.max_tokens,
                 mode=args.mode, max_examples=args.max_examples)

    checked: Dict[str, Any] = {}
    if not args.no_preflight:
        checked = Q.preflight(llm)
        if not checked.get("ok"):
            log.close()
            sys.exit("preflight failed; nothing was sent.")
        if not checked.get("tool_calls") and args.mode == "auto":
            llm.mode = "json"
            print("[info] starting in json mode (grammar-constrained)",
                  file=sys.stderr)

    records: List[Dict[str, Any]] = []
    t_start = time.time()
    try:
        for n, item in enumerate(items, 1):
            print(f"[{n}/{len(items)}] {item['utterance_id']} ...",
                  file=sys.stderr)
            rec = parse_one(llm, item,
                            use_section=not args.no_section_anatomy)
            records.append(rec)
            print_record(rec)
            done = time.time() - t_start
            print(f"    [{rec['elapsed_s']:.0f}s, {llm.calls} call(s) so far, "
                  f"{done / n * (len(items) - n) / 60:.0f} min left]",
                  file=sys.stderr)
    finally:
        calls, itok, otok = llm.calls, llm.in_tokens, llm.out_tokens
        log_paths = [log.jsonl_path, log.text_path]
        log.close()

    elapsed = time.time() - t_start
    meta = {
        "run_id": run_id,
        "spec": SPEC_DOC,
        "source": args.jsonl or ("--text" if args.text else args.csv),
        "section_anatomy": not args.no_section_anatomy,
        "max_examples": args.max_examples,
        "api_calls": calls, "input_tokens": itok, "output_tokens": otok,
        "log_files": log_paths,
        "backend": Q.backend_meta(llm, checked, args.thinking),
        "summary": summarize(records),
        "elapsed_s": round(elapsed, 1),
    }
    paths = write_outputs(records, meta, args.out)
    if args.spec_json:
        paths.append(write_spec_json(records, args.spec_json))
    if args.spec_dir:
        written = write_spec_dir(records, args.spec_dir)
        paths.append(f"{args.spec_dir}/ ({len(written)} file(s))")

    s = meta["summary"]
    rate = f"{otok / elapsed:.1f}" if elapsed > 0 else "?"
    print(f"\nutterances={s['utterances']}  propositions={s['propositions']}  "
          f"errors={s['with_errors']}  review={s['flagged_for_review']}  "
          f"calls={calls}  in={itok}  out={otok}")
    print(f"propositions per utterance: {s['propositions_per_utterance']}")
    print(f"time={elapsed / 60:.1f} min  ({rate} output tok/s, "
          f"{elapsed / max(calls, 1):.1f} s/call, mode={llm.mode})")
    print("saved: " + " , ".join(paths))
    print("logs : " + " , ".join(log_paths))


if __name__ == "__main__":
    main()
