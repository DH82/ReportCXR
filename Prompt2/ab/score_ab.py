#!/usr/bin/env python3
"""Score the A/B run, in three layers kept separate:

  1. per-stratum target -- did the defect that stratum was picked for go away
  2. global rule violations -- did anything else regress (S8 is the control)
  3. label hygiene and step 2 churn -- does the prompt agree with the ontology

Churn is a metric because a label normalize.py had to fix is a label the prompt
taught wrongly; it is silently repaired here and a defect wherever repair fails.
"""
import json, sys, os, collections, re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "out", "ab")
rows = [json.loads(l) for l in open(f"{OUT}/out.jsonl")]

# Arms to compare; v1 vs v2 by default.
LEFT, RIGHT = (sys.argv[1:] + ["v1", "v2"])[:2]

BARE = {"left", "right", "bilateral", "left_side", "right_side",
        "left_sided", "right_sided"}
# Leftovers after stripping a prefix: not structures, so never a label (rule 16).
FRAGMENT = {"sided", "side", "lateral", "sides"}
PREP = re.compile(r"^\s*(below|above|beneath|under|adjacent to|near|behind|"
                  r"overlying|at the level of)\b", re.I)
LIMIT = re.compile(r"limited|limiting|obscur|poorly assessed|suboptimal|"
                   r"difficult to assess|excluded from|not well seen", re.I)
LOWER_BOUND = re.compile(r"at least|no less than", re.I)
SIDE_WORD = re.compile(r"(?<![a-z])(left|right|bilateral)(?![a-z])", re.I)
LAT = re.compile(r"^(left|right|bilateral)_")
DIGIT = re.compile(r"\d")


def props(r, which="norm"):
    return ((r.get(which) or {}).get("propositions")) or []


def codes(r):
    return collections.Counter(f["code"] for f in (r.get("findings") or []))


