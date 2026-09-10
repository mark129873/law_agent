# init.md -- 开始工作前，请验证项目可以正常无报错构建。

- 如果存在后端项目, 验证后端项目可以正常构建与运行:
  - 启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
  - 验证：`cd backend && uv run pytest`（全量 98 个自动化测试）；启动后 `curl http://127.0.0.1:8000/api/health`
- 如果存在前端项目, 验证前端项目可以正常构建与运行:
  - 构建：`cd frontend && npm install && npm run build`（tsc 类型检查 + vite 打包）
  - 启动：`cd frontend && npm run dev`（http://localhost:5173，/api 代理到后端 8000；联调需先启动后端）

- 检测AGENTS.md, progress.md, feature_list.json, clean-state-checklist.md, session-handoff.md 是否存在
- 检测docs/ARCHITECTURE.md, docs/PRODUCT.md, docs/RELIABILITY.md 是否存在
-  如果上述文件均存在, 则 echo "=== Init完成. 所有检查通过. ==="
-  如果上述文件中存在缺失, 则 echo "=== Init完成. 有缺失文件. ==="
