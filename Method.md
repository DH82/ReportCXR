# Method — 무엇을, 왜, 어떻게 구현했는가

[`README.md`](README.md) 는 폴더 지도이고 [`Start.md`](Start.md) 는 실행
안내, [`Glossary.md`](Glossary.md) 는 기호 사전입니다. 이 문서는 **설계의 논리**를 논문 Method 절처럼 풀어 씁니다 —
각 부품이 무엇을 뜻하고, 왜 그렇게 나뉘어 있고, 실제로 어떻게 구현돼 있는가.

---

## 1. 문제 정의

### 1.1 입력과 출력

입력은 판독문 **문장 하나**와 그 문장이 속한 **섹션 제목**입니다.

```
utterance : "Mild indentation of the left trachea at the level of the clavicles, unchanged."
section   : "Lungs and Airways"
```

출력은 **명제(proposition)의 집합**입니다. 명제 하나는 다섯 축이 서로 묶인
단위입니다.

| 축 | 무엇 | 위 문장에서 |
|---|---|---|
| `entity` | 무엇이 있는가 | `indentation` |
| `anatomy` | 어디인가 (여러 개 가능) | `trachea`(left), `clavicle`(relative_location) |
| `descriptors` | 어떤 성질인가 | `{severity: mild}` |
| `assertion` | 있는가 없는가 불확실한가 | `present` |
| `comparison` | 이전 영상 대비 | `stable` (cue: "unchanged") |

### 1.2 왜 "명제"인가 — 라벨 다섯 봉지로는 안 되는 이유

가장 순진한 설계는 문장에서 개체·부위·수식어를 각각 뽑아 다섯 개의 리스트로
내는 것입니다. 이것이 무너지는 지점은 문장에 **개체가 둘 이상**일 때입니다.

```
"Small right pleural effusion, no pneumothorax."

라벨 봉지:  entity=[pleural_effusion, pneumothorax]
            laterality=[right]
            size=[small]
            assertion=[present, absent]
```

이 표현은 **기흉이 오른쪽인지 흉수가 오른쪽인지 복원할 수 없습니다.** 축이
서로 풀려 버렸기 때문입니다. 그래서 이 프로젝트의 rule 1은 *"다섯 개의 라벨
봉지를 내지 말 것. 모든 축을 해당 개체에 묶어 둘 것"* 입니다. 명제 구조는
이 묶임을 자료구조로 강제한 것입니다.

```
p1: entity=pleural_effusion  anatomy=[pleura(right)]  size=small   assertion=present
p2: entity=pneumothorax      anatomy=[]                            assertion=absent
```

CSV 테이블(`flatten.py`)은 이 중첩 구조의 **투영**일 뿐이며, 정본은 언제나
중첩 JSON입니다. 테이블이 정본이 되는 순간 위의 묶임 정보가 사라집니다.

### 1.3 이 작업의 고유한 난점

| 난점 | 예 | 이 저장소의 대응 |
|---|---|---|
| 같은 사실, 다른 문자열 | `left_lower_lobe` / `lower lobe of the left lung` | 온톨로지 표로 정규화 (§4.1) |
| 부정·불확실이 흔하다 | "no evidence of", "possible" | `assertion` 축을 별도로 둠 |
| 한정된 부정 | "no **large** effusion" | rule 11 — 배제된 것은 "큰 흉수"지 흉수가 아니다 |
| 원문에 없는 말을 지어냄 | entity.text `"atrial pacemaker leads"` | rule 3 — 모든 span은 원문의 연속 구간 |
| 정보가 두 자리에 | `left_lower_lobe` + `laterality:left` | E1/E3 — 한 사실은 한 자리 (§3.6) |

---

## 2. 시스템 개요 — 세 단계로 나눈 이유

```mermaid
flowchart LR
    U["문장"] --> S1["step 1<br/>LLM 추출"]
    S1 --> S2["step 2<br/>표 정규화"]
    S2 --> S3["step 3<br/>규칙 검증"]
    S3 --> R["레코드"]
    R -.-> V["Verify<br/>사후 감사"]
```

이 분할의 근거는 **비용과 결정성의 비대칭**입니다.

| | step 1 | step 2 · 3 |
|---|---|---|
| 무엇이 하나 | LLM (Qwen3.8-27B) | 파이썬 함수 + 표 |
| 비용 | 문장당 ~30초, GPU | 무시 가능 |
| 결정적인가 | **아니오** (샘플러를 고정해도 완전 보장 안 됨) | **예** |
| 다시 돌리려면 | 110만 문장 = 이 기기로 불가 | 몇 분 |

