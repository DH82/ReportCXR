# Glossary — 기호 찾아보기

문서를 읽다가 `S`, `C`, `E2`, `P1b`, `1-A` 같은 게 나와서 막혔을 때
**여기서 찾아보세요.** 처음부터 읽는 문서가 아닙니다.

---

## 먼저: 자주 쓰는 말 여섯 개

기호보다 이 말들이 먼저입니다. 이것만 알면 대부분의 문서가 읽힙니다.

| 말 | 쉽게 말하면 |
|---|---|
| **명제 (proposition)** | 판독문에서 뽑아낸 **사실 한 개**. "무엇이 / 어디에 / 어떤 / 있나없나 / 예전보다" 다섯 칸이 한 묶음 |
| **표 · 온톨로지** | **사전**. `왼쪽아래엽` 을 `아래엽` + `왼쪽` 으로 바꾸는 규칙표 |
| **정규화 (step 2)** | 사전을 씌워 **표기를 통일하는 일** |
| **팔 (arm)** | **어느 지시서로 뽑았는지**. 지시서가 다르면 결과도 다르니 따로 보관한다 (`jsonl/Prompt2/` = 지금 지시서로 뽑은 것, `jsonl/Prompt/` = 첫 지시서로 뽑은 것) |
| **지문 (fingerprint)** | 채점표 맨 위에 찍는 **"어떤 사전·코드·데이터로 쟀는지"** 도장. 이게 다르면 두 점수는 비교 불가 |
| **고정점 (fixed point)** | 사전을 **한 번 더 씌워도 아무것도 안 바뀌는 상태**. 이게 깨지면 사전에 버그가 있는 것 |

---

## 0. 겹치는 글자 세 개 — 가장 헷갈리는 것

이 셋만 알면 나머지는 헷갈리지 않습니다.

| 글자 | 문맥 A | 문맥 B |
|---|---|---|
| **S** | **Verify 섹션 S** = 파일 구조 검사 | **A/B 층 S1~S8** = 64문장 표본의 결함 유형 8층 |
| **C** | **Verify 섹션 C** = 원문 대비 완전성 | **Phase 0 관문 C1~C3** = 연구 계획의 판정 기준 |
| **1** | **Verify 섹션 1-A~1-F** = 온톨로지 적용 상태 | **rule 1** = 프롬프트 규칙 / **step 1** = LLM 추출 / **W1** = 계획 1주차 |

**이 문서들이 쓰는 표기 규칙** — 앞에 소속을 붙여 구분합니다.

```
Verify §S       파일 구조 섹션          rule 7        프롬프트 규칙 7번
Verify §1-B     과소 정규화 섹션        step 2        파이프라인 2단계
관문 C2         Phase 0 판정 기준        표 결정 E2    온톨로지 설계 결정
A/B S8층        대조군 층                명세 §8       SRRG 명세 8절
```

---

## 1. Verify 평가요소 — 검증 리포트에 찍히는 기호

`Verify/run.py -s <기호>` 로 골라 돌립니다. **요소 하나 = 판정 하나**
(`Verify/metrics/mNN_*.py`) 이고, **읽는 단위는 그보다 위인 묶음**입니다 —
17개 요소가 주제별 6개 묶음으로 묶여 `out/reports/<arm>/<splits>/gN_*.md`
여섯 장으로 나옵니다 (`run.py -g g5` 로 묶음째 고를 수 있습니다).
묶음 정의는 `Verify/metrics/groups.py`, 자세한 설명은
[`Verify/README.md`](Verify/README.md) §1.

| 묶음 | 요소 |
|---|---|
| `g1_integrity` 배관 | S · C · 0 |
| `g2_vocabulary` 어휘 | 1-A · 1-B · 1-C · 1-D · P2 |
| `g3_fields` 필드 | 1-E · 1-F |
| `g4_rules` 규칙 | R |
| `g5_grounding` 근거 | G1 · G2 · P3 |
| `g6_overspec` 과잉 특정 | P1a · P1b · P1c |

**묶음의 판정은 속한 요소 중 가장 무거운 것이고 평균이 아닙니다.**

각 요소는 **`Per split` 표(train·validate·test·test_reviewed)로 시작하고,
예시 문장은 `test_reviewed` 것만** 싣습니다 (`run.py --examples-from` 으로 변경).
1-D 와 P3 은 판정 단위가 split 이 아니라 어휘 전체라서 split 별 표가 없고,
그 이유를 본문 첫 줄에 적고 시작합니다.

