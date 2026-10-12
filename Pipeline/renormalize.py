#!/usr/bin/env python3
"""Re-apply step 2 to jsonl/ -- the only tool in this repo that writes there.

Normalization is idempotent, so on a correct file this changes nothing; what it
does change is the residue that section 0 reports.

Five guards, and a failure in any one means nothing is written:

  1. backup     the file's sha256 must appear in a backup SHA256SUMS
                (--no-backup-check)
  2. drift      the normalizer actually used must match the one in Pipeline/
                (--allow-drift)
  3. schema     input and output key sets must match per record, ignoring the
                normalization field; section S compares keys strictly
  4. metric C   study ids, utterance ids, utterance text and counts must all
                survive, compared by hash
  5. atomic     written to <file>.tmp, then os.replace

    python3 renormalize.py --dry-run                 # everything, writes nothing
    python3 renormalize.py --split test_reviewed     # one split, for real
    python3 renormalize.py                           # everything
"""

from __future__ import annotations

import argparse
import copy
import datetime
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ARM = os.environ.get("REPORTCXR_ARM", "Prompt")   # jsonl/<arm>/, see --arm
JSONL_DIR = os.path.join(REPO, "jsonl", ARM)
FROZEN = os.path.join(HERE, "normalize.py")

# There used to be a second copy of normalize.py in another repo and this
# checked drift against it. One copy now, so the only question left is whether
# the normalizer about to run is this repo's -- which was always the important one.
RUNNER_COPY = None
BACKUP_GLOB = "/data3/backup/ReportCXR-Ko/*/SHA256SUMS"

SPLITS = ["train", "validate", "test", "test_reviewed"]
REC_KEYS = {"utterance_id", "utterance", "section", "propositions", "warnings"}

if REPO not in sys.path:
    sys.path.insert(0, REPO)


# =============================================================================
#  Guards
# =============================================================================

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backed_up(path: str) -> tuple[bool, str]:
    """Is this file's content listed in any backup manifest?"""
    digest = sha256_file(path)
    for manifest in glob.glob(BACKUP_GLOB):
        with open(manifest) as f:
            for line in f:
                if line.split()[0] == digest:
                    return True, os.path.dirname(manifest)
    return False, digest


def check_drift(chosen: str) -> tuple[bool, list[str]]:
    """Is the normalizer we will actually use the frozen one?

    Both halves matter: without the first, --normalize could pass any file.
    """
    frozen = sha256_file(FROZEN)
    lines, ok = [], True

    chosen_abs = os.path.abspath(chosen)
    if chosen_abs == os.path.abspath(FROZEN):
        lines.append(f"normalizer in use = the copy in Pipeline/  ({frozen[:16]}...)")
    else:
        got = sha256_file(chosen_abs)
        same = got == frozen
        lines.append(f"normalizer in use = {chosen_abs}")
        lines.append(f"      {got}  {'(identical)' if same else '<- DIFFERS'}")
        if not same:
            ok = False

    if RUNNER_COPY:
        if not os.path.exists(RUNNER_COPY):
            lines.append(f"no second copy ({RUNNER_COPY})")
        else:
            rc = sha256_file(RUNNER_COPY)
            if rc == frozen:
                lines.append("second copy is identical")
            else:
                lines.append(f"second copy DIFFERS\n      {RUNNER_COPY}\n      {rc}")
                ok = False
    else:
        lines.append("only one copy exists in this repository")
    return ok, lines


