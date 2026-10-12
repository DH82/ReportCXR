#!/usr/bin/env python3
"""같은 입력을 여러 번 물었을 때 판정이 얼마나 흔들리는가.

이 모델은 `temperature` 를 받지 않아 기본값 1 로만 돌아간다. 즉 같은 리포트를
두 번 물으면 두 번 다른 답이 올 수 있고, 실제로 그랬다 -- 프롬프트를 고친
뒤 사라진 지적 중 하나(`entity.text` 에 서술 구절이 섞인 건)는 어떤 수정도
겨냥하지 않은 것이었다.

그래서 233개를 돌리기 전에 이것부터 잰다. 분산을 모르면 결과 목록이
"이 파일의 결함"인지 "그날 뽑힌 제비"인지 구분할 수 없고, 그 둘은 쓰임새가
완전히 다르다.

    python3 GPT/stability.py out/gpt_records/by_report_{1,2,3}

판정 단위는 (utterance_id, verdict, field) 다. 같은 결함을 두 실행이
다른 문장으로 설명하는 것은 흔들림이 아니고, 한 실행만 제기한 것은 흔들림이다.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def load_run(d: str) -> dict:
    """한 실행 -> {utterance_id: (status, {(verdict, field), ...})}"""
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        for u in json.load(open(f, encoding="utf-8"))["utterances"]:
            out[u["utterance_id"]] = (
                u["status"],
                {(i["verdict"], i["field"]) for i in u["issues"]},
                u.get("claims_read_from_sentence", []),
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+")
    a = ap.parse_args()
    runs = [load_run(d) for d in a.dirs]
    k = len(runs)
    uids = sorted(set().union(*[set(r) for r in runs]))

    # -- 발화 단위 status
    st = collections.Counter()
    unstable = []
    for u in uids:
        vals = [r[u][0] if u in r else "missing" for r in runs]
        c = collections.Counter(vals)
        top, n = c.most_common(1)[0]
        st[f"{n}/{k} 일치"] += 1
        if n < k:
            unstable.append((u, vals))

    # -- 지적 단위
    seen = collections.Counter()
    for r in runs:
        for u, (_, iss, _) in r.items():
            for i in iss:
                seen[(u, i)] += 1
    dist = collections.Counter(seen.values())
    total = len(seen)

    print(f"실행 {k}회 · 발화 {len(uids)}건 · 서로 다른 지적 {total}종\n")
    print("발화 status 일치:")
    for key in sorted(st, reverse=True):
        print(f"  {key}   {st[key]}")
    print("\n지적이 몇 번 등장했나:")
    for n in range(k, 0, -1):
        share = dist[n] / total if total else 0
        tag = "  ← 모든 실행에서 나옴 (안정)" if n == k else (
              "  ← 한 실행에서만 나옴 (불안정)" if n == 1 else "")
        print(f"  {n}/{k} 회   {dist[n]:>3}  ({share:5.1%}){tag}")
    if total:
        print(f"\n안정 비율 {dist[k]}/{total} = {dist[k]/total:.0%}")

    if unstable:
        print("\nstatus 가 갈린 발화:")
        for u, vals in unstable:
            print(f"  {u}\n      {' | '.join(vals)}")

    print("\n지적별:")
    for (u, i), n in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0][0])):
        mark = "안정" if n == k else ("흔들림" if n == 1 else "부분")
        print(f"  [{n}/{k}] {mark:<4} {u[:40]:<40} {i[0]}/{i[1]}")

    # -- claims 는 판정이 아니라 읽기다. 여기가 흔들리면 원인이 더 깊다.
    print("\nclaims 개수 (발화별, 실행순):")
    for u in uids:
        ns = [len(r[u][2]) if u in r else -1 for r in runs]
        if len(set(ns)) > 1:
            print(f"  {u[:44]:<44} {ns}  ← 읽기 자체가 갈림")
    print("  (출력이 없으면 세 실행이 문장에서 같은 개수를 읽었다는 뜻)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
