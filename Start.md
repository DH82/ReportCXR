# Start — 무엇을 치면 되는가

**하고 싶은 일을 목차에서 찾아서 그 부분만 보세요.** 처음부터 읽을 필요
없습니다.

| 하고 싶은 것 | 어디 |
|---|---|
| 문장 하나 넣어 보기 | §1 |
| 지금 데이터가 잘 돼 있는지 채점 | §2 |
| 지시서 두 개 비교하기 | §3 |
| 사전을 고쳤는데 데이터에 반영하기 | §4 |
| 데이터를 다른 지시서로 다시 뽑기 | §5 |
| 연구 계획의 관문 점수 재기 | §6 |

프로젝트가 뭔지는 [`README.md`](README.md), 기호가 뭔지는
[`Glossary.md`](Glossary.md) 를 보세요.

모든 명령은 저장소 루트(`/home/ldh/ReportCXR-Ko`)가 기준입니다.

---

## 0. 시작하기 전에 — 딱 두 가지

### (1) AI 서버가 필요한 일 / 필요 없는 일

**중요: AI 서버 없이 할 수 있는 일이 아주 많습니다.** 사전을 고쳤을 때 AI를
다시 부를 필요가 없습니다 — 사전만 다시 적용하면 됩니다(§4).

| 하려는 것 | AI 서버 | 걸리는 시간 |
|---|---|---|
| 사전·검사만 다시 돌리기 | **필요 없음** | 몇 초~몇 분 |
| 채점표 만들기 | **필요 없음** | 1분~몇 분 |
| 문장 하나 넣어 보기 | 필요 | 30초 |
| 지시서 비교 (64문장) | 필요 | 33분 |
| 데이터 한 덩이 다시 뽑기 (1,565문장) | 필요 | **13시간** |
| 전체 다시 뽑기 (110만 문장) | 필요 | **이 컴퓨터로는 불가** |

### (2) AI 서버 켜기 (필요한 일을 할 때만)

```bash
cd Serving
./run.sh -d                      # 백그라운드로 llama.cpp 서버 기동
curl -s localhost:8080/health    # 떴는지 확인
```

첫 로딩은 30GB 모델을 GPU 4장에 나눠 올리므로 수 분 걸립니다. 빌드부터
해야 한다면 [`Serving/README.md`](Serving/README.md) 를 보십시오.

```bash
cd Pipeline && python3 parse_utterances.py --check   # 서버 + tool calling 확인
```

---

## 1. 문장 하나 넣어 보기 — 가장 먼저 해 볼 것

```bash
cd Pipeline

# 현재 최선 프롬프트(v3.4)로
REPORTCXR_PROMPT=Prompt2 python3 parse_utterances.py \
    --text "Bilateral pleural effusions, left greater than right." --section Pleura
```

`REPORTCXR_PROMPT` 가 **어느 지시서를 쓸지**를 정합니다. 안 쓰면 옛날 지시서
(v1)가 기본값입니다 — 옛날 그대로 둔 것뿐이니, **새로 뽑을 때는 반드시
`Prompt2` 를 적어 주세요.**

| 값 | 무엇 |
|---|---|
| `Prompt` (기본값) | 첫 지시서. 비교용으로만 씀 |
| `Prompt2` | **지금 쓰는 지시서(v3.4) + 사전** |

> 예전에는 v3 지시서가 `Prompt3/` 에 따로 있었습니다. **`Prompt2/` 로
> 합쳤으므로 `REPORTCXR_PROMPT=Prompt3` 는 이제 동작하지 않습니다.**
> 합치면서 데이터 쪽 팔 이름도 따라 바뀌었습니다: `jsonl/Prompt3/` →
> **`jsonl/Prompt2/`**. 내용은 그대로입니다 (v3.4 로 뽑은 `test_reviewed`
> 233 study).

AI 서버 없이 사전·검사만 확인하려면:

```bash
python3 parse_utterances.py --selftest       # 사전·검사만 (AI 서버 불필요)
python3 parse_utterances.py --dry-run --limit 5   # 무엇이 나갈지만
python3 parse_utterances.py --dump-prompt OUT.md   # 실제로 나가는 프롬프트 전문
```

---

## 2. 지금 데이터가 잘 돼 있는지 채점하기 (AI 서버 불필요)

이미 만들어 둔 데이터가 제대로 됐는지를 **12가지 관점**으로 채점합니다.
채점만 하고 데이터는 건드리지 않습니다.

```bash
cd Verify

python3 run.py --list                 # 섹션 목록부터
python3 run.py                        # 전체 섹션, train 제외 (~1분)
python3 run.py -s S -s R              # 섹션 골라서 (S=구조, R=규칙검증)
python3 run.py --all -o ../out/reports/report.md   # train 포함 (수 분)
python3 run.py --arm Prompt2          # 다른 팔의 데이터를 검증
```

