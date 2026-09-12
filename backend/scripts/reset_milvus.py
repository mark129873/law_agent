"""干净环境重置脚本：删除 Milvus 中的知识库集合（RELIABILITY.md，BE-029）。

为什么需要单独重置：BE-029 起向量数据由 Milvus 容器卷持久化，
不在 backend/data/ 目录内——按 RELIABILITY.md 做"测试干净环境
管理"时，除删除 backend/data/ 外还需删除知识库集合。

用法：cd backend && uv run python scripts/reset_milvus.py
前提：Milvus standalone 已启动（backend/docker-compose.yml）。
脚本幂等：集合不存在时直接成功。
"""
import os
import sys

# 脚本直跑时 sys.path 只有 scripts/，手动加入 backend/ 才能导入 app 包
_BACKEND_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
os.chdir(_BACKEND_ROOT)
sys.path.insert(0, os.path.abspath(_BACKEND_ROOT))

from pymilvus import MilvusClient

from app.config.settings import get_settings

collection = "law_chunks"
client = MilvusClient(uri=get_settings().milvus_uri)
if client.has_collection(collection):
    client.drop_collection(collection)
    print(f"dropped collection: {collection}")
else:
    print(f"collection not exists (nothing to do): {collection}")
