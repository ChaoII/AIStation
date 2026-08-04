"""rec 解码与训练器测试。"""
import os
import tempfile

import numpy as np
import pytest
import torch
from PIL import Image

from pytorch_ocr.postprocess.rec_postprocess import CTCLabelDecode
from pytorch_ocr.trainer.rec_trainer import RecTrainer


def test_ctc_decode_default_dict():
    """CTCLabelDecode 用默认字符集，返回 [str, ...]（不锁定具体文本）。"""
    decode = CTCLabelDecode(dict_path=None)
    # 模拟 logits：B=1, W=5, C=10
    logits = torch.zeros(1, 5, 10)
    logits[0, 0, 1] = 2.0
    logits[0, 1, 2] = 2.0
    logits[0, 2, 0] = 2.0  # blank
    logits[0, 3, 2] = 2.0
    logits[0, 4, 3] = 2.0
    text = decode(logits)
    assert isinstance(text, list) and len(text) == 1
    assert isinstance(text[0], str)


def test_ctc_decode_dedup_and_blank():
    """自定义小字符集：验证 blank 跳过 + 连续重复去重。"""
    with tempfile.TemporaryDirectory() as tmp:
        dict_path = os.path.join(tmp, "dict.txt")
        with open(dict_path, "w", encoding="utf-8") as f:
            f.write("a\nb\nc\nd\n")
        decode = CTCLabelDecode(dict_path=dict_path)
        # characters = [a, b, c, d, ' ']，blank = 0（索引 0 保留给 blank）
        logits = torch.zeros(1, 6, 6)
        logits[0, 0, 1] = 2.0  # a
        logits[0, 1, 1] = 2.0  # a（连续重复，应去重）
        logits[0, 2, 0] = 2.0  # blank（应跳过）
        logits[0, 3, 2] = 2.0  # b
        logits[0, 4, 3] = 2.0  # c
        logits[0, 5, 4] = 2.0  # d
        assert decode(logits) == ["abcd"]


def test_rec_trainer_has_train_eval():
    assert hasattr(RecTrainer, "train")
    assert hasattr(RecTrainer, "eval")


def test_rec_trainer_empty_dataset_raises():
    """空 train_list.txt 时 train() 应抛出 ValueError。"""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "train_list.txt"), "w", encoding="utf-8") as f:
            f.write("")
        config = {
            "model_size": "tiny",
            "num_classes": 6906,
            "image_shape": (48, 320),
        }
        trainer = RecTrainer(config, device="cpu")
        with pytest.raises(ValueError, match="数据集为空"):
            trainer.train(
                data_dir,
                num_epochs=1,
                output_dir=os.path.join(tmp, "output"),
                workers=0,
            )


def _write_synthetic_data(data_dir, num_images=3):
    """构造最小可训练数据集：data_dir/img_*.jpg + data_dir/train_list.txt。"""
    os.makedirs(data_dir, exist_ok=True)
    lines = []
    for i in range(num_images):
        img = np.random.randint(0, 255, (48, 320, 3), dtype=np.uint8)
        Image.fromarray(img).save(os.path.join(data_dir, f"img_{i}.jpg"))
        lines.append(f"img_{i}.jpg\t你好世界\n")
    with open(os.path.join(data_dir, "train_list.txt"), "w", encoding="utf-8") as f:
        f.writelines(lines)


def test_rec_trainer_smoke_train_produces_best_pt():
    """端到端冒烟：CPU 上 1 个 epoch 训练后 output_dir 生成 best.pt。"""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        output_dir = os.path.join(tmp, "output")
        _write_synthetic_data(data_dir)
        config = {
            "model_size": "tiny",
            "num_classes": 6906,
            "image_shape": (48, 320),
            "max_text_length": 25,
            "nrtr_dim": 384,
            "backbone_out_channels": 160,
        }
        trainer = RecTrainer(config, device="cpu")
        best_path = trainer.train(
            data_dir,
            num_epochs=1,
            batch_size=2,
            output_dir=output_dir,
            workers=0,
            lr=0.001,
        )
        assert best_path == os.path.join(output_dir, "best.pt")
        assert os.path.isfile(best_path)


# ---------------------------------------------------------------------------
# eval（字符级准确率）
# ---------------------------------------------------------------------------


