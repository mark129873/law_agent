# 会话交接

## 当前已验证

- 现在明确可用的部分：
  - 数据侧：SQLite（Database 抽象）+ Chroma（VectorStore 抽象）+ Milvus 骨架，全部接入 lifespan 自动初始化。
  - LLM 侧：LLMProvider 抽象 + OllamaProvider（真实调用已验证）+ GLMProvider（协议级验证）。
  - 知识库侧：DocumentParserFactory（TXT/PDF）→ DocumentPipeline → EmbeddingService → KnowledgeIngestionService → VectorStore 全链路，容器装配齐备。
- 这轮实际跑过的验证：
  - `uv run pytest tests -q` → 53 passed
  - Ollama 真实 chat + 流式问答（qwen3.5:9b 覆盖默认模型）
  - 知识库入库端到端：真实 Chroma 检索命中 + 按文档删除
  - 真实启动 smoke：Database/VectorStore initialized，/api/health ok

## 本轮改动

- 新增了哪些代码或行为：
  - BE-009：domain/entities/llm.py、domain/repositories/llm_provider.py、test_llm_provider.py
  - BE-010：infrastructure/llm/ollama.py、glm.py、test_llm_providers.py（MockTransport 协议测试）
  - BE-011：domain/services/document_parser.py、application/services/document_pipeline.py、infrastructure/document_parser/text_parser.py
  - BE-012：infrastructure/document_parser/pdf_parser.py、test_document_parsers.py
  - BE-013：domain/services/embedding.py、infrastructure/embedding/ollama_embedding.py、application/services/knowledge_service.py、test_embedding_ingestion.py
  - 容器新增 LLMProvider/DocumentPipeline/EmbeddingService/KnowledgeIngestionService 注册
- 基础设施或 harness 发生了哪些变化：依赖新增 httpx（主）、pypdf（主）、fpdf2（dev）；配置新增 OLLAMA_EMBEDDING_MODEL；docs/ARCHITECTURE.md 新增第 21-25 节；新增 backend/scripts/verify_ollama_stream.py 验证脚本

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径（环境阻塞，均已记录在 feature_list）：
  - BE-010：GLM 真实调用（缺 GLM_API_KEY）
  - BE-013：真实 Ollama 向量生成（本机 Ollama 未以 --embeddings 启动，报 "This server does not support embeddings"）
- 下一轮会话需要注意的风险：
  - `uv pip install` 进 venv 的包必须同步写入 pyproject.toml，否则 uv sync 会移除（pypdf 教训）
  - RAG API 层尚未存在；BE-014 需要决定检索接口形态（Service → API 分两步走）

## 下一步最佳动作

- 最高优先级未完成功能：BE-014 RAG 检索服务
- 为什么它是下一步：BE-015/016（LangGraph Agent）需要消费检索上下文，BE-014 是 RAG 闭环的最后一层
- 什么结果才算 passing：针对测试知识库查询明确内容，返回相关 chunk 与来源信息，仅依赖抽象接口
- 这一步中哪些东西不要动：Pipeline/Embedding/KnowledgeIngestion 的编排结构；LLM Provider 的 transport 注入接缝；SQLite 提交边界设计

## 命令

- 启动命令：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 验证命令：`cd backend && uv run pytest tests -q`
- 定向调试命令：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；Ollama 流式验证 `PYTHONPATH=backend OLLAMA_MODEL=qwen3.5:9b python backend/scripts/verify_ollama_stream.py`
