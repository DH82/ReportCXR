"""
Section 4 -- the user message.

USER_TEMPLATE is Section 4 verbatim. render() is what actually goes on the
wire: the few-shot examples selection.py chose, then the target utterance in
the Section 4 shape.

Why the examples are inlined in the user message rather than sent as prior
assistant turns:

  * In tool mode a prior assistant turn has to be a tool_call message with a
    matching tool result, and llama.cpp's chat template renders those
    differently per model. An example that renders wrong teaches the wrong
    thing, silently.
  * The system prompt is byte-identical on every call, so it stays in the KV
    cache (qwen_client.py sends cache_prompt). The examples change per
    utterance and would break the cache wherever they were put; putting them
    in the user message at least keeps the break after the system prompt.

The input JSON is rendered with sorted keys off and a fixed key order, so two
runs over the same utterance produce byte-identical prompts.

qwen_client.py imports render(); nothing in this package imports back.
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
