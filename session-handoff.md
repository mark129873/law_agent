# 会话交接

## 当前已验证

- 现在明确可用的部分：
  - 数据侧：Database 抽象 + SQLite 实现（lifespan 自动建库）；VectorStore 抽象 + Chroma 实现（cosine 空间，lifespan 自动初始化）；Milvus 骨架（配置可表达，调用明确报错）。
  - DI：单一装配点 containers.py，Database/VectorStore 均按配置注册工厂，业务代码只依赖抽象接口。
- 这轮实际跑过的验证：
  - `uv run pytest tests -q` → 28 passed
  - 真实启动：`curl /api/health` → ok，日志依次出现 "Database initialized"、"VectorStore initialized"
  - VECTOR_STORE_PROVIDER=milvus 时 initialize 抛出明确 NotImplementedError

## 本轮改动

- 新增了哪些代码或行为：
  - BE-006：domain/entities/chunk.py、domain/repositories/vector_store.py、test_vector_store_abstraction.py（内存 Fake）
  - BE-007：infrastructure/vector_store/chroma.py、test_chroma_vector_store.py
  - BE-008：infrastructure/vector_store/milvus.py、test_vector_store_factory.py、containers.py 注册 VectorStore、main.py lifespan 初始化向量库
- 基础设施或 harness 发生了哪些变化：依赖新增 chromadb 1.x；docs/ARCHITECTURE.md 新增第 18-20 节

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：Chroma 多进程并发写入；Milvus 完整实现（预留）；embedding 生成（BE-013）
- 下一轮会话需要注意的风险：
  - 本机 Ollama 现有模型 qwen3.5:9b；默认模型配置已是 qwen3.5:4b，BE-010 真实调用验证前需 `ollama pull qwen3.5:4b`
  - GLM_API_KEY 未设置（BE-010 的 GLM 真实调用验证可能受阻，可用协议级测试 + 环境变量注入）
  - `cd xxx && uv run pytest` 复合命令偶发挂起（疑似 shell 权限确认），用 `uv sync --project` 与 python os.chdir 规避

## 下一步最佳动作

- 最高优先级未完成功能：BE-009 LLM Provider 抽象层
- 为什么它是下一步：BE-010（Ollama/GLM 实现）、BE-015/016（LangGraph Agent）都依赖统一 LLM 接口
- 什么结果才算 passing：Agent 可通过统一 LLM 接口调用模型，能独立替换具体 LLM Provider，接口有测试证据
- 这一步中哪些东西不要动：VectorStore/Database 的抽象契约与提交边界设计；di.py 双重检查锁；容器工厂分支结构

## 命令

- 启动命令：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 验证命令：`cd backend && uv run pytest tests -q`
- 定向调试命令：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`