| 기호 | 리포트 제목 | 무엇을 묻나 | 층 |
|---|---|---|---|
| **S** | File structure | 파일 자체가 온전한가 (잘린 줄, id 중복, 감사 필드 유출) | 배관 |
| **C** | Completeness vs source | 원본 CSV의 문장이 **글자 그대로** 다 있는가 | 배관 |
| **0** | Fixed point | 정규화를 한 번 더 돌려도 안 바뀌는가 | 배관 |
| **1-A** | Ontology coverage | 라벨을 표에서 찾았나, 못 찾고 통과시켰나(passthrough) | 판단 |
| **1-B** | Under-normalization | 같은 표면형이 두 라벨을 받았다 | 판단 |
| **1-C** | Over-normalization | 한 라벨이 너무 많은 표면형을 흡수했다 | 판단 |
| **1-D** | Merge candidates | 표면형을 안 겹치면서 사실 같은 개념인 두 라벨 | 판단 |
| **1-E** | Descriptor axis purity | descriptor가 제 축에 들어갔나 (rule 9). **표 밖 단어로만 판정한다** — 표 안은 step 2 가 일치를 강제하므로 측정이 불가능하다 | 판단 |
| **1-F** | Post-normalization invariants | 정규화 후에도 남은 모순 | 판단 |
| **R** | Rule validation | 명세 15개 규칙 중 무엇을 어겼나 (step 3의 44개 검사) | 규칙 |
| **G1** | Span grounding | 인용했다는 문구가 원문에 실제로 있는가 | 근거 |
| **G2** | Cue / label agreement | cue 가 assertion·comparison 라벨을 뒷받침하는가 | 근거 |
| **P1** | Label doing a field's job | 라벨이 필드의 일을 대신한다 (P1a·P1b·P1c 세 파일) | 진단 |
| **P2** | Same concept, split labels | 같은 개념인데 라벨이 갈렸다 | 진단 |
| **P3** | Recall (misses) | 뽑았어야 하는데 안 뽑은 것 | 진단 |

**왜 `G` 층이 따로 있나**: 1-A~1-F 는 전부 *온톨로지가 일관되게 적용되었나*를
묻습니다. **지어낸 span 도 똑같이 깨끗하게 정규화되므로** 그 검사들은 모델이
문장을 실제로 읽었는지를 볼 수 없습니다. G 층만이 JSON 을 원문과 대조합니다.

**판정 기호도 여섯 가지가 있습니다** — `PASS` · `WARN` · `FAIL` · `INFO` ·
`BLIND` · `SKIP`. **`BLIND` 와 `INFO` 는 `PASS` 가 아닙니다**:
`BLIND` 는 볼 수 있는 어휘가 너무 적어 측정 자체가 일어나지 않은 것이고,
`INFO` 는 임상 판단 없이 옳고 그름을 말할 수 없는 목록입니다.
[`Verify/README.md`](Verify/README.md) §1 참고.

**왜 `0`이 따로 있나**: 고정점은 "정규화가 **실행됐다**"만 증명하고
"**옳게** 됐다"는 증명하지 못합니다. 그래서 0은 배관 층에 있고, 판단은
1-A~1-F가 합니다.

### P1의 하위 코드

| 기호 | 무엇 | 어느 표 결정이 다루나 |
|---|---|---|
| **P1a** | 편측성이 라벨에 구워졌다 (`left_lower_lobe`) | E1 |
| **P1b** | 기구 위치가 descriptor로 샜다 (`tip_in_mid_svc`) | E2 |
| **P1c** | 정상성이 라벨에 구워졌다 (`normal_heart_size`) | E3 |

---

## 2. 표 결정 E1 · E2 · E3 — 온톨로지 설계

셋 다 같은 실수 하나를 고칩니다: **정보가 두 자리에 있으면 반드시 어긋난다.**
셋 다 담을 필드가 스키마에 이미 있어 **스키마를 바꾸지 않습니다.**

| 기호 | 결정 | 이전 | 이후 |
|---|---|---|---|
| **E1** | 편측성은 `laterality` 필드가 단독으로 진다 | `left_lower_lobe` + `laterality:left` | `lower_lobe` + `laterality:left` |
| **E2** | 혈관 구간은 `zone` 이 진다 | `mid_svc`, `descriptor: tip_in_mid_svc` | `svc` + `zone:mid` + `role:tip_location` |
| **E3** | 정상성은 `descriptor.type=normality` 가 진다 | `entity: normal_heart_size` | `heart_size` + `{normality: normal}` |

셋 다 `Prompt2/ontology.py` 의 표와 `Pipeline/normalize.py` 의 step 2에
구현돼 있습니다 (E2는 2026-09-14 구현 — [`PROVENANCE.md`](PROVENANCE.md) §4).

---

## 3. Phase 0 관문 C1 · C2 · C3 — 연구 계획의 판정 기준

**Verify 섹션 C와 아무 관계가 없습니다.** 이쪽은 "이 코퍼스가 연구가 세우려는
축을 지탱하는가"의 판정입니다. 현재 값은 [`README.md`](README.md) §1.

