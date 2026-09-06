"""轻量依赖注入容器。

为什么自己实现而不是引入 DI 框架：本项目需要注入的组件只有
数据库、向量库、LLM 三类 Provider，一个百行级容器足够；
引入框架反而增加理解成本与依赖负担。
"""

from __future__ import annotations

import threading
from typing import Any, Callable

# 工厂签名：接收容器本身，便于工厂内部解析其他依赖（依赖链装配）
Factory = Callable[["DIContainer"], Any]


class DIContainer:
    """按抽象接口注册与解析实例的容器。

    为什么按类型（接口）为键：业务代码通过 `resolve(接口)` 获取实现，
    永远不接触具体实现类名，这是依赖倒置的关键。
    """

    def __init__(self) -> None:
        self._factories: dict[type, Factory] = {}
        self._singletons: dict[type, Any] = {}
        # 装配发生在启动期，锁只为防御性保证 resolve 幂等安全
        self._lock = threading.Lock()

    def register(self, interface: type, factory: Factory, *, singleton: bool = True) -> None:
        """为抽象接口注册工厂函数。

        默认单例：数据库连接、LLM 客户端等重资源组件必须复用，
        因此单例是更安全的默认值；需要每次新建的场景显式传 singleton=False。
        """
        self._factories[interface] = factory
        # 重复注册视为装配错误：同一接口出现两个工厂说明装配点有冲突，
        # 应该在启动期暴露而不是静默覆盖。
        if interface in self._singletons:
            del self._singletons[interface]

    def resolve(self, interface: type) -> Any:
        """解析接口对应的实例（单例缓存）。

        为什么不在锁内调用工厂：工厂内部往往会 resolve 其他依赖
        （依赖链装配），而非重入锁在嵌套 resolve 时会自锁死锁；
        因此采用双重检查：查缓存与写缓存加锁，工厂执行放在锁外。
        """
        with self._lock:
            if interface in self._singletons:
                return self._singletons[interface]
            factory = self._factories.get(interface)
            if factory is None:
                raise KeyError(
                    f"接口 {interface.__name__} 未注册工厂；"
                    f"请在 containers.create_container 装配点注册后再使用"
                )
        # 工厂在锁外执行，允许内部递归 resolve 其他依赖
        instance = factory(self)
        with self._lock:
            # 并发场景下另一线程可能已完成构建，setdefault 保证只保留一份
            return self._singletons.setdefault(interface, instance)
