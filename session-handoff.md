# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **后端 BE-001~028 全部 passing**；**前端 FE-001~012 全部 passing**。
  - **测试体系**：后端自动化 134 个（2026-09-12 全绿）；端到端脚本 3 个（依赖本机 Ollama，手工运行）。
  - **RAG 检索现为混合检索（BE-028）**：向量通道（Chroma 语义）+ BM25 关键词通道（jieba + rank_bm25 词面），RRF（k=60）融合；入库双写、删除双清；`HYBRID_SEARCH_ENABLED=false` 可回退纯向量。
- 最近一轮实际跑过的验证（2026-09-12，Session 026，BE-028 混合检索）：
  - 干净环境（先删 `backend/data`）`uv run pytest tests -q` → **134 passed**（基线 117，新增 17）
  - 真实端到端（8013 端口，Ollama qwen3.5:4b + nomic-embed-text）：专利法 TXT 上传 → 29 chunk 双写 → 流式问答正确引用第四十二条"二十年" → sources 事件与持久化一致 → 删除后 BM25 快照归零
  - 回退开关实测（8014，HYBRID_SEARCH_ENABLED=false）：无 KeywordIndex 初始化、纯向量问答正常
  - 本机 Ollama 已恢复（Session 025 期间曾崩溃）：qwen3.5:4b / nomic-embed-text:latest 均可用

## 本轮改动（Session 026）
- **新增领域端口** `KeywordIndex`（backend/app/domain/repositories/keyword_index.py）：与 VectorStore 同构的关键词检索契约
- **新增基础设施实现** `Bm25KeywordIndex`（backend/app/infrastructure/keyword_index/bm25.py）：jieba 分词 + BM25Okapi；词面不相交的 chunk 被排除，小语料 IDF 归零时按命中词数兜底排序；语料快照原子写 `backend/data/bm25_index.json`；阻塞操作经 asyncio.to_thread + 锁
- **RagService 混合检索**：模块级纯函数 `reciprocal_rank_fusion`（RRF k=60，多路命中叠加得分天然去重，单路保序）；min_score 语义不变（仅向量通道）；keyword_index=None 时优雅降级
- **双写/双清**：KnowledgeIngestionService 在向量库写入后写关键词索引（复用 chunk_id）；DocumentService 删除同步清关键词索引（日志新增 keyword_removed_chunks）
- **接线**：settings（HYBRID_SEARCH_ENABLED 默认 true / BM25_INDEX_PATH 锚定 backend/）、containers（工厂 + 开关在装配点判断）、main lifespan（初始化/关闭关键词索引）、DDD 边界守护名单加 jieba/rank_bm25、test_api fixture 增加 bm25 临时路径并保留关键词索引注入
- **依赖**：uv add rank_bm25 jieba（纯 Python）
- **文档**：ARCHITECTURE（§1 技术栈 / §2 目录 / §3 端口清单 / §4 混合检索与双写双清 / §6 配置 / §9 测试统计）、RELIABILITY（service 清单新增 keyword_index）、.env.example、feature_list.json（BE-028 passing）、progress.md

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：
  - MySQL 8.0 真实接入（驱动、URL 分支、真实实例集成测试、增量迁移方案）——只做到"方言无关 + 容器显式拒绝"
  - 连接池化（每请求一会话/连接）——当前仍是单会话
  - 前端本轮未改动（未重跑 `npm run build`；API 契约与 SSE 协议未变）
  - 浏览器 GUI E2E 本轮未执行（后端 API 层 E2E 已用真实服务验证）
- 下一轮会话需要注意的风险：
  - **BM25 快照与 Chroma 是两份存储**：一致性靠"同目录 + 唯一编排入口"；绕过 API 手工删其一会残留，检索会优雅降级但不自愈，需重传文档或删除对应文档重建
  - **BM25Okapi 每次增删全量重建**：万级 chunk 以上需评估增量索引结构（当前规模无感）
  - **双 uvicorn 实例并存时第二个实例可能因 OpenBLAS 内存分配失败启动崩溃**（本轮实测两次复现，单实例正常；环境问题，与本功能代码无关）
  - **测试干净环境流程**（RELIABILITY.md）：开工/收尾测试前删除 `backend/data/`（启动时自动重建，含 bm25_index.json 快照）
  - ORM 维护面、同一 created_at 无第二排序键、Ollama 0.32.0 偶发缺陷等遗留项同前（本轮未触碰）
  - min_score 默认 0.0；E2E 脚本依赖本机 Ollama 与 .env 中 GLM_API_KEY
  - Git Bash 下 curl 上传中文文件名会 GBK 乱码：用 `uv run python` + httpx 以 UTF-8 上传

## 下一步最佳动作
- 若继续做检索方向：混合检索参数化调优（RRF k、每路 fetch 深度、中文停用词表）或加检索单元级评测集（问题→期望命中 chunk 的回归评测）
- 若继续做数据库方向：MySQL 8.0 接入（`uv add aiomysql` → `containers.py` URL 分支 → 真实实例跑同一批契约测试 → Alembic autogenerate）
- 可选产品增强（需用户决定）：会话重命名（需 PATCH 端点）、回答停止按钮（需取消协议）、深色主题手动开关、部署方案与 CORS 收敛、OllamaProvider 加重试
- 这一步中哪些东西不要动：后端 API 契约（ARCHITECTURE.md 第 7 节表格与 SSE 协议含 sources）；统一错误结构 {code,message}；前端 api/state 分层与主题 token 体系；messages.sources 的存储格式；`IsoDateTime` 的 ISO-8601 存储格式；领域层零技术依赖（jieba/rank_bm25 与 ORM 模型一样不得进入 domain，守护测试会拦）；**数据存放位置**（保持 `backend/data/`）；**RRF 融合对 chunk_id 一致性的依赖**（关键词索引必须复用向量库生成的 chunk_id，别改双写顺序）

## 命令
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 干净环境重置（RELIABILITY.md 规定，测试前后各做一次）：删除 `backend/data/`（启动时会自动重建，含 bm25_index.json 快照位置）
- 后端验证：`cd backend && uv run pytest`（全量 134 个）；分层：`pytest tests/unit` / `pytest tests/integration`
- 数据落点确认：`Get-ChildItem backend\data -Force`（应看到 `law_agent.db`、`chroma\`、`bm25_index.json`）
- 前端构建：`cd frontend && npm install && npm run build`（tsc 类型检查 + vite）
- 前端启动：`cd frontend && npm run dev`（http://localhost:5173，/api 代理到后端 8000；联调需先启动后端）
- 端到端（需本机 Ollama）：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
