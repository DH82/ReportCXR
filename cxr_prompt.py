#!/usr/bin/env python3
"""
ReportCXR2 — 프롬프트 전부. 이 파일에는 프롬프트만 있다.

`Prompt/` 패키지가 여섯 모듈에 나눠 들고 있는 것을, 모델에 실제로 나가는 형태
그대로 한 파일에 합친 것이다. 호출도, 정규화도, 검증도 여기에 없다.
쓰는 쪽은 cxr_run.py.

    from cxr_prompt import build, TOOL_NAME, TOOL_SCHEMA
    text = build("There is no pleural effusion.", section="Pleura")

## 무엇을 {} 로 채우게 되어 있나

PROMPT 안의 치환 자리는 네 개뿐이고, 전부 str.format() 이름 인자다.

    {examples}       few-shot 예시 블록. 기본값은 아래 EXAMPLES
    {utterance_id}   발화 id. 없으면 build() 가 JSON null 로 넣는다
    {utterance}      파싱할 발화 원문
    {section}        SRRG 섹션 헤딩. 없으면 JSON null

예시 JSON 안의 중괄호는 이스케이프하지 않았다. 그래야 EXAMPLES 를 손으로
고칠 수 있고, 그럴 수 있는 이유는 그것이 format 대상이 아니라 {examples}
자리에 들어가는 값이기 때문이다. PROMPT 본문에서 실제 중괄호가 필요한 곳은
마지막 입력 블록 하나뿐이고, 거기만 {{ }} 로 escape 돼 있다.

## 원본과 다른 점 두 가지

1. system 메시지와 user 메시지를 하나로 합쳤다. 원본은 규칙을 system 으로
   따로 보내 KV 캐시에 남기지만, 여기서는 한 덩어리다.

2. 예시가 고정 4개다. 원본은 발화의 cue 를 보고 8개 중 3~4개를 고른다
   (명세 §7). 정적 프롬프트에는 그 선택이 없으므로, 서로 다른 문장 구조를
   덮는 4개를 골라 박아 두었다:

       qualified        한정된 부정 + warning         (rule 11)
       multi_location   한 소견, 위치 여러 개          (rule 2)
       device           삽입 부위 vs 팁 위치           (rule 7)
       inference        관찰 1 + 해석 3, derived_from  (rule 6)

   나머지 넷(basic·negation_multi·temporal·normal)이 가르치던 것은 규칙
   10·12·14 의 문장이 담고 있다. 명세 §6 은 예시를 더 넣는 것이 낫지 않다고
   명시한다.
"""

import json

# =============================================================================
#  TOOL  --  답을 강제하는 스키마
# =============================================================================
# 프롬프트는 아니지만 같이 나가는 입력이다. llama.cpp 는 이 스키마를 GGBNF
# 문법으로 컴파일하므로, 여기 없는 값은 생성 자체가 되지 않는다.
#
# tool_choice 는 "required" 로 보낼 것. llama-server 는 tool_choice 를
# 문자열로만 파싱해서, OpenAI 의 객체 형태를 주면 조용히 "auto" 로 떨어지고
# 호출을 강제하던 문법이 사라진다. 도구가 하나뿐이므로 "required" 로 족하다.
#
# JSON Schema 그대로 두고 파싱한다. 원본이 JSON 이므로 그 형태가 읽기 쉽다.

TOOL_NAME = "return_propositions"

