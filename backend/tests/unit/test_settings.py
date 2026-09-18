"""配置管理测试。

为什么做这些测试：BE-002 的验收标准是"通过配置切换 Provider 而无需修改
业务代码"，因此必须验证默认值、环境变量覆盖和非法配置拒绝三种行为；
测试直接构造 Settings 实例（绕过 lru_cache），避免用例之间互相污染。
"""

import pathlib

import pytest
from pydantic import ValidationError

from app.config.settings import (
    DbProvider,
    LlmProvider,
    Settings,
    VectorStoreProvider,
)


def test_default_settings_use_current_generation_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认配置应指向当前 Provider 代际：sqlite + milvus + ollama。"""
    # 测试进程可能由 conftest 注入 LOG_DIR（隔离测试产物），此处清除以断言真实默认值
    monkeypatch.delenv("LOG_DIR", raising=False)
    # pymilvus 导入时会 load_dotenv 把 backend/.env 写进进程环境（BE-029 引入），
    # .env 的 LLM_PROVIDER 会污染 _env_file=None 的默认值断言，一并清除
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    for name in ("MILVUS_CLOUD_URI", "MILVUS_CLOUD_TOKEN", "MILVUS_URI", "MILVUS_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.db_provider is DbProvider.SQLITE
    assert settings.vector_store_provider is VectorStoreProvider.MILVUS
    assert settings.milvus_uri == "http://127.0.0.1:19530"
    assert settings.milvus_token == ""
    assert settings.llm_provider is LlmProvider.OLLAMA
    # BE-027：日志默认 INFO（保证"重要业务事件"默认可见），并落盘 backend/log/
    assert settings.log_level == "INFO"
    assert settings.log_dir == "log"
    assert settings.log_file_name == "app.log"
    assert settings.log_backup_count == 30


def test_providers_switchable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """仅通过环境变量即可切换 Provider，模拟未来切换 mysql/glm 的场景。"""
    monkeypatch.delenv("MILVUS_CLOUD_URI", raising=False)
    monkeypatch.delenv("MILVUS_CLOUD_TOKEN", raising=False)
    monkeypatch.setenv("DB_PROVIDER", "mysql")
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("MILVUS_URI", "http://127.0.0.1:19531")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.db_provider is DbProvider.MYSQL
    assert settings.llm_provider is LlmProvider.GLM
    assert settings.milvus_uri == "http://127.0.0.1:19531"


def test_milvus_cloud_config_takes_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    """云端 URI/API Key 优先于旧的本地 standalone 配置。"""
    monkeypatch.setenv("MILVUS_URI", "http://127.0.0.1:19530")
    monkeypatch.setenv("MILVUS_TOKEN", "local-token")
    monkeypatch.setenv("MILVUS_CLOUD_URI", "https://cloud.example")
    monkeypatch.setenv("MILVUS_CLOUD_TOKEN", "cloud-api-key")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.milvus_uri == "https://cloud.example"
    assert settings.milvus_token == "cloud-api-key"


def test_sensitive_config_from_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """GLM_API_KEY 必须来自环境变量，默认值为空且不落盘。

    为什么先 delenv：pymilvus 在 import 时会调用 load_dotenv 把
    backend/.env 整体灌入进程环境（第三方行为），导致即使
    _env_file=None 也会从 os.environ 读到 .env 里的真实密钥；
    本用例验证的是"未提供环境变量时默认为空"，因此先清除。
    """
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.glm_api_key == ""
    monkeypatch.setenv("GLM_API_KEY", "test-secret-key")
    settings_with_key = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings_with_key.glm_api_key == "test-secret-key"


def test_invalid_provider_rejected() -> None:
    """非法 Provider 取值应在构造配置时立即失败，而不是运行中段才暴露。"""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, db_provider="oracle")  # type: ignore[call-arg]


def test_removed_chroma_provider_rejected() -> None:
    """BE-029 起 Chroma 已删除：旧配置值必须在启动时被拒绝而不是静默生效。"""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vector_store_provider="chroma")  # type: ignore[call-arg]


def test_llm_thinking_disabled_by_default_and_switchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """思考模式默认关闭（降低推理模型首字延迟），且可通过环境变量开启。"""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_enable_thinking is False
    monkeypatch.setenv("LLM_ENABLE_THINKING", "true")
    settings_enabled = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings_enabled.llm_enable_thinking is True


def test_log_dir_relative_path_anchored_to_backend() -> None:
    """日志目录相对路径必须锚定 backend/（不随进程工作目录漂移）。"""
    backend_root = pathlib.Path(__file__).resolve().parents[2]
    # 显式传入相对路径，避免 conftest 注入的 LOG_DIR 覆盖本用例意图
    settings = Settings(log_dir="log", _env_file=None)  # type: ignore[call-arg]
    assert pathlib.Path(settings.resolved_log_dir) == backend_root / "log"


def test_langfuse_disabled_by_default_and_keys_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """BE-043：Langfuse 默认关闭、密钥为空（关闭=零导入零开销）。"""
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)  # pymilvus load_dotenv 会灌入 .env 值
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.langfuse_enabled is False
    assert settings.langfuse_public_key == ""
    assert settings.langfuse_secret_key == ""
    assert settings.langfuse_base_url == "https://cloud.langfuse.com"


def test_langfuse_enabled_switchable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """开关经 .env/环境变量生效（用户要求的 .env 配置口径）。"""
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://jp.cloud.langfuse.com")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.langfuse_enabled is True
    assert settings.langfuse_base_url == "https://jp.cloud.langfuse.com"
    assert settings.langfuse_public_key == "pk-lf-test"


def test_tavily_defaults_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tavily 配置默认使用 Remote MCP、basic 深度和 5 条结果。"""
    for name in ("TAVILY_API_KEY", "TAVILY_MCP_URL", "TAVILY_SEARCH_DEPTH", "TAVILY_MAX_RESULTS"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.tavily_mcp_url == "https://mcp.tavily.com/mcp/"
    assert settings.tavily_api_key == ""
    assert settings.tavily_search_depth == "basic"
    assert settings.tavily_max_results == 5

    monkeypatch.setenv("TAVILY_MCP_URL", "https://example.test/mcp")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("TAVILY_SEARCH_DEPTH", "advanced")
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "8")
    overridden = Settings(_env_file=None)  # type: ignore[call-arg]
    assert overridden.tavily_mcp_url == "https://example.test/mcp"
    assert overridden.tavily_api_key == "tvly-test"
    assert overridden.tavily_search_depth == "advanced"
    assert overridden.tavily_max_results == 8


def test_tavily_max_results_is_bounded() -> None:
    """避免一次请求把远程结果量配置到不可控范围。"""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tavily_max_results=4)  # type: ignore[call-arg]