여기서 설계 원칙 하나가 따라 나옵니다:

> **표로 판정할 수 있는 것은 절대 모델에게 시키지 않는다.**

`left_lower_lobe` → `lower_lobe` + `laterality:left` 같은 변환은 표를 한 번
찾으면 끝나는 일입니다. 이것을 모델에게 시키면 비싸고, 흔들리고, 고치려면
110만 번을 다시 호출해야 합니다. 표에 맡기면 공짜이고, 결정적이고, 고친 뒤
step 2만 다시 돌리면 됩니다.

**이 비대칭이 저장소 구조 전체를 설명합니다.** `Prompt*/`는 비싼 단계에 무엇을
시킬지를 정하고, `Pipeline/`의 step 2·3은 싼 단계에서 최대한 많은 일을 하며,
`Verify/`는 그 결과를 사후에 감사합니다.

---

## 3. `Prompt/` · `Prompt2/` — 추출 규격

### 3.1 무엇인가

프롬프트 패키지는 **"모델에게 무엇을 어떻게 시킬 것인가"를 담은 하나의 단위**
입니다. 모델을 직접 부르지 않고, 파일을 쓰지도 않습니다 — 문자열과 표만
들고 있습니다.

| 파일 | 역할 | 비유 |
|---|---|---|
| `system.py` | 규칙 20개 (무엇을 어떻게 뽑을지) | 작업 지시서 |
| `schema.py` | 출력 JSON Schema | 제출 양식 |
| `user_template.py` | 문장을 감싸는 사용자 메시지 | 문제지 |
| `examples.py` | few-shot 예시 11개 | 모범 답안 |
| `selection.py` | 문장마다 어느 예시를 붙일지 | 문제 유형별 모범답안 배정 |
| `ontology.py`·`vocabulary.py` | 표 (step 2·3이 읽음) | 채점 기준표 |

### 3.2 출력 형식은 문법으로 강제한다

모델에게 "JSON만 내라"고 **말로** 부탁하지 않습니다. llama.cpp의 강제 함수
호출(`tool_choice="required"`)로 스키마를 **문법 수준에서** 고정합니다.

```python
llm.chat(..., tools=[EMIT_TOOL], tool_choice="required")
```

그래서 "JSON이 깨져서 파싱 실패" 같은 실패 유형이 원리적으로 없습니다.
`Verify`의 스키마 검사(enum·id·그래프 무결성)가 한 번도 안 깨진 이유입니다.

샘플러도 고정합니다 — `temperature 0, top_p 1, top_k 1, seed 0`. 구조화
추출은 같은 문장에 같은 답을 내야 하기 때문입니다. (다만 이 호스트에서 같은
seed·같은 프롬프트가 어긋난 사례가 관측됐고, 그 사실이 `qwen_client.py`
주석에 남아 있습니다 — **보장이 아니라 최선의 노력**입니다.)

### 3.3 few-shot 예시를 문장마다 고르는 방식

예시 11개를 모두 붙이면 프롬프트가 길어지고 비용이 오릅니다. 그래서 문장의
표면 신호로 유형을 찍어 **최대 4개**만 붙입니다.

```python
CUE_TABLE = [
    ("blanket",      ["no significant change", "unremarkable", ...]),
    ("coordination", [", and ", " or ", "and endotracheal", ...]),
    ("inference",    ["suggesting", "likely", "cannot exclude", ...]),
    ...
]
```

규칙은 단순합니다 — **단어 경계 매칭, 먼저 걸린 것이 이김, 같은 예시는 두 번
보내지 않음, 상한 4개.** `blanket`과 `coordination`을 표 맨 앞에 둔 것은
v1이 가장 크게 실패한 두 유형이기 때문입니다 (먼저 걸리므로 우선 배정됩니다).
v3에서 추가된 `limitation`은 그보다도 앞에 둡니다 — 부정과 한정을 동시에
담은 문장이 "부정" 쪽으로 빨려 들어가면, v2에 예시조차 없던 유형이 계속
예시를 못 받기 때문입니다.

### 3.4 두 패키지의 관계 — 원본은 동결, 나머지는 하나

