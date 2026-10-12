#!/usr/bin/env python3
"""
The driver. One utterance in, one Section 2 record out, for as many
utterances as were asked for.

    LLM extraction  ->  ontology normalization  ->  rule-based validation
    qwen_client.py      normalize.py                validate.py

That is Section 8's pipeline and this file is the only place the three steps
meet. Each utterance costs exactly one call to the local Qwen server; the
other two steps are local, deterministic and free, which is why they are
where every judgement that can be made from a table is made.

Usage

    python parse_utterances.py --check              # server only, no parsing
    python parse_utterances.py --dry-run --limit 5  # what would be sent
    python parse_utterances.py --text "No pleural effusion." --section Pleura
    python parse_utterances.py                      # the first CSV row
    python parse_utterances.py --rows 0-9 --yes
    python parse_utterances.py --jsonl subset.jsonl --yes
    python parse_utterances.py --selftest           # no server needed

Output, in ./out_parse/, all sharing one run id:

    parse_{run}.json            the nested records -- the output of record
    propositions_{run}.csv      Section 8's three tables
    anatomy_{run}.csv
    descriptors_{run}.csv
    review_{run}.csv            the utterances a human is asked to look at
    logs/api_calls_{run}.jsonl  every request and reply

The nested JSON is written first and the tables are derived from it, in that
order, because Section 8 says so and because a flattened row cannot be
un-flattened back into a proposition.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flatten as F                    # noqa: E402
import srrg_input as I                 # noqa: E402
from normalize import normalize_record  # noqa: E402
from validate import validate_record    # noqa: E402
import qwen_client as Q                 # noqa: E402

OUTPUT_DIR = "./out_parse"
SPEC_DOC = "MD/Ko-SRRG_CXR_5category_parser_simple.md"

# More utterances than this need an explicit --yes. One call each, tens of
# seconds each, on a 27B model split over four 1080 Ti's.
CONFIRM_ABOVE = 50


# =============================================================================
#  ONE UTTERANCE
# =============================================================================

def parse_one(llm: Q.Qwen, item: Dict[str, Any], *,
              use_section: bool = True) -> Dict[str, Any]:
    """extraction -> normalization -> validation, for one utterance.

    The returned record is Section 2's object plus three keys this pipeline
    adds and Section 2 does not forbid:

        normalization   what step 2 changed, one entry per change
        review          step 3's findings and Section 8's triggers
        row_id          where the utterance came from, for joining back

    A call that fails after its retries returns a record with no propositions
    and an error in review, rather than killing the run: one bad utterance in
    a thousand should cost one row, not the other nine hundred and ninety-nine.
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
    """Write everything that goes on the wire, as one file. No calls.

    The prompt is assembled from six modules at request time, which is right
    for the code and wrong for reading it: nobody can see what the model is
    actually told without running something. This renders the whole thing --
    system message, tool schema, every few-shot example, the selection rule
    and one complete assembled request -- from those same modules, so the
    file cannot drift from what is sent.

    Regenerate it after touching anything under Prompt/.
    """
    from Prompt import (EXAMPLES, PROPOSITIONS, SYSTEM_PROMPT, TOOL_NAME,
                        render, selected)
    from Prompt.selection import ALWAYS_FIRST, CUE_TABLE, MAX_EXAMPLES
    from Prompt.user_template import _HEADER, input_block, render_example
    import qwen_client as QC

    uid, utt, sec = _DUMP_UTTERANCE
    picked = selected(utt)
    out: List[str] = []
    w = out.append

    w("# ReportCXR2 — 모델에 실제로 들어가는 프롬프트 전문\n")
    w(f"생성: `python parse_utterances.py --dump-prompt {path}`  \n"
      f"출처: `Prompt/` 모듈에서 직접 렌더. 손으로 옮겨 적은 부분은 없다.\n")
    w("발화 하나가 요청 하나다. 요청은 아래 세 조각으로 조립된다.\n")
    w("```")
    w("messages[0]  role=system   §1 그대로, 매 호출 동일")
    w("messages[1]  role=user     §3 머리말 + §2에서 고른 예시 3~4개 + §4 대상 발화")
    w(f"tools[0]     {TOOL_NAME}  §5 스키마, tool_choice=\"required\"로 강제")
    w("```\n")
    w("---\n")

    w("## 1. SYSTEM 메시지\n")
    w(f"매 호출 바이트까지 동일하다 ({len(SYSTEM_PROMPT):,}자). "
      f"출처 `Prompt/system.py`.\n")
    w("```text")
    w(SYSTEM_PROMPT.rstrip("\n"))
    w("```")
    w("(파일에는 끝에 개행 하나가 더 있다. 위 블록은 그것만 뺀 전문이다.)\n")
    w("---\n")

    w("## 2. USER 메시지 — few-shot 예시 8종\n")
    w("아래 8개 중 발화마다 3~4개가 §3의 규칙으로 선택되어 user 메시지 앞부분에 "
      "그대로 들어간다. 출처 `Prompt/examples.py`.\n")
    w("`### Example N` 의 N은 그 요청에서 몇 번째로 실렸는지이고, 선택 결과에 따라 "
      "매번 다시 매겨진다. 아래는 풀 안에서의 순번으로 보인 것이다.\n")
    for i, name in enumerate(EXAMPLES, 1):
        w(f"### `{name}`\n")
        w("```text")
        w(render_example(EXAMPLES[name], i).rstrip())
        w("```\n")
    w("---\n")

    w("## 3. 어느 예시를 보내는가\n")
    w("```")
    w(f"[1] {ALWAYS_FIRST!r}                                   항상")
    w("[2] 'qualified' (발화에 부정이 있으면) / 'multi_location'  항상")
    w("[3] 아래 표에서 처음 걸리는 것 하나                        cue")
    w("[3'] 아무 cue도 안 걸리면 [2]의 나머지 반쪽                폴백")
    w(f"    총 {MAX_EXAMPLES}개를 넘지 않는다")
    w("```\n")
    w("표의 순서가 곧 우선순위다. cue는 단어 경계로 맞춘다.\n")
    w("| # | 예시 | cue |")
    w("|---|---|---|")
    for i, (nm, cues) in enumerate(CUE_TABLE, 1):
        w(f"| {i} | `{nm}` | " +
          " · ".join(f"`{c.strip()}`" for c in cues) + " |")
    w("")
    w("---\n")

    w("## 4. USER 메시지 — 대상 발화 블록\n")
    w("예시들 뒤에 붙는 부분. 이것만 발화마다 바뀐다.\n")
    w("```text")
    w("### Now parse this one\n")
    w("Parse this SRRG chest X-ray utterance.\n")
    w(input_block("{{ID}}", "{{UTTERANCE}}", "{{SECTION_OR_NULL}}"))
    w("\nReturn JSON only.")
    w("```\n")
    w("`utterance_id`·`section`이 없으면 문자열이 아니라 JSON `null`이 들어간다.\n")
    w("---\n")

    w("## 5. TOOL 스키마\n")
    w(f"`tools[0].function.name = \"{TOOL_NAME}\"`, "
      f"`tool_choice = \"required\"`. llama.cpp가 이 스키마를 GGBNF 문법으로 "
      f"컴파일하므로 여기 없는 값은 생성 자체가 안 된다. "
      f"출처 `Prompt/schema.py` + `Prompt/vocabulary.py`.\n")
    w("```json")
    w(json.dumps(PROPOSITIONS, ensure_ascii=False, indent=2))
    w("```\n")
    w("---\n")

    w("## 6. 완성된 요청 — 실제 한 건\n")
    w(f"발화: `{utt}` (section `{sec}`)  \n")
    w(f"선택된 예시: {', '.join('`' + e['name'] + '`' for e in picked)}\n")
    user = render(uid, utt, sec, picked)
    w(f"### messages[0] · system ({len(SYSTEM_PROMPT):,}자)\n")
    w("§1과 동일.\n")
    w(f"### messages[1] · user ({len(user):,}자)\n")
    w("```text")
    w(user)
    w("```\n")
    w("---\n")

    w("## 7. json 모드일 때만 붙는 것\n")
    w("서버가 tool call을 못 하면 같은 user 메시지 끝에 아래가 이어 붙고, "
      "`response_format=json_schema`로 §5의 스키마가 다시 실린다.\n")
    w("```text")
    w(QC.JSON_INSTRUCTION.format(schema="<§5의 스키마>").strip())
    w("```\n")
    w("---\n")

    w("## 8. 프롬프트가 아닌 것\n")
    w("| 파일 | 왜 안 나가나 |")
    w("|---|---|")
    w("| `Prompt/ontology.py` | 응답을 받은 **뒤** 정규화에만 쓴다 |")
    w("| `Prompt/user_template.py`의 `USER_TEMPLATE` | 명세 §4 원문 보존용. 실제 조립은 `render()` |")
    w("| `Prompt/schema.py`의 `FULL_RECORD` | 디스크에서 읽은 레코드 검사용 |")
    w("| `Prompt/examples.py`의 `NOTE_D` | 명세 §6 D를 인코딩할 때 채운 자리의 기록 |")
    w("")

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(out).rstrip() + "\n")
    return path


