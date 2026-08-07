FROM pytorch/pytorch:2.13.0-cuda13.2-cudnn9-runtime

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 用清华镜像装轻量依赖（基础镜像已含 torch，不重复下载）
RUN pip install --no-cache-dir --break-system-packages \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    opencv-python-headless>=5.0.0.93 pyclipper>=1.4.0 pillow>=10.0.0 \
    albumentations>=1.4.0 shapely>=2.0.0

# 安装独立 OCR 库（--no-deps 避免重复拉 torch）
WORKDIR /workspace
COPY pyproject.toml README.md ./
COPY pytorch_ocr/ pytorch_ocr/
RUN pip install --no-cache-dir --break-system-packages \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --no-deps .

# 默认入口
ENTRYPOINT ["python", "-m", "pytorch_ocr.cli"]
