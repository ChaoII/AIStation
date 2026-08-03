"""NRTRHead（Transformer 解码器，自研，对齐 frotms/PaddleOCR2Pytorch rec_nrtr_head.py）。

NRTRHead 是完整的 Transformer 解码器：
- 输入投影 Linear(in_channels -> nrtr_dim)（对应参考 MultiHead 的 before_gtc/FCTranspose）；
- Embeddings（词表 = num_classes）+ 正弦位置编码；
- ``num_decoder_layers`` 层 TransformerDecoderLayer（self-attn + cross-attn + FFN）；
- 输出投影 ``tgt_word_prj``（Linear，无 bias）→ logits [B, max_text_length, num_classes]。

层结构 / 参数命名与参考逐层对齐（QKV 用 1x1 Conv2d conv1/conv2/conv3，
FFN 用 1x1 Conv2d conv1/conv2），保证权重转换器（位置对应法）可按序映射。

- 训练：teacher forcing（输入 = [SOS] + label_gtc[:-1]，pad token = 0），
  输出 logits [B, max_text_length, num_classes]。
- 推理：贪心自回归解码，逐位置收集 logits，输出 [B, max_text_length, num_classes]。
"""
import math
from copy import deepcopy

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.init import xavier_normal_, xavier_uniform_

SOS_TOKEN = 2
EOS_TOKEN = 3


# ---------------------------------------------------------------------------
# MultiheadAttention（QKV 用 1x1 Conv2d 投影，对齐参考 multiheadAttention.py）
# ---------------------------------------------------------------------------


class MultiheadAttention(nn.Module):
    """多头注意力。

    参数结构与参考 ``multiheadAttention.py`` 一致：
    ``out_proj``（Linear）+ ``conv1/conv2/conv3``（Q/K/V 的 1x1 Conv2d 投影）。
    """

    def __init__(self, embed_dim, num_heads, dropout=0.0, bias=True):
        super().__init__()
        assert embed_dim % num_heads == 0, "embed_dim must be divisible by num_heads"
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.dropout = dropout
        self.head_dim = embed_dim // num_heads
        self.scaling = self.head_dim**-0.5
        self.out_proj = nn.Linear(embed_dim, embed_dim, bias=bias)
        self.conv1 = nn.Conv2d(embed_dim, embed_dim, (1, 1))
        self.conv2 = nn.Conv2d(embed_dim, embed_dim, (1, 1))
        self.conv3 = nn.Conv2d(embed_dim, embed_dim, (1, 1))
        xavier_uniform_(self.out_proj.weight)

    def _in_proj(self, x, conv):
        # x: [T, B, E] -> [B, E, T] -> [B, E, 1, T] -> conv -> [T, B, E]
        x = x.permute(1, 2, 0)
        x = torch.unsqueeze(x, 2)
        x = conv(x)
        x = torch.squeeze(x, 2)
        x = x.permute(2, 0, 1)
        return x

    def forward(self, query, key, value, attn_mask=None, key_padding_mask=None):
        # query/key/value: [T, B, embed_dim]
        q_shape = query.shape
        src_shape = key.shape
        q = self._in_proj(query, self.conv1) * self.scaling
        k = self._in_proj(key, self.conv2)
        v = self._in_proj(value, self.conv3)

        def _heads(x, length):
            return x.reshape(length, q_shape[1], self.num_heads, self.head_dim).permute(
                1, 2, 0, 3
            )

        q = _heads(q, q_shape[0])  # [B, heads, T, head_dim]
        k = _heads(k, src_shape[0])  # [B, heads, S, head_dim]
        v = _heads(v, src_shape[0])  # [B, heads, S, head_dim]

        attn = torch.matmul(q, k.transpose(-1, -2))  # [B, heads, T, S]
        if attn_mask is not None:
            attn = attn + attn_mask.unsqueeze(0).unsqueeze(0)
        if key_padding_mask is not None:
            # key_padding_mask: [B, S] bool（True=padding）-> [B, 1, 1, S]
            attn = attn.masked_fill(
                key_padding_mask.unsqueeze(1).unsqueeze(2), float("-inf")
            )
        attn = F.softmax(attn, dim=-1)
        attn = F.dropout(attn, p=self.dropout, training=self.training)
        out = torch.matmul(attn, v)  # [B, heads, T, head_dim]
        out = out.permute(2, 0, 1, 3).reshape(q_shape[0], q_shape[1], self.embed_dim)
        return self.out_proj(out)


