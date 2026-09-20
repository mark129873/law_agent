"""向量库 Provider 工厂测试（BE-029/BE-050）。

为什么这样测试：工厂的职责是"按配置解析出对应实现并保证单例"。
通过仅修改配置构造不同容器，验证工厂解析行为；真实 Milvus 读写
行为由 test_milvus_vector_store.py 在服务可达时覆盖。
"""

import pytest

from app.config.settings import Settings
from app.containers import create_container
from app.domain.repositories.vector_store import VectorStore
from app.infrastructure.vector_store.milvus import MilvusVectorStore


def test_factory_resolves_milvus_by_default() -> None:
    """默认 Provider 是云端，配置 Endpoint 后可解析 Milvus 单例（构造不建连）。"""
    container = create_container(
        Settings(milvus_cloud_uri="https://cloud.example", _env_file=None)  # type: ignore[call-arg]
    )
    store = container.resolve(VectorStore)
    assert isinstance(store, MilvusVectorStore)
    store2 = container.resolve(VectorStore)
    assert store is store2  # 容器保证单例


def test_factory_respects_custom_uri() -> None:
    """Endpoint 与 token 应透传到 Milvus 实现（部署地址切换只改配置）。"""
    settings = Settings(
        milvus_cloud_uri="https://cloud.example",
        milvus_cloud_token="cloud-api-key",
        _env_file=None,
    )  # type: ignore[call-arg]
    store = create_container(settings).resolve(VectorStore)
    assert isinstance(store, MilvusVectorStore)
    assert store._uri == "https://cloud.example"
    assert store._token == "cloud-api-key"


def test_factory_rejects_missing_selected_uri() -> None:
    """默认云端但未配置云端 URI 时，应给出配置错误而非猜测本地服务。"""
    settings = Settings(milvus_cloud_uri="", _env_file=None)  # type: ignore[call-arg]

    with pytest.raises(ValueError, match="MILVUS_PROVIDER=cloud"):
        create_container(settings).resolve(VectorStore)
