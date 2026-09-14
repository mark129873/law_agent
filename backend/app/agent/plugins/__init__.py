"""Plugin / Skill 包：一期仅 Stub（设计 §16，BE-037）。

后续二期把 Stub 替换为 plugin / skill runtime，主图路由接口不变。
"""

from app.agent.plugins.plugin_entry_node import PluginEntryNode
from app.agent.plugins.plugin_stub_node import PluginStubNode

__all__ = ["PluginEntryNode", "PluginStubNode"]
