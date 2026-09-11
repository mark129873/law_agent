# 干净收尾状态检查清单

- 执行`init.md`的内容, 确保项目可正常构建或启动, 保证下一轮会话可以直接运行项目
- 测试先根据 docs/RELIABILITY.md 进行测试干净环境管理, 再确认所有测试通过, 包括但不限于: 
  - 单元测试
  - 集成测试
  - 接口测试
  - 端到端测试
- progress.md 记录到当前会话的进度
- feature_list.json 功能状态与实际开发进度一致, 真实反映 passing 和未验证的边界
- session-handoff.md 确认记录当前会话的交接摘要
- 没有任何半成品步骤处于未记录状态

- 检查代码仓库状态
    - git 状态中无意外新增文件
    - 没有提交敏感文件（.env、密钥凭证）
    - `dist` ,` node_modules`, `data` 目录文件未被提交; `backend/log` 日志目录未被提交