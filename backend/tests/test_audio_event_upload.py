"""音频上传 service 单测：白名单校验、大小上限、ffprobe 探测、size_bytes、计数递增与失败清理。

仅 mock s3_client 与 db 会话，验证 AudioService.upload_audio 的核心行为。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.module_annotation.dataset import audio_service
from app.api.v1.module_annotation.dataset.audio_service import AudioService
from app.core.exceptions import CustomException


def _make_file(name, content, size=None):
    """构造一个模拟 UploadFile。"""
    f = AsyncMock()
    f.filename = name
    f.size = size if size is not None else len(content)
    f.read = AsyncMock(return_value=content)
    return f


def _make_db(dataset=None):
    """构造一个模拟 async db 会话。"""
    db = AsyncMock()
    db.get = AsyncMock(return_value=dataset)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _dataset():
    ds = MagicMock()
    ds.id = 7
    ds.is_deleted = False
    ds.audio_count = 0
    return ds


def _run(coro):
    return asyncio.run(coro)


def test_rejects_non_audio_extension():
    # 白名单外的扩展名（如 .exe）应直接拒绝，不写对象也不入库。
    db = _make_db(dataset=_dataset())
    file = _make_file("malware.exe", b"hello")
    with patch("app.api.v1.module_annotation.dataset.audio_service.s3_client") as s3, \
         patch("app.api.v1.module_annotation.dataset.audio_service._probe_audio") as probe:
        try:
            _run(AudioService.upload_audio(db, 7, file, auth=None))
        except CustomException as e:
            assert "不支持" in e.msg or "格式" in e.msg
        else:
            raise AssertionError("应抛出业务异常")
    s3.upload_fileobj.assert_not_called()
    probe.assert_not_called()
    db.add.assert_not_called()


def test_rejects_oversize_file():
    # 超过 100MB 应拒绝。
    db = _make_db(dataset=_dataset())
    file = _make_file("big.wav", b"x", size=100 * 1024 * 1024 + 1)
    with patch("app.api.v1.module_annotation.dataset.audio_service.s3_client") as s3:
        try:
            _run(AudioService.upload_audio(db, 7, file, auth=None))
        except CustomException as e:
            assert "过大" in e.msg
        else:
            raise AssertionError("应抛出业务异常")
    s3.upload_fileobj.assert_not_called()


def test_probe_audio_parses_fields():
    # 音频流字段应被正确解析：duration/sample_rate/channels/bitrate（kbps）。
    with patch("app.api.v1.module_annotation.dataset.audio_service._run_ffprobe",
               return_value={
                   "streams": [{
                       "codec_type": "audio",
                       "sample_rate": "44100",
                       "channels": 2,
                       "bit_rate": "320000",
                   }],
                   "format": {"duration": "12.5"},
               }):
        info = audio_service._probe_audio("demo.wav")
    assert info["duration"] == 12.5
    assert info["sample_rate"] == 44100
    assert info["channels"] == 2
    assert info["bitrate"] == 320  # 320000 bps -> 320 kbps


def test_probe_audio_guards_missing_stream_and_null_bitrate():
    # 缺失音频流或 bit_rate 为空时，应回退默认值且 bitrate 为 None。
    with patch("app.api.v1.module_annotation.dataset.audio_service._run_ffprobe",
               return_value={"streams": [], "format": {}}):
        info = audio_service._probe_audio("empty.wav")
    assert info["duration"] == 0.0
    assert info["sample_rate"] == 0
    assert info["channels"] == 0
    assert info["bitrate"] is None

    with patch("app.api.v1.module_annotation.dataset.audio_service._run_ffprobe",
               return_value={
                   "streams": [{"codec_type": "audio", "sample_rate": "8000", "channels": 1}],
                   "format": {"duration": "3"},
               }):
        info = audio_service._probe_audio("no-bitrate.wav")
    assert info["sample_rate"] == 8000
    assert info["bitrate"] is None


def test_probe_audio_raises_on_bad_rs():
    # ffprobe 失败（_run_ffprobe 抛错）时, _probe_audio 应向上抛。
    with patch("app.api.v1.module_annotation.dataset.audio_service._run_ffprobe",
               side_effect=ValueError("ffprobe 探测失败")):
        try:
            audio_service._probe_audio("bad.wav")
        except ValueError:
            return
        raise AssertionError("应抛出探测异常")


def test_upload_populates_model_and_increments_count():
    # 白名单内音频：应上传对象、写入模型（含 size_bytes/元数据）并递增 audio_count。
    db = _make_db(dataset=_dataset())
    content = b"\x00\x01" * 10
    file = _make_file("demo.wav", content)
    probe = {
        "duration": 5.0,
        "sample_rate": 44100,
        "channels": 2,
        "bitrate": 128,
    }
    ds = db.get.return_value
    with patch("app.api.v1.module_annotation.dataset.audio_service.s3_client") as s3, \
         patch("app.api.v1.module_annotation.dataset.audio_service._probe_audio",
               return_value=probe):
        audio = _run(AudioService.upload_audio(db, 7, file, auth=None))
    assert audio.object_key.startswith("datasets/7/audios/")
    assert audio.object_key.endswith(".wav")
    assert audio.size_bytes == len(content)
    assert audio.duration == 5.0
    assert audio.sample_rate == 44100
    assert audio.channels == 2
    assert audio.bitrate == 128
    assert audio.name == "demo.wav"
    s3.upload_fileobj.assert_called_once()
    # 上传的字节流内容应与原始一致
    uploaded = s3.upload_fileobj.call_args[0][0]
    assert uploaded.getvalue() == content
    db.add.assert_called()
    # audio_count 递增
    assert ds.audio_count == 1


def test_failure_cleans_up_uploaded_object():
    # 入库失败（flush 抛错）时，应删除已上传对象并重新抛错。
    db = _make_db(dataset=_dataset())
    db.flush = AsyncMock(side_effect=RuntimeError("db boom"))
    file = _make_file("demo.wav", b"\x00" * 16)
    with patch("app.api.v1.module_annotation.dataset.audio_service.s3_client") as s3, \
         patch("app.api.v1.module_annotation.dataset.audio_service._probe_audio",
               return_value={"duration": 1.0, "sample_rate": 8000,
                             "channels": 1, "bitrate": None}):
        try:
            _run(AudioService.upload_audio(db, 7, file, auth=None))
        except RuntimeError:
            pass
        else:
            raise AssertionError("应重新抛出入库异常")
    s3.delete_object.assert_called()
