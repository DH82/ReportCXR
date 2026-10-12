# PROVENANCE — 이 데이터를 무엇이 만들었나

> ## 이 문서가 왜 있나요 (쉬운 설명)
>
> 어느 날 점수가 이상해서 "전에 잰 것과 비교해 보자" 했는데,
> **그 사이에 사전이 바뀌었는지 코드가 바뀌었는지 알 수가 없으면** 두 점수를
> 맞대는 게 아무 의미가 없습니다. 이 프로젝트에서 가장 비싼 실수는 전부
> 이것 때문이었습니다.
>
> 그래서 이 문서는 **"언제 무엇이 바뀌었는지"를 날짜와 지문(해시)으로
> 적어 둔 장부**입니다.
>
> **보통은 안 보셔도 됩니다.** 아래 셋 중 하나일 때만 오세요.
>
> | 이럴 때 | 볼 곳 |
> |---|---|
> | 데이터를 실수로 망가뜨려서 되돌려야 한다 | §2 백업 |
> | 옛 점수와 지금 점수가 왜 다른지 알아야 한다 | §4 지문 |
> | "그때 왜 그렇게 했더라?" 를 찾는다 | §4 날짜별 기록 |
>
> **용어 셋만 알면 읽힙니다.**
> - **지문(fingerprint)** = 채점표 맨 위에 찍는 도장. "어떤 사전·코드·데이터로
>   쟀는지". 이게 다르면 두 점수는 비교 대상이 아니다
> - **고정점(fixed point)** = 사전을 한 번 더 씌워도 아무것도 안 바뀌는 상태.
>   깨지면 사전에 버그가 있는 것
> - **E1 · E2 · E3** = 사전을 크게 고친 세 번의 결정
>   ([`Glossary.md`](Glossary.md) §2)

폴더별 사용법은 각 `README.md` 에 있다. 여기에는 **판정과 체크섬**만 적는다.

---

## 1. 무엇이 추적되고 무엇이 추적되지 않나

| | 어디 | git |
|---|---|---|
| 코드 · 문서 | `Prompt/` `Prompt2/` `Pipeline/` `Verify/` `Serving/` `RadLex/*.tsv` | 추적 |
| 구조화 결과 | `jsonl/` (778MB) | **미추적** |
| 생성물 | `out/` — 리포트 · 단어장 · A/B 산출물 | **미추적** (`out/README.md` 만 예외) |
| 명세와 설계 문서 | `docs/` | **미추적** |
| RadLex 원본 | `RadLex/*.owl` (83MB) | **미추적**. RSNA 에서 받는다 |

`jsonl/` 과 `out/` 에는 MIMIC-CXR · CheXpert 판독문 원문이 그대로 들어 있다.
MIMIC 은 PhysioNet 자격 인증 데이터이고 DUA 가 비인증자에게의 재배포를 금지하므로
**공개 원격에 올리지 않는다.** 로컬과 백업에만 둔다.

---

## 2. 백업

데이터는 git 이 아니라 백업 + 체크섬으로 관리한다.

```
/data3/backup/ReportCXR-Ko/
  jsonl-v1-20260904/              782MB   최초 동결 (E1/E3 이전)
  jsonl-v5pre-lift-20260914/      778MB   수식어 lift 직전 (E1/E3 적용 상태)
  jsonl-v6pre-E2-20260914/        777MB   E2 적용 직전 (가장 최근)
```

각 디렉터리에 `SHA256SUMS` 와 `README.txt` 가 있다.

```bash
# 무결성 확인
cd /data3/backup/ReportCXR-Ko/jsonl-v6pre-E2-20260914 && sha256sum -c SHA256SUMS

# 되돌리기 (팔별 디렉터리로 들어간다)
cp /data3/backup/ReportCXR-Ko/jsonl-v6pre-E2-20260914/*.jsonl jsonl/Prompt/
```

---

## 3. 표의 정본은 `Prompt2/` 다

`Prompt/` 는 **처음 쓰던 프롬프트를 원본 그대로** 보존하는 자리다 (A/B 의 v1 팔).
E1·E3·E2 로 고친 표는 전부 `Prompt2/` 가 들고 있고, step 2·3 과 `Verify/` 가 읽는
것도 그 표다.

| 파일 | 무엇 |
|---|---|
| `Prompt2/ontology.py` | E1(편측성) · E2(혈관 구간) · E3(정상성) 적용 표. **지문의 출처** |
| `Prompt2/vocabulary.py` | E2 혈관 구간 zone 을 포함한 닫힌 어휘 |
| `Prompt2/relations.py` | RadLex 가 모르는 개념 24 · 관계 22 |
| `Prompt2/schema.py` | v1 스키마에 zone 값만 넓힌 파생. 구조의 정본은 `Prompt/schema.py` |

