"""LightSVTR neck（PP-OCRv6 small/medium rec 的 CTCHead neck，自研实现）。

对齐 PaddleOCR ``ppocr/modeling/necks/rnn.py`` 的 ``EncoderWithLightSVTR``：
``conv_reduce``（1x1 降维）→ ``local_conv``（DWConv [1, local_kernel] 局部增强）→
``svtr_block``（N × SVTR Block，全局注意力 + MLP，prenorm=False）→ ``norm``
（LayerNorm）→ 与 ``skip_conv`` 残差相加。

模块参数命名逐层对齐官方（``conv_reduce``/``skip_conv``/``local_conv``/
``svtr_block``/``norm``，Block 内 ``norm1``/``mixer.qkv``/``mixer.proj``/
``norm2``/``mlp.fc1``/``mlp.fc2``），保证后续权重转换器可按语义名映射官方
PaddleX .pdparams（``head.ctc_encoder.encoder.*`` → 自研 ``head.ctc_neck.*``）。

- 输入 [B, W, C] token 序列（MultiHead 已把 backbone [B, C, 1, W] reshape 成
  [B, W, C]），输出 [B, W, dims]，随后由 Linear 映射到 CTC 字符类别。
- small: dims=120, depth=2, mlp_ratio=2.0, local_kernel=7
- medium: dims=192, depth=2, mlp_ratio=4.0, local_kernel=7
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


class DropPath(nn.Module):
    """Stochastic Depth（每样本，作用于残差主路）。对齐官方 DropPath。"""

    def __init__(self, drop_prob=0.0):
        super().__init__()
        self.drop_prob = drop_prob

    def forward(self, x):
        if self.drop_prob == 0.0 or not self.training:
            return x
        keep_prob = 1.0 - self.drop_prob
        shape = (x.shape[0],) + (1,) * (x.ndim - 1)
        random_tensor = keep_prob + torch.rand(shape, dtype=x.dtype, device=x.device)
        random_tensor = torch.floor(random_tensor)
        return x.div(keep_prob) * random_tensor


class Identity(nn.Module):
    def forward(self, x):
        return x


class Mlp(nn.Module):
    """两层 MLP，参数名 fc1/fc2 对齐官方。激活层（SiLU/Swish）无参数。"""

    def __init__(self, in_features, hidden_features=None, out_features=None,
                 act_layer=nn.SiLU, drop=0.0):
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)

    def forward(self, x):
        x = self.fc1(x)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x


class ConvMixer(nn.Module):
    """局部卷积混合器（SVTR Local/Conv mixer）。lightsvtr 用 Global 注意力，
    本类保留用于对齐官方 Block 结构。"""

    def __init__(self, dim, num_heads=8, HW=None, local_k=(3, 3)):
        super().__init__()
        self.HW = HW
        self.dim = dim
        self.local_mixer = nn.Conv2d(
            dim, dim, local_k, 1, [local_k[0] // 2, local_k[1] // 2], groups=num_heads
        )

    def forward(self, x):
        B, N, C = x.shape
        h, w = self.HW
        x = x.transpose(1, 2).reshape(B, self.dim, h, w)
        x = self.local_mixer(x)
        x = x.flatten(2).transpose(1, 2)
        return x


class Attention(nn.Module):
    """多头自注意力（对齐 SVTRNet Attention）。

    qkv 由单一 Linear 生成（dim → 3*dim），Global 模式即标准多头自注意力。
    """

    def __init__(self, dim, num_heads=8, mixer="Global", HW=None, local_k=(7, 11),
                 qkv_bias=False, qk_scale=None, attn_drop=0.0, proj_drop=0.0):
        super().__init__()
        self.num_heads = num_heads
        self.dim = dim
        self.head_dim = dim // num_heads
        self.scale = qk_scale or self.head_dim**-0.5

        self.qkv = nn.Linear(dim, dim * 3, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)
        self.HW = HW
        self.mixer = mixer
        if mixer == "Local" and HW is not None:
            h, w = HW[0], HW[1]
            mask = torch.ones([h * w, h + local_k[0] - 1, w + local_k[1] - 1])
            for hi in range(h):
                for wi in range(w):
                    mask[hi * w + wi, hi:hi + local_k[0], wi:wi + local_k[1]] = 0.0
            mask = mask[:, local_k[0] // 2:h + local_k[0] // 2,
                        local_k[1] // 2:w + local_k[1] // 2].flatten(1)
            mask_inf = torch.full([h * w, h * w], float("-inf"))
            mask = torch.where(mask < 1, mask, mask_inf)
            self.register_buffer("mask", mask.unsqueeze(0).unsqueeze(1))

    def forward(self, x):
        # x: [B, N, C]
        B, N, C = x.shape
        qkv = (
            self.qkv(x)
            .reshape(B, N, 3, self.num_heads, self.head_dim)
            .permute(2, 0, 3, 1, 4)
        )
        q, k, v = qkv[0] * self.scale, qkv[1], qkv[2]
        attn = q @ k.transpose(-2, -1)
        if self.mixer == "Local":
            attn = attn + self.mask
        attn = F.softmax(attn, dim=-1)
        attn = self.attn_drop(attn)
        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        return x


class Block(nn.Module):
    """SVTR Transformer Block（对齐官方 SVTRNet Block；lightsvtr 用 prenorm=False）。"""

    def __init__(self, dim, num_heads, mixer="Global", local_mixer=(7, 11), HW=None,
                 mlp_ratio=4.0, qkv_bias=False, qk_scale=None, drop=0.0,
                 attn_drop=0.0, drop_path=0.0, act_layer=nn.SiLU,
                 norm_layer=nn.LayerNorm, epsilon=1e-5, prenorm=True):
        super().__init__()
        self.norm1 = norm_layer(dim, eps=epsilon)
        if mixer in ("Global", "Local"):
            self.mixer = Attention(
                dim, num_heads=num_heads, mixer=mixer, HW=HW, local_k=local_mixer,
                qkv_bias=qkv_bias, qk_scale=qk_scale, attn_drop=attn_drop,
                proj_drop=drop,
            )
        elif mixer == "Conv":
            self.mixer = ConvMixer(dim, num_heads=num_heads, HW=HW, local_k=local_mixer)
        else:
            raise TypeError("mixer 必须为 Global/Local/Conv")
        self.drop_path = DropPath(drop_path) if drop_path > 0.0 else Identity()
        self.norm2 = norm_layer(dim, eps=epsilon)
        mlp_hidden_dim = int(dim * mlp_ratio)
        self.mlp_ratio = mlp_ratio
        self.mlp = Mlp(in_features=dim, hidden_features=mlp_hidden_dim,
                       act_layer=act_layer, drop=drop)
        self.prenorm = prenorm

    def forward(self, x):
        if self.prenorm:
            x = self.norm1(x + self.drop_path(self.mixer(x)))
            x = self.norm2(x + self.drop_path(self.mlp(x)))
        else:
            x = x + self.drop_path(self.mixer(self.norm1(x)))
            x = x + self.drop_path(self.mlp(self.norm2(x)))
        return x


class ConvBNLayer(nn.Module):
    """Conv + BN + 激活（对齐官方 ConvBNLayer）。lightsvtr 只用到 1x1 卷积。"""

    def __init__(self, in_channels, out_channels, kernel_size=1, act=nn.SiLU):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size,
                              padding=kernel_size // 2, bias=False)
        self.norm = nn.BatchNorm2d(out_channels)
        self.act = act()

    def forward(self, x):
        return self.act(self.norm(self.conv(x)))


class LightSVTR(nn.Module):
    """LightSVTR neck（PP-OCRv6 small/medium rec 的 CTCHead neck）。

    结构对齐 PaddleOCR ``EncoderWithLightSVTR``：``conv_reduce`` 1x1 降维 →
    ``local_conv`` DWConv 局部增强 → ``svtr_block`` N × Block（全局注意力 +
    MLP，prenorm=False）→ ``norm`` LayerNorm → ``skip_conv`` 残差相加。

    输入 [B, W, C]，输出 [B, W, dims]。
    """

    def __init__(self, in_channels, out_channels=None, dims=64, depth=2,
                 num_heads=8, qkv_bias=True, mlp_ratio=2.0, drop_rate=0.1,
                 attn_drop_rate=0.1, drop_path=0.0, qk_scale=None,
                 local_kernel=7, use_guide=False, **kwargs):
        super().__init__()
        self.in_channels = in_channels
        self.use_guide = use_guide
        self.conv_reduce = ConvBNLayer(in_channels, dims, kernel_size=1, act=nn.SiLU)
        self.local_conv = nn.Sequential(
            nn.Conv2d(dims, dims, (1, local_kernel), padding=(0, local_kernel // 2),
                      groups=dims, bias=False),
            nn.BatchNorm2d(dims),
            nn.SiLU(),
        )
        self.svtr_block = nn.ModuleList([
            Block(dim=dims, num_heads=num_heads, mixer="Global", HW=None,
                  mlp_ratio=mlp_ratio, qkv_bias=qkv_bias, qk_scale=qk_scale,
                  drop=drop_rate, act_layer=nn.SiLU, attn_drop=attn_drop_rate,
                  drop_path=drop_path, norm_layer=nn.LayerNorm, epsilon=1e-5,
                  prenorm=False)
            for _ in range(depth)
        ])
        self.norm = nn.LayerNorm(dims, eps=1e-6)
        self.skip_conv = ConvBNLayer(in_channels, dims, kernel_size=1, act=nn.SiLU)
        self.out_channels = dims
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            nn.init.trunc_normal_(m.weight, mean=0.0, std=0.02)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.LayerNorm):
            nn.init.zeros_(m.bias)
            nn.init.ones_(m.weight)

    def forward(self, x):
        # x: [B, W, C]
        if self.use_guide:
            x = x.detach()
        x4 = x.permute(0, 2, 1).unsqueeze(2)  # [B, C, 1, W]
        skip = self.skip_conv(x4)  # [B, dims, 1, W]
        z = self.conv_reduce(x4)  # [B, dims, 1, W]
        z = z + self.local_conv(z)  # [B, dims, 1, W]
        B, C_, H, W = z.shape
        z = z.flatten(2).transpose(1, 2)  # [B, W, dims]
        for blk in self.svtr_block:
            z = blk(z)
        z = self.norm(z)
        z = z.transpose(1, 2).reshape(B, C_, H, W)  # [B, dims, 1, W]
        z = z + skip
        z = z.reshape(B, C_, H * W).transpose(1, 2)  # [B, W, dims]
        return z
