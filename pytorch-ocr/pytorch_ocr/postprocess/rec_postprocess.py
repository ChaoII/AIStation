"""rec 解码：CTC logits → 文本。自研实现。"""
import os

import numpy as np
import torch

from ..data.rec_dataset import CharacterDict

_DEFAULT_DICT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "utils", "dict", "ppocrv6_tiny_dict.txt"
)


class CTCLabelDecode:
    """CTC 贪心解码：argmax → 去重（blank 忽略）。"""

    def __init__(self, dict_path=None, use_space_char=True, blank_idx=0):
        if dict_path is None:
            dict_path = _DEFAULT_DICT_PATH
        self.char_dict = CharacterDict(
            dict_path, use_space_char=use_space_char, blank_idx=blank_idx
        )

    def __call__(self, logits):
        """logits: [B, W, C]（softmax 后）→ [str, ...]。"""
        if isinstance(logits, torch.Tensor):
            logits = logits.detach().cpu().numpy()
        preds = np.argmax(logits, axis=-1)  # [B, W]
        blank = self.char_dict.blank
        results = []
        for pred in preds:
            chars = []
            for i, idx in enumerate(pred):
                if idx == blank:
                    continue
                if i > 0 and idx == pred[i - 1]:
                    continue  # 去重
                chars.append(self.char_dict.idx_to_char[int(idx)])
            results.append("".join(chars))
        return results