**쓰이는 표는 하나다.** A/B 의 두 팔은 프롬프트만 다르고 표는 공유한다 — 표가
팔마다 다르면 지표의 차이가 프롬프트 때문인지 표 때문인지 알 수 없게 된다.
`qwen_client.py` 의 스키마도 `Prompt2` 것 하나다. `Prompt` 의 원본 어휘에는 E2 의
혈관 구간(`proximal`/`mid`/`distal`)이 없어서, 그 스키마로는 v2 가 내는
`zone=mid` 를 llama.cpp 문법이 막는다.

---

## 4. 온톨로지 지문

**모든 검증 리포트 첫머리에 표 세 개가 찍힌다. 어느 한 표라도 다른 두 리포트는
비교 대상이 아니다** — 다른 표로 계산한 지표를 맞대면 두 표의 차이를 데이터
품질로 보고하게 된다. (`Verify/core.py` `ontology_fingerprint` ·
`code_fingerprint` · `data_fingerprint`, 2026-09-14 확장.)

| | ANATOMY | ANAT_ALIASES | ENTITY_ALIASES | DESC_LEXICON | SIDED_MIDLINE |
|---|---|---|---|---|---|
| `Prompt2/ontology.py` (**쓰임**) | 107 | 130 | 75 | 149 | **22** |
| `Prompt/ontology.py` (원본, 미사용) | 147 | 113 | 56 | 149 | 7 |

**표 크기만으로는 부족하다** — 길이가 같은 채로 내용이 바뀌거나(항목 교체),
같은 표를 다른 코드가 읽거나, 같은 코드가 다른 jsonl 을 만들어도 다섯 숫자는
그대로다. 그래서 리포트 머리는 이제 세 층을 따로 찍는다:

| 층 | 무엇을 해싱하나 | 무엇을 잡나 |
|---|---|---|
| `content_hash` | `Prompt2/ontology.py` 의 public 테이블을 **파싱해서** (키 정렬, 순서 보존) 직렬화한 것 | 표 내용이 바뀌었는데 길이는 그대로인 경우. 파일 바이트가 아니라 파싱된 값을 해싱하므로 주석·줄바꿈 정리는 잡지 않는다 |
| `normalizer code` | `Pipeline/normalize.py` · `validate.py` · `renormalize.py` 각각의 파일 바이트 | 정규화기 코드 자체가 바뀐 경우 |
| `split` (`sha256` · `records`) | 각 `jsonl/<arm>/<split>.jsonl` 파일 바이트 + 레코드 수, `(size, mtime)` 로 캐시 | **표도 코드도 안 바뀌었는데 데이터만 다시 만들어진 경우** — 2026-09-14 의 49,405건 변경이 이 층 없이는 지문에 안 잡혔다 |

### 변경 이력 — 한눈에 보기

전부 2026-09-14 하루에 일어난 일이다. **위에서 아래로 시간순**이고,
`content_hash` 는 그 변경 직후의 값이다.

| | 무엇이 바뀌었나 | 표가 바뀌나 | `content_hash` | 데이터 재정규화 |
|---|---|---|---|---|
| 1 | **수식어 lift** — `focal_consolidation` -> `consolidation` + `{focal}` | 아니오 (코드만) | 그대로 | 49,405건 |
| 2 | **`BILATERAL_COLLECTIVE` 왕복 2줄** — `bronchus`/`pleural_sinus` 가 표 밖으로 새던 것 | 예 | `ab189fa7` -> `25f2578f` | 없음 |
| 3 | **`SIDED_MIDLINE` 4계열 추가** — midline 구조에 붙은 정상적인 좌/우 서술이 오탐이던 것 | 예 | `25f2578f` -> `1b3dc45b` | 없음 |
| 4 | **E2 구현 + 적용** — 혈관 구간이 `zone` 으로 | 예 (+코드) | `1b3dc45b` -> `7259390a` | **22,584건** |

**"표가 바뀌나"가 왜 중요한가**: 표가 안 바뀌고 코드만 바뀌면 표 크기 다섯
숫자는 그대로다. 1번이 정확히 그 경우였고, 그래서 지문에 코드·데이터 층을
더했다 (위 표).


### 2026-09-17 — cue 표 형태론 + rule 12 면제 (검사기만)

