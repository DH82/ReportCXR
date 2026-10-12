#!/usr/bin/env python3
"""Direction A -- is our label a RadLex concept? Read-only.

Matching is staged, weakest last, and WHICH STAGE matched matters more than
whether one did: it says what our label added on top of the RadLex concept.

    exact | plural | wordorder | laterality | modifier | surface | (unmatched)

Labels that match only after stripping laterality or a modifier are
over-specified -- the same population that metrics 1-B/1-C flag internally.

    python3 radlex_match.py                 # all splits
    python3 radlex_match.py --split test
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

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")

# RadLex does not bake laterality into a concept; strip it before comparing.
_SIDE = ("left", "right", "bilateral", "both", "sided", "midline")

# Latin plurals, which the regular rule does not catch.
_IRREGULAR = {
    "hila": "hilum", "apices": "apex", "bases": "base", "bronchi": "bronchus",
    "alveoli": "alveolus", "pleurae": "pleura", "septa": "septum",
    "ostia": "ostium", "cavities": "cavity", "vertebrae": "vertebra",
    "lumina": "lumen", "fossae": "fossa", "sulci": "sulcus", "hemidiaphragms":
    "hemidiaphragm",
}


def norm(t: str | None) -> str:
    """Put labels and surface forms in one space; snake_case is unpacked here."""
    s = (t or "").lower().replace("_", " ")
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def depluralize(s: str) -> str:
    """Depluralize the last word only; deliberately not aggressive."""
    w = s.rsplit(" ", 1)
    last = w[-1]
    if last in _IRREGULAR:
        last = _IRREGULAR[last]
    elif last.endswith("ies") and len(last) > 4:
        last = last[:-3] + "y"
    elif last.endswith("ses") and len(last) > 4:
        last = last[:-2]
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 3:
        last = last[:-1]
    w[-1] = last
    return " ".join(w)


def strip_side(s: str) -> str:
    w = [x for x in s.split() if x not in _SIDE]
    return " ".join(w)


def strip_modifier(s: str, mods: set) -> str:
    w = [x for x in s.split() if x not in mods]
    return " ".join(w)


def wordorder(s: str):
    """'lung base' <-> 'base of lung'; RadLex often uses the latter."""
    w = s.split()
    if len(w) == 2:
        yield f"{w[1]} of {w[0]}"
        yield f"{w[1]} {w[0]}"
    if " of " in s:
        a, b = s.split(" of ", 1)
        yield f"{b} {a}"


def load_radlex(path: str):
    """Normalized surface -> RID. A label beats a synonym."""
    if not os.path.exists(path):
        sys.exit(f"term table not found: {path}\nRun radlex_import.py first.")
    by_label, by_syn, rid_label = {}, {}, {}
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            parts = line.rstrip("\n").split("\t")
            rid, label, syns = parts[0], parts[1], parts[2]
            rid_label[rid] = label
            if label:
                by_label.setdefault(norm(label), rid)
            for s in syns.split("|"):
                if s:
                    by_syn.setdefault(norm(s), rid)
    return by_label, by_syn, rid_label


def load_corpus(splits):
    """(field, label) -> count, plus label -> surface-form counter."""
    freq = {f: collections.Counter() for f in ("entity", "anatomy", "descriptor")}
    surf = {f: collections.defaultdict(collections.Counter)
            for f in ("entity", "anatomy", "descriptor")}
    for sp in splits:
        p = os.path.join(JSONL, f"{sp}.jsonl")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                for r in json.loads(line).get("records") or []:
                    for prop in r.get("propositions") or []:
                        e = prop.get("entity") or {}
                        if e.get("label"):
                            freq["entity"][e["label"]] += 1
                            if e.get("text"):
                                surf["entity"][e["label"]][e["text"].lower()] += 1
                        for a in prop.get("anatomy") or []:
                            if a.get("label"):
                                freq["anatomy"][a["label"]] += 1
                                if a.get("text"):
                                    surf["anatomy"][a["label"]][a["text"].lower()] += 1
                        for d in prop.get("descriptors") or []:
                            if d.get("label"):
                                freq["descriptor"][d["label"]] += 1
                                if d.get("text"):
                                    surf["descriptor"][d["label"]][d["text"].lower()] += 1
    return freq, surf


def _lookup(cand, by_label, by_syn):
    if not cand:
        return None
    return by_label.get(cand) or by_syn.get(cand)


def candidates(label, mods):
    """Yield (surface, stage) weakest last; the first hit is the answer."""
    base = norm(label)
    yield base, "exact"
    dp = depluralize(base)
    if dp != base:
        yield dp, "plural"
    for form in (base, dp):
        for wo in wordorder(form):
            yield wo, "wordorder"
    for form in (base, dp):
        ss = strip_side(form)
        if ss and ss != form:
            yield ss, "laterality"
            yield depluralize(ss), "laterality"
            for wo in wordorder(ss):
                yield wo, "laterality"
    for form in (base, dp):
        sm = strip_modifier(form, mods)
        if sm and sm != form:
            yield sm, "modifier"
            yield depluralize(sm), "modifier"
            smm = strip_side(sm)
            if smm and smm != sm:
                yield smm, "modifier"


def match(label, surfaces, by_label, by_syn, mods):
    """(stage, RID), or (None, None)."""
    for cand, how in candidates(label, mods):
        rid = _lookup(cand, by_label, by_syn)
        if rid:
            return how, rid
    for s, _n in surfaces.most_common(5):
        for cand, _how in candidates(s, mods):
            rid = _lookup(cand, by_label, by_syn)
            if rid:
                return "surface", rid
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", action="append", choices=SPLITS)
    ap.add_argument("--min-freq", type=int, default=1)
    a = ap.parse_args()
    splits = a.split or SPLITS

    by_label, by_syn, rid_label = load_radlex(TERMS)
    print(f"RadLex surfaces: label {len(by_label):,} + synonym {len(by_syn):,}")

    sys.path.insert(0, REPO)
    from Prompt2 import ontology as ONT
    mods = set()
    for w in ONT.DESCRIPTOR_LEXICON:
        mods.update(norm(w).split())
    for _w, z in ONT.ZONE_WORDS:
        mods.add(z)
    print(f"modifier list (for stripping): {len(mods)}")
    freq, surf = load_corpus(splits)

    for field in ("entity", "anatomy", "descriptor"):
        c = freq[field]
        tot_occ = sum(c.values())
        labels = [(l, n) for l, n in c.items() if n >= a.min_freq]
        how_cnt = collections.Counter()
        matched_occ = 0
        unmatched = []
        for l, n in labels:
            how, rid = match(l, surf[field][l], by_label, by_syn, mods)
            if how:
                how_cnt[how] += 1
                matched_occ += n
            else:
                unmatched.append((l, n))

        nm = sum(how_cnt.values())
        print(f"\n{'='*72}\n{field}   distinct {len(labels):,}   occurrences {tot_occ:,}\n{'='*72}")
        print(f"  matched labels       {nm:,} / {len(labels):,}  ({100*nm/max(1,len(labels)):.1f}%)")
        print(f"  matched occurrences  {matched_occ:,} / {tot_occ:,}  ({100*matched_occ/max(1,tot_occ):.1f}%)")
        for how in ("exact", "plural", "wordorder", "laterality", "modifier",
                    "surface"):
            if how_cnt[how]:
                tag = "  <- over-specified" if how in ("laterality", "modifier") else ""
                print(f"      {how:12} {how_cnt[how]:6,}{tag}")
        unmatched.sort(key=lambda x: -x[1])
        print(f"  top unmatched (by frequency):")
        for l, n in unmatched[:15]:
            print(f"      {n:8,}  {l}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
