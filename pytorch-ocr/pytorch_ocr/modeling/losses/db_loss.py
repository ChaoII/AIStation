"""DBLoss（prob + thresh + binary，主损失 DiceFocal）。自研实现。"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def _dice_loss(pred, target, mask):
    """Dice loss，对齐官方 DiceLoss（det_basic_loss.py）。

    官方: intersection = sum(pred * gt * mask);
          union = sum(pred * mask) + sum(gt * mask) + eps
          loss = 1 - 2.0 * intersection / union
    """
    eps = 1e-6
    intersect = torch.sum(pred * target * mask)
    union = torch.sum(pred * mask) + torch.sum(target * mask) + eps
    return 1 - 2.0 * intersect / union


def _mask_l1_loss(pred, target, mask):
    """MaskL1Loss（对齐官方 det_basic_loss.py）：mask 内平均 L1。

    loss = (abs(pred - gt) * mask).sum() / (mask.sum() + eps)
    """
    eps = 1e-6
    return (torch.abs(pred - target) * mask).sum() / (mask.sum() + eps)


def _focal_loss(pred, target, mask, alpha=0.25, gamma=2.5):
    """二分类 Focal loss，对齐官方 MaskedFocalLoss。

    官方: pred=clip(pred,eps,1-eps); logit=log(pred/(1-pred));
          loss = sigmoid_focal_loss(logit, gt, alpha, gamma)  # -alpha_t*(1-p_t)^gamma*log(p_t)
          return (loss * mask).sum() / (mask.sum() + eps)
    """
    eps = 1e-6
    pred = pred.clamp(eps, 1 - eps)
    logit = torch.log(pred / (1 - pred))
    p = torch.sigmoid(logit)
    ce = F.binary_cross_entropy_with_logits(logit, target, reduction="none")
    p_t = p * target + (1 - p) * (1 - target)
    alpha_t = alpha * target + (1 - alpha) * (1 - target)
    loss = alpha_t * (1 - p_t).pow(gamma) * ce
    return (loss * mask).sum() / (mask.sum() + eps)


class DBLoss(nn.Module):
    """DB 检测损失 = alpha*L_binary + beta*L_thresh + L_prob。

    main_loss_type: "DiceFocalLoss"（binary 用 dice+focal）/ "BCELoss"
    """

    def __init__(
        self,
        alpha=5,
        beta=10,
        main_loss_type="DiceFocalLoss",
        focal_alpha=0.25,
        focal_gamma=2.5,
        aux_weight_p4=0.0,
        aux_weight_p3=0.0,
        aux_weight_p2=0.0,
    ):
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.main_loss_type = main_loss_type
        self.focal_alpha = focal_alpha
        self.focal_gamma = focal_gamma
        self.aux_weight = {"p4": aux_weight_p4, "p3": aux_weight_p3, "p2": aux_weight_p2}

    def _binary_loss(self, pred, gt):
        mask = gt["shrink_mask"]
        target = gt["shrink_map"]
        if self.main_loss_type == "DiceLoss":
            # 官方 PP-OCRv5 det：shrink/binary 均用纯 DiceLoss
            # （balance_loss + OHEM 对 DiceLoss 标量无增益，官方实际等效纯 Dice）
            return _dice_loss(pred, target, mask)
        if self.main_loss_type == "DiceFocalLoss":
            dice = _dice_loss(pred, target, mask)
            focal = _focal_loss(pred, target, mask,
                                self.focal_alpha, self.focal_gamma)
            # 对齐官方 DiceFocalLoss：dice_weight=1.0, focal_weight=1.0
            return dice + focal
        return F.binary_cross_entropy(pred, gt["shrink_map"], reduction="mean")

    def forward(self, pred, gt):
        # pred: dict {maps, aux_maps_*}（训练，head 完整输出）或 (N,3,H,W) tensor
        if isinstance(pred, dict):
            aux_maps = {k: v for k, v in pred.items() if k.startswith("aux_maps_")}
            pred = pred["maps"]
        else:
            aux_maps = {}
        # pred: (N, 3, H, W) = [shrink, thresh, binary]
        # 对齐官方 DBLoss：
        #   shrink (ch0) -> DiceFocalLoss(Dice + MaskedFocal, mask 内)
        #   thresh (ch1) -> MaskL1
        #   binary (ch2) -> DiceFocalLoss(Dice + MaskedFocal, mask 内)
        shrink_pred = pred[:, 0:1]
        thresh_pred = pred[:, 1:2]
        binary_pred = pred[:, 2:3]
        shrink_mask = gt["shrink_mask"]
        shrink_target = gt["shrink_map"]

        shrink_loss = self._binary_loss(shrink_pred, gt)
        thresh_mask = gt["threshold_mask"]
        thresh_target = gt["threshold_map"]
        # MaskL1（官方 det_basic_loss.py）：mask 内平均 L1
        thresh_loss = _mask_l1_loss(thresh_pred, thresh_target, thresh_mask)
        binary_loss = self._binary_loss(binary_pred, gt)
        loss = self.alpha * shrink_loss + self.beta * thresh_loss + binary_loss

        # 多尺度辅助损失（aux_maps_p4/p3/p2），对齐官方 aux_weight 加权
        for level in ("p4", "p3", "p2"):
            w = self.aux_weight.get(level, 0.0)
            key = f"aux_maps_{level}"
            if w <= 0 or key not in aux_maps:
                continue
            aux = aux_maps[key]
            aux_shrink = aux[:, 0:1]
            aux_thresh = aux[:, 1:2]
            aux_binary = aux[:, 2:3]
            l_shrink = self.alpha * self._binary_loss(aux_shrink, gt)
            l_thresh = self.beta * _mask_l1_loss(
                aux_thresh, thresh_target, thresh_mask)
            l_binary = self._binary_loss(aux_binary, gt)
            loss = loss + w * (l_shrink + l_thresh + l_binary)
        return loss