| | 무엇이 바뀌었나 | 표가 바뀌나 | `content_hash` | 데이터 재정규화 |
|---|---|---|---|---|
| 5 | **`NEGATION_CUES`·`UNCERTAINTY_CUES` 형태론 보강** + **m12 에 rule 12 면제** | 예 (cue 목록만) | `b2095b90` -> `9c3bee94` | **없음** |

**데이터가 안 바뀐 이유**가 이 변경의 핵심이다. 두 cue 목록을 읽는 곳은
`Pipeline/validate.py` 와 `Verify/metrics/m12_cue_agreement.py` 뿐이고,
`Pipeline/normalize.py` 는 이 둘을 import 하지 않는다 (`COMPARISON_CUES` 는
import 한다 — 그래서 그 표는 이번에 손대지 않았다). 즉 **검사기만 바뀌었고
`jsonl/` 은 바이트 하나 안 바뀌었다.** 고정점도 그대로다: Prompt21 은
여전히 도달, Prompt 은 여전히 2건.

**무엇이 문제였나.** 셋 다 데이터가 아니라 도구의 결함이었다.

1. `NEGATION_CUES` 에 `resolved` 는 있는데 `resolution` 이 없었다. m12 는
   단어 경계로 맞추므로 둘은 다른 낱말이다. `free of`/`free from`,
   `suggesting`/`suggests` 도 같은 꼴.
2. `UNCERTAINTY_CUES` 에 `may represent`·`may reflect` 는 있는데
   `may suggest`·`may indicate` 가 없었고, `cannot be excluded` 는 있는데
   `not excluded` 가 없었다.
3. **`absent_bad_cue` 가 rule 12 를 몰랐다.** 지시서 rule 12 는
   `resolved -> resolved and assertion=absent` 를 요구한다. 그래서
   "Interval removal of a right chest tube" 는 assertion=absent 가 맞고,
   그 근거는 부정어가 아니라 **해소어**다. 검사기가 부정어를 요구해
   **35건 중 27건이 이미 `comparison=resolved` 를 달고 있는데도** 결함으로
   세고 있었다.

**면제를 좁게 둔 이유.** `comparison=resolved` 만으로 면제하면 Prompt21 의
`absent_bad_cue` 가 0 이 되는데, 거기에는 헤지를 부정 근거로 인용한 진짜
rule 10 위반 4건이 섞여 있다. 그래서 **두 cue 가 내용어를 공유할 때만**
면제한다 (`_resolution_licenses_absent`). 기능어는 제외한다 —
`"suggestive of"` 와 `"Resolution of"` 는 `of` 를 공유하지만 같은 것을
가리키지 않는다.

**결과** (둘 다 test_reviewed, 데이터 불변):

| | `absent_bad_cue` | `uncertain_bad_cue` | G2 합계 |
|---|---|---|---|
| Prompt | 21 -> **9** | 57 -> **35** | 79 -> **45** (4.09% -> 2.33%) |
| Prompt21 | 25 -> **4** | 36 -> **16** | 62 -> **21** (3.09% -> 1.05%) |

**남은 것은 전부 진짜 결함이다.** Prompt 의 9건 중 8건은 제거를 비교로
아예 기록하지 않은 것(`comparison=none`)이고 — **Prompt21 이 그 8건을 전부
고쳤다** — 나머지와 Prompt21 의 4건은 헤지(`suggestive of`, `likely`,
`likely representing`)를 부정 근거로 인용한 rule 10 위반이다.

**넣지 않은 것**: `removal`/`removed`/`normalization` 을 `NEGATION_CUES` 에
넣는 안은 버렸다. 이것들은 부정어가 아니라 비교어이고, 넣으면 재현율 검사
(`negation_uncited`) 가 "removal" 이 든 모든 문장에 absent 를 요구하게 된다.
증상이 아니라 원인을 고치는 쪽이 rule 12 면제였다.

동결된 이전 리포트: `out/reports/_frozen_b2095b908c9853f9/`
jsonl 백업: `/data3/backup/ReportCXR-Ko/jsonl-v12pre-cue-tables-20260917`


### 2026-09-17 (2) — 판정 프롬프트와 precheck (표도 데이터도 안 바뀜)

`Prompt2/` 는 손대지 않았다. 지문 `9c3bee94` 그대로이고 `jsonl/` 도 그대로다.
바뀐 것은 **누가 무엇을 묻는가** 뿐이다.

**판정 프롬프트 (`GPT/audit_records.py`).** 20개 리포트 표본에서 만장일치
오탐 셋이 나왔고, 셋 다 원인이 판정 프롬프트가 추출 명세와 어긋난 것이었다.

