# Prompt2 — 지시서(v3.4) + 사전

> **한 줄 요약: 지금 쓰는 지시서와 사전이 둘 다 여기 하나에 있습니다.**
>
> - 예전에는 `Prompt2/`(v2 지시서 + 사전)와 `Prompt3/`(v2 위에 패치를 얹는 v3
>   지시서)로 나뉘어 있었습니다. **`Prompt3/` 는 이 패키지로 합쳤습니다** —
>   패치는 `system.py` 본문에 그대로 반영되어, 지시서는 이제 조립되는 것이
>   아니라 **한 편의 완성된 문서**입니다.
> - **사전(`ontology.py`·`vocabulary.py`)은 예전처럼 여기 것 하나**입니다.
>   사전이 지시서마다 다르면, 점수 차이가 지시서 때문인지 사전 때문인지 알 수
>   없기 때문입니다.
> - `Prompt/` 는 명세 3절을 그대로 옮긴 **원본(v1)** 이고 손대지 않습니다.
>   기준선이 움직이면 비교가 불가능해지기 때문입니다.
>
> **합치면서 잃은 것 하나:** v2 지시서 **본문은 더 이상 import 되지 않습니다.**
> git 히스토리에 있고, v2 팔의 결과 행은 이미 `out/ab/out.jsonl` 에 있으므로
> 채점은 그대로 되지만, **v2 팔을 다시 돌릴 수는 없습니다.**

여기의 지시서는 `Prompt/` 원본을 **1,131,774 레코드에 대한 측정으로만** 고친
것이다. 근거 없이 바꾼 문장은 없다.

**프롬프트에서 v1 과 다른 파일은 셋뿐이다** — `system.py`, `examples.py`,
`selection.py`. 여기에 더해 **이 패키지가 표의 정본을 들고 있다**:

| 파일 | 무엇 |
|---|---|
| `system.py` | 지시서 전문 (v2 의 rule 2·3·7·11·16·17 + v3 의 7개 패치) |
| `examples.py` | few-shot 11개. 전부 step 2 고정점 |
| `selection.py` | 발화마다 어느 예시가 붙는지 |
| `ontology.py` | E1(편측성) · E2(혈관 구간) · E3(정상성) 적용 표. **지문의 출처** |
| `vocabulary.py` | E2 혈관 구간 zone 을 포함한 닫힌 어휘 |
| `relations.py` | RadLex 가 모르는 개념과 관계 (1-D) |
| `schema.py` | v1 스키마에 zone 값만 넓힌 파생. 구조의 정본은 `Prompt/schema.py` |

**표가 하나라는 조건은 그대로다.** step 2·3 과 `Verify/` 가 전부 이 표를 읽고,
A/B 의 두 팔은 프롬프트만 다르고 표는 공유한다. 표가 팔마다 움직이면 지표의
차이가 프롬프트 때문인지 표 때문인지 알 수 없게 된다 (PROVENANCE.md 의
"온톨로지 지문").

```python
from Prompt2 import SYSTEM_PROMPT, PROPOSITIONS, TOOL_NAME, select
```

> **데이터 쪽 팔 이름도 따라갔다.** v3.4 로 뽑은 결과는 `jsonl/Prompt3/` 에
> 있었고 지금은 **`jsonl/Prompt2/`** 다 (내용은 그대로, `test_reviewed`
> 233 study). 팔 이름은 패키지 이름을 따르므로, 합치면서 같이 옮겼다.

## 실행

환경변수 하나만 바꾼다. 표와 스키마는 어느 쪽이든 이 패키지 것이다.

```bash
cd Pipeline
REPORTCXR_PROMPT=Prompt2 python3 parse_utterances.py --text "Right PICC tip in the mid SVC."
REPORTCXR_PROMPT=Prompt2 python3 parse_utterances.py --jsonl subset.jsonl --yes
REPORTCXR_PROMPT=Prompt2 python3 parse_utterances.py --dump-prompt OUT.md   # 지시서 전문
```

A/B 는 `ab/` 에서 돈다. 저장소 루트에서 실행한다. **돌릴 수 있는 팔은 `v1` 과
`v3.4` 둘뿐이다** — 나머지 팔은 지시서 본문이 git 히스토리에만 있어서
`run_ab.py` 가 이름을 대면 에러로 막는다. 채점은 `out.jsonl` 에 이미 있는
행을 읽으므로 예전 팔도 그대로 비교된다.

```bash
python3 Prompt2/ab/build_sample.py        # 표본 64문장 (결정적, seed 20260907)
python3 Prompt2/ab/run_ab.py v1 v3.4      # 두 팔 실행. 중단하면 이어서 돈다
python3 Prompt2/ab/renorm.py              # 채점 전 필수 — 모든 팔을 같은 step 2·3 에 맞춘다
python3 Prompt2/ab/score_ab.py v2.1 v3.4  # 채점 (예전 팔은 out.jsonl 에서 읽는다)
python3 Prompt2/ab/show_ab.py S3          # 한 층을 나란히 눈으로
```

산출물은 `../out/ab/` 로 간다 (`out.jsonl` · `logs/`). 입력인 `ab/sample.jsonl` 만
코드 옆에 남는다 — 생성물이 아니라 고정된 시험 문제지다.

---