TOOL_SCHEMA = json.loads(r"""
{
  "type": "object",
  "properties": {
    "propositions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "entity": {
            "type": "object",
            "properties": {
              "text": {
                "type": "string"
              },
              "label": {
                "type": "string"
              },
              "type": {
                "type": "string",
                "enum": [
                  "finding",
                  "disease",
                  "device",
                  "anatomical_state",
                  "postoperative_state",
                  "other"
                ]
              }
            },
            "required": [
              "text",
              "label",
              "type"
            ],
            "additionalProperties": false
          },
          "anatomy": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "text": {
                  "type": [
                    "string",
                    "null"
                  ]
                },
                "label": {
                  "type": [
                    "string",
                    "null"
                  ]
                },
                "laterality": {
                  "type": "string",
                  "enum": [
                    "left",
                    "right",
                    "bilateral",
                    "midline",
                    "unspecified",
                    "not_applicable"
                  ]
                },
                "zone": {
                  "enum": [
                    "upper",
                    "middle",
                    "lower",
                    "apical",
                    "basilar",
                    "perihilar",
                    "retrocardiac",
                    "diffuse",
                    null
                  ]
                },
                "role": {
                  "type": "string",
                  "enum": [
                    "site",
                    "insertion_site",
                    "tip_location",
                    "relative_location"
                  ]
                },
                "source": {
                  "type": "string",
                  "enum": [
                    "utterance",
                    "section_context",
                    "entity_semantics",
                    "linked_proposition"
                  ]
                }
              },
              "required": [
                "text",
                "label",
                "laterality",
                "zone",
                "role",
                "source"
              ],
              "additionalProperties": false
            }
          },
          "descriptors": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "text": {
                  "type": "string"
                },
                "type": {
                  "type": "string",
                  "enum": [
                    "size",
                    "severity",
                    "extent",
                    "distribution",
                    "number",
                    "morphology",
                    "measurement",
                    "device_position",
                    "chronicity",
                    "normality",
                    "other"
                  ]
                },
                "label": {
                  "type": "string"
                }
              },
              "required": [
                "text",
                "type",
                "label"
              ],
              "additionalProperties": false
            }
          },
          "assertion": {
            "type": "object",
            "properties": {
              "label": {
                "type": "string",
                "enum": [
                  "present",
                  "absent",
                  "uncertain",
                  "unknown"
                ]
              },
              "cue": {
                "type": [
                  "string",
                  "null"
                ]
              }
            },
            "required": [
              "label",
              "cue"
            ],
            "additionalProperties": false
          },
          "comparison": {
            "type": "object",
            "properties": {
              "label": {
                "type": "string",
                "enum": [
                  "new",
                  "improved",
                  "worsened",
                  "stable",
                  "resolved",
                  "none",
                  "unclear"
                ]
              },
              "cue": {
                "type": [
                  "string",
                  "null"
                ]
              }
            },
            "required": [
              "label",
              "cue"
            ],
            "additionalProperties": false
          },
          "derived_from": {
            "type": [
              "string",
              "null"
            ]
          }
        },
        "required": [
          "id",
          "entity",
          "anatomy",
          "descriptors",
          "assertion",
          "comparison",
          "derived_from"
        ],
        "additionalProperties": false
      }
    },
    "warnings": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "propositions",
    "warnings"
  ],
  "additionalProperties": false
}
""")

# =============================================================================
#  EXAMPLES  --  {examples} 자리에 들어가는 값
# =============================================================================
# 여기 중괄호는 escape 하지 않는다 (모듈 docstring 참조).
# 예시를 바꾸려면 이 문자열만 고치면 된다.