1. `site` vs `relative_location` 전치사 테스트가 **기구 끝에도** 적용되고
   있었다. `"3.4 cm above the carina"` 의 `above` 를 읽고 판정자가
   `relative_location` 을 요구했는데, `Prompt2/system.py` rule 7 은 같은
   문장을 예시로 들어 `tip_location` 을 지시한다. 판정자가 틀린 게 아니라
   두 문서가 다른 말을 하고 있었다. 전치사 테스트를 소견에만 적용하도록
   범위를 좁혔다.
2. assertion 필드 설명이 `"with the word that decided it (cue)"` 로만 되어
   있어 모든 라벨에 cue 가 필요한 것처럼 읽혔다. rule 10 의 면제
   (`present` 는 cue 없음이 정상) 를 필드 설명에 직접 넣었다.
3. 혈관 구간 `zone` 이 표 조회라는 것을 몰랐다. `superior -> proximal` 은
   `Prompt2/vocabulary.py` 가 정한 값이다.

여기에 통과 기준 한 문단을 세웠다 — **"이 문장을 주의 깊게 읽은 사람이 이
레코드를 쓰고 옳았을 수 있는가"** 가 기준이고, 인코딩 취향의 우열은 묻지
않는다. 같은 문단에 과잉 억제 방지를 박았다: 이 관대함은 `hallucinated` 와
`dropped` 에는 적용되지 않는다.

**측정 (20 리포트 · 140 발화).** 오탐 셋은 두 실행 모두에서 사라졌다.
그러나 같은 프롬프트로 두 번 돌린 결과가 5건과 7건이고, **발화·명제 단위
재현율이 57%** 였다. 더 중요한 것은 `right chest tube` 건이 한 실행에서
**3/3 만장일치**로 나오고 다른 실행에서는 아예 안 나왔다는 점이다 —
**한 실행 안의 3/3 은 실행 간 안정성을 뜻하지 않는다.** 두 실행 모두에
나온 4건만 행동 가능한 결함으로 본다. 12 -> 5 같은 감소폭을 프롬프트
효과로 읽으면 안 된다.

**precheck (`GPT/precheck.py`) — `modifier_only_in_label` 신설.**
`indistinct_pulmonary_vasculature` 처럼 수식어가 라벨 안에만 있고
`descriptors` 에는 없는 경우다. `normalize.py` 의 `lift_modifier_prefix` 가
일부러 손대지 않는 여집합이다 — 그쪽은 "이미 descriptor 에 있으면 라벨에서
뗀다" 이고, descriptor 가 없으면 떼는 순간 그 사실의 유일한 사본이 사라진다.
그러니 고칠 곳은 정규화가 아니라 추출이고, 검출은 `DESCRIPTOR_LEXICON`
조회로 끝난다.

**억제층(SUPPRESSED)이 아니라 ADVISORY 에 두었다.** 이 파일에는 severity
접두 규칙을 통째로 뺀 이력이 있다 — 잡힌 2건이 `small_cell_carcinoma` 와
`large_bowel` 로 둘 다 고유명이었고, "0건을 잡는 규칙과 2건을 틀리는 규칙
중에서는 전자가 낫다" 고 적혀 있다. 그 원칙은 **모델이 반박할 수 없는 층**
에 대한 것이다. 고유명은 `MODIFIER_IS_THE_NAME` 으로 빼고 (precheck 전용 —
`normalize.py` 는 읽지 않으므로 데이터 불변), 나머지는 ADVISORY 에 두어
모델이 반박할 수 있게 했다.

| | precheck 지적 | 그중 신규 코드 |
|---|---|---|
| Prompt | 293 -> 318 | 25 |
| Prompt21 | 113 -> 128 | 15 |

Prompt 25 대 Prompt21 15 는 이 축에서도 Prompt21 이 낫다는 뜻이다.
정밀도는 **아직 측정되지 않았다** — `out/gpt_records/Prompt21/goldset/
sheet_precheck.tsv` (128행) 를 채워야 한다.

**하지 않은 것**: "선행검사 참조 없는 comparison" (`Enlarged` 로 worsened
를 단정한 건) 은 규칙으로 만들지 않았다. 표에 없는 comparison cue 가 두 팔
모두 12~13% 나오는데, 그 대부분이 `increase`/`decrease`/`no change`/
`removed`/`resolving` 같은 **형태론 누락**이다. `COMPARISON_CUES` 는
`normalize.py` 가 읽으므로 손대면 데이터가 바뀐다. 그 표를 메우기 전에는
진짜 결함과 표의 구멍이 구분되지 않으므로, 3단계로 넘긴다.