```mermaid
flowchart LR
    P1["Prompt/<br/>v1 원본 (동결)"]
    P2["Prompt2/<br/>v3.4 지시서 + 표의 정본"]
    P1 -.->|"A/B 기준선으로만 비교"| P2
```

`Prompt/`는 손대지 않습니다. 기준선이 움직이면 "나아졌다"는 말 자체가 성립하지
않기 때문입니다. 그 외의 모든 것 — 지시서 본문, 예시, 예시 배정, 표, 스키마,
어휘 — 은 `Prompt2/` 하나에 있습니다.

**한때는 셋이었습니다.** v3 지시서는 `Prompt3/`에 있었고, v2 본문을 import해서
정해진 문자열을 찾아 바꾸는 **패치** 방식이었습니다. 복사본을 두면 v2를 고쳤을
때 v3가 조용히 옛 문장을 들고 있게 되는데, 패치는 v2가 바뀌는 순간 import
시점에 큰 소리로 실패하기 때문입니다.

v3.4에서 패치가 7개까지 늘자 그 방식의 비용이 이득을 넘었습니다 — **실제로
모델에게 나가는 문장을 읽으려면 두 파일을 머릿속에서 겹쳐야** 했고, 규칙
사이의 간섭(v3.0에서 rule 3과 rule 20이 서로를 이긴 사건이 그 예입니다)이
바로 그 겹쳐 읽기에서 놓쳤던 것입니다. 그래서 패치를 본문에 반영하고 두
패키지를 합쳤습니다. 지시서는 이제 조립되는 것이 아니라 **한 편의 완성된
문서**입니다.

합치면서 **v2 본문은 import 대상에서 사라졌습니다.** git 히스토리에 있고 v2
팔의 결과 행은 `out/ab/out.jsonl`에 남아 있어 채점은 그대로 되지만, v2 팔을
다시 돌릴 수는 없습니다. 이것이 합치기의 값입니다 — 이중 정본을 없앤 대가로
옛 팔의 재현성을 내놓았습니다. 옛 팔은 이미 "그때 파일 상태"에 의존해서
재현이 불안정했으므로 (§ `out/README.md`) 실제로 잃은 것은 크지 않습니다.

이 저장소의 반복되는 주제는 그대로입니다 — *이중 정본은 반드시 어긋나고,
어긋나면 무엇이 데이터를 만들었는지 알 수 없게 된다.* 합치기는 그 주제를
버린 것이 아니라 끝까지 밀어붙인 것입니다.

같은 이유로 **표는 팔과 무관하게 언제나 `Prompt2/` 것 하나**입니다. 표가
프롬프트를 따라 같이 움직이면, A/B에서 관측된 차이가 프롬프트 때문인지 표
때문인지 분리할 수 없습니다.

### 3.5 규칙은 어떻게 만들어지는가 — 근거 → 규칙

이 저장소는 "이렇게 하면 더 좋을 것 같다"로 프롬프트를 고치지 않습니다.
**모든 규칙 변경에는 코퍼스 실측치가 붙어 있습니다.**

| 실측 (1,131,774 레코드) | 진단 | 규칙 변경 |
|---|---|---|
| `no_propositions` 29,252건 | v1은 "언제 0개가 맞는지"를 안 적었다 | rule 2에 판정 기준 추가 |
| `entity_text_not_in_utterance` 3,755건 | 대부분 등위 분배 | rule 3에서 `text`(구간)와 `label`(개념) 분리 |
| `tip_location` 사용률 32.0% | v1 예시가 기구 위치를 descriptor로 가르쳤다 | rule 7 재작성 + 예시 교체 |
| 편측 접두 라벨 42,077건 | 라벨이 `laterality` 필드의 일을 대신한다 | rule 16 신설 |

### 3.6 가장 중요한 발견 — 예시가 규칙보다 세게 가르친다

v1의 few-shot 예시가 내놓는 anatomy 라벨 **넷이 현재 온톨로지에 아예 없었고**,
예시를 step 2에 통과시키면 **여섯이 되돌려집니다.** 즉 모델에게 틀린 형식을
가르친 뒤 111만 번 되돌리고 있었습니다.

```
v1 예시가 가르친 것            step 2가 되돌리나?
right_upper_lobe            → 되돌림 (낭비)
clear_lungs                 → 되돌림 (낭비)
tip_in_distal_svc           → 안 됨  ← tip_location 사용률 32%의 원인
```

