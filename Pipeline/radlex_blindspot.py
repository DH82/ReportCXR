#!/usr/bin/env python3
"""Direction B -- systematic blind spots. Read-only.

Corpus self-consistency only finds ragged misses: a concept the model has never
extracted is invisible to the corpus, and only an external vocabulary shows it.

    a RadLex term appears in the utterance
      -> no extracted span covers it
      -> its coverage rate stays low across utterances
      -> a blind spot in the prompt

Coverage is decided by CHARACTER OFFSET; string replacement would leave
'catheter' behind in "...central catheter (PICC) line..." and false-positive.

    python3 radlex_blindspot.py --split test --split validate
    python3 radlex_blindspot.py --min-total 20
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TERMS = os.path.join(REPO, "RadLex", "radlex_terms.tsv")
JSONL = os.path.join(REPO, "jsonl",
                     os.environ.get("REPORTCXR_ARM", "Prompt"))
SPLITS = ["train", "validate", "test", "test_reviewed"]
MAXGRAM = 4

_TOK = re.compile(r"[a-z0-9]+")

# Clinical top-level categories only, or imaging and reporting terms
# ("frontal view", "assessment") dominate the candidate list.
CLINICAL = {
    "RID3":     "anatomical entity",
    "RID34785": "clinical finding",
    "RID5":     "imaging observation",
    "RID34861": "object",             # devices
    "RID7479":  "non-anatomical substance",
}
# Concepts in RadLex but function words in a report; the 1-gram false positives.
_STOP = {"a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
         "in", "is", "it", "no", "not", "of", "on", "or", "the", "to", "with",
         "was", "were", "this", "that", "has", "have", "may", "can", "all",
         "both", "may", "than", "then", "there", "which", "who", "you", "your",
         "well", "new", "old", "上", "size", "seen", "note", "noted", "line",
         "view", "study", "image", "imaging", "film", "exam", "left", "right"}


def toks(text):
    """(word, start, end) list, offsets preserved."""
    return [(m.group(0), m.start(), m.end())
            for m in _TOK.finditer((text or "").lower())]


def load_radlex_surfaces(path, branches=None):
    """Normalized surface -> RID, 1..MAXGRAM words, clinical categories only."""
    surf, kept = {}, 0
    with open(path, encoding="utf-8") as f:
        header = next(f).rstrip("\n").split("\t")
        bi = header.index("branch") if "branch" in header else None
        for line in f:
            p = line.rstrip("\n").split("\t")
            rid, label, syns = p[0], p[1], p[2]
            if branches is not None and bi is not None:
                if (p[bi] if len(p) > bi else "") not in branches:
                    continue
            kept += 1
            for s in [label] + syns.split("|"):
                if not s:
                    continue
                w = _TOK.findall(s.lower())
                if not w or len(w) > MAXGRAM:
                    continue
                if len(w) == 1 and (w[0] in _STOP or len(w[0]) < 4):
                    continue
                surf.setdefault(" ".join(w), rid)
    return surf, kept


def spans_of(prop):
    e = prop.get("entity") or {}
    yield e.get("text")
    for a in prop.get("anatomy") or []:
        yield a.get("text")
    for d in prop.get("descriptors") or []:
        yield d.get("text")
    for k in ("assertion", "comparison"):
        yield (prop.get(k) or {}).get("cue")


def covered_ranges(record):
    """The [start, end) ranges the extracted spans occupy in the utterance."""
    utt = (record.get("utterance") or "").lower()
    out = []
    for p in record.get("propositions") or []:
        for s in spans_of(p):
            if not s:
                continue
            s = s.lower().strip()
            start = 0
            while True:
                i = utt.find(s, start)
                if i < 0:
                    break
                out.append((i, i + len(s)))
                start = i + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", action="append", choices=SPLITS)
    ap.add_argument("--min-total", type=int, default=10,
                    help="only terms appearing at least this many times")
    ap.add_argument("--max-cov", type=float, default=0.5,
                    help="report only terms at or below this coverage")
    ap.add_argument("--all-branches", action="store_true",
                    help="include imaging/reporting categories (many false positives)")
    a = ap.parse_args()
    splits = a.split or SPLITS

    branches = None if a.all_branches else set(CLINICAL)
    surf, kept = load_radlex_surfaces(TERMS, branches)
    scope = "all categories" if a.all_branches else \
        "clinical categories only (" + ", ".join(CLINICAL.values()) + ")"
    print(f"scope: {scope}")
    print(f"  RadLex concepts {kept:,} -> surfaces (1..{MAXGRAM} words) {len(surf):,}")

    stat = collections.defaultdict(lambda: [0, 0])      # term -> [covered, uncovered]
    example = {}
    n_utt = 0
    for sp in splits:
        p = os.path.join(JSONL, f"{sp}.jsonl")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                for rec in json.loads(line).get("records") or []:
                    n_utt += 1
                    utt = rec.get("utterance") or ""
                    tk = toks(utt)
                    if not tk:
                        continue
                    rng = covered_ranges(rec)
                    for i in range(len(tk)):
                        for n in range(1, MAXGRAM + 1):
                            if i + n > len(tk):
                                break
                            gram = " ".join(w for w, _s, _e in tk[i:i + n])
                            if gram not in surf:
                                continue
                            s0, e0 = tk[i][1], tk[i + n - 1][2]
                            hit = any(s < e0 and s0 < e for s, e in rng)
                            stat[gram][0 if hit else 1] += 1
                            if not hit and gram not in example:
                                example[gram] = utt[:88]

    print(f"utterances checked: {n_utt:,}\n")
    rows = []
    for term, (c, u) in stat.items():
        tot = c + u
        if tot >= a.min_total:
            rows.append((term, c, u, c / tot, surf[term]))

    blind = sorted([r for r in rows if r[3] <= a.max_cov and r[2] > 0],
                   key=lambda x: -x[2])
    print("=" * 78)
    print(f"blind-spot candidates -- RadLex terms that are almost never extracted "
          f"(occurrences>={a.min_total}, coverage<={a.max_cov})")
    print("=" * 78)
    print(f"{'term':34} {'RID':11} {'cov':>6} {'uncov':>7} {'rate':>7}")
    for term, c, u, r, rid in blind[:35]:
        print(f"  {term:32} {rid:11} {c:6,} {u:7,} {r:7.2f}")
        print(f"       e.g. {example.get(term,'')}")
    print(f"\n{len(blind)} terms / {sum(x[2] for x in blind):,} uncovered occurrences")
    return 0


if __name__ == "__main__":
    sys.exit(main())
