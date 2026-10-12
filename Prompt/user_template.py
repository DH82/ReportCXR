"""Section 4 -- the user message: few-shot examples, then the utterance.

Examples are inlined here, not sent as prior assistant turns, and JSON is
rendered with a fixed key order so two runs give byte-identical prompts.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# Section 4, verbatim.
USER_TEMPLATE = """Parse this SRRG chest X-ray utterance.

{
  "utterance_id": "{{ID}}",
  "utterance": "{{UTTERANCE}}",
  "section": "{{SECTION_OR_NULL}}"
}

Return JSON only.
"""

_HEADER = ("Worked examples. Each shows one utterance and the propositions "
           "it produces.\n")


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def input_block(utterance_id: Optional[str], utterance: str,
                section: Optional[str]) -> str:
    """The Section 4 input object. null stays null; it is not the string."""
    return _json({"utterance_id": utterance_id, "utterance": utterance,
                  "section": section})


def render_example(ex: Dict[str, Any], n: int) -> str:
    inp = ex["input"]
    return (f"### Example {n}\n"
            f"Input:\n{input_block(inp.get('utterance_id'), inp['utterance'], inp.get('section'))}\n"
            f"Output:\n{_json(ex['output'])}\n")


def render(utterance_id: Optional[str], utterance: str,
           section: Optional[str],
           examples: Optional[List[Dict[str, Any]]] = None) -> str:
    """The full user message: examples, then the utterance to parse."""
    parts: List[str] = []
    if examples:
        parts.append(_HEADER)
        for n, ex in enumerate(examples, 1):
            parts.append(render_example(ex, n))
        parts.append("### Now parse this one\n")
    parts.append("Parse this SRRG chest X-ray utterance.\n")
    parts.append(input_block(utterance_id, utterance, section))
    parts.append("\nReturn JSON only.")
    return "\n".join(parts)


__all__ = ["USER_TEMPLATE", "render", "render_example", "input_block"]
