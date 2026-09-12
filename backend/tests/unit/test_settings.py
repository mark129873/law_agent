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
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.db_provider is DbProvider.SQLITE
    assert settings.vector_store_provider is VectorStoreProvider.MILVUS
    assert settings.milvus_uri == "http://127.0.0.1:19530"
    assert settings.llm_provider is LlmProvider.OLLAMA
    # BE-027：日志默认 INFO（保证"重要业务事件"默认可见），并落盘 backend/log/
    assert settings.log_level == "INFO"
    assert settings.log_dir == "log"
    assert settings.log_file_name == "app.log"
    assert settings.log_backup_count == 30


def test_providers_switchable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """仅通过环境变量即可切换 Provider，模拟未来切换 mysql/glm 的场景。"""
    monkeypatch.setenv("DB_PROVIDER", "mysql")
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("MILVUS_URI", "http://127.0.0.1:19531")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.db_provider is DbProvider.MYSQL
    assert settings.llm_provider is LlmProvider.GLM
    assert settings.milvus_uri == "http://127.0.0.1:19531"


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
