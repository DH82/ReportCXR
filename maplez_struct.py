#!/usr/bin/env python3
"""
Line-level structured annotation of chest X-ray report findings (OpenAI API).

Unit of work
    one line  ->  one finding entity  ->  three axes

The input is expected to be short: a finding line, optionally under an
anatomical heading, and (optionally) an earlier report to compare against. Each
line is read on its own, the single medical observation / finding it is about is
named in open vocabulary, and every axis is judged for that one entity. A line
therefore yields at most one annotation row -- never one row per abnormality.

    Lungs and Airways:
    - New pulmonary vascular cephalization

Axes
    presence   Present / Uncertain / Absent / Not asserted
    location   localizing expressions, plus positive/negative keyword labels
    severity   None(0) < Trace(1) < Minimal(2) < Mild(3) < Moderate(4) < Severe(5)
    change     Resolved / Improved / Stable / Worsened / New / Not comparable

Calls per line: 1 when the line holds no finding, 3 for an absent finding,
5 for a present one. Nothing is asked twice and nothing is asked in stages.

Prompt heritage
    The presence, location and severity prompts condense the knowledge-driven
    decision tree of Bigolin Lanfredi, Mukherjee, Summers (2024), "Enhancing
    chest X-ray datasets with privacy-preserving large language models and
    multi-type annotations", Medical Image Analysis 99:103383 (Appendix A.1.1
    prompts 1/8, 9/10/11 and 12/13) into one call per axis, at line scope. The
    location resource tables (keywords, replacement lists, mutual-exclusion
    rules) follow Appendix A.2.1-A.2.2 and are reused unchanged.

Deviations from the paper
    - open-vocabulary entity extraction (prompt 0) replaces the thirteen fixed
      abnormalities, so nothing is annotated that the line does not state;
    - the paper's probability axis is not implemented at all: presence is asked
      for directly, in one call, with four values;
    - severity is a six-step ladder instead of Mild/Moderate/Severe;
    - the interval-change axis is this script's extension. It is decided by rule
      from the matched prior annotation, with the line's own change wording
      (prompt 4) taking precedence over the rule.

Layout
    Everything sent to the API lives in ./Prompt/ -- one module per question
    (system, p0_entity .. p4_change), plus vocabulary.py (the answer spaces),
    denominations.py (Appendix A.1.2) and location_tables.py (Appendix
    A.2.1-A.2.2, rule-side). This file holds the config, the segmentation, the
    API client, the rules and the orchestration, and imports the rest.

Design constraints for this build
    - Every API request and response is logged (JSONL + human-readable text).
    - All text sent to the API is ASCII English/digits/simple punctuation only.
    - Only three user inputs: API key, current report, prior report (optional).

Usage
    1. Fill in the USER INPUT block below.
    2. python maplez_struct.py
    3. Results land in ./out_maplez/ ; logs in ./out_maplez/logs/
    Offline check of all rule tables (no API key needed):
        python maplez_struct.py --selftest
    List the models this key can actually use:
        python maplez_struct.py --models
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
#  USER INPUT  -- fill in these three values
# =============================================================================

API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Optional: point the client at an OpenAI-compatible endpoint (gateway,
# Azure-style proxy, vLLM server). Leave empty for api.openai.com.
BASE_URL = os.environ.get("OPENAI_BASE_URL", "")

CURRENT_REPORT = """
Pleura:
- No large pleural effusion
"""

PRIOR_REPORT = """
The patient presents with acute shortness of breath.
"""
# Set to None when there is no prior study:
# PRIOR_REPORT = None

# =============================================================================
#  CONFIG
# =============================================================================

# Model / deployment id served by the endpoint above.
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
# Response cap. None -> send no cap at all (the request shape that is known to
# work against this endpoint). Set an int only if replies need to be bounded;
# note that reasoning models spend this budget on hidden reasoning tokens too.
MAX_TOKENS: Optional[int] = None
# How structured answers are obtained: "auto" (forced tool call, falling back
# to JSON-in-text if the endpoint rejects tools), "tool", or "json".
RESPONSE_MODE = os.environ.get("OPENAI_RESPONSE_MODE", "auto")

MAX_WORKERS = 4
MAX_RETRIES = 3
OUTPUT_DIR = "./out_maplez"
LOG_DIR = os.path.join(OUTPUT_DIR, "logs")

# =============================================================================
#  LINE SEGMENTATION -- which parts of the input are read
# =============================================================================

# Any line of the form "Name:" opens a section, so anatomical headings such as
# "Lungs and Airways:" and classic headers such as "FINDINGS:" both work. These
# section names carry no findings and are dropped (compared upper-case).
SKIP_SECTIONS = {
    "TECHNIQUE", "COMPARISON", "EXAM", "EXAMINATION", "PROCEDURE",
    "CLINICAL HISTORY", "HISTORY", "INDICATION", "CLINICAL INFORMATION",
    "REASON FOR EXAM", "REASON FOR EXAMINATION",
}

# =============================================================================
#  PROMPTS AND PREDEFINED CONTENT  -- see ./Prompt/
# =============================================================================
#  Everything that is sent to the API, plus the value sets the answers are
#  checked against, lives in the Prompt package: one module per API question
#  (system, p0_entity, p1_presence, p2_location, p3_severity, p4_change) plus
#  vocabulary, denominations and location_tables. Nothing there imports back
#  from this file, so a prompt can be read and edited on its own.

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Prompt import (                                              # noqa: E402
    # system prompt, sent with every call
    SYSTEM_PROMPT,
    # one prompt + one tool schema per axis
    P0, S_ENTITY,            # e0  which finding is this line about
    P1, S_PRESENCE,          # q1  presence
    P2, S_EXPRESSIONS,       # q2  location
    P3, S_SEVERITY,          # q3  severity
    P4, S_CHANGE_CUE,        # q4  change wording
    PROMPTS,                 # stage id -> (template, schema, tool name)
    # answer spaces
    ENTITY_TYPES, ANNOTATED_ENTITY_TYPES,
    CATEGORICAL_VALUES, PRESENT_LIKE, ABSENT_LIKE,
    SEVERITY_SCALE, SEVERITY_ORDINAL, SEVERITY_BY_ORDINAL,
    SEVERITY_WORDS, NO_SEVERITY_WORDS, SEVERITY_LOOKUP,
    CHANGE_VALUES, CHANGE_DIRECTION, CHANGE_CUES,
    # Appendix A.1.2 denominations and the open-vocabulary bridge
    DENOMINATIONS, DENOMINATIONS_ATTR, USE_GENERIC_DENOMINATIONS, TERM_ALIASES,
    # Appendix A.2.1-A.2.2 location keyword rules (rule-side, never sent)
    THORAX, LOCATION_KEYWORDS, RIB_ORDINALS,
    REPLACEMENT, MAKES_NEGATIVE, PREVENT_NEGATIVE,
)

# =============================================================================
#  ASCII GUARD -- nothing but English text may reach the API
# =============================================================================

ASCII_OK = re.compile(r"^[\x20-\x7E\n\r\t]*$")


def assert_ascii(text: str, where: str) -> str:
    """Reject any non-ASCII character before it reaches the API."""
    if not ASCII_OK.match(text):
        bad = sorted({c for c in text if not ASCII_OK.match(c)})
        raise ValueError(
            f"non-ASCII character(s) {bad!r} found in {where}; "
            f"all API input must be plain English/ASCII")
    return text


def sanitize_report(text: str) -> str:
    """Normalize the input to plain ASCII.

    Anonymization placeholders such as '___' are replaced with 'thing', per
    Appendix A.1.1. Smart quotes and dashes are folded to ASCII equivalents;
    any remaining non-ASCII character is dropped.
    """
    subs = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
            "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " "}
    for k, v in subs.items():
        text = text.replace(k, v)
    text = re.sub(r"_{2,}", "thing", text)
    text = "".join(c for c in text if ASCII_OK.match(c))
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

# =============================================================================
#  LINE SEGMENTATION (rule-based; no API call)
# =============================================================================

# "Lungs and Airways:" / "FINDINGS:" / "FINDINGS: There is ..." all open a
# section. The length bound keeps an ordinary sentence that happens to contain a
# colon from being read as a heading.
_HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z ,&/-]{2,47}?)\s*:\s*(.*)$")

# Numbered or bulleted items start a unit of their own.
_ENUMERATOR_RE = re.compile(r"^\s*(?:\(?\d{1,2}[\.\)]|[-*])\s+")

# Split after . ; ! ? when the next unit starts like a new statement. Decimal
# points ("4.5 cm") are safe because they are not followed by whitespace.
_SENTENCE_RE = re.compile(r"(?<=[.;!?])\s+(?=[A-Z0-9(\"'])")


def split_sections(report: str) -> List[Tuple[str, List[str]]]:
    """Split the input into (section name, lines) pairs.

    Text before the first heading is returned under the name "BODY", which is
    also what an entirely heading-less input yields.
    """
    out: List[Tuple[str, List[str]]] = []
    name, buf = "BODY", []
    for raw in report.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _HEADER_RE.match(line)
        if m and not _ENUMERATOR_RE.match(line):
            if buf:
                out.append((name, buf))
                buf = []
            name = m.group(1).strip()
            rest = m.group(2).strip()
            if rest:
                buf.append(rest)
            continue
        buf.append(line)
    if buf:
        out.append((name, buf))
    return out


def _unwrap(lines: List[str]) -> List[str]:
    """Rejoin hard-wrapped lines, keeping enumerated items separate."""
    chunks: List[str] = []
    for line in lines:
        if _ENUMERATOR_RE.match(line) or not chunks:
            chunks.append(_ENUMERATOR_RE.sub("", line))
        else:
            chunks[-1] = chunks[-1] + " " + line
    return chunks


def split_lines(report: str) -> List[Dict[str, str]]:
    """Input -> the lines that will each be annotated once.

    Sections named in SKIP_SECTIONS are dropped; a line shorter than three
    characters or with no letter in it is dropped.
    """
    units: List[Dict[str, str]] = []
    for name, lines in split_sections(report):
        if name.upper() in SKIP_SECTIONS:
            continue
        for chunk in _unwrap(lines):
            for piece in _SENTENCE_RE.split(chunk):
                s = piece.strip()
                if len(s) < 3 or not re.search(r"[A-Za-z]", s):
                    continue
                units.append({"section": name, "text": s})
    return units

# =============================================================================
#  LOGGING
# =============================================================================

class CallLog:
    """Records every API request and response to JSONL and a readable text log."""

    def __init__(self, log_dir: str, run_id: str):
        os.makedirs(log_dir, exist_ok=True)
        self.run_id = run_id
        self.jsonl_path = os.path.join(log_dir, f"api_calls_{run_id}.jsonl")
        self.text_path = os.path.join(log_dir, f"api_calls_{run_id}.log")
        self.n = 0
        self._jsonl = open(self.jsonl_path, "a", encoding="utf-8")
        self._text = open(self.text_path, "a", encoding="utf-8")

    def record(self, entry: Dict[str, Any]) -> None:
        self.n += 1
        entry = {"seq": self.n, "run_id": self.run_id,
                 "ts": datetime.now(timezone.utc).isoformat(), **entry}
        self._jsonl.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._jsonl.flush()

        head = (f"[{entry['seq']:04d}] {entry['ts']}  stage={entry.get('stage')}  "
                f"label={entry.get('label')}  doc={entry.get('doc')}  "
                f"status={entry.get('status')}  attempt={entry.get('attempt')}  "
                f"latency_ms={entry.get('latency_ms')}")
        self._text.write(head + "\n")
        self._text.write("--- system ---\n" + str(entry.get("system", "")) + "\n")
        self._text.write("--- prompt ---\n" + str(entry.get("prompt", "")) + "\n")
        self._text.write("--- response ---\n"
                         + json.dumps(entry.get("response"), ensure_ascii=False)
                         + "\n")
        if entry.get("error"):
            self._text.write("--- error ---\n" + str(entry["error"]) + "\n")
        self._text.write("=" * 78 + "\n")
        self._text.flush()

    def close(self) -> None:
        self._jsonl.close()
        self._text.close()

# =============================================================================
#  API WRAPPER
# =============================================================================
def extract_json(text: str) -> Dict[str, Any]:
    """Pull a JSON object out of a plain-text model reply (json mode)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1 or j < i:
        raise ValueError(f"no JSON object in model reply: {t[:120]!r}")
    return json.loads(t[i:j + 1])