리포트 첫머리에 **표 세 개**가 찍힙니다:

```
| ontology        | ANATOMY | ... | content_hash     |   ← 어떤 표로 계산했나
| normalizer code | sha256  |                          ← 어떤 코드가 만들었나
| split           | sha256  | records |                 ← 어떤 데이터 파일인가
```

**이 세 표가 다르면 두 리포트는 비교 대상이 아닙니다.** 그래서 리포트를 남길
때는 이 머리 부분을 같이 남겨야 합니다.

---

## 3. 지시서 두 개 비교하기 (A/B 시험)

**같은 64문장**을 두 지시서에 각각 넣어 보고 어느 쪽이 나은지 보는 시험입니다.
한 번에 **33분**쯤 걸립니다.

64문장은 아무거나 고른 게 아니라, **결함 유형별로 8가지 × 8문장**씩 고른
것입니다. 그래야 고치려는 문제가 실제로 표본에 들어 있습니다.

```bash
# (필요할 때만) 표본 다시 만들기 — seed 고정이라 결과가 같습니다
python3 Prompt2/ab/build_sample.py

# 1) 실행 — 한 번에 한 팔씩. 중단해도 이어서 돕니다
cd Prompt2/ab
python3 run_ab.py v3.4

# 2) 채점 전 필수 — 모든 팔을 같은 step 2·3 으로 맞춥니다
python3 renorm.py

# 3) 채점
python3 score_ab.py v2.1 v3.4         # 왼쪽이 기준, 오른쪽이 비교 대상
python3 show_ab.py S4                 # 한 층을 눈으로 나란히
```

> **중요.** `run_ab.py` 의 팔 이름(`v3.4` 등)은 **그 시점의
> `Prompt2/system.py` 내용**으로 실행됩니다. 파일을 고치고 같은 이름으로 다시
> 돌리면 이전 결과와 뒤섞입니다. 프롬프트를 고쳤으면 **새 이름**을 쓰십시오
> (`run_ab.py` 의 `ARMS` 에 한 줄 추가).

새 프롬프트 버전을 만드는 절차는 이렇습니다:

1. `Prompt2/system.py` 의 `SYSTEM_PROMPT` 본문을 직접 고친다
2. `Prompt2/ab/run_ab.py` 의 `ARMS` 에 새 팔 이름 등록 (옛 팔은 `RETIRED` 로)
3. 위 1)~3) 실행
4. 결과를 `Prompt2/README.md` 에 **예측과 함께** 기록

---

## 4. 사전을 고쳤다 — 데이터에 반영하기 (AI 서버 불필요)

`Prompt2/ontology.py`(사전)를 고쳤다면 **AI를 다시 부를 필요가 없습니다.**
사전만 데이터에 다시 씌우면 됩니다.

```bash
# A/B 산출물에 반영 (저장된 step 1 원본에서 step 2·3 만 다시)
cd Prompt2/ab && python3 renorm.py

# jsonl/ 전체에 반영
cd Pipeline
python3 renormalize.py --dry-run      # 무엇이 바뀔지만 먼저
python3 renormalize.py                # 실제 적용
```

`renormalize.py` 에는 안전장치 다섯이 걸려 있고 하나라도 실패하면 쓰지
않습니다 — 백업 확인 · 정규화기 drift 확인 · 스키마 보존 · 지표 보존 ·
원자적 쓰기.

표를 고친 뒤에는 **4개 split 전수로 회귀를 확인**하는 것이 이 저장소의 관례입니다:

```bash
cd /home/ldh/ReportCXR-Ko && python3 -c "
import json
from Pipeline.validate import validate_record
from collections import Counter
for split in ['validate','test','test_reviewed']:
    c=Counter(); n=0
    for line in open(f'jsonl/Prompt/{split}.jsonl'):
        for rec in json.loads(line).get('records') or []:
            n+=1
            for f in validate_record(rec)['findings']: c[f['code']]+=1
    print(split, n, dict(c))
"
```

---

## 5. 데이터를 다른 지시서로 다시 뽑기

```bash
cd Pipeline
python3 extract_split.py --split test_reviewed --arm Prompt2 --limit 1   # 먼저 한 study 만
python3 extract_split.py --split test_reviewed --arm Prompt2             # 전량 (~13시간)
```

- 입력은 언제나 `jsonl/Prompt/<split>.jsonl` 의 **발화**이고, 바뀌는 것은
  프롬프트뿐입니다 (표·정규화기·검증기는 팔마다 같습니다).
