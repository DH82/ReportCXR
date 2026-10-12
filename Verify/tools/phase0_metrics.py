#!/usr/bin/env python3
"""Phase 0 decision metrics (C1 / C2) for the study design, not for data quality.

The rest of Verify/ asks "is this structuring correct?". This asks a different
question: "does this corpus actually support the axes the study wants to build
on?" -- the W1/W2 gates of the Phase 0 plan.

    C1  share of studies holding two or more propositions that share a factor.
        Below 15% the multiplicity axis is not worth a spine and spatial
        grounding takes its place.

    C2  minable contrastive pairs per axis:
          assertion swap -- same entity+anatomy, polarity flips
          anatomy   swap -- same entity+polarity, location differs
        Below 1,000 the design collapses to a single anatomy axis.

Also reports what W1 asked for directly: propositions per study, and the
entity-anatomy combination frequencies.

    python3 phase0_metrics.py                 # small splits
    python3 phase0_metrics.py --all           # include train (~3 min)
    python3 phase0_metrics.py --arm Prompt2

Read-only. Never writes jsonl/.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # Verify/
import core                                        # noqa: E402


def _key_anatomy(prop):
    """The anatomy side of a proposition, order-insensitive."""
    return tuple(sorted(
        (a.get("label") or "", a.get("laterality") or "", a.get("zone") or "")
        for a in prop.get("anatomy") or []))


def _descriptor_key(prop):
    return tuple(sorted((d.get("type") or "", d.get("label") or "")
                        for d in prop.get("descriptors") or []))


def collect(splits):
    st = {
        "studies": 0,
        "propositions": 0,
        "props_per_study": collections.Counter(),
        # C1
        "share_any": 0, "share_entity": 0, "share_anatomy": 0,
        # W2: explicit negation
        "studies_with_absent": 0,
        # combination frequency
        "ent_anat": collections.Counter(),
        # C2 buckets: (entity, anatomy) -> {polarity: set(study)}
        "polarity": collections.defaultdict(lambda: collections.defaultdict(set)),
        # (entity, polarity) -> {anatomy: set(study)}
        "location": collections.defaultdict(lambda: collections.defaultdict(set)),
    }

    for split in splits:
        path = core.split_path(split)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                study = json.loads(line)
                sid = study.get("id")
                st["studies"] += 1

                ents, anats, keys = [], [], []
                has_absent = False
                n_props = 0

                for rec in study.get("records") or []:
                    for prop in rec.get("propositions") or []:
                        n_props += 1
                        ent = (prop.get("entity") or {}).get("label") or ""
                        pol = (prop.get("assertion") or {}).get("label") or ""
                        anat = _key_anatomy(prop)

                        ents.append(ent)
                        anats.append(anat)
                        keys.append((ent, anat, pol, _descriptor_key(prop)))
                        if pol == "absent":
                            has_absent = True

                        for a in prop.get("anatomy") or []:
                            st["ent_anat"][(ent, a.get("label") or "")] += 1
                        if ent and pol:
                            st["polarity"][(ent, anat)][pol].add(sid)
                            st["location"][(ent, pol)][anat].add(sid)

                st["propositions"] += n_props
                st["props_per_study"][min(n_props, 30)] += 1
                if has_absent:
                    st["studies_with_absent"] += 1

                # C1 -- two or more propositions sharing a factor
                if n_props >= 2:
                    dup_ent = len(ents) != len(set(ents))
                    dup_anat = len(anats) != len(set(anats))
                    if dup_ent:
                        st["share_entity"] += 1
                    if dup_anat:
                        st["share_anatomy"] += 1
                    if dup_ent or dup_anat:
                        st["share_any"] += 1
    return st


def pair_yield(buckets, min_studies=1):
    """Disjoint pairs minable from a {key: {variant: set(study)}} map.

    A pair needs two studies that agree on the key and differ on the variant,
    so the yield for one key is the number of disjoint two-study matchings --
    bounded by the second largest variant's study count, summed greedily.
    """
    total, keys_with_pair = 0, 0
    for _key, variants in buckets.items():
        sizes = sorted((len(s) for s in variants.values()), reverse=True)
        if len(sizes) < 2 or sizes[1] < min_studies:
            continue
        keys_with_pair += 1
        total += sum(sizes[1:])          # each non-dominant study can pair off
    return total, keys_with_pair


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="include train")
    ap.add_argument("--arm", help="jsonl/<arm>/ (default: Prompt)")
    ap.add_argument("--split", action="append")
    a = ap.parse_args()

    if a.arm:
        core.set_arm(a.arm)
    splits = a.split or (core.SPLITS if a.all else core.SMALL)
    splits = [s for s in splits if s in core.available_splits()]

    fp = core.fingerprint()
    print(f"arm {core.ARM}  splits {', '.join(splits)}  "
          f"ontology {fp['content_hash']}\n")

    st = collect(splits)
    n = st["studies"] or 1

    print("=== W1 — 규모와 분포 ===")
    print(f"  studies                         {st['studies']:,}")
    print(f"  propositions                    {st['propositions']:,}")
    print(f"  propositions per study (mean)   {st['propositions']/n:.2f}")
    dist = st["props_per_study"]
    for b in (0, 1, 2, 3, 5, 10):
        c = sum(v for k, v in dist.items() if k >= b)
        print(f"    >= {b:>2} propositions              {c:>9,}  ({100*c/n:5.1f}%)")

    print("\n=== C1 — factor 를 공유하는 proposition 이 2개 이상인 study ===")
    for label, key in (("entity 공유", "share_entity"),
                       ("anatomy 공유", "share_anatomy"),
                       ("**둘 중 하나라도**", "share_any")):
        c = st[key]
        print(f"  {label:<22} {c:>9,}  ({100*c/n:5.1f}%)")
    verdict = "PASS — multiplicity 축 유지" if 100*st["share_any"]/n >= 15 \
        else "FAIL — spatial grounding 으로 전환"
    print(f"  판정 (기준 15%)        {verdict}")

    print("\n=== W2 — 명시적 부정 ===")
    c = st["studies_with_absent"]
    print(f"  absent 를 하나라도 가진 study    {c:>9,}  ({100*c/n:5.1f}%)")

    print("\n=== C2 — 축별 contrastive pair 수율 ===")
    for label, buckets in (("assertion swap", st["polarity"]),
                           ("anatomy swap", st["location"])):
        total, keys = pair_yield(buckets)
        verdict = "PASS" if total >= 1000 else "FAIL"
        print(f"  {label:<16} pairs {total:>9,}   "
              f"(키 {keys:,}개)   기준 1,000 → {verdict}")

    print("\n=== W1 — entity·anatomy 조합 빈도 (상위 15) ===")
    print(f"  distinct 조합 {len(st['ent_anat']):,}")
    for (e, a), c in st["ent_anat"].most_common(15):
        print(f"    {c:>8,}  {e or '∅'} @ {a or '∅'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
