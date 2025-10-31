FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LLAMA_CPP_REPO=https://github.com/ggerganov/llama.cpp.git \
    BUILD_DIR=/opt/llama.cpp

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        build-essential \
        cmake \
        python3 \
        python3-pip \
        curl && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 ${LLAMA_CPP_REPO} ${BUILD_DIR} && \
    cmake -S ${BUILD_DIR} -B ${BUILD_DIR}/build -DLLAMA_CUBLAS=OFF && \
    cmake --build ${BUILD_DIR}/build -j $(nproc)

WORKDIR ${BUILD_DIR}

RUN pip3 install --no-cache-dir huggingface-hub==0.25.2

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]

