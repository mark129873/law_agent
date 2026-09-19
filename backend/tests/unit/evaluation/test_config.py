"""BE-049 Judge 与 Milvus 配置测试。"""

from app.config.settings import Settings
from app.containers import build_evaluation_judge_provider, create_container
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.infrastructure.llm.deepseek import DeepSeekProvider


class PrimaryFake:
    model_name = "primary-fake"


def test_judge_defaults_to_the_primary_provider() -> None:
    primary = PrimaryFake()
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert build_evaluation_judge_provider(settings, primary) is primary


def test_judge_can_use_a_separate_ollama_model_without_network_call() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        eval_judge_provider="ollama",
        eval_judge_model="judge-model",
    )

    judge = build_evaluation_judge_provider(settings, PrimaryFake())

    assert judge.model_name == "judge-model"


def test_container_can_select_deepseek_provider_without_network_call() -> None:
    """主 LLM 选择 DeepSeek 时，容器应构造对应适配器而不是发起网络请求。"""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_provider="deepseek",
        deepseek_api_key="test-key",
        deepseek_model="deepseek-test",
        milvus_cloud_uri="https://cloud.example",
    )

    provider = create_container(settings).resolve(LLMProvider)

    assert isinstance(provider, DeepSeekProvider)
    assert provider.model_name == "deepseek-test"


def test_custom_collection_is_passed_to_milvus_adapter() -> None:
    settings = Settings(
        milvus_cloud_uri="https://cloud.example",
        milvus_collection_name="test_collection",
        _env_file=None,
    )  # type: ignore[call-arg]
    container = create_container(settings)

    store = container.resolve(VectorStore)

    assert store._collection_name == "test_collection"