# ---------------------------------------------------------------------------
# Embeddings / PositionalEncoding
# ---------------------------------------------------------------------------


class Embeddings(nn.Module):
    def __init__(self, d_model, vocab, padding_idx=0, scale_embedding=True):
        super().__init__()
        self.embedding = nn.Embedding(vocab, d_model, padding_idx=padding_idx)
        w0 = torch.normal(0.0, d_model**-0.5, (vocab, d_model))
        self.embedding.weight.data.copy_(w0)
        self.d_model = d_model
        self.scale_embedding = scale_embedding

    def forward(self, x):
        x = self.embedding(x)
        if self.scale_embedding:
            x = x * math.sqrt(self.d_model)
        return x


class PositionalEncoding(nn.Module):
    def __init__(self, dropout, dim, max_len=5000):
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        pe = torch.zeros(max_len, dim)
        position = torch.arange(0, max_len, dtype=torch.float32).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, dim, 2).float() * (-math.log(10000.0) / dim)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).permute(1, 0, 2)  # [max_len, 1, dim]
        # 非持久 buffer：Paddle 的位置编码在 forward 内动态生成（无对应参数），
        # 保持非持久可避免出现在 state_dict 中破坏权重转换器的位置对应。
        self.register_buffer("pe", pe, persistent=False)

    def forward(self, x):
        # x: [T, B, dim]
        x = x + self.pe[: x.shape[0]]
        return self.dropout(x)


# ---------------------------------------------------------------------------
# TransformerEncoder / Decoder 层
# ---------------------------------------------------------------------------


class TransformerEncoderLayer(nn.Module):
    def __init__(
        self,
        d_model,
        nhead,
        dim_feedforward=2048,
        attention_dropout_rate=0.0,
        residual_dropout_rate=0.1,
    ):
        super().__init__()
        self.self_attn = MultiheadAttention(d_model, nhead, dropout=attention_dropout_rate)
        self.conv1 = nn.Conv2d(d_model, dim_feedforward, (1, 1))
        self.conv2 = nn.Conv2d(dim_feedforward, d_model, (1, 1))
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout1 = nn.Dropout(residual_dropout_rate)
        self.dropout2 = nn.Dropout(residual_dropout_rate)

    def forward(self, src, src_mask=None, src_key_padding_mask=None):
        src2 = self.self_attn(
            src, src, src, attn_mask=src_mask, key_padding_mask=src_key_padding_mask
        )
        src = self.norm1(src + self.dropout1(src2))

        src = src.permute(1, 2, 0).unsqueeze(2)  # [B, E, 1, T]
        src2 = self.conv2(F.relu(self.conv1(src)))
        src2 = src2.squeeze(2).permute(2, 0, 1)  # [T, B, E]
        src = src.squeeze(2).permute(2, 0, 1)  # [T, B, E]
        src = self.norm2(src + self.dropout2(src2))
        return src


class TransformerEncoder(nn.Module):
    def __init__(self, encoder_layer, num_layers):
        super().__init__()
        self.layers = nn.ModuleList([deepcopy(encoder_layer) for _ in range(num_layers)])
        self.num_layers = num_layers

    def forward(self, src):
        output = src
        for layer in self.layers:
            output = layer(output, src_mask=None, src_key_padding_mask=None)
        return output


class TransformerDecoderLayer(nn.Module):
    def __init__(
        self,
        d_model,
        nhead,
        dim_feedforward=2048,
        attention_dropout_rate=0.0,
        residual_dropout_rate=0.1,
    ):
        super().__init__()
        self.self_attn = MultiheadAttention(d_model, nhead, dropout=attention_dropout_rate)
        self.multihead_attn = MultiheadAttention(
            d_model, nhead, dropout=attention_dropout_rate
        )
        self.conv1 = nn.Conv2d(d_model, dim_feedforward, (1, 1))
        self.conv2 = nn.Conv2d(dim_feedforward, d_model, (1, 1))
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.norm3 = nn.LayerNorm(d_model)
        self.dropout1 = nn.Dropout(residual_dropout_rate)
        self.dropout2 = nn.Dropout(residual_dropout_rate)
        self.dropout3 = nn.Dropout(residual_dropout_rate)

    def forward(
        self,
        tgt,
        memory,
        tgt_mask=None,
        memory_mask=None,
        tgt_key_padding_mask=None,
        memory_key_padding_mask=None,
    ):
        tgt2 = self.self_attn(
            tgt, tgt, tgt, attn_mask=tgt_mask, key_padding_mask=tgt_key_padding_mask
        )
        tgt = self.norm1(tgt + self.dropout1(tgt2))
        tgt2 = self.multihead_attn(
            tgt,
            memory,
            memory,
            attn_mask=memory_mask,
            key_padding_mask=memory_key_padding_mask,
        )
        tgt = self.norm2(tgt + self.dropout2(tgt2))

        tgt = tgt.permute(1, 2, 0).unsqueeze(2)  # [B, E, 1, T]
        tgt2 = self.conv2(F.relu(self.conv1(tgt)))
        tgt2 = tgt2.squeeze(2).permute(2, 0, 1)  # [T, B, E]
        tgt = tgt.squeeze(2).permute(2, 0, 1)  # [T, B, E]
        tgt = self.norm3(tgt + self.dropout3(tgt2))
        return tgt


