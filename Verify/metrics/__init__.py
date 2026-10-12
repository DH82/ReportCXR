"""One file per evaluation element.

The rule for what gets its own file: a metric is one file when it has one
verdict. Two questions that can pass and fail independently -- under- and
over-normalization, the three branches of P1 -- were sharing a file, which
meant sharing a verdict, and a shared verdict is no verdict: a file that is
half PASS and half WARN reports neither.

Files starting with `_` are shared measurement, not metrics. run.py discovers
only `mNN_*.py`, so a helper two metrics both need lives in `_name.py` and is
measured once.
"""
