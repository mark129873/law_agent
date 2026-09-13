"""Agent 模块配置（BE-032，设计 §43）。

为什么用 dataclass 而不是 pydantic-settings：Agent 图的配置值统一由
装配点（containers.py）从全局 Settings 构造注入——保持"业务代码经
get_settings() 读取配置、禁止散读环境变量"的项目约定；
AgentConfig 只是图节点的参数对象（Parameter Object 模式），
默认值与设计文档 §43 对齐，测试可直接构造覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    """主图运行参数（设计 §43）。"""

    # 顶层编排最大步数（防死循环，设计强制约束 20；超限强制 finish）
    max_global_steps: int = 4
    # 用户 Web Search 开关默认值（一期 Stub：false 时 web entry 直接 DISABLED）
    web_search_enabled_default: bool = False
    # 插件能力开关（一期恒为 False，Stub 返回 NOT_IMPLEMENTED）
    plugin_enabled: bool = False