### 2026-09-14 (1) — 수식어 lift

step 2 가 수식어를 라벨에서 descriptor 로 올리기 시작했다 (`focal_consolidation`
+ `{extent focal}` -> `consolidation` + `{extent focal}`). E3 의 정상성 lift 를
다른 축으로 일반화한 것이고, 49,405 레코드가 바뀌었다.

**지문은 그대로다** (107·130·75·149·7) — 표 크기가 아니라 `normalize.py` 가
바뀌었다. 그래서 이 날짜 앞뒤의 리포트는 지문이 같아도 비교 대상이 아니다.
아래 해시가 그 구분선이다.

| 파일 | sha256 |
|---|---|
| `Pipeline/normalize.py` (lift 포함) | `73c36d98bbfecd4c695dfffc024ebaef8f7bdd6007f02cd0420297e1c3cf98dd` |
| `Prompt2/ontology.py` (`appearance of` · `MODIFIER_LIFT_EXCEPTIONS`) | `79113552b42c5951d5717ba94a981be483e53c7b16311b6b3065aee8760ea34f` |
| `Pipeline/validate.py` (검사 3종) | `8b3f19520ccf98bb40a2af6669850e4b323c4232c66ece20307e09ad517a5405` |

적용 직전 상태는 `/data3/backup/ReportCXR-Ko/jsonl-v5pre-lift-20260914/` 에 있다.

> **멱등이 아니어서 한 번 되돌렸다.** 첫 구현은 접두를 한 번에 하나만 벗겨서
> `focal_nodular_density` -> `nodular_density` -> `density` 처럼 두 겹인 라벨이
> 2차 통과에서 또 바뀌었다 (test 5 · validate 1). 고정점은 step 2 의 전제이므로
> 백업에서 복원하고, 벗길 것이 없을 때까지 도는 형태로 고쳐 다시 적용했다.
> 적용 후 4개 split 전부 NET diff 0.

2026-09-14 에 주석을 정리하면서 세 파일의 해시가 바뀌었다. **주석만 바뀌었고 표의
내용은 그대로다** — 프롬프트 문자열 · 예시 · 온톨로지 전 테이블 · step 2·3 산출물
72개 항목을 정리 전후로 대조해 전부 동일함을 확인했다. 이전 값은
`git log -- Prompt/ontology.py` 에 남아 있다.

---

### 2026-09-14 (2) — `BILATERAL_COLLECTIVE` 왕복 두 줄 추가

rule 17(snake_case·단수)이 `bronchi`/`pleural_sinuses` 처럼 불규칙 복수인
ANATOMY 라벨까지 무차별로 단수화하면, 그 결과(`bronchus`/`pleural_sinus`)를
되돌릴 왕복 항목이 표에 없어 `ANATOMY` 밖으로 새어나간다 --
`jsonl/Prompt`에 `pleural_sinus`(단수, 2건)가 실제로 이렇게 새 있었다.
13개 bilateral 라벨 중 8개만 `BILATERAL_COLLECTIVE`에 왕복이 있었던 것이
원인이고, 남은 셋(`pulmonary_vasculature`·`lung_parenchyma`·
`lung_interstitium`)은 규칙적 "-s" 복수가 아니라 애초에 이 위험이 없다.

`content_hash` 는 이 변경으로 `ab189fa7ef93b774` -> `25f2578fc145fcc9` 로
바뀐다. **표가 바뀌었으니 바뀌는 게 맞다** -- 이 지문 층이 잡으려던 바로
그 경우다.

### 2026-09-14 (3) — `SIDED_MIDLINE` 에 실사례 확인된 4계열 추가

`ANATOMY` 에서 `midline` 로 선언된 라벨 25개 중 **21개가 예외 목록에
없었다.** 그래서 판독문이 매일 쓰는 정상적인 서술이 모순으로 잡혔다.

```
"Mild indentation of the left trachea"          trachea 는 midline 인데 left?
"leads extending into the right heart"          heart 는 midline 인데 right?
"right-sided convex scoliosis in the thoracic spine"
"terminating in a known left superior vena cava"   (실제 해부 변이)
```

넷 다 **midline 구조를 한쪽 경계나 변이로 서술한 것**이고, 예외 목록이
이미 종격동에 대해 봐주던 것과 같은 모양이다. 실제 코퍼스 사례가 있는 넷만
추가했다 — `trachea`, `heart`+`cardiac_silhouette`, spine 계열 6개,
svc 계열 6개. 사례가 없는 `carina`·`aorta`·`esophagus`·`sternum` 등은
**추측으로 넣지 않았다**: 예외를 넓히는 것은 검사를 무디게 하는 일이라
근거 없이 하면 안 된다.

