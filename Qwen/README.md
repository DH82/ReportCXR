# Qwen3.8-27B GGUF — 로컬 서빙 (llama.cpp / CUDA)

`maplez_struct.py` · `SRRG.py`가 쓰는 OpenAI 호환 엔드포인트를 로컬 GPU에서 띄우기 위한
docker 환경. `llama-server`가 `/v1/chat/completions`를 제공하고, `--jinja`로 tool calling
(강제 function calling) 경로를 활성화한다.

## 이 호스트의 조건

| 항목 | 값 | 의미 |
|---|---|---|
| GPU | GTX 1080 Ti × 4 (11GB) | Pascal `sm_61`, VRAM 합계 44GB |
| 드라이버 | 535.183.01 (CUDA 12.2) | 베이스 이미지를 12.2.2로 고정 |
| 모델 | `Qwen3.8-27B-UD-Q8_K_XL.gguf`, 30GB | **한 장에 안 들어감 → 4장 분할 필수** |
| 아키텍처 | `qwen35`, 65 blocks, SSM+attention 하이브리드 | 최신 llama.cpp 빌드가 필요 |

fp16 연산이 1080 Ti에서 fp32의 1/64 속도라 `GGML_CUDA_F16=OFF` + `GGML_CUDA_FORCE_MMQ=ON`
(정수 dp4a 커널)으로 빌드한다.

## 1. 빌드

```bash
docker build -t reportcxr/llamacpp:cu122 /home/ldh/ReportCXR/Qwen
```

CUDA 커널 컴파일이라 10~20분 걸린다.

기본값 `master`는 빌드하는 시점마다 다른 커밋을 가져온다. 아래는 이 호스트에서
빌드·검증이 끝난 커밋으로, 재현이 필요하면 이걸 그대로 쓰면 된다:

```bash
docker build --build-arg LLAMA_CPP_REF=5d5cb4c3a4ea8769490d39a275ee49a45184774d \
             -t reportcxr/llamacpp:cu122 /home/ldh/ReportCXR/Qwen
```

현재 이미지가 어느 커밋으로 빌드됐는지는 이미지 안에 남아 있다:

```bash
docker run --rm --entrypoint cat reportcxr/llamacpp:cu122 /opt/llama.cpp/COMMIT
```

## 2. 실행

```bash
cd /home/ldh/ReportCXR/Qwen
./run.sh            # 포그라운드
./run.sh -d         # 백그라운드
```

또는 직접:

```bash
GGUF=$(realpath ~/.cache/huggingface/hub/models--unsloth--Qwen3.8-27B-GGUF/snapshots/*/Qwen3.8-27B-UD-Q8_K_XL.gguf)
docker run --rm --gpus all -p 8080:8080 -v "$GGUF:/models/model.gguf:ro" reportcxr/llamacpp:cu122
```

첫 로딩은 30GB를 4장에 올리므로 수 분 걸린다. `nvidia-smi`로 카드당 ~8GB가 차는지 확인.

## 3. 동작 확인

```bash
curl -s localhost:8080/health
curl -s localhost:8080/v1/models | python3 -m json.tool

# tool calling (파이프라인이 실제로 쓰는 경로)
curl -s localhost:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "qwen3.8-27b",
  "messages": [{"role":"user","content":"No pleural effusion."}],
  "tools": [{"type":"function","function":{"name":"emit","description":"emit finding",
    "parameters":{"type":"object","properties":{"entity":{"type":"string"},
    "presence":{"type":"string"}},"required":["entity","presence"]}}}],
  "tool_choice": {"type":"function","function":{"name":"emit"}}
}' | python3 -m json.tool
```

`tool_calls`가 채워져 나오면 파이프라인 연결 준비 완료.

## 4. 파이프라인 연결

`../SRRG_Qwen.py`가 이 서버를 기본값으로 물고 있다. 환경변수 설정 없이 바로:

```bash
cd /home/ldh/ReportCXR
python SRRG_Qwen.py --check     # 서버 상태 + tool calling 가능 여부만 확인
python SRRG_Qwen.py --row 0
```

원본 `SRRG.py`를 그대로 쓰려면 환경변수로 붙일 수도 있다(이쪽은 thinking이 켜진
채로 돌아가므로 훨씬 느리다):

```bash
export OPENAI_BASE_URL="http://localhost:8080/v1"
export OPENAI_API_KEY="sk-local"       # 서버가 검사하지 않지만 비면 즉시 종료함
export OPENAI_MODEL="qwen3.8-27b"
python SRRG.py --row 0
```

## 튜닝 / 문제 대응

| 증상 | 대응 |
|---|---|
| OOM (로딩 중) | `CTX=8192 ./run.sh`, 또는 `-ngl`을 낮춰 일부 레이어를 CPU로 |
| GPU별 VRAM이 다를 때 | `--tensor-split` 비율 조정 |
| 카드 일부만 쓰고 싶을 때 | `--gpus '"device=0,1"'` |
| 속도가 이상하게 느림 | `-fa off` (Pascal에서 flash-attn 커널이 불리할 수 있음) |
| 로딩 중 `unknown model architecture: qwen35` | llama.cpp가 오래됨 → `--no-cache`로 재빌드 |
| 호스트 RAM 압박 | `--no-mmap` 추가 |

## 범위 밖 메모

- 이 GGUF는 **텍스트 전용**이다. `../Qwen3.8-27B/`의 원본은 VL 모델(`Qwen3_5ForConditionalGeneration`,
  vision/video preprocessor 포함)이므로 영상 입력을 쓰려면 같은 repo의 `mmproj-*.gguf`를 받아
  `--mmproj`로 함께 붙여야 한다.
- 컨텍스트 상한은 262144지만 이 VRAM에서 전부 쓸 수는 없다. 32k에서 시작해 필요한 만큼 올릴 것.
