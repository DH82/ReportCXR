#!/usr/bin/env python3
"""Metric S -- is the file itself intact?

Reads the FILE, not the records: this catches a broken WRITE rather than a
broken parse, and every quality number is meaningless until it passes.

  parse          every non-empty line is JSON (a partial last line means a run
                 died mid-flush)
  keys           exactly {id, split, records}; records are FULL_RECORD's five
                 fields. An extra key is a leaked audit field.
  split field    agrees with the filename
  id uniqueness  study ids and utterance_ids
  id format      "{study}_{section_slug}_{nn}", as srrg_input.py derives it
  sections       the eight canonical headings

Streams: train.jsonl is 800 MB, so only counters and id sets are held.
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'S'
TITLE = 'File structure'
SCOPE = 'split'          # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Is the FILE intact -- parseable, no truncated last line, no duplicate "
        "ids, no audit field leaked into the shipped record?")

MEANS = """## 한 줄로

**파일 자체가 멀쩡한지만 본다.** 내용이 맞는지는 보지 않는다.

## 무슨 검사인가

다른 모든 검사는 레코드의 **내용**을 읽는다. 이것만 **파일**을 읽는다.

잡아내는 것은 "잘못 읽기"가 아니라 **"잘못 쓰기"** 다.

| 찾는 것 | 쉽게 말하면 |
|---|---|
| 잘린 마지막 줄 | 저장하다 만 파일 |
| id 중복 | 같은 번호가 두 번 |
| 파일명과 내용의 `split` 불일치 | `test.jsonl` 안에 `train` 이라 적힌 것 |
| 감사용 필드 유출 | 내부 작업 메모가 배포본에 섞여 나간 것 |

## 왜 이걸 제일 먼저 하나

**이게 깨져 있으면 뒤의 모든 숫자가 엉뚱한 파일에 대한 숫자가 된다.**

시험지 채점을 하기 전에, 답안지가 몇 장인지 먼저 세는 것과 같다. 답안지가
찢어져 있으면 채점 결과는 아무 의미가 없다.

## 읽는 법

**0 이 아니면 곧바로 `FAIL` 이고, 중간 단계가 없다.**