**되돌아오지 않는 것이 더 나쁩니다.** 그래서 v2의 예시 10개는 전부 **step 2
고정점**입니다 — 예시를 정규화기에 통과시켜도 라벨이 바뀌지 않습니다. 예시와
표가 같은 말을 하게 만든 것입니다.

---

## 4. `Pipeline/` — 결정적 정규화와 검증

### 4.1 step 2 `normalize.py` — 순서가 있는 변환 파이프

입력은 모델 출력 한 레코드, 출력은 정규화된 레코드입니다. **모델이 무엇을
주장했는지는 절대 뒤집지 않습니다** — 모순되는 증거는 노트로 남기고 판정은
step 3에 넘깁니다.

실제 실행 순서(`normalize_record`)와 각 단계의 의미:

| # | 변환 | 무엇을 하나 | 예 |
|---|---|---|---|
| 1 | **정상성 lift** (E3) | 라벨에 구운 정상성을 descriptor로 | `normal_heart_size` → `heart_size` + `{normality: normal}` |
| 2 | **수식어 lift** | 다른 축도 같은 방식으로 | `focal_consolidation` → `consolidation` + `{extent: focal}` |
| 3 | 정상성 lift **다시** | 2가 가리고 있던 정상성이 드러날 수 있음 | `well_expanded_clear_lungs` → `clear_lungs` → `lungs` + `{clear}` |
| 4 | entity 별칭 | `ENTITY_ALIASES`로 표기 통일, 타입 교정 | `ptx` → `pneumothorax` |
| 5 | **anatomy 정규화** | 아래 §4.1.1 | |
| 6 | **기구 끝 lift** (E2) | 기구 끝 위치 descriptor를 anatomy로 (rule 7) | `{device_position: tip_in_mid_svc}` → anatomy `svc`/zone `mid`/role `tip_location` |
| 7 | 미지원 span 제거 | 원문에 없는 `text`는 null로 (rule 3) | |
| 8 | 섹션 채움 (rule 4) | **비어 있는** 넓은 부위만 제목에서 채움 | 제목이 편측성·zone을 주는 것은 금지 |
| 9 | descriptor 정규화 | `DESCRIPTOR_LEXICON` → (축, 값), 측정치는 형태로 | `8 mm` → `{measurement, 8_mm}` |
| 10 | 비교 축 정리 | 시간 비교가 descriptor로 샌 것 회수, `chronic`은 만성도로 | |
| 11 | `resolved` 규칙 | 비교가 "해소됨"이면 assertion은 반드시 `absent` | |
| 12 | `derived_from` 복구 | 없는 id를 가리키는 링크·자기참조·순환 제거 | |

#### 4.1.1 anatomy 정규화가 하는 일 (E1의 핵심)

```
입력 label "left_lower_lobe", laterality unset

  ① 조회 키 만들기      표는 맨몸 구조명("lower lobe")으로 색인돼 있으므로
                        측면 낱말을 지운 형태를 따로 만든다  → bare="lower lobe"
  ② 라벨 결정           이미 표에 있는 라벨이면 그대로 둔다(벗기지 않는다).
                        아니면 별칭표를 spaced → flat → bare 순으로 조회
                        E1 이후 "left_lower_lobe" 는 표에 없으므로 bare 가 맞는다
                                                              → label="lower_lobe"
  ③ 편측성 채우기       필드가 비어 있으면 text 또는 라벨 표면형에서 읽어 채운다
                                                              → laterality="left"
                        필드에 이미 값이 있는데 라벨이 다른 쪽을 말하면
                        덮어쓰지 않고 lateral_prefix_conflict 노트만 남긴다
  ④ 좌우 해부 지식      left + middle_lobe 는 존재하지 않는다 → mid_lung_field
  ⑤ 집합명사 승격/강등  lung + bilateral → lungs  /  lungs + left → lung
  ⑥ 혈관 구간 분리      "mid_svc" -> "svc" + zone "mid"                  ← E2
                        카테터가 지나는 도관에만 적용한다(SEGMENTED_VESSELS).
                        폐야로 나뉘는 pulmonary_vasculature 는 건드리지 않는다
  ⑦ zone 채우기         라벨이 함의하면 채운다 (섹션 제목에서는 절대 안 채움)
                        혈관은 폐야 어휘(upper/middle/lower)가 아니라
                        구간 어휘(proximal/mid/distal)로만 읽는다

출력 label "lower_lobe", laterality "left"
```

