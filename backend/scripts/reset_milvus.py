"""干净环境重置脚本：删除 Milvus 中的知识库集合（RELIABILITY.md，BE-029）。

为什么需要单独重置：向量数据由 Milvus Cloud 或 standalone 持久化，
不在 backend/data/ 目录内——按 RELIABILITY.md 做"测试干净环境管理"时，
除删除 backend/data/ 外还需删除知识库集合。

用法：本地 standalone 执行 `uv run python scripts/reset_milvus.py`；
云端执行 `uv run python scripts/reset_milvus.py --yes`。
脚本幂等：集合不存在时直接成功。
"""
import argparse
import os
import sys

# 脚本直跑时 sys.path 只有 scripts/，手动加入 backend/ 才能导入 app 包
_BACKEND_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
os.chdir(_BACKEND_ROOT)
sys.path.insert(0, os.path.abspath(_BACKEND_ROOT))

from pymilvus import MilvusClient

from app.config.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="删除当前 Milvus 配置中的 law_chunks 集合")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="确认删除已认证 Milvus（包括 Milvus Cloud）中的集合",
    )
    args = parser.parse_args()

    settings = get_settings()
    if settings.milvus_token and not args.yes:
        raise SystemExit(
            "当前 Milvus 配置带有认证信息，可能是云端正式数据；"
            "确认目标后请使用 --yes。"
        )

    client_kwargs: dict[str, str] = {"uri": settings.milvus_uri}
    if settings.milvus_token:
        client_kwargs["token"] = settings.milvus_token
    client = MilvusClient(**client_kwargs)
    collection = settings.milvus_collection_name
    if client.has_collection(collection):
        client.drop_collection(collection)
        print(f"dropped collection: {collection}")
    else:
        print(f"collection not exists (nothing to do): {collection}")


if __name__ == "__main__":
    main()
