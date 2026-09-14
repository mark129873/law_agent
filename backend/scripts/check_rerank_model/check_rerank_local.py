"""下载并验证项目统一使用的本地 Reranker 模型。

这个脚本与生产配置共享同一个 Hugging Face 模型标识：首次运行时下载到
仓库根目录的 ``.model``，然后从该目录加载 CrossEncoder 做最小推理验证。
这样既能在启动服务前提前发现模型文件或依赖问题，也能让离线启动直接复用
已经下载的本地目录。
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from huggingface_hub import snapshot_download
from sentence_transformers import CrossEncoder


# 该值必须与 app.config.settings.Settings 的默认配置保持一致，避免脚本验证
# 的模型和实际服务加载的模型不一致。模型目录故意放在仓库内但被 Git 忽略的目录中，
# 防止几十到几百 MB 的权重文件进入 Git 提交。
MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
MODEL_DEVICE = "cpu"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = PROJECT_ROOT / ".model" / Path(MODEL_NAME)


def ensure_model_downloaded() -> Path:
    """确保本地模型目录完整，并返回可供 CrossEncoder 加载的路径。"""

    # 只判断目录存在会把中断下载留下的空目录误认为已完成；config.json
    # 是 CrossEncoder 加载模型时必需的清单文件，用它作为最小完整性检查。
    config_file = MODEL_DIR / "config.json"
    if not config_file.is_file():
        print(f"正在下载 Reranker 模型：{MODEL_NAME}")
        snapshot_download(repo_id=MODEL_NAME, local_dir=str(MODEL_DIR))
        print(f"模型已下载到：{MODEL_DIR}")
    else:
        print(f"复用本地 Reranker 模型：{MODEL_DIR}")
    return MODEL_DIR


def main() -> None:
    """下载、加载并执行三条样本打分，输出耗时与分数供人工确认。"""

    total_start = perf_counter()
    model_dir = ensure_model_downloaded()

    load_start = perf_counter()
    reranker = CrossEncoder(str(model_dir), device=MODEL_DEVICE)
    print(f"模型加载耗时：{perf_counter() - load_start:.4f} 秒")

    query = "Transformer 的机制是什么？"
    documents = [
        "BERT采用双向预训练，使用masked language model。",
        "Transformer 的核心是自注意力机制，可以建模长距离token之间的依赖关系。",
        "ResNet使用残差连接解决深度网络梯度消失。",
    ]

    inference_start = perf_counter()
    scores = reranker.predict(
        [(query, document) for document in documents],
        batch_size=16,
    )

    print("模型名称：", MODEL_NAME)
    print("设备：", MODEL_DEVICE)
    print("Scores:", scores)
    print(f"模型推理耗时：{perf_counter() - inference_start:.4f} 秒")
    print(f"总耗时：{perf_counter() - total_start:.4f} 秒")


if __name__ == "__main__":
    main()
