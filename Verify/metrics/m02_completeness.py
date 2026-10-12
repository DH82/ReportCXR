#!/usr/bin/env python3
"""Metric C -- did every input reach the output?

The only check that reads the INPUT side (the SRRG findings CSV). Everything
else reads the records that ARE in the file, so a study whose call failed or a
bullet the sectionizer dropped leaves no trace: the file stays valid and
quietly short.

Three comparisons, increasingly strict:

  study set        ids in the CSV vs ids in the jsonl
  utterance count  per study
  utterance text   position by position -- silent rewriting voids rule 3's
                   span guarantee, which validate.py cannot see because it
                   checks spans against the record, not the report

Memory: text is compared through one md5 per study, not by holding the corpus.
"""


from __future__ import annotations

# Metric modules run standalone and through run.py.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# -- run.py contract ---------------------------------------------------
SECTION = 'C'
TITLE = 'Completeness vs source'
SCOPE = 'split'          # 'split' = per split, 'corpus' = whole corpus
ASKS = ("Did every utterance in the source CSV survive into the jsonl, "
        "character for character? The failure mode is silent loss.")

MEANS = """## 한 줄로

**원본에 있던 문장이 JSON 에 글자 그대로 다 있는지 센다.**

## 왜 이 검사가 필요한가

AI 로 데이터를 만들 때 가장 흔하고 가장 무서운 실패는 **틀리게 만드는 것이
아니라 조용히 몇 건을 흘리는 것**이다.

처리 중에 한 번 시간이 초과되거나 한 번 형식이 깨지면 그 환자 한 명이 통째로
사라진다. 그런데 **결과 파일은 여전히 멀쩡해 보인다.** 111만 문장 중 50 문장이
없어진 걸 눈으로 알아챌 방법은 없다.

## 어떻게 확인하나

원본 CSV 와 만들어진 JSON 을 네 가지로 맞대 본다.

| 확인 | 묻는 것 |
|---|---|
| 환자 번호 | 원본에 있는 검사가 JSON 에도 다 있나 |
| 문장 번호 | 문장 하나하나가 다 있나 |
| 개수 | 환자마다 문장 수가 같나 |
| 글자 | 문장 내용이 **한 글자도 안 바뀌었나** |

## 통과하면 무엇이 증명되나

**"1단계 추출이 원문을 잃거나 바꾸지 않았다"** 가 증명된다. 이게 이 프로젝트의
가장 기본 전제다.

> **단, 뽑은 내용이 옳다는 뜻은 한 마디도 아니다.** 문장을 다 갖고 있다는 것과
> 그 문장을 제대로 이해했다는 것은 전혀 다른 얘기다. 후자는 뒤의 검사들이 묻는다.

## 못 돌 때

원본 CSV 가 있는 디렉터리를 못 찾으면 이 검사만 `SKIP` 이 되고 나머지는 정상으로
나온다.
"""


import csv
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import core
from core import pct, section, split_path, table

csv.field_size_limit(10 ** 9)

DEFAULT_SOURCE_DIR = "/data3/CXR/SRRG/srrg_findings_csv"

_WS = re.compile(r"\s+")