def replay(log_path: str, *, use_section: bool = True
           ) -> List[Dict[str, Any]]:
    """Re-run steps 2 and 3 over a previous run's raw replies. No calls.

    Step 1 costs 25 seconds an utterance on this host; steps 2 and 3 cost
    nothing and are pure functions of a table. Every time Prompt/ontology.py
    grows a row, the question "what does that change" has an exact answer,
    and it should not take an hour of GPU time to get it.

    logs/api_calls_{run}.jsonl holds the payload of every reply, so this
    reads them back, normalizes and validates them again, and returns the
    records as if the run had just happened. The model's answers are
    untouched; only what this repository does to them is re-done.
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
    """The records with nothing this pipeline added -- Section 2 and no more.

    parse_{run}.json carries `normalization`, `review`, `row_id` and timing
    alongside the record, because a run has to be auditable. A file written
    for the specification's own shape must not: anything beyond the five keys
    of Section 2 is this parser talking about itself, not a parse.
    """
    return [{k: rec.get(k) for k in SPEC_KEYS} for rec in records]


def write_spec_json(records: List[Dict[str, Any]], path: str) -> str:
    """Write the Section 2 records to one file, as a JSON array.

    One utterance is one Section 2 object; a findings_section is several of
    them, in the order they appear in the report. So the file is an array of
    those objects and nothing wraps it.
    """
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(spec_records(records), fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    return path


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def write_spec_dir(records: List[Dict[str, Any]], outdir: str) -> List[str]:
    """One Section 2 file per source row, named by that row's id.

    A run over many rows is still one run -- one log, one meta, one set of
    tables -- but the parse of a report belongs with that report. So this
    writes DIR/{row_id}.json, holding exactly the utterances of that row in
    the order they appear in its findings_section.

    Records that came from --text have no row id and land in adhoc.json.
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

    The pool is the specification's own worked answers, so normalization must
    be a no-op on it and validation must find nothing. If either fires, a
    table has drifted away from the prompt that teaches it, and every parse
    made since is suspect.
    """
    from Prompt.examples import EXAMPLES

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