class TransformerDecoder(nn.Module):
    def __init__(self, decoder_layer, num_layers):
        super().__init__()
        self.layers = nn.ModuleList([deepcopy(decoder_layer) for _ in range(num_layers)])
        self.num_layers = num_layers

    def forward(
        self,
        tgt,
        memory,
        tgt_mask=None,
        memory_mask=None,
        tgt_key_padding_mask=None,
        memory_key_padding_mask=None,
    ):
        output = tgt
        for layer in self.layers:
            output = layer(
                output,
                memory,
                tgt_mask=tgt_mask,
                memory_mask=memory_mask,
                tgt_key_padding_mask=tgt_key_padding_mask,
                memory_key_padding_mask=memory_key_padding_mask,
            )
        return output


# ---------------------------------------------------------------------------
# Transformer（decoder-only，encoder 可选）
# ---------------------------------------------------------------------------


class Transformer(nn.Module):
    """NRTR Transformer。默认 decoder-only（num_encoder_layers <= 0）。

    结构与参考 ``rec_nrtr_head.py`` 的 ``Transformer`` 一致：
    ``embedding`` / ``positional_encoding`` / ``decoder`` / ``tgt_word_prj``。
    """

    def __init__(
        self,
        d_model=384,
        nhead=12,
        num_encoder_layers=-1,
        beam_size=-1,
        num_decoder_layers=4,
        max_len=25,
        dim_feedforward=1536,
        attention_dropout_rate=0.0,
        residual_dropout_rate=0.1,
        out_channels=6625,
        scale_embedding=True,
    ):
        super().__init__()
        self.out_channels = out_channels
        self.max_len = max_len
        self.beam_size = beam_size
        self.d_model = d_model
        self.nhead = nhead

        self.embedding = Embeddings(
            d_model=d_model,
            vocab=out_channels,
            padding_idx=0,
            scale_embedding=scale_embedding,
        )
        self.positional_encoding = PositionalEncoding(
            dropout=residual_dropout_rate, dim=d_model
        )
        if num_encoder_layers > 0:
            encoder_layer = TransformerEncoderLayer(
                d_model, nhead, dim_feedforward, attention_dropout_rate,
                residual_dropout_rate,
            )
            self.encoder = TransformerEncoder(encoder_layer, num_encoder_layers)
        else:
            self.encoder = None
        decoder_layer = TransformerDecoderLayer(
            d_model, nhead, dim_feedforward, attention_dropout_rate,
            residual_dropout_rate,
        )
        self.decoder = TransformerDecoder(decoder_layer, num_decoder_layers)

        self._reset_parameters()

        self.tgt_word_prj = nn.Linear(d_model, out_channels, bias=False)
        w0 = torch.normal(0.0, d_model**-0.5, (out_channels, d_model))
        self.tgt_word_prj.weight.data.copy_(w0)
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Conv2d):
            xavier_normal_(m.weight)
            if m.bias is not None:
                torch.nn.init.zeros_(m.bias)

    def _reset_parameters(self):
        for p in self.parameters():
            if p.dim() > 1:
                xavier_uniform_(p)

    def generate_square_subsequent_mask(self, sz, device=None):
        mask = torch.triu(
            torch.full((sz, sz), float("-inf"), dtype=torch.float32, device=device),
            diagonal=1,
        )
        return mask

    def generate_padding_mask(self, x):
        return x == torch.tensor(0, dtype=x.dtype, device=x.device)

    def forward_train(self, src, label_gtc):
        # src: [B, W, d_model]；label_gtc: [B, max_len] long，0=pad，无 SOS/EOS
        batch_size, max_len = label_gtc.shape
        sos = torch.full(
            (batch_size, 1), SOS_TOKEN, dtype=torch.long, device=label_gtc.device
        )
        tgt_in = torch.cat([sos, label_gtc[:, :-1]], dim=1)  # [B, max_len]
        tgt_padding_mask = self.generate_padding_mask(tgt_in)  # [B, max_len]

        tgt = self.embedding(tgt_in).permute(1, 0, 2)  # [max_len, B, d_model]
        tgt = self.positional_encoding(tgt)
        tgt_mask = self.generate_square_subsequent_mask(tgt.shape[0], tgt.device)

        if self.encoder is not None:
            src = self.positional_encoding(src.permute(1, 0, 2))
            memory = self.encoder(src)
        else:
            memory = src.permute(1, 0, 2)  # [W, B, d_model]

        output = self.decoder(
            tgt,
            memory,
            tgt_mask=tgt_mask,
            memory_mask=None,
            tgt_key_padding_mask=tgt_padding_mask,
            memory_key_padding_mask=None,
        )
        output = output.permute(1, 0, 2)  # [B, max_len, d_model]
        logit = self.tgt_word_prj(output)  # [B, max_len, out_channels]
        return logit

    def forward_test(self, src):
        # src: [B, W, d_model] -> 贪心解码，返回逐位置 logits [B, max_len, out_channels]
        batch_size = src.shape[0]
        if self.encoder is not None:
            src = self.positional_encoding(src.permute(1, 0, 2))
            memory = self.encoder(src)
        else:
            memory = src.permute(1, 0, 2)  # [W, B, d_model]

        dec_seq = torch.full(
            (batch_size, 1), SOS_TOKEN, dtype=torch.int64, device=src.device
        )
        logits = []
        for _ in range(self.max_len):
            dec_embed = self.embedding(dec_seq).permute(1, 0, 2)
            dec_embed = self.positional_encoding(dec_embed)
            tgt_mask = self.generate_square_subsequent_mask(
                dec_embed.shape[0], dec_embed.device
            )
            output = self.decoder(
                dec_embed,
                memory,
                tgt_mask=tgt_mask,
                memory_mask=None,
                tgt_key_padding_mask=None,
                memory_key_padding_mask=None,
            )
            output = output.permute(1, 0, 2)  # [B, T, d_model]
            step_logits = self.tgt_word_prj(output[:, -1, :])  # [B, out_channels]
            logits.append(step_logits)
            preds_idx = step_logits.argmax(dim=1).unsqueeze(1)  # [B, 1]
            dec_seq = torch.cat([dec_seq, preds_idx], dim=1)
        return torch.stack(logits, dim=1)  # [B, max_len, out_channels]

    def forward(self, src, targets=None):
        if self.training:
            if targets is None:
                raise ValueError("NRTRHead 训练需要 targets（label_gtc: [B, max_len]）")
            if isinstance(targets, dict):
                targets = targets["label_gtc"]
            return self.forward_train(src, targets)
        return self.forward_test(src)