## 지금 지시서 (v3.4) — 경과와 근거
> **한 줄 요약: 지금 쓸 지시서입니다. 64문장 시험에서 오류 0개.**
>
> - v3 는 원래 v2 지시서 위에 **필요한 문장만 찾아 바꾸는 방식(패치)** 으로
>   `Prompt3/system.py` 에 얹혀 있었습니다. **지금은 그 패치가 `system.py`
>   본문에 반영되어 있어** 읽을 때 두 파일을 겹쳐 볼 필요가 없습니다. 아래에서
>   "패치"라고 부르는 것은 전부 이미 반영된 상태입니다.
> - 아래는 v3.0 → v3.4 로 오면서 **무엇을 고쳤고 무엇을 잘못 짚었는지**의
>   기록입니다. 실패한 시도도 그대로 남겨 두었습니다.
>
> #### ⚠️ 아래 수치는 전부 E2 적용 **이전** 측정치입니다
>
> 2026-09-14 저녁에 E2(혈관 구간)를 표와 데이터에 적용하면서, **모든 팔의
> 점수가 함께 내려갔습니다** — 표 수정이 오류 한 종류를 전 팔에서 동시에
> 없앴기 때문입니다. 지금 `score_ab.py` 를 돌리면 아래와 다른 값이 나옵니다.
>
> **현재 값 (E2 적용 후, 같은 64문장)**
>
> | 팔 | error | warning | |
> |---|---|---|---|
> | v1 | 4 | 46 | 첫 지시서 |
> | v2 | 0 | 40 | **지금 코드로는 재현 안 됨** (아래 §기준선 정정) |
> | **v2.1** | **1** | **37** | 합치기 전 `Prompt2/system.py` 가 이것이었다 |
> | v3.0 | 2 | 30 | |
> | v3.1 | 1 | 29 | |
> | v3.2 · v3.2b | 1 | 30 | |
> | v3.3 | 1 | 29 | |
> | **v3.4** | **0** | **24** | **현재 최선** |
>
> 판정은 바뀌지 않았습니다 — 실제로 쓸 수 있는 기준선(v2.1)과 v3.4 를 맞대면
> 여전히 **1 → 0, 37 → 24** 로 v3.4 가 이깁니다. 아래 본문의 경과와 진단은
> 그대로 유효하고, **절대 수치만 이 표로 읽으시면 됩니다.**

---

### ✅ 전량 판정 — `test_reviewed` 1,565문장 (2026-09-15)

**64문장은 방향만 보는 표본이라고 계속 적어 왔고, 이제 사람이 검수한 split
전량으로 판정했다.** v3.4 로 1,565문장을 다시 뽑는 데 12.2시간이 걸렸다.

| | v1 (기존 데이터) | **v3.4** | |
|---|---|---|---|
| error 가 있는 레코드 | 9 (0.58%) | **3 (0.19%)** | **-67%** |
| error 총 건수 | 9 | **4** | |
| warning 총 건수 | 264 | **147** | **-44%** |
| 명제를 하나도 못 뽑은 발화 | 38 (2.4%) | **7 (0.45%)** | **-82%** |
| 뽑아낸 명제 수 | 1,930 | 2,042 | +112 |
| 파일 구조 · 고정점 | — | ✅ 통과 | |

**64문장에서 본 방향이 24배 규모에서 그대로 재현됐다.** 특히 warning 이 264 ->
147 로 준 것은 64문장(46 -> 24)과 거의 같은 비율이다.

경고 항목별로도 v3 가 겨냥한 축이 정확히 움직였다:

| 코드 | v1 | v3.4 | 겨냥한 규칙 |
|---|---|---|---|
| `qualified_negation_unwarned` | 35 | **4** | rule 11 |
| `no_propositions` | 38 | **7** | rule 2 |
| `anatomy_span_is_side_only` | 114 | **69** | rule 18 |
| `anatomy_source_carries_span` | 38 | **29** | rule 18 |
| `anatomy_span_is_relative` | 5 | **0** | rule 18 |
| `section_conflict` | 16 | 18 | (증가, 경고) |
| `should_be_one_proposition` | 2 | 9 | (증가, 경고) |

#### 남은 error 3건 — 전수 확인

| 원문 | 무엇이 잘못됐나 | 판정 |
|---|---|---|
| `"Moderate atelectasis at the right base, otherwise clear."` | entity.text 로 `"lungs are clear"` 를 냈다. 원문에 그 구간이 없다 | **진짜 결함** (rule 3). 생략문("otherwise clear")이 새 방아쇠 |
| `"Persistent increased retrocardiac opacification..."` | `"increased"` 를 severity descriptor 로 넣었다. 시간 비교다 | **진짜 결함** (rule 12) |
| `"...right suprahilar region of the right upper lobe..."` | `upper_lobe` 에 zone `perihilar`. 표는 `upper` 를 함의 | **검사기 쪽 의심** (아래) |

세 번째는 **엽의 하위 구역**을 말한 경우다. 발화가 "상엽의 **상폐문부**"라고
명시했으므로 둘 다 참이고, 모순이 아니라 **더 정밀한 서술**이다. 같은 모양이
기존 코퍼스에도 있다 (`lower_lobe` + `retrocardiac` 4건, `hilum` + `lower` 2건).

