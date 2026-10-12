#!/usr/bin/env python3
"""Shared loading, ontology access, classification and table output.

Two things this module pins down, because either one silently invalidates
every number downstream:

  WHICH ONTOLOGY  imported by absolute path, with no sys.path fallback. The
  data was normalized against this repo's tables; a metric computed against
  another copy measures the gap between two tables, not data quality.

  WHAT COUNTS AS A HIT  a label that came out of snake() unchanged and matched
  no table is a PASSTHROUGH -- canonical in form, untouched in meaning. The
  classification lives here so every section agrees on it.

Nothing in Verify/ calls a model, writes jsonl/, or mutates a record.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, Iterator, List, Optional, Tuple

# -- the repository this audit belongs to ------------------------------------
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# WHICH ARM. jsonl/ holds one directory per prompt package, because the same
# split extracted by a different prompt is a different dataset. Every number in
# a report is about one arm, so the arm is printed in the header next to the
# ontology fingerprint. Set with REPORTCXR_ARM or run.py --arm.
ARM = os.environ.get("REPORTCXR_ARM", "Prompt")
JSONL_DIR = os.path.join(REPO, "jsonl", ARM)


def set_arm(arm: str) -> None:
    """Point the loader at another arm's directory."""
    global ARM, JSONL_DIR
    ARM = arm
    JSONL_DIR = os.path.join(REPO, "jsonl", arm)

if REPO not in sys.path:
    sys.path.insert(0, REPO)

from Prompt2 import ontology as ONT         # noqa: E402
from Prompt2 import vocabulary as VOCAB     # noqa: E402

SPLITS = ["train", "validate", "test", "test_reviewed"]
# train is 800MB and is left out by default.
SMALL = ["validate", "test", "test_reviewed"]

RADLEX_TSV = os.path.join(REPO, "RadLex", "radlex_terms.tsv")

_WS = re.compile(r"\s+")
_TOK = re.compile(r"[a-z0-9]+")      # toks(): offset-preserving tokenizer
_PUNCT = re.compile(r"[^a-z0-9 ]+")  # unsnake(): label/surface normalization


