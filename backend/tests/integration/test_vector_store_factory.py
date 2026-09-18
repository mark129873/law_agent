"""向量库 Provider 工厂测试（BE-029）。

为什么这样测试：工厂的职责是"按配置解析出对应实现并保证单例"。
通过仅修改配置构造不同容器，验证工厂解析行为；真实 Milvus 读写
行为由 test_milvus_vector_store.py 在服务可达时覆盖。
"""

from app.config.settings import Settings
from app.containers import create_container
from app.domain.repositories.vector_store import VectorStore
from app.infrastructure.vector_store.milvus import MilvusVectorStore


def test_factory_resolves_milvus_by_default() -> None:
    """默认配置应解析出 MilvusVectorStore 单例（构造不建连，无外部依赖）。"""
    container = create_container(Settings(_env_file=None))  # type: ignore[call-arg]
    store = container.resolve(VectorStore)
    assert isinstance(store, MilvusVectorStore)
    store2 = container.resolve(VectorStore)
    assert store is store2  # 容器保证单例


def test_factory_respects_custom_uri() -> None:
    """Endpoint 与 token 应透传到 Milvus 实现（部署地址切换只改配置）。"""
    settings = Settings(
        milvus_uri="https://cloud.example",
        milvus_token="cloud-api-key",
        _env_file=None,
    )  # type: ignore[call-arg]
    store = create_container(settings).resolve(VectorStore)
    assert isinstance(store, MilvusVectorStore)
    assert store._uri == "https://cloud.example"
    assert store._token == "cloud-api-key"
