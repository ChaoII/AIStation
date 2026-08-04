"""OCR 推理管线：det 检测 → rec 识别 → 聚合。自研实现。"""
import cv2
import numpy as np
import torch

from ..modeling.backbones.pplcnetv4 import PPLCNetV4, rec_backbone_out_channels
from ..modeling.heads.det_db_head import DBHead
from ..modeling.heads.rec_multi_head import MultiHead
from ..modeling.necks.rep_lk_fpn import RepLKFPN
from ..postprocess.db_postprocess import DBPostProcess
from ..postprocess.rec_postprocess import CTCLabelDecode

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _preprocess(image, size):
    """BGR→RGB→等比缩放+padding→normalize→CHW。

    对齐官方 DetResizeForTest 的 letterbox：最长边缩放到 size，短边等比，
    不足处 padding 0。避免直接拉伸导致文字变形（训练增强同样用等比）。
    """
    img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]
    th, tw = size
    scale = min(tw / w, th / h)
    if scale < 1.0:
        new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        img = cv2.resize(img, (new_w, new_h))
    else:
        new_w, new_h = w, h
    pad = np.zeros((th, tw, 3), dtype=np.uint8)
    pad[:new_h, :new_w] = img
    pad = (pad.astype(np.float32) / 255.0 - _MEAN) / _STD
    return torch.from_numpy(pad).permute(2, 0, 1).unsqueeze(0).float()


def _infer_rec_out_channels(rec_state, config):
    """从 rec 权重 state_dict 形状推断 CTC/NRTR 词表大小。

    官方 PP-OCRv6 双头词表不同（CTC=dict 大小 6906，NRTR=dict+4 特殊 token
    6910）；用户训练产物两头顶为同词表（6906/6906）。config 显式指定优先，
    否则按权重形状推导，缺省回退到 ``num_classes``。
    """
    ctc = config.get("ctc_out_channels")
    nrtr = config.get("nrtr_out_channels")
    if rec_state:
        for key in ("head.ctc_head.fc2.weight", "head.ctc_head.fc.weight"):
            if key in rec_state and ctc is None:
                ctc = int(rec_state[key].shape[0])
        for key in (
            "head.nrtr_head.transformer.tgt_word_prj.weight",
            "head.nrtr_head.transformer.embedding.embedding.weight",
        ):
            if key in rec_state and nrtr is None:
                nrtr = int(rec_state[key].shape[0])
    default = config.get("num_classes", 6906)
    return ctc or default, nrtr or default


