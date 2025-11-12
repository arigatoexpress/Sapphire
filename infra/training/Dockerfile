ARG BASE_IMAGE=pytorch/pytorch:2.2.2-cuda12.1-cudnn8-runtime
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    PYTHONPATH=/workspace:$PYTHONPATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt /tmp/base.txt
COPY cloud_trader/training/requirements.txt /tmp/training.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/base.txt && \
    pip install --no-cache-dir -r /tmp/training.txt

COPY cloud_trader /workspace/cloud_trader
COPY models/common /workspace/models/common

ENTRYPOINT ["python"]