`aortic_knob` 오탐 4건은 원인이 다르다(측면이 안 적힌 문장에 인접 문맥의
`midline` 이 번진다). 별개 결함으로 남겨 두었다.

4개 split 전수 확인: 대상 라벨 0건, 남은 findings 는 전부 무관한 라벨.
`SIDED_MIDLINE` 7 -> 22.


### 2026-09-14 (4) — E2 를 `normalize.py` 에 구현

E2(혈관 구간은 `zone` 이 진다)는 2026-09-04 에 결정되고 어휘
(`vocabulary.VESSEL_SEGMENTS` · `VESSEL_SEGMENT_ALIASES`)까지 만들어 두고도
**step 2 구현이 없어 열 달치 문서에서 계속 "미구현"으로 남아 있던 항목**이다.
프롬프트는 v2 부터 이미 `svc` + `zone=mid` 를 내고 있었고, step 2 만 받아 줄
준비가 안 돼 있었다.

두 절반을 다 구현했다.

| | 무엇 | 예 |
|---|---|---|
| **E2(a)** | 합성 라벨을 구조 + 구간으로 분리 | `mid_svc` -> `svc` + zone `mid` |
| **E2(b)** | 기구 끝 위치 descriptor 를 anatomy 로 (rule 7) | `{device_position: tip_in_mid_svc}` -> anatomy `svc`/zone `mid`/role `tip_location` |

구현하면서 함정 넷을 지났고, 넷 다 이 저장소가 이미 적어 둔 원칙으로 풀렸다.

| 함정 | 무엇이 잘못될 뻔했나 | 어떻게 막았나 |
|---|---|---|
| 구조 이름 속 방향어 | `inferior_vena_cava` 가 `distal` + `vena_cava` 로 쪼개진다 | 베이스가 **단독으로** 혈관 라벨이어야 한다. `"vena cava"` 는 라벨이 아니므로 IVC·SVC 본체는 도달하지 않는다 |
| 멱등성 | `"mid/lower SVC"` 와 `"midportion of the superior vena cava"` 가 2차 통과에서 또 바뀌었다 | 서로 다른 구간이 둘 이상이면 범위로 보고 None. `vena` 앞의 방향어는 구간으로 읽지 않는다 |
| 과잉 적용 | `pulmonary_vasculature` 의 `perihilar`·`diffuse` 가 지워진다 | 구간은 **카테터가 지나는 도관**의 것이다 (`SEGMENTED_VESSELS`). 양폐에 퍼진 나무는 폐야로 나눈다 |
| 범위 표현 | `"mid to low SVC"` 가 한쪽 끝으로 단정된다 | zone 을 비우고 원문 범위는 `anatomy.text` 에 남긴다 -- 구멍이 거짓 진술보다 낫다 |

**중복 제거가 실제 작업의 대부분이었다.** 3개 split 에서
`device_position_duplicate_dropped` 371 대 `device_position_to_anatomy` 4 --
코퍼스는 이미 기구 끝을 anatomy 와 descriptor 양쪽에 적고 있었다. v1 예시가
그렇게 가르쳤기 때문이고(`Prompt2/README.md` §1), E2 는 그 둘 중 rule 7 이
지정한 쪽만 남긴다.

검증: 4개 split 전량에서 **재정규화 2차 통과 NET diff 0**(고정점 유지),
새 검증 오류 0건(오히려 `laterality_contradicts_label` 오탐 1건 감소),
`renormalize.py` 안전장치 다섯 통과(metric C 보존 · 스키마 결함 0 · 명제 수
불변), 64문장 A/B 영향 없음(v3.4 여전히 0/64).

#### 적용 (2026-09-14 저녁)

`renormalize.py` 로 4개 split 전량에 적용했다. 직전 상태는
`/data3/backup/ReportCXR-Ko/jsonl-v6pre-E2-20260914/` 에 있다.

| split | 바뀐 레코드 | 명제 수 |
|---|---|---|
| `train` | 22,183 | 1,340,923 -> 1,340,923 (불변) |
| `validate` | 108 | 7,183 -> 7,183 |
| `test` | 257 | 11,835 -> 11,835 |
| `test_reviewed` | 36 | 1,930 -> 1,930 |
| **합계** | **22,584** | |

