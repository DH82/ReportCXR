#!/usr/bin/env python3
"""
cxr_prompt.py 를 로컬 Qwen 서버에 던지고 결과를 받는 실행기.

cxr_prompt.py 가 프롬프트 전부이고, 이 파일이 그것을 쓰는 전부다.
정규화도 검증도 하지 않는다 -- 모델이 답한 그대로 낸다. 그 두 단계가
필요하면 parse_utterances.py 쪽을 쓸 것.

서버부터:

    cd Qwen && ./run.sh -d

쓰는 법:

    python cxr_run.py --show                       # 보낼 프롬프트만 출력, 호출 없음
    python cxr_run.py --check                      # 서버 확인
    python cxr_run.py "There is no pleural effusion." --section Pleura
    python cxr_run.py --jsonl utterances.jsonl -o out.json
    echo "No pneumothorax" | python cxr_run.py -

입력 형식 (--jsonl): 한 줄에 객체 하나.

    {"utterance_id": "10_pleura_01", "utterance": "...", "section": "Pleura"}

출력: Section 2 레코드의 JSON 배열. utterance_id / utterance / section 은
모델이 아니라 입력에서 다시 붙인다 -- 원문이 모델의 오타로 바뀌면 안 된다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

from cxr_prompt import TOOL_NAME, TOOL_SCHEMA, build

# -- 서버 -----------------------------------------------------------------
# OPENAI_* 는 일부러 읽지 않는다. 쉘에 남은 유료 키로 과금될 수 없게.
BASE_URL = os.environ.get("QWEN_BASE_URL", "http://localhost:8080/v1")
MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-27b")
API_KEY = os.environ.get("QWEN_API_KEY", "sk-local")
TIMEOUT = float(os.environ.get("QWEN_TIMEOUT", "900"))

# -- 샘플링 ---------------------------------------------------------------
# 구조화 추출이다. 샘플러를 변수에서 제거한다.
TEMPERATURE = 0.0
TOP_P = 1.0
TOP_K = 1
SEED = 0
# 중첩 레코드 전체가 한 번에 나온다. 잘린 응답은 부분 답이 아니라 파싱 불가
# 응답이므로, 짧게 잡느니 넉넉히 잡는다.
MAX_TOKENS = 2048
MAX_RETRIES = 3


def client():
    from openai import OpenAI
    return OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=TIMEOUT,
                  max_retries=0)


def extract_json(text):
    """tool call 이 안 왔을 때, 응답 본문에서 JSON 객체를 긁어낸다."""
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip()).strip()
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j <= i:
        raise ValueError(f"응답에 JSON 객체가 없다: {t[:160]!r}")
    return json.loads(t[i:j + 1])


def ask(cli, prompt):
    """프롬프트 하나 -> {"propositions": [...], "warnings": [...]}"""
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            msg = cli.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": "function",
                        "function": {"name": TOOL_NAME,
                                     "description": "Return the propositions "
                                                    "this utterance states.",
                                     "parameters": TOOL_SCHEMA}}],
                # 문자열이어야 한다. 객체 형태는 llama-server 가 "auto" 로
                # 떨어뜨려 호출 강제 문법이 사라진다.
                tool_choice="required",
                temperature=TEMPERATURE, top_p=TOP_P, seed=SEED,
                max_tokens=MAX_TOKENS,
                extra_body={"top_k": TOP_K, "cache_prompt": True,
                            "chat_template_kwargs": {"enable_thinking": False}},
            )
            choice = msg.choices[0]
            if choice.finish_reason == "length":
                raise ValueError(f"응답이 max_tokens({MAX_TOKENS})에서 잘렸다")

            payload = None
            for tc in choice.message.tool_calls or []:
                if tc.function.name == TOOL_NAME:
                    payload = json.loads(tc.function.arguments or "{}")
                    break
            if payload is None:
                payload = extract_json(choice.message.content)

            usage = getattr(msg, "usage", None)
            return payload, (getattr(usage, "prompt_tokens", 0) or 0,
                             getattr(usage, "completion_tokens", 0) or 0)
        except Exception as e:                            # noqa: BLE001
            last = e
            if getattr(e, "status_code", None) in (401, 403, 404):
                raise SystemExit(
                    f"서버가 요청을 거부했다: {e}\n"
                    f"  model    = {MODEL!r}\n"
                    f"  base_url = {BASE_URL}\n"
                    f"  서버가 떠 있나?  cd Qwen && ./run.sh -d")
            time.sleep(1.5 * attempt)
    raise SystemExit(f"{MAX_RETRIES}번 시도했지만 답을 못 받았다: {last}")


def parse_one(cli, item):
    """발화 하나 -> Section 2 레코드 하나."""
    payload, tok = ask(cli, build(item["utterance"], item.get("section"),
                                  item.get("utterance_id")))
    props = payload.get("propositions")
    warns = payload.get("warnings")
    return {
        # 입력에서 다시 붙인다. 모델이 되돌려 준 값을 믿지 않는다.
        "utterance_id": item.get("utterance_id"),
        "utterance": item["utterance"],
        "section": item.get("section"),
        "propositions": props if isinstance(props, list) else [],
        "warnings": warns if isinstance(warns, list) else [],
    }, tok


def check():
    """서버가 떠 있고, 모델이 로딩됐고, tool call 을 할 수 있는가."""
    root = BASE_URL[:-3].rstrip("/") if BASE_URL.rstrip("/").endswith("/v1") \
        else BASE_URL.rstrip("/")
    try:
        req = urllib.request.Request(
            f"{root}/props", headers={"Authorization": f"Bearer {API_KEY}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            props = json.loads(r.read().decode())
        print(f"model : {os.path.basename(str(props.get('model_path','?')))}"
              f"  ({props.get('build_info','?')})")
    except Exception as e:                                # noqa: BLE001
        raise SystemExit(f"서버에 닿지 않는다 ({type(e).__name__}: {e})\n"
                         f"  cd Qwen && ./run.sh -d")

    t0 = time.time()
    payload, tok = ask(client(), build("There is no pleural effusion.",
                                       section="Pleura"))
    n = len(payload.get("propositions") or [])
    print(f"tool call OK  ({time.time()-t0:.1f}s, in {tok[0]} / out {tok[1]}, "
          f"명제 {n}개)")


def load(args):
    """--jsonl / 위치 인자 / stdin -> 발화 목록."""
    if args.jsonl:
        out = []
        with open(args.jsonl, encoding="utf-8") as fp:
            for n, line in enumerate(fp, 1):
                if not line.strip():
                    continue
                obj = json.loads(line)
                if "utterance" not in obj:
                    raise SystemExit(f"{args.jsonl}:{n}: 'utterance' 키가 없다")
                out.append(obj)
        return out
    if args.utterance == "-":
        return [{"utterance": l.strip(), "section": args.section,
                 "utterance_id": f"stdin_{i:02d}"}
                for i, l in enumerate(sys.stdin, 1) if l.strip()]
    if args.utterance:
        return [{"utterance": args.utterance, "section": args.section,
                 "utterance_id": args.id}]
    raise SystemExit("발화를 주거나 --jsonl 을 쓸 것. 도움말은 -h")


def main():
    ap = argparse.ArgumentParser(
        description="cxr_prompt.py 의 프롬프트로 발화를 파싱한다.")
    ap.add_argument("utterance", nargs="?", help='발화. "-" 면 stdin 한 줄씩')
    ap.add_argument("--section", help="SRRG 섹션 헤딩 (예: Pleura)")
    ap.add_argument("--id", help="utterance_id")
    ap.add_argument("--jsonl", help="한 줄에 객체 하나인 입력 파일")
    ap.add_argument("-o", "--out", help="결과를 쓸 JSON 파일 (기본: stdout)")
    ap.add_argument("--show", action="store_true",
                    help="보낼 프롬프트만 출력하고 끝낸다. 호출 없음")
    ap.add_argument("--check", action="store_true", help="서버 확인만")
    args = ap.parse_args()

    if args.check:
        check()
        return

    items = load(args)

    if args.show:
        for it in items:
            print(build(it["utterance"], it.get("section"),
                        it.get("utterance_id")))
            print("\n" + "=" * 78 + "\n")
        print(f"{len(items)}개 발화. 호출하지 않았다.", file=sys.stderr)
        return

    cli = client()
    records, t_in, t_out = [], 0, 0
    t0 = time.time()
    for n, item in enumerate(items, 1):
        print(f"[{n}/{len(items)}] {item.get('utterance_id') or item['utterance'][:40]}",
              file=sys.stderr)
        rec, tok = parse_one(cli, item)
        records.append(rec)
        t_in += tok[0]
        t_out += tok[1]

    text = json.dumps(records, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fp:
            fp.write(text + "\n")
        print(f"saved: {args.out}", file=sys.stderr)
    else:
        print(text)

    props = sum(len(r["propositions"]) for r in records)
    print(f"발화 {len(records)} · 명제 {props} · in {t_in} / out {t_out} · "
          f"{time.time()-t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
