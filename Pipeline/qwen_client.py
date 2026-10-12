#!/usr/bin/env python3
"""Section 8, step 1 -- LLM extraction. The only file that talks to the server.

    base_url  http://localhost:8080/v1   model  qwen3.8-27b   (see ../Serving)

OPENAI_* is deliberately NOT consulted, so a paid key left in the shell cannot
be billed here; point elsewhere with --base-url / --model.

    temperature 0, top_p 1, top_k 1, seed 0
        Pinned for structured extraction, but NOT a guarantee: llama.cpp
        reduces over four cards and reuses a KV cache, neither of which is
        bit-reproducible. What makes two runs comparable is step 2 folding the
        wording into one label -- a label that drifts is a gap in the ontology.
    thinking OFF        one call per utterance is the budget (--thinking re-enables)
    max_tokens 2048     one call returns a whole nested record; a truncated
                        reply is unparseable, not partial
    tool mode           a forced call to return_propositions, so the schema is
                        compiled into a grammar. Falls back to json_schema, then
                        free-form JSON.
    cache_prompt        the system prompt is byte-identical every call

    python qwen_client.py --check        # preflight only, no parsing
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                     # sibling modules
sys.path.insert(0, os.path.dirname(_HERE))    # prompt packages at the repo root
# Which prompt package to use; v1 by default, switched by the env var.
#
#     REPORTCXR_PROMPT=Prompt2 python3 parse_utterances.py --jsonl subset.jsonl
#
# The schema and tool name ALWAYS come from Prompt2, whichever prompt is used:
# one output shape, or the jsonl becomes two kinds of file. Prompt2 because it
# owns the vocabulary -- Prompt's zone enum has no E2 vessel segments, and the
# grammar would then forbid the zone=mid that v2 emits.
_PROMPT_PKG = os.environ.get("REPORTCXR_PROMPT", "Prompt")

from Prompt2 import PROPOSITIONS, TOOL_NAME                # noqa: E402

# Resolve the chosen package once and re-export it, so the tools that display
# the prompt (--dump-prompt, --self-check, --dry-run) cannot drift from what is sent.
import importlib                                           # noqa: E402
PROMPT = importlib.import_module(_PROMPT_PKG)
SYSTEM_PROMPT, render, selected = (PROMPT.SYSTEM_PROMPT, PROMPT.render,
                                   PROMPT.selected)
if _PROMPT_PKG != "Prompt":
    print(f"[info] prompt package: {_PROMPT_PKG}", file=sys.stderr)

# =============================================================================
#  CONFIG
# =============================================================================

BASE_URL = os.environ.get("QWEN_BASE_URL", "http://localhost:8080/v1")
MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-27b")
# llama-server ignores the key unless started with --api-key, but the OpenAI
# client refuses to construct without one.
API_KEY = os.environ.get("QWEN_API_KEY", "sk-local")

REQUEST_TIMEOUT = float(os.environ.get("QWEN_TIMEOUT", "900"))

TEMPERATURE = 0.0
TOP_P = 1.0
TOP_K = 1
SEED = 0
MAX_TOKENS = 2048

# The server runs --parallel 1. Raise both together or not at all.
WORKERS = 1
MAX_RETRIES = 3

# =============================================================================
#  LOGGING
# =============================================================================

class CallLog:
    """Every request and reply, to JSONL and to a log a human can read.

    The JSONL is the record the run is reproducible from: prompt, response,
    which examples were selected, token counts, latency, and which attempt
    finally answered.
    """

    def __init__(self, log_dir: str, run_id: str):
        os.makedirs(log_dir, exist_ok=True)
        self.run_id = run_id
        self.jsonl_path = os.path.join(log_dir, f"api_calls_{run_id}.jsonl")
        self.text_path = os.path.join(log_dir, f"api_calls_{run_id}.log")
        self.n = 0
        self._lock = threading.Lock()
        self._jsonl = open(self.jsonl_path, "a", encoding="utf-8")
        self._text = open(self.text_path, "a", encoding="utf-8")

    def record(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            self.n += 1
            entry = {"seq": self.n, "run_id": self.run_id,
                     "ts": datetime.now(timezone.utc).isoformat(), **entry}
            self._jsonl.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._jsonl.flush()

            self._text.write(
                f"[{entry['seq']:04d}] {entry['ts']}  "
                f"utterance_id={entry.get('utterance_id')}  "
                f"status={entry.get('status')}  attempt={entry.get('attempt')}  "
                f"mode={entry.get('mode')}  "
                f"examples={','.join(entry.get('examples') or [])}  "
                f"latency_ms={entry.get('latency_ms')}\n")
            self._text.write("--- prompt ---\n"
                             + str(entry.get("prompt", "")) + "\n")
            self._text.write("--- response ---\n"
                             + json.dumps(entry.get("response"),
                                          ensure_ascii=False) + "\n")
            if entry.get("error"):
                self._text.write("--- error ---\n" + str(entry["error"]) + "\n")
            self._text.write("=" * 78 + "\n")
            self._text.flush()

    def close(self) -> None:
        self._jsonl.close()
        self._text.close()

# =============================================================================
#  REPLY HANDLING
# =============================================================================

def extract_json(text: str) -> Dict[str, Any]:
    """Pull a JSON object out of a plain-text reply (json mode fallback)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1 or j < i:
        raise ValueError(f"no JSON object in model reply: {t[:160]!r}")
    return json.loads(t[i:j + 1])