| 기호 | 묻는 것 | 기준 | 못 넘으면 |
|---|---|---|---|
| **C1** | 한 study 안에 factor를 공유하는 proposition이 2개 이상인가 | 15% | multiplicity 축 대신 spatial grounding |
| **C2** | 축별 대조 pair를 몇 개나 캘 수 있나 | 1,000 | anatomy 단일 축으로 축소 |
| **C3** | bag-of-findings oracle 대비 gap | 10점 | 대안 구성으로 전환 |

측정: `Verify/tools/phase0_metrics.py`

### 주차 기호 W1 · W2 · W3

Phase 0의 작업 주차입니다 (W1 = 8/31–9/6, W2 = 9/7–9/13, W3 = 9/14–9/20).

---

## 4. A/B 층 S1 ~ S8 — 64문장 표본의 결함 유형

**Verify 섹션 S와 아무 관계가 없습니다.** 프롬프트를 비교할 때, 무작위
64문장은 결함이 드물어 아무것도 못 보므로 **결함 유형별로 8층 × 8문장**을
뽑습니다.

| 층 | 무엇을 보려고 | 겨냥하는 규칙 |
|---|---|---|
| **S1** | 명제 0개 | rule 2 |
| **S2** | 한정된 부정 | rule 11 |
| **S3** | 기구 끝 위치 | rule 7 |
| **S4** | 원문에 없는 텍스트 | rule 3 |
| **S5** | 섹션 충돌 | rule 4 |
| **S6** | 명제 쪼개기 (양방향) | rule 2 |
| **S7** | 편측 라벨 | rule 16 |
| **S8** | **대조군 — 이미 깨끗한 문장** | (퇴행 감시) |

**S8이 통과 조건입니다.** 고치려던 것이 고쳐졌는지보다, 이미 잘 되던 것을
망가뜨리지 않았는지가 먼저입니다.

---

## 5. 파이프라인 step 1 · 2 · 3

| 기호 | 코드 | 무엇 | 비용 | 결정적인가 |
|---|---|---|---|---|
| **step 1** | `Pipeline/qwen_client.py` | LLM 추출 | 문장당 ~30초, GPU | 아니오 |
| **step 2** | `Pipeline/normalize.py` | 표 적용 (정규화) | 무시 가능 | **예** |
| **step 3** | `Pipeline/validate.py` | 규칙 검증 (44개 검사) | 무시 가능 | **예** |

---

## 6. 프롬프트 rule 1 ~ 20

모델에게 주는 규칙 번호입니다. 전문은 `Prompt2/system.py` (v3.4).
자주 인용되는 것만:

| 규칙 | 무엇 |
|---|---|
| **rule 1** | 라벨 다섯 봉지를 내지 말 것 — 모든 축을 해당 개체에 묶어라 |
| **rule 2** | 한 발화가 명제 0개·1개·여러 개를 낼 수 있다 (쪼개기 기준) |
| **rule 3** | 모든 `text`·`cue`는 원문의 **연속 구간**이어야 한다 |
| **rule 4** | 발화가 섹션 제목을 이긴다 (제목은 약한 문맥) |
| **rule 7** | 기구 끝은 `anatomy` + `role`, `tip_*` descriptor 금지 |
| **rule 9** | descriptor 축을 서로 섞지 말 것 |
| **rule 11** | 한정된 부정에는 `"Qualified negation:"` 경고 |
| **rule 12·13** | 시간 비교와 만성도를 구분 |
| **rule 14** | 정상성은 라벨이 아니라 descriptor 축 (E3) |
| **rule 16** | anatomy 라벨은 구조만, side는 `laterality` 필드 (E1) |
| **rule 17** | snake_case · 단수 · 숫자 없음 |
| **rule 18** | `source`가 `text`를 정한다 (v3 신설) |
| **rule 19** | 검사 자체를 기술한 문장을 버리지 말 것 (v3 신설) |
| **rule 20** | 한 정보는 한 자리 (v3 신설, 14·16의 일반화) |

---

## 7. 프롬프트 버전 — v1 · v2 · v2.1 · v3 ~ v3.4

| 버전 | 어디 | 무엇 |
|---|---|---|
| **v1** | `Prompt/` | 명세 3절 그대로. 동결, A/B 기준선 전용 |
| **v2 · v2.1** | — | `Prompt2/` 의 옛 상태. **git 히스토리에만 있음** (아래) |
| **v3 ~ v3.3** | — | 옛 `Prompt3/` 의 중간 상태들. out.jsonl 에만 남아 있음 |
| **v3.4** | `Prompt2/` | **현재 최선.** 64문장 error 0/64 |

