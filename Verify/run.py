#!/usr/bin/env python3
"""Run the metrics and write one markdown file per metric, plus an index.

    python3 run.py                       # small splits, every metric
    python3 run.py --all                 # include train
    python3 run.py -s S -s C -s R        # selected metrics
    python3 run.py --one report.md       # the old single-file report
    python3 run.py --list

WHY ONE FILE PER METRIC.  The audit used to emit a single report holding
twelve metrics. Two things went wrong with that. Reading it meant scrolling
past eleven metrics to reach the one you came for, so in practice nobody read
past the first screen. And a metric that moved could not be diffed on its own:
the whole file changed whenever anything did, which is the same as no history
at all. Splitting the output makes `git diff` answer "what moved since the
last run" per metric, and makes each file small enough to actually be read.

The index is the part that was missing before. Each metric now returns a
verdict as well as markdown (core.Result), so INDEX.md is a table -- one row
per metric, verdict and headline number -- and the question "did this dataset
pass" has an answer that fits on one screen.

A metric is metrics/mNN_*.py exposing five names:

    SECTION   symbol ("S", "1-A", "P1a") -- the key used by -s
    TITLE     one line
    SCOPE     "split" = measured per split, "corpus" = once over everything
    ASKS      one sentence: the question this metric answers
    run(cfg)  returns core.Result (or bare markdown, treated as UNKNOWN)
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import os
import pathlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import core                                                          # noqa: E402
from core import SMALL, SPLITS, available_splits, table, worst       # noqa: E402
from metrics.groups import GROUPS, grouped as groups_of               # noqa: E402

METRIC_DIR = "metrics"
OUT_ROOT = os.path.join(core.REPO, "out", "reports")


class Config:
    """Settings handed to a metric; each takes only what it needs."""

    def __init__(self, splits, limit=None, normalize_path=None,
                 source_dir=None, min_freq=5, example_split=None):
        self.splits = splits
        self.limit = limit
        self.normalize_path = normalize_path
        self.source_dir = source_dir
        self.min_freq = min_freq
        # WHICH SPLIT THE EXAMPLE ROWS COME FROM. Numbers are wanted for every
        # split; example sentences are not. Four splits' worth of examples is
        # four times the reading for no extra information -- the same defect
        # looks the same in train as in test -- and train's examples are the
        # least useful of the four, being the split nobody inspects by hand.
        # So the tables span every split and the sentences come from one.
        self.example_split = example_split

    def shows_examples(self, split: str) -> bool:
        """True for the one split whose example rows are printed."""
        return self.example_split is None or split == self.example_split


class Metric:
    """One discovered metric module and the identity its file gets."""

    def __init__(self, mod):
        self.mod = mod
        self.stem = mod.__name__.split(".")[-1]          # m04_coverage
        self.symbol = mod.SECTION
        self.title = mod.TITLE
        self.scope = mod.SCOPE
        self.asks = getattr(mod, "ASKS", "")

    @property
    def filename(self) -> str:
        return f"{self.stem}.md"


def discover():
    """Read metrics/mNN_*.py in filename order."""
    out = []
    for p in sorted(pathlib.Path(HERE, METRIC_DIR).glob("m[0-9][0-9]*_*.py")):
        mod = importlib.import_module(f"{METRIC_DIR}.{p.stem}")
        if hasattr(mod, "run"):
            out.append(Metric(mod))
    return out


def slug(names) -> str:
    """Directory name for a set of splits: stable, and short enough to type."""
    if set(names) == set(SPLITS):
        return "all"
    if set(names) == set(SMALL):
        return "small"
    return "-".join(names)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip("\n") + "\n")


def group_file(g, rows, splits, stamp: str) -> str:
    """One theme's file: why these belong together, then each member in full.

    The group's verdict is the WORST among its members, never an average. An
    average would let a FAIL hide behind four PASSes, which is the one thing a
    summary must not do. Each member keeps its own verdict inside, so the file
    says both "this theme has a problem" and "it is this metric".

    Part 1 of each member is its MEANS string, which is Korean prose: this file
    is where someone finds out what a metric means, so it cannot be a symbol
    they have to go look up. The measured output stays English -- it is table
    headers and verdict words emitted by code.
    """
    verdict = core.Result("", worst(r.verdict for _m, r in rows)).mark
    out = [
        f"# {g.title}",
        "",
        f"**묶음 판정: {verdict}** — 아래 {len(rows)}개 요소 중 가장 무거운 "
        f"판정이다. 평균이 아니다.",
        "",
        f"`{core.ARM}` / {', '.join(splits)} · {stamp}",
        "",
        table([[r.mark, m.symbol, m.title, r.headline or ""]
               for m, r in rows],
              ["verdict", "metric", "title", "headline"]),
    ]
    if (g.blurb or "").strip():
        out += ["", "## 왜 이것들이 한 묶음인가", "", g.blurb.strip()]

    for i, (m, res) in enumerate(rows, 1):
        means = (getattr(m.mod, "MEANS", "") or "").strip() or m.asks
        out += [
            "",
            "---",
            "",
            f"# {i}. {m.symbol} — {m.title}",
            "",
            f"**판정: {res.mark}**" + (f" — {res.headline}" if res.headline else ""),
            "",
            f"## {i}.1 이 지표가 무엇인가",
            "",
            means or "_(설명 없음 — 모듈에 `MEANS` 를 추가할 것)_",
            "",
            f"## {i}.2 현재 데이터가 어떤가",
            "",
            # A corpus-scope body opens with its own heading and no leading
            # newline; without the lstrip+blank line it would run onto the
            # heading above.
            res.body.lstrip("\n").rstrip(),
        ]

    out += [
        "",
        "---",
        "",
        "<details><summary>이 숫자가 어느 온톨로지·정규화기·데이터로 "
        "계산되었는지</summary>",
        "",
        table([[m.symbol, f"`{METRIC_DIR}/{m.stem}.py`", m.scope]
               for m, _r in rows], ["metric", "측정 코드", "범위"]),
        "",
        core.provenance(splits),
        "",
        "지문이 다른 두 파일의 숫자는 비교 대상이 아니다.",
        "",
        "</details>",
    ]
    return "\n".join(out) + "\n"


def index_file(groups, splits, stamp: str, failures) -> str:
    """The one screen that answers 'did this dataset pass'.

    Two levels, because the two questions are different: which THEME is in
    trouble (the group rows), and which metric inside it (the indented rows).
    """
    every = [r for _g, rows in groups for _m, r in rows]
    body = [
        "# Verify — 감사 결과",
        "",
        f"`{core.ARM}` / {', '.join(splits)} · {stamp} · "
        f"{len(groups)}개 묶음 / {len(every)}개 요소",
        "",
        f"**전체 판정: {core.Result('', worst(r.verdict for r in every)).mark}** "
        "— 가장 무거운 판정 하나를 그대로 올린 값이다. 평균이 아니다.",
        "",
    ]
    rows = []
    for g, members in groups:
        gv = core.Result("", worst(r.verdict for _m, r in members)).mark
        rows.append([f"**{gv}**", "", f"**[{g.title}]({g.key}.md)**",
                     f"요소 {len(members)}개"])
        for m, res in members:
            rows.append(["", m.symbol, f"　└ {m.title}", res.headline or ""])
    body += [
        table(rows, ["verdict", "metric", "묶음 / 요소", "headline"]),
        "",
        "**굵은 줄이 파일 하나다.** 제목을 누르면 그 묶음의 md 가 열리고, 그 안에 "
        "속한 요소들이 **① 이 지표가 무엇인가 ② 현재 데이터가 어떤가** 순서로 "
        "들어 있다.",
        "",
        "## 판정 기호 — 여섯 가지",
        "",
        table([
            ["PASS", "고칠 것 없음", "그대로 두면 된다"],
            ["WARN", "진짜 문제이지만 급하지는 않음",
             "고쳐야 하지만 이것 때문에 다른 숫자가 무의미해지지는 않는다"],
            ["FAIL", "**먼저 고쳐야 함**",
             "이걸 고치기 전에는 나머지 숫자를 믿을 수 없다"],
            ["INFO", "사람이 볼 목록. **점수가 아님**",
             "옳고 그름을 기계가 정할 수 없어 순위만 매긴 것"],
            ["BLIND", "**측정이 일어나지 않음**",
             "결함이 없는 게 아니라, 볼 수 있는 상태가 아니다"],
            ["SKIP", "전제가 없어 못 돌림", "필요한 파일이나 코드가 없다"],
        ], ["판정", "뜻", "무엇을 해야 하나"]),
        "",
        "### ⚠️ BLIND 와 INFO 는 PASS 가 아니다",
        "",
        "**이 둘은 초보자가 반드시 헷갈리고, 헷갈리면 정반대로 읽게 된다.**",
        "",
        "`BLIND` 는 **자로 재려는데 자에 눈금이 없는 상태**다. 예를 들어 어떤 "
        "검사는 \"표가 아는 단어\"끼리만 어긋남을 셀 수 있는데, 표가 아는 게 "
        "거의 없으면 어긋남도 0 으로 나온다. 그 0 은 화면상 `PASS` 와 똑같이 "
        "생겼지만 **뜻이 정반대다** — 깨끗한 게 아니라 재지 않은 것이다.",
        "",
        "`INFO` 는 **기계가 답할 수 없는 질문**이다. 예를 들어 \"이 두 이름표를 "
        "합치는 게 맞나\" 는 의학을 아는 사람만 답할 수 있다. 그래서 순위만 "
        "매겨 넘긴다. **그 줄 수를 결함 수로 세면**, 이 도구가 어떻게 해석했는지를 "
        "**데이터의 품질인 것처럼 보고하게 된다.**",
        "",
        "---",
        "",
        "<details><summary>이 숫자가 어느 온톨로지·정규화기·데이터로 "
        "계산되었는지</summary>",
        "",
        core.provenance(splits),
        "",
        "</details>",
    ]
    if failures:
        body += ["", "## 실행 중 죽은 요소", ""] + \
                [f"- `{s}`: {e}" for s, e in failures]
    return "\n".join(body)


def main() -> int:
    metrics = discover()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="include train")
    ap.add_argument("--split", action="append", help="repeatable")
    ap.add_argument("-s", "--section", action="append",
                    help="metric symbol; repeatable; default is all")
    ap.add_argument("-g", "--group", action="append",
                    help="group key (g2_vocabulary) or a prefix of it; "
                         "repeatable; selects every metric in it")
    ap.add_argument("--limit", type=int, help="max records per split")
    ap.add_argument("--normalize", help="path to normalize.py (metric 0)")
    ap.add_argument("--source", help="source CSV directory (metric C)")
    ap.add_argument("--examples-from", default="test_reviewed",
                    help="split the example rows are taken from "
                         "(default test_reviewed; 'all' for every split)")
    ap.add_argument("--arm", help="which jsonl/<arm>/ to audit (default: Prompt)")
    ap.add_argument("--list", action="store_true", help="list metrics and exit")
    ap.add_argument("-o", "--out", help="output directory "
                    "(default out/reports/<arm>/<splits>/)")
    ap.add_argument("--one", help="also write the old single-file report here")
    a = ap.parse_args()

    if a.list:
        rows = []
        for g, members in groups_of(metrics):
            rows.append([f"{g.key}.md", "", f"**{g.title}**", ""])
            for m in members:
                rows.append(["", m.symbol, f"　└ {m.title}", m.stem])
        print(table(rows, ["파일", "metric", "묶음 / 요소", "측정 코드"]))
        return 0

    want = set(a.section or [])
    for key in a.group or []:
        hit = [g for g in GROUPS if g.key == key or g.key.startswith(key)]
        if not hit:
            sys.exit(f"no such group: {key}  "
                     f"(have: {', '.join(g.key for g in GROUPS)})")
        want.update(sym for g in hit for sym in g.members)
    chosen = [m for m in metrics if not want or m.symbol in want]
    if want and not chosen:
        sys.exit(f"no such metric: {sorted(want)}")

    if a.arm:
        core.set_arm(a.arm)

    splits = a.split or (SPLITS if a.all else SMALL)
    splits = [s for s in splits if s in available_splits()]
    if not splits:
        sys.exit("no split files found under " + core.JSONL_DIR)
    ex = None if a.examples_from == "all" else a.examples_from
    if ex and ex not in splits:
        ex = splits[-1]        # asked-for split is not in this run; do not
                               # silently print nothing
    cfg = Config(splits, a.limit, a.normalize, a.source, example_split=ex)
    stamp = f"{datetime.datetime.now():%Y-%m-%d %H:%M}"

    outdir = a.out or os.path.join(OUT_ROOT, core.ARM, slug(splits))
    results, failures = {}, []
    for m in chosen:
        sys.stderr.write(f"  [{m.symbol}] {m.title} ...\n")
        try:
            res = core.Result.of(m.mod.run(cfg))
        except Exception as e:        # one dead metric must not stop the rest
            sys.stderr.write(f"      failed: {type(e).__name__}: {e}\n")
            failures.append((m.stem, f"{type(e).__name__}: {e}"))
            res = core.Result(f"\nThis metric failed: `{type(e).__name__}: {e}`\n",
                              core.SKIP, "crashed")
        results[m.symbol] = res

    groups = [(g, [(m, results[m.symbol]) for m in members])
              for g, members in groups_of(chosen)]
    for g, rows in groups:
        write(os.path.join(outdir, f"{g.key}.md"),
              group_file(g, rows, splits, stamp))

    write(os.path.join(outdir, "INDEX.md"),
          index_file(groups, splits, stamp, failures))
    sys.stderr.write(f"-> {outdir}/  ({len(groups)}개 묶음 / "
                     f"{len(chosen)}개 요소 + INDEX.md)\n")

    if a.one:
        doc = [f"# Verify -- normalization audit report\n", f"{stamp}\n",
               core.provenance(splits)]
        for _g, rows in groups:
            for m, res in rows:
                doc.append(f"\n---\n\n# {m.symbol}  {m.title}\n")
                doc.append(res.body)
        write(a.one, "\n".join(doc))
        sys.stderr.write(f"-> {a.one}\n")

    print(index_file(groups, splits, stamp, failures).split("\n---\n")[0])
    return 1 if any(r.verdict == core.FAIL for r in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
