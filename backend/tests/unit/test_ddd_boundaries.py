"""DDD 分层边界守护测试。

为什么用测试守护架构：分层规则若只写在文档里，会随迭代悄悄腐化；
本测试在每次 pytest 时对 app/ 全部源码做 AST 扫描，任何违例
（领域层引入技术库、应用层直连基础设施、langgraph 泄漏出 agent/ 等）
都会导致测试失败，把架构约束变成可执行的规则。
"""

import ast
import pathlib

# backend/app 目录（本文件位于 backend/tests/unit/）
APP_ROOT = pathlib.Path(__file__).resolve().parents[2] / "app"

# 领域层/应用层禁止引入的技术库；pydantic 仅允许 API 层 DTO 使用
# BE-024 起数据库技术栈为 SQLAlchemy（aiosqlite 仅作为其 SQLite 异步驱动，
# 同样禁止在领域层/应用层直接导入），两者都在守护名单内
# BE-028 起关键词检索技术栈为 jieba/rank_bm25，只允许出现在 infrastructure
_TECH_LIBS = {
    "fastapi", "httpx", "chromadb", "sqlalchemy", "aiosqlite", "pypdf",
    "langgraph", "pydantic", "pydantic_settings", "uvicorn",
    "jieba", "rank_bm25",
}

# 全项目只允许在 app/agent/ 内导入 langgraph（工作流引擎隔离区）
_LANGGRAPH_ALLOWED_PREFIX = "agent"


def _imports_of(path: pathlib.Path) -> set[str]:
    """提取文件的全部顶层导入（import a / from a.b 均取首段）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def _module_refs(path: pathlib.Path) -> list[str]:
    """提取全部 from app.xxx 的完整模块路径。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    refs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            refs.append(node.module)
    return refs


def _iter_app_files():
    yield from APP_ROOT.rglob("*.py")


def test_domain_layer_has_no_technology_dependencies() -> None:
    """领域层必须零技术依赖：实体、端口、业务规则不绑定任何框架。"""
    violations = []
    for py in _iter_app_files():
        rel = py.relative_to(APP_ROOT).as_posix()
        if not rel.startswith("domain/"):
            continue
        hits = _imports_of(py) & _TECH_LIBS
        if hits:
            violations.append(f"{rel}: {sorted(hits)}")
        # 领域层不得依赖应用层（业务规则是被依赖方，不是依赖方）
        for ref in _module_refs(py):
            if ref.startswith("app.application"):
                violations.append(f"{rel}: 依赖了应用层 {ref}")
    assert not violations, "领域层出现技术依赖或反向依赖：\n" + "\n".join(violations)


def test_application_and_api_do_not_import_infrastructure() -> None:
    """应用层/API 层只能依赖领域端口，禁止直连基础设施实现。"""
    violations = []
    for py in _iter_app_files():
        rel = py.relative_to(APP_ROOT).as_posix()
        if not rel.startswith(("application/", "api/")):
            continue
        for ref in _module_refs(py):
            if ref.startswith("app.infrastructure"):
                violations.append(f"{rel}: {ref}")
    assert not violations, "应用层/API 层直连基础设施：\n" + "\n".join(violations)


def test_application_layer_has_no_technology_dependencies() -> None:
    """应用层禁止技术库：编排逻辑经领域端口工作，引擎细节不属于此层。"""
    violations = []
    for py in _iter_app_files():
        rel = py.relative_to(APP_ROOT).as_posix()
        if not rel.startswith("application/"):
            continue
        hits = _imports_of(py) & _TECH_LIBS
        if hits:
            violations.append(f"{rel}: {sorted(hits)}")
    assert not violations, "应用层出现技术依赖：\n" + "\n".join(violations)


def test_langgraph_confined_to_agent_module() -> None:
    """langgraph 只允许出现在 app/agent/ 内（工作流引擎隔离区）。"""
    violations = []
    for py in _iter_app_files():
        rel = py.relative_to(APP_ROOT).as_posix()
        if "langgraph" in _imports_of(py) and not rel.startswith(_LANGGRAPH_ALLOWED_PREFIX):
            violations.append(rel)
    assert not violations, "langgraph 泄漏出 agent 隔离区：\n" + "\n".join(violations)
