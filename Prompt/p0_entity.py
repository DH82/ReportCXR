"""
Prompt 0 -- which single finding is this line about.

This script's own prompt; it has no counterpart in the paper, which
worked from a fixed list of thirteen abnormalities instead.
Placeholders: {section}, {sentence}.  Stage id: e0.

maplez_struct.py imports from here; nothing in this package imports back.
"""

from Prompt.vocabulary import ENTITY_TYPES

P0 = ('A chest X-ray report contains the following line under the heading '
      '"{section}": "{sentence}". '
      'Name the one medical observation or finding that this line is about. '
      'Follow these rules. '
      '(1) Return exactly one entity, the one the line is primarily about. If '
      'the line names further findings, list their names in "other_candidates" '
      'and describe none of them. '
      '(2) "term" is the standard English name of the finding: lower case, '
      'singular, with every modifier removed. Remove laterality, size, '
      'severity, negation and comparison words. "small right pleural effusion" '
      'gives "pleural effusion"; "no evidence of pneumothorax" gives '
      '"pneumothorax"; "New pulmonary vascular cephalization" gives "pulmonary '
      'vascular cephalization". '
      '(3) When the line denies a finding or calls a structure normal, name the '
      'finding that is being denied, not the normality. "the lungs are clear" '
      'gives "lung opacity"; "normal mediastinal contours" gives "mediastinal '
      'abnormality". '
      '(4) "mention" is copied verbatim from the line, as a substring. '
      '(5) entity_type: "imaging_finding" for something seen on the image, '
      '"diagnosis" for an interpretation of it (pneumonia, malignancy), '
      '"device" for lines, tubes and hardware, "procedure" for surgical or '
      'interventional history (status post lobectomy, CABG), "technical" for '
      'image quality statements (low lung volumes, rotated, motion artifact), '
      'and "none" when the line describes no imaging finding, device or '
      'procedure at all. A clinical symptom or piece of history -- shortness of '
      'breath, fever, chest pain, a stated indication for the exam -- is not an '
      'imaging finding and must be answered with "none" and an empty term.')

S_ENTITY = {
    "type": "object",
    "properties": {
        "term": {"type": "string"},
        "entity_type": {"type": "string", "enum": ENTITY_TYPES},
        "mention": {"type": "string"},
        "other_candidates": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["term", "entity_type", "mention", "other_candidates"],
}