def load_normalizer(path: str):
    """Same contract as Verify/metrics/m03_fixed_point.py.

    An external checkout's package path is APPENDED, never prepended, so the
    ontology is always this repo's whichever normalize.py is loaded.
    """
    import importlib.util
    pkg_dir = os.path.dirname(os.path.abspath(path))
    if pkg_dir in sys.path:
        sys.path.remove(pkg_dir)
    sys.path.append(pkg_dir)
    spec = importlib.util.spec_from_file_location("_norm_step2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# =============================================================================
#  Metric C preservation
# =============================================================================

class RoundTripGuard:
    """Folds study ids, utterance ids, text and counts into hashes to compare."""

    def __init__(self) -> None:
        self.h = hashlib.sha256()
        self.studies = 0
        self.utterances = 0
        self.propositions = 0

    def feed(self, study: dict) -> None:
        self.studies += 1
        self.h.update(str(study.get("id")).encode())
        self.h.update(str(study.get("split")).encode())
        for rec in study.get("records") or []:
            self.utterances += 1
            self.propositions += len(rec.get("propositions") or [])
            self.h.update(str(rec.get("utterance_id")).encode())
            self.h.update(b"\x00")
            self.h.update(str(rec.get("utterance")).encode())
            self.h.update(b"\x01")

    @property
    def digest(self) -> str:
        return self.h.hexdigest()

    def same_as(self, other: "RoundTripGuard") -> tuple[bool, str]:
        if self.digest != other.digest:
            return False, "study id / utterance id / text hash mismatch"
        if (self.studies, self.utterances) != (other.studies, other.utterances):
            return False, (f"count mismatch: studies {self.studies}->{other.studies} "
                           f"utterance {self.utterances}->{other.utterances}")
        return True, "preserved"


# =============================================================================
#  Main
# =============================================================================

def process_split(mod, split: str, dry_run: bool) -> dict:
    src = os.path.join(JSONL_DIR, f"{split}.jsonl")
    tmp = src + ".tmp"

    before_g, after_g = RoundTripGuard(), RoundTripGuard()
    changed_records = 0
    changed_fields: dict[str, int] = {}
    notes: dict[str, int] = {}
    key_faults = 0

    out = None if dry_run else open(tmp, "w", encoding="utf-8")
    try:
        with open(src, encoding="utf-8") as f:
            for line in f:
                study = json.loads(line)
                before_g.feed(study)

                new_records = []
                for rec in study.get("records") or []:
                    src_keys = set(rec)
                    after = mod.normalize_record(copy.deepcopy(rec))
                    for n in after.pop("normalization", []) or []:
                        notes[n["code"]] = notes.get(n["code"], 0) + 1

                    # guard 3: schema preserved
                    if set(after) != src_keys:
                        key_faults += 1
                        for k in set(after) - src_keys:
                            after.pop(k, None)

                    if after != rec:
                        changed_records += 1
                        if rec.get("section") != after.get("section"):
                            changed_fields["section"] = \
                                changed_fields.get("section", 0) + 1
                        for p0, p1 in zip(rec.get("propositions") or [],
                                          after.get("propositions") or []):
                            for k in p0:
                                if p0.get(k) != p1.get(k):
                                    changed_fields[k] = \
                                        changed_fields.get(k, 0) + 1
                    new_records.append(after)

                study["records"] = new_records
                after_g.feed(study)
                if out is not None:
                    out.write(json.dumps(study, ensure_ascii=False) + "\n")
    except BaseException:
        if out is not None:
            out.close()
            os.unlink(tmp)
        raise
    if out is not None:
        out.flush()
        os.fsync(out.fileno())
        out.close()

    ok, why = before_g.same_as(after_g)
    res = {"split": split, "studies": before_g.studies,
           "utterances": before_g.utterances,
           "propositions_before": before_g.propositions,
           "propositions_after": after_g.propositions,
           "changed_records": changed_records,
           "changed_fields": sorted(changed_fields.items(), key=lambda x: -x[1]),
           "notes": sorted(notes.items(), key=lambda x: -x[1])[:12],
           "notes_all": dict(sorted(notes.items(), key=lambda x: -x[1])),
           "key_faults": key_faults, "roundtrip_ok": ok, "roundtrip_why": why,
           "written": False}

    if dry_run:
        return res
    if not ok:                                   # guard 4
        os.unlink(tmp)
        return res
    if key_faults:                               # guard 3
        os.unlink(tmp)
        return res
    os.replace(tmp, src)                         # guard 5: atomic replace
    res["written"] = True
    return res


NOTES_DIR = os.path.join(REPO, "out", "normalization")
MAX_HISTORY = 20


def write_notes(results, arm: str) -> str:
    """Append what step 2 changed to a per-split history, outside the records.

    Step 2 destroys its own evidence. `normalize_descriptor` overwrites
    `descriptor.type` to whatever DESCRIPTOR_LEXICON says, so afterwards the
    data agrees with the table by construction and metric 1-E's conflict count
    is structurally zero -- it reads an enforced agreement as a clean result.
    The model's own answer is gone: the shipped record carries only
    text/type/label, and metric S counts a leaked `normalization` field as a
    fault, so it cannot be kept there either.

    WHY A HISTORY AND NOT THE LAST RUN.  The first version of this kept only
    the latest pass and lost the number within the hour. A file at its fixed
    point changes nothing on the next run BY DEFINITION, so any later pass --
    including one that touched two records -- overwrote "the table corrected
    the model 2,135 times" with a row of zeros. The number that matters is the
    last run on which a note actually fired, which needs the history to find.

    Capped at MAX_HISTORY entries; the oldest fall off.
    """
    os.makedirs(NOTES_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    for r in results:
        path = os.path.join(NOTES_DIR, f"{arm}_{r['split']}_notes.json")
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            doc = {}
        history = doc.get("history") or []
        # A sidecar written before the history existed still holds one run.
        if not history and doc.get("notes"):
            history.append({k: doc.get(k) for k in
                            ("applied", "dry_run", "ontology_content_hash",
                             "changed_records", "changed_fields", "notes")})
        history.append({
            "applied": stamp,
            "dry_run": not r["written"],
            "ontology_content_hash": ontology_content_hash(),
            "changed_records": r["changed_records"],
            "changed_fields": dict(r["changed_fields"]),
            "notes": r.get("notes_all") or {},
        })
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"arm": arm, "split": r["split"],
                       "records": r["studies"], "utterances": r["utterances"],
                       "history": history[-MAX_HISTORY:]},
                      fh, ensure_ascii=False, indent=2, sort_keys=True)
    return NOTES_DIR