`SIDED_MIDLINE` 때와 같은 판단이 필요하다 — 예외를 넓히면 검사가 무뎌지므로
**근거 없이 넓히지 않는다**. 현재 근거는 6~8건뿐이라 **미결로 남긴다.**

#### 주의 — 추출 도중에 정규화기가 바뀌었다

추출은 2026-09-14 20:34 에 시작됐고, E2 구현은 **그날 저녁 그 뒤**였다.
파이썬은 시작 시점에 모듈을 읽으므로, 12시간 내내 **E2 이전의
`normalize.py`** 로 정규화된 채 기록됐다. 그 결과 9건이 고정점이 아니었다.

`REPORTCXR_ARM=Prompt2 python3 renormalize.py --split test_reviewed` 로
E2 를 입혀 **고정점 0건**을 확인했다. 직전 상태는
`/data3/backup/ReportCXR-Ko/jsonl-Prompt3-v34-preE2renorm-20260915/` 에 있다.

> **다음에 긴 추출을 돌릴 때의 교훈**: 추출 중에는 `normalize.py` 를 고치지
> 말거나, 고쳤으면 끝난 뒤 반드시 재정규화한다. 리포트의 고정점 검사가
> 이것을 잡아 준다.

v2 의 규칙들은 **무엇을 빼라**고는 말했지만 **뺀 것이 어디로 가는지**를 절반만
말했다. 목적지를 적은 규칙은 지표가 움직였고, 안 적은 규칙은 새 결함을 만들었다.

| 규칙 | 목적지 | 결과 (64문장 A/B) |
|---|---|---|
| rule 16 side → `laterality` | ✅ | P1a 22.9% → 2.9% |
| rule 14 정상성 → `descriptor` | ✅ | P1c 8.0% → 0.0% |
| rule 7 기구 끝 → `anatomy.role` | ✅ | descriptor 기구위치 20.9% → 0.0% |
| rule 17 단수 | ❌ 복수가 나르던 side 의 행선지 없음 | `lungs→lung` 에서 bilateral 소실 |
| rule 3 text/label | ❌ text 가 무엇을 **배제**할지 없음 | entity text `"Dense opacity"` |

v3 는 그 빈자리를 메운다. **표·스키마·어휘는 `Prompt2` 것을 그대로 쓴다** —
프롬프트만 움직여야 차이가 프롬프트 때문이라고 말할 수 있다.

### 여섯 패치와 근거

근거는 전부 실측이다 (`validate + test + test_reviewed`, 명제 20,948 / anatomy 22,493).

| 규칙 | 무엇을 바꿨나 | 실측 근거 |
|---|---|---|
| **3** | entity `text` 는 descriptor 가 이미 가진 수식어를 포함하지 않는다 | v2 가 `"Dense opacity"`, `"large subpulmonic effusion"` 를 냄 |
| **4** | 개체 의미가 위치를 정하면 섹션 헤더를 보지 않는다 | pneumothorax 의 anatomy source: `entity_semantics` 1,545 대 `section_context` 136 |
| **11** | 하한 한정("at least")에 `"Qualified assertion:"` 경고 | rule 11 이 한정 **부정**만 다루고 있었다 |
| **17** | 복수가 나르던 side 는 `laterality` 로 간다 | `"the lungs"` → `lung` + unspecified (bilateral 소실) |
| **18** 신설 | `source` 가 `text` 를 정한다 — 파생 source 면 `text` 는 null, 편측 낱말·전치사구는 구조의 span 이 아니다 | 파생 source + text 존재 **358** · 편측 낱말만 **1,090** · 전치사 시작 **120** |
| **19** 신설 | 검사 자체를 기술한 문장(`limited`, `obscured`, `poorly assessed`)을 버리지 않는다 | 판독 제한 발화 162 중 **119(73%)** 가 통째로 사라짐. P3 최저 피복: `assessment` 0.215 · `evaluation` 0.186 |
| **20** 신설 | 한 정보는 한 자리 — 필드가 있는 factor 는 라벨에 다시 쓰지 않는다 (14·16 의 일반화) | 라벨이 descriptor 를 되풀이하는 명제 **977** |

예시도 하나 더했다 — `limitation`. rule 19 에 대응 예시가 아무 데도 없었고,
v2 의 교훈이 "예시가 규칙보다 세게 가르친다"였다. 시험 문장과 겹치지 않는
실제 코퍼스 문장을 골랐다.

### 비용

프롬프트가 6,878자 → 9,693자로 **41% 길어졌다.** 규칙이 늘면 희석될 수 있으므로
이것 자체가 가설이고, 같은 64문장 A/B 가 판정한다.

### 실행

```bash
python3 Prompt2/ab/run_ab.py v3        # 같은 64문장, v3 팔만
python3 Prompt2/ab/renorm.py           # 채점 전 필수 — 모든 팔을 같은 step 2·3 으로
python3 Prompt2/ab/score_ab.py v2 v3   # v2 대 v3
python3 Prompt2/ab/show_ab.py S1       # 한 층을 나란히

REPORTCXR_PROMPT=Prompt2 python3 Pipeline/parse_utterances.py --text "..."
python3 Pipeline/extract_split.py --split test_reviewed --arm Prompt2
```

### 예측표 — 결과를 보기 전에 박아 둔다