세 곳이 이 코드의 성격을 잘 보여 줍니다.

**③ — 표는 모델을 덮어쓰지 않습니다.** 라벨과 필드가 서로 다른 측면을 말하면
둘 중 하나를 고르지 않고 노트만 남깁니다. 무엇이 옳은지는 step 3이 판정할
일입니다.

**⑤ — 책임을 한 곳에 몰아 둡니다.** `"the lungs"`는 복수형 자체가 "양쪽"을
뜻하는데, rule 17(단수화)을 그대로 적용하면 `lung`이 되면서 그 정보가
사라집니다. 그래서 **프롬프트는 단수 + `laterality:bilateral`까지만 책임지고,
집합명사 철자는 표(`BILATERAL_COLLECTIVE`)가 단독으로 결정**합니다.

**맨몸 방향어는 일부러 건드리지 않습니다.** `"bilateral"`처럼 구조를 부르지
않는 라벨을 섹션 제목으로 메워 보는 시도를 했다가 되돌렸습니다 — 자기 자신의
편측성과 모순되는 라벨을 지어냈기 때문입니다. 코드 주석이 그 판단을 이렇게
적어 두고 있습니다:

> *"커버되지 않은 라벨은 구멍이지만, 모순되는 라벨은 거짓 진술이다."*

#### 4.1.2 두 가지 불변식

**(a) 멱등성 = 고정점.** 이미 정규화된 레코드를 다시 정규화하면 아무것도
바뀌면 안 됩니다. 실제로 이걸 어긴 적이 있습니다 — 접두를 한 번에 하나만
벗기는 구현이라 `focal_nodular_density` → `nodular_density` → `density`로
2차 통과에서 또 바뀌었고, 백업에서 복원한 뒤 "벗길 것이 없을 때까지 도는"
형태로 고쳤습니다.

**(b) 모든 변경은 흔적을 남긴다.** 각 변환은
`{code, proposition, field, from, to}`를 `record["normalization"]`에 덧붙입니다.
"왜 이 라벨이 이렇게 됐지?"에 사후에 답할 수 있어야 하기 때문입니다.

### 4.2 step 3 `validate.py` — 44개 검사

레코드를 **고치지 않습니다.** 무엇이 잘못됐는지만 말합니다 — *"레코드에
무엇이 잘못됐는가"와 "레코드" 자체는 서로 다른 것이고, 파서의 출력물은
후자뿐이기 때문입니다.*

검사는 네 부류로 나뉩니다.

| 함수 | 묻는 것 | 예 |
|---|---|---|
| `check_spans` | 모든 `text`·`cue`가 원문에 실제로 있는가 | `entity_text_not_in_utterance` |
| `check_shape` | enum·id·그래프가 온전한가 | `assertion_invalid`, `derived_from_cycle` |
| `check_rules` | 명세 15개 규칙을 어겼는가 | `laterality_contradicts_label`, `qualified_negation_unwarned` |
| `check_splitting` | rule 2대로 쪼갰는가 (양방향) | `should_be_one_proposition`, `coordination_not_split` |

**error와 warning의 구분 기준**이 중요합니다.

- **error** = 그 상태로는 쓸 수 없다. 원문에 없는 텍스트, 규칙과의 정면 모순
  (`comparison=resolved`인데 `assertion≠absent`).
- **warning** = 내부적으로 모순은 없지만 규칙이 지목한다. 사람이 볼 가치가
  있다는 표시이지 결함 판정이 아닙니다.

여기에 더해 **review trigger 7종**이 있습니다 (개체 2개 이상, 한정된 부정,
불확실 해석, 복수 부위, 기구 끝 위치, 시간 비교, 섹션 충돌). 이것은 결함이
아니라 **오류가 몰리는 자리**의 표식이고, 사람 검수 표본을 뽑을 때 씁니다.

### 4.3 `parse_utterances.py` — 세 단계가 만나는 유일한 곳

`srrg_input.py`(입력 정규화) → step 1 → step 2 → step 3을 잇는 드라이버입니다.
서버와 통신하는 파일은 `qwen_client.py` 하나뿐이고, `jsonl/`에 쓰는 코드는
`Pipeline/`에만 있습니다 (`Verify/`는 설계상 절대 쓰지 않습니다).

설계 결정 두 가지가 사고 방지용입니다:

