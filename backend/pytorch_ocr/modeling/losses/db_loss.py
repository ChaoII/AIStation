"""DBLoss（prob + thresh + binary，主损失 DiceFocal）。自研实现。"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def _dice_loss(pred, target, mask):
    """Dice loss，忽略 mask=0 区域。"""
    pred = pred * mask
    target = target * mask
    smooth = 1e-5
    intersect = torch.sum(pred * target)
    union = torch.sum(pred) + torch.sum(target)
    return 1 - (2 * intersect + smooth) / (union + smooth)


def _focal_loss(pred, target, alpha=0.25, gamma=2.5):
    """二分类 Focal loss。"""
    eps = 1e-6
    pt = torch.where(target > 0.5, pred, 1 - pred).clamp(eps, 1 - eps)
    weight = alpha * (1 - pt).pow(gamma)
    loss = F.binary_cross_entropy(pred, target, reduction="none")
    return (weight * loss).mean()


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
            focal = _focal_loss(pred, target, self.focal_alpha, self.focal_gamma)
            return 0.5 * dice + 0.5 * focal
        return F.binary_cross_entropy(pred, gt["shrink_map"], reduction="mean")

    def forward(self, pred, gt):
        # pred: (N, 3, H, W) = [shrink, thresh, binary]
        shrink_pred = pred[:, 0:1]
        thresh_pred = pred[:, 1:2]
        binary_pred = pred[:, 2:3]

        binary_loss = self._binary_loss(binary_pred, gt)
        thresh_mask = gt["threshold_mask"]
        thresh_target = gt["threshold_map"]
        thresh_loss = F.smooth_l1_loss(
            thresh_pred * thresh_mask, thresh_target * thresh_mask, reduction="mean"
        )
        prob_loss = F.binary_cross_entropy(shrink_pred, gt["shrink_map"], reduction="mean")
        return self.alpha * binary_loss + self.beta * thresh_loss + prob_loss
