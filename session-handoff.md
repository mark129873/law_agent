# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **后端 BE-001~029 全部 passing**（BE-007 Chroma / BE-008 Milvus 骨架 / BE-028 自研 BM25 混合检索已置 deprecated）；**前端 FE-001~012 全部 passing**。
  - **测试体系**：后端自动化 119 个（2026-09-12 全绿）；其中 test_milvus_vector_store.py 5 例需要真实 Milvus（docker compose up -d），服务不可达时自动跳过，其余保持封闭性。
  - **向量库已全面迁移到 Milvus（BE-029）**：单集合稠密(FLOAT_VECTOR/COSINE) + 稀疏(BM25 Function + jieba 分词器)，hybrid_search 由服务端 RRFRanker(k=60) 融合；集合首次入库按 embedding 维度懒建；Chroma 与自研 BM25 索引代码已全部删除。
- 最近一轮实际跑过的验证（2026-09-12，Session 027，BE-029 Milvus 迁移）：
  - 干净环境（删 backend/data + reset_milvus.py）`uv run pytest tests -q` → **119 passed**（含真实 Milvus 5 例）
  - 真实端到端（8013 端口，GLM glm-4.5-air + Ollama nomic-embed-text + 真实 Milvus v3.0.0）：专利法上传 201 ready → 流式问答正确引用第四十二条"二十年" → sources 事件与持久化一致 → 删除文档 204 后集合 count(*)=0
  - Ollama LLM 路径本机仍故障（llama-server 500，已知问题），LLM 侧以 GLM 等价验证

## 本轮改动（Session 027）
- **MilvusVectorStore 完整实现**（backend/app/infrastructure/vector_store/milvus.py）：MilvusClient + asyncio.to_thread/Lock；consistency_level="Strong"（默认 Bounded 下新数据不可见，且 hybrid_search 空结果触发 Milvus 缺陷 #50969 误报 unsupported ID type）；min_score 经稠密请求 range search(radius)，min_score<=0 不加 radius（COSINE range 严格大于会误滤 0 分）；主键结果以字段名 chunk_id 返回
- **端口演进**：VectorStore.search → hybrid_search(query_text, query_embedding, top_k, min_score)（domain/repositories/vector_store.py）
- **服务层简化**：rag_service（删自研 RRF 与 keyword_index）、knowledge_service（删双写）、document_service（删双清）
- **删除**：chroma.py、domain/repositories/keyword_index.py、infrastructure/keyword_index/ 整包、4 个旧测试文件；依赖 chromadb/jieba/rank-bm25 卸载、pymilvus 3.0.1 入列
- **配置**：settings 移除 CHROMA 枚举/chroma_persist_dir/bm25_index_path/HYBRID_SEARCH_ENABLED，默认 milvus；新增回归断言 vector_store_provider=chroma 被拒绝
- **测试**：tests/fakes.py 共享 InMemoryVectorStore（余弦+子串词面+RRF 近似）；test_milvus_vector_store.py 5 例真实服务测试（skip 机制、独立集合名、测后清理）；DDD 边界名单 chromadb/jieba/rank_bm25 → pymilvus
- **运维脚本**：scripts/reset_milvus.py（干净环境重置新增步骤：drop law_chunks 集合）
- **文档**：ARCHITECTURE（§0/1/2/3/4/6/8/9/10 全面改写为 Milvus 混合检索口径）、RELIABILITY（service 清单删 keyword_index；干净环境重置新增 reset_milvus 步骤）、.env.example/.env、feature_list.json、progress.md

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：
  - MySQL 8.0 真实接入（驱动、URL 分支、真实实例集成测试）——只做到"方言无关 + 容器显式拒绝"
  - 连接池化（每请求一会话/连接）——当前仍是单会话
  - 前端本轮未改动（未重跑 `npm run build`；API 契约与 SSE 协议未变）
  - 浏览器 GUI E2E 本轮未执行（后端 API 层 E2E 已用真实服务验证）
  - Ollama LLM 路径（本机 llama-server 崩溃中，恢复后可补验 Ollama Provider 完整链路）
- 下一轮会话需要注意的风险：
  - **启动前置条件变化**：后端启动前 Milvus 必须可达（`cd backend && docker compose up -d`）；容器当前由另一项目目录（code1/milvus）创建的同名容器承载，backend/docker-compose.yml 与其配置一致，`docker compose up -d` 会因容器名冲突报错——直接 `docker start milvus-etcd milvus-minio milvus-standalone` 即可
  - **容器内存上限（2026-09-12，按 4GB WSL2 重新收紧）**：milvus 2GB / etcd 256MB / minio 256MB，合计 2.5GB ≈ VM 的 62%（docker-compose.yml 已定义，并已对运行中容器 docker update 热应用）；若 Milvus 因内存压力被 OOM kill，先检查知识库规模是否已超出 2GB 上限承载，必要时同步调大 .wslconfig 与 mem_limit；注意 WSL 配置改动需 `wsl --shutdown` 重启后才生效
  - **pymilvus import 副作用**：import pymilvus 会 load_dotenv 把 backend/.env 灌入进程环境；新增依赖或测试时注意环境变量污染（敏感配置测试已加 delenv 防御）
  - **Milvus 一致性契约**：生产代码所有 create/search 都显式 Strong，改动检索代码时勿去掉（否则触发 #50969 空结果误报）
  - **测试干净环境流程**：删 `backend/data/` + `uv run python scripts/reset_milvus.py`（两步都要）
  - 既有遗留项：MySQL 未启用、连接池未引入、min_score 默认 0.0、Ollama 0.32.0 崩溃、Git Bash curl 上传中文文件名乱码（用 httpx）
- 下一步最佳动作（需用户决定）：可选产品增强（会话重命名 / 停止按钮 / 深色主题开关 / CORS 收敛 / OllamaProvider 重试）或 MySQL 8.0 接入
- 这一步中哪些东西不要动：后端 API 契约（第 7 节表格与 SSE 协议含 sources）；统一错误结构 {code,message}；前端 api/state 分层；messages.sources 存储格式；`IsoDateTime` ISO-8601 格式；领域层零技术依赖（pymilvus 不得进入 domain，守护测试会拦）；数据落点（SQLite 在 backend/data/，Milvus 在容器卷）；**Milvus 集合 schema 与 Strong 一致性**（BM25 Function 依赖 content 字段名；去掉 Strong 会触发空结果误报）；**RRFRanker k=60 口径**

## 命令
- Milvus 启动：`cd backend && docker compose up -d`（容器名冲突时：`docker start milvus-etcd milvus-minio milvus-standalone`）
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 干净环境重置（RELIABILITY.md，两步）：删除 `backend/data/` + `uv run python scripts/reset_milvus.py`
- 后端验证：`cd backend && uv run pytest`（全量 119 个；Milvus 未启动时 5 例自动跳过）
- 数据落点确认：SQLite `backend/data/law_agent.db`；Milvus 集合 `law_chunks`（容器卷）
- 前端构建/启动：`cd frontend && npm install && npm run build` / `npm run dev`
- 端到端（需 Milvus + Ollama/GLM）：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
