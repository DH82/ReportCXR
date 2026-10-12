#!/usr/bin/env python3
"""Build the stratified sample: even coverage of the failure types a prompt owns.

A random sample is useless here -- most utterances already parse correctly, so
no prompt change would move the sheet. Deterministic (seed 20260907).
"""
import json, os, random, sys, collections

ROOT = "/home/ldh/ReportCXR-Ko"
ARM = os.environ.get("REPORTCXR_ARM", "Prompt")   # jsonl/<arm>/
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "Pipeline"))
from validate import validate_record

PER = 8
SPLITS = ["test", "validate", "test_reviewed"]

def has_lateral_label(rec):
    for p in rec.get("propositions") or []:
        for a in p.get("anatomy") or []:
            l = (a.get("label") or "")
            if l.startswith(("left_", "right_")) or l in ("left", "right",
                                                          "left_side", "right_side",
                                                          "left_sided", "right_sided"):
                return True
    return False

def has_tip_descriptor(rec):
    for p in rec.get("propositions") or []:
        for d in p.get("descriptors") or []:
            if (d.get("label") or "").startswith("tip_"):
                return True
    return False

STRATA = {
    "S1_no_propositions":    lambda r, c: "no_propositions" in c,
    "S2_qualified_negation": lambda r, c: "qualified_negation_unwarned" in c,
    "S3_device_tip":         lambda r, c: "device_tip_not_located" in c or has_tip_descriptor(r),
    "S4_text_not_in_utt":    lambda r, c: "entity_text_not_in_utterance" in c
                                          or "descriptor_text_not_in_utterance" in c,
    "S5_section_conflict":   lambda r, c: "section_conflict" in c,
    "S6_split":              lambda r, c: bool(c & {"inference_not_split",
                                                    "coordination_not_split",
                                                    "should_be_one_proposition"}),
    "S7_lateral_label":      lambda r, c: has_lateral_label(r),
    "S8_clean":              lambda r, c: not c and bool(r.get("propositions")),
}

pools = collections.defaultdict(list)
seen_utt = set()
for sp in SPLITS:
    with open(f"{ROOT}/jsonl/{ARM}/{sp}.jsonl") as fh:
        for line in fh:
            study = json.loads(line)
            for rec in study.get("records") or []:
                utt = rec.get("utterance") or ""
                if not utt.strip() or utt in seen_utt:
                    continue
                seen_utt.add(utt)
                res = validate_record(rec)
                codes = {f["code"] for f in res["findings"]}
                for name, pred in STRATA.items():
                    if pred(rec, codes):
                        pools[name].append({
                            "utterance_id": rec.get("utterance_id"),
                            "utterance": utt,
                            "section": rec.get("section"),
                            "split": sp,
                            "stratum": name,
                            "v1_codes": sorted(codes),
                        })

rng = random.Random(20260907)
sample, report = [], []
for name in STRATA:
    pool = pools[name]
    rng.shuffle(pool)
    take = pool[:PER]
    sample.extend(take)
    report.append((name, len(pool), len(take)))

# An utterance can match several strata; keep it in the first one only.
uniq, got = [], set()
for it in sample:
    if it["utterance"] in got:
        continue
    got.add(it["utterance"]); uniq.append(it)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.jsonl")
with open(out, "w") as fh:
    for it in uniq:
        fh.write(json.dumps(it, ensure_ascii=False) + "\n")

print(f"{'stratum':24s} {'pool':>7s} {'taken':>6s}")
for n, p, t in report:
    print(f"{n:24s} {p:7d} {t:6d}")
print(f"\n{len(uniq)} utterances after de-duplication -> {out}")