def metrics(r):
    m = collections.Counter()
    P = props(r)
    m["records"] = 1
    m["props"] = len(P)
    if not P:
        m["zero_props"] = 1
    c = codes(r)
    for k, v in c.items():
        m["code:" + k] += v
    m["errors"] = sum(1 for f in r.get("findings") or []
                      if f.get("severity") == "error")
    m["warnings_v"] = sum(1 for f in r.get("findings") or []
                          if f.get("severity") == "warning")
    if any(f.get("severity") == "error" for f in r.get("findings") or []):
        m["rec_with_error"] = 1

    # Label hygiene is read from the raw step 1 output, before step 2 hides it.
    for p in props(r, "raw"):
        ent = (p.get("entity") or {})
        if ent.get("type") == "device":
            m["device_props"] += 1
            if any(a.get("role") == "tip_location" for a in p.get("anatomy") or []):
                m["device_tip_located"] += 1
        for a in p.get("anatomy") or []:
            l = a.get("label") or ""
            if not l:
                continue
            m["anat_labels"] += 1
            if l in BARE:
                m["anat_bare_side"] += 1
            elif LAT.match(l):
                m["anat_lateral_prefix"] += 1
            # Not exclusive: a stripped leftover matches none of the above.
            if l in FRAGMENT:
                m["anat_side_fragment"] += 1
            if DIGIT.search(l):
                m["anat_digit"] += 1
        for d in p.get("descriptors") or []:
            l = d.get("label") or ""
            m["desc_labels"] += 1
            if l.startswith("tip_") or l.endswith("_position"):
                m["desc_device_position"] += 1
            if DIGIT.search(l):
                m["desc_digit"] += 1

    # Side bleed: only utterances with exactly one side word. If several
    # propositions then carry a side, one clause's side bled into another.
    # A coarse proxy -- two clauses can legitimately share a side.
    utt = r.get("utterance") or ""
    if len(SIDE_WORD.findall(utt)) == 1 and len(props(r, "raw")) > 1:
        m["bleed_records"] += 1
        m["bleed_props"] += len(props(r, "raw"))
        for p in props(r, "raw"):
            if any(a.get("laterality") in ("left", "right")
                   for a in p.get("anatomy") or []):
                m["bleed_sided_props"] += 1

    # -- v3 targets. Each one is a defect class measured on the corpus, and
    # each is read from the raw step 1 output, before step 2 can hide it.
    DERIVED = ("entity_semantics", "section_context", "linked_proposition")
    for p in props(r, "raw"):
        ent = p.get("entity") or {}
        ent_text = (ent.get("text") or "").lower()
        desc_words = set()
        for d in p.get("descriptors") or []:
            for w in ((d.get("text") or "") + " " + (d.get("label") or "")).lower().split():
                desc_words.add(w.strip(",.;"))
        label = ent.get("label") or ""
        # rule 3: a modifier the descriptor holds must not sit in the entity text
        if any(w and w in ent_text.split() for w in desc_words) and len(ent_text.split()) > 1:
            m["r3_text_has_descriptor"] += 1
        # rule 20: the label repeats a descriptor it already has a field for
        for w in desc_words:
            if w and w != label and (label.startswith(w + "_") or label.endswith("_" + w)):
                m["r20_label_repeats_descriptor"] += 1
                break
        for a in p.get("anatomy") or []:
            t = (a.get("text") or "").strip()
            m["anat_entries"] += 1
            # rule 18: a derived source cannot carry a span
            if a.get("source") in DERIVED and t:
                m["r18_derived_with_text"] += 1
            # rule 18: a side word alone is not the structure's span
            if t.lower().rstrip(".") in ("left", "right", "bilateral", "midline"):
                m["r18_side_only_span"] += 1
            # rule 18: a span that starts with a preposition is a relation
            if PREP.match(t):
                m["r18_prep_span"] += 1

    # rule 19: the utterance limits what could be read -- was it kept?
    if LIMIT.search(utt):
        m["limit_utterances"] += 1
        kept = any("limit" in (p.get("entity", {}).get("label") or "")
                   or (p.get("entity", {}).get("type") == "other"
                       and LIMIT.search(p.get("entity", {}).get("text") or ""))
                   for p in props(r, "raw"))
        warned = any(w.startswith("Assessment limited:")
                     for w in (r.get("raw") or {}).get("warnings") or [])
        if kept or warned:
            m["r19_limit_kept"] += 1

    # rule 11: a lower bound warns like a qualified negation does
    if LOWER_BOUND.search(utt):
        m["lower_bound_utterances"] += 1
        if any(w.startswith("Qualified assertion:")
               for w in (r.get("raw") or {}).get("warnings") or []):
            m["r11_lower_bound_warned"] += 1

    # how many labels step 2 had to fix
    for n in (r.get("norm") or {}).get("normalization") or []:
        if str(n.get("field", "")).endswith("label"):
            m["step2_label_fixes"] += 1
    return m


by_arm = collections.defaultdict(collections.Counter)
by_arm_stratum = collections.defaultdict(collections.Counter)
paired = collections.defaultdict(dict)
for r in rows:
    if "error" in r:
        by_arm[r["arm"]]["api_error"] += 1
        continue
    m = metrics(r)
    by_arm[r["arm"]] += m
    by_arm_stratum[(r["arm"], r["stratum"])] += m
    paired[r["utterance"]][r["arm"]] = m

both = [u for u, d in paired.items() if LEFT in d and RIGHT in d]
print(f"{LEFT} vs {RIGHT}  --  utterances parsed by both arms: {len(both)} / {len(paired)}\n")

A, B = by_arm[LEFT], by_arm[RIGHT]


def line(name, key, fmt="{:,}", denom=None):
    a, b = A[key], B[key]
    if denom:
        da, db = A[denom] or 1, B[denom] or 1
        sa, sb = f"{100*a/da:.1f}%", f"{100*b/db:.1f}%"
        extra = f"({a}/{da} → {b}/{db})"
    else:
        sa, sb = fmt.format(a), fmt.format(b)
        extra = ""
    arrow = "  " if a == b else ("↓" if b < a else "↑")
    print(f"  {name:38s} {sa:>10s} → {sb:>10s} {arrow} {extra}")