같은 64문장에서 v2 를 기준으로 v3 가 무엇을 움직여야 하는가. **움직이지 않으면
그 패치가 틀렸거나 프롬프트가 길어져 희석된 것이다.**

| 지표 | v1 | v2 (기준) | v3 예측 |
|---|---|---|---|
| rule 19 판독 제한 보존 | 0/2 | 0/2 | **2/2** — 예시까지 넣었으므로 |
| rule 11 하한 한정 경고 | 0/1 | 0/1 | **1/1** (n=1, 판정 불가) |
| rule 18 파생 source 가 text 보유 | 9.0% | 6.9% | **크게 감소** |
| rule 18 편측 낱말만인 span | 10.0% | 9.9% | **크게 감소** — v2 가 전혀 못 줄인 축 |
| rule 3 entity text 에 수식어 | 17 | 15 | 감소 |
| rule 20 라벨이 descriptor 되풀이 | 15 | 9 | 감소 |
| error 가 있는 레코드 | 7.8% | 1.6% | **유지** (퇴행 없음이 통과 조건) |
| S8 대조군 finding | 0 | 0 | **0** |
| step 2 가 라벨을 고친 횟수 | 53 | 25 | 유지 또는 감소 |

n 이 작은 둘(rule 19 는 2문장, rule 11 은 1문장)은 **방향만** 보는 것이고
판정은 `test_reviewed` 전량에서 난다.

가장 큰 위험은 프롬프트가 41% 길어진 것이다. 희석이 일어나면 **이미 잘 되던
축**(error 1.6%, S8 0)이 먼저 무너진다. 그 두 줄이 퇴행하면 패치 수가 아니라
길이가 원인이므로, 규칙을 줄이고 예시로 옮겨야 한다.

### 실측 — 세 라운드

같은 64문장, 표·정규화기·검증기 동일. 채점 전 `renorm.py` 로 모든 팔을 같은
step 2·3 에 맞췄다.

| 지표 | v2 | v3 | v3.1 | 예측 대비 |
|---|---|---|---|---|
| error 가 있는 레코드 | **1.6%** | 4.7% | 3.1% | ❌ 퇴행 |
| warning finding | 20 | 16 | **16** | ✅ |
| rule 19 판독 제한 보존 | 0/2 | **2/2** | **2/2** | ✅ 맞음 |
| rule 20 라벨이 descriptor 되풀이 | 9 | **1** | 3 | ✅ |
| rule 18 파생 source + text | 6.9% | **1.9%** | **1.9%** | ✅ |
| rule 3 entity text 에 수식어 | 15 | 10 | **8** | ✅ |
| `qualified_negation_unwarned` | 4 | **1** | **1** | (예측 안 함) |
| rule 18 편측 낱말만인 span | 9.9% | 9.3% | 9.7% | ❌ 안 움직임 |
| rule 11 하한 한정 경고 | 0/1 | 0/1 | 0/1 | ❌ (n=1) |
| S8 대조군 finding | 0 | **0** | **0** | ✅ |

#### 배운 것 셋

**1. 길이는 원인이 아니었다.** 프롬프트가 42% 길어져도 S8 대조군은 세 팔 모두 0.
희석 가설은 기각됐고, 퇴행은 전부 규칙 간 충돌에서 왔다.

**2. 나는 v1 의 실수를 반복했다.** rule 3 의 새 문단을 등위 문단 **뒤에** 붙였더니
모델이 마지막 지시를 "이름을 온전히 써라" 로 읽고 원문에 없는 이름을 조립했다
(하드 에러 2건, 전부 S4 층). 이 저장소가 이미 기록해 둔 실패 형태다 --
"rule 2 와 rule 3 이 서로 모순이었다".

v3.1 에서 순서를 뒤집자 1건이 돌아왔고 1건이 남았다. **순서 문제가 아니었다** --
중복 규칙을 span 규칙 안에 넣은 것 자체가 문제다. v3.2 는 rule 3 을 v2 원문
그대로 되돌리고(바이트 동일 확인) 그 문장을 rule 20 으로 옮기면서
"이것이 rule 3 을 이기지 못한다" 를 명시한다. `system.py` 는 이미
이 상태다.

**3. 편측 낱말 span 은 프롬프트로 안 움직인다.** 세 팔 모두 9.3~9.9% 로 붙박이다.
코퍼스 1,090건짜리 이 결함은 **step 3 검사의 몫**이지 규칙의 몫이 아니다.

#### 네 번째 라운드 — v3.2 는 안 고쳤다 (2026-09-14, 사후 기록)

v3.2 를 실행하고도(`out/ab/run_v32.log`) 이 문서에 결과를 적지 않은 채로
하루가 지났다 -- 표는 그대로인데 데이터가 다른, 이 저장소가 §온톨로지
지문에서 경계하던 바로 그 모양의 방치다. 뒤늦게 채점한 결과:

| 지표 | v2 (기준) | v3.2 |
|---|---|---|
| error 가 있는 레코드 | 1.6% | **3.1% -- 그대로, 안 고쳐짐** |
| rule 3 entity text 에 수식어 | 15 | **17 -- 악화** |
| `entity_text_not_in_utterance` | 0 | 1 |
| `should_be_one_proposition` (신규) | 0 | 1 |

