# out — 기계가 만든 파일들

> **한 줄 요약: 프로그램이 만들어 낸 결과물(채점표·실험 기록·로그)만 모아 두는
> 곳입니다.** 사람이 손으로 쓴 파일은 여기 두지 않습니다.
>
> **왜 나눠 두나요?** 손으로 쓴 것과 기계가 뱉은 것이 섞여 있으면, 고칠 게
> 생겼을 때 **어느 쪽을 고쳐야 하는지** 알 수 없게 됩니다. 기계가 뱉은 건
> 고쳐 봐야 다음에 또 덮어씌워집니다.
>
> **이 폴더는 git에 올라가지 않습니다** — 안에 환자 판독문 원문이 들어 있고,
> MIMIC 데이터는 재배포가 금지돼 있기 때문입니다. 직접 만드셔야 합니다
> (아래 표에 만드는 명령이 있습니다).

**코드가 쓰는 자리는 여기뿐이다.** 코드 디렉터리(`Prompt/` · `Prompt2/` ·
`Pipeline/` · `Verify/` · `Serving/`)에는 생성물을 두지 않는다. 손으로 쓴 것과
기계가 쓴 것이 같은 폴더에 있으면 무엇을 고쳐야 하는지가 흐려진다.

**이 디렉터리는 이 README 말고는 git 이 추적하지 않는다.** 리포트와 A/B 산출물에
MIMIC-CXR · CheXpert 판독문 원문이 그대로 들어 있고, MIMIC 은 PhysioNet 자격
인증 데이터라 재배포할 수 없다. 아래 파일들은 로컬에서 직접 만들어야 한다.

| | 무엇 | 만드는 것 |
|---|---|---|
| `reports/` | 검증 리포트 (.md) | `Verify/run.py -o ../out/reports/<이름>.md` |
| `lexicon/` | 단어장 `lexicon.tsv` | `Verify/tools/lexicon.py --all` |
| `ab/` | A/B 원본 `out.jsonl` · API 호출 로그 · 실행 로그 | `Prompt2/ab/run_ab.py` |

예외가 하나 있다. `Prompt2/ab/sample.jsonl` 은 생성물이 아니라 **시험 문제지**다 —
`build_sample.py` 가 seed 20260907 로 결정적으로 뽑은 고정 입력이므로 실험 코드
옆에 둔다.

`Pipeline/parse_utterances.py` 의 산출물은 `--out` 이 정하며 기본값은 실행 위치의
`./out_parse` 다 (추적하지 않는다).

---

## 리포트를 읽기 전에

모든 리포트 첫머리에 `Prompt2/ontology.py` 의 표 크기가 지문으로 찍힌다.
**지문이 다른 두 리포트는 비교 대상이 아니다** — 다른 온톨로지로 계산한 지표를
맞대면 두 테이블의 차이를 데이터 품질로 보고하게 된다. 루트
[`PROVENANCE.md`](../PROVENANCE.md) 참조.

현재 파일:

```
reports/Prompt/all/                      ★ 최신 감사 결과. 여기부터 볼 것
    INDEX.md                             한 화면 요약 — 묶음 6개 / 요소 17개
    g1_integrity.md … g6_overspec.md     주제별 상세 (① 뜻 ② 현재 데이터)
reports/archive/                         다시 만들 수 없는 옛 리포트. archive/README.md 참조
normalization/<arm>_<split>_notes.json   step 2 가 무엇을 바꿨나 — 실행 이력 (지표 1-E 가 읽는다)
normalization/batch1_pre_renormalize_conflicts.json
                                         2026-09-15, 표가 덮어쓰기 직전에 뜬 모델의 원래 답 64건
lexicon/lexicon.tsv                      등급 A/B/C/D 판정이 붙은 단어장 (4 split 전량)
ab/out.jsonl                             전 팔의 레코드 (step 1 원본 포함)
                                         v1 · v2 · v2.1 · v3 · v3.1 · v3.2 · v3.2b · v3.3 · v3.4
ab/logs/api_calls_ab.{log,jsonl}         호출 로그
ab/run_v*.log                            팔별 실행 로그
extract/<arm>/<split>/                   extract_split.py 의 호출 로그
```

**`reports/Prompt/all/` 은 언제든 다시 만들 수 있다** (`cd Verify && python3
run.py --all`, 약 10분). 반면 **`reports/archive/` 는 다시 만들 수 없다** —
그때의 데이터나 온톨로지가 남아 있지 않다. 지우기 전에
[`reports/archive/README.md`](reports/archive/README.md) 를 읽을 것.

**`normalization/` 은 지우면 안 된다.** step 2 는 자기가 고친 흔적을 레코드에
남기지 않는다(남기면 지표 S 가 감사 필드 유출로 잡는다). 그래서 "표가 모델을
몇 번 고쳤나"는 **이 파일에만** 있고, 지우면 지표 1-E 가 `BLIND` 로 돌아간다.

**이 파일은 실행 이력을 쌓는다(최근 20회).** 마지막 실행만 남기면 안 되기
때문이다 — **고정점에 도달한 파일은 다시 돌려도 아무것도 안 바뀌므로**, 나중에
돌린 작은 실행이 큰 실행의 기록을 0 으로 덮어쓴다. 실제로 2026-09-15 에
2,135건이 그렇게 사라져 로그에서 복원했다.

**팔 이름은 그 시점의 프롬프트 파일 내용을 가리킨다.** `run_ab.py` 의 `ARMS` 는
`v3`~`v3.4` 를 전부 같은 `SYSTEM_PROMPT` 에 연결해 두었고, 실제로 무엇이
나갔는지는 **그때 파일이 어떤 상태였는가**로 정해진다. 그래서 프롬프트를
고쳤으면 반드시 **새 이름**으로 돌려야 하고, 같은 이름으로 다시 돌리면 이전
결과와 뒤섞인다.

`Prompt3/` 를 `Prompt2/` 로 합친 뒤로는 그 함정이 줄었다 — `run_ab.py` 가
돌릴 수 있는 팔은 `v1` 과 `v3.4` 뿐이고, 옛 팔 이름을 대면 에러로 막는다.
옛 팔의 행은 여기 `out.jsonl` 에 있으므로 채점에는 계속 쓰인다.
