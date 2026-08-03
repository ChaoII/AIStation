"""rec 数据集测试。"""
import os
import tempfile

import numpy as np
import torch
from PIL import Image

from pytorch_ocr.data.rec_dataset import CharacterDict, RecDataset

_DICT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "pytorch_ocr", "utils", "dict", "ppocrv6_tiny_dict.txt"
)


def test_character_dict_loads():
    cd = CharacterDict(_DICT_PATH, use_space_char=True)
    assert len(cd.characters) > 1000
    assert cd.characters[-1] == " "
    assert cd.blank == 0
    assert cd.num_classes == len(cd.characters) + 1
    assert cd.char_to_idx["一"] >= 1
    assert cd.idx_to_char[cd.char_to_idx["一"]] == "一"
    encoded = cd.encode("你好一")
    assert all(i >= 1 for i in encoded)
    assert [cd.idx_to_char[i] for i in encoded] == ["你", "好", "一"]
    assert 0 not in cd.idx_to_char


def test_character_dict_skips_unknown():
    cd = CharacterDict(_DICT_PATH, use_space_char=False)
    encoded = cd.encode("你好\uffff未知字符")
    assert [cd.idx_to_char[i] for i in encoded] == ["你", "好", "未", "知", "字", "符"]


def test_rec_dataset_len_and_item():
    with tempfile.TemporaryDirectory() as tmp:
        img = np.random.randint(0, 255, (48, 320, 3), dtype=np.uint8)
        Image.fromarray(img).save(os.path.join(tmp, "img_0.jpg"))
        lst = os.path.join(tmp, "train_list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write("img_0.jpg\t你好世界\n")
        ds = RecDataset(data_dir=tmp, label_path=lst, image_shape=(48, 320))
        assert len(ds) == 1
        item = ds[0]
        # 4 元组 (image, label_ctc, label_gtc, length)
        assert isinstance(item, tuple) and len(item) == 4
        image, label_ctc, label_gtc, length = item
        assert image.shape == (3, 48, 320)
        assert isinstance(label_ctc, list)
        assert isinstance(label_gtc, torch.Tensor)
        assert label_gtc.shape == (ds.max_text_length,)
        assert label_gtc.dtype == torch.long
        assert label_gtc[:length].tolist() == label_ctc
        assert label_gtc[length:].sum() == 0  # pad token 0
        assert length == len("你好世界")