**v3.2 가 고치려던 바로 그 결함이 v3.2 에서도 재현된다.** S4 층의
`"Right atrial and ventricular pacemaker leads present, with the ventricular
lead coursing in the mid RV."` 에서 v3.0 과 동일하게 `entity.text
"atrial pacemaker leads"` 를 조립한다 -- 원문에 없는 구간이다.

v3.1 의 원 출력을 다시 대조하면 범인이 좁혀진다. **v3.1 은 이 문장을 이미
고쳤었다** -- `entity.text "atrial"` / `"ventricular"`, 하드 에러 없음,
경고 하나뿐. v3.2 가 한 일은 그 문단을 rule 3 안에서 rule 20 으로 옮긴
것뿐인데 고쳐졌던 문장이 다시 깨졌다. 그렇다면 원인은 "rule 2 대 rule 3"
가 아니라 **rule 20 자신의 새 문장**이다:

> "The entity text follows the same rule where it can: a modifier you
> recorded as a descriptor is not part of the entity's own name."

이 지시가 "수식어를 지운 나머지"를 만들라고 하는데, 모델은 그 "나머지"를
**모자란 것으로 여기고 다른 절에서 head noun("pacemaker leads")을 끌어와
붙인다** -- rule 3 의 첫 등위 분배 예시("aortic, mitral, and tricuspid
valve repair" -> text "aortic")가 정확히 금지하는 동작이다. rule 20 이
rule 3 의 등위 분배 결과를 "부족한 이름"으로 오독하게 만든 것이다.

v3.2b(재실행)는 v3.2 와 findings 가 완전히 동일해 재현성만 확인했다.

**결론(정정): v3 계열은 아직 v2 를 못 이긴다.** 문제는 rule 2 도 rule 3
자체도 아니고, **rule 20 이 rule 3 의 등위 분배를 되돌린다**는 것이다.
그 전까지 프로덕션 팔은 v2 다.

#### v3.3 -- rule 20 에 등위 예외 명시

v3.1 이 우연히 피했던 것을 규칙으로 못 박는다. rule 20 의 entity-text
문단 끝에 `"Right atrial and ventricular pacemaker leads present"` 를
그대로 반례로 넣고, "rule 3 이 이미 등위로 나눈 head noun 을 rule 20 이
다시 붙이지 않는다" 를 명시했다 (지금은 `system.py` 본문). 표·스키마·어휘는
그대로, 문장 하나만 움직였다.

| 지표 | v2 (기준) | v3.2 | v3.3 예측 | v3.3 실측 |
|---|---|---|---|---|
| error 가 있는 레코드 | 1.6% | 3.1% | 1.6% 이하로 복귀 | 3.1% -- ❌ 안 줄었다 |
| S4 pacemaker-lead 하드 에러 | 없음 | 있음 | **없음** | **없음 -- ✅ 진단대로 고쳐짐** |
| rule 3 entity text 에 수식어 | 15 | 17 | v3.2 이하 | 17 -- ❌ 그대로 |
| rule 18 파생 source + text | 6.9% | 1.0% | v3.2 유지 | 0.9% -- ✅ |
| S8 대조군 finding | 0 | 0 | **0** | **0 -- ✅** |

**진단은 맞았고, 대가가 다른 곳에서 나왔다.** rule 20 을 고쳤더니 목표
문장(S4 pacemaker lead)은 정확히 예측대로 고쳐졌다 -- `entity_text_not_
in_utterance` 0/64 로 완전히 사라졌다. 하지만 error 있는 레코드 수는
2/64 로 그대로다. 원인은 다른 utterance:

```
"Bilateral pleural effusions, left greater than right."
  v3.2  p3  descriptor.text "greater than right"  label "less_than_left"
             (스팬은 원문 그대로, 라벨만 어긋남 -- 안전)
  v3.3  p3  descriptor.text "less than left"       label "less_than_left"
             (원문에 없는 구간을 만들어 붙임 -- 하드 에러)
```

v3.2 는 "greater than right" 텍스트를 재사용하면서 라벨만(안전하지 않게)
반대로 붙였을 뿐인데, v3.3 은 라벨과 짝을 맞추려고 **텍스트까지 새로
지어냈다.** rule 20 addendum 에 붙인 문장("head noun 을 다시 붙이지
않는다")이 이 utterance 와는 무관한데도, 프롬프트에 등위 반례를 하나 더
넣은 것 자체가 모델의 "이름과 라벨을 맞추려는" 성향을 다른 곳에서 건드린
것으로 보인다 -- 이 저장소가 이미 §2 에서 겪은 "규칙 하나를 고치면 다른
문장이 움직인다"의 재현이다.

**결론.** rule 20 대 rule 3 진단은 맞았고 그 문장으로 목표 결함은
없앴다 -- 이 부분은 다음 라운드에 들고 가도 된다. 그러나 같은 패치가
비교급("greater than X") 문장에서 새 결함을 냈으므로 **v3.3 은 아직 v2
를 이기지 못했다.** 프로덕션 팔은 계속 v2 다. 다음 라운드는 v3.3 의
rule 20 문장을 유지한 채, 비교급 descriptor 재사용(derived_from 명제가
부모의 텍스트를 반대 라벨로 재사용하는 경우) 을 별도 규칙으로 막아야
한다 -- "라벨을 바꿀 때 텍스트를 새로 짓지 말고 원문에 있는 대로 두거나
비워라" 가 유력한 다음 패치다.

#### 기준선 정정 -- "v2" 는 이미 재현 불가능했다

위에서 계속 기준으로 삼은 "v2 = 1.6%" 를 다시 파보니, out.jsonl 에 `v2` 로
찍힌 원본은 **같은 날 오후 1f9f47c(v2.1) 커밋으로 대체되기 전** 스냅샷이었다.
당시 `Prompt2/system.py` 의 RULES 본문은 v2.1 과 바이트 단위로 같았다 --
`diff <(git show 1f9f47c:Prompt2/system.py | sed -n '/^RULES/,$p') <(git show
<합치기_직전_커밋>:Prompt2/system.py | sed -n '/^RULES/,$p')` 가 빈 결과를
낸다. 즉 **그 코드를 그대로 돌리면 1.6% 가 아니라 3.1% 가 나왔다** -- v2.1 자신의 커밋 메시지가 이미
"side 번짐 표적은 고쳤고 rule 3 이 한 건 깨졌다, n=64 로는 판정이 안 된다"
고 적어 뒀는데, v3 라운드들이 이걸 "새 결함"으로 다시 발견한 것이었다.

그 "한 건 깬" 것이 바로 v3.0~v3.3 이 좇던 S4 pacemaker-lead 하드 에러다.
이후의 모든 실측은 `v2` 대신 `v2.1`(= 지금 코드)을 기준선으로 다시 잡는다.

#### 표 버그 둘을 고치자 v2.1 과 v3.3 이 같은 지점으로 수렴했다

`Prompt2/ontology.py` 의 두 표 버그(`BILATERAL_COLLECTIVE` 왕복 누락,
`SIDED_MIDLINE` 예외 21개 중 17개 누락 -- 커밋 `5fb2973`·`435172f`)를
고치고 저장된 원본을 `renorm.py` 로만 다시 돌렸더니(모델 재호출 없음),
전 팔에 공통이던 `trachea` 오탐이 사라지면서 v2.1 과 v3.3 이 정확히
같은 지점(1.6%, 각자 다른 결함 하나씩)으로 수렴했다:

| | v2.1 (현재 코드) | v3.3 |
|---|---|---|
| error 있는 레코드 | 1.6% (1/64) | 1.6% (1/64) |
| 남은 유일한 에러 | pacemaker-lead (S4) | pleura 비교급 |

두 결함을 나란히 보면 **같은 원인의 두 자식**이라는 것이 보인다. v1·v2
(원본)는 `"Bilateral pleural effusions, left greater than right."` 를
쪼개지 않고 명제 하나 + `descriptor.text "left greater than right"`
(원문 그대로)로 안전하게 처리했었다. v2.1 이 rule 16 에 붙인 "laterality
는 그 절에서만 읽는다" 문단이, 양쪽을 이미 다 말하는 분포 표현까지 쪽마다
쪼개도록 모델을 유도한 것으로 보인다 -- 쪼개고 나면 두 번째 쪽은 베낄
텍스트가 없어 지어내게 된다. pacemaker-lead 도 같은 모양이다.

#### v3.4 -- rule 2 에 "이미 양쪽을 말하는 분포는 안 쪼갠다" 추가 (실측)

v3.3 의 rule 20 패치는 유지하고, rule 2 에 새 항목을 하나 추가했다:
"left greater than right" 처럼 이미 양쪽을 말하는 분포 표현은 laterality
bilateral 인 명제 하나로 두고, 반대쪽 표현을 지어내지 않는다. 반례 문장을
그대로 박아 뒀다 (지금은 `system.py` 본문).

64문장 실측 (`score_ab.py v2.1 v3.4`, 표 버그 수정 반영):

| 지표 | v2.1 (기준) | v3.4 |
|---|---|---|
| **error 있는 레코드** | 1.6% (1/64) | **0.0% (0/64)** |
| S4 pacemaker-lead 하드 에러 | 없음 (v3.3 이 이미 고침) | 없음 |
| pleura 비교급 하드 에러 | 있음 | **없음 -- 목표 달성** |
| findings (warning) | 37 | **24** |
| rule 20 라벨이 descriptor 되풀이 | 9 | **3** |
| rule 18 파생 source + text | 6.1% | **1.0%** |
| S8 대조군 finding | 0 | **0** |

새로 생긴 것은 둘, 둘 다 warning 이고 n=1: `absent_without_cue`
(무관한 문장, "improved from previous consolidation") 와 raw 출력에서
`right_atrium` 라벨 하나(파이프라인 2단계가 어차피 다시 벗겨 낸다).
전체 warning 은 37 -> 24 로 오히려 줄었다.

**결론. v3.4 가 지금까지 나온 팔 중 처음으로 error 0/64 를 낸다.**
"프로덕션 팔은 v2" 는 이제 **v3.4** 로 바꾼다.
다음 관문은 이 결과를 `test_reviewed` 전량(1,565 레코드)에서 재확인하는
것 -- 64문장은 방향만 보는 표본이라는 원칙은 여전히 유효하다.

---

## 부록 — v2 가 v1 에서 무엇을 고쳤나

아래는 v2 를 만들 때의 기록이다. v3 는 이 위에 쌓였으므로, 진단(특히 "원인은
규칙 문구가 아니라 예시였다")은 여전히 이 지시서를 읽는 데 필요하다.

### 1. 왜 고쳤나 — 원인은 규칙 문구가 아니라 예시였다

v1 의 few-shot 예시가 내놓는 anatomy 라벨을 현재(E1/E2/E3 이후) 온톨로지에
대조하면 **넷이 전부 표에 없다.**

| 예시 | 라벨 | 무엇을 가르쳤나 |
|---|---|---|
| `multi_location`·`temporal` | `right_upper_lobe` `right_lower_lobe` | 편측성을 라벨에 굽는 법 (P1a) |
| `device` | `left_subclavian_region` | 〃 |
| `inference` | `right_infrahilar_region` | 〃 |
| `device` | `tip_in_distal_svc` (descriptor) | 기구 위치를 descriptor 로 내는 법 (P1b) |
| `device` | `distal_svc` (anatomy) | 구조와 구간을 한 라벨에 붙이는 법 (E2 가 step 2 에서 분리한다) |
| `normal` | `clear_lungs` (entity) | 정상성을 라벨에 굽는 법 (P1c) |

예시를 step 2 에 통과시켜 보면 여섯은 `normalize.py` 가 되돌린다
(`right_upper_lobe` → `upper_lobe` + laterality). 즉 **모델에게 틀린 것을
가르치고 111만 번 되돌리고 있었다.** 되돌아오지 않는 둘이 더 나쁘다:

* `tip_in_distal_svc` — v1 예시는 tip 을 anatomy 와 descriptor **양쪽에**
  넣어 두었고 모델은 더 쉬운 descriptor 쪽만 배웠다. device 명제의
  `tip_location` 사용률이 32.0% 에 머무는 이유다.
* `distal_svc` — E2(혈관 구간 zone)가 `vocabulary.py` 에 선언만 되어 있고
  `normalize.py` 에 구현이 없었다. **2026-09-14 에 구현됐다** — step 2 가
  `distal_svc` 를 `svc` + zone `distal` 로 나눈다.

v2 의 예시 10개는 전부 **step 2 고정점**이다 (통과시켜도 라벨이 안 바뀐다).

### 2. rule 2 와 rule 3 이 서로 모순이었다

`entity_text_not_in_utterance` 3,755건의 실물은 대부분 **등위 분배**다.

```
"…for aortic, mitral, and tricuspid valve repair."   entity.text 'aortic valve repair' 가 원문에 없다
"No enteric or endotracheal tubes visualized."       entity.text 'enteric tubes' 가 원문에 없다
```

모델은 rule 2 가 시킨 대로 나눴는데 rule 3 이 그것을 하드 에러로 만든다.
**모델 결함이 아니라 명세 결함이다.** v2 rule 3 은 `text`(가리킬 수 있는 연속
구간)와 `label`(완성된 개념)을 갈라 스키마 변경 없이 해소한다.

### 3. 바뀐 규칙

| 규칙 | 근거 (실측) | 바꾼 것 |
|---|---|---|
| 2 | `no_propositions` 29,252 (2.58%) | 언제 zero 가 맞는지의 판정 기준 — 해부·소견을 이름으로 부르면 명제가 나와야 한다 |
| 3 | `entity_text_not_in_utterance` 3,755 | text/label 분리 (위 §2) |
| 4 | `section_conflict` 15,329 | 경고 문구를 지정 |
| 7 | `tip_location` 사용률 32.0% | 기구 끝은 anatomy, `tip_*` descriptor 금지, 거리는 measurement 로 분리 |
| 11 | `qualified_negation_unwarned` 25,004 | 경고를 내라고 **명시**하고 `"Qualified negation:"` 문구를 지정 (validate.py 가 그 문구를 본다) |
| 14 | P1c | 정상성은 라벨이 아니라 descriptor 축 |
| **16** (신설) | P1a 42,077 | anatomy 라벨은 구조만. side 는 `laterality` 필드 |
| **17** (신설) | 라벨 측정치 유입 13,690 / 단복수 분열 55,138 | snake_case·단수·숫자 없음 |

예시 둘을 더했다 — `blanket`(rule 2) 와 `coordination`(rule 3). 둘 다 v1 에
대응 예시가 없어 모델이 배울 데가 없던 유형이다.

### 4. 결과 — `ab/`

층화 표본 64문장(8층 × 8), v1/v2 를 한 문장씩 번갈아, 온톨로지·정규화기·검증기
동일. 128 호출 / 67분 (zeus-02, Qwen3.8-27B Q8_K_XL).

```bash
python3 ab/build_sample.py        # 표본 (결정적, seed 20260907)
python3 ab/run_ab.py              # 두 팔 실행. 중단하면 이어서 돈다
python3 ab/score_ab.py            # 채점
python3 ab/show_ab.py S3          # 한 층을 나란히 눈으로
```

| | v1 | v2 | |
|---|---|---|---|
| error 가 있는 레코드 | 7.8% | **1.6%** | ↓ |
| `entity_text_not_in_utterance` | 4 | **0** | ↓ |
| anatomy 라벨에 편측 접두 | 38.0% | **5.7%** | ↓ |
| anatomy 라벨이 구조 아닌 side | 8.0% | **0.0%** | ↓ |
| descriptor 가 기구 위치 | 20.9% | **0.0%** | ↓ |
| `qualified_negation_unwarned` | 6 | 4 | ↓ |
| 명제 0개인 레코드 | 4.7% | 3.1% | ↓ |
| **step 2 가 라벨을 고친 횟수** | 53 | **25** | ↓ |
| S8 대조군 (깨끗한 문장) finding | 0 | **0** | 퇴행 없음 |

마지막 두 줄이 중요하다. step2 churn 이 절반으로 준 것은 **프롬프트가 온톨로지와
같은 말을 하기 시작했다**는 뜻이고, S8 이 0 인 것은 이미 잘 되던 문장을
망가뜨리지 않았다는 뜻이다.

`ab/show_ab.py S3` 이 보여주는 전형:

```
"Endotracheal tube sits 4 cm above the carina."
  v1  anat above_carina[tip_location]   desc device_position=tip_4cm_above_carina
  v2  anat carina[tip_location]         desc measurement=4_cm

"Right PICC tip terminates in the mid/lower SVC, unchanged."
  v1  anat right[insertion_site] ; mid_lower_svc[zone=middle/tip_location]
  v2  anat None[right/insertion_site] ; svc[zone=mid/tip_location]
```

두 번째가 특히 볼 만하다 — **당시 `normalize.py` 에 E2 구현이 없었는데도
프롬프트만으로 `svc` + `zone=mid` 가 나왔다.** 표를 고치는 대신 애초에 그렇게
내게 한 것이다. (step 2 쪽 E2 는 2026-09-14 에 따라붙었다 -- 이제 옛 데이터도
같은 모양으로 정규화된다.)

### 5. 남은 것

| | 무엇 | 왜 |
|---|---|---|
| 1 | **전량 재추출을 안 했다** | 111만 문장 × 30초 = 이 기기로 불가. 표본 64는 방향을 보는 것이지 최종 수치가 아니다 |
| 2 | ~~E2 가 `normalize.py` 에 없다~~ | ✅ **2026-09-14 구현.** step 2 가 `mid_svc` 를 `svc` + zone `mid` 로 나누고, 기구 끝 descriptor 를 anatomy 로 옮긴다 |
| 3 | `qualified_negation_unwarned` 가 4건 남는다 | 문구를 지정해도 안 내는 경우가 있다. 예시를 하나 더 넣을지 판단 필요 |
| 4 | **양자화 델타 미측정** | 이 기기는 8bit 프로토타입이다. 여기서 잰 개선이 프로덕션(full precision)으로 전이된다는 보장이 없다 |

4번이 가장 크다. 이 실험은 "v2 가 v1 보다 낫다"를 이 기기 안에서 보인 것이고,
프로덕션으로 전이되는지는 별개 문제다.

#### v2.1 — `sided` 는 프롬프트 결함이 아니었다

라벨에 남던 `sided` 는 step 2 결함이었다. v2 는 rule 16 을 지켜 `label=null` 을
냈는데 `normalize.py` 가 `label or text` 로 메우고, `"Right-sided"` 에서 side 를
떼니 `sided` 가 남았다. **null 은 빠뜨린 것이 아니라 "이 발화는 구조를 부르지
않는다"는 진술이므로 메우면 안 된다.** `SIDE_LEFTOVERS` 로 좁게 고쳤고 기존
jsonl 고정점은 그대로다 (17,215 레코드 재정규화 변경 0건).

v1 데이터에는 0건이라 어떤 검사도 이것을 보지 못했다 — v1 은 애초에
`right_sided` 를 라벨로 냈고 null 을 준 적이 없다. **rule 16 이 잠복해 있던
step 2 버그를 드러낸 것이다.**

v2 대 v2.1(64문장)은 side 번짐 표적이 고쳐지고 S7 편측 라벨이 1 → 0 이 되었으나
rule 3 이 한 건 깨졌다. **1건 고치고 1건 깼으므로 n=64 로는 판정이 안 난다.**

> #### ⚠️ 2026-09-14 정정 — 이 문서의 "v2" 수치는 지금 코드가 아니다
>
> **이 정정을 쓸 당시 `Prompt2/system.py` 는 위의 v2.1 상태였다** (RULES 본문이
> v2.1 커밋 `1f9f47c` 와 바이트 단위로 같았다). 따라서 §4 표의
> "v2 = error 1.6%" 는 **그 코드로 재현되지 않는다** — 돌리면 3.1% 가 나온다.
> 위에서 "판정이 안 난다"고 미뤄 둔 그 깨진 rule 3 한 건이 남아 있기 때문이다.
>
> **지금은 v2.1 도 아니다.** `Prompt3/` 를 이 패키지로 합치면서 `system.py` 는
> v3.4 본문이 되었다. v2·v2.1 본문은 git 히스토리에만 있다.
>
> 그 한 건의 정체와 이후 전말(v3.0 ~ v3.4)은 이 문서 위쪽
> [지금 지시서 (v3.4) — 경과와 근거](#지금-지시서-v34--경과와-근거) 에 있다.
> 결론만 적으면: 표 버그 둘(`BILATERAL_COLLECTIVE` 왕복 누락, `SIDED_MIDLINE`
> 예외 누락)을 고치고 rule 2 에 패치 하나를 더한 **v3.4 가 현재 최선이고
> 64문장 error 0/64** 다. 새로 뽑을 때는 `REPORTCXR_PROMPT=Prompt2` 를 쓴다.
