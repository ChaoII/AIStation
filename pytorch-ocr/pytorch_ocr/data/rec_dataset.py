"""rec 训练数据集：读取 train_list.txt，返回 CTC/NRTR 标签。自研实现。"""
import os

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

_MEAN = np.array([0.5, 0.5, 0.5], dtype=np.float32)
_STD = np.array([0.5, 0.5, 0.5], dtype=np.float32)

_DEFAULT_DICT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "utils", "dict", "ppocrv6_tiny_dict.txt"
)


class CharacterDict:
    """字符集 <-> 索引映射。

    索引 0 保留给 CTC blank（对齐官方 PP-OCRv6 ``ctc_blank_idx=0``），
    真实字符从索引 1 开始（``char_to_idx`` 存储 ``i + 1``）。
    """

    def __init__(self, dict_path: str, use_space_char: bool = True, blank_idx: int = 0):
        self.characters = []
        with open(dict_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip("\n")
                if line != "":
                    self.characters.append(line)
        if use_space_char:
            self.characters.append(" ")
        # 字符索引 +1（保留索引 0 给 blank），对齐官方 PP-OCRv6 (ctc_blank_idx=0)
        self.char_to_idx = {c: i + 1 for i, c in enumerate(self.characters)}
        self.idx_to_char = {i + 1: c for i, c in enumerate(self.characters)}
        self.blank = blank_idx  # 0

    @property
    def num_classes(self):
        return len(self.characters) + 1  # +1 blank

    def encode(self, text: str) -> list:
        return [self.char_to_idx[c] for c in text if c in self.char_to_idx]


class RecDataset(Dataset):
    def __init__(
        self,
        data_dir,
        label_path,
        image_shape=(48, 320),
        dict_path=None,
        max_text_length=25,
        is_train=True,
    ):
        self.data_dir = data_dir
        self.image_shape = image_shape
        self.max_text_length = max_text_length
        if dict_path is None:
            dict_path = _DEFAULT_DICT_PATH
        self.char_dict = CharacterDict(dict_path)
        self.items = []
        with open(label_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "\t" not in line:
                    continue
                img_name, label = line.split("\t", 1)
                self.items.append((img_name, label))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        img_name, label = self.items[idx]
        img = cv2.imread(os.path.join(self.data_dir, img_name), cv2.IMREAD_COLOR)
        if img is None:
            return self[(idx + 1) % len(self.items)]
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.image_shape[1], self.image_shape[0]))
        img = (img.astype(np.float32) / 255.0 - _MEAN) / _STD
        img = torch.from_numpy(img).permute(2, 0, 1).float()

        # CTC 标签（索引列表）；torch.nn.CTCLoss 内部处理 target 序列
        label_ctc = self.char_dict.encode(label)[: self.max_text_length]
        length = len(label_ctc)
        # NRTR 标签：pad 到 max_text_length，pad token = 0
        label_gtc = torch.zeros(self.max_text_length, dtype=torch.long)
        if length > 0:
            label_gtc[:length] = torch.tensor(label_ctc, dtype=torch.long)
        return img, label_ctc, label_gtc, length
