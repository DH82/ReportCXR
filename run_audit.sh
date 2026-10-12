#!/usr/bin/env bash
# 구조화 결과를 검증하고, 사람이 읽을 문서까지 한 번에 낸다.
#
#     ./run_audit.sh                 # 기본: 모델 호출 없이 갈 수 있는 데까지
#     ./run_audit.sh --with-gpt      # GPT 감사까지 (OPENAI_API_KEY 필요)
#     ./run_audit.sh --arm Prompt2   # 다른 팔을 대상으로
#
# 단계마다 "이 단계가 무엇을 말해줄 수 있는가" 가 다르다. 순서는 싸고 확실한
# 것부터다 -- 기계가 답할 수 있는 것을 모델에게 묻지 않기 위해서.
#
# 2026-09-16 수정: out/gpt_records/ 가 arm 별로 안 나뉘어 있어, 다른 arm 을
# --rebuild 하면 예전 arm 의 캐시(samples.jsonl)를 조용히 재사용했다.
# GPT/*.py 는 이제 out/gpt_records/<arm>/ 밑에 쓰고, Verify/run.py 도 --arm
# 을 받는다.
set -euo pipefail
cd "$(dirname "$0")"

ARM=Prompt
SPLIT=test_reviewed
WITH_GPT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --arm)   ARM="$2"; shift 2 ;;
    --split) SPLIT="$2"; shift 2 ;;
    --with-gpt) WITH_GPT=1; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "모르는 인자: $1" >&2; exit 2 ;;
  esac
done

SRC="jsonl/$ARM/$SPLIT.jsonl"
[ -f "$SRC" ] || { echo "없음: $SRC" >&2; exit 1; }
GPT_OUT="out/gpt_records/$ARM"
step() { printf '\n\033[1m[%s]\033[0m %s\n' "$1" "$2"; }

step 1/5 "기계 검증 — 규칙으로 결정되는 것 (모델 호출 없음)"
python3 GPT/precheck.py --arm "$ARM" --split "$SPLIT"

step 2/5 "17개 지표 — 어휘·필드·규칙 일관성 (모델 호출 없음)"
python3 Verify/run.py --arm "$ARM" || echo "  (Verify 실패 — 계속 진행)"

if [ "$WITH_GPT" = 1 ]; then
  if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "  OPENAI_API_KEY 가 없습니다. --with-gpt 를 건너뜁니다." >&2
  else
    step 3/5 "GPT 감사 — 읽어야만 아는 것. 리포트당 3표본, 투표"
    python3 GPT/audit_records.py --records "$SRC"
  fi
else
  step 3/5 "GPT 감사 — 건너뜀 (--with-gpt 로 켜집니다)"
  if [ -f "$GPT_OUT/samples.jsonl" ]; then
    python3 GPT/audit_records.py --records "$SRC" --rebuild
  else
    echo "  $GPT_OUT/samples.jsonl 없음 — 이 arm 은 아직 GPT 감사를 돌린 "
    echo "  적이 없습니다. 2/4/5 단계의 '읽어야만 아는 것' 부분은 비어 "
    echo "  나옵니다. --with-gpt 로 다시 실행하십시오."
  fi
fi

step 4/5 "사례 문서 — 의사 검수용 A~E장"
python3 Verify/tools/defect_cases.py --arm "$ARM" --split "$SPLIT"

step 5/5 "종합 문서 — 확정 결함 하나로"
python3 Verify/tools/defect_report.py --arm "$ARM" --split "$SPLIT"

cat <<MSG

────────────────────────────────────────────────────────────
읽을 것은 이 하나입니다:

    docs/DEFECTS_FINAL_${ARM}_${SPLIT}.md

  1장  의사 판단이 필요한 것       2장  확정된 결함
  3장  근거와 신뢰도               4장  아직 못 쓰는 것
  5장  정정 이력

근거가 되는 파일 (모두 $ARM 전용):
    $GPT_OUT/precheck.md                     기계 검증
    $GPT_OUT/flagged.md                      GPT 가 지적한 것 (--with-gpt 필요)
    out/reports/$ARM/$SPLIT/INDEX.md         17개 지표
    docs/PROMPT_DEFECTS_${ARM}_${SPLIT}.md   사례 상세
────────────────────────────────────────────────────────────
MSG