def check_shape(payload: Any) -> Dict[str, Any]:
    """Is this the object Prompt/schema.PROPOSITIONS describes?

    Only the shape is checked here -- keys present, types right, ids unique.
    Whether the CONTENT obeys the rules is validate.py's job, and it must run
    on a record that at least parses. Missing "warnings" is tolerated and
    filled in: the model dropping an empty array is not worth a retry.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"expected an object, got {type(payload).__name__}")
    props = payload.get("propositions")
    if not isinstance(props, list):
        raise ValueError("'propositions' missing or not a list")

    seen = set()
    for i, p in enumerate(props):
        if not isinstance(p, dict):
            raise ValueError(f"proposition[{i}] is not an object")
        for key in ("entity", "assertion", "comparison"):
            if not isinstance(p.get(key), dict):
                raise ValueError(f"proposition[{i}] has no {key!r} object")
        if not isinstance(p["entity"].get("text"), str):
            raise ValueError(f"proposition[{i}].entity.text is not a string")
        pid = p.get("id") or f"p{i + 1}"
        if pid in seen:
            raise ValueError(f"duplicate proposition id {pid!r}")
        seen.add(pid)
        p["id"] = pid
        for key, default in (("anatomy", []), ("descriptors", [])):
            if not isinstance(p.get(key), list):
                p[key] = default
        p.setdefault("derived_from", None)

    warns = payload.get("warnings")
    payload["warnings"] = [w for w in warns if isinstance(w, str)] \
        if isinstance(warns, list) else []
    payload["propositions"] = props
    return payload


JSON_INSTRUCTION = ("\n\nReturn a single JSON object matching this schema, "
                    "with no prose and no code fences: {schema}")

_TOOL_UNSUPPORTED = ("tool", "function", "tool_choice")

# =============================================================================
#  CLIENT
# =============================================================================

class Qwen:
    """One call per utterance, against the local llama.cpp server.

    Three ways of getting a structured answer, tried in this order:

      tool    forced call to return_propositions; llama.cpp turns the schema
              into a grammar, so the reply cannot leave the answer space.
      json    response_format=json_schema -- the same grammar, reached
              without tool calling. Used when the server has no tool support.
      (retry) whatever came back is scraped for a JSON object.

    mode="auto" starts in tool mode and switches for the rest of the run the
    first time the endpoint refuses tools, because it will refuse every time.
    """

    def __init__(self, log: CallLog, *, base_url: str = BASE_URL,
                 model: str = MODEL, api_key: str = API_KEY,
                 thinking: Optional[str] = None,
                 timeout: float = REQUEST_TIMEOUT,
                 max_tokens: int = MAX_TOKENS,
                 mode: str = "auto",
                 max_examples: int = 4):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url,
                             timeout=timeout, max_retries=0)
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.thinking = thinking          # None -> off, else reasoning_effort
        self.max_tokens = max_tokens
        self.max_examples = max_examples
        self.log = log
        self.mode = "json" if mode == "json" else "tool"
        self.auto = mode == "auto"
        self.calls = 0
        self.in_tokens = 0
        self.out_tokens = 0
        self._lock = threading.Lock()

    # -- request shaping ------------------------------------------------------

    def extra_body(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"enable_thinking": self.thinking is not None}
        if self.thinking is not None:
            kwargs["reasoning_effort"] = self.thinking
        return {"top_k": TOP_K, "cache_prompt": True,
                "chat_template_kwargs": kwargs}

    def _fall_back_to_json(self, why: str) -> None:
        with self._lock:
            if self.mode != "json":
                self.mode = "json"
                print(f"[info] switching to json mode ({why})", file=sys.stderr)

    def _messages(self, user: str) -> List[Dict[str, str]]:
        return [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user}]

    def _create(self, **kwargs: Any) -> Any:
        # llama-server takes max_tokens; max_completion_tokens is silently
        # ignored rather than rejected, which is worse than being rejected.
        kwargs.setdefault("model", self.model)
        kwargs.setdefault("temperature", TEMPERATURE)
        kwargs.setdefault("top_p", TOP_P)
        kwargs.setdefault("seed", SEED)
        kwargs.setdefault("max_tokens", self.max_tokens)
        kwargs["extra_body"] = {**self.extra_body(),
                                **(kwargs.get("extra_body") or {})}
        return self.client.chat.completions.create(**kwargs)

    # -- one utterance --------------------------------------------------------

    def build_prompt(self, utterance_id: Optional[str], utterance: str,
                     section: Optional[str]) -> Dict[str, Any]:
        """The user message and which examples went into it. No call is made."""
        examples = selected(utterance, self.max_examples)
        return {
            "prompt": render(utterance_id, utterance, section, examples),
            "examples": [e["name"] for e in examples],
        }

    def parse(self, utterance_id: Optional[str], utterance: str,
              section: Optional[str]) -> Dict[str, Any]:
        """Section 8 step 1: one utterance in, propositions + warnings out.

        Raises RuntimeError when the server never produced a parseable reply.
        The caller decides whether that kills the run or marks one row.
        """
        built = self.build_prompt(utterance_id, utterance, section)
        prompt, names = built["prompt"], built["examples"]
        last_err: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            mode = self.mode
            t0 = time.time()
            try:
                if mode == "tool":
                    msg = self._create(
                        messages=self._messages(prompt),
                        tools=[{"type": "function",
                                "function": {
                                    "name": TOOL_NAME,
                                    "description": "Return the propositions "
                                                   "this utterance states.",
                                    "parameters": PROPOSITIONS}}],
                        # llama-server parses tool_choice only as a string and
                        # falls back to "auto" for the OpenAI object form,
                        # which drops the grammar that forces the call. One
                        # tool is sent, so "required" names it unambiguously.
                        tool_choice="required",
                    )
                else:
                    msg = self._create(
                        messages=self._messages(
                            prompt + JSON_INSTRUCTION.format(
                                schema=json.dumps(PROPOSITIONS))),
                        response_format={
                            "type": "json_schema",
                            "json_schema": {"name": TOOL_NAME,
                                            "schema": PROPOSITIONS,
                                            "strict": True}},
                    )
                dt = int((time.time() - t0) * 1000)

                choice = msg.choices[0]
                content = choice.message.content
                calls = list(choice.message.tool_calls or [])
                payload = None
                if mode == "tool":
                    for tc in calls:
                        if tc.function.name == TOOL_NAME:
                            payload = json.loads(tc.function.arguments or "{}")
                            break
                    if payload is None and content:
                        # Grammar-constrained servers occasionally answer with
                        # the object as content. It is still the right object.
                        payload = extract_json(content)
                else:
                    payload = extract_json(content)
                if payload is not None:
                    payload = check_shape(payload)

                self.calls += 1
                usage = getattr(msg, "usage", None)
                in_tok = getattr(usage, "prompt_tokens", 0) or 0
                out_tok = getattr(usage, "completion_tokens", 0) or 0
                self.in_tokens += in_tok
                self.out_tokens += out_tok
                self.log.record({
                    "utterance_id": utterance_id, "section": section,
                    "utterance": utterance,
                    "status": "ok" if payload is not None else "no_tool_call",
                    "attempt": attempt, "latency_ms": dt, "mode": mode,
                    "model": self.model, "examples": names,
                    "prompt": prompt, "response": payload,
                    "content": content,
                    "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
                    "stop_reason": choice.finish_reason,
                })
                if choice.finish_reason == "length":
                    # A truncated nested record is not a partial answer.
                    raise ValueError(
                        f"reply hit max_tokens ({self.max_tokens}); raise it "
                        f"with --max-tokens")
                if payload is None:
                    if self.auto:
                        self._fall_back_to_json("model returned no tool call")
                    raise ValueError("no tool call returned")
                return payload

            except Exception as e:                     # noqa: BLE001
                last_err = e
                self.log.record({
                    "utterance_id": utterance_id, "section": section,
                    "utterance": utterance, "status": "error",
                    "attempt": attempt, "mode": mode, "model": self.model,
                    "examples": names, "prompt": prompt, "response": None,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "error": f"{type(e).__name__}: {e}",
                })
                status = getattr(e, "status_code", None)
                text = str(e).lower()
                if (mode == "tool" and self.auto and status in (400, 404)
                        and any(w in text for w in _TOOL_UNSUPPORTED)):
                    self._fall_back_to_json("endpoint rejected tool calling")
                    continue                       # retry now, in json mode
                if status in (401, 403, 404):
                    raise RuntimeError(
                        f"server rejected the request: {e}\n"
                        f"  model    = {self.model!r}\n"
                        f"  base_url = {self.base_url}\n"
                        f"  is llama-server up?  cd Qwen && "
                        f"./run.sh -d") from e
                time.sleep(1.5 * attempt)

        raise RuntimeError(f"no parseable reply after {MAX_RETRIES} attempts "
                           f"({utterance_id}): {last_err}")

# =============================================================================
#  PREFLIGHT
# =============================================================================

_PROBE_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "string", "enum": ["yes", "no"]}},
    "required": ["ok"],
}


def _server_root(base_url: str) -> str:
    """.../v1 -> ...   (llama.cpp serves /health and /props at the root)"""
    return base_url[:-3].rstrip("/") if base_url.rstrip("/").endswith("/v1") \
        else base_url.rstrip("/")


def _get_json(url: str, api_key: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def preflight(llm: Qwen, *, verbose: bool = True) -> Dict[str, Any]:
    """Health, /props, /v1/models and one real tool call, before any row.

    A server that is down, still loading a 30GB GGUF onto four cards, or
    built without --jinja should be reported in seconds, not halfway through
    the file. Never raises for a server-side problem: the caller decides.
    """
    root = _server_root(llm.base_url)
    out: Dict[str, Any] = {"base_url": llm.base_url, "ok": False,
                           "tool_calls": False}

    def say(msg: str) -> None:
        if verbose:
            print(msg, file=sys.stderr)

    try:
        out["health"] = _get_json(f"{root}/health", llm.api_key)
    except urllib.error.HTTPError as e:              # 503 while loading
        out["error"] = f"health {e.code}: model still loading?"
        say(f"[preflight] {llm.base_url}  NOT READY -- {out['error']}")
        return out
    except Exception as e:                            # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        say(f"[preflight] {llm.base_url}  UNREACHABLE -- {out['error']}\n"
            f"            start it with:  cd Qwen && ./run.sh -d")
        return out

    try:
        props = _get_json(f"{root}/props", llm.api_key)
        gen = props.get("default_generation_settings") or {}
        # A short summary on purpose: /props also returns the whole chat
        # template, which has no business being copied into every meta block.
        out["props"] = {
            "model_path": props.get("model_path"),
            "model_alias": props.get("model_alias"),
            "n_ctx": gen.get("n_ctx", props.get("n_ctx")),
            "build_info": props.get("build_info"),
            "total_slots": props.get("total_slots"),
        }
        say(f"[preflight] model : "
            f"{os.path.basename(str(props.get('model_path', '?')))}"
            f"   ({props.get('build_info', '?')})")
        say(f"[preflight] n_ctx : {out['props']['n_ctx'] or '?'}"
            f"   slots: {props.get('total_slots', '?')}")
    except Exception as e:                            # noqa: BLE001
        say(f"[preflight] /props unavailable ({type(e).__name__})")

    try:
        served = [m.id for m in llm.client.models.list().data]
        out["served_models"] = served
        say(f"[preflight] serves: {', '.join(served) or '(none listed)'}")
        if served and llm.model not in served:
            say(f"[preflight] note  : --model {llm.model!r} is not in that "
                f"list; llama.cpp answers anyway, but check it is intended")
    except Exception as e:                            # noqa: BLE001
        say(f"[preflight] /v1/models failed ({type(e).__name__}: {e})")

    t0 = time.time()
    try:
        msg = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user",
                       "content": "Answer yes by calling the tool."}],
            tools=[{"type": "function",
                    "function": {"name": "probe",
                                 "description": "Return the answer.",
                                 "parameters": _PROBE_SCHEMA}}],
            tool_choice="required",
            temperature=TEMPERATURE, top_p=TOP_P, seed=SEED, max_tokens=64,
            extra_body=llm.extra_body(),
        )
        dt = int((time.time() - t0) * 1000)
        out["latency_ms"] = dt
        calls = list(msg.choices[0].message.tool_calls or [])
        out["tool_calls"] = bool(calls)
        usage = getattr(msg, "usage", None)
        out["probe_tokens"] = getattr(usage, "completion_tokens", 0) or 0
        out["ok"] = True
        if calls:
            say(f"[preflight] tool calling OK ({dt} ms, "
                f"{out['probe_tokens']} output tokens)")
        else:
            say(f"[preflight] tool calling returned no tool_call ({dt} ms) "
                f"-- will use json mode with a grammar instead")
    except Exception as e:                            # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        say(f"[preflight] tool call failed -- {out['error']}\n"
            f"            will use json mode with a grammar instead")
        out["ok"] = True          # the server answers; only tools are missing

    return out


def backend_meta(llm: Qwen, checked: Dict[str, Any],
                 thinking: Optional[str]) -> Dict[str, Any]:
    """What this run actually talked to, for the meta block of the output."""
    return {
        "base_url": llm.base_url,
        "model": llm.model,
        "response_mode": llm.mode,
        "thinking": thinking or "off",
        "temperature": TEMPERATURE, "top_p": TOP_P, "top_k": TOP_K,
        "seed": SEED, "max_tokens": llm.max_tokens,
        "workers": WORKERS,
        "server": checked.get("props"),
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Check the local Qwen server.")
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--api-key", default=API_KEY)
    ap.add_argument("--check", action="store_true", help="(default)")
    args = ap.parse_args()

    log = CallLog("./out_parse/logs", "check")
    try:
        llm = Qwen(log, base_url=args.base_url, model=args.model,
                   api_key=args.api_key)
        res = preflight(llm)
    finally:
        log.close()
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