- **`history_section`을 프롬프트에 넣지 않는다.** 임상 병력은 *의뢰의가 의심한
  것*이지 이 영상이 보여주는 것이 아닙니다. 넣으면 `"history of pneumonia"`가
  폐렴 명제가 됩니다.
- **`OPENAI_*` 환경변수를 의도적으로 읽지 않는다.** 셸에 남은 유료 키로
  과금되는 일이 없도록. 다른 엔드포인트는 `--base-url`로 **명시**해야 합니다.

---

## 5. `Verify/` — 사후 감사

### 5.1 왜 별도의 층인가

`Pipeline/`은 데이터를 만들고, `Verify/`는 **만들어진 데이터를 읽기만**
합니다. 모델을 부르지 않고, `jsonl/`을 수정하지 않고, 레코드를 변형하지
않습니다. 만드는 코드가 채점까지 하면, 만들면서 저지른 실수를 같은 가정으로
못 보고 지나가기 때문입니다.

**측정하는 단위와 읽는 단위가 다릅니다.** `metrics/mNN_*.py` 하나가 **요소**
이고 판정을 정확히 하나 갖습니다 — 서로 다르게 답하는 두 질문을 한 판정으로
덮으면 둘 중 어느 것도 아니게 되기 때문입니다. 읽는 단위는 그보다 위인
**묶음**이고, 묶음 하나가 md 한 장입니다. `metrics/groups.py` 가 정의합니다.

요소는 `SECTION`, `TITLE`, `SCOPE`, `ASKS`, `MEANS`, `run` 여섯 이름을 노출하면
`run.py` 가 자동으로 발견합니다. 출력은
`out/reports/<arm>/<splits>/` 에 묶음 md 6장 + `INDEX.md` 입니다.

### 5.2 17개 요소는 6개 묶음으로 읽는다

| 묶음 | 요소 | 묻는 것 | 고칠 자리 |
|---|---|---|---|
| **배관** | S, C, 0 | 파일이 온전한가 · 원문을 잃지 않았나 · 정규화가 돌긴 했나 | 파이프라인 |
| **어휘** | 1-A, 1-B, 1-C, 1-D, P2 | 온톨로지가 표면형을 제대로 접었나 | `Prompt2/ontology.py` 의 표 |
| **필드** | 1-E, 1-F | 라벨과 그 옆 칸이 서로 맞나 | 표 + 스키마 규약 |
| **규칙** | R | 명세 15개 규칙 중 무엇을 어겼나 | 프롬프트 |
| **근거** | G1, G2, P3 | **JSON 이 원문을 실제로 읽었나** | **프롬프트 (표로는 안 됨)** |
| **과잉 특정** | P1a, P1b, P1c | 라벨이 필드의 일을 대신하나 | 표 결정 E1·E2·E3 |

**묶는 기준은 "고칠 자리가 어디인가" 입니다.** 둘 다 WARN 이라도 보내는 곳이
다르면 한 묶음이 아닙니다. 묶음의 판정은 속한 요소 중 가장 무거운 것이고
평균이 아닙니다 — 평균이면 FAIL 하나가 PASS 넷 뒤에 숨습니다.

### 5.3 숫자는 전 split, 예시는 한 split

각 요소는 **4개 split(train · validate · test · test_reviewed)을 나란히 놓은
표로 시작합니다.** 이 감사의 질문이 절대값이기 전에 **비교값**이기 때문입니다 —
test 의 25% 는 train 이 24% 일 때와 3% 일 때 전혀 다른 뜻이고, 한 split 만 튀면
데이터 문제이거나 표본 문제인데 어느 쪽이든 split 별로 흩어진 절을 스크롤해서는
보이지 않습니다.

**예시 문장은 `test_reviewed` 것만 싣습니다** (`--examples-from` 으로 변경).
같은 결함은 어느 split 에서나 같은 모양이므로 네 벌의 예시는 분량만 네 배가
되고 새로 알려 주는 것이 없으며, `test_reviewed` 가 **사람이 실제로 손으로
들여다보는 split** 이기 때문입니다.

**1-D 와 P3 만 split 별 표가 없습니다.** 판정 단위가 split 이 아니라 어휘
전체이기 때문입니다 — 두 라벨이 같은 개념인지는 어느 split 에 나왔는지와
무관하고(1-D), 손으로 선언한 사전 없이 코퍼스를 자기 사전으로 쓰는 피복률은
어휘 전체에 대해서만 뜻이 있습니다(P3). 두 파일 모두 그 이유를 본문 첫 줄에
적고 시작합니다.