> **팔(arm) 이름은 그 시점의 파일 내용을 가리킵니다.** 옛 `run_ab.py` 는
> v3~v3.4 를 전부 같은 `SYSTEM_PROMPT` 에 연결해 두었고, 실제로 무엇이
> 나갔는지는 **그때 파일이 어떤 상태였는가**로 정해집니다. 그래서 프롬프트를
> 고쳤으면 반드시 새 이름으로 돌려야 합니다.
>
> `Prompt3/` 를 `Prompt2/` 로 합친 뒤로는 `run_ab.py` 가 **`v1` 과 `v3.4` 만**
> 돌리고, 옛 팔 이름을 대면 에러로 막습니다. 옛 팔의 행은 `out/ab/out.jsonl`
> 에 남아 있어 채점에는 계속 쓰입니다.

### "팔(arm)"

같은 문장을 다른 프롬프트로 뽑으면 다른 데이터가 됩니다. 그래서 결과를
프롬프트별로 갈라 둡니다 — `jsonl/<arm>/<split>.jsonl`. 디렉터리 이름이 곧
팔 이름입니다 (`jsonl/Prompt/` = v1로 뽑은 것).

---

## 8. 명세 절 번호 (Section 2 · 3 · 8)

SRRG 명세 문서의 절 번호이고, 이 저장소의 섹션 기호와 무관합니다.

| 명세 절 | 무엇 | 이 저장소의 어디 |
|---|---|---|
| **§2** | 레코드 구조와 enum | `Prompt/schema.py`, `Prompt2/vocabulary.py` |
| **§3** | 시스템 프롬프트 | `Prompt*/system.py` |
| **§8** | 파이프라인 3단계 | `Pipeline/` |

---

## 9. 데이터 split

| split | 레코드 | 무엇 |
|---|---|---|
| `train` | 1,114,559 | 학습용 대부분 |
| `validate` | 6,015 | |
| `test` | 9,635 | |
| `test_reviewed` | 1,565 | **사람이 검수한** split |

---

## 10. 자주 나오는 검사 코드

step 3(`validate.py`)이 내는 44개 중 리포트에서 자주 보이는 것들.

| 코드 | 뜻 | 심각도 |
|---|---|---|
| `entity_text_not_in_utterance` | 원문에 없는 구간을 `text`에 썼다 | error |
| `laterality_contradicts_label` | 라벨이 함의하는 side와 필드가 다르다 | error |
| `zone_contradicts_label` | 〃 zone | error |
| `zone_missing_from_label` · `zone_not_canonicalized` | 라벨이 함의하는 zone과 필드가 정확히 같지 않다 | error |
| `qualified_negation_unwarned` | 한정된 부정인데 경고가 없다 (rule 11) | warning |
| `anatomy_span_is_side_only` | `anatomy.text`가 구조가 아니라 side 낱말 | warning |
| `section_conflict` | 발화의 부위가 섹션 제목과 다르다 (rule 4) | warning |
| `no_propositions` | 비어 있지 않은 발화인데 명제가 0개 | warning |
| `should_be_one_proposition` · `coordination_not_split` | rule 2의 양방향 위반 | warning |

**error** = 그 상태로는 쓸 수 없다. **warning** = 내부 모순은 없지만 사람이
볼 가치가 있다.

### step 2가 남기는 노트 코드

`validate.py`의 검사와 다릅니다 — 이쪽은 **step 2가 무엇을 바꿨는지**의
기록(`record["normalization"]`)입니다.

| 코드 | 무엇을 바꿨나 |
|---|---|
| `anatomy_label` · `entity_alias` · `descriptor_label` | 표를 찾아 라벨을 바꿨다 |
| `laterality_from_label` · `laterality_from_text` | 비어 있던 편측성을 채웠다 |
| `vessel_segment_from_label` · `vessel_segment_from_text` | E2 — 혈관 구간을 `zone`에 넣었다 |
| `device_position_to_anatomy` | E2 — 기구 끝 descriptor를 anatomy로 옮겼다 |
| `device_position_duplicate_dropped` | E2 — 양쪽에 있던 중복 descriptor를 지웠다 |
| `normality_prefix_lifted` · `modifier_prefix_lifted` | E3 — 라벨의 수식어를 descriptor로 올렸다 |
| `section_context_zone_dropped` · `section_context_laterality_dropped` | rule 4 — 제목이 준 zone·side를 버렸다 |
| `lung_zone_on_vessel_dropped` | E2 — 혈관에 붙은 폐야 zone을 버렸다 |

---

## 읽을 곳

| 알고 싶은 것 | 문서 |
|---|---|
| 전체 구조와 현재 상태 | [`README.md`](README.md) |
| 무엇을 치면 되는가 | [`Start.md`](Start.md) |
| 왜 이렇게 설계했나 | [`Method.md`](Method.md) |
| 무엇이 이 데이터를 만들었나 | [`PROVENANCE.md`](PROVENANCE.md) |
| Verify 섹션별 상세와 실측 | [`Verify/README.md`](Verify/README.md) |
