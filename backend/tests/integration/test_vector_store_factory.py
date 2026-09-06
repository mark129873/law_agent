"""向量库 Provider 工厂测试（BE-008）。

为什么这样测试：BE-008 的验收标准是"配置和架构可以表达
Chroma/Milvus Provider，核心 RAG 代码不存在 Chroma 强耦合"。
通过仅修改配置构造不同容器，验证工厂能解析出对应实现，
且 Milvus 骨架在使用时给出明确错误而不是静默失败。
"""

import pytest

from app.containers import create_container
from app.domain.repositories.vector_store import VectorStore
from app.infrastructure.vector_store.chroma import ChromaVectorStore
from app.infrastructure.vector_store.milvus import MilvusVectorStore
from app.config.settings import Settings


def _make_container(provider: str, tmp_path=None):
    """按 Provider 构造最小容器，模拟"只改配置切换 Provider"。"""
    kwargs = {"vector_store_provider": provider, "_env_file": None}
    if tmp_path is not None:
        kwargs["chroma_persist_dir"] = str(tmp_path / "chroma")
    return create_container(Settings(**kwargs))  # type: ignore[arg-type]


def test_factory_resolves_chroma_by_config(tmp_path) -> None:
    """默认配置应解析出可用的 ChromaVectorStore。"""
    container = _make_container("chroma", tmp_path)
    store = container.resolve(VectorStore)
    assert isinstance(store, ChromaVectorStore)
    # 与具体实现类型无关的可用性验证：抽象接口可直接工作
    store2 = container.resolve(VectorStore)
    assert store is store2  # 容器保证单例


def test_factory_resolves_milvus_skeleton_by_config() -> None:
    """milvus 配置应能解析出骨架实例（装配成功、实现未提供）。"""
    container = _make_container("milvus")
    store = container.resolve(VectorStore)
    assert isinstance(store, MilvusVectorStore)


@pytest.mark.asyncio
async def test_milvus_skeleton_fails_loudly_on_use() -> None:
    """Milvus 骨架调用时应抛出明确异常，而不是静默返回空结果。"""
    container = _make_container("milvus")
    store = container.resolve(VectorStore)
    with pytest.raises(NotImplementedError, match="尚未实现"):
        await store.initialize()