**근거(G) 층은 2026-09-15 에 추가되었고, 그 전까지 이 감사에 없던 질문입니다.**
판단 층은 온톨로지가 일관되게 적용되었는지만 묻는데, **지어낸 span 도 똑같이
깨끗하게 정규화되기 때문에** 모델이 문장을 읽었는지는 볼 수 없었습니다. G 층만이
JSON 을 원문과 직접 대조하며, 정답 데이터도 모델 호출도 필요로 하지 않습니다.

배관 층은 전부 통과 상태입니다 — 181,874 study / 1,114,559 문장에서 **누락 0,
글자 불일치 0**. LLM 파이프라인이 가장 흔히 실패하는 방식(조용히 몇 건 흘리기)
이 전 split 0건이라는 뜻입니다.

### 5.3 가장 중요한 함정 — 고정점은 "정규화가 돌았다"만 증명한다

섹션 0(고정점)은 재정규화해도 안 바뀌는지를 봅니다. 통과하면 안심하기 쉽지만,

> `pleural_effusion`과 `effusion`을 **분리해 둔** 온톨로지도,
> **합쳐 둔** 온톨로지도 둘 다 완벽한 고정점입니다.

즉 고정점은 *일관되게 적용됐다*는 것이지 *옳게 적용됐다*가 아닙니다. 그래서
1-A~1-F가 그 다음을 보고, P1~P3이 왜 그런지를 봅니다.

### 5.4 지표가 조작 가능하다는 것을 문서에 적어 두는 이유

1-A(커버리지)는 "라벨이 승인 목록에 있는가"로 판정합니다. 그런데
`ENTITY_ALIASES` 75행 중 **18행이 항등행**입니다 — 표기 규약(공백/밑줄)만
다를 뿐 아무것도 바꾸지 않는 줄입니다.

```python
"consolidation":                 "consolidation"
"pulmonary vascular congestion": "pulmonary_vascular_congestion"
```

이런 줄을 하나 추가하면 수만 건이 passthrough에서 적중으로 넘어갑니다.
**데이터는 전혀 나아지지 않았는데 지표만 오릅니다.**

**그래서 커버리지를 목표로 삼으면 안 됩니다.** 이 사실이 README에 명시돼
있는 것은, 지표를 올리는 것과 데이터를 좋게 만드는 것이 다른 일이기
때문입니다.

### 5.5 지문 — 비교 가능성의 보증

모든 리포트 첫머리에 표 세 개가 찍힙니다.

| 층 | 무엇을 해싱 | 무엇을 잡나 |
|---|---|---|
| `content_hash` | 온톨로지 표를 **파싱해서** 정렬 직렬화 | 표 내용 변경. 주석·줄바꿈에는 둔감 |
| `normalizer code` | `normalize/validate/renormalize.py` 바이트 | 정규화기 코드 변경 |
| `split sha256` | 각 `jsonl` 파일 바이트 + 레코드 수 | **표도 코드도 그대로인데 데이터만 바뀐 경우** |

세 번째 층이 있는 이유는 실제 사고 때문입니다 — 표 크기 다섯 숫자만 찍던
시절, 표는 그대로인데 데이터 49,405건이 바뀐 일이 지문에 안 잡혔습니다.
**지문이 다른 두 리포트는 비교 대상이 아닙니다.**

---

## 6. 실험 설계 — A/B는 어떻게 판정하는가

프롬프트를 고쳤을 때 "좋아졌다"를 어떻게 말할 수 있는가의 문제입니다.

### 6.1 층화 표본 64문장

무작위 64문장은 결함이 드물어 아무것도 못 봅니다. 그래서 **결함 유형별로
8층 × 8문장**을 뽑습니다.

| 층 | 무엇을 보려고 |
|---|---|
| S1 | 명제 0개 (rule 2) |
| S2 | 한정된 부정 (rule 11) |
| S3 | 기구 끝 위치 (rule 7) |
| S4 | 원문에 없는 텍스트 (rule 3) |
| S5 | 섹션 충돌 (rule 4) |
| S6 | 명제 쪼개기 (rule 2 양방향) |
| S7 | 편측 라벨 (rule 16) |
| **S8** | **대조군 — 이미 깨끗한 문장** |

