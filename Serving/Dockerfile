# =============================================================================
#  llama.cpp (CUDA) — Qwen3.8-27B GGUF local serving
#
#  Target host : zeus-02 / GTX 1080 Ti x4 (11GB each, Pascal sm_61)
#                driver 535.183.01 -> CUDA 12.2
#  Purpose     : OpenAI-compatible endpoint (/v1) for maplez_struct.py / SRRG.py
#                which drive the model with forced function calling, so the
#                server must run with --jinja (tool-call template support).
#
#  build:  docker build -t reportcxr/llamacpp:cu122 /home/ldh/ReportCXR/Qwen
#  run  :  see README.md / run.sh
# =============================================================================

ARG CUDA_VERSION=12.2.2
ARG UBUNTU_VERSION=22.04

# -----------------------------------------------------------------------------
#  Stage 1 — build llama.cpp with CUDA
# -----------------------------------------------------------------------------
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS builder

ARG DEBIAN_FRONTEND=noninteractive

# qwen35 (hybrid SSM + attention) is a recent architecture: pin to a commit or
# tag that is known to load it. "master" = whatever is newest at build time.
ARG LLAMA_CPP_REPO=https://github.com/ggml-org/llama.cpp.git
ARG LLAMA_CPP_REF=master

# 1080 Ti = compute capability 6.1. Build for that arch only -> smaller, faster
# compile. Add more here (e.g. "61;75;86") if the image must run elsewhere.
ARG CUDA_ARCHS=61

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        ccache \
        cmake \
        git \
        libcurl4-openssl-dev \
        ninja-build \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --filter=blob:none ${LLAMA_CPP_REPO} llama.cpp \
    && cd llama.cpp \
    && git checkout ${LLAMA_CPP_REF} \
    && git submodule update --init --recursive --depth 1 \
    && git rev-parse HEAD > /src/LLAMA_CPP_COMMIT

WORKDIR /src/llama.cpp

# Pascal-specific notes:
#   GGML_CUDA_F16=OFF       1080 Ti runs fp16 at 1/64 of fp32 rate -- forcing
#                           the fp16 path would be a large slowdown.
#   GGML_CUDA_FORCE_MMQ=ON  use the integer (dp4a) quantized matmul kernels,
#                           which sm_61 does support, instead of dequant+cuBLAS.
#   GGML_NATIVE=OFF         no -march=native, so the image stays portable.
# LLAMA_BUILD_EXAMPLES=OFF drops the demo programs; tools (llama-server,
# llama-cli, llama-bench, llama-quantize, llama-perplexity) are what is used.
# libggml-cuda.so records a dependency on libcuda.so.1 (the CUDA driver API:
# cuMemCreate, cuMemMap, ... for its VMM pooled allocator). The devel image
# ships only the stub /usr/local/cuda/lib64/stubs/libcuda.so, with no .so.1,
# so linking any executable against that shared library fails with
# "undefined reference to cuMemCreate". Give the linker a .so.1 to find.
# The real driver is injected by the NVIDIA container runtime at run time;
# this stub must therefore be visible ONLY while linking -- hence the symlink
# stays in the builder stage and the flag below is -rpath-link (link-time
# search) and not -rpath (which would bake the stub into the binaries and
# make them load a driver that cannot talk to a GPU).
RUN ln -sf /usr/local/cuda/lib64/stubs/libcuda.so \
           /usr/local/cuda/lib64/stubs/libcuda.so.1

RUN cmake -B build -S . -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCHS} \
        -DGGML_CUDA=ON \
        -DGGML_CUDA_F16=OFF \
        -DGGML_CUDA_FORCE_MMQ=ON \
        -DGGML_NATIVE=OFF \
        -DLLAMA_CURL=ON \
        -DLLAMA_BUILD_SERVER=ON \
        -DLLAMA_BUILD_TOOLS=ON \
        -DLLAMA_BUILD_EXAMPLES=OFF \
        -DLLAMA_BUILD_TESTS=OFF \
        -DBUILD_SHARED_LIBS=ON \
        -DCMAKE_EXE_LINKER_FLAGS="-Wl,-rpath-link,/usr/local/cuda/lib64/stubs" \
        -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-rpath-link,/usr/local/cuda/lib64/stubs" \
    && cmake --build build --config Release -j"$(nproc)" \
    && cmake --install build --prefix /opt/llama.cpp

# convert_hf_to_gguf.py & friends -- handy for re-quantizing the local
# safetensors copy in ../Qwen3.8-27B later. Costs nothing to carry.
RUN mkdir -p /opt/llama.cpp/scripts \
    && cp -r convert_hf_to_gguf.py gguf-py requirements /opt/llama.cpp/scripts/ 2>/dev/null || true

# -----------------------------------------------------------------------------
#  Stage 2 — runtime
# -----------------------------------------------------------------------------
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION}

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libcurl4 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/llama.cpp /opt/llama.cpp
COPY --from=builder /src/LLAMA_CPP_COMMIT /opt/llama.cpp/COMMIT

ENV PATH=/opt/llama.cpp/bin:${PATH} \
    LD_LIBRARY_PATH=/opt/llama.cpp/lib:${LD_LIBRARY_PATH} \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /models
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15m --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

ENTRYPOINT ["llama-server"]

# Defaults sized for this host. Override by appending flags to `docker run`
# (the whole CMD is replaced, so repeat what you still need).
#
#   -m                weights bind-mounted at /models/model.gguf
#   -ngl 999          every layer on GPU
#   --tensor-split    even split over the 4 cards (30GB weights / 44GB VRAM)
#   -c 32768          KV is small here (only ~1 of every 4 blocks is full
#                     attention), so 32k costs ~2GB; raise or lower freely
#   --jinja           REQUIRED: enables the chat template's tool-call path,
#                     which maplez_struct.py depends on
CMD ["-m", "/models/model.gguf", \
     "--alias", "qwen3.8-27b", \
     "-ngl", "999", \
     "--split-mode", "layer", \
     "--tensor-split", "1,1,1,1", \
     "-c", "32768", \
     "-t", "12", \
     "--parallel", "1", \
     "--jinja", \
     "--host", "0.0.0.0", \
     "--port", "8080"]
