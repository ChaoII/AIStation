"""共享层：激活函数等。"""
import torch.nn as nn


class Activation(nn.Module):
    """按名称选择激活函数（relu/hardswish/silu/gelu）。"""

    def __init__(self, act_type: str = "relu"):
        super().__init__()
        if act_type == "relu":
            self.act = nn.ReLU(inplace=True)
        elif act_type == "hardswish":
            self.act = nn.Hardswish()
        elif act_type == "silu":
            self.act = nn.SiLU(inplace=True)
        elif act_type == "gelu":
            self.act = nn.GELU()
        else:
            raise ValueError(f"unsupported activation: {act_type}")

    def forward(self, x):
        return self.act(x)
