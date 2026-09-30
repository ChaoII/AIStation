"""训练 / 评估 / 预测 / 部署的工作目录解析。

⚠️ 这些目录**不只是本项目自己用**。TorchKiln 训练服务、以及本项目为
paddlex / ultralytics 起的训练容器，都要**读写或挂载同一批路径**：
标注导出的数据目录（容器里当 ``/data``）、``train.log`` / ``eval.log``
（容器往里写、本项目 tail 出来转成 SSE）。因此两侧算出的路径必须**逐字相同**，
否则会静默失败：

- 路径对不上 -> 容器里 ``open(train.txt)`` 报 FileNotFoundError，
  而本项目只看到「训练失败」，看不出是路径问题；
- 日志路径对不上 -> 本项目 tail 不到文件，训练在跑但页面永远没有新日志。

同一台机器上、后端与训练服务都跑在宿主时，两边都是系统临时目录，恰好一致；
一旦后端进了容器、或训练服务在另一台机器，就必须显式声明共享根目录——
这正是 ``TORKILN_SHARED_DATA_ROOT`` 的用途。未配置时退回系统临时目录，
**行为与之前完全一致**，所以配置它是纯增量、不配置也不改变任何现状。
"""
import os
import tempfile

from app.config.setting import settings


def shared_root() -> str:
    """训练链路的共享根目录。

    优先 ``TORKILN_SHARED_DATA_ROOT``（显式声明，两侧都按它算）；
    未配置时退回系统临时目录——这依赖「后端与训练服务同机同用户」的隐含前提，
    换机器就会错位，所以那种部署方式下必须配置。
    """
    configured = (settings.TORKILN_SHARED_DATA_ROOT or "").strip()
    return configured or tempfile.gettempdir()


def work_dir(kind: str, *parts: object) -> str:
    """``work_dir("train_output", 123)`` -> 共享根下的 ``train_output/123``。

    ``kind`` 是顶层子目录名（``train_output`` / ``eval_output`` /
    ``predict_output`` / ``deploy_output`` / ``model_export`` /
    ``dataset_export`` 等），与 :mod:`cleanup` 清理的前缀一一对应。

    加新类型时注意：``cleanup._running_ids`` 只登记了 4 个前缀（train / eval /
    predict / deploy），其余前缀下**运行中**的任务目录不会被跳过——实际靠
    cleanup 的「7 天 mtime cutoff」兜底（活跃目录 mtime 是当下，不会被删），
    但想要更强的保护就得同步那张表。
    """
    return os.path.join(shared_root(), kind, *[str(p) for p in parts])