def validate_payload(payload: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal check that a payload matches one of the S_* schemas."""
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object, got {type(payload).__name__}")
    for key in schema.get("required", []):
        if key not in payload:
            raise ValueError(f"missing key {key!r} in {payload!r}")
    for key, spec in schema.get("properties", {}).items():
        if key not in payload:
            continue
        val, kind = payload[key], spec.get("type")
        if kind == "string":
            if not isinstance(val, str):
                raise ValueError(f"{key!r} must be a string, got {val!r}")
            if spec.get("enum") and val not in spec["enum"]:
                raise ValueError(f"{key!r}={val!r} not in {spec['enum']}")
        elif kind == "integer":
            if isinstance(val, bool):
                raise ValueError(f"{key!r} must be an integer, got {val!r}")
            if isinstance(val, str):                      # "95" / "95%" -> 95
                m = re.search(r"-?\d+", val)
                if not m:
                    raise ValueError(f"{key!r} is not numeric: {val!r}")
                val = int(m.group())
            if not isinstance(val, int):
                raise ValueError(f"{key!r} must be an integer, got {val!r}")
            lo, hi = spec.get("minimum"), spec.get("maximum")
            if (lo is not None and val < lo) or (hi is not None and val > hi):
                raise ValueError(f"{key!r}={val} outside [{lo}, {hi}]")
            payload[key] = val
        elif kind == "array":
            if not isinstance(val, list):
                raise ValueError(f"{key!r} must be a list, got {val!r}")
            payload[key] = [x for x in val if isinstance(x, str)]
    return payload


JSON_INSTRUCTION = ('\n\nReturn your answer as a single JSON object matching '
                    'this schema, with no prose and no code fences: {schema}')

# Errors that mean "this model/endpoint does not do tool calling".
_TOOL_UNSUPPORTED = ("tool", "function", "tool_choice")


class OpenAIChat:
    """Chat Completions client for the MAPLEZ prompts.

    Requests are kept to the shape that is known to work against this endpoint:
    model + messages, plus a token cap only when MAX_TOKENS is set.

    Two ways of getting structured output:
      - "tool": forced function call (preferred; the answer is schema-checked
        by the API itself).
      - "json": plain reply that must contain a JSON object, extracted and
        validated locally. Used when the model has no tool-calling support.
    RESPONSE_MODE = "auto" starts in tool mode and switches to json mode for
    the rest of the run the first time the endpoint rejects tools.
    """

    def __init__(self, api_key: str, log: CallLog, model: str = MODEL):
        from openai import OpenAI
        opts: Dict[str, Any] = {"api_key": api_key}
        if BASE_URL:
            opts["base_url"] = BASE_URL
        self.client = OpenAI(**opts)
        self.model = model
        self.log = log
        self.calls = 0
        self.in_tokens = 0
        self.out_tokens = 0
        self.mode = "json" if RESPONSE_MODE == "json" else "tool"
        self.auto = RESPONSE_MODE == "auto"
        self._lock = threading.Lock()
        # Newer OpenAI models require max_completion_tokens; older models and
        # some compatible servers only accept max_tokens. Detected on first use.
        self._token_param = "max_completion_tokens"

    def _fall_back_to_json(self, why: str) -> None:
        with self._lock:
            if self.mode != "json":
                self.mode = "json"
                print(f"[info] switching to json mode ({why})", file=sys.stderr)

    def _create(self, **kwargs: Any) -> Any:
        """One request. MAX_TOKENS is sent only when it is set."""
        if MAX_TOKENS is None:
            return self.client.chat.completions.create(**kwargs)
        try:
            return self.client.chat.completions.create(
                **{self._token_param: MAX_TOKENS}, **kwargs)
        except Exception as e:  # noqa: BLE001
            text = str(e)
            if "max_tokens" not in text and "max_completion_tokens" not in text:
                raise
            self._token_param = ("max_tokens"
                                 if self._token_param == "max_completion_tokens"
                                 else "max_completion_tokens")
            return self.client.chat.completions.create(
                **{self._token_param: MAX_TOKENS}, **kwargs)

    def ask(self, prompt: str, schema: Dict[str, Any], tool_name: str,
            stage: str, label: str = "", doc: str = "") -> Dict[str, Any]:
        assert_ascii(prompt, f"prompt[{stage}/{label}]")
        assert_ascii(SYSTEM_PROMPT, "system prompt")
        last_err: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            mode = self.mode
            t0 = time.time()
            try:
                if mode == "tool":
                    msg = self._create(
                        model=self.model,
                        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                                  {"role": "user", "content": prompt}],
                        tools=[{"type": "function",
                                "function": {
                                    "name": tool_name,
                                    "description": "Return the answer in "
                                                   "structured form.",
                                    "parameters": schema}}],
                        tool_choice={"type": "function",
                                     "function": {"name": tool_name}},
                    )
                else:
                    user = prompt + JSON_INSTRUCTION.format(
                        schema=json.dumps(schema))
                    msg = self._create(
                        model=self.model,
                        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                                  {"role": "user", "content": user}],
                    )
                dt = int((time.time() - t0) * 1000)

                choice = msg.choices[0]
                content = choice.message.content
                tool_calls = list(choice.message.tool_calls or [])
                payload = None
                if mode == "tool":
                    for tc in tool_calls:
                        if tc.function.name == tool_name:
                            payload = json.loads(tc.function.arguments or "{}")
                            break
                    raw = [tc.function.name for tc in tool_calls] or ["text"]
                else:
                    payload = extract_json(content)
                    raw = ["json"]
                if payload is not None:
                    payload = validate_payload(payload, schema)

                self.calls += 1
                usage = getattr(msg, "usage", None)
                in_tok = getattr(usage, "prompt_tokens", 0) or 0
                out_tok = getattr(usage, "completion_tokens", 0) or 0
                self.in_tokens += in_tok
                self.out_tokens += out_tok
                self.log.record({
                    "stage": stage, "label": label, "doc": doc,
                    "status": "ok" if payload is not None else "no_tool_call",
                    "attempt": attempt, "latency_ms": dt, "model": self.model,
                    "mode": mode, "tool": tool_name, "system": SYSTEM_PROMPT,
                    "prompt": prompt, "response": payload,
                    "raw_content": raw, "content": content,
                    "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
                    "stop_reason": choice.finish_reason,
                })
                if payload is None:
                    if self.auto:
                        self._fall_back_to_json("model returned no tool call")
                    raise ValueError("no tool call returned")
                return payload
            except Exception as e:  # noqa: BLE001
                last_err = e
                self.log.record({
                    "stage": stage, "label": label, "doc": doc,
                    "status": "error", "attempt": attempt,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "model": self.model, "mode": mode, "tool": tool_name,
                    "system": SYSTEM_PROMPT, "prompt": prompt,
                    "response": None, "error": f"{type(e).__name__}: {e}",
                })
                status = getattr(e, "status_code", None)
                text = str(e).lower()
                if (mode == "tool" and self.auto and status in (400, 404)
                        and any(w in text for w in _TOOL_UNSUPPORTED)):
                    self._fall_back_to_json("endpoint rejected tool calling")
                    continue                      # retry immediately in json mode
                if status in (400, 401, 403, 404):
                    # Bad key, no access, or unknown model: retrying cannot help.
                    raise RuntimeError(
                        f"API call rejected ({stage}/{label}): {e}\n"
                        f"  model    = {self.model!r}\n"
                        f"  base_url = {BASE_URL or 'https://api.openai.com/v1'}\n"
                        f"  Run `python maplez_struct.py --models` to list the "
                        f"models this key can actually use, then set "
                        f"OPENAI_MODEL accordingly.") from e
                time.sleep(1.5 * attempt)
        raise RuntimeError(f"API call failed after {MAX_RETRIES} attempts "
                           f"({stage}/{label}): {last_err}")

# =============================================================================
#  RULE HELPERS
# =============================================================================

def tokens_of(expressions: List[str]) -> List[str]:
    """Lowercase word tokens from a list of location expressions."""
    joined = " ".join(expressions).lower()
    joined = joined.replace("-", "-")  # keep hyphenated forms intact
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", joined)


def resolve_known_label(term: str) -> Optional[str]:
    """Open-vocabulary term -> one of the thirteen paper labels, or None.

    Only two things depend on this: which denomination the prompts show, and
    which location keyword set Appendix A.2.2 supplies. An unmatched term is
    annotated all the same, under its own name.
    """
    t = (term or "").lower().strip().strip('".')
    if not t:
        return None
    if t in TERM_ALIASES:
        return TERM_ALIASES[t]
    for key in DENOMINATIONS:
        if t == key.lower():
            return key
    words = t.split()
    for i in range(1, len(words)):          # "loculated pleural effusion"
        tail = " ".join(words[i:])
        if tail in TERM_ALIASES:
            return TERM_ALIASES[tail]
    return None


def denom_for(term: str, attr: bool = False) -> str:
    """The name the prompts use for this entity.

    A known finding is asked about with the paper's denomination, which spells
    out its synonyms; anything else is asked about under the term itself.
    """
    if USE_GENERIC_DENOMINATIONS:
        return term
    key = resolve_known_label(term)
    if key is None:
        return term
    return (DENOMINATIONS_ATTR if attr else DENOMINATIONS)[key]


def keyword_set_for(term: str) -> List[str]:
    key = resolve_known_label(term)
    if key is None:
        return list(THORAX)
    return LOCATION_KEYWORDS.get(key, list(THORAX))


def keyword_labels(term: str, expressions: List[str]
                   ) -> Dict[str, Dict[str, Any]]:
    """Turn free-text location expressions into positive/negative/unlabeled
    keyword labels, following Appendix A.2.1.
    """
    keys = keyword_set_for(term)
    toks = set(tokens_of(expressions))

    positive = set()
    for kw in keys:
        if kw in toks or any(r in toks for r in REPLACEMENT.get(kw, [])):
            positive.add(kw)

    negative = set()
    for p in positive:
        negative |= set(MAKES_NEGATIVE.get(p, []))
    protected = set()
    for p in positive:
        protected |= set(PREVENT_NEGATIVE.get(p, []))
    negative -= protected
    negative -= positive          # a positive mention always wins
    negative &= set(keys)

    out: Dict[str, Dict[str, Any]] = {}
    for kw in keys:
        if kw in positive:
            state = "positive"
        elif kw in negative:
            state = "negative"
        else:
            state = "unlabeled"
        out[kw] = {"state": state}
    return out


def laterality_from(keywords: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """Side of the body, read off the keyword labels. Used for prior matching."""
    left = (keywords.get("left") or {}).get("state") == "positive"
    right = (keywords.get("right") or {}).get("state") == "positive"
    if left and right:
        return "bilateral"
    if left:
        return "left"
    if right:
        return "right"
    return None


def severity_from_words(text: str) -> Optional[str]:
    """Map free text to a step of the severity ladder."""
    low = text.lower()
    for word in NO_SEVERITY_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low):
            low = re.sub(rf"\b{re.escape(word)}\b", " ", low)
    for phrase, cls in SEVERITY_LOOKUP:
        if re.search(rf"\b{re.escape(phrase)}\b", low):
            return cls
    return None


def norm_term(term: str) -> str:
    """Matching key for an entity: the paper label when known, else the term."""
    key = resolve_known_label(term)
    if key:
        return key.lower()
    return re.sub(r"\s+", " ", (term or "").lower().strip())

# =============================================================================
#  DATA MODEL
# =============================================================================
#  The presence values are defined next to the severity ladder above. The
#  MAPLEZ value "Not mentioned" was a report-level verdict; at line scope the
#  entity always is mentioned, so the fourth value says instead that the line
#  asserts nothing about this study (history, recommendation, hypothetical).

@dataclass
class Annotation:
    id: str = ""
    doc: str = ""                            # "current" or "prior"
    section: str = ""
    sentence: str = ""
    # --- entity (prompt 0) ---
    entity: str = ""                         # open-vocabulary, normalized
    entity_type: str = ""
    mention: str = ""                        # verbatim span in the line
    other_candidates: List[str] = field(default_factory=list)
    known_label: Optional[str] = None        # paper label, when the term maps
    denomination: str = ""                   # what the prompts actually asked about
    annotated: bool = False
    # --- presence (prompt 1) ---
    categorical: Optional[str] = None
    cue: Optional[str] = None
    # --- severity (prompt 3) ---
    severity: Optional[str] = None
    severity_ordinal: Optional[int] = None
    severity_from_table: Optional[str] = None
    # --- location (prompt 2) ---
    location_expressions: List[str] = field(default_factory=list)
    location_keywords: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    laterality: Optional[str] = None
    # --- interval change (prompt 4 + rule) ---
    change: Optional[str] = None
    change_cue: Optional[str] = None         # what the line itself said
    change_reason: Optional[str] = None
    change_allowed: List[str] = field(default_factory=list)
    prior_status: Optional[str] = None       # no_prior_report/not_matched/found
    prior_ref: Optional[str] = None
    prior_categorical: Optional[str] = None
    prior_severity: Optional[str] = None
    # --- bookkeeping ---
    duplicate_of: Optional[str] = None
    flags: List[str] = field(default_factory=list)
    decision_path: List[str] = field(default_factory=list)

    @property
    def match_key(self) -> str:
        return f"{norm_term(self.entity)}|{self.laterality or '-'}"

# =============================================================================
#  STAGE 1 -- which finding is this line about (prompt 0)
# =============================================================================

def extract_entity(llm: OpenAIChat, unit: Dict[str, str], doc: str,
                   idx: int) -> Annotation:
    a = Annotation(id=f"{doc[0]}{idx}", doc=doc, section=unit["section"],
                   sentence=unit["text"])
    res = llm.ask(P0.format(section=a.section, sentence=a.sentence),
                  S_ENTITY, "name_entity", "e0", "", doc)

    a.entity = (res.get("term") or "").strip().strip('"').lower()
    a.entity_type = res.get("entity_type") or "none"
    a.mention = (res.get("mention") or "").strip()
    a.other_candidates = [c.strip() for c in (res.get("other_candidates") or [])
                          if c and c.strip()]
    a.decision_path.append(f"e0:{a.entity_type}:{a.entity or '-'}")

    if a.mention and a.mention.lower() not in a.sentence.lower():
        a.flags.append("mention_not_in_sentence")
    if a.other_candidates:
        # Recorded, never annotated: one line produces one row.
        a.flags.append("other_candidates:" + ",".join(a.other_candidates))

    a.known_label = resolve_known_label(a.entity)
    a.annotated = bool(a.entity) and a.entity_type in ANNOTATED_ENTITY_TYPES
    if not a.annotated:
        a.flags.append(f"not_annotated:{a.entity_type}")
        return a
    a.denomination = denom_for(a.entity)
    if a.known_label is None:
        a.flags.append("open_vocabulary_term")
    return a

# =============================================================================
#  STAGE 2 -- presence (prompt 1)
# =============================================================================

def presence_submodule(llm: OpenAIChat, a: Annotation) -> None:
    res = llm.ask(P1.format(sentence=a.sentence, label=a.denomination),
                  S_PRESENCE, "answer_presence", "q1", a.entity, a.doc)
    a.categorical = res.get("presence")
    a.cue = (res.get("cue") or "").strip() or None
    a.decision_path.append(f"q1:{a.categorical}")
    if a.cue and a.cue.lower() not in a.sentence.lower():
        a.flags.append("cue_not_in_sentence")

# =============================================================================
#  STAGE 3 -- location (prompt 2)
# =============================================================================

def location_submodule(llm: OpenAIChat, a: Annotation, label: str) -> List[str]:
    raw = llm.ask(P2.format(sentence=a.sentence, label=label), S_EXPRESSIONS,
                  "list_expressions", "q2", a.entity, a.doc).get("expressions", [])
    kept: List[str] = []
    for e in raw:
        expr = (e or "").strip().strip('"').strip()
        if not expr:
            continue
        try:
            assert_ascii(expr, "expression from q2")
        except ValueError:
            a.flags.append("non_ascii_expression_dropped")
            continue
        kept.append(expr)
    a.decision_path.append(f"q2:{len(kept)} expression(s)")
    return kept

# =============================================================================
#  STAGE 4 -- severity on the six-step ladder (prompt 3)
# =============================================================================

def severity_submodule(llm: OpenAIChat, a: Annotation, label: str) -> Optional[str]:
    sev = llm.ask(P3.format(sentence=a.sentence, label=label), S_SEVERITY,
                  "answer_severity", "q3", a.entity, a.doc)["severity"]
    a.decision_path.append(f"q3:{sev}")
    if sev == "Undefined":
        return None
    if sev == "None" and a.categorical in PRESENT_LIKE:
        # A finding that is present cannot have zero degree; the model is
        # answering "no degree stated", which is what Undefined is for.
        a.flags.append("severity_none_for_present_finding")
        return None
    return sev

# =============================================================================
#  STAGE 5a -- what the line itself says about change (prompt 4)
# =============================================================================

def change_cue_submodule(llm: OpenAIChat, a: Annotation, label: str
                         ) -> Optional[str]:
    cue = llm.ask(P4.format(sentence=a.sentence, label=label), S_CHANGE_CUE,
                  "answer_change", "q4", a.entity, a.doc)["change"]
    a.decision_path.append(f"q4:{cue}")
    return None if cue == "Not stated" else cue

# =============================================================================
#  One line, end to end
# =============================================================================

def annotate_line(llm: OpenAIChat, unit: Dict[str, str], doc: str, idx: int,
                  judge_change: bool) -> Annotation:
    a = extract_entity(llm, unit, doc, idx)
    if not a.annotated:
        return a

    presence_submodule(llm, a)
    label_attr = denom_for(a.entity, attr=True)

    if a.categorical in PRESENT_LIKE:
        a.location_expressions = location_submodule(llm, a, label_attr)
        a.severity = severity_submodule(llm, a, label_attr)

        # Cross-check against the Appendix A.3.2.2 wording table. The input is
        # one short line, so the table is applied to the line itself. A
        # disagreement is flagged, never silently rewritten; only a gap the
        # model left empty is filled in.
        table_sev = severity_from_words(a.sentence)
        a.severity_from_table = table_sev
        if table_sev and a.severity and table_sev != a.severity:
            a.flags.append(f"severity_table_mismatch:table={table_sev},"
                           f"model={a.severity}")
        elif table_sev and not a.severity:
            a.severity = table_sev
            a.flags.append(f"severity_filled_from_table:{table_sev}")

    a.location_keywords = keyword_labels(a.entity, a.location_expressions)
    a.laterality = laterality_from(a.location_keywords)
    if a.severity:
        a.severity_ordinal = SEVERITY_ORDINAL[a.severity]

    if judge_change:
        a.change_cue = change_cue_submodule(llm, a, label_attr)
    return a


def annotate_report(llm: OpenAIChat, report: str, doc: str,
                    judge_change: bool) -> List[Annotation]:
    units = split_lines(report)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        return list(ex.map(
            lambda t: annotate_line(llm, t[1], doc, t[0], judge_change),
            list(enumerate(units, 1))))

# =============================================================================
#  STAGE 5b -- matching the prior report (rule)
# =============================================================================

_PRIOR_RANK = {"Present": 0, "Uncertain": 1, "Absent": 2, "Not asserted": 3}


def _prior_sort_key(p: Annotation) -> Tuple[int, int]:
    """Prefer the most assertive prior statement, then the most severe."""
    return (_PRIOR_RANK.get(p.categorical or "", 9),
            -(p.severity_ordinal if p.severity_ordinal is not None else -1))


def match_prior(current: List[Annotation], prior: List[Annotation],
                prior_available: bool) -> Dict[str, Optional[Annotation]]:
    index: Dict[str, List[Annotation]] = {}
    for p in prior:
        if p.annotated:
            index.setdefault(p.match_key, []).append(p)

    mapping: Dict[str, Optional[Annotation]] = {}
    for c in current:
        if not c.annotated:
            c.prior_status = "not_applicable"
            mapping[c.id] = None
            continue
        if not prior_available:
            c.prior_status = "no_prior_report"
            mapping[c.id] = None
            continue

        hits = list(index.get(c.match_key) or [])
        if not hits:                    # relax: same finding, any laterality
            hits = [p for p in prior if p.annotated
                    and norm_term(p.entity) == norm_term(c.entity)]
            if hits:
                c.flags.append("match_relaxed:laterality")
        if hits:
            best = sorted(hits, key=_prior_sort_key)[0]
            c.prior_status = "found"
            c.prior_ref = best.id
            c.prior_categorical = best.categorical
            c.prior_severity = best.severity
            mapping[c.id] = best
        else:
            c.prior_status = "not_matched"
            mapping[c.id] = None
    return mapping

# =============================================================================
#  STAGE 5c -- interval change (rule, constrained by the line's own wording)
# =============================================================================

def allowed_changes(categorical: Optional[str], prior_status: Optional[str],
                    prior_categorical: Optional[str]) -> List[str]:
    """Which of the six values the pair of annotations can support.

    With nothing to compare against, the only honest answers are New -- and
    only when the line says so in as many words -- and Not comparable.
    """
    if prior_status in ("no_prior_report", "not_matched"):
        return ["New", "Not comparable"]
    if categorical in ABSENT_LIKE:
        if prior_categorical in PRESENT_LIKE:
            return ["Resolved", "Not comparable"]
        return ["Stable", "Not comparable"]
    if prior_categorical in ABSENT_LIKE:
        return ["New", "Not comparable"]
    return ["Improved", "Stable", "Worsened", "Not comparable"]


def interval_change(cur: Annotation, prior: Optional[Annotation]
                    ) -> Tuple[str, str]:
    """Resolved / Improved / Stable / Worsened / New / Not comparable."""
    allowed = allowed_changes(cur.categorical, cur.prior_status,
                              prior.categorical if prior else None)
    cur.change_allowed = allowed

    # 1. The line's own wording wins -- but only if the two annotations can
    #    support it. "increased" against a prior report that never mentioned the
    #    finding is not a comparison this pipeline can stand behind; such a cue
    #    is flagged and dropped, and the comparison below decides instead.
    if cur.change_cue:
        if cur.change_cue in allowed:
            return cur.change_cue, f"the line states it ({cur.change_cue.lower()})"
        cur.flags.append(f"change_cue_unsupported:{cur.change_cue}")

    # 2. No usable wording: compare the two annotations.
    if cur.prior_status == "no_prior_report":
        return "Not comparable", "no prior report"
    if cur.prior_status == "not_matched":
        return "Not comparable", "the prior report says nothing about this finding"
    if prior is None:
        return "Not comparable", "no matched prior annotation"

    if cur.categorical in ABSENT_LIKE and prior.categorical in PRESENT_LIKE:
        return "Resolved", "present in the prior report, absent now"
    if cur.categorical in PRESENT_LIKE and prior.categorical in ABSENT_LIKE:
        return "New", "absent in the prior report, present now"
    if cur.categorical in ABSENT_LIKE and prior.categorical in ABSENT_LIKE:
        return "Stable", "absent at both time points"

    if cur.severity_ordinal is not None and prior.severity_ordinal is not None:
        d = cur.severity_ordinal - prior.severity_ordinal
        if d > 0:
            return "Worsened", f"severity {prior.severity} -> {cur.severity}"
        if d < 0:
            return "Improved", f"severity {prior.severity} -> {cur.severity}"
        return "Stable", f"severity unchanged at {cur.severity}"

    return "Not comparable", "no severity stated on at least one side"


def mark_duplicates(anns: List[Annotation]) -> None:
    """Link lines that annotate the same finding (FINDINGS vs IMPRESSION).

    Nothing is merged: each line keeps its own row, and the later rows point at
    the first one.
    """
    seen: Dict[str, Annotation] = {}
    for a in anns:
        if not a.annotated:
            continue
        head = seen.get(a.match_key)
        if head is None:
            seen[a.match_key] = a
        else:
            a.duplicate_of = head.id
            head.flags.append(f"also_stated_in:{a.id}")

# =============================================================================
#  ORCHESTRATION
# =============================================================================

def run(api_key: str, current: str, prior: Optional[str]) -> Dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + \
        uuid.uuid4().hex[:6]
    log = CallLog(LOG_DIR, run_id)
    llm = OpenAIChat(api_key, log)

    cur_txt = assert_ascii(sanitize_report(current), "current report")
    prior_available = bool(prior and prior.strip())
    prior_txt = assert_ascii(sanitize_report(prior), "prior report") if prior_available else ""

    try:
        prior_anns: List[Annotation] = []
        if prior_available:
            print("[1/3] annotating prior report ...", file=sys.stderr)
            prior_anns = annotate_report(llm, prior_txt, "prior", judge_change=False)
            print(f"      {len(prior_anns)} line(s), "
                  f"{sum(1 for a in prior_anns if a.annotated)} with a finding",
                  file=sys.stderr)

        print("[2/3] annotating current report ...", file=sys.stderr)
        cur_anns = annotate_report(llm, cur_txt, "current", judge_change=True)
        print(f"      {len(cur_anns)} line(s), "
              f"{sum(1 for a in cur_anns if a.annotated)} with a finding",
              file=sys.stderr)

        print("[3/3] matching the prior report and judging interval change ...",
              file=sys.stderr)
        mapping = match_prior(cur_anns, prior_anns, prior_available)
        for a in cur_anns:
            if a.annotated:
                a.change, a.change_reason = interval_change(a, mapping[a.id])
        mark_duplicates(cur_anns)
    finally:
        calls, itok, otok = llm.calls, llm.in_tokens, llm.out_tokens
        log_paths = [log.jsonl_path, log.text_path]
        log.close()

    return {
        "meta": {
            "run_id": run_id, "model": MODEL,
            "generic_denominations": USE_GENERIC_DENOMINATIONS,
            "prior_report_available": prior_available,
            "lines": len(cur_anns),
            "findings": sum(1 for a in cur_anns if a.annotated),
            "api_calls": calls, "input_tokens": itok, "output_tokens": otok,
            "log_files": log_paths,
        },
        "current": [asdict(a) for a in cur_anns],
        "prior": [asdict(a) for a in prior_anns],
        "reports": {"current": cur_txt, "prior": prior_txt},
    }

# =============================================================================
#  OUTPUT
# =============================================================================

CSV_COLS = ["id", "section", "entity", "entity_type", "known_label",
            "categorical", "cue", "severity", "severity_ordinal", "laterality",
            "location_positive", "location_negative", "location_expressions",
            "change", "change_cue", "change_reason", "prior_status",
            "prior_ref", "prior_categorical", "prior_severity",
            "other_candidates", "duplicate_of", "flags", "decision_path",
            "sentence"]

# The second sheet keeps the judgements and the line they were made from, and
# nothing else. Dropped: the wording a judgement came from, the numeric twin of
# a value that is already there by name, the keyword labels derived from
# location_expressions, everything about the prior report, and the bookkeeping
# (other candidates, duplicate link, flags, decision path). The full sheet and
# the JSON keep all of it -- note in particular that "flags", the quality gate,
# is only there.
SLIM_DROP = ["cue", "severity_ordinal", "location_positive",
             "location_negative", "change_cue", "change_reason",
             "prior_status", "prior_ref", "prior_categorical", "prior_severity",
             "other_candidates", "duplicate_of", "flags", "decision_path"]
SLIM_COLS = [c for c in CSV_COLS if c not in SLIM_DROP]
_SLIM_IDX = [CSV_COLS.index(c) for c in SLIM_COLS]


def slim_row(row: List[Any]) -> List[Any]:
    """A csv_row() line with the SLIM_DROP columns taken out.

    Derived from the full line by position, so the two sheets cannot drift.
    """
    return [row[i] for i in _SLIM_IDX]


def slim_record(a: Dict[str, Any]) -> Dict[str, Any]:
    """The JSON twin of slim_row(): one annotation, SLIM_COLS keys only.

    Every SLIM_COLS name is a field of Annotation, so this is a straight
    projection -- and unlike the CSV it keeps native types, so
    location_expressions stays a list instead of a ";"-joined string.
    """
    return {c: a.get(c) for c in SLIM_COLS}


def csv_row(a: Dict[str, Any]) -> List[Any]:
    """One annotation as a CSV line, in CSV_COLS order.

    Public so that a batch driver can build a combined sheet without repeating
    the column order (see SRRG.py).
    """
    kws = a.get("location_keywords") or {}
    pos = [k for k, v in kws.items() if v["state"] == "positive"]
    neg = [k for k, v in kws.items() if v["state"] == "negative"]
    return [
        a.get("id"), a.get("section"), a.get("entity"),
        a.get("entity_type"), a.get("known_label"),
        a.get("categorical"), a.get("cue"), a.get("severity"),
        a.get("severity_ordinal"), a.get("laterality"),
        ";".join(pos), ";".join(neg),
        ";".join(a.get("location_expressions") or []),
        a.get("change"), a.get("change_cue"), a.get("change_reason"),
        a.get("prior_status"), a.get("prior_ref"),
        a.get("prior_categorical"), a.get("prior_severity"),
        ";".join(a.get("other_candidates") or []),
        a.get("duplicate_of"),
        ";".join(a.get("flags") or []),
        " > ".join(a.get("decision_path") or []),
        a.get("sentence"),
    ]


def write_output(result: Dict[str, Any], outdir: str = OUTPUT_DIR) -> List[str]:
    os.makedirs(outdir, exist_ok=True)
    jpath = os.path.join(outdir, f"annotations_{result['meta']['run_id']}.json")
    with open(jpath, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)

    rows = [csv_row(a) for a in result["current"]]

    cpath = os.path.join(outdir, f"annotations_{result['meta']['run_id']}.csv")
    with open(cpath, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(CSV_COLS)
        w.writerows(rows)

    scpath = os.path.join(outdir, f"annotations_{result['meta']['run_id']}_slim.csv")
    with open(scpath, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(SLIM_COLS)
        w.writerows(slim_row(r) for r in rows)

    # The slim JSON carries the same records as the slim CSV: no prior report,
    # no working columns, no full report text. meta stays for provenance.
    sjpath = os.path.join(outdir, f"annotations_{result['meta']['run_id']}_slim.json")
    with open(sjpath, "w", encoding="utf-8") as fp:
        json.dump({"meta": result["meta"],
                   "annotations": [slim_record(a) for a in result["current"]]},
                  fp, ensure_ascii=False, indent=2)
    return [jpath, cpath, sjpath, scpath]


def print_table(result: Dict[str, Any]) -> None:
    hdr = ["id", "entity", "presence", "severity", "loc(+)", "change"]
    w = [5, 30, 13, 10, 18, 15]
    print("\n" + "  ".join(h.ljust(x) for h, x in zip(hdr, w)))
    print("-" * (sum(w) + 2 * len(w)))
    for a in result["current"]:
        kws = a.get("location_keywords") or {}
        pos = [k for k, v in kws.items() if v["state"] == "positive"]
        if not a.get("annotated"):
            cells = [a.get("id", ""), (a.get("sentence") or "")[:30],
                     "(no finding)", "-", "-", "-"]
        else:
            cells = [
                a.get("id", ""),
                (a.get("entity") or "")[:30],
                str(a.get("categorical") or ""),
                str(a.get("severity") or "-"),
                (",".join(pos)[:18] or "-"),
                str(a.get("change") or ""),
            ]
        print("  ".join(str(c).ljust(x) for c, x in zip(cells, w)))
    m = result["meta"]
    print(f"\nlines={m['lines']}  findings={m['findings']}  "
          f"api_calls={m['api_calls']}  in={m['input_tokens']}  "
          f"out={m['output_tokens']}  run_id={m['run_id']}")
    print("logs: " + " , ".join(m["log_files"]))

# =============================================================================
#  SELF TEST -- no API key required
# =============================================================================

def _ann(**kw: Any) -> Annotation:
    a = Annotation(annotated=True, **kw)
    if a.severity and a.severity_ordinal is None:
        a.severity_ordinal = SEVERITY_ORDINAL[a.severity]
    return a


def selftest() -> None:
    # --- ascii guard ---------------------------------------------------------
    assert_ascii("Small right pleural effusion.", "t")
    try:
        assert_ascii("small effusion (soft)", "t")
    except ValueError:
        raise AssertionError("plain ASCII was wrongly rejected")
    bad = False
    try:
        assert_ascii("interval change \ud55c\uae00", "t")
    except ValueError:
        bad = True
    assert bad, "non-ASCII text was not rejected"
    assert sanitize_report("tip is ____ cm") == "tip is thing cm"

    # every prompt template and denomination must be ASCII
    assert_ascii(SYSTEM_PROMPT, "SYSTEM")
    for stage, (tpl, schema, tool) in PROMPTS.items():
        assert_ascii(tpl, stage)
        assert isinstance(schema.get("properties"), dict), stage
        assert schema.get("required"), stage
    # the registry must agree with the prompts the pipeline actually calls
    assert PROMPTS == {
        "e0": (P0, S_ENTITY, "name_entity"),
        "q1": (P1, S_PRESENCE, "answer_presence"),
        "q2": (P2, S_EXPRESSIONS, "list_expressions"),
        "q3": (P3, S_SEVERITY, "answer_severity"),
        "q4": (P4, S_CHANGE_CUE, "answer_change"),
    }, "Prompt/__init__.py PROMPTS is out of step with the pipeline"
    for d in list(DENOMINATIONS.values()) + list(DENOMINATIONS_ATTR.values()):
        assert_ascii(d, "denomination")
    assert len(DENOMINATIONS) == 13, len(DENOMINATIONS)

    # --- line segmentation: the expected input shape -------------------------
    units = split_lines(sanitize_report("""
Lungs and Airways:
- New pulmonary vascular cephalization
"""))
    assert units == [{"section": "Lungs and Airways",
                      "text": "New pulmonary vascular cephalization"}], units
    # a bare sentence with no heading at all
    assert split_lines("The patient presents with acute shortness of breath.") \
        == [{"section": "BODY",
             "text": "The patient presents with acute shortness of breath."}]
    # several headings, several bullets
    srrg = split_lines(sanitize_report("""
Lungs and Airways:
- Mild interstitial pulmonary edema
- Right middle lobe atelectasis
Pleura:
- No pneumothorax
"""))
    assert [u["section"] for u in srrg] == ["Lungs and Airways",
                                            "Lungs and Airways", "Pleura"]
    assert srrg[2]["text"] == "No pneumothorax"
    # classic report: headers inline, numbered impression, skipped sections
    rep = split_lines(sanitize_report("""
FINDINGS: There is a small right pleural effusion. No pneumothorax.
TECHNIQUE:
Portable AP view.
IMPRESSION:
1. Enlarging right pleural effusion.
"""))
    texts = [u["text"] for u in rep]
    assert texts == ["There is a small right pleural effusion.",
                     "No pneumothorax.",
                     "Enlarging right pleural effusion."], texts
    assert [u["section"] for u in rep] == ["FINDINGS", "FINDINGS", "IMPRESSION"]
    # hard-wrapped lines are rejoined, decimals are not line breaks
    wrapped = split_lines("Endotracheal tube tip is 4.5 cm\nabove the carina.")
    assert len(wrapped) == 1 and wrapped[0]["text"].endswith("above the carina.")

    # --- open-vocabulary entity resolution ----------------------------------
    assert resolve_known_label("pleural effusion") == "Pleural effusion"
    assert resolve_known_label("effusion") == "Pleural effusion"
    assert resolve_known_label("loculated pleural effusion") == "Pleural effusion"
    assert resolve_known_label("pulmonary vascular cephalization") is None
    assert denom_for("pneumonia").startswith("pneumonia (infection)")
    assert denom_for("pulmonary vascular cephalization") \
        == "pulmonary vascular cephalization"
    assert keyword_set_for("pulmonary vascular cephalization") == THORAX
    assert "fissure" in keyword_set_for("effusion")
    assert norm_term("effusion") == norm_term("pleural effusion")

    # --- Appendix A.2.1 worked examples from the paper text -----------------
    k = keyword_labels("consolidation", ["in the lower lobe", "upper"])
    assert k["base"]["state"] != "negative", "base must be protected by lower"
    k = keyword_labels("consolidation", ["right"])
    assert k["left"]["state"] == "negative"
    assert k["lower"]["state"] == "unlabeled"
    k = keyword_labels("consolidation", ["bilateral"])
    assert k["left"]["state"] == "positive" and k["right"]["state"] == "positive"
    assert laterality_from(k) == "bilateral"
    k = keyword_labels("consolidation", ["retrocardiac"])
    assert k["left"]["state"] == "positive" and k["lower"]["state"] == "positive"
    k = keyword_labels("pleural effusion", ["along the fissure"])
    assert k["fissure"]["state"] == "positive"
    k = keyword_labels("fracture", ["fifth rib", "posterior"])
    assert k["fifth"]["state"] == "positive" and k["rib"]["state"] == "positive"
    assert k["fourth"]["state"] == "negative"
    assert k["clavicular"]["state"] == "negative"
    assert laterality_from(keyword_labels("consolidation", ["right"])) == "right"
    assert laterality_from(keyword_labels("consolidation", ["basilar"])) is None

    # --- severity ladder: six steps, 0-5 ------------------------------------
    assert SEVERITY_SCALE == ["None", "Trace", "Minimal", "Mild", "Moderate",
                              "Severe"]
    assert SEVERITY_ORDINAL["None"] == 0 and SEVERITY_ORDINAL["Severe"] == 5
    assert SEVERITY_ORDINAL["Trace"] < SEVERITY_ORDINAL["Minimal"] \
        < SEVERITY_ORDINAL["Mild"] < SEVERITY_ORDINAL["Moderate"] \
        < SEVERITY_ORDINAL["Severe"]
    assert severity_from_words("trace effusion") == "Trace"
    assert severity_from_words("minimal atelectasis") == "Minimal"
    assert severity_from_words("small effusion") == "Mild"
    assert severity_from_words("mild to moderate effusion") == "Moderate"
    assert severity_from_words("moderate to severe edema") == "Severe"
    # everything above "severe" folds into Severe
    assert severity_from_words("massive effusion") == "Severe"
    assert severity_from_words("marked cardiomegaly") == "Severe"
    assert severity_from_words("extensive consolidation") == "Severe"
    assert severity_from_words("increasing effusion") is None   # change, not degree
    assert severity_from_words("New pulmonary vascular cephalization") is None
    assert severity_from_words("no adjectives here") is None
    assert set(S_SEVERITY["properties"]["severity"]["enum"]) == \
        set(SEVERITY_SCALE) | {"Undefined"}

    # --- the probability axis is gone ----------------------------------------
    for gone in ("S_PROB", "PROBABILITY_EXPRESSIONS", "probability_from_expression",
                 "PRESENT_PROBABILITY_THRESHOLD", "PROBABILITY_CHANGE_MARGIN"):
        assert gone not in globals(), f"{gone} should have been removed"
    assert not hasattr(Annotation(), "probability")

    # --- prior matching ------------------------------------------------------
    cur = [_ann(id="c1", entity="pleural effusion", laterality="right",
                categorical="Present", severity="Mild"),
           _ann(id="c2", entity="pneumothorax", categorical="Absent")]
    pri = [_ann(id="p1", doc="prior", entity="effusion", laterality="right",
                categorical="Present", severity="Trace"),
           _ann(id="p2", doc="prior", entity="effusion", laterality="right",
                categorical="Uncertain")]
    m = match_prior(cur, pri, True)
    assert m["c1"].id == "p1", "the most assertive prior statement wins"
    assert cur[0].prior_status == "found" and cur[0].prior_severity == "Trace"
    assert m["c2"] is None and cur[1].prior_status == "not_matched"
    # laterality relaxation, and only when the finding itself matches
    cur2 = [_ann(id="c3", entity="pleural effusion", laterality="left",
                 categorical="Present")]
    m2 = match_prior(cur2, pri, True)
    assert m2["c3"] is not None and "match_relaxed:laterality" in cur2[0].flags
    # a line with no finding never matches anything
    skip = [Annotation(id="c4", entity_type="none", annotated=False)]
    assert match_prior(skip, pri, True)["c4"] is None
    assert skip[0].prior_status == "not_applicable"

    # --- interval change -----------------------------------------------------
    def chg(cur_kw: Dict[str, Any], prior_kw: Optional[Dict[str, Any]],
            status: str, cue: Optional[str] = None) -> str:
        c = _ann(prior_status=status, change_cue=cue, **cur_kw)
        p = _ann(doc="prior", **prior_kw) if prior_kw is not None else None
        return interval_change(c, p)[0]

    assert set(CHANGE_VALUES) == {"Resolved", "Improved", "Stable", "Worsened",
                                  "New", "Not comparable"}
    # nothing to compare against -> Not comparable
    assert chg({"categorical": "Present"}, None, "no_prior_report") == "Not comparable"
    assert chg({"categorical": "Present"}, None, "not_matched") == "Not comparable"
    # ... unless the line itself says the finding is new. This is the expected
    # path for "New pulmonary vascular cephalization" against a prior report
    # that only states a symptom.
    assert chg({"categorical": "Present"}, None, "not_matched", "New") == "New"
    # a cue the pair of annotations cannot support is dropped, not passed
    # through; the annotation comparison decides instead
    assert chg({"categorical": "Present"}, None, "not_matched", "Improved") \
        == "Not comparable"
    assert chg({"categorical": "Present"}, {"categorical": "Absent"}, "found",
               "Worsened") == "New"
    assert chg({"categorical": "Absent"}, {"categorical": "Absent"}, "found",
               "Worsened") == "Stable"
    # severity ladder comparison
    assert chg({"categorical": "Present", "severity": "Moderate"},
               {"categorical": "Present", "severity": "Mild"}, "found") == "Worsened"
    assert chg({"categorical": "Present", "severity": "Trace"},
               {"categorical": "Present", "severity": "Minimal"}, "found") == "Improved"
    assert chg({"categorical": "Present", "severity": "Severe"},
               {"categorical": "Present", "severity": "Severe"}, "found") == "Stable"
    # presence transitions
    assert chg({"categorical": "Absent"},
               {"categorical": "Present"}, "found") == "Resolved"
    assert chg({"categorical": "Present"},
               {"categorical": "Absent"}, "found") == "New"
    assert chg({"categorical": "Absent"},
               {"categorical": "Absent"}, "found") == "Stable"
    # explicit wording beats the severity comparison
    assert chg({"categorical": "Present", "severity": "Mild"},
               {"categorical": "Present", "severity": "Mild"}, "found",
               "Worsened") == "Worsened"
    # no severity on one side and nothing else to go on
    assert chg({"categorical": "Present"},
               {"categorical": "Present"}, "found") == "Not comparable"
    # every result is one of the six values
    for status in ("no_prior_report", "not_matched", "found"):
        for cat in CATEGORICAL_VALUES:
            for pcat in CATEGORICAL_VALUES:
                for cue in [None] + CHANGE_VALUES[:-1]:
                    got = chg({"categorical": cat}, {"categorical": pcat},
                              status, cue)
                    assert got in CHANGE_VALUES, (status, cat, pcat, cue, got)

    # --- duplicate linking ---------------------------------------------------
    dup = [_ann(id="c1", section="FINDINGS", entity="pleural effusion",
                laterality="right", categorical="Present"),
           _ann(id="c2", section="IMPRESSION", entity="effusion",
                laterality="right", categorical="Present")]
    mark_duplicates(dup)
    assert dup[1].duplicate_of == "c1" and "also_stated_in:c2" in dup[0].flags

    # --- json mode: extraction and schema validation -------------------------
    assert extract_json('```json\n{"severity": "Mild"}\n```') == {"severity": "Mild"}
    assert extract_json('Sure! {"change": "New"} hope that helps') == {"change": "New"}
    assert validate_payload({"expressions": ["right", 3]},
                            S_EXPRESSIONS)["expressions"] == ["right"]
    ent = validate_payload({"term": "pulmonary vascular cephalization",
                            "entity_type": "imaging_finding",
                            "mention": "pulmonary vascular cephalization",
                            "other_candidates": []}, S_ENTITY)
    assert ent["term"] == "pulmonary vascular cephalization"
    assert validate_payload({"presence": "Present", "cue": "there is"},
                            S_PRESENCE)["presence"] == "Present"
    assert validate_payload({"change": "Not stated"}, S_CHANGE_CUE)["change"] \
        == "Not stated"
    for bad, schema in [({"presence": "Maybe", "cue": ""}, S_PRESENCE),
                        ({"cue": "x"}, S_PRESENCE),
                        ({"severity": "Marked"}, S_SEVERITY),
                        ({"severity": "Huge"}, S_SEVERITY),
                        ({"change": "Better"}, S_CHANGE_CUE),
                        ({"term": "x", "entity_type": "guess", "mention": "x",
                          "other_candidates": []}, S_ENTITY)]:
        try:
            validate_payload(bad, schema)
        except ValueError:
            continue
        raise AssertionError(f"invalid payload accepted: {bad}")
    for bad_text in ["", "no json here"]:
        try:
            extract_json(bad_text)
        except ValueError:
            continue
        raise AssertionError(f"non-JSON reply accepted: {bad_text!r}")

    # --- the two CSV column sets --------------------------------------------
    assert set(SLIM_DROP) < set(CSV_COLS), "SLIM_DROP names a column that is gone"
    assert SLIM_COLS == [c for c in CSV_COLS if c not in SLIM_DROP]
    assert len(SLIM_COLS) == len(CSV_COLS) - len(SLIM_DROP)
    for dropped in ("cue", "severity_ordinal", "location_positive",
                    "location_negative", "change_cue", "change_reason",
                    "other_candidates", "duplicate_of", "flags",
                    "decision_path"):
        assert dropped not in SLIM_COLS, dropped
    assert not [c for c in SLIM_COLS if c.startswith("prior")]
    assert SLIM_COLS == ["id", "section", "entity", "entity_type",
                         "known_label", "categorical", "severity",
                         "laterality", "location_expressions", "change",
                         "sentence"], SLIM_COLS
    probe = _ann(id="c1", section="Pleura", entity="pleural effusion",
                 sentence="There is a small right pleural effusion.",
                 categorical="Present", severity="Mild", laterality="right",
                 cue="there is", change="New", change_cue="New",
                 change_reason="the line states it (new)", prior_status="found",
                 location_keywords=keyword_labels("pleural effusion", ["right"]))
    full = csv_row(asdict(probe))
    slim = slim_row(full)
    assert len(full) == len(CSV_COLS) and len(slim) == len(SLIM_COLS)
    assert dict(zip(SLIM_COLS, slim)) == {c: v for c, v in zip(CSV_COLS, full)
                                          if c in SLIM_COLS}
    assert dict(zip(SLIM_COLS, slim)) == {
        "id": "c1", "section": "Pleura", "entity": "pleural effusion",
        "entity_type": "", "known_label": None, "categorical": "Present",
        "severity": "Mild", "laterality": "right",
        "location_expressions": "", "change": "New",
        "sentence": "There is a small right pleural effusion."}, \
        dict(zip(SLIM_COLS, slim))
    assert "there is" not in slim and "found" not in slim
    rec = slim_record(asdict(probe))
    assert list(rec) == SLIM_COLS, list(rec)
    assert rec == dict(zip(SLIM_COLS, slim)) or \
        all(rec[c] == v or (v == "" and not rec[c]) or
            (isinstance(rec[c], list) and ";".join(rec[c]) == v)
            for c, v in zip(SLIM_COLS, slim)), (rec, slim)
    assert isinstance(rec["location_expressions"], list), \
        "the JSON twin must keep native types"

    # --- logging round-trip --------------------------------------------------
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        lg = CallLog(td, "testrun")
        lg.record({"stage": "e0", "label": "pleural effusion", "doc": "current",
                   "status": "ok", "attempt": 1, "latency_ms": 12,
                   "prompt": "p", "response": {"term": "pleural effusion"}})
        lg.close()
        with open(lg.jsonl_path, encoding="utf-8") as fp:
            row = json.loads(fp.readline())
        assert row["seq"] == 1 and row["response"]["term"] == "pleural effusion"
        assert os.path.getsize(lg.text_path) > 0

    print("selftest OK -- ascii guard, line segmentation (headings, bullets, "
          "skipped sections), open-vocabulary entity resolution, location "
          "keyword rules (A.2.1 worked examples), 6-step severity ladder, "
          "no probability axis, prior matching, interval change (6 values), "
          "duplicate linking, full/slim csv columns, json-mode "
          "parsing/validation, api logging")


def list_models() -> None:
    """Print the model ids this API key / endpoint actually exposes."""
    if not API_KEY:
        sys.exit("API_KEY is empty. Export OPENAI_API_KEY.")
    from openai import OpenAI
    opts: Dict[str, Any] = {"api_key": API_KEY}
    if BASE_URL:
        opts["base_url"] = BASE_URL
    ids = sorted(m.id for m in OpenAI(**opts).models.list())
    for mid in ids:
        print(mid)
    print(f"\n{len(ids)} model(s) visible at "
          f"{BASE_URL or 'https://api.openai.com/v1'}")
    print(f"configured MODEL = {MODEL!r}  ->  "
          + ("listed" if MODEL in ids else "NOT in the list above"))

    # Being listed is not the same as being entitled to run it: a project can
    # see a model and still be refused at inference time. Probe for real.
    client = OpenAI(**opts)
    try:
        client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Reply with the word OK."}])
        print("live probe      ->  usable (chat.completions accepted the model)")
    except Exception as e:  # noqa: BLE001
        print(f"live probe      ->  REFUSED: {type(e).__name__}: {e}")


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()
        return
    if "--models" in sys.argv:
        list_models()
        return
    if not API_KEY:
        sys.exit("API_KEY is empty. Set it at the top of this file or export "
                 "OPENAI_API_KEY.")
    result = run(API_KEY, CURRENT_REPORT, PRIOR_REPORT)
    paths = write_output(result)
    print_table(result)
    print("saved: " + " , ".join(paths))


if __name__ == "__main__":
    main()
