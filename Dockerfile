FROM ultralytics/ultralytics:latest

RUN pip install "onnx>=1.12.0,<2.0.0" onnxruntime "onnxslim>=0.1.82" -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir