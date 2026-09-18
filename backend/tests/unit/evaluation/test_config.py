"""BE-049 Judge 与 Milvus 隔离配置测试。"""

from app.config.settings import Settings
from app.containers import build_evaluation_judge_provider, create_container
from app.domain.repositories.vector_store import VectorStore


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


def test_custom_collection_is_passed_to_milvus_adapter() -> None:
    settings = Settings(milvus_collection_name="law_agent_eval_test", _env_file=None)  # type: ignore[call-arg]
    container = create_container(settings)

    store = container.resolve(VectorStore)

    assert store._collection_name == "law_agent_eval_test"
