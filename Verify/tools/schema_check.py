#!/usr/bin/env python3
"""Structural check of jsonl/, independent of the Verify suite.

Section S reads the file and its keys. This adds two things:

  1. Validates records against the SCHEMA DOCUMENT itself
     (Prompt2/schema.py:FULL_RECORD) -- the same document llama.cpp compiles
     into a grammar. validate.py re-types the enums by hand, and two copies
     can drift.
  2. Measures usefulness for the next stage (image-text grounding): not
     whether a proposition obeys the rules, but whether it can be attached to
     an image at all. An entity with no anatomy has nothing to hang on.
"""
import json, sys, os, collections

ROOT = "/home/ldh/ReportCXR-Ko"
ARM = os.environ.get("REPORTCXR_ARM", "Prompt")   # jsonl/<arm>/
sys.path.insert(0, ROOT)
from Prompt2.schema import FULL_RECORD
from Prompt2.vocabulary import (ENTITY_TYPES, LATERALITY, ZONES, ANATOMY_ROLES,
                               ANATOMY_SOURCES, DESCRIPTOR_TYPES,
                               ASSERTION_LABELS, COMPARISON_LABELS)

AUDIT_KEYS = ("normalization", "review", "row_id")
SIDED = {"left", "right", "bilateral"}

# Not a full JSON Schema implementation: only what FULL_RECORD uses (type,
# enum, properties, required, additionalProperties, items), to avoid a
# dependency. It therefore understands this one schema and no other.
_PY = {"string": str, "object": dict, "array": list, "boolean": bool,
       "number": (int, float), "integer": int, "null": type(None)}


def _sv(inst, sch, path, out):
    if "enum" in sch:
        if inst not in sch["enum"]:
            out.append((path, "enum", f"{inst!r} is not an allowed value"))
            return
    t = sch.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(isinstance(inst, _PY[x]) and
                   not (x != "boolean" and isinstance(inst, bool))
                   for x in ts):
            out.append((path, "type", f"{type(inst).__name__}, expected {ts}"))
            return
    if isinstance(inst, dict) and "properties" in sch:
        props = sch["properties"]
        for k in sch.get("required", []):
            if k not in inst:
                out.append((path, "required", f"{k!r} is missing"))
        if sch.get("additionalProperties") is False:
            for k in inst:
                if k not in props:
                    out.append((path, "additionalProperties", f"{k!r} is not in the schema"))
        for k, v in inst.items():
            if k in props:
                _sv(v, props[k], f"{path}/{k}" if path else k, out)
    if isinstance(inst, list) and "items" in sch:
        for i, v in enumerate(inst):
            _sv(v, sch["items"], f"{path}/{i}" if path else str(i), out)


class VAL_:
    def iter_errors(self, inst):
        out = []
        _sv(inst, FULL_RECORD, "", out)
        for path, kind, msg in out:
            yield type("E", (), {"absolute_path": path.split("/") if path else [],
                                 "validator": kind, "message": msg})()


VAL = VAL_()


def check(split, limit=None):
    c = collections.Counter()
    schema_err = collections.Counter()
    ex = {}
    with open(f"{ROOT}/jsonl/{ARM}/{split}.jsonl") as fh:
        for ln, line in enumerate(fh):
            if limit and ln >= limit:
                break
            study = json.loads(line)
            c["studies"] += 1
            for rec in study.get("records") or []:
                c["utterances"] += 1
                probe = {k: v for k, v in rec.items() if k not in AUDIT_KEYS}
                if VAL is not None:
                    errs = list(VAL.iter_errors(probe))
                    if errs:
                        c["schema_invalid"] += 1
                        for e in errs[:3]:
                            key = "/".join(str(p) for p in e.absolute_path) or "(root)"
                            key = key.split("/")[0] + ":" + (e.validator or "?")
                            schema_err[key] += 1
                            ex.setdefault(key, (rec.get("utterance"), e.message[:120]))

                props = rec.get("propositions") or []
                ids = [p.get("id") for p in props]
                if len(set(ids)) != len(ids):
                    c["dup_prop_id"] += 1
                if ids != [f"p{i}" for i in range(1, len(ids) + 1)]:
                    c["prop_id_not_sequential"] += 1
                known = set(ids)
                for p in props:
                    c["props"] += 1
                    df = p.get("derived_from")
                    if df is not None and df not in known:
                        c["derived_from_dangling"] += 1
                    if df == p.get("id"):
                        c["derived_from_self"] += 1

                    # -- usable by the next stage? ---------------------------
                    ent = p.get("entity") or {}
                    if (ent.get("label") or "").strip():
                        c["has_entity_label"] += 1
                    anats = [a for a in (p.get("anatomy") or [])]
                    if anats:
                        c["has_anatomy"] += 1
                    if any((a.get("label") or "") for a in anats):
                        c["has_anatomy_label"] += 1
                    if any(a.get("laterality") in SIDED for a in anats):
                        c["has_side"] += 1
                    if any(a.get("zone") for a in anats):
                        c["has_zone"] += 1
                    if any(a.get("source") == "utterance" for a in anats):
                        c["anatomy_from_utterance"] += 1
                    if p.get("descriptors"):
                        c["has_descriptor"] += 1
                    c["assert_" + str((p.get("assertion") or {}).get("label"))] += 1
                    if (p.get("comparison") or {}).get("label") not in (None, "none"):
                        c["has_comparison"] += 1
                    if df:
                        c["derived"] += 1
                    if ent.get("type") == "device":
                        c["device"] += 1
                        if any(a.get("role") == "tip_location" for a in anats):
                            c["device_tip_located"] += 1
    return c, schema_err, ex


def pct(n, d):
    return f"{100.0*n/d:6.2f}%" if d else "     -"


splits = sys.argv[1:] or ["validate", "test", "test_reviewed", "train"]
print(f"{'':22s} " + "".join(f"{s:>16s}" for s in splits))
cols = {}
for s in splits:
    cols[s] = check(s)

rows_int = ["studies", "utterances", "props", "schema_invalid", "dup_prop_id",
            "prop_id_not_sequential", "derived_from_dangling", "derived_from_self"]
print("\n--- integrity (must be 0) ---")
for r in rows_int:
    print(f"{r:22s} " + "".join(f"{cols[s][0][r]:>16,}" for s in splits))

print("\n--- what propositions carry (share of props) ---")
rows_pct = ["has_entity_label", "has_anatomy", "has_anatomy_label",
            "anatomy_from_utterance", "has_side", "has_zone", "has_descriptor",
            "has_comparison", "derived",
            "assert_present", "assert_absent", "assert_uncertain",
            "assert_unknown"]
for r in rows_pct:
    print(f"{r:22s} " + "".join(f"{pct(cols[s][0][r], cols[s][0]['props']):>16s}" for s in splits))

print("\n--- device propositions using tip_location ---")
for s in splits:
    c = cols[s][0]
    print(f"  {s:16s} {c['device_tip_located']:,} / {c['device']:,}  "
          f"{pct(c['device_tip_located'], c['device'])}")

print("\n--- schema violations ---")
for s in splits:
    _, se, ex = cols[s]
    if not se:
        print(f"  {s:16s} none")
        continue
    print(f"  {s}")
    for k, n in se.most_common(8):
        print(f"     {k:34s} {n:>9,}   e.g. {ex[k][1]}")