def _canon(obj: Any) -> Any:
    """Order- and whitespace-stable form of a table, for hashing.

    Dict keys are sorted -- two tables that hold the same mapping hash the
    same regardless of definition order or a comment moved between entries.
    List/tuple order is kept: several tables (LATERALITY_WORDS, ZONE_WORDS)
    match longest-prefix-first, so their order is meaning, not formatting.
    """
    if isinstance(obj, dict):
        return sorted((k, _canon(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(_canon(x) for x in obj)
    return obj


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()[:16]


def ontology_content_hash() -> str:
    """One hash over every public table in Prompt2/ontology.py's *content*.

    Not the file's bytes: a comment or a re-wrapped line must not change
    this, or a no-op edit reads as a new ontology. Only the tables -- the
    thing normalize.py and every prompt actually consult -- can move it.
    """
    names = sorted(n for n in dir(ONT) if n.isupper() and not n.startswith("_"))
    tables = {n: _canon(getattr(ONT, n)) for n in names}
    blob = json.dumps(tables, sort_keys=True, ensure_ascii=False,
                       default=str).encode("utf-8")
    return _sha(blob)


# Code whose drift changes what normalize() does to a record, independent of
# the ontology tables it reads. Paths are relative to REPO.
_NORMALIZER_CODE = [
    "Pipeline/normalize.py",
    "Pipeline/validate.py",
    "Pipeline/renormalize.py",
]


def code_fingerprint() -> Dict[str, Optional[str]]:
    """sha256[:16] of each normalizer file, or None if it is missing."""
    out: Dict[str, Optional[str]] = {}
    for rel in _NORMALIZER_CODE:
        path = os.path.join(REPO, rel)
        try:
            with open(path, "rb") as fh:
                out[rel] = _sha(fh.read())
        except OSError:
            out[rel] = None
    return out


def data_fingerprint(splits: List[str]) -> Dict[str, Dict[str, Any]]:
    """sha256[:16] + record count of each split's jsonl, cached by (size, mtime).

    train.jsonl is 800MB; hashing it on every report run would make --all
    slow enough that nobody does it. The cache in
    jsonl/<arm>/.fingerprint.json is keyed on (size, mtime_ns), so a file
    that was actually rewritten -- like today's 49,405-record change -- is
    rehashed, and one that was not is read from cache in O(1).
    """
    cache_path = os.path.join(JSONL_DIR, ".fingerprint.json")
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        cache = {}

    out: Dict[str, Dict[str, Any]] = {}
    dirty = False
    for split in splits:
        path = split_path(split)
        if not os.path.exists(path):
            continue
        st = os.stat(path)
        entry = cache.get(split)
        if (entry and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns):
            out[split] = entry
            continue
        h = hashlib.sha256()
        records = 0
        with open(path, "rb") as fh:
            for line in fh:
                h.update(line)
                if line.strip():
                    records += 1
        out[split] = {
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": h.hexdigest()[:16],
            "records": records,
        }
        dirty = True

    if dirty:
        cache.update(out)
        try:
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, indent=2, sort_keys=True)
        except OSError:
            pass  # a report must not fail because the cache is unwritable

    return out


def ontology_fingerprint() -> Dict[str, Any]:
    """Table sizes plus content/code/data hashes, so a report says which
    ontology, which normalizer and which jsonl files produced it.

    Sizes alone (the pre-2026-09-14 version of this function) only catch a
    table gaining or losing an entry. A same-length edit -- or a comment
    that changes the file's bytes but not its tables -- and, above all, the
    jsonl files being rewritten with the same code and the same table both
    passed through silently. That is exactly what happened on 2026-09-14:
    the head-of-report table was identical while 49,405 records changed
    underneath it. The hashes below are what would have caught it.
    """
    return {
        "path": ONT.__file__,
        "ANATOMY": len(ONT.ANATOMY),
        "ANATOMY_ALIASES": len(ONT.ANATOMY_ALIASES),
        "ENTITY_ALIASES": len(ONT.ENTITY_ALIASES),
        "DESCRIPTOR_LEXICON": len(ONT.DESCRIPTOR_LEXICON),
        "SIDED_MIDLINE": len(getattr(ONT, "SIDED_MIDLINE", ()) or ()),
        "content_hash": ontology_content_hash(),
        "code": code_fingerprint(),
    }


# =============================================================================
#  LOADING
# =============================================================================

def split_path(split: str) -> str:
    return os.path.join(JSONL_DIR, f"{split}.jsonl")


def available_splits() -> List[str]:
    return [s for s in SPLITS if os.path.exists(split_path(s))]


def studies(split: str) -> Iterator[Dict[str, Any]]:
    """One study per line. Streamed: train.jsonl is 800 MB."""
    with open(split_path(split), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def records(split: str, limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
    """Every utterance record, with `study_id` attached for traceability."""
    n = 0
    for study in studies(split):
        sid = study.get("id")
        for rec in study.get("records") or []:
            rec = dict(rec, study_id=sid)
            yield rec
            n += 1
            if limit and n >= limit:
                return


def propositions(split: str, limit: Optional[int] = None
                 ) -> Iterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """(record, proposition) pairs. The record is needed for its utterance."""
    for rec in records(split, limit):
        for prop in rec.get("propositions") or []:
            yield rec, prop


def norm_text(text: Optional[str]) -> str:
    """The form two surface mentions are compared in."""
    return _WS.sub(" ", (text or "").strip().lower())


# =============================================================================
#  WHAT THE ONTOLOGY DECIDED
# =============================================================================
#  Three outcomes, and the middle one is the one that matters:
#
#     table       a table named this label. Normalization made a decision.
#     alias       a table REWROTE something into this label. Strongest signal.
#     passthrough nothing matched. snake() lowercased it and it shipped.
#
#  A high passthrough rate is not automatically wrong -- a report vocabulary
#  has a long tail and no table will ever cover it -- but it is the ceiling on
#  how much of the canonicalization is actually attributable to the ontology.

_ENTITY_TARGETS = set(ONT.ENTITY_ALIASES.values())
_ENTITY_TYPED = set(ONT.DISEASE_LABELS) | set(ONT.DEVICE_LABELS)
_ANATOMY_TARGETS = set(ONT.ANATOMY_ALIASES.values())
_DESCRIPTOR_VALUES = {v for _, v in ONT.DESCRIPTOR_LEXICON.values()}


def classify_entity(label: Optional[str]) -> str:
    if not label:
        return "missing"
    if label in _ENTITY_TARGETS:
        return "alias"
    if label in _ENTITY_TYPED:
        return "table"
    return "passthrough"


def classify_anatomy(label: Optional[str]) -> str:
    if not label:
        return "missing"          # legal: entity_semantics / section_context
    if label in ONT.ANATOMY:
        return "table"
    if label in _ANATOMY_TARGETS:
        return "alias"
    return "passthrough"


def classify_descriptor(label: Optional[str]) -> str:
    if not label:
        return "missing"
    if label in _DESCRIPTOR_VALUES:
        return "table"
    return "passthrough"


# =============================================================================
#  WHAT A METRIC RETURNS
# =============================================================================
#  A metric used to return markdown and nothing else, so the only way to learn
#  what it concluded was to read its prose. That is fine for one combined
#  report and useless for twenty files: an index has to say, in one row per
#  metric, whether the thing passed.
#
#  So a metric returns a Result. `verdict` is the row in the index, `headline`
#  is the one number that verdict rests on, and `body` is the markdown it
#  always produced. Returning a bare string still works -- it becomes a Result
#  with verdict UNKNOWN -- so a metric not yet converted is not a broken one.

PASS    = "PASS"       # nothing to fix
WARN    = "WARN"       # real signal, not a blocker
FAIL    = "FAIL"       # must be fixed before the numbers mean anything
INFO    = "INFO"       # a list for a human; no pass/fail to give
BLIND   = "BLIND"      # the metric could not see -- coverage too low to judge
SKIP    = "SKIP"       # a prerequisite is missing
UNKNOWN = "UNKNOWN"

_MARK = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL", INFO: "INFO",
         BLIND: "BLIND", SKIP: "SKIP", UNKNOWN: "-"}


class Result:
    """What one metric concluded, plus the markdown that shows the work."""

    def __init__(self, body: str, verdict: str = UNKNOWN, headline: str = "",
                 numbers: Optional[Dict[str, Any]] = None) -> None:
        self.body = body
        self.verdict = verdict
        self.headline = headline
        self.numbers = numbers or {}

    @property
    def mark(self) -> str:
        return _MARK.get(self.verdict, self.verdict)

    @staticmethod
    def of(value: Any) -> "Result":
        """Accept a Result or the bare markdown an unconverted metric returns."""
        return value if isinstance(value, Result) else Result(str(value))


def worst(verdicts) -> str:
    """The verdict a group of metrics gets: the most severe one present."""
    order = [FAIL, BLIND, WARN, SKIP, UNKNOWN, INFO, PASS]
    present = set(verdicts)
    for v in order:
        if v in present:
            return v
    return UNKNOWN


# =============================================================================
#  REPORTING
# =============================================================================

def pct(part: int, whole: int) -> str:
    return "  -  " if not whole else f"{100.0 * part / whole:5.2f}%"


def table(rows: List[List[Any]], head: List[str]) -> str:
    """A markdown table, so run_all.py's output pastes into a report."""
    # A cell holding a literal "|" ends the column early and silently shifts
    # every value after it one column left. Headlines are prose and do carry
    # pipes, so escape rather than trusting callers.
    cells = [[str(c).replace("|", "\\|") for c in r] for r in rows]
    width = [max(len(head[i]), *(len(r[i]) for r in cells)) if cells
             else len(head[i]) for i in range(len(head))]
    out = ["| " + " | ".join(h.ljust(width[i]) for i, h in enumerate(head)) + " |",
           "|" + "|".join("-" * (w + 2) for w in width) + "|"]
    for r in cells:
        out.append("| " + " | ".join(r[i].ljust(width[i])
                                     for i in range(len(head))) + " |")
    return "\n".join(out)


def section(title: str) -> str:
    """A heading inside a metric's measured output.

    Level 3, not 2: in a metric file these sit under "## 2. 현재 데이터가
    어떤가", so a level-2 heading here would be that section's sibling and the
    file would read as if the per-split results were a third top-level part.
    """
    return f"\n### {title}\n"


def summary(rows: List[List[Any]], head: List[str], note: str = "") -> str:
    """The cross-split table that opens a metric's measured output.

    Every metric leads with one row per split, because the question a reader
    brings to four splits is comparative before it is absolute: 25% on test
    means one thing if train is 24% and another if train is 3%. A split that
    stands out is either a data problem or a sampling artifact, and neither is
    visible in four separate per-split sections further down the page.
    """
    out = ["\n**Per split**\n", table(rows, head)]
    if note:
        out.append("\n" + note)
    return "\n".join(out) + "\n"


def example_note(split: str) -> str:
    """The line that says why only one split's sentences are shown."""
    return (f"\n> **예시 행은 `{split}` 에서만 뽑는다.** 위 표의 숫자는 전 split "
            f"을 덮지만, 같은 결함은 어느 split 에서나 같은 모양이므로 네 벌의 "
            f"예시는 읽을거리만 네 배가 되고 새로 알려 주는 것이 없다. "
            f"`{split}` 인 이유는 **사람이 실제로 손으로 들여다보는 split** 이기 "
            f"때문이다. 다른 split 의 예시가 필요하면 "
            f"`run.py --examples-from <split>` 또는 `--examples-from all`.\n")


def provenance(splits: List[str]) -> str:
    """The three fingerprint tables every report file must carry.

    One combined report could print these once at the top. Twenty files
    cannot: a file that travels on its own without saying which ontology,
    which normalizer and which jsonl produced it is a number with no referent,
    and two such files get compared by someone who has no way to know they
    should not be. So every metric file repeats them.
    """
    fp = ontology_fingerprint()
    data = data_fingerprint(splits)
    return "\n".join([
        table([[fp["path"].replace(REPO + os.sep, ""), fp["ANATOMY"],
                fp["ANATOMY_ALIASES"], fp["ENTITY_ALIASES"],
                fp["DESCRIPTOR_LEXICON"], fp["SIDED_MIDLINE"],
                fp["content_hash"]]],
              ["ontology", "ANATOMY", "ANAT_ALIASES", "ENTITY_ALIASES",
               "DESC_LEXICON", "SIDED_MIDLINE", "content_hash"]),
        "",
        table([[rel, h or "MISSING"] for rel, h in fp["code"].items()],
              ["normalizer code", "sha256"]),
        "",
        table([[s, data[s]["sha256"], data[s]["records"]]
               for s in splits if s in data],
              ["split", "sha256", "studies"]),
    ])


def unsnake(t: Optional[str]) -> str:
    return norm((t or "").replace("_", " "))

def spans_of(prop: Dict[str, Any]) -> Iterator[Optional[str]]:
    """Every string this proposition took from the utterance."""
    yield (prop.get("entity") or {}).get("text")
    for a in prop.get("anatomy") or []:
        yield a.get("text")
    for d in prop.get("descriptors") or []:
        yield d.get("text")
    for k in ("assertion", "comparison"):
        yield (prop.get(k) or {}).get("cue")

def covered_ranges(record: Dict[str, Any]) -> List[tuple]:
    """The [start, end) ranges the extracted spans occupy in the utterance.

    Offsets, not string replacement: replacement leaves 'catheter' behind in
    "...central catheter (PICC) line..." and reports a false miss.
    """
    utt = (record.get("utterance") or "").lower()
    out = []
    for p in record.get("propositions") or []:
        for s in spans_of(p):
            if not s:
                continue
            s = s.lower().strip()
            i = utt.find(s)
            while i >= 0:
                out.append((i, i + len(s)))
                i = utt.find(s, i + 1)
    return out

def toks(text: Optional[str]) -> List[tuple]:
    return [(m.group(0), m.start(), m.end())
            for m in _TOK.finditer((text or "").lower())]

def load_radlex():
    """Normalized surface -> (rid, branch), or (None, None)."""
    if not os.path.exists(RADLEX_TSV):
        return None
    surf = {}
    with open(RADLEX_TSV, encoding="utf-8") as f:
        head = next(f).rstrip("\n").split("\t")
        bi = head.index("branch") if "branch" in head else None
        for line in f:
            p = line.rstrip("\n").split("\t")
            rid, label, syns = p[0], p[1], p[2]
            br = p[bi] if bi is not None and len(p) > bi else ""
            for s in [label] + syns.split("|"):
                if s:
                    surf.setdefault(norm(s), (rid, br))
    return surf

RADLEX_CLINICAL = {
    "RID3": "anatomical entity", "RID34785": "clinical finding",
    "RID5": "imaging observation", "RID34861": "object",
    "RID7479": "non-anatomical substance",
}


# short alias for ontology_fingerprint
fingerprint = ontology_fingerprint
# short aliases kept for older modules
norm = norm_text

__all__ = [
    "REPO", "JSONL_DIR", "ARM", "set_arm", "SPLITS", "ONT", "VOCAB",
    "ontology_fingerprint", "split_path", "available_splits",
    "studies", "records", "propositions", "norm_text",
    "classify_entity", "classify_anatomy", "classify_descriptor",
    "pct", "table", "section", "SMALL", "fingerprint",
    "unsnake", "spans_of", "covered_ranges", "toks", "load_radlex",
    "Result", "worst", "PASS", "WARN", "FAIL", "INFO", "BLIND", "SKIP",
    "UNKNOWN", "data_fingerprint", "code_fingerprint", "provenance",
    "summary", "example_note",
    "RADLEX_CLINICAL", "RADLEX_TSV",
]