class OCRPipeline:
    """det + rec 串联推理。det 模型为训练产物（PPLCNetV4+FPN+DBHead），
    rec 模型为训练产物（PPLCNetV4+MultiHead）。"""

    def __init__(self, det_state=None, rec_state=None, config=None):
        self.config = config or {}
        size = self.config.get("model_size", "tiny")
        out_channels = self.config.get("num_classes", 6906)
        max_text_length = self.config.get("max_text_length", 25)
        out_channels_fpn = self.config.get("out_channels", 64)

        # det 网络
        self.det_backbone = PPLCNetV4(model_size=size, det=True)
        neck = self.config.get("neck", "rep_lk_fpn")
        if neck == "rep_lk_pan":
            from ..modeling.necks.rep_lk_pan import RepLKPAN
            self.det_fpn = RepLKPAN(
                in_channels=self.det_backbone.feat_channels,
                out_channels=out_channels_fpn,
                intracl=self.config.get("intracl", False))
        else:
            self.det_fpn = RepLKFPN(
                in_channels=self.det_backbone.feat_channels,
                out_channels=out_channels_fpn,
                dilated_kernel_size=self.config.get("dilated_kernel_size", 5))
        self.det_head = DBHead(in_channels=out_channels_fpn,
                               k=self.config.get("k", 50))
        self.det_net = torch.nn.ModuleDict(
            {"backbone": self.det_backbone, "fpn": self.det_fpn, "head": self.det_head})
        if det_state is not None:
            # 兼容转换器命名（neck.*）与旧版命名（fpn.*）
            remapped = {}
            for k, v in det_state.items():
                if k.startswith("neck."):
                    remapped["fpn." + k[len("neck."):]] = v
                else:
                    remapped[k] = v
            self.det_net.load_state_dict(remapped, strict=False)
        self.det_net.eval()
        self.det_postprocess = DBPostProcess(
            thresh=self.config.get("thresh", 0.2),
            box_thresh=self.config.get("box_thresh", 0.45),
            max_candidates=self.config.get("max_candidates", 3000),
            unclip_ratio=self.config.get("unclip_ratio", 1.4))

        # rec 网络
        backbone_out = (self.config.get("backbone_out_channels")
                        or rec_backbone_out_channels(size))
        ctc_out, nrtr_out = _infer_rec_out_channels(rec_state, self.config)
        self.rec_backbone = PPLCNetV4(model_size=size, det=False)
        self.rec_head = MultiHead(
            in_channels=backbone_out, out_channels=out_channels,
            max_text_length=max_text_length,
            nrtr_dim=self.config.get("nrtr_dim", 384),
            ctc_out_channels=ctc_out,
            nrtr_out_channels=nrtr_out)
        self.rec_net = torch.nn.ModuleDict(
            {"backbone": self.rec_backbone, "head": self.rec_head})
        if rec_state is not None:
            self.rec_net.load_state_dict(rec_state, strict=False)
        self.rec_net.eval()
        self.rec_decode = CTCLabelDecode()

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")
        self.det_net.to(self.device)
        self.rec_net.to(self.device)

    @torch.no_grad()
    def __call__(self, image):
        """image: BGR ndarray → [{text, confidence, box}]。

        det 输入用等比缩放 + padding（letterbox）。DBPostProcess 的 shape_list
        传缩放后图像尺寸 [new_h, new_w]，得到缩放图坐标系下的框，再乘回原图
        缩放因子得到原图坐标（padding 区域无真实内容，不产生框）。
        """
        image_h, image_w = image.shape[:2]
        det_input = _preprocess(image, (640, 640))
        # 等比缩放后的实际图像尺寸（padding 前），用于正确映射坐标
        scale = min(640.0 / image_w, 640.0 / image_h)
        new_w, new_h = max(1, int(round(image_w * scale))), max(1, int(round(image_h * scale)))
        feats = self.det_backbone(det_input.to(self.device))
        fused = self.det_fpn(feats)
        if isinstance(fused, dict):
            fused = fused["fuse"]
        det_out = self.det_head(fused)  # {"maps": (1,1,640,640)}
        maps = det_out["maps"]
        # dest_size 与 maps 同尺寸（640×640），返回 640 坐标系框
        boxes = self.det_postprocess(maps.cpu(), [[640, 640]])

        # 放大回原图坐标系
        results = []
        for box in boxes[0] if boxes else []:
            if len(box) != 4:
                continue
            box = np.array(box, dtype=np.float32)
            box[:, 0] = box[:, 0] * image_w / new_w
            box[:, 1] = box[:, 1] * image_h / new_h
            quad = np.array(box, dtype=np.float32)
            # 透视矫正裁剪
            cropped = self._crop_box(image, quad)
            if cropped is None or cropped.size == 0:
                continue
            text, conf = self._recognize(cropped)
            if text:
                results.append({
                    "text": text,
                    "confidence": float(conf),
                    "box": box.tolist(),
                })
        return results

    def _crop_box(self, image, quad):
        """四边形透视矫正裁剪为矩形。

        用质心极角排序得到顺时针四边形，再旋转保证 0-1 边为顶部长边，
        避免 ``minAreaRect`` 对水平框返回转置宽高（angle=-90 的怪癖）。
        """
        h, w = image.shape[:2]
        quad = np.clip(quad, 0, [w, h])
        src = np.array(quad, dtype=np.float32)
        center = src.mean(axis=0)
        angles = np.arctan2(src[:, 1] - center[1], src[:, 0] - center[0])
        src = src[np.argsort(angles)]
        e01 = float(np.linalg.norm(src[0] - src[1]))
        e12 = float(np.linalg.norm(src[1] - src[2]))
        if e12 > e01:
            src = np.roll(src, 1, axis=0)  # 使长边成为 0-1
        if src[0, 1] + src[1, 1] > src[2, 1] + src[3, 1]:
            src = np.roll(src, 2, axis=0)  # 使 0-1 为上边
        width = int(round(float(np.linalg.norm(src[0] - src[1]))))
        height = int(round(float(np.linalg.norm(src[1] - src[2]))))
        if width < 2 or height < 2:
            return None
        dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1],
                        [0, height - 1]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(src, dst)
        return cv2.warpPerspective(image, M, (width, height))

    def _recognize(self, cropped):
        """识别单行文字。返回 (text, confidence)。

        官方 PP-OCRv6 rec 输入用 [-1,1] 归一化（mean=std=0.5），与 det 的
        ImageNet 归一化不同，这里单独处理。
        """
        # 缩放到 rec 输入高度 48，宽度按比例（最小 8 最大 320）
        h, w = cropped.shape[:2]
        target_h = 48
        target_w = max(8, min(320, int(w * target_h / max(h, 1))))
        img = cv2.resize(cropped, (target_w, target_h))
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        x = ((rgb.astype(np.float32) / 255.0 - 0.5) / 0.5)
        x = torch.from_numpy(x).permute(2, 0, 1).unsqueeze(0).float()
        feats = self.rec_backbone(x.to(self.device))
        preds = self.rec_head(feats)  # eval: dict {ctc, nrtr}
        ctc_probs = preds["ctc"]  # [1, W, C] (softmax)
        text = self.rec_decode(ctc_probs)[0]
        conf = float(ctc_probs.max(dim=-1).values.mean())
        return text, conf