def bullets(block: Optional[str]) -> List[str]:
    """findings_section -> the utterances, in order, as srrg_input reads them.

    Two shapes that a naive "- " scan gets wrong, both observed in
    test_reviewed.csv and both cases where the pipeline is right and the naive
    reader is wrong:

      bullet-colon a bullet whose own text ends in a colon. Test for the
                  "- " prefix BEFORE testing for a heading, or the bullet is
                  read as a heading and dropped -- 29 studies in train.
      preamble    a report may open with a sentence before any heading --
                  "No significant interval change." then "Cardiovascular:".
                  It is an utterance, and the dataset carries it with a null
                  section. Dropping it here would report the DATASET as having
                  an extra utterance.
      whitespace  the source has runs of spaces inside sentences. The pipeline
                  collapses them, so a byte comparison flags a difference that
                  is not one. Compare whitespace-normalized; a real edit still
                  shows.
    """
    out: List[str] = []
    for raw in (block or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("- "):
            # Bullet first: a bullet may itself end in a colon --
            # "- No significant abnormalities, except for the following:"
            # -- and testing for a heading before testing for a bullet
            # silently deletes it.
            out.append(s[2:].strip())
        elif not s.endswith(":"):
            out.append(s)
    return out


def _sig(items: List[str]) -> str:
    flat = "\x00".join(_WS.sub(" ", i.strip()) for i in items)
    return hashlib.md5(flat.encode()).hexdigest()


def measure(split: str, source_dir: str = DEFAULT_SOURCE_DIR,
            limit: Optional[int] = None) -> Dict[str, Any]:
    src_path = os.path.join(source_dir, f"{split}.csv")
    if not os.path.exists(src_path):
        return {"split": split, "available": False, "source": src_path}

    src: Dict[str, Tuple[int, str]] = {}
    with open(src_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            b = bullets(row.get("findings_section"))
            src[row["id"]] = (len(b), _sig(b))

    out: Dict[str, Tuple[int, str]] = {}
    with open(split_path(split), encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            obj = json.loads(line)
            u = [r.get("utterance") or "" for r in obj.get("records") or []]
            out[obj["id"]] = (len(u), _sig(u))
            if limit and len(out) >= limit:
                break

    both = set(src) & set(out)
    count_bad = sorted(i for i in both if src[i][0] != out[i][0])
    text_bad = sorted(i for i in both
                      if src[i][0] == out[i][0] and src[i][1] != out[i][1])
    return {
        "split": split, "available": True, "source": src_path,
        "src_studies": len(src), "out_studies": len(out),
        "src_utterances": sum(v[0] for v in src.values()),
        "out_utterances": sum(v[0] for v in out.values()),
        "missing": sorted(set(src) - set(out)),
        "extra": sorted(set(out) - set(src)),
        "count_mismatch": count_bad,
        "text_mismatch": text_bad,
        "examples": [(i, src[i][0], out[i][0]) for i in count_bad[:8]],
    }


def render(res: Dict[str, Any], cfg=None) -> str:
    show_ex = cfg is None or cfg.shows_examples(res["split"])
    if not res.get("available"):
        return (section(f"C  Completeness  ({res['split']})") +
                f"SKIPPED -- source CSV not found at `{res['source']}`.\n"
                f"Pass --source /path/to/srrg_findings_csv to enable it.\n")

    faults = (len(res["missing"]) + len(res["extra"])
              + len(res["count_mismatch"]) + len(res["text_mismatch"]))
    body = [section(f"C  Completeness vs source  ({res['split']})"),
            f"Source: `{res['source']}`\n",
            table([[res["src_studies"], res["out_studies"],
                    res["src_utterances"], res["out_utterances"],
                    res["out_utterances"] - res["src_utterances"]]],
                  ["CSV studies", "JSONL studies", "CSV bullets",
                   "JSONL utterances", "delta"]),
            "",
            table([[len(res["missing"]), len(res["extra"]),
                    len(res["count_mismatch"]), len(res["text_mismatch"]),
                    pct(faults, res["src_studies"])]],
                  ["missing studies", "extra studies", "count mismatch",
                   "text mismatch", "% of studies"]),
            "\n**Verdict**: " + (
                "every study and every utterance round-trips from the source."
                if faults == 0 else
                f"{faults} study/studies do not match the source.") + "\n"]
    if res["missing"] and show_ex:
        body.append("\n**Missing** (in CSV, not in dataset)\n")
        body.append(table([[i] for i in res["missing"][:20]], ["study id"]))
    if res["extra"] and show_ex:
        body.append("\n**Extra** (in dataset, not in CSV)\n")
        body.append(table([[i] for i in res["extra"][:20]], ["study id"]))
    if res["examples"] and show_ex:
        body.append("\n**Utterance-count mismatches**\n")
        body.append(table([[i, a, b] for i, a, b in res["examples"]],
                          ["study id", "CSV bullets", "JSONL utterances"]))
    if res["text_mismatch"] and show_ex:
        body.append("\n**Text differs from source** (rule 3's guarantee does "
                    "not survive this)\n")
        body.append(table([[i] for i in res["text_mismatch"][:20]],
                          ["study id"]))
    return "\n".join(body) + "\n"


def _join(parts):
    return "\n".join(parts)


def run(cfg) -> core.Result:
    src = cfg.source_dir or DEFAULT_SOURCE_DIR
    per = [measure(sp, src, cfg.limit) for sp in cfg.splits]

    def n(r, k):
        v = r[k]
        return len(v) if isinstance(v, (list, dict, set)) else v

    body = core.summary(
        [[r["split"]] + (["(source not readable)", "", "", "", "", ""]
                         if not r["available"] else
                         [f"{r['src_studies']:,}", f"{r['src_utterances']:,}",
                          n(r, "missing"), n(r, "extra"),
                          n(r, "count_mismatch"), n(r, "text_mismatch")])
         for r in per],
        ["split", "source studies", "source utterances", "missing", "extra",
         "count mismatch", "text mismatch"],
        "Four zeros on a row means that split round-trips from the source CSV "
        "with nothing lost and nothing altered.")
    body += _join(render(r, cfg) for r in per)

    if not any(r["available"] for r in per):
        return core.Result(body, core.SKIP,
                           f"source CSVs not readable at {src}")
    seen = [r for r in per if r["available"]]
    faults = {k: sum(len(r[k]) if isinstance(r[k], (list, set, dict)) else r[k]
                     for r in seen)
              for k in ("missing", "extra", "count_mismatch", "text_mismatch")}
    bad = {k: v for k, v in faults.items() if v}
    verdict = core.FAIL if bad else core.PASS
    head = (f"{sum(r['src_studies'] for r in seen):,} studies / "
            f"{sum(r['src_utterances'] for r in seen):,} utterances round-trip "
            f"with no loss" if not bad
            else "; ".join(f"{v:,} {k}" for k, v in sorted(bad.items())))
    return core.Result(body, verdict, head, faults)


if __name__ == "__main__":
    import sys
    print(render(measure(sys.argv[1] if len(sys.argv) > 1 else "test")))