def ontology_content_hash() -> str:
    """Same fingerprint Verify prints, so a sidecar says which table it is for."""
    sys.path.insert(0, os.path.join(REPO, "Verify"))
    import core                                   # noqa: E402
    return core.ontology_content_hash()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", action="append", choices=SPLITS,
                    help="default: every split")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    ap.add_argument("--normalize", default=FROZEN,
                    help=f"path to normalize.py (default: {FROZEN})")
    ap.add_argument("--no-backup-check", action="store_true")
    ap.add_argument("--allow-drift", action="store_true")
    a = ap.parse_args()
    splits = a.split or SPLITS

    print("=" * 78)
    print(f"renormalize     {'DRY RUN' if a.dry_run else 'WRITING'}")
    print("=" * 78)

    # --- guard 2: drift ------------------------------------------------------
    ok, lines = check_drift(a.normalize)
    print("\n[2] normalize.py drift")
    for ln in lines:
        print(f"    {ln}")
    if not ok and not a.allow_drift:
        print("\nRefused: the normalizer to be used differs from this repo's copy.")
        print("      Decide which one is right, or pass --allow-drift if intended.")
        return 2

    # --- guard 1: backup -----------------------------------------------------
    print("\n[1] backup check")
    missing = []
    for sp in splits:
        p = os.path.join(JSONL_DIR, f"{sp}.jsonl")
        found, info = backed_up(p)
        print(f"    {sp:14} {'OK  ' + info if found else 'MISSING  sha256=' + info}")
        if not found:
            missing.append(sp)
    if missing and not (a.no_backup_check or a.dry_run):
        print(f"\nRefused: no backup for -> {missing}")
        print("      Make a backup first, or pass --no-backup-check.")
        return 2

    mod = load_normalizer(a.normalize)

    results = []
    for sp in splits:
        print(f"\n{'-' * 78}\n{sp}\n{'-' * 78}")
        r = process_split(mod, sp, a.dry_run)
        results.append(r)
        print(f"  study {r['studies']}  utterance {r['utterances']}  "
              f"proposition {r['propositions_before']} -> {r['propositions_after']}")
        print(f"  [4] metric C     : {r['roundtrip_why']}")
        print(f"  [3] schema faults: {r['key_faults']}")
        print(f"  changed records  : {r['changed_records']}")
        if r["changed_fields"]:
            print(f"    by field       : {r['changed_fields']}")
        if r["notes"]:
            print(f"    notes          : {r['notes']}")
        print(f"  [5] write        : {'written' if r['written'] else 'DRY RUN' if a.dry_run else 'refused'}")

    bad = [r for r in results if not r["roundtrip_ok"] or r["key_faults"]]
    print("\n" + "=" * 78)
    if bad:
        print(f"Failed: {[r['split'] for r in bad]} -- nothing was written.")
        return 1
    total = sum(r["changed_records"] for r in results)
    print(f"Done. {total} records changed. "
          f"{'Nothing written (dry run).' if a.dry_run else 'Written.'}")
    try:
        print(f"Notes    -> {write_notes(results, ARM)}/  "
              f"(what step 2 changed; metric 1-E reads this)")
    except Exception as e:      # a sidecar must never fail the run
        print(f"Notes    -> not written: {type(e).__name__}: {e}")
    print("Next: python3 Verify/tools/diff_probe.py <split> to confirm NET diff 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