def stratum(arm, st):
    return by_arm_stratum[(arm, st)]


print("=== global ===")
line("records", "records")
line("propositions", "props")
line("records with 0 propositions", "zero_props", denom="records")
line("records with an error", "rec_with_error", denom="records")
line("findings (error)", "errors")
line("findings (warning)", "warnings_v")

print("\n=== label hygiene (raw step 1 output) ===")
line("anatomy label with a side prefix", "anat_lateral_prefix", denom="anat_labels")
line("anatomy label is a side, not a structure", "anat_bare_side", denom="anat_labels")
line("anatomy label contains a digit", "anat_digit", denom="anat_labels")
line("descriptor is a device position", "desc_device_position", denom="desc_labels")
line("descriptor label contains a digit", "desc_digit", denom="desc_labels")
line("anatomy label is a side leftover (sided/side)", "anat_side_fragment",
     denom="anat_labels")
line("side bleed proxy (coarse, small n)", "bleed_sided_props",
     denom="bleed_props")
line("device propositions using tip_location", "device_tip_located", denom="device_props")
line("labels step 2 had to fix", "step2_label_fixes")

print("\n=== v3 targets (raw step 1 output) ===")
line("rule 3  entity text holds a descriptor", "r3_text_has_descriptor")
line("rule 20 label repeats a descriptor", "r20_label_repeats_descriptor")
line("rule 18 derived source carries text", "r18_derived_with_text", denom="anat_entries")
line("rule 18 span is a side word only", "r18_side_only_span", denom="anat_entries")
line("rule 18 span starts with a preposition", "r18_prep_span", denom="anat_entries")
line("rule 19 limitation kept", "r19_limit_kept", denom="limit_utterances")
line("rule 11 lower bound warned", "r11_lower_bound_warned",
     denom="lower_bound_utterances")

print("\n=== per check code ===")
allc = sorted({k for k in list(A) + list(B) if k.startswith("code:")},
              key=lambda k: -(A[k] + B[k]))
print(f"  {'code':38s} {LEFT:>10s} → {RIGHT:>10s}")
for k in allc:
    a, b = A[k], B[k]
    arrow = "  " if a == b else ("↓" if b < a else "↑")
    print(f"  {k[5:]:38s} {a:>10,} → {b:>10,} {arrow}")

print("\n=== per-stratum target ===")
TARGET = {
    "S1_no_propositions": ("records with 0 propositions", "zero_props"),
    "S2_qualified_negation": ("qualified_negation_unwarned",
                              "code:qualified_negation_unwarned"),
    "S3_device_tip": ("device_tip_not_located", "code:device_tip_not_located"),
    "S4_text_not_in_utt": ("entity_text_not_in_utterance",
                           "code:entity_text_not_in_utterance"),
    "S5_section_conflict": ("section_conflict", "code:section_conflict"),
    "S6_split": ("propositions (more = more splitting)", "props"),
    "S7_lateral_label": ("anatomy labels carrying a side", None),
    "S8_clean": ("findings (an increase is a regression)", "errors"),
}
for st, (desc, key) in TARGET.items():
    a = stratum(LEFT, st)
    b = stratum(RIGHT, st)
    if key is None:
        av = a["anat_lateral_prefix"] + a["anat_bare_side"]
        bv = b["anat_lateral_prefix"] + b["anat_bare_side"]
    else:
        av, bv = a[key], b[key]
    if st == "S8_clean":
        av += a["warnings_v"]; bv += b["warnings_v"]
    arrow = "  " if av == bv else ("↓" if bv < av else "↑")
    print(f"  {st:22s} {desc:34s} {av:>6} → {bv:>6} {arrow}")