def test_rec_trainer_backbone_out_channels_derived():
    """backbone_out_channels 缺省时按 model_size 推导（tiny=160/small=384/medium=768）。"""
    for size, expected in (("tiny", 160), ("small", 384), ("medium", 768)):
        config = {"model_size": size, "num_classes": 6906}
        trainer = RecTrainer(config, device="cpu")
        assert trainer.head.ctc_head.guide_layer[0].in_channels == expected
        assert trainer.backbone.out_channels == expected


def test_compute_rec_metrics_perfect():
    from pytorch_ocr.trainer.rec_trainer import compute_rec_metrics
    m = compute_rec_metrics(["abc", "你好"], ["abc", "你好"])
    assert m["char_acc"] == 1.0
    assert m["full_acc"] == 1.0
    assert m["total_chars"] == 5
    assert m["total_strings"] == 2


def test_compute_rec_metrics_partial():
    from pytorch_ocr.trainer.rec_trainer import compute_rec_metrics
    # "abcd" vs "abxy": 2/4 字符正确；"xx" vs "ab": 0/2；整句 0/2 正确
    m = compute_rec_metrics(["abcd", "xx"], ["abxy", "ab"])
    assert m["char_acc"] == pytest.approx(2 / 6)
    assert m["full_acc"] == 0.0
    assert m["total_chars"] == 6


def test_rec_trainer_eval_deterministic_char_acc():
    """eval 端到端：伪造 ctc 头固定输出 'a'，标签全为 'a' → char_acc=full_acc=1.0。"""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        os.makedirs(data_dir, exist_ok=True)
        dict_path = os.path.join(tmp, "dict.txt")
        with open(dict_path, "w", encoding="utf-8") as f:
            f.write("a\n")
        for i in range(2):
            img = np.random.randint(0, 255, (48, 320, 3), dtype=np.uint8)
            Image.fromarray(img).save(os.path.join(data_dir, f"img_{i}.jpg"))
        with open(os.path.join(data_dir, "train_list.txt"), "w", encoding="utf-8") as f:
            f.writelines([f"img_{i}.jpg\ta\n" for i in range(2)])

        config = {
            "model_size": "tiny",
            "num_classes": 3,
            "image_shape": (48, 320),
            "max_text_length": 5,
            "dict_path": dict_path,
        }
        trainer = RecTrainer(config, device="cpu")

        class FakeHead(torch.nn.Module):
            def forward(self, x):
                logits = torch.full((1, 40, 3), -100.0)
                logits[..., 1] = 0.0  # 'a'（索引 1，索引 0 是 blank）
                return {"ctc": logits, "nrtr": logits}

        trainer.net["head"] = FakeHead()
        trainer.head = FakeHead()
        result = trainer.eval(data_dir=data_dir)
        assert result["char_acc"] == 1.0
        assert result["full_acc"] == 1.0
        assert result["total_strings"] == 2


def test_rec_trainer_eval_returns_metrics_dict():
    """eval 返回真实指标 dict（键齐全、值域合法），不再返回 {}。"""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        _write_synthetic_data(data_dir)
        config = {
            "model_size": "tiny",
            "num_classes": 6906,
            "image_shape": (48, 320),
            "max_text_length": 25,
            "nrtr_dim": 384,
        }
        trainer = RecTrainer(config, device="cpu")
        result = trainer.eval(data_dir=data_dir)
        assert "char_acc" in result
        assert "full_acc" in result
        assert 0.0 <= result["char_acc"] <= 1.0
        assert 0.0 <= result["full_acc"] <= 1.0
        assert result["total_strings"] == 3

def test_rec_trainer_loads_pretrained():
    """RecTrainer 支持加载预训练权重（跳过 shape 不匹配层）。"""
    import tempfile, os
    from pytorch_ocr.trainer.rec_trainer import RecTrainer

    t = RecTrainer({"model_size": "tiny", "num_classes": 6906, "max_text_length": 25,
                    "nrtr_dim": 384, "backbone_out_channels": 160}, device="cpu")
    cur = t.net.state_dict()
    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
        torch.save(cur, f.name)
        tmp = f.name
    try:
        t2 = RecTrainer({"model_size": "tiny", "num_classes": 6906, "max_text_length": 25,
                         "nrtr_dim": 384, "backbone_out_channels": 160,
                         "pretrained": tmp}, device="cpu")
        assert t2.net.state_dict()["head.ctc_head.fc2.weight"].equal(cur["head.ctc_head.fc2.weight"])
    finally:
        os.remove(tmp)
