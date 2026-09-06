优化 docs/RELIABILITY.md 与 AGENTS.md（ARCHITECTURE.md 和 PRODUCT.md 不动）

## 一、重写 docs/RELIABILITY.md（与实际实现对齐）

1. **日志基础设施**（补事实）：实现位置 `backend/app/common/logging.py`；单行 JSON 字段结构 `{timestamp, level, service, message, data}`；uvicorn 自身日志归一为同格式；`LOG_LEVEL` 环境变量控制、默认 ERROR（保留现有等级表）
2. **各服务日志埋点**（对齐真实代码，替换不存在的 QaService）：
   - DocumentService：upload started/completed/failed（含 document_id/filename/chunk_count）
   - KnowledgeIngestionService：ingestion started/completed
   - DocumentPipeline：processing started/completed
   - RagService：retrieval completed（query_length/hit_count/top_score）
   - ChatService：stream failed/completed（answer_length）
   - Agent：generate started/completed（model/answer_length）
   - ConversationService：created/deleted（removed_messages）
   - API 层：Business error（code/detail）/Unexpected error（兜底 500）
   - system：Application configured / Database initialized / VectorStore initialized
3. **日志禁区**（新增）：密钥（GLM_API_KEY）禁止进日志；extra 键禁止使用 LogRecord 保留字段（message/filename 等——记录真实踩坑：曾导致业务 404 变 500），原因与规避方式
4. **干净环境章节**：保留原内容，补 clean-state-checklist.md 具体路径

## 二、AGENTS.md 四处小改（其余内容原样保留，含你新加的前端代码规范与测试收尾清单）

1. 启动工作流程 3 行 `--` 前缀改为 `-`（格式统一）
2. 功能完成定义中 `"pass"` 改为 `"passing"`（与 feature_list.json status_legend 术语一致）
3. 测试数据源路径 `tests/data_source/` 改为 `backend/tests/data_source/`
4. 启动工作流程补一行标准命令：
   - 启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - 验证：`cd backend && uv run pytest`（全量 83 个测试）

## 三、验证与提交

- 无代码改动，无需跑测试；改完自查两个文件的 Markdown 渲染与内容一致性
- 提交信息：`docs: align RELIABILITY.md with actual logging implementation; fix AGENTS.md inconsistencies`