**S8이 핵심입니다.** 고치려는 것이 고쳐졌는지보다, *이미 잘 되던 것을
망가뜨리지 않았는지*가 통과 조건입니다. S8에서 finding이 늘면 그 패치는
실패입니다.

### 6.2 채점 전에 반드시 `renorm.py`

각 팔은 서로 다른 시점에 실행되므로, 그 사이에 표나 정규화기가 바뀌었을 수
있습니다. 채점 전에 **저장된 step 1 원본에서 step 2·3을 모두 다시** 돌려
모든 팔을 같은 기준으로 맞춥니다. 이걸 빼먹으면 프롬프트 차이와 표 차이가
섞입니다.

### 6.3 예측표를 결과보다 먼저 박아 둔다

고치기 전에 "무엇이 얼마나 움직여야 하는가"를 문서에 적어 둡니다.
**안 움직이면 그 진단이 틀린 것**입니다. 실제로 절반은 맞고 절반은 틀렸으며,
틀린 쪽이 더 유용했습니다 — 예컨대 편측 라벨 잔여분이 편측성 문제가 아니라
**커버리지 문제**(줄기가 표에 없어 접두를 벗겨도 미지의 라벨이 남음)라는 것을
그렇게 알아냈습니다.

### 6.4 복제 팔로 잡음 바닥을 잰다

`v3.2b`는 `v3.2`와 **바이트 동일한 프롬프트**로 한 번 더 돌린 팔입니다. 둘의
차이가 곧 이 표본이 분해하지 못하는 잡음의 크기입니다. (실제로 findings가
완전히 동일하게 나와, 이 규모에서 실행 간 변동은 없다는 것이 확인됐습니다.)

---

## 7. 한계

| | 무엇 | 뜻 |
|---|---|---|
| 1 | **표본 64문장은 방향만 본다** | 최종 수치가 아닙니다. 판정은 split 전량에서 나야 합니다 |
| 2 | **전량은 아직 v1 산출물** | 프롬프트 개선(v2·v3)은 표본에서만 검증됐습니다 |
| 3 | **양자화 델타 미측정** | 이 기기는 8bit 프로토타입입니다. 여기서 잰 개선이 프로덕션(full precision)으로 전이된다는 보장이 없습니다 |
| 4 | **자동 지표는 전부 대리 지표** | "임상적으로 옳은가"는 사람만 답할 수 있습니다 (`tools/sample_review.py`) |
| 5 | ~~E2 미구현~~ | ✅ 2026-09-14 구현됨 — `mid_svc` → `svc`+zone `mid`, 기구 끝 descriptor → anatomy |

3번이 가장 큽니다. 이 실험이 보인 것은 *"이 기기 안에서 v3.4가 v1보다
낫다"*이고, 그것이 프로덕션으로 전이되는지는 별개의 문제입니다.

---

## 부록 — 한 문장이 지나가는 전 과정

```
입력   "Bilateral pleural effusions, left greater than right."   section: Pleura

step 1 (LLM)  selection.py가 "bilateral" → multi_location 예시를 배정
              강제 tool call로 스키마 고정, temperature 0
              → entity "pleural effusions", anatomy [pleura], descriptor "left greater than right"

step 2 (표)   entity 별칭:  pleural effusions → pleural_effusion
              anatomy:      laterality 채움 → bilateral
              descriptor:   DESCRIPTOR_LEXICON → {type: distribution}
              note 3건이 record["normalization"]에 기록됨

step 3 (규칙) span 검사: "left greater than right"가 원문에 있는가 → 있음 ✓
              rule 2 검사: 한 개체·같은 assertion → 한 명제가 맞는가 ✓
              → findings 0건

Verify        S: 파일 온전 · C: 원문 무손실 · 0: 재정규화해도 불변
              R: 규칙 위반 0 · P1: 라벨이 필드 일을 대신하는가 → 아니오
```

이 문장은 v3.4에서 위와 같이 처리되지만, v3.3에서는 step 1이 좌우를 **두
명제로 쪼개고** 오른쪽 descriptor의 텍스트를 `"less than left"`로 **지어내어**
step 3의 span 검사에 걸렸습니다. 그 결함을 rule 2 패치로 막은 것이 v3.4이고,
전말은 [`Prompt2/README.md`](Prompt2/README.md)에 있습니다.
