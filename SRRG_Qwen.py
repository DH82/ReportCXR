#!/usr/bin/env python3
"""
SRRG.py, pointed at the local Qwen3.8-27B GGUF instead of the OpenAI API.

Everything about how a report is read, split and annotated is unchanged: this
file imports SRRG.py and maplez_struct.py and reuses them as they are. What it
replaces is the client and its defaults, which is the only part that has to
know it is talking to a llama.cpp server on this machine:

  base_url      http://localhost:8080/v1, never api.openai.com. The OpenAI
                environment variables are deliberately NOT consulted, so a
                paid key left in the shell cannot silently be billed by this
                script. Use --base-url / --model to point elsewhere.
  thinking      OFF. Qwen3.8's chat template turns thinking on by default at
                reasoning_effort "xhigh"; at five calls per bullet on four
                1080 Ti's that is the difference between a run finishing and
                a run not finishing. --thinking turns it back on.
  sampling      temperature 0, fixed seed. The GGUF ships temp=1.0/top_p=0.95
                sampling defaults, which is the wrong setting for structured
                extraction that is supposed to be reproducible.
  json mode     when the endpoint cannot return a tool call, the retry is sent
                with response_format=json_schema, so llama.cpp constrains the
                output with a grammar instead of the model being asked nicely
                to emit JSON.
  preflight     one health check, one models call and one real tool call
                before any row is processed, so a server that is down, still
                loading, or unable to do tool calling is reported in seconds
                rather than halfway through the CSV.

Start the server first (see ./Qwen/README.md):

    cd Qwen && ./run.sh -d

Usage -- the flags of SRRG.py all still work:

    python SRRG_Qwen.py --check           # test the server only, no rows
    python SRRG_Qwen.py --dry-run         # show what would be sent, no calls
    python SRRG_Qwen.py                   # annotate the first row
    python SRRG_Qwen.py --row 3
    python SRRG_Qwen.py --rows 0-9 --yes
    python SRRG_Qwen.py --limit 50 --yes --thinking low

Results land in ./out_srrg_qwen/ in the same four shapes SRRG.py writes, so
the two backends can be diffed row by row.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maplez_struct as M  # noqa: E402
import SRRG as S           # noqa: E402  -- CSV parsing, annotation, output

# =============================================================================
#  CONFIG  -- local defaults, independent of the OPENAI_* environment
# =============================================================================

BASE_URL = os.environ.get("QWEN_BASE_URL", "http://localhost:8080/v1")
MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-27b")
# llama-server ignores the key unless it was started with --api-key, but the
# OpenAI client refuses to construct without one.
API_KEY = os.environ.get("QWEN_API_KEY", "sk-local")

OUTPUT_DIR = "./out_srrg_qwen"

# A 27B model split over four 1080 Ti's answers in tens of seconds, and the
# first call also pays for the prompt cache being cold. The SDK's own retrying
# is turned off; maplez_struct.ask() already retries MAX_RETRIES times.
REQUEST_TIMEOUT = float(os.environ.get("QWEN_TIMEOUT", "900"))

# Structured extraction, not prose: greedy and reproducible.
TEMPERATURE = 0.0
TOP_P = 1.0
TOP_K = 1
SEED = 0

# A forced tool call is grammar-constrained, so the answer cannot run away.
# The cap is here to stop a broken json-mode reply from generating until the
# context is full.
MAX_TOKENS = 1024

# The server is started with --parallel 1, so one request at a time. Raise
# both together or not at all.
WORKERS = 1

# =============================================================================
#  CLIENT
# =============================================================================

def _tool_choice_for_llamacpp(choice: Any, tools: Any) -> Any:
    """OpenAI's forced-tool object -> the string llama.cpp actually accepts.

    maplez_struct asks for a specific function the OpenAI way:

        tool_choice = {"type": "function", "function": {"name": ...}}

    llama-server only parses tool_choice as a string and answers an object
    with

        Wrong type supplied for parameter 'tool_choice', using default value

    then falls back to "auto" -- which drops the grammar that forces the call,
    so the model is free to reply with prose instead. Every request in this
    pipeline carries exactly one tool, so "required" names it unambiguously.
    A request with several tools is left alone: "required" would no longer say
    which one, and silently picking the wrong one is worse than the warning.
    """
    if not isinstance(choice, dict):
        return choice
    if isinstance(tools, list) and len(tools) == 1:
        return "required"
    return choice


class QwenChat(M.OpenAIChat):
    """maplez_struct's client with the llama.cpp-specific request shape.

    Only the request is touched. Retries, logging, token accounting, schema
    validation and the tool -> json fallback are the parent's, unchanged.
    """

    def __init__(self, log: M.CallLog, *, base_url: str = BASE_URL,
                 model: str = MODEL, api_key: str = API_KEY,
                 thinking: Optional[str] = None,
                 timeout: float = REQUEST_TIMEOUT):
        super().__init__(api_key, log, model=model)
        self.base_url = base_url
        self.api_key = api_key
        self.thinking = thinking          # None -> off, else reasoning_effort
        # Rebuild the client: the parent's has no timeout and retries twice on
        # its own, which hides a stalled server behind a very long wait.
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url,
                             timeout=timeout, max_retries=0)
        # llama-server takes max_tokens; max_completion_tokens is silently
        # ignored rather than rejected, so the parent's probe never fires.
        self._token_param = "max_tokens"
        # ask() knows the schema, _create() does not. Stash it per thread.
        self._stash = threading.local()

    # -- request shaping ------------------------------------------------------

    def extra_body(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "top_k": TOP_K,
            # The system prompt is identical on every call; keeping the KV
            # cache lets the server skip re-reading it each time.
            "cache_prompt": True,
        }
        kwargs: Dict[str, Any] = {"enable_thinking": self.thinking is not None}
        if self.thinking is not None:
            kwargs["reasoning_effort"] = self.thinking
        body["chat_template_kwargs"] = kwargs
        return body

    def _create(self, **kwargs: Any) -> Any:
        kwargs.setdefault("temperature", TEMPERATURE)
        kwargs.setdefault("top_p", TOP_P)
        kwargs.setdefault("seed", SEED)
        if "tool_choice" in kwargs:
            kwargs["tool_choice"] = _tool_choice_for_llamacpp(
                kwargs["tool_choice"], kwargs.get("tools"))
        kwargs["extra_body"] = {**self.extra_body(),
                                **(kwargs.get("extra_body") or {})}

        # json mode: hand llama.cpp the schema so the reply is grammar-
        # constrained. In tool mode the forced tool call already is.
        schema = getattr(self._stash, "schema", None)
        if "tools" not in kwargs and schema is not None:
            kwargs.setdefault("response_format", {
                "type": "json_schema",
                "json_schema": {
                    "name": getattr(self._stash, "tool_name", "answer"),
                    "schema": schema,
                    "strict": True,
                },
            })
        return super()._create(**kwargs)

    def ask(self, prompt: str, schema: Dict[str, Any], tool_name: str,
            stage: str, label: str = "", doc: str = "") -> Dict[str, Any]:
        self._stash.schema = schema
        self._stash.tool_name = tool_name
        try:
            return super().ask(prompt, schema, tool_name, stage, label, doc)
        finally:
            self._stash.schema = None
            self._stash.tool_name = None

# =============================================================================
#  PREFLIGHT  -- is the server there, loaded, and able to do tool calls
# =============================================================================

# Deliberately trivial: the answer is not used, only the shape of the reply.
_PROBE_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "string", "enum": ["yes", "no"]}},
    "required": ["ok"],
}


def _server_root(base_url: str) -> str:
    """.../v1 -> ...  (llama.cpp serves /health and /props at the root)"""
    return base_url[:-3].rstrip("/") if base_url.rstrip("/").endswith("/v1") \
        else base_url.rstrip("/")


def _get_json(url: str, api_key: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def preflight(llm: QwenChat, *, verbose: bool = True) -> Dict[str, Any]:
    """Check the server and find out which response mode actually works.

    Returns {"ok", "tool_calls", "props", "latency_ms", ...}. Never raises for
    a server-side problem: main() decides what to do about it.
    """
    root = _server_root(llm.base_url)
    out: Dict[str, Any] = {"base_url": llm.base_url, "ok": False,
                           "tool_calls": False}

    def say(msg: str) -> None:
        if verbose:
            print(msg, file=sys.stderr)

    # 1. is it up, and is the model finished loading
    try:
        health = _get_json(f"{root}/health", llm.api_key)
        out["health"] = health
    except urllib.error.HTTPError as e:            # 503 while still loading
        out["error"] = f"health {e.code}: model still loading?"
        say(f"[preflight] {llm.base_url}  NOT READY -- {out['error']}")
        return out
    except Exception as e:                          # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        say(f"[preflight] {llm.base_url}  UNREACHABLE -- {out['error']}\n"
            f"            start it with:  cd Qwen && ./run.sh -d")
        return out

    # 2. what is actually loaded
    try:
        props = _get_json(f"{root}/props", llm.api_key)
        gen = props.get("default_generation_settings") or {}
        # Deliberately a short summary: /props also returns the whole chat
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
    except Exception as e:                          # noqa: BLE001
        say(f"[preflight] /props unavailable ({type(e).__name__})")

    try:
        served = [m.id for m in llm.client.models.list().data]
        out["served_models"] = served
        say(f"[preflight] serves: {', '.join(served) or '(none listed)'}")
        if served and llm.model not in served:
            say(f"[preflight] note  : --model {llm.model!r} is not in that "
                f"list; llama.cpp answers anyway, but check it is intended")
    except Exception as e:                          # noqa: BLE001
        say(f"[preflight] /v1/models failed ({type(e).__name__}: {e})")

    # 3. one real forced tool call -- the shape maplez_struct depends on
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
            tool_choice="required",          # see _tool_choice_for_llamacpp
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
    except Exception as e:                          # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        say(f"[preflight] tool call failed -- {out['error']}\n"
            f"            will use json mode with a grammar instead")
        out["ok"] = True          # the server answers; only tools are missing

    return out

# =============================================================================
#  MAIN
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="SRRG findings bullets -> maplez_struct, against the "
                    "local Qwen3.8-27B llama.cpp server.")
    # -- the SRRG.py flags, unchanged
    ap.add_argument("--csv", default=S.CSV_PATH, help=f"default: {S.CSV_PATH}")
    ap.add_argument("--row", type=int, action="append",
                    help="0-based row index; repeatable")
    ap.add_argument("--rows", help="inclusive range of row indices, e.g. 0-9")
    ap.add_argument("--id", action="append",
                    help=f"value of the {S.ID_COL!r} column; repeatable")
    ap.add_argument("--limit", type=int, help="the first N rows")
    ap.add_argument("--all", action="store_true", help="every row in the file")
    ap.add_argument("--no-history", action="store_true",
                    help="do not send history_section")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the inputs that would be sent; no calls")
    ap.add_argument("--yes", action="store_true",
                    help=f"required for more than {S.CONFIRM_ABOVE} rows")
    ap.add_argument("--out", default=OUTPUT_DIR, help=f"default: {OUTPUT_DIR}")
    # -- local serving
    g = ap.add_argument_group("local server")
    g.add_argument("--base-url", default=BASE_URL, help=f"default: {BASE_URL}")
    g.add_argument("--model", default=MODEL, help=f"default: {MODEL}")
    g.add_argument("--api-key", default=API_KEY,
                   help="only needed if llama-server was started with --api-key")
    g.add_argument("--thinking", nargs="?", const="low", default=None,
                   choices=["low", "medium", "xhigh"],
                   help="enable the model's thinking mode at this reasoning "
                        "effort (default: off; bare --thinking means low). "
                        "Slow: every bullet costs five calls.")
    g.add_argument("--mode", default="auto", choices=["auto", "tool", "json"],
                   help="how structured answers are obtained (default: auto)")
    g.add_argument("--workers", type=int, default=WORKERS,
                   help=f"parallel requests for the history block; must not "
                        f"exceed llama-server's --parallel (default: {WORKERS})")
    g.add_argument("--timeout", type=float, default=REQUEST_TIMEOUT,
                   help=f"per-request seconds (default: {REQUEST_TIMEOUT:.0f})")
    g.add_argument("--max-tokens", type=int, default=MAX_TOKENS,
                   help=f"response cap (default: {MAX_TOKENS})")
    g.add_argument("--check", action="store_true",
                   help="run the preflight only, then exit")
    g.add_argument("--no-preflight", action="store_true",
                   help="skip the preflight and start calling")
    return ap


def apply_config(args: argparse.Namespace) -> None:
    """Push the local settings into maplez_struct's module-level config.

    maplez_struct reads these at call time, so assigning them here is enough;
    the OPENAI_* environment is left untouched on purpose.
    """
    M.BASE_URL = args.base_url
    M.MODEL = args.model
    M.MAX_TOKENS = args.max_tokens
    M.MAX_WORKERS = max(1, args.workers)
    M.RESPONSE_MODE = args.mode


def main() -> None:
    args = build_parser().parse_args()
    apply_config(args)

    if args.check:
        run_id = "check-" + uuid.uuid4().hex[:6]
        log = M.CallLog(os.path.join(args.out, "logs"), run_id)
        llm = _client(args, log)
        try:
            res = preflight(llm)
        finally:
            log.close()
        sys.exit(0 if res.get("ok") else 1)

    rows = S.load_rows(args.csv)
    picked = S.select_rows(rows, args)
    print(f"{args.csv}: {len(rows)} row(s) available, {len(picked)} selected",
          file=sys.stderr)

    if args.dry_run:
        S.dry_run(picked)
        return

    if len(picked) > S.CONFIRM_ABOVE and not args.yes:
        sys.exit(f"{len(picked)} rows, each several calls per bullet, on a "
                 f"local 27B model. That is hours, not minutes. Re-run with "
                 f"--yes, or use --dry-run first.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + \
        uuid.uuid4().hex[:6]
    log = M.CallLog(os.path.join(args.out, "logs"), run_id)
    llm = _client(args, log)

    checked: Dict[str, Any] = {}
    if not args.no_preflight:
        checked = preflight(llm)
        if not checked.get("ok"):
            log.close()
            sys.exit("preflight failed; nothing was sent.")
        # Known-good answer up front beats discovering it on bullet #1.
        if not checked.get("tool_calls") and args.mode == "auto":
            llm.mode = "json"
            print("[info] starting in json mode (grammar-constrained)",
                  file=sys.stderr)

    results: List[Dict[str, Any]] = []
    t_start = time.time()
    try:
        for n, row in enumerate(picked, 1):
            rid = row.get(S.ID_COL) or "?"
            t0 = time.time()
            print(f"[{n}/{len(picked)}] {rid} ...", file=sys.stderr)
            res = S.annotate_row(llm, row, use_history=not args.no_history)
            results.append(res)
            S.print_row(res)
            dt = time.time() - t0
            done = time.time() - t_start
            eta = done / n * (len(picked) - n)
            print(f"    [{dt:.0f}s for this row, {llm.calls} call(s) so far, "
                  f"{eta / 60:.0f} min left]", file=sys.stderr)
    finally:
        calls, itok, otok = llm.calls, llm.in_tokens, llm.out_tokens
        log_paths = [log.jsonl_path, log.text_path]
        log.close()

    elapsed = time.time() - t_start
    meta = {
        "run_id": run_id, "model": args.model, "csv": args.csv,
        "rows": len(results),
        "bullets": sum(r["bullets"] for r in results),
        "findings": sum(r["findings"] for r in results),
        "history_used": not args.no_history,
        "api_calls": calls, "input_tokens": itok, "output_tokens": otok,
        "log_files": log_paths,
        # what this run actually talked to, so two runs can be compared
        "backend": {
            "base_url": args.base_url,
            "response_mode": llm.mode,
            "thinking": args.thinking or "off",
            "temperature": TEMPERATURE, "top_p": TOP_P, "top_k": TOP_K,
            "seed": SEED, "max_tokens": args.max_tokens,
            "workers": M.MAX_WORKERS,
            "server": checked.get("props"),
        },
        "elapsed_s": round(elapsed, 1),
    }
    paths = S.write_outputs(results, meta, args.out)
    rate = f"{otok / elapsed:.1f}" if elapsed > 0 else "?"
    print(f"\nrows={meta['rows']}  bullets={meta['bullets']}  "
          f"findings={meta['findings']}  calls={calls}  "
          f"in={itok}  out={otok}")
    print(f"time={elapsed / 60:.1f} min  ({rate} output tok/s, "
          f"{elapsed / max(calls, 1):.1f} s/call, mode={llm.mode})")
    print("saved: " + " , ".join(paths))
    print("logs : " + " , ".join(log_paths))


def _client(args: argparse.Namespace, log: M.CallLog) -> QwenChat:
    llm = QwenChat(log, base_url=args.base_url, model=args.model,
                   api_key=args.api_key, thinking=args.thinking,
                   timeout=args.timeout)
    return llm


if __name__ == "__main__":
    main()
