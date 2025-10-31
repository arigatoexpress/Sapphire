FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        git \
        curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
    vllm==0.4.2 \
    fastapi==0.110.2 \
    uvicorn==0.29.0

WORKDIR /workspace

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]