보통 지표에는 "조금 나쁨(WARN)" 구간이 있는데 여기에는 없다. 파일이 **"조금
깨진"** 상태나 번호가 **"조금 겹친"** 상태라는 것은 있을 수 없기 때문이다.
깨졌거나 안 깨졌거나 둘 중 하나다.
"""


import collections
import json
import re
from typing import Any, Dict, Optional

import core
from core import ONT, pct, section, split_path, table

_TOP_KEYS = {"id", "split", "records"}
_REC_KEYS = {"utterance_id", "utterance", "section", "propositions", "warnings"}
_UID = re.compile(r"^[a-z]+-[\w-]+_[a-z_]+_\d+$")


def measure(split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    studies = utterances = props = 0
    bad_json = bad_top = bad_rec = bad_split = bad_uid = 0
    empty_props = 0
    study_ids: collections.Counter = collections.Counter()
    utt_ids: collections.Counter = collections.Counter()
    sources: collections.Counter = collections.Counter()
    sections: collections.Counter = collections.Counter()
    extra_keys: collections.Counter = collections.Counter()

    with open(split_path(split), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                bad_json += 1
                continue
            studies += 1
            if set(obj) != _TOP_KEYS:
                bad_top += 1
                extra_keys.update(set(obj) - _TOP_KEYS)
            study_ids[obj.get("id")] += 1
            sources[str(obj.get("id", "")).split("-")[0]] += 1
            if obj.get("split") != split:
                bad_split += 1

            for rec in obj.get("records") or []:
                utterances += 1
                if set(rec) != _REC_KEYS:
                    bad_rec += 1
                    extra_keys.update(set(rec) - _REC_KEYS)
                uid = rec.get("utterance_id")
                utt_ids[uid] += 1
                if not uid or not _UID.match(uid):
                    bad_uid += 1
                sections[rec.get("section")] += 1
                ps = rec.get("propositions") or []
                props += len(ps)
                if not ps:
                    empty_props += 1
            if limit and studies >= limit:
                break

    return {
        "split": split,
        "studies": studies, "utterances": utterances, "propositions": props,
        "bad_json": bad_json, "bad_top_keys": bad_top, "bad_rec_keys": bad_rec,
        "bad_split_field": bad_split, "bad_uid_format": bad_uid,
        "extra_keys": extra_keys.most_common(8),
        "dup_studies": sum(v - 1 for v in study_ids.values() if v > 1),
        "dup_utterances": sum(v - 1 for v in utt_ids.values() if v > 1),
        "empty_props": empty_props,
        "sources": sources.most_common(),
        "sections": sections.most_common(),
        "noncanonical_sections": [(k, v) for k, v in sections.items()
                                  if k not in ONT.SECTIONS],
    }


def render(res: Dict[str, Any]) -> str:
    faults = (res["bad_json"] + res["bad_top_keys"] + res["bad_rec_keys"]
              + res["bad_split_field"] + res["bad_uid_format"]
              + res["dup_studies"] + res["dup_utterances"])
    body = [section(f"S  File structure  ({res['split']})"),
            table([[res["studies"], res["utterances"], res["propositions"],
                    res["empty_props"],
                    pct(res["empty_props"], res["utterances"])]],
                  ["studies", "utterances", "propositions",
                   "empty-prop utterances", "%"]),
            "",
            table([[res["bad_json"], res["bad_top_keys"], res["bad_rec_keys"],
                    res["bad_split_field"], res["bad_uid_format"],
                    res["dup_studies"], res["dup_utterances"]]],
                  ["parse fail", "top keys", "record keys", "split field",
                   "uid format", "dup study id", "dup utt id"]),
            "\n**Verdict**: " + ("file is structurally intact."
                                 if faults == 0 else
                                 f"{faults} structural fault(s) -- fix before "
                                 f"reading any quality metric.") + "\n",
            "\n**Sources**\n",
            table([[k, v, pct(v, res["studies"])] for k, v in res["sources"]],
                  ["prefix", "studies", "%"])]
    if res["extra_keys"]:
        body.append("\n**Unexpected keys** (audit fields must not ship):\n")
        body.append(table([[k, v] for k, v in res["extra_keys"]],
                          ["key", "count"]))
    if res["noncanonical_sections"]:
        body.append("\n**Non-canonical section headings**\n")
        body.append(table([[repr(k), v]
                           for k, v in sorted(res["noncanonical_sections"],
                                              key=lambda x: -x[1])],
                          ["heading", "utterances"]))
    return "\n".join(body) + "\n"


def _join(parts):
    return "\n".join(parts)


def run(cfg) -> core.Result:
    per = [measure(sp, cfg.limit) for sp in cfg.splits]
    keys = ["bad_json", "bad_top_keys", "bad_rec_keys", "bad_split_field",
            "bad_uid_format", "extra_keys", "dup_studies", "dup_utterances",
            "noncanonical_sections"]

    def n(r, k):
        v = r[k]
        return len(v) if isinstance(v, (list, dict, set)) else v

    body = core.summary(
        [[r["split"], f"{r['studies']:,}", f"{r['utterances']:,}",
          f"{r['propositions']:,}", sum(n(r, k) for k in keys)]
         for r in per],
        ["split", "studies", "utterances", "propositions", "faults"],
        "`faults` sums every hard fault this metric counts. There is no "
        "tolerance band -- a file that does not parse cannot be partly "
        "acceptable -- so any nonzero is FAIL.")
    body += _join(render(r) for r in per)

    # Every fault this metric counts is a hard one: a file that does not parse
    # or that ships a duplicate id cannot be partly acceptable, so any nonzero
    # is FAIL and there is no WARN band.
    keys = ["bad_json", "bad_top_keys", "bad_rec_keys", "bad_split_field",
            "bad_uid_format", "extra_keys", "dup_studies", "dup_utterances",
            "noncanonical_sections"]
    faults = {k: sum(len(r[k]) if isinstance(r[k], (list, dict, set)) else r[k]
                     for r in per) for k in keys}
    bad = {k: v for k, v in faults.items() if v}
    verdict = core.FAIL if bad else core.PASS
    head = ("clean: " + ", ".join(f"{sum(r[k] for r in per):,} {k}"
                                  for k in ("studies", "utterances", "propositions"))
            if not bad else
            "; ".join(f"{v:,} {k}" for k, v in sorted(bad.items())))
    return core.Result(body, verdict, head, faults)


if __name__ == "__main__":
    import sys
    print(render(measure(sys.argv[1] if len(sys.argv) > 1 else "test")))
