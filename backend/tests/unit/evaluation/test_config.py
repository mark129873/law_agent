"""BE-049 Judge、Milvus 与真实质量评测边界测试。"""

import pytest

from app.config.settings import JudgeProvider, Settings
from app.containers import build_evaluation_judge_provider, create_container
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.evaluation.runner import validate_real_rag_evaluation_settings
from app.infrastructure.llm.deepseek import DeepSeekProvider


class PrimaryFake:
    model_name = "primary-fake"


def test_judge_defaults_to_the_primary_provider() -> None:
    primary = PrimaryFake()
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.eval_judge_provider is JudgeProvider.FOLLOW
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


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"llm_provider": "ollama"}, "DeepSeek"),
        ({"eval_judge_provider": "ollama"}, "follow 或 deepseek"),
        ({"eval_judge_provider": "glm"}, "follow 或 deepseek"),
        ({"rerank_enabled": False}, "Reranker"),
    ],
)
def test_real_rag_evaluation_rejects_non_baseline_settings(overrides: dict[str, object], message: str) -> None:
    """真实质量评测不得悄悄切到 Ollama/GLM 或关闭精排。"""
    settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]

    with pytest.raises(ValueError, match=message):
        validate_real_rag_evaluation_settings(settings)


def test_real_rag_evaluation_allows_deepseek_follow_or_separate_judge() -> None:
    """follow 与独立 DeepSeek Judge 都属于当前质量评测基线。"""
    for judge_provider in ("follow", "deepseek"):
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            llm_provider="deepseek",
            eval_judge_provider=judge_provider,
            rerank_enabled=True,
        )

        validate_real_rag_evaluation_settings(settings)