# ---------------------------------------------------------------------------
# NRTRHead（头部包装）
# ---------------------------------------------------------------------------


class NRTRHead(nn.Module):
    """NRTR 识别头：输入投影 + Transformer 解码器。

    参数：
        in_channels: 骨干输出通道数（rec 模式 backbone.out_channels）。
        out_channels: 字符类别数（含 blank）。
        nrtr_dim: Transformer 模型维度（tiny_rec.yml = 384）。
        max_text_length: 最大文本长度（默认 25）。
    """

    def __init__(
        self,
        in_channels,
        out_channels,
        nrtr_dim=384,
        max_text_length=25,
        num_decoder_layers=4,
        nhead=None,
        dim_feedforward=None,
        dropout=0.1,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.nrtr_dim = nrtr_dim
        self.max_text_length = max_text_length
        # 输入投影（对应参考 MultiHead 的 before_gtc / FCTranspose，bias=False）
        self.linear = nn.Linear(in_channels, nrtr_dim, bias=False)
        self.transformer = Transformer(
            d_model=nrtr_dim,
            nhead=nhead if nhead is not None else nrtr_dim // 32,
            num_encoder_layers=-1,
            beam_size=-1,
            num_decoder_layers=num_decoder_layers,
            max_len=max_text_length,
            dim_feedforward=dim_feedforward if dim_feedforward is not None else nrtr_dim * 4,
            out_channels=out_channels,
        )

    def forward(self, x, targets=None):
        # x: [B, W, C]（MultiHead 已 squeeze/permute）
        x = self.linear(x)  # [B, W, nrtr_dim]
        return self.transformer(x, targets)
