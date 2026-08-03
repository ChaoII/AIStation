FROM pytorch/pytorch:2.13.0-cuda13.2-cudnn9-runtime

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（Ubuntu 24.04 基础镜像带 EXTERNALLY-MANAGED 标记，需 --break-system-packages）
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# 打包 pytorch_ocr 包
WORKDIR /workspace
COPY pytorch_ocr/ /workspace/pytorch_ocr/

# 默认入口
ENTRYPOINT ["python", "-m", "pytorch_ocr.cli"]
