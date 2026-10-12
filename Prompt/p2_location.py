"""
Prompt 2 -- location.

Condenses Appendix A.1.1 prompts 9, 10 and 11: the model filters to
anatomical expressions inline instead of classifying each one in a
separate call.  Placeholders: {sentence}, {label}.  Stage id: q2.

maplez_struct.py imports from here; nothing in this package imports back.
"""

P2 = ('Given the line "{sentence}" from a chest X-ray report, list the '
      'localizing expressions characterizing specifically the "{label}" '
      'finding. Break the answer down into each and every one of the localizing '
      'adjectives and each independent localizing prepositional phrase, one per '
      'list element. Output an empty list if there are 0 locations mentioned '
      'for "{label}". Do not mention the central nouns identified as "{label}". '
      'Do not mention any nouns that are not part of an adjective. Include only '
      'anatomical location: leave out severity, size, comparison, probability '
      'and visual texture words, and leave out expressions that belong to '
      'another finding. Use very short answers without complete sentences.')

S_EXPRESSIONS = {
    "type": "object",
    "properties": {
        "expressions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["expressions"],
}
