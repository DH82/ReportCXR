#!/usr/bin/env python3
"""RadLex OWL -> flat term table. Read-only.

RadLex uses a punning structure: the same RID is declared as owl:Class,
owl:NamedIndividual and rdf:Description with annotations spread across all
three, so reading only owl:Class yields 21,895 of 45,988 English labels. All
three are read and merged by RID. RDF/XML is streamed with iterparse.

    python3 radlex_import.py                    # writes RadLex/radlex_terms.tsv
    python3 radlex_import.py --owl <path>
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_OWL = os.path.join(REPO, "RadLex", "RadLex.owl")
DEFAULT_OUT = os.path.join(REPO, "RadLex", "radlex_terms.tsv")

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
RDFS = "{http://www.w3.org/2000/01/rdf-schema#}"
OWL = "{http://www.w3.org/2002/07/owl#}"
RIDNS = "{http://www.radlex.org/RID/}"
XMLLANG = "{http://www.w3.org/XML/1998/namespace}lang"


def rid_of(uri: str | None) -> str | None:
    if not uri:
        return None
    tail = uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return tail if tail.startswith("RID") else None


CARRIERS = (OWL + "Class", OWL + "NamedIndividual", RDF + "Description")


def parse(owl_path: str) -> dict:
    """RID -> {label, synonyms, parents, definition}, merged across the three."""
    terms: dict = {}
    for _, el in ET.iterparse(owl_path, events=("end",)):
        if el.tag not in CARRIERS:
            continue
        rid = rid_of(el.get(RDF + "about"))
        if not rid:
            el.clear()
            continue
        t = terms.setdefault(rid, {"label": None, "label_any": None,
                                   "synonyms": [], "parents": [],
                                   "definition": None})
        for ch in el:
            tag, txt = ch.tag, (ch.text or "").strip()
            if not txt and tag != RDFS + "subClassOf":
                continue
            lang = ch.get(XMLLANG)
            if tag == RDFS + "label":
                if lang == "en":
                    t["label"] = txt                      # English wins
                elif t["label_any"] is None:
                    t["label_any"] = txt                  # last resort
            elif tag == RIDNS + "Synonym":
                if lang in (None, "en") and txt not in t["synonyms"]:
                    t["synonyms"].append(txt)
            elif tag == RIDNS + "Definition":
                if t["definition"] is None:
                    t["definition"] = " ".join(txt.split())
            elif tag == RDFS + "subClassOf":
                # Direct rdf:resource parents only; owl:Restriction is a
                # relation axiom, not hierarchy.
                p = rid_of(ch.get(RDF + "resource"))
                if p and p not in t["parents"]:
                    t["parents"].append(p)
        el.clear()
    return terms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owl", default=DEFAULT_OWL)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    if not os.path.exists(a.owl):
        sys.exit(f"OWL file not found: {a.owl}")

    terms = parse(a.owl)

    # Direct children of RID1 are the working top-level categories; without them
    # imaging-procedure terms like "frontal view" look like clinical findings.
    def branch_of(rid: str) -> str:
        seen, cur, prev = set(), rid, rid
        while cur not in seen:
            seen.add(cur)
            ps = terms.get(cur, {}).get("parents") or []
            if not ps:
                return prev if prev != rid else ""
            if ps[0] == "RID1":
                return cur
            prev, cur = cur, ps[0]
        return ""

    branches = {rid: branch_of(rid) for rid in terms}
    bcount = collections.Counter(branches.values())

    n = n_lab = n_syn = n_par = n_def = 0
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("rid\tlabel\tsynonyms\tparents\tbranch\tdefinition\n")
        for rid in sorted(terms):
            t = terms[rid]
            label = t["label"] or t["label_any"] or ""
            n += 1
            n_lab += bool(t["label"])
            n_syn += len(t["synonyms"])
            n_par += bool(t["parents"])
            n_def += bool(t["definition"])
            f.write("\t".join([
                rid, label, "|".join(t["synonyms"]), "|".join(t["parents"]),
                branches.get(rid, ""),
                (t["definition"] or "").replace("\t", " ")]) + "\n")

    print(f"RadLex parsed: {a.owl}")
    print(f"  classes            {n:,}")
    print(f"  English labels     {n_lab:,}")
    print(f"  synonyms           {n_syn:,}")
    print(f"  with a parent      {n_par:,}")
    print(f"  with a definition  {n_def:,}")
    print(f"\n  top-level categories (direct children of RID1):")
    for b, k in bcount.most_common(10):
        if b:
            print(f"    {b:11} {k:7,}  {terms.get(b, {}).get('label') or ''}")
    print(f"\n  -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