노트 분포(train): `device_position_duplicate_dropped` 20,712 ·
`anatomy_label` 11,633 · `vessel_segment_from_label` 10,840 ·
`lung_zone_on_vessel_dropped` 592 · `device_position_to_anatomy` 191 ·
`vessel_segment_from_text` 94.

적용 후 실측(3개 작은 split): `svc` 계열 anatomy 가 합성 라벨 없이
`svc`+구간으로 모였고(distal 88 · mid 79 · proximal 34 · 없음 44),
남은 합성 라벨은 **6건**(전부 `lower_svc_cavoatrial_junction` 같은 접합부
복합어 -- 커버리지 공백이지 E2 의 실패가 아니다). `tip_in_*`/`tip_at_*`
descriptor 는 451 -> 76 (83% 해소).

> **⚠️ Verify §P1 의 "vessel segment in an anatomy label" 은 이 변화를
> 보여주지 못한다.** 그 검사의 정규식은 `svc|ivc|cavoatrial_junction|
> above_carina|below_diaphragm` 이 **들어간 모든 라벨**을 세므로, 정본인
> `svc` 자신도 센다. 즉 E2 가 성공할수록 그 숫자는 오히려 `svc` 로 모인다.
> 같은 절의 "tip position in a descriptor" 도 `*_position$` 를 포함해
> `appropriate_position` 처럼 **장소가 아닌** 상태 표현까지 센다.
> 지표를 고칠지는 미결이고, 그때까지 E2 의 진척은 위의 실측(합성 라벨 6건,
> tip descriptor 76건)으로 읽어야 한다.

#### train 전량 검증 (1,114,559 레코드)

**재정규화 2차 통과 0건** -- 111만 규모에서도 고정점이 유지된다.
적용 후 `renormalize.py --dry-run` 도 4개 split 전부 `changed records: 0`.

검증 findings 의 변화는 **error 가 줄고 warning 이 조금 늘었다.**

| 코드 | 심각도 | 전 | 후 | |
|---|---|---|---|---|
| `laterality_contradicts_label` | error | 1,494 | **1,482** | -12 |
| `descriptor_text_not_in_utterance` | error | 911 | **907** | -4 |
| `should_be_one_proposition` | warning | 736 | 745 | +9 |
| `section_conflict` | warning | 15,052 | 15,063 | +11 |
| `device_role_on_non_device` | warning | 280 | 281 | +1 |

늘어난 셋은 전부 **E2 가 anatomy 항목을 새로 만들기 때문**이다 (train 191건).
새 항목의 그룹이 섹션 제목과 다르면 `section_conflict` 가 뜨고, descriptor 가
사라지면서 두 명제가 더 닮아 보이면 `should_be_one_proposition` 이 뜬다.
**둘 다 결함 판정이 아니라 사람이 볼 자리의 표식**이고, 그 대가로 하드 에러
16건이 사라졌다.

| 파일 | sha256 (16자) |
|---|---|
| `Prompt2/ontology.py` content_hash | `7259390a6aaaf5d1` |
| `Pipeline/normalize.py` | `6515bc222b6ce347` |
| `Pipeline/validate.py` | `e88eecc9526cb75d` |

| split | 적용 후 sha256 (16자) | study |
|---|---|---|
| `validate` | `35f83d75b0bb3c55` | 976 |
| `test` | `e9ce1a16f771792d` | 1,459 |
| `test_reviewed` | `a9b5b1104474827c` | 233 |

### 체크섬 (2026-09-14)

| 파일 | sha256 |
|---|---|
| `Prompt2/ontology.py` | `4c3369950f19b3064c0dbf6bfbd5f756c52f1811399df3a633d3e0f31027916d` |
| `Prompt/ontology.py` | `9bab6a0dd2091e74cf2b51076dda211042a9ab5ea188bf1c5258f3e8bb99597c` |
| `Pipeline/normalize.py` | `5901c104720dbf00a6173ea7a91992d268dbf06020ac631975c3c14dcfa9feea` |

## 5. 드리프트를 막는 장치

| | 어디 | 무엇 |
|---|---|---|
| 0 | `Prompt2/schema.py` | v1 스키마와 zone 말고 다른 곳이 다르면 import 시점에 실패 |
| 1 | `Verify/metrics/m03_fixed_point.py` | 외부 `normalize.py` 를 로드해도 패키지 경로를 **append** 하므로 표는 항상 이 저장소 것 |
| 2 | `Pipeline/renormalize.py` | 쓸 정규화기가 이 저장소의 것과 다르면 `--allow-drift` 없이 거부 |
| 3 | 모든 리포트 | 첫머리에 온톨로지·코드·데이터 지문 세 표 (§4) |
| 4 | `Pipeline/` | step 1~3 이 표와 같은 저장소에 있다 |
| 5 | `Pipeline/validate.py` (`zone_missing_from_label` · `zone_not_canonicalized`) | 라벨이 zone 을 함의하면 `anatomy.zone` 은 그 값과 **정확히** 같아야 한다 (§6-1) |