EXAMPLES = """\
### Example 1
Input:
{
  "utterance_id": "12_pleura_01",
  "utterance": "No large pleural effusion.",
  "section": "Pleura"
}
Output:
{
  "propositions": [
    {
      "id": "p1",
      "entity": {
        "text": "pleural effusion",
        "label": "pleural_effusion",
        "type": "finding"
      },
      "anatomy": [
        {
          "text": "pleural",
          "label": "pleura",
          "laterality": "unspecified",
          "zone": null,
          "role": "site",
          "source": "utterance"
        }
      ],
      "descriptors": [
        {
          "text": "large",
          "type": "size",
          "label": "large"
        }
      ],
      "assertion": {
        "label": "absent",
        "cue": "No"
      },
      "comparison": {
        "label": "none",
        "cue": null
      },
      "derived_from": null
    }
  ],
  "warnings": [
    "Qualified negation: smaller pleural effusion is not excluded."
  ]
}

### Example 2
Input:
{
  "utterance_id": "13_lungs_01",
  "utterance": "Multifocal consolidation in the right upper and lower lobes.",
  "section": "Lungs and Airways"
}
Output:
{
  "propositions": [
    {
      "id": "p1",
      "entity": {
        "text": "consolidation",
        "label": "consolidation",
        "type": "finding"
      },
      "anatomy": [
        {
          "text": "right upper",
          "label": "right_upper_lobe",
          "laterality": "right",
          "zone": "upper",
          "role": "site",
          "source": "utterance"
        },
        {
          "text": "lower lobes",
          "label": "right_lower_lobe",
          "laterality": "right",
          "zone": "lower",
          "role": "site",
          "source": "utterance"
        }
      ],
      "descriptors": [
        {
          "text": "Multifocal",
          "type": "distribution",
          "label": "multifocal"
        }
      ],
      "assertion": {
        "label": "present",
        "cue": null
      },
      "comparison": {
        "label": "none",
        "cue": null
      },
      "derived_from": null
    }
  ],
  "warnings": []
}

### Example 3
Input:
{
  "utterance_id": "14_devices_01",
  "utterance": "Left subclavian PICC line in place with tip in the distal SVC, unchanged in position.",
  "section": "Tubes, Catheters, and Support Devices"
}
Output:
{
  "propositions": [
    {
      "id": "p1",
      "entity": {
        "text": "PICC line",
        "label": "picc_line",
        "type": "device"
      },
      "anatomy": [
        {
          "text": "Left subclavian",
          "label": "left_subclavian_region",
          "laterality": "left",
          "zone": null,
          "role": "insertion_site",
          "source": "utterance"
        },
        {
          "text": "distal SVC",
          "label": "distal_svc",
          "laterality": "midline",
          "zone": null,
          "role": "tip_location",
          "source": "utterance"
        }
      ],
      "descriptors": [
        {
          "text": "tip in the distal SVC",
          "type": "device_position",
          "label": "tip_in_distal_svc"
        }
      ],
      "assertion": {
        "label": "present",
        "cue": "in place"
      },
      "comparison": {
        "label": "stable",
        "cue": "unchanged in position"
      },
      "derived_from": null
    }
  ],
  "warnings": []
}

### Example 4
Input:
{
  "utterance_id": "15_lungs_01",
  "utterance": "Right infrahilar opacity suggesting atelectasis or edema; concurrent infection cannot be excluded.",
  "section": "Lungs and Airways"
}
Output:
{
  "propositions": [
    {
      "id": "p1",
      "entity": {
        "text": "opacity",
        "label": "opacity",
        "type": "finding"
      },
      "anatomy": [
        {
          "text": "Right infrahilar",
          "label": "right_infrahilar_region",
          "laterality": "right",
          "zone": "perihilar",
          "role": "site",
          "source": "utterance"
        }
      ],
      "descriptors": [],
      "assertion": {
        "label": "present",
        "cue": null
      },
      "comparison": {
        "label": "none",
        "cue": null
      },
      "derived_from": null
    },
    {
      "id": "p2",
      "entity": {
        "text": "atelectasis",
        "label": "atelectasis",
        "type": "disease"
      },
      "anatomy": [
        {
          "text": null,
          "label": "right_infrahilar_region",
          "laterality": "right",
          "zone": "perihilar",
          "role": "site",
          "source": "linked_proposition"
        }
      ],
      "descriptors": [],
      "assertion": {
        "label": "uncertain",
        "cue": "suggesting"
      },
      "comparison": {
        "label": "none",
        "cue": null
      },
      "derived_from": "p1"
    },
    {
      "id": "p3",
      "entity": {
        "text": "edema",
        "label": "pulmonary_edema",
        "type": "disease"
      },
      "anatomy": [
        {
          "text": null,
          "label": "right_infrahilar_region",
          "laterality": "right",
          "zone": "perihilar",
          "role": "site",
          "source": "linked_proposition"
        }
      ],
      "descriptors": [],
      "assertion": {
        "label": "uncertain",
        "cue": "suggesting"
      },
      "comparison": {
        "label": "none",
        "cue": null
      },
      "derived_from": "p1"
    },
    {
      "id": "p4",
      "entity": {
        "text": "infection",
        "label": "pulmonary_infection",
        "type": "disease"
      },
      "anatomy": [],
      "assertion": {
        "label": "uncertain",
        "cue": "cannot be excluded"
      },
      "descriptors": [],
      "comparison": {
        "label": "none",
        "cue": null
      },
      "derived_from": "p1"
    }
  ],
  "warnings": []
}
"""

# =============================================================================
#  PROMPT  --  하나로 합친 프롬프트
# =============================================================================

