# init.md -- 开始工作前，请验证项目可以正常无报错构建。

1. 如果此次更新后端项目, 则验证后端项目可以正常构建与运行:
  - 默认使用 Milvus Cloud：确认 `backend/.env` 已配置 `MILVUS_CLOUD_URI` 和 `MILVUS_CLOUD_TOKEN`，再运行项目外部服务 smoke 或启动后端验证连接。
  - 只有切换到本地 standalone 时才启动 Milvus：
    `cd backend && docker compose up -d`
    （若容器已存在但已停止，容器名会冲突，改用：`docker start milvus-etcd milvus-minio milvus-standalone`）
    就绪确认：`curl http://127.0.0.1:9091/healthz` 返回 OK
  - 启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`

2. 如果此次更新前端项目, 则验证前端项目可以正常构建与运行:
  - 构建：`cd frontend && npm install && npm run build`
  - 启动：`cd frontend && npm run dev`（http://localhost:5173，/api 代理到后端 8000；联调需先启动后端）

3. 检测AGENTS.md, progress.md, feature_list.json, clean-state-checklist.md, session-handoff.md 是否存在
4. 检测docs/ARCHITECTURE.md, docs/PRODUCT.md, docs/RELIABILITY.md 是否存在
5. 如果上述文件均存在, 则 echo "=== Init完成. 所有检查通过. ===", 如果上述文件中存在缺失, 则 echo "=== Init完成. 有缺失文件. ==="