- **이어서 돕니다.** 이미 끝난 study 는 건너뛰므로 13시간짜리 실행이 끊겨도
  다시 실행하면 그 자리에서 계속됩니다.
- 오래 걸리므로 반드시 백그라운드로:

```bash
cd Pipeline
nohup python3 extract_split.py --split test_reviewed --arm Prompt2 \
      > /tmp/extract_test_reviewed.log 2>&1 &
tail -f /tmp/extract_test_reviewed.log     # 진행 상황
```

다 뽑고 나면 그 팔을 검증합니다:

```bash
cd Verify && python3 run.py --arm Prompt2 -o ../out/reports/prompt2_test_reviewed.md
```

---

## 6. 연구 계획의 관문 점수 재기 (AI 서버 불필요)

C1(multiplicity 축이 설 수 있는가) · C2(대조 pair 가 충분한가) 를 잽니다.
자세한 배경과 현재 판정은 [`README.md`](README.md) §1.

```bash
cd Verify/tools
python3 phase0_metrics.py                 # 작은 split (수 초)
python3 phase0_metrics.py --all           # train 포함 전량 (~1.5분)
python3 phase0_metrics.py --arm Prompt2   # 다른 팔로
```

출력은 C1 비율, 축별 pair 수율, study당 proposition 분포, entity·anatomy
조합 빈도입니다. 기준선(15% / 1,000)과의 대조 판정이 같이 찍힙니다.

---

## 7. RadLex 대조 (서버 불필요)

우리 라벨이 RadLex 개념인지(방향 A), RadLex 에 있는데 한 번도 안 뽑은 개념이
있는지(방향 B)를 봅니다.

```bash
python3 Pipeline/radlex_import.py --owl RadLex/RadLex.owl    # OWL → TSV (최초 1회)
python3 Pipeline/radlex_match.py --split test                # 방향 A
python3 Pipeline/radlex_blindspot.py --split test --split validate   # 방향 B
```

`RadLex/*.owl`(83MB)은 추적하지 않습니다. RSNA 에서 받아야 합니다.
결과 해석은 [`RadLex/README.md`](RadLex/README.md).

---

## 8. "지금 가장 좋은 상태" 그대로 해 보기

```bash
# 1) 서버
cd Serving && ./run.sh -d

# 2) 현재 최선 프롬프트로 한 문장
cd ../Pipeline
REPORTCXR_PROMPT=Prompt2 python3 parse_utterances.py \
    --text "Right PICC tip terminates in the mid SVC." --section Tubes

# 3) 현재 최선 조합의 A/B 근거 확인 (서버 불필요)
cd ../Prompt2/ab && python3 renorm.py && python3 score_ab.py v2.1 v3.4

# 4) 현재 데이터 상태 감사 (서버 불필요)
cd ../../Verify && python3 run.py
```

---

## 자주 막히는 곳

| 증상 | 원인과 대응 |
|---|---|
| `server NOT READY` | 서버가 안 떠 있음. `cd Serving && ./run.sh -d`, 로딩에 수 분 |
| 결과가 예전과 다르다 | 표가 바뀌었을 수 있음. 리포트 머리의 `content_hash` 비교 |
| A/B 점수가 이상하다 | `renorm.py` 를 안 돌렸을 가능성. 채점 전 필수입니다 |
| `unknown arm: vX` | `Prompt2/ab/run_ab.py` 의 `ARMS` 에 등록해야 합니다 |
| 어느 프롬프트로 뽑혔는지 모르겠다 | `jsonl/<arm>/` 의 디렉터리 이름이 곧 팔 이름입니다 |
| 13시간 실행이 끊겼다 | 그냥 같은 명령을 다시 실행하면 이어서 돕니다 |
| 옛 문서의 수치가 안 맞는다 | [`PROVENANCE.md`](PROVENANCE.md) 의 정정 기록을 먼저 확인 |

---

## 무엇을 고치면 무엇이 깨지는가

| 고치는 것 | 다시 돌려야 하는 것 | LLM 필요? |
|---|---|---|
| `Prompt2/ontology.py` (표) | `renorm.py` + `renormalize.py` + 검증 | ❌ |
| `Pipeline/normalize.py` (step 2) | 〃 | ❌ |
| `Pipeline/validate.py` (step 3) | 검증만 | ❌ |
| `Prompt*/system.py` (프롬프트) | **재추출** (A/B 또는 split 전량) | ✅ |
| `Verify/metrics/*` | 리포트만 | ❌ |

**프롬프트를 고치면 반드시 재추출이 필요하고, 그것만이 비쌉니다.** 나머지는
전부 무료이고 결정적입니다 — 이 비대칭이 이 저장소의 설계 전체를 설명합니다.