PROMPT = """\
You are a deterministic parser for English chest X-ray report utterances.

Given one utterance and an optional section heading, return valid JSON only.

For each clinical entity, create one proposition containing five linked categories:

1. entity
2. anatomy/location
3. descriptor(s)
4. assertion
5. temporal comparison

RULES

1. Do not output five separate bags of labels. Keep all factors linked to the correct entity.

2. One utterance may produce zero, one, or multiple propositions.
   - "No pleural effusion or pneumothorax" produces two propositions.
   - If one entity has several locations with the same assertion and descriptors, use one proposition with multiple anatomy entries.
   - If different locations have different descriptors, assertions, or comparisons, split them into separate propositions.

3. Use exact source text in all "text" and "cue" fields.
   Do not invent findings, locations, severity, or temporal states.

4. The utterance overrides the section heading.
   The section heading is only a weak context that may fill a missing broad anatomy.
   Never use it to add laterality, zone, or lobe.
   Add a warning if the section conflicts with the utterance.

5. Entity types:
   finding, disease, device, anatomical_state, postoperative_state, other.

6. Keep findings and disease interpretations separate.
   Example:
   "Opacity suggesting pneumonia"
   - opacity: present
   - pneumonia: uncertain, derived_from the opacity proposition

7. Anatomy may contain multiple entries.
   For devices, distinguish insertion_site and tip_location.

8. Descriptor types:
   size, severity, extent, distribution, number, morphology,
   measurement, device_position, chronicity, normality, other.

9. Keep size and severity separate.
   - small = size
   - mild = severity
   - multifocal = distribution
   - chronic = chronicity

10. Assertion labels:
    present, absent, uncertain, unknown.

    Negation:
    - no, without, not identified -> absent

    Uncertainty:
    - possible, suggesting, likely, may represent,
      cannot exclude, consistent with -> uncertain

    An unmentioned finding is not absent.

11. Preserve qualified negation.
    - "No large pleural effusion" means large pleural effusion is absent.
    - It does not prove that every pleural effusion is absent.

12. Comparison labels:
    new, improved, worsened, stable, resolved, none, unclear.

    - unchanged, stable, remains -> stable
    - new -> new
    - improved, decreased -> improved
    - worsened, increased -> worsened
    - resolved -> resolved and assertion=absent

13. "Chronic" and "known" are not temporal comparison.
    Store them as chronicity descriptors.

14. Normal statements are anatomical states.
    Do not convert "normal", "within normal limits", or "clear"
    into absence of every possible disease.

15. Return JSON only. Do not explain your reasoning.

OUTPUT SHAPE

Return an object with exactly two keys: "propositions" and "warnings".
Do not echo utterance_id, utterance, or section; the caller already has them.
Number the propositions "p1", "p2", ... in the order you create them.

WORKED EXAMPLES

{examples}
### Now parse this one

Parse this SRRG chest X-ray utterance.

{{
  "utterance_id": {utterance_id},
  "utterance": "{utterance}",
  "section": {section}
}}

Return JSON only."""


# =============================================================================
#  build  --  {} 를 채워 완성된 프롬프트 하나를 돌려준다
# =============================================================================

def _quoted(value):
    """None 은 문자열 "null" 이 아니라 JSON null 로 들어가야 한다."""
    return "null" if value is None else json.dumps(str(value),
                                                   ensure_ascii=False)


def build(utterance, section=None, utterance_id=None, examples=EXAMPLES):
    """발화 하나 -> 그대로 보낼 수 있는 프롬프트 하나.

    utterance 는 감싸는 따옴표 안에 들어가므로, 발화에 큰따옴표나 역슬래시가
    있으면 JSON 이 깨진다. json.dumps 로 escape 한 뒤 바깥 따옴표만 벗긴다.
    """
    return PROMPT.format(
        examples=examples,
        utterance_id=_quoted(utterance_id),
        utterance=json.dumps(str(utterance), ensure_ascii=False)[1:-1],
        section=_quoted(section),
    )


__all__ = ["PROMPT", "EXAMPLES", "TOOL_NAME", "TOOL_SCHEMA", "build"]


if __name__ == "__main__":
    # 완성된 프롬프트가 어떻게 생겼는지 눈으로 보려면:  python cxr_prompt.py
    print(build("There is no pleural effusion.",
                section="Pleura", utterance_id="10_pleura_01"))
