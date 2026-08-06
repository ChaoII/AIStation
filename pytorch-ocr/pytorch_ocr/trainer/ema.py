"""EMA（指数移动平均），精确对齐 PaddleOCR ModelEMA（ppocr/utils/ema.py）。

关键：decay 为 threshold 型 ``min(decay, (1+step)/(10+step))``（从 0.1 升到目标），
shadow 初始为 zeros，apply() 时做 bias correction ``v / (1 - decay**step)``。
"""
import torch


class ModelEMA:
    def __init__(self, model, decay=0.9998, gamma=2000, ema_decay_type="threshold"):
        self.decay = decay
        self.gamma = gamma
        self.ema_decay_type = ema_decay_type
        self.step = 0
        self._decay = decay
        # shadow 初始 zeros（对齐官方）
        self.state = {}
        for k, v in model.state_dict().items():
            self.state[k] = torch.zeros_like(v, dtype=torch.float32)

    def _get_decay(self):
        if self.ema_decay_type == "threshold":
            return min(self.decay, (1 + self.step) / (10 + self.step))
        elif self.ema_decay_type == "exponential":
            import math
            return self.decay * (1 - math.exp(-(self.step + 1) / self.gamma))
        return self.decay

    def update(self, model):
        decay = self._get_decay()
        self._decay = decay
        model_dict = model.state_dict()
        with torch.no_grad():
            for k, v in self.state.items():
                if k in model_dict:
                    cur = model_dict[k]
                    if v.dtype != cur.dtype:
                        cur = cur.to(v.dtype)
                    self.state[k] = decay * v + (1 - decay) * cur
        self.step += 1

    def apply(self):
        """返回 bias-corrected EMA 状态（供 eval/save），不改内部。"""
        if self.step == 0:
            return {k: v.clone() for k, v in self.state.items()}
        out = {}
        for k, v in self.state.items():
            if self.ema_decay_type != "exponential":
                # threshold / normal 需 bias correction
                v = v / (1 - self._decay**self.step)
            out[k] = v.clone()
        return out
