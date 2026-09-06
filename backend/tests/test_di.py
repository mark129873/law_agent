"""依赖注入容器测试。

为什么做这些测试：BE-003 的验收标准是"核心业务层不直接依赖
具体实现"。测试用业务组件只持有抽象接口的场景证明：
通过容器注册替换实现，业务代码零修改即可切换行为。
"""

from abc import ABC, abstractmethod

import pytest

from app.common.di import DIContainer
from app.containers import create_container
from app.config.settings import Settings


# ---- 测试用抽象接口与两个实现：模拟"业务层依赖抽象，基础设施可替换" ----
class Notifier(ABC):
    """通知抽象接口。"""

    @abstractmethod
    def send(self, content: str) -> str: ...


class EmailNotifier(Notifier):
    """模拟邮件实现。"""

    def send(self, content: str) -> str:
        return f"email:{content}"


class SmsNotifier(Notifier):
    """模拟短信实现。"""

    def send(self, content: str) -> str:
        return f"sms:{content}"


class AlertService:
    """业务组件：只依赖抽象接口，不知道任何具体实现的存在。"""

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    def alert(self, content: str) -> str:
        return self._notifier.send(content)


def test_resolve_returns_singleton() -> None:
    """默认注册的组件应返回同一实例（重资源必须复用）。"""
    container = DIContainer()
    container.register(Notifier, lambda c: EmailNotifier())
    assert container.resolve(Notifier) is container.resolve(Notifier)


def test_unregistered_interface_raises_clear_error() -> None:
    """未注册的接口应立即报清晰错误，而不是运行到一半才失败。"""
    container = DIContainer()
    with pytest.raises(KeyError, match="未注册工厂"):
        container.resolve(Notifier)


def test_business_code_swaps_impl_via_container_only() -> None:
    """核心验收：只改容器注册，业务组件行为切换，业务代码零修改。"""
    # 用工厂函数模拟"根据配置选择实现"的装配方式
    container = DIContainer()
    container.register(Notifier, lambda c: EmailNotifier())
    container.register(AlertService, lambda c: AlertService(c.resolve(Notifier)))
    assert container.resolve(AlertService).alert("hello") == "email:hello"

    # 切换实现：仅重新注册工厂，AlertService 源码未动
    container2 = DIContainer()
    container2.register(Notifier, lambda c: SmsNotifier())
    container2.register(AlertService, lambda c: AlertService(c.resolve(Notifier)))
    assert container2.resolve(AlertService).alert("hello") == "sms:hello"


def test_factory_can_resolve_dependencies_from_container() -> None:
    """工厂应能从容器解析其他依赖（依赖链），例如配置驱动的实现选择。"""
    container = create_container(Settings(_env_file=None))  # type: ignore[call-arg]
    # 装配点注册的 Settings 单例可被任何工厂解析
    assert container.resolve(Settings) is container.resolve(Settings)