이중 정본은 반드시 어긋나고, 어긋나면 어느 쪽이 데이터를 만들었는지 알 수 없게
된다. 프롬프트 본문도 표도 사본을 두지 않는다.

---

## 6. 미해결 — 정직하게

`jsonl/` 을 재정규화하면 바뀌는 레코드가 **27건** 있었다
(train 17 / test 1 / test_reviewed 9). 원인 가설 셋을 검증했고 **셋 다 기각**됐다.

| 가설 | 검증 | 결과 |
|---|---|---|
| 구버전 표로 정규화됨 | `ANATOMY` · `ZONE_WORDS` · `SECTION_ALIASES` 대조 | **동일.** 기각 |
| step 2 미실행 | `mediastinum` 108,974 중 108,961 이 이미 정규화됨 | **실행됨.** 기각 |
| `normalize.py` 코드 드리프트 | 커밋 이력상 변경 없음 | 기각 |

남는 설명은 **전량 추출이 다른 기기에서, 다른 시점의 코드로 돌았다**는 것뿐이고
그 기기의 이력은 여기 없다. 실무적으로는 재정규화로 해소되었다 — 4개 split 전부
NET diff 0. **앞으로는 이 저장소가 그 질문에 답한다.**

### 6-1. E7 — zone 이 라벨에 구워진 23개 (2026-09-14, 해소)

`ANATOMY` 의 23개 라벨(`lung_base`, `hilum`, `upper_lobe`, ... )은 zone 을
라벨 철자 자체에 담고 있으면서 `anatomy.zone` 필드도 따로 갖는다. 같은 사실이
두 필드에 있는 것은, 그 둘이 **어긋날 수 없다는 것이 보장될 때만** 안전하다 —
아니면 어느 쪽이 정본인지 매번 다시 물어야 한다.

라벨을 쪼개는 마이그레이션(`lung_base` -> `lung` + zone `basilar`)은 하지
않았다. step 2 의 접두 제거가 멱등이 아니어서 한 번 되돌린 전례(§4)와 같은
함정이고, 라벨 어휘가 좁아지면 서로 다른 개념이 충돌한다. 대신 **불변식으로
못 박았다**: `Pipeline/validate.py` 의 `check_rules` 에 `zone_missing_from_label`
· `zone_not_canonicalized` 두 검사를 추가해, 소스가 `section_context` 가
아닌 한 `anatomy.zone` 이 라벨의 implied zone 과 **정확히** 같지 않으면 error
가 뜨도록 했다. (기존 `zone_contradicts_label` 은 서로 양립 불가능한 경우만
잡았고 — "upper" vs "lower" — "basilar" 처럼 호환되지만 다른 철자인 경우는
빠져나갔다.)

4개 split 전수(1,127,317 레코드: train 1,114,559 + validate 6,015 + test
9,635 + test_reviewed 1,565)에 적용한 결과: 새 두 검사는 **전량 0건**, 기존
`zone_contradicts_label` 은 진짜 모순 191건(test 6건 -- `hilum`+zone
`lower`, `lower_lobe`+zone `retrocardiac` -- , train 185건)을 그대로 잡는다.
즉 현재 데이터는 이미 그 불변식을 만족하고 있었고, 이번 변경은 그것을
**우연이 아니라 강제된 것**으로 바꿨을 뿐이다. 191건의 진짜 모순은 이 불변식과
무관한 별개 결함이며 리뷰 대상이다.

---

## 7. 실행 환경

| | |
|---|---|
| 전량 추출 | **다른 기기**, Qwen3.8-27B |
| 이 기기 | zeus-02, GTX 1080 Ti ×4 (11GB, Pascal). **Qwen3.8-27B 8bit** 프로토타입용 |
| 엔드포인트 | `http://localhost:8080/v1`, 모델명 `qwen3.8-27b` (llama.cpp) |

**8bit 는 구조화 출력에서 사실상 무손실**이라는 것이 문헌의 보고지만, 프롬프트
개선을 이 기기에서 측정하면 프로덕션(full precision)으로 전이된다는 보장이 없다.
**양자화 델타를 먼저 재야 그것이 실험의 노이즈 바닥이 된다.**
