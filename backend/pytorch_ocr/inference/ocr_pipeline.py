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
    """BGR→RGB→resize→normalize→CHW。"""
    img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (size[1], size[0]))
    img = (img.astype(np.float32) / 255.0 - _MEAN) / _STD
    return torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float()


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
        self.det_fpn = RepLKFPN(
            in_channels=self.det_backbone.feat_channels,
            out_channels=out_channels_fpn,
            dilated_kernel_size=self.config.get("dilated_kernel_size", 5))
        self.det_head = DBHead(in_channels=out_channels_fpn,
                               k=self.config.get("k", 50))
        self.det_net = torch.nn.ModuleDict(
            {"backbone": self.det_backbone, "fpn": self.det_fpn, "head": self.det_head})
        if det_state is not None:
            self.det_net.load_state_dict(det_state, strict=False)
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

        det 输入被缩放为 640×640（非 letterbox），DBPostProcess 的 shape_list
        传原图尺寸 [H, W]，使返回的 box 落在原图坐标系，随后可直接在原图上裁剪。
        """
        image_h, image_w = image.shape[:2]
        det_input = _preprocess(image, (640, 640))
        feats = self.det_backbone(det_input.to(self.device))
        fused = self.det_fpn(feats)
        if isinstance(fused, dict):
            fused = fused["fuse"]
        det_out = self.det_head(fused)  # {"maps": (1,1,640,640)}
        maps = det_out["maps"]
        boxes = self.det_postprocess(maps.cpu(), [[image_h, image_w]])

        # rec on each box
        results = []
        for box in boxes[0] if boxes else []:
            if len(box) != 4:
                continue
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
                    "box": box,
                })
        return results

    def _crop_box(self, image, quad):
        """四边形透视矫正裁剪为矩形。"""
        h, w = image.shape[:2]
        quad = np.clip(quad, 0, [w, h])
        src = np.array(quad, dtype=np.float32)
        rect = cv2.minAreaRect(src)
        box = cv2.boxPoints(rect)
        box = np.array(box, dtype=np.float32)
        width = int(rect[1][0])
        height = int(rect[1][1])
        if width < 2 or height < 2:
            return None
        dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1],
                        [0, height - 1]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(box, dst)
        return cv2.warpPerspective(image, M, (width, height))

    def _recognize(self, cropped):
        """识别单行文字。返回 (text, confidence)。"""
        # 缩放到 rec 输入高度 48，宽度按比例（最小 8 最大 320）
        h, w = cropped.shape[:2]
        target_h = 48
        target_w = max(8, min(320, int(w * target_h / max(h, 1))))
        img = cv2.resize(cropped, (target_w, target_h))
        img = _preprocess(img, (target_h, target_w))
        feats = self.rec_backbone(img.to(self.device))
        preds = self.rec_head(feats)  # eval: dict {ctc, nrtr}
        ctc_probs = preds["ctc"]  # [1, W, C] (softmax)
        text = self.rec_decode(ctc_probs)[0]
        conf = float(ctc_probs.max(dim=-1).values.mean())
        return text, conf
