#!/usr/bin/env python3
"""Which metrics are read together, and why.

MEASURING AND READING ARE DIFFERENT UNITS, and conflating them is what made
this report hard to use twice, in opposite directions.

One combined report hid everything: to reach the metric you cared about you
scrolled past eleven you did not, and a `git diff` said "the report changed"
and nothing more. Splitting it gave seventeen files, and seventeen is a
directory you navigate rather than a result you read.

So the split stays where it earns its keep and the join happens one level up:

  A METRIC is a unit of MEASUREMENT. It has exactly one verdict, because a
  verdict that covers two questions answering differently -- 1-B WARN and 1-C
  INFO -- is neither of them. Keeping them apart is what lets the index say
  which half is failing.

  A GROUP is a unit of READING. It is one theme, one file, and its verdict is
  the worst verdict among its members, so nothing a member found can be hidden
  by an average. Every member keeps its own verdict inside the file.

The grouping below is by WHAT A FIX WOULD TOUCH, not by how the numbers look.
Everything in `vocabulary` is fixed by editing tables in `Prompt2/ontology.py`;
everything in `grounding` is fixed in the prompt, because no table can make a
model quote a sentence it did not read. Two metrics that both say WARN but send
you to different files do not belong in one group.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple


class Group(NamedTuple):
    key: str          # filename stem: g1_integrity.md
    title: str        # heading
    members: List[str]   # metric SECTION symbols, in reading order
    blurb: str        # why these are one file


GROUPS: List[Group] = [
    Group(
        key="g1_integrity",
        title="배관 — 파일과 파이프라인이 온전한가",
        members=["S", "C", "0"],
        blurb='''
## 한 줄로

**파일이 멀쩡한지, 원본 문장을 하나도 잃지 않았는지 확인한다.**

## 왜 이걸 먼저 하나

판독문을 JSON 으로 바꾸는 작업은 여러 단계를 거친다. 그 과정에서 **파일이 깨지거나
문장이 몇 개 사라지는 일**이 생길 수 있는데, 그러면 뒤에 나오는 모든 숫자가
"엉뚱한 파일에 대한 숫자"가 되어 버린다.

책 1,000 쪽을 베껴 쓴 다음, 내용이 맞는지 따지기 전에 **쪽수가 1,000 쪽이 맞는지
부터** 세어 보는 것과 같다. 990 쪽밖에 없으면 내용 검사는 의미가 없다.

## 세 가지를 본다

| 기호 | 묻는 것 | 비유 |
|---|---|---|
| **S** | 파일이 찢어지거나 잘리지 않았나 | 공책이 멀쩡한가 |
| **C** | 원본 문장이 글자 그대로 다 있나 | 베껴 쓰다 빠뜨린 줄이 없나 |
| **0** | 정리 규칙을 한 번 더 돌려도 안 바뀌나 | 맞춤법 검사를 두 번 돌려도 같은 결과인가 |

## 읽는 법

**셋 다 `PASS` 여야 정상이고, 중간이 없다.** 파일이 "조금 깨진" 상태나 문장을
"조금 잃은" 상태는 있을 수 없기 때문에, 하나라도 0 이 아니면 곧바로 `FAIL` 이다.

> **여기가 전부 통과해도 "내용이 옳다"는 뜻은 전혀 아니다.** 이 묶음은 그릇만
> 본다. 내용이 맞는지는 나머지 다섯 묶음이 묻는다.
''',
    ),
    Group(
        key="g2_vocabulary",
        title="어휘 — 온톨로지가 표면형을 제대로 접었나",
        members=["1-A", "1-B", "1-C", "1-D", "P2"],
        blurb='''
## 한 줄로

**판독문에 쓰인 말을 정해진 이름표로 바꿀 때, 그 바꾸기가 일관적인지 본다.**

## 무슨 말인가

판독문에는 같은 것을 여러 가지로 쓴다. "물이 찼다", "흉수", "pleural effusion" —
전부 같은 소견이다. 컴퓨터가 쓰려면 이걸 **하나의 이름표**로 모아야 한다.

    "pleural effusion"  ┐
    "effusion"          ├─→  pleural_effusion   (이름표)
    "layering fluid"    ┘

이 모으기를 **정규화**라고 하고, 무엇을 무엇으로 모을지 적어 둔 표를
**온톨로지**라고 한다. 이 묶음은 그 표가 제대로 작동했는지 다섯 각도에서 본다.

## 다섯 각도

| 기호 | 묻는 것 | 쉽게 |
|---|---|---|
| **1-A** | 표가 결정했나, 못 찾아 그냥 통과시켰나 | 사전을 찾아 고쳤나, 못 찾아 그대로 뒀나 |
| **1-B** | 같은 말이 **두 이름표로 갈렸나** | 같은 말인데 다르게 적었다 |
| **1-C** | 다른 말이 **한 이름표로 뭉개졌나** | 다른 말인데 같게 적었다 |
| **1-D** | 글자는 안 겹치는데 사실 같은 개념인 둘 | "흉수"와 "pleural effusion" 처럼 |
| **P2** | 단수·복수 때문에 갈린 이름표 | `contour` 와 `contours` |

**1-B 와 1-C 는 정반대의 실수다.** 하나는 뭉쳐야 할 걸 안 뭉쳤고, 하나는 뭉치면
안 되는 걸 뭉쳤다. **1-D 와 P2 도 짝이다** — 같은 결함을 반대편에서 찾는다.
P2 는 글자가 비슷한 것만(`contour`/`contours`), 1-D 는 글자가 전혀 안 겹치는
것만 찾으므로, **하나만으로는 절반을 놓친다.**

## 왜 다섯이 한 파일인가

**고칠 자리가 전부 같기 때문이다** — `Prompt2/ontology.py` 의 표다. 여기 나온
문제는 전부 그 파일을 고쳐서 해결된다.

## 읽을 때 조심할 것

> **1-A 만 점수처럼 생겼는데, 그게 함정이다.** 이 숫자는 표에 무의미한 줄
> (`"consolidation" → "consolidation"` 처럼 자기를 자기로 바꾸는 줄) 하나만
> 넣어도 수만 건이 "성공"으로 넘어간다. **목표로 삼으면 안 되고, 천장으로만
> 읽어야 한다.**
>
> **진짜 신호는 1-B 다.** 그것만이 사람의 판단 없이 **데이터가 스스로
> 모순된다**는 것을 보여 준다. 같은 말에 다른 이름표가 붙었으면, 어느 쪽이
> 맞든 다른 쪽은 틀린 것이기 때문이다.
''',
    ),
    Group(
        key="g3_fields",
        title="필드 — 라벨과 그 옆 칸이 서로 맞나",
        members=["1-E", "1-F"],
        blurb='''
## 한 줄로

**이름표와 그 옆 칸에 적힌 내용이 서로 안 맞는 곳을 찾는다.**

## 무슨 말인가

명제 하나는 이름표 하나로 끝나지 않는다. 옆에 칸이 여러 개 붙는다.

    이름표: pleural_effusion   (무슨 소견인가)
    방향  : left               (어느 쪽인가)
    정도  : small              (얼마나 심한가)

앞 묶음(어휘)이 **이름표끼리** 맞는지 봤다면, 이 묶음은 **이름표와 옆 칸 사이**가
맞는지 본다. 이름표가 `mediastinum`(가슴 한가운데 있는 부위)인데 방향 칸에
`right`(오른쪽)라고 적혀 있으면 앞뒤가 안 맞는 것이다.

## 두 가지를 본다

| 기호 | 묻는 것 | 쉽게 |
|---|---|---|
| **1-E** | 같은 단어가 항상 같은 칸에 들어가나 | `"mild"` 를 어떤 데선 '정도', 어떤 데선 '범위' 칸에 넣었나 |
| **1-F** | 이름표가 뜻하는 값과 칸의 값이 어긋나나 | 한가운데 부위에 "오른쪽"이라 적었나 |

## 읽을 때 조심할 것

> **"0 건"이 좋은 소식이 아닐 수 있다.** 두 검사 모두 **아는 것끼리만** 비교할
> 수 있다. 아는 게 적으면 어긋남도 못 찾고, 그 결과 0 이 나오는데 그건
> *"깨끗하다"* 가 아니라 ***"재지 않았다"*** 다. 그래서 `BLIND` 라는 판정이
> 따로 있다.
>
> **1-E 는 함정이 하나 더 있다.** 정리 규칙(step 2)이 표에 맞춰 칸을 **덮어쓴다.**
> 그래서 표가 아는 단어는 항상 표와 같아지고, 어긋남이 **구조적으로 0** 이 된다.
> 실제로 train 59만 건 중 0 이었다. 그래서 1-E 는 **표가 모르는 단어만으로**
> 판정한다 — 거기만 아무도 일치를 강제하지 않은 자리이기 때문이다.

## 여기서 답하지 않는 것

**"왜 어긋났는가"** 는 다루지 않는다. 그 진단은 마지막 묶음(과잉 특정)이 한다.
''',
    ),
    Group(
        key="g4_rules",
        title="규칙 — 명세를 어긴 곳",
        members=["R"],
        blurb='''
## 한 줄로

**정해 놓은 규칙 44개를 전체 데이터에 돌려서, 어긴 곳을 센다.**

## 무슨 말인가

이 프로젝트에는 "명제를 이렇게 만들어라"라는 규칙이 문서로 적혀 있다. 예를 들면
이런 것들이다.

- *rule 3* — 원문에 없는 말을 지어내지 마라
- *rule 9* — '크기'와 '정도'는 다른 칸이다. 섞지 마라
- *rule 11* — "큰 것은 없다"처럼 **조건이 붙은 부정**에는 경고를 달아라

다른 묶음들이 각자 하나의 성질을 재는 것과 달리, 이 묶음은 **적어 놓은 규칙을
그대로 집행한다.** 그래서 혼자 한 묶음이다.

## 두 등급이 있다

| 등급 | 뜻 |
|---|---|
| `error` | **그 상태로는 쓸 수 없다** |
| `warning` | **사람이 한 번 봐야 한다** (틀렸다는 뜻은 아니다) |

## 이 묶음의 진짜 쓸모

**규칙별 위반 표가 곧 "프롬프트를 어디부터 고칠까"의 우선순위다.** 실제로 프롬프트
v2 는 이 표의 상위 다섯 줄을 근거로 고쳐졌다.

## 읽을 때 알아 둘 것

> **한 번도 안 터진 검사들이 오히려 좋은 소식이다.** 안 터진 것은 거의 전부
> "칸에 정해진 값만 들어갔나", "번호가 겹치지 않나" 같은 **형식 검사**다. 즉
> **형식은 완벽하고, 남은 문제가 전부 판단의 문제**라는 증거다.

일부 검사는 다른 묶음과 일부러 겹친다. **두 검사가 각각 따로 같은 것을 짚으면
그건 중복이 아니라 교차 확인이다.**
''',
    ),
    Group(
        key="g5_grounding",
        title="근거 — JSON 이 원문을 실제로 읽었나",
        members=["G1", "G2", "P3"],
        blurb='''
## 한 줄로

**JSON 을 원문과 직접 맞대 본다. 지어내지 않았는지, 빠뜨리지 않았는지.**

## 왜 따로 있나

앞의 묶음들은 전부 *"정해진 이름표를 일관되게 썼나"* 를 묻는다. 그 검사들은
**모델이 문장을 실제로 읽었는지 아닌지를 볼 수 없다.** 지어낸 말도 똑같이
깨끗하게 이름표로 바뀌기 때문이다.

> 예시 — 원문: `"Status post sternotomy with mitral and aortic valve replacements."`
> (승모판과 대동맥판 치환술)
>
> JSON 은 `"mitral valve replacement"` 를 인용했다고 적었다. **원문에 그런
> 연속된 구절은 없다.** 모델이 "mitral ... valve replacements" 를 재조립해
> 만들어 낸 것이다. 그런데 이름표는 멀쩡하게 붙으므로 앞의 검사들은 전부
> 통과한다.

**이 묶음만이 그걸 잡는다.** 정답 데이터도, AI 를 다시 부르는 것도 필요 없다 —
그 문구가 문장 안에 있거나 없거나 둘 중 하나이기 때문이다.

## 세 방향

| 기호 | 방향 | 묻는 것 |
|---|---|---|
| **G1** | JSON → 원문 | 인용했다는 문구가 문장에 실제로 있나 (**지어냈나**) |
| **G2** | 양방향 | "없다/아마도"라고 적고 댄 근거 단어가 진짜 그런 뜻인가 |
| **P3** | 원문 → JSON | 문장이 말한 것 중 **빠뜨린** 게 있나 |

G1 은 *있는 게 틀렸나*, P3 은 *있어야 할 게 없나* 를 묻는다. **정반대 방향이고,
둘 다 필요하다.**

## 왜 이 묶음이 특별한가

**고칠 자리가 다르다.** 어휘 묶음의 문제는 표를 고치면 해결된다. 하지만
**여기 있는 문제는 어떤 표로도 해결되지 않는다** — 읽지 않은 문장을 인용하게
만들어 주는 표는 없기 때문이다. 고칠 자리는 **AI 에게 주는 지시문(프롬프트)** 이다.

> 이 묶음은 2026-09-15 에 새로 만들었다. 그 전까지 이 감사에 **아예 빠져 있던
> 질문**이다.
''',
    ),
    Group(
        key="g6_overspec",
        title="과잉 특정 — 라벨이 필드의 일을 대신함",
        members=["P1a", "P1b", "P1c"],
        blurb='''
## 한 줄로

**이름표에, 옆 칸에 적어야 할 것을 적어 넣은 경우를 센다.**

## 무슨 말인가

칸이 나뉘어 있는 데는 이유가 있다. 그런데 이름표 하나에 다 밀어 넣는 일이 생긴다.

    잘못: 이름표 = right_internal_jugular_vein   ("오른쪽" 이 이름표 안에)
          방향   = right                          ("오른쪽" 이 또 있다

    올바름: 이름표 = internal_jugular_vein
            방향   = right

**같은 사실이 두 군데 적히면 반드시 언젠가 어긋난다.** 한쪽만 고치는 일이
생기기 때문이다. 그리고 **어긋난 결과가 바로 앞 묶음(1-F)의 숫자**다. 즉
이 묶음은 **그 숫자의 원인 쪽**이다.

## 세 갈래

| 갈래 | 이름표에 잘못 들어간 것 | 가야 할 칸 | 상태 |
|---|---|---|---|
| **P1a** | 방향 (`right_internal_jugular_vein`) | `laterality` | ✅ 해결됨 |
| **P1b** | 기구 끝 위치 (`tip_in_mid_svc`) | `anatomy.role` + `zone` | ⏳ 진행 중 |
| **P1c** | 정상 여부 (`normal_heart_size`) | `descriptor` | ✅ 해결됨 |

## 좋은 소식

**세 갈래 모두 담을 칸이 이미 있다.** 새 칸을 만들 필요가 없고, 옮기기만 하면
된다.

## 왜 셋을 따로 세나

**진행 상태가 서로 다르기 때문이다.** P1a 와 P1c 는 고쳐서 내려갔고 P1b 는 아직
열려 있는데, **셋을 한 숫자로 합치면 그 차이가 사라진다.** 합친 숫자는 "뭔가
남아 있다"까지만 말하고 "무엇이 남았는지"는 말해 주지 못한다.
''',
    ),
]

GROUP_OF: Dict[str, Group] = {sym: g for g in GROUPS for sym in g.members}


def grouped(metrics):
    """[(Group, [metric, ...])] in declared order; ungrouped metrics last."""
    out, seen = [], set()
    by_symbol = {m.symbol: m for m in metrics}
    for g in GROUPS:
        members = [by_symbol[s] for s in g.members if s in by_symbol]
        if members:
            out.append((g, members))
            seen.update(m.symbol for m in members)
    orphans = [m for m in metrics if m.symbol not in seen]
    if orphans:
        out.append((Group("g9_other", "묶이지 않은 요소", [], ""), orphans))
    return out
