# RAG 评测历史基线（旧版隔离配置）

> 本报告生成于评测改为复用当前知识库之前。旧版运行使用了独立集合和 SQLite
> 路径；当前实现已改为跟随 `Settings` 的业务配置，因此本报告仅作历史记录，
> 不作为当前共享知识库配置的质量基线。

## 运行范围

- 日期：2026-09-18
- 数据源：`backend/tests/data_source/` 当前保留的 5 份法律文档
- 数据集：`backend/tests/evaluation/rag_cases.jsonl`，23 条案例
- 旧版 Milvus 集合：`law_agent_eval`（当时与正式集合 `law_chunks` 隔离）
- 主模型/Judge：GLM `glm-4.5-air`
- Embedding：`nomic-embed-text:latest`
- Reranker：`cross-encoder/ms-marco-MiniLM-L-6-v2`，CPU

## 工作流直调结果

报告目录：`backend/log/evaluation/20260918T132908Z-cabbe758/`

| 指标 | 结果 |
| --- | ---: |
| 案例总数 | 23 |
| 完成数 | 10 |
| 工作流失败数 | 13 |
| 状态匹配率 | 40.0% |
| grounding 通过率 | 70.0% |
| Judge 通过率 | 20.0% |
| Hit@5 | 90.0% |
| Recall@5 | 90.0% |
| MRR | 0.8333 |
| 引用精确率 | 50.0% |
| 引用召回率 | 80.0% |
| 延迟 P50/P95 | 48,305 / 63,845 ms |

检索指标只对完成的 10 条案例聚合。13 条失败中有 12 条 `ConnectError` 和 1 条 GLM HTTP 400，属于外部模型调用不稳定，不能当作检索质量通过或失败的证据；因此 BE-049 仍保持 `in_progress`，不把这次结果当作质量门禁。

## HTTP/SSE 冒烟

最近一次报告：`backend/log/evaluation/api-smoke-20260918T133249Z-0ddb95/`。

- 有依据案例：SSE 顺序、来源事件、来源持久化、`done` 收尾和错误脱敏全部通过。
- 证据不足案例：允许直接收尾而不产生 `plan`，SSE、错误边界和持久化检查通过。
- 结果：2/2 通过。

## 回归验证

- `uv run pytest tests -q -rs`：254 passed、1 warning；Milvus 集成用例全部执行。
- `uv run pytest tests/unit/evaluation -q -rs`：12 passed。
- `npm run build`、`compileall`、`git diff --check` 通过。

报告原始 JSON/Markdown 保留在 `backend/log/evaluation/`，该目录已被 Git 忽略；本文件只提交脱敏汇总。
