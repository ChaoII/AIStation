# pytorch-ocr

AIStation 自研 PyTorch OCR 库（PP-OCRv6 架构对齐：det 检测 + rec 识别），作为独立库打包进 `aistation-ocr` Docker 镜像（与 ultralytics 镜像的集成方式一致）。

## 结构

```
pytorch-ocr/
├── pyproject.toml          # 独立库（pip install）
├── pytorch_ocr/            # 库代码
│   ├── cli.py              # 命令行入口（train-det/eval-det/train-rec/eval-rec/predict）
│   ├── modeling/           # PPLCNetV4 / RepLKFPN / DBHead / CTCHead / NRTRHead / MultiHead
│   ├── data/               # DetDataset / RecDataset / CharacterDict / 增强
│   ├── trainer/            # DetTrainer / RecTrainer（训练循环）
│   ├── inference/          # OCRPipeline（det→rec 串联）
│   ├── postprocess/        # DBPostProcess / CTCLabelDecode
│   ├── converter/          # Paddle→PyTorch 权重转换 + 验证
│   └── utils/dict/         # PP-OCRv6 官方字符集
├── tests/                  # 库内单元测试
└── Dockerfile               # aistation-ocr 镜像（pip install 本库）
```

## 用法

容器内（aistation-ocr 镜像）：

```bash
python -m pytorch_ocr.cli train-det --data /data --output /output --device 0
python -m pytorch_ocr.cli train-rec --data /data --output /output --device 0
python -m pytorch_ocr.cli predict --image /input.jpg --det-model /model/det.pt --rec-model /model/rec.pt
```

## 测试

```bash
pip install -e .[test]   # 或手动安装 torch/opencv/pyclipper
pytest tests/
```

## 权重转换

官方 PP-OCRv6 权重（Paddle `.pdparams`）→ PyTorch `.pt`：

```bash
python -m pytorch_ocr.converter.verify_conversion --paddle ... --pytorch ...
```

det 转换已用官方权重验证（MSE 1.68e-11），rec 转换支持官方 GTC 双头。
