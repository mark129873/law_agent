"""配置管理测试。

为什么做这些测试：BE-002 的验收标准是"通过配置切换 Provider 而无需修改
业务代码"，因此必须验证默认值、环境变量覆盖和非法配置拒绝三种行为；
测试直接构造 Settings 实例（绕过 lru_cache），避免用例之间互相污染。
"""

import pytest
from pydantic import ValidationError

from app.config.settings import (
    DbProvider,
    LlmProvider,
    Settings,
    VectorStoreProvider,
)


def test_default_settings_use_current_generation_providers() -> None:
    """默认配置应指向第一代 Provider：sqlite + chroma + ollama。"""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.db_provider is DbProvider.SQLITE
    assert settings.vector_store_provider is VectorStoreProvider.CHROMA
    assert settings.llm_provider is LlmProvider.OLLAMA
    assert settings.log_level == "ERROR"


def test_providers_switchable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """仅通过环境变量即可切换 Provider，模拟未来切换 mysql/milvus/glm 的场景。"""
    monkeypatch.setenv("DB_PROVIDER", "mysql")
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "milvus")
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.db_provider is DbProvider.MYSQL
    assert settings.vector_store_provider is VectorStoreProvider.MILVUS
    assert settings.llm_provider is LlmProvider.GLM


def test_sensitive_config_from_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """GLM_API_KEY 必须来自环境变量，默认值为空且不落盘。"""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.glm_api_key == ""
    monkeypatch.setenv("GLM_API_KEY", "test-secret-key")
    settings_with_key = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings_with_key.glm_api_key == "test-secret-key"


def test_invalid_provider_rejected() -> None:
    """非法 Provider 取值应在构造配置时立即失败，而不是运行中段才暴露。"""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, db_provider="oracle")  # type: ignore[call-arg]


def test_llm_thinking_disabled_by_default_and_switchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """思考模式默认关闭（降低推理模型首字延迟），且可通过环境变量开启。"""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_enable_thinking is False
    monkeypatch.setenv("LLM_ENABLE_THINKING", "true")
    settings_enabled = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings_enabled.llm_enable_thinking is True
