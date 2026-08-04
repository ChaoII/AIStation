"""DBLoss（prob + thresh + binary，主损失 DiceFocal）。自研实现。"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def _dice_loss(pred, target, mask):
    """Dice loss，仅在 mask=1（文字区域）计算（对齐官方 DiceLoss）。

    官方: intersection = sum(pred * gt * mask);
          union = sum(pred * mask) + sum(gt * mask)
    注意这里 pred/target 不带 mask 相乘进入求和（官方只对 mask 区域统计，
    而非先乘 mask 再全图求和——后者会把 mask 外 pred 也计入 union，语义错误）。
    """
    smooth = 1e-5
    intersect = torch.sum(pred * target * mask)
    union = torch.sum(pred * mask) + torch.sum(target * mask) + smooth
    return 1 - (2 * intersect + smooth) / union


def _focal_loss(pred, target, mask, alpha=0.25, gamma=2.5):
    """二分类 Focal loss，仅在 mask=1（文字区域）平均（对齐官方 MaskedFocalLoss）。

    官方: (weight * loss * mask).sum() / mask.sum()
    全图平均会被大量背景像素稀释（本项目文字仅占 ~2%），导致模型学不到文字。
    """
    eps = 1e-6
    pt = torch.where(target > 0.5, pred, 1 - pred).clamp(eps, 1 - eps)
    weight = alpha * (1 - pt).pow(gamma)
    loss = F.binary_cross_entropy(pred, target, reduction="none")
    return (weight * loss * mask).sum() / (mask.sum() + eps)


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
    ):
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.main_loss_type = main_loss_type
        self.focal_alpha = focal_alpha
        self.focal_gamma = focal_gamma

    def _binary_loss(self, pred, gt):
        if self.main_loss_type == "DiceFocalLoss":
            mask = gt["shrink_mask"]
            target = gt["shrink_map"]
            dice = _dice_loss(pred, target, mask)
            focal = _focal_loss(pred, target, mask,
                                self.focal_alpha, self.focal_gamma)
            return 0.5 * dice + 0.5 * focal
        return F.binary_cross_entropy(pred, gt["shrink_map"], reduction="mean")

    def forward(self, pred, gt):
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
        thresh_loss = F.smooth_l1_loss(
            thresh_pred * thresh_mask, thresh_target * thresh_mask, reduction="mean"
        )
        binary_loss = self._binary_loss(binary_pred, gt)
        return self.alpha * shrink_loss + self.beta * thresh_loss + binary_loss